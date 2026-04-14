"""
run_all.py — Master Benchmark Orchestrator

Iterates through all combinations:
  5 strategies × 3 complexities × 2 ratios × N repetitions
  = 30 combinations × 5 reps = 150 total runs

Features:
  - Prioritization: Read-Heavy first (as specified)
  - Resume capability: skips completed runs
  - Results saved to JSON per run
  - Summary CSV generated
"""

import asyncio
import json
import os
import sys
import time
import logging
import argparse
from pathlib import Path

from router.strategies import all_strategy_names
from benchmark.workload import all_workload_names, get_workload_config
from benchmark.runner import BenchmarkRunner

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# =============================================================================
# Configuration
# =============================================================================
STRATEGIES = all_strategy_names()
COMPLEXITIES = ["simple", "medium", "complex"]
# Ordered: read_heavy first (prioritas)
WORKLOADS = ["read_heavy", "balanced"]

DEFAULT_DURATION = 600     # 10 minutes
DEFAULT_CONCURRENCY = 50
DEFAULT_WARMUP = 1000
DEFAULT_REPS = 5
BASE_SEED = 42


def get_results_dir() -> Path:
    """Get or create results directory."""
    results_dir = Path("results")
    results_dir.mkdir(exist_ok=True)
    return results_dir


def run_key(strategy: str, complexity: str, workload: str, rep: int) -> str:
    """Generate a unique key for a run combination."""
    return f"{strategy}__{complexity}__{workload}__rep{rep}"


def is_completed(results_dir: Path, key: str) -> bool:
    """Check if a run has already been completed."""
    result_file = results_dir / f"{key}.json"
    return result_file.exists()


def save_result(results_dir: Path, key: str, result: dict):
    """Save a single run result to JSON."""
    result_file = results_dir / f"{key}.json"
    with open(result_file, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str)


