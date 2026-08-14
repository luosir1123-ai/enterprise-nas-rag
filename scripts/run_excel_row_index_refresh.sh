#!/bin/bash
set -euo pipefail

INSTALL_ROOT="${RAGFLOW_SYNC_INSTALL_ROOT:-${HOME}/Library/Application Support/waimao-ragflow}"
RUN_ROOT="${RAGFLOW_EXCEL_INDEX_RUN_ROOT:-${HOME}/Library/Logs/waimao-ragflow/excel_row_index}"
CONTAINER="${RAGFLOW_CONTAINER:-docker-ragflow-cpu-1}"
DATABASE="/ragflow/structured-index/excel_rows.sqlite3"
LOCK_DIR="/tmp/waimao-ragflow-excel-row-index.lock"
DOCKER="/usr/local/bin/docker"

mkdir -p "$RUN_ROOT"
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  exit 0
fi
trap 'rmdir "$LOCK_DIR"' EXIT

timestamp="$(date +%Y%m%d_%H%M%S)"
run_dir="$RUN_ROOT/$timestamp"
mkdir -p "$run_dir"

if ! "$DOCKER" inspect -f '{{.State.Running}}' "$CONTAINER" 2>/dev/null | /usr/bin/grep -qx true; then
  printf '%s\n' "RAGFlow container is not running: $CONTAINER" > "$run_dir/skipped.log"
  exit 0
fi

"$DOCKER" cp "$INSTALL_ROOT/ragflow_env.py" "$CONTAINER:/tmp/ragflow_env.py"
"$DOCKER" cp "$INSTALL_ROOT/business_metadata.py" "$CONTAINER:/tmp/business_metadata.py"
"$DOCKER" cp "$INSTALL_ROOT/ragflow_build_excel_row_index.py" "$CONTAINER:/tmp/ragflow_build_excel_row_index.py"
"$DOCKER" cp "$INSTALL_ROOT/excel_row_index.json" "$CONTAINER:/tmp/excel_row_index.json"

force_arg=""
if [[ "${RAGFLOW_EXCEL_INDEX_FORCE:-0}" == "1" ]]; then
  force_arg="--force"
fi

"$DOCKER" exec "$CONTAINER" sh -lc \
  "cd /ragflow && PYTHONPATH=/tmp:/ragflow python /tmp/ragflow_build_excel_row_index.py --config /tmp/excel_row_index.json --database $DATABASE --report /tmp/ragflow_excel_row_index_report.json $force_arg" \
  > "$run_dir/run.log" 2>&1

"$DOCKER" cp "$CONTAINER:/tmp/ragflow_excel_row_index_report.json" "$run_dir/report.json"
/usr/bin/find "$RUN_ROOT" -mindepth 1 -maxdepth 1 -type d -mtime +30 -exec /bin/rm -rf {} +
