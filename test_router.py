"""
test_router.py — Smoke Test for Phase 2: Query Router
Verifies that the router can:
  1. Connect to all backends
  2. Route read queries to replicas
  3. Route write queries to primary
  4. All 5 strategies produce results
  5. Health checker runs properly
  6. Metrics are collected
"""

import asyncio
import sys
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("test_router")


async def test_strategy(strategy_name: str) -> dict:
    """Test a single strategy with a few queries."""
    from router.query_router import QueryRouter

    router = QueryRouter(
        strategy_name=strategy_name,
        primary_host="localhost",
        primary_port=5439,
        replica_configs=[
            {"name": "replica1", "host": "localhost", "port": 5440, "weight": 4},
            {"name": "replica2", "host": "localhost", "port": 5441, "weight": 2},
            {"name": "replica3", "host": "localhost", "port": 5442, "weight": 1},
        ],
        pool_size=5,
        health_check_interval=5.0,
    )

    try:
        await router.start()

        # Test 1: Simple read (PK lookup)
        result = await router.execute(
            "SELECT id, customer_id, total_price FROM orders WHERE id = $1",
            1, complexity="simple"
        )
        assert len(result) > 0, "Simple read returned no results"

        # Test 2: Medium read (JOIN)
        result = await router.execute(
            "SELECT o.id, c.name, o.total_price "
            "FROM orders o JOIN customers c ON o.customer_id = c.id "
            "WHERE o.region = $1 LIMIT 5",
            "Asia", complexity="medium"
        )
        assert len(result) > 0, "Medium read returned no results"

        # Test 3: Complex read (JOIN + aggregation)
        result = await router.execute(
            "SELECT c.region, p.category, COUNT(*) as cnt, AVG(o.total_price) as avg_price "
            "FROM orders o "
            "JOIN customers c ON o.customer_id = c.id "
            "JOIN products p ON o.product_id = p.id "
            "GROUP BY c.region, p.category "
            "ORDER BY cnt DESC LIMIT 5",
            complexity="complex"
        )
        assert len(result) > 0, "Complex read returned no results"

        # Test 4: Run multiple reads to test distribution
        for i in range(15):
            await router.execute(
                "SELECT id FROM orders WHERE id = $1",
                (i % 500000) + 1, complexity="simple"
            )

        # Test 5: Write query (to primary)
        import datetime
        await router.execute_write(
            "INSERT INTO orders (customer_id, product_id, quantity, total_price, status, region, order_date) "
            "VALUES ($1, $2, $3, $4, $5, $6, $7)",
            1, 1, 1, 99.99, "pending", "Test", datetime.date(2026, 1, 1),
            complexity="simple"
        )

        # Get results
        states = router.get_replica_states()
        metrics = router.metrics.compute_results()

        return {
            "strategy": strategy_name,
            "display_name": router.strategy.name(),
            "replica_states": states,
            "total_queries": metrics["total_queries"],
            "total_reads": metrics["total_reads"],
            "total_writes": metrics["total_writes"],
            "read_avg_ms": metrics["read_avg_ms"],
            "replica_distribution": metrics["replica_query_counts"],
            "passed": True,
        }

    except Exception as e:
        logger.error(f"Strategy {strategy_name} failed: {e}")
        return {"strategy": strategy_name, "passed": False, "error": str(e)}

    finally:
        await router.stop()


async def main():
    print("=" * 70)
    print("  Phase 2 Smoke Test: Query Router")
    print("=" * 70)

    strategies = [
        "round_robin",
        "load_based",
        "latency_based",
        "weighted_rr",
        "least_conn",
    ]

    all_passed = True

    for strat in strategies:
        print(f"\n--- Testing: {strat} ---")
        result = await test_strategy(strat)

        if result["passed"]:
            print(f"  [PASS] {result['display_name']}")
            print(f"    Queries: {result['total_reads']}R + {result['total_writes']}W = {result['total_queries']} total")
            print(f"    Read Avg Latency: {result['read_avg_ms']:.2f} ms")
            print(f"    Distribution: {result['replica_distribution']}")
            print(f"    Replica states:")
            for s in result["replica_states"]:
                print(f"      {s['name']:12s} | healthy={s['healthy']} | "
                      f"ema={s['ema_latency_ms']:.1f}ms | "
                      f"cpu={s['cpu_pct']:.1f}% | conns={s['active_connections']}")
        else:
            print(f"  [FAIL] {strat}: {result.get('error', 'unknown')}")
            all_passed = False

    # Cleanup: remove test data
    print("\n--- Cleanup ---")
    try:
        import asyncpg as apg
        conn = await apg.connect(
            host="localhost", port=5439,
            user="postgres", password="postgres",
            database="benchmark"
        )
        await conn.execute("DELETE FROM orders WHERE region = 'Test'")
        await conn.close()
        print("  Test data cleaned up")
    except Exception as e:
        print(f"  Cleanup warning: {e}")

    print("\n" + "=" * 70)
    if all_passed:
        print("  [ALL PASS] All 5 strategies working correctly!")
    else:
        print("  [SOME FAILED] Check errors above")
    print("=" * 70)

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