def generate_summary(results_dir: Path):
    """Generate a summary CSV from all completed runs."""
    import csv

    summary_file = results_dir / "summary.csv"
    rows = []

    for json_file in sorted(results_dir.glob("*.json")):
        if json_file.name == "summary.json":
            continue
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            config = data.get("config", {})
            rows.append({
                "strategy": config.get("strategy", ""),
                "complexity": config.get("complexity", ""),
                "workload": config.get("workload", ""),
                "seed": config.get("seed", ""),
                "read_avg_ms": data.get("read_avg_ms", 0),
                "read_p95_ms": data.get("read_p95_ms", 0),
                "throughput_qps": data.get("throughput_qps", 0),
                "load_cv": data.get("load_cv", 0),
                "staleness_pct": data.get("staleness_pct", 0),
                "router_overhead_ms": data.get("router_overhead_ms", 0),
                "avg_cpu_pct": data.get("avg_cpu_pct", 0),
                "total_queries": data.get("total_queries", 0),
                "total_reads": data.get("total_reads", 0),
                "total_writes": data.get("total_writes", 0),
                "errors": data.get("errors", 0),
                "duration_s": data.get("duration_s", 0),
            })
        except Exception as e:
            logger.warning(f"Error reading {json_file}: {e}")

    if rows:
        with open(summary_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
        logger.info(f"Summary saved: {summary_file} ({len(rows)} runs)")


async def run_all(
    duration_s: int = DEFAULT_DURATION,
    concurrency: int = DEFAULT_CONCURRENCY,
    warmup: int = DEFAULT_WARMUP,
    reps: int = DEFAULT_REPS,
    strategies: list[str] = None,
    complexities: list[str] = None,
    workloads: list[str] = None,
    resume: bool = True,
):
    """
    Run all benchmark combinations.
    """
    strategies = strategies or STRATEGIES
    complexities = complexities or COMPLEXITIES
    workloads = workloads or WORKLOADS

    results_dir = get_results_dir()

    # Build run list
    runs = []
    for workload in workloads:  # read_heavy first
        for complexity in complexities:
            for strategy in strategies:
                for rep in range(1, reps + 1):
                    key = run_key(strategy, complexity, workload, rep)
                    runs.append((strategy, complexity, workload, rep, key))

    total = len(runs)
    completed = sum(1 for _, _, _, _, k in runs if is_completed(results_dir, k))
    remaining = total - completed if resume else total

    logger.info("=" * 70)
    logger.info(f"  BENCHMARK ORCHESTRATOR")
    logger.info(f"  Strategies:    {strategies}")
    logger.info(f"  Complexities:  {complexities}")
    logger.info(f"  Workloads:     {workloads}")
    logger.info(f"  Repetitions:   {reps}")
    logger.info(f"  Duration/run:  {duration_s}s")
    logger.info(f"  Concurrency:   {concurrency}")
    logger.info(f"  Total runs:    {total}")
    logger.info(f"  Completed:     {completed}")
    logger.info(f"  Remaining:     {remaining}")
    logger.info(f"  Est. time:     {(remaining * (duration_s + 30)) / 3600:.1f} hours")
    logger.info("=" * 70)

    run_idx = 0
    for strategy, complexity, workload, rep, key in runs:
        run_idx += 1

        # Skip completed (resume mode)
        if resume and is_completed(results_dir, key):
            logger.info(f"[{run_idx}/{total}] SKIP (done): {key}")
            continue

        workload_cfg = get_workload_config(workload)
        seed = BASE_SEED + (rep * 100)

        logger.info(f"\n{'='*70}")
        logger.info(f"[{run_idx}/{total}] RUN: {key}")
        logger.info(f"  Strategy={strategy}, Complexity={complexity}, "
                     f"Workload={workload_cfg.label}, Rep={rep}, Seed={seed}")
        logger.info(f"{'='*70}")

        t0 = time.monotonic()

        try:
            runner = BenchmarkRunner(
                strategy=strategy,
                complexity=complexity,
                workload=workload,
                duration_s=duration_s,
                concurrency=concurrency,
                warmup=warmup,
                seed=seed,
            )

            result = await runner.run()
            save_result(results_dir, key, result)

            elapsed = time.monotonic() - t0
            logger.info(
                f"[{run_idx}/{total}] DONE in {elapsed:.1f}s: "
                f"qps={result['throughput_qps']:.1f}, "
                f"read_avg={result['read_avg_ms']:.2f}ms"
            )

        except Exception as e:
            logger.error(f"[{run_idx}/{total}] FAILED: {e}")
            # Save error result
            save_result(results_dir, key, {
                "config": {
                    "strategy": strategy,
                    "complexity": complexity,
                    "workload": workload,
                    "seed": seed,
                },
                "error": str(e),
            })

        # Small cool-down between runs
        await asyncio.sleep(3)

    # Generate summary
    generate_summary(results_dir)
    logger.info("\nAll runs complete!")


def main():
    parser = argparse.ArgumentParser(
        description="PostgreSQL Query Routing Benchmark Orchestrator"
    )
    parser.add_argument(
        "--duration", type=int, default=DEFAULT_DURATION,
        help=f"Duration per run in seconds (default: {DEFAULT_DURATION})"
    )
    parser.add_argument(
        "--concurrency", type=int, default=DEFAULT_CONCURRENCY,
        help=f"Number of concurrent clients (default: {DEFAULT_CONCURRENCY})"
    )
    parser.add_argument(
        "--warmup", type=int, default=DEFAULT_WARMUP,
        help=f"Number of warm-up queries (default: {DEFAULT_WARMUP})"
    )
    parser.add_argument(
        "--reps", type=int, default=DEFAULT_REPS,
        help=f"Repetitions per combination (default: {DEFAULT_REPS})"
    )
    parser.add_argument(
        "--strategies", nargs="+", default=None,
        help="Specific strategies to test (default: all)"
    )
    parser.add_argument(
        "--complexities", nargs="+", default=None,
        help="Specific complexities to test (default: all)"
    )
    parser.add_argument(
        "--workloads", nargs="+", default=None,
        help="Specific workloads to test (default: all)"
    )
    parser.add_argument(
        "--no-resume", action="store_true",
        help="Do not skip completed runs (re-run everything)"
    )
    # Quick test mode
    parser.add_argument(
        "--quick", action="store_true",
        help="Quick smoke test: 60s duration, 1 rep, 10 concurrency"
    )

    args = parser.parse_args()

    if args.quick:
        args.duration = 60
        args.reps = 1
        args.concurrency = 10
        args.warmup = 100
        logger.info("Quick mode: 60s, 1 rep, 10 concurrency, 100 warmup")

    asyncio.run(run_all(
        duration_s=args.duration,
        concurrency=args.concurrency,
        warmup=args.warmup,
        reps=args.reps,
        strategies=args.strategies,
        complexities=args.complexities,
        workloads=args.workloads,
        resume=not args.no_resume,
    ))


if __name__ == "__main__":
    main()
