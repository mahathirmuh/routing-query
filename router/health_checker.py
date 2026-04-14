"""
health_checker.py — Periodic Health Check & Monitoring
Runs as an asyncio background task that:
  - Probes each replica with SELECT 1 (latency measurement)
  - Queries pg_stat_activity for active connection count & CPU estimate
  - Updates EMA latency (alpha=0.3)
  - Marks unhealthy replicas (excluded from routing)
  - Collects CPU samples for metrics
"""

import asyncio
import time
import logging
from typing import Optional

import asyncpg

from router.strategies import ReplicaInfo
from router.metrics import MetricsCollector

logger = logging.getLogger(__name__)

# EMA smoothing factor (as specified in the assignment)
EMA_ALPHA = 0.3


class HealthChecker:
    """
    Periodic health checker for PostgreSQL replicas.
    Runs every `interval` seconds, probing each replica.
    """

    def __init__(
        self,
        replicas: list[ReplicaInfo],
        interval: float = 5.0,
        db_name: str = "benchmark",
        db_user: str = "postgres",
        db_password: str = "postgres",
        metrics_collector: Optional[MetricsCollector] = None,
    ):
        self.replicas = replicas
        self.interval = interval
        self.db_name = db_name
        self.db_user = db_user
        self.db_password = db_password
        self.metrics = metrics_collector
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._probe_pools: dict[str, asyncpg.Pool] = {}

    async def start(self):
        """Start background health check task."""
        if self._running:
            return
        self._running = True

        # Create lightweight probe pools (1 connection each)
        for r in self.replicas:
            try:
                pool = await asyncpg.create_pool(
                    host=r.host, port=r.port,
                    user=self.db_user, password=self.db_password,
                    database=self.db_name,
                    min_size=1, max_size=2,
                    command_timeout=5.0,
                )
                self._probe_pools[r.name] = pool
                logger.info(f"Health probe pool created for {r.name}")
            except Exception as e:
                logger.error(f"Failed to create probe pool for {r.name}: {e}")
                r.healthy = False

        self._task = asyncio.create_task(self._run_loop())
        logger.info(f"Health checker started (interval={self.interval}s, EMA alpha={EMA_ALPHA})")

    async def stop(self):
        """Stop background health check task."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        # Close probe pools
        for name, pool in self._probe_pools.items():
            await pool.close()
        self._probe_pools.clear()
        logger.info("Health checker stopped")

    async def _run_loop(self):
        """Main health check loop."""
        while self._running:
            try:
                await self._check_all()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Health check error: {e}")

            await asyncio.sleep(self.interval)

    async def _check_all(self):
        """Check all replicas concurrently."""
        tasks = [self._check_one(r) for r in self.replicas]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _check_one(self, replica: ReplicaInfo):
        """Perform health check on a single replica."""
        pool = self._probe_pools.get(replica.name)
        if pool is None:
            replica.healthy = False
            return

        try:
            async with pool.acquire() as conn:
                # --- 1. Latency probe (SELECT 1) ---
                t0 = time.perf_counter()
                await conn.fetchval("SELECT 1")
                latency_ms = (time.perf_counter() - t0) * 1000.0

                # Update EMA latency
                if replica.ema_latency_ms == 0.0:
                    replica.ema_latency_ms = latency_ms
                else:
                    replica.ema_latency_ms = (
                        EMA_ALPHA * latency_ms +
                        (1 - EMA_ALPHA) * replica.ema_latency_ms
                    )

                # --- 2. Active connections count ---
                conn_count = await conn.fetchval(
                    "SELECT COUNT(*) FROM pg_stat_activity "
                    "WHERE state = 'active' AND backend_type = 'client backend'"
                )
                replica.active_connections = conn_count or 0

                # --- 3. CPU estimate (via active query ratio) ---
                # In Docker containers without direct CPU access, we estimate
                # CPU load from active query ratio relative to max_connections
                total_conns = await conn.fetchval(
                    "SELECT COUNT(*) FROM pg_stat_activity "
                    "WHERE backend_type = 'client backend'"
                )
                max_conns = await conn.fetchval("SHOW max_connections")
                max_conns = int(max_conns) if max_conns else 200
                if max_conns > 0:
                    replica.cpu_pct = ((total_conns or 0) / max_conns) * 100.0
                else:
                    replica.cpu_pct = 0.0

                # --- 4. Mark as healthy ---
                if not replica.healthy:
                    logger.info(f"Replica {replica.name} recovered")
                replica.healthy = True

                # --- 5. Record CPU sample for metrics ---
                if self.metrics:
                    self.metrics.record_cpu_sample(replica.name, replica.cpu_pct)

        except Exception as e:
            if replica.healthy:
                logger.warning(f"Replica {replica.name} unhealthy: {e}")
            replica.healthy = False

    async def force_check(self):
        """Force an immediate health check (useful before benchmarks)."""
        await self._check_all()
