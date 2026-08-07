#!/bin/bash
set -euo pipefail

INSTALL_ROOT="${RAGFLOW_SYNC_INSTALL_ROOT:-/Users/letouch/Library/Application Support/letouch-ragflow}"
RUN_ROOT="${RAGFLOW_SYNC_RUN_ROOT:-/Users/letouch/Library/Logs/letouch-ragflow/incremental_sync}"
MOUNT_DIR="/Users/Shared/nas/LE_TOUCH_SHR"
CONTAINER="docker-ragflow-cpu-1"
LOCK_DIR="/tmp/letouch-ragflow-incremental-sync.lock"
DOCKER="/usr/local/bin/docker"

mkdir -p "$RUN_ROOT"
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  exit 0
fi
trap 'rmdir "$LOCK_DIR"' EXIT

timestamp="$(date +%Y%m%d_%H%M%S)"
run_dir="$RUN_ROOT/$timestamp"
mkdir -p "$run_dir"

if ! /sbin/mount | /usr/bin/grep -Fq "on $MOUNT_DIR (nfs, read-only)"; then
  printf '%s\n' "NAS is not mounted read-only: $MOUNT_DIR" > "$run_dir/skipped.log"
  exit 0
fi

if ! "$DOCKER" inspect -f '{{.State.Running}}' "$CONTAINER" 2>/dev/null | /usr/bin/grep -qx true; then
  printf '%s\n' "RAGFlow container is not running: $CONTAINER" > "$run_dir/skipped.log"
  exit 0
fi

"$DOCKER" cp "$INSTALL_ROOT/ragflow_env.py" "$CONTAINER:/tmp/ragflow_env.py"
"$DOCKER" cp "$INSTALL_ROOT/nas_sync_policy.py" "$CONTAINER:/tmp/nas_sync_policy.py"
"$DOCKER" cp "$INSTALL_ROOT/business_metadata.py" "$CONTAINER:/tmp/business_metadata.py"
"$DOCKER" cp "$INSTALL_ROOT/ragflow_incremental_sync.py" "$CONTAINER:/tmp/ragflow_incremental_sync.py"
"$DOCKER" cp "$INSTALL_ROOT/ragflow_build_excel_row_index.py" "$CONTAINER:/tmp/ragflow_build_excel_row_index.py"
"$DOCKER" cp "$INSTALL_ROOT/excel_row_index.json" "$CONTAINER:/tmp/excel_row_index.json"

"$DOCKER" exec "$CONTAINER" sh -lc \
  "cd /ragflow && PYTHONPATH=/tmp:/ragflow RAGFLOW_SYNC_APPLY=${RAGFLOW_SYNC_APPLY:-1} RAGFLOW_SYNC_PARSE=${RAGFLOW_SYNC_PARSE:-1} RAGFLOW_SYNC_MAX_CHANGES=${RAGFLOW_SYNC_MAX_CHANGES:-300} RAGFLOW_SYNC_MAX_BYTES=${RAGFLOW_SYNC_MAX_BYTES:-524288000} RAGFLOW_SYNC_SOURCE_ID=${RAGFLOW_SYNC_SOURCE_ID:-synology-192.168.1.90} RAGFLOW_SYNC_SOURCE_NAME='${RAGFLOW_SYNC_SOURCE_NAME:-LeTouch NAS 2026}' python /tmp/ragflow_incremental_sync.py" \
  > "$run_dir/run.log" 2>&1

"$DOCKER" cp "$CONTAINER:/tmp/ragflow_incremental_sync_report.json" "$run_dir/report.json"
"$DOCKER" cp "$CONTAINER:/tmp/ragflow_incremental_sync.log" "$run_dir/sync.log"

"$DOCKER" exec "$CONTAINER" sh -lc \
  "cd /ragflow && PYTHONPATH=/tmp:/ragflow python /tmp/ragflow_build_excel_row_index.py --config /tmp/excel_row_index.json --database /ragflow/structured-index/excel_rows.sqlite3 --report /tmp/ragflow_excel_row_index_report.json" \
  > "$run_dir/excel_row_index.log" 2>&1
"$DOCKER" cp "$CONTAINER:/tmp/ragflow_excel_row_index_report.json" "$run_dir/excel_row_index_report.json"

/usr/bin/find "$RUN_ROOT" -mindepth 1 -maxdepth 1 -type d -mtime +30 -exec /bin/rm -rf {} +
