#!/bin/bash
set -euo pipefail

INSTALL_ROOT="${RAGFLOW_EVAL_INSTALL_ROOT:-${HOME}/Library/Application Support/waimao-ragflow}"
RUN_ROOT="${RAGFLOW_EVAL_RUN_ROOT:-${HOME}/Library/Logs/waimao-ragflow/evaluation}"
CONTAINER="docker-ragflow-cpu-1"
LOCK_DIR="/tmp/waimao-ragflow-evaluation.lock"
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
"$DOCKER" cp "$INSTALL_ROOT/ragflow_business_acceptance.py" "$CONTAINER:/tmp/ragflow_business_acceptance.py"
"$DOCKER" cp "$INSTALL_ROOT/eval_questions_template.csv" "$CONTAINER:/tmp/eval_questions_template.csv"
"$DOCKER" cp "$INSTALL_ROOT/purchase_sales_acceptance_v1.csv" "$CONTAINER:/tmp/purchase_sales_acceptance_v1.csv"

"$DOCKER" exec "$CONTAINER" sh -lc \
  "cd /ragflow && PYTHONPATH=/tmp:/ragflow python /tmp/ragflow_business_acceptance.py --cases source_coverage=/tmp/eval_questions_template.csv --cases business_accuracy=/tmp/purchase_sales_acceptance_v1.csv --output /tmp/ragflow_evaluation_report.json" \
  > "$run_dir/run.log" 2>&1

"$DOCKER" cp "$CONTAINER:/tmp/ragflow_evaluation_report.json" "$run_dir/report.json"
/usr/bin/find "$RUN_ROOT" -mindepth 1 -maxdepth 1 -type d -mtime +90 -exec /bin/rm -rf {} +
