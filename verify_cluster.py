#!/usr/bin/env python3
"""
Verification script for Phase 1: PostgreSQL Cluster Health Check
Checks: connectivity, replication status, data availability on all nodes.
"""

import subprocess
import sys
import time


def run_psql(host, port, query, db="benchmark"):
    """Execute a psql query and return output."""
    cmd = [
        "docker", "exec", f"pg_{host}",
        "psql", "-U", "postgres", "-d", db,
        "-t", "-A", "-c", query
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return result.stdout.strip(), result.returncode
    except subprocess.TimeoutExpired:
        return "TIMEOUT", 1
    except Exception as e:
        return str(e), 1


def check_connectivity():
    """Check if all nodes are reachable."""
    print("\n" + "=" * 60)
    print("1. CONNECTIVITY CHECK")
    print("=" * 60)

    nodes = ["primary", "replica1", "replica2", "replica3"]
    all_ok = True

    for node in nodes:
        output, rc = run_psql(node, 5432, "SELECT 'OK'")
        status = "✓ OK" if rc == 0 and "OK" in output else "✗ FAIL"
        if "FAIL" in status:
            all_ok = False
        print(f"  {node:12s} -> {status}")

    return all_ok


def check_replication():
    """Check replication status from primary."""
    print("\n" + "=" * 60)
    print("2. REPLICATION STATUS (from primary)")
    print("=" * 60)

    query = """
    SELECT
        application_name,
        state,
        sync_state,
        sent_lsn,
        write_lsn,
        flush_lsn,
        replay_lsn
    FROM pg_stat_replication
    ORDER BY application_name;
    """
    output, rc = run_psql("primary", 5432, query)

    if rc == 0 and output:
        print(f"  Active replicas:")
        for line in output.split("\n"):
            parts = line.split("|")
            if len(parts) >= 3:
                name = parts[0].strip()
                state = parts[1].strip()
                sync = parts[2].strip()
                print(f"    {name:12s} | state={state:10s} | sync={sync}")
        return True
    else:
        print("  ✗ No replication connections found!")
        return False


def check_replication_slots():
    """Check replication slot status."""
    print("\n" + "=" * 60)
    print("3. REPLICATION SLOTS")
    print("=" * 60)

    query = "SELECT slot_name, slot_type, active FROM pg_replication_slots ORDER BY slot_name;"
    output, rc = run_psql("primary", 5432, query)

    if rc == 0 and output:
        for line in output.split("\n"):
            parts = line.split("|")
            if len(parts) >= 3:
                name = parts[0].strip()
                stype = parts[1].strip()
                active = parts[2].strip()
                status = "✓" if active == "t" else "✗"
                print(f"  {status} {name:20s} | type={stype:10s} | active={active}")
        return True
    else:
        print("  ✗ No replication slots found!")
        return False


def check_data_counts():
    """Check row counts on all nodes."""
    print("\n" + "=" * 60)
    print("4. DATA VERIFICATION (row counts)")
    print("=" * 60)

    nodes = ["primary", "replica1", "replica2", "replica3"]
    tables = ["customers", "products", "orders"]
    expected = {"customers": 10000, "products": 1000, "orders": 500000}

    all_ok = True

    for table in tables:
        print(f"\n  {table} (expected: {expected[table]:,}):")
        for node in nodes:
            query = f"SELECT COUNT(*) FROM {table};"
            output, rc = run_psql(node, 5432, query)
            if rc == 0:
                count = int(output.strip())
                status = "✓" if count == expected[table] else "✗"
                if count != expected[table]:
                    all_ok = False
                print(f"    {node:12s} -> {count:>10,} {status}")
            else:
                print(f"    {node:12s} -> FAILED ✗")
                all_ok = False

    return all_ok


def check_replica_readonly():
    """Verify replicas are in read-only mode."""
    print("\n" + "=" * 60)
    print("5. READ-ONLY CHECK (replicas)")
    print("=" * 60)

    replicas = ["replica1", "replica2", "replica3"]
    all_ok = True

    for replica in replicas:
        # Try to insert — should fail on replica
        query = "INSERT INTO customers (name, email, region, tier) VALUES ('test', 'test@test.com', 'Test', 'Test');"
        output, rc = run_psql(replica, 5432, query)
        is_readonly = rc != 0 or "read-only" in output.lower() or "cannot execute" in output.lower()
        status = "✓ Read-only" if is_readonly else "✗ Writable (ERROR!)"
        if not is_readonly:
            all_ok = False
        print(f"  {replica:12s} -> {status}")

    return all_ok


def check_replica_lag():
    """Check replication lag."""
    print("\n" + "=" * 60)
    print("6. REPLICATION LAG")
    print("=" * 60)

    replicas = ["replica1", "replica2", "replica3"]

    for replica in replicas:
        query = """
        SELECT
            CASE WHEN pg_last_wal_receive_lsn() = pg_last_wal_replay_lsn()
                THEN 0
                ELSE EXTRACT(EPOCH FROM now() - pg_last_xact_replay_timestamp())
            END AS lag_seconds;
        """
        output, rc = run_psql(replica, 5432, query)
        if rc == 0 and output.strip():
            try:
                lag = float(output.strip())
                status = "✓" if lag < 5 else "⚠"
                print(f"  {replica:12s} -> {lag:.3f}s {status}")
            except ValueError:
                print(f"  {replica:12s} -> {output.strip()}")
        else:
            print(f"  {replica:12s} -> Unable to check")

    return True


def main():
    print("=" * 60)
    print("  PostgreSQL Cluster Verification — Phase 1")
    print("=" * 60)

    results = []
    results.append(("Connectivity", check_connectivity()))
    results.append(("Replication", check_replication()))
    results.append(("Replication Slots", check_replication_slots()))
    results.append(("Data Counts", check_data_counts()))
    results.append(("Read-Only", check_replica_readonly()))
    results.append(("Replication Lag", check_replica_lag()))

    print("\n" + "=" * 60)
    print("  SUMMARY")
    print("=" * 60)
    all_pass = True
    for name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        if not passed:
            all_pass = False
        print(f"  {name:20s} -> {status}")

    print()
    if all_pass:
        print("  ★ All checks passed! Cluster is ready for benchmarking.")
    else:
        print("  ✗ Some checks failed. Please investigate before proceeding.")
    print("=" * 60)

    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
