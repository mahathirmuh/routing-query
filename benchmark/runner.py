"""
runner.py — Concurrent Benchmark Engine

Runs a single benchmark configuration:
  - 50 concurrent asyncio clients
  - Warm-up phase: 1000 queries
  - Test duration: configurable (default 10 minutes)
  - Fixed seed for reproducibility
  - Collects all 7 metrics
"""

import asyncio
import time
import logging
from typing import Optional

from router.query_router import QueryRouter
from router.metrics import MetricsCollector
from benchmark.workload import WorkloadGenerator

logger = logging.getLogger(__name__)


class BenchmarkRunner:
    """
    Executes a single benchmark run with specified configuration.

    Parameters:
        strategy:    Routing strategy name
        complexity:  Query complexity level ('simple', 'medium', 'complex')
        workload:    Workload profile ('read_heavy', 'balanced')
        duration_s:  Test duration in seconds (default 600 = 10 min)
        concurrency: Number of concurrent clients (default 50)
        warmup:      Number of warm-up queries (default 1000)
        seed:        Random seed for reproducibility
    """

    def __init__(
        self,
        strategy: str,
        complexity: str,
        workload: str,
        duration_s: int = 600,
        concurrency: int = 50,
        warmup: int = 1000,
        seed: int = 42,
        primary_host: str = "localhost",
        primary_port: int = 5439,
        replica_configs: Optional[list[dict]] = None,
    ):
        self.strategy = strategy
        self.complexity = complexity
        self.workload = workload
        self.duration_s = duration_s
        self.concurrency = concurrency
        self.warmup = warmup
        self.seed = seed
        self.primary_host = primary_host
        self.primary_port = primary_port
        self.replica_configs = replica_configs or [
            {"name": "replica1", "host": "localhost", "port": 5440, "weight": 4},
            {"name": "replica2", "host": "localhost", "port": 5441, "weight": 2},
            {"name": "replica3", "host": "localhost", "port": 5442, "weight": 1},
        ]

        # State
        self._stop_event = asyncio.Event()
        self._query_count = 0
        self._error_count = 0

    async def run(self) -> dict:
        """
        Execute the benchmark run.
        Returns computed metrics dictionary.
        """
        label = f"[{self.strategy}|{self.complexity}|{self.workload}]"
        logger.info(f"{label} Starting benchmark run")
        logger.info(f"{label} Duration={self.duration_s}s, Concurrency={self.concurrency}, "
                     f"Warmup={self.warmup}, Seed={self.seed}")

        # Create router
        router = QueryRouter(
            strategy_name=self.strategy,
            primary_host=self.primary_host,
            primary_port=self.primary_port,
            replica_configs=self.replica_configs,
            pool_size=20,
            health_check_interval=5.0,
        )

        try:
            await router.start()

            # --------------------------------------------------------
            # Phase 1: Warm-up
            # --------------------------------------------------------
            logger.info(f"{label} Warm-up: {self.warmup} queries...")
            warmup_gen = WorkloadGenerator(
                complexity=self.complexity,
                workload_name=self.workload,
                seed=self.seed,
            )

            warmup_tasks = []
            for i in range(self.warmup):
                query_tpl = warmup_gen.next_query()
                task = self._execute_one(router, query_tpl, count=False)
                warmup_tasks.append(task)

                # Batch execute in groups
                if len(warmup_tasks) >= self.concurrency:
                    await asyncio.gather(*warmup_tasks, return_exceptions=True)
                    warmup_tasks.clear()

            if warmup_tasks:
                await asyncio.gather(*warmup_tasks, return_exceptions=True)

            logger.info(f"{label} Warm-up complete")

            # Reset metrics after warmup
            router.metrics.reset()
            self._query_count = 0
            self._error_count = 0

            # --------------------------------------------------------
            # Phase 2: Benchmark
            # --------------------------------------------------------
            logger.info(f"{label} Benchmark starting ({self.duration_s}s)...")
            router.metrics.start()
            self._stop_event.clear()

            # Create workload generators (one per worker)
            workers = []
            for worker_id in range(self.concurrency):
                worker_seed = self.seed + worker_id + 1
                gen = WorkloadGenerator(
                    complexity=self.complexity,
                    workload_name=self.workload,
                    seed=worker_seed,
                )
                workers.append(
                    asyncio.create_task(
                        self._worker(worker_id, router, gen, label)
                    )
                )

            # Timer task
            timer = asyncio.create_task(self._timer(self.duration_s, label))

            # Wait for timer to complete
            await timer

            # Signal all workers to stop
            self._stop_event.set()

            # Wait for workers to finish current queries
            await asyncio.gather(*workers, return_exceptions=True)

            # Stop metrics
            router.metrics.stop()

            # --------------------------------------------------------
            # Phase 3: Collect results
            # --------------------------------------------------------
            results = router.metrics.compute_results()
            results["config"] = {
                "strategy": self.strategy,
                "complexity": self.complexity,
                "workload": self.workload,
                "duration_s": self.duration_s,
                "concurrency": self.concurrency,
                "seed": self.seed,
            }
            results["errors"] = self._error_count
            results["replica_states"] = router.get_replica_states()

            logger.info(
                f"{label} Benchmark complete: "
                f"{results['total_queries']} queries, "
                f"{results['throughput_qps']:.1f} qps, "
                f"read_avg={results['read_avg_ms']:.2f}ms, "
                f"errors={self._error_count}"
            )

            return results

        finally:
            await router.stop()

    async def _worker(
        self,
        worker_id: int,
        router: QueryRouter,
        gen: WorkloadGenerator,
        label: str,
    ):
        """Single concurrent worker that continuously executes queries."""
        while not self._stop_event.is_set():
            query_tpl = gen.next_query()
            await self._execute_one(router, query_tpl, count=True)

    async def _execute_one(
        self,
        router: QueryRouter,
        query_tpl,
        count: bool = True,
    ):
        """Execute a single query from a template."""
        try:
            params = query_tpl.params_fn()
            if query_tpl.query_type == "read":
                await router.execute(
                    query_tpl.sql, *params,
                    complexity=query_tpl.complexity,
                )
            else:
                await router.execute_write(
                    query_tpl.sql, *params,
                    complexity=query_tpl.complexity,
                )
            if count:
                self._query_count += 1
        except Exception as e:
            if count:
                self._error_count += 1
            # Don't log every error to avoid flooding
            if self._error_count <= 10:
                logger.warning(f"Query error: {e}")

    async def _timer(self, duration_s: int, label: str):
        """Timer that signals benchmark end after duration."""
        interval = max(duration_s // 10, 5)
        elapsed = 0

        while elapsed < duration_s:
            wait = min(interval, duration_s - elapsed)
            await asyncio.sleep(wait)
            elapsed += wait

            pct = (elapsed / duration_s) * 100
            logger.info(
                f"{label} Progress: {elapsed}/{duration_s}s ({pct:.0f}%) — "
                f"{self._query_count} queries, {self._error_count} errors"
            )


async def run_single_benchmark(
    strategy: str,
    complexity: str,
    workload: str,
    duration_s: int = 600,
    concurrency: int = 50,
    warmup: int = 1000,
    seed: int = 42,
    **kwargs,
) -> dict:
    """Convenience function to run a single benchmark."""
    runner = BenchmarkRunner(
        strategy=strategy,
        complexity=complexity,
        workload=workload,
        duration_s=duration_s,
        concurrency=concurrency,
        warmup=warmup,
        seed=seed,
        **kwargs,
    )
    return await runner.run()
