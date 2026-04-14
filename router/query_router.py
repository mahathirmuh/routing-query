"""
query_router.py — Custom Query Router Proxy
Main entry point for routing queries to PostgreSQL primary/replicas.

Architecture:
  - Maintains connection pools to primary + all replicas
  - Classifies queries as READ (SELECT) or WRITE (INSERT, UPDATE, DELETE, etc.)
  - Routes WRITEs → primary, READs → replica via pluggable strategy
  - Integrates health checker and metrics collector
  - ~200 lines of core logic (as specified in the assignment)
"""

import asyncio
import time
import re
import logging
from typing import Optional, Any

import asyncpg

from router.strategies import (
    ReplicaInfo, RoutingStrategy, get_strategy, all_strategy_names
)
from router.health_checker import HealthChecker
from router.metrics import MetricsCollector

logger = logging.getLogger(__name__)

# Regex to classify queries
_READ_PATTERN = re.compile(
    r"^\s*(SELECT|SHOW|EXPLAIN|WITH\s+.*\s+SELECT)\b",
    re.IGNORECASE
)


class QueryRouter:
    """
    Custom Query Router Proxy for PostgreSQL read replicas.

    Routes read queries to replicas using one of 5 strategies,
    while directing all write queries to the primary.

    Usage:
        router = QueryRouter(strategy_name="round_robin", ...)
        await router.start()
        result = await router.execute("SELECT * FROM orders WHERE id = $1", 42)
        await router.stop()
    """

    def __init__(
        self,
        strategy_name: str = "round_robin",
        primary_host: str = "localhost",
        primary_port: int = 5439,
        replica_configs: Optional[list[dict]] = None,
        db_name: str = "benchmark",
        db_user: str = "postgres",
        db_password: str = "postgres",
        pool_size: int = 20,
        health_check_interval: float = 5.0,
    ):
        self.strategy: RoutingStrategy = get_strategy(strategy_name)
        self.primary_host = primary_host
        self.primary_port = primary_port
        self.db_name = db_name
        self.db_user = db_user
        self.db_password = db_password
        self.pool_size = pool_size
        self.health_check_interval = health_check_interval

        # Setup replica info
        if replica_configs is None:
            replica_configs = [
                {"name": "replica1", "host": "localhost", "port": 5440, "weight": 4},
                {"name": "replica2", "host": "localhost", "port": 5441, "weight": 2},
                {"name": "replica3", "host": "localhost", "port": 5442, "weight": 1},
            ]

        self.replicas: list[ReplicaInfo] = [
            ReplicaInfo(
                name=rc["name"],
                host=rc["host"],
                port=rc["port"],
                weight=rc.get("weight", 1),
            )
            for rc in replica_configs
        ]

        # Components (initialized on start)
        self.metrics = MetricsCollector()
        self.health_checker: Optional[HealthChecker] = None
        self._primary_pool: Optional[asyncpg.Pool] = None
        self._replica_pools: dict[str, asyncpg.Pool] = {}
        self._started = False

    async def start(self):
        """Initialize connection pools and start health checker."""
        if self._started:
            return

        logger.info(f"Starting QueryRouter [strategy={self.strategy.name()}]")

        # Create primary pool
        self._primary_pool = await asyncpg.create_pool(
            host=self.primary_host,
            port=self.primary_port,
            user=self.db_user,
            password=self.db_password,
            database=self.db_name,
            min_size=2,
            max_size=self.pool_size,
            command_timeout=30.0,
        )
        logger.info(f"Primary pool created ({self.primary_host}:{self.primary_port})")

        # Create replica pools
        for r in self.replicas:
            try:
                pool = await asyncpg.create_pool(
                    host=r.host,
                    port=r.port,
                    user=self.db_user,
                    password=self.db_password,
                    database=self.db_name,
                    min_size=2,
                    max_size=self.pool_size,
                    command_timeout=30.0,
                )
                self._replica_pools[r.name] = pool
                logger.info(f"Replica pool created: {r.name} ({r.host}:{r.port})")
            except Exception as e:
                logger.error(f"Failed to create pool for {r.name}: {e}")
                r.healthy = False

        # Start health checker
        self.health_checker = HealthChecker(
            replicas=self.replicas,
            interval=self.health_check_interval,
            db_name=self.db_name,
            db_user=self.db_user,
            db_password=self.db_password,
            metrics_collector=self.metrics,
        )
        await self.health_checker.start()

        # Initial health check
        await self.health_checker.force_check()

        self._started = True
        logger.info("QueryRouter ready")

    async def stop(self):
        """Stop health checker and close all pools."""
        if not self._started:
            return

        logger.info("Stopping QueryRouter...")

        # Stop health checker
        if self.health_checker:
            await self.health_checker.stop()

        # Close replica pools
        for name, pool in self._replica_pools.items():
            await pool.close()
        self._replica_pools.clear()

        # Close primary pool
        if self._primary_pool:
            await self._primary_pool.close()

        self._started = False
        logger.info("QueryRouter stopped")

    def set_strategy(self, strategy_name: str):
        """Switch routing strategy (between runs)."""
        self.strategy = get_strategy(strategy_name)
        self.strategy.reset()
        logger.info(f"Strategy changed to: {self.strategy.name()}")

    @staticmethod
    def is_read_query(query: str) -> bool:
        """Classify a query as READ (True) or WRITE (False)."""
        return _READ_PATTERN.match(query) is not None

    async def execute(
        self,
        query: str,
        *args,
        complexity: str = "simple",
    ) -> list[asyncpg.Record]:
        """
        Execute a query, routing to the appropriate backend.

        - READ queries → routed to a replica via the current strategy
        - WRITE queries → always sent to primary

        Returns list of Record objects.
        """
        is_read = self.is_read_query(query)

        # Measure routing overhead
        t_route_start = time.perf_counter()

        if is_read:
            # Get healthy replicas
            healthy = [r for r in self.replicas if r.healthy]
            replica = self.strategy.select_replica(healthy) if healthy else None
            target_name = replica.name if replica else "primary"
            pool = self._replica_pools.get(target_name, self._primary_pool)
        else:
            target_name = "primary"
            pool = self._primary_pool
            replica = None

        t_route_end = time.perf_counter()
        routing_overhead_ms = (t_route_end - t_route_start) * 1000.0

        # Execute query
        t_query_start = time.perf_counter()

        try:
            async with pool.acquire() as conn:
                if is_read:
                    result = await conn.fetch(query, *args)
                else:
                    result = await conn.fetch(query, *args)
        except Exception as e:
            logger.error(f"Query error on {target_name}: {e}")
            raise

        t_query_end = time.perf_counter()
        total_latency_ms = (t_query_end - t_query_start) * 1000.0

        # Update EMA latency for the target replica
        if replica is not None:
            from router.health_checker import EMA_ALPHA
            replica.ema_latency_ms = (
                EMA_ALPHA * total_latency_ms +
                (1 - EMA_ALPHA) * replica.ema_latency_ms
            )

        # Record metrics
        query_type = "read" if is_read else "write"
        self.metrics.record_query(
            replica_name=target_name,
            query_type=query_type,
            complexity=complexity,
            latency_ms=total_latency_ms,
            routing_overhead_ms=routing_overhead_ms,
        )

        return result

    async def execute_write(
        self, query: str, *args, complexity: str = "simple"
    ) -> str:
        """
        Execute a write query on primary. Returns status string.
        """
        t_route_start = time.perf_counter()
        t_route_end = time.perf_counter()
        routing_overhead_ms = (t_route_end - t_route_start) * 1000.0

        t_query_start = time.perf_counter()
        try:
            async with self._primary_pool.acquire() as conn:
                status = await conn.execute(query, *args)
        except Exception as e:
            logger.error(f"Write error on primary: {e}")
            raise
        t_query_end = time.perf_counter()
        total_latency_ms = (t_query_end - t_query_start) * 1000.0

        self.metrics.record_query(
            replica_name="primary",
            query_type="write",
            complexity=complexity,
            latency_ms=total_latency_ms,
            routing_overhead_ms=routing_overhead_ms,
        )

        return status

    def get_replica_states(self) -> list[dict]:
        """Get current state of all replicas (for debugging/logging)."""
        return [
            {
                "name": r.name,
                "healthy": r.healthy,
                "ema_latency_ms": round(r.ema_latency_ms, 2),
                "cpu_pct": round(r.cpu_pct, 2),
                "active_connections": r.active_connections,
                "weight": r.weight,
            }
            for r in self.replicas
        ]
