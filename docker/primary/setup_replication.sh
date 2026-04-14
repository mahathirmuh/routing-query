#!/bin/bash
# =============================================================================
# Setup replication user and slot on PRIMARY
# Runs as part of docker-entrypoint-initdb.d (before init.sql)
# =============================================================================

set -e

echo "=== Setting up replication user and slots ==="

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    -- Create replication user (same as postgres for simplicity)
    -- The postgres user already has replication privileges by default

    -- Create replication slots for each replica
    SELECT pg_create_physical_replication_slot('replica1_slot', true);
    SELECT pg_create_physical_replication_slot('replica2_slot', true);
    SELECT pg_create_physical_replication_slot('replica3_slot', true);

    -- Verify
    SELECT slot_name, slot_type, active FROM pg_replication_slots;
EOSQL

echo "=== Replication setup complete ==="
