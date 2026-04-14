#!/bin/bash
# =============================================================================
# PostgreSQL Replica Entrypoint
# Performs pg_basebackup from primary if data directory is empty,
# then starts PostgreSQL in standby (read-only) mode.
# =============================================================================

set -e

PGDATA="/var/lib/postgresql/data"
PRIMARY_HOST="${PRIMARY_HOST:-pg_primary}"
PRIMARY_PORT="5432"
REPLICA_NAME="${REPLICA_NAME:-replica1}"
SLOT_NAME="${REPLICA_NAME}_slot"

echo "=== Replica ${REPLICA_NAME} starting ==="
echo "    Primary: ${PRIMARY_HOST}:${PRIMARY_PORT}"
echo "    Slot: ${SLOT_NAME}"

# -------------------------------------------------------
# Setup .pgpass for password-less authentication
# -------------------------------------------------------
PGPASS_FILE="/var/lib/postgresql/.pgpass"
echo "${PRIMARY_HOST}:${PRIMARY_PORT}:*:postgres:postgres" > "${PGPASS_FILE}"
chown postgres:postgres "${PGPASS_FILE}"
chmod 0600 "${PGPASS_FILE}"

# -------------------------------------------------------
# Check if data directory needs initialization
# -------------------------------------------------------
if [ -z "$(ls -A ${PGDATA} 2>/dev/null)" ]; then
    echo "=== Data directory empty — running pg_basebackup ==="

    # Wait for primary to be fully ready
    echo "Waiting for primary to be ready..."
    until su - postgres -c "pg_isready -h ${PRIMARY_HOST} -p ${PRIMARY_PORT} -U postgres" 2>/dev/null; do
        echo "  Primary not ready yet, retrying in 2s..."
        sleep 2
    done

    # Additional wait for init scripts to complete
    echo "Waiting for primary init scripts to complete..."
    sleep 10

    # Ensure data directory exists with correct ownership
    mkdir -p ${PGDATA}
    chown -R postgres:postgres ${PGDATA}
    chmod 0700 ${PGDATA}

    # Perform base backup from primary AS postgres user
    echo "Running pg_basebackup..."
    gosu postgres pg_basebackup \
        -h ${PRIMARY_HOST} \
        -p ${PRIMARY_PORT} \
        -U postgres \
        -D ${PGDATA} \
        -Fp -Xs -P -R \
        -S ${SLOT_NAME}

    echo "=== pg_basebackup complete ==="

    # -------------------------------------------------------
    # Configure standby settings
    # -------------------------------------------------------

    # standby.signal is already created by pg_basebackup -R
    if [ ! -f "${PGDATA}/standby.signal" ]; then
        touch "${PGDATA}/standby.signal"
    fi

    # Update postgresql.auto.conf with replica-specific settings
    cat >> "${PGDATA}/postgresql.auto.conf" <<EOF

# --- Replica Settings (auto-configured) ---
primary_conninfo = 'host=${PRIMARY_HOST} port=${PRIMARY_PORT} user=postgres password=postgres application_name=${REPLICA_NAME}'
primary_slot_name = '${SLOT_NAME}'
hot_standby = on
hot_standby_feedback = on
max_connections = 200
shared_buffers = 96MB
effective_cache_size = 192MB
work_mem = 4MB
EOF

    echo "=== Standby configuration written ==="

    # Set proper permissions
    chown -R postgres:postgres ${PGDATA}
    chmod 0700 ${PGDATA}

else
    echo "=== Data directory exists — reusing existing data ==="

    # Ensure standby.signal exists (in case of restart)
    if [ ! -f "${PGDATA}/standby.signal" ]; then
        touch "${PGDATA}/standby.signal"
    fi

    # Ensure correct ownership
    chown -R postgres:postgres ${PGDATA}
fi

# -------------------------------------------------------
# Start PostgreSQL as postgres user in standby mode
# -------------------------------------------------------
echo "=== Starting PostgreSQL replica ${REPLICA_NAME} ==="
exec gosu postgres postgres -D ${PGDATA}
