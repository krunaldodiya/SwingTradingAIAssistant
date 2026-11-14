#!/usr/bin/env bash
# Independent, incremental provider capture, run before research.
#
# Sub-step 1 writes the raw session cache research reads. Sub-step 2 updates the
# adjusted-daily benchmark store. Both read only the retained universe snapshot
# and the date; neither reads the exchange calendar, pair state, safety policy,
# or research result. Existing data is reused: a member whose newest retained
# session already reaches the requested end is skipped without a provider
# request, and the adjusted stage is skipped when its retained history is
# already current. One sub-step failing does not stop the other.
set -u

SCRIPT_PATH=${BASH_SOURCE[0]}
REPO=${SWING_REPO:-$(cd "$(dirname "$SCRIPT_PATH")/.." && pwd)}
STORE=${SWING_STORAGE_ROOT:-$HOME/SwingTradingAIAssistantData}
DOPPLER=${DOPPLER_BIN:-$HOME/.local/bin/doppler}
PROJECT=${SWING_DOPPLER_PROJECT:-swing-trading}
CONFIG=${SWING_DOPPLER_CONFIG:-dev}
PYTHON=${SWING_CAPTURE_PYTHON:-$REPO/.venv/bin/python}
RAW=${SWING_CAPTURE_RAW_SCRIPT:-$REPO/scripts/capture_bharatstock_current.py}
DOWNLOADER=${SWING_CAPTURE_DOWNLOADER:-$REPO/.venv/bin/equity-data-download}
START_DAYS=${SWING_CAPTURE_START_DAYS:-45}
LOG=${SWING_LOG_DIR:-$STORE/daily-scan}
STAMP=${SWING_DATE_OVERRIDE:-$(TZ=Asia/Kolkata date +%F)}
UNIVERSE="$STORE/universe_snapshots/nifty-universe-v3.json"

STARTED_AT=$(date -u +%Y-%m-%dT%H:%M:%SZ)

[ -d "$STORE" ] || { echo "capture_invalid: storage root unavailable: $STORE" >&2; exit 2; }
[ -f "$UNIVERSE" ] || { echo "capture_invalid: universe snapshot unavailable: $UNIVERSE" >&2; exit 2; }
mkdir -p "$LOG" || exit 1

START=${SWING_CAPTURE_START:-$(date -d "$STAMP - $START_DAYS days" +%F)}
[ -n "$START" ] || { echo "capture_invalid: invalid start date" >&2; exit 2; }

INSTRUMENTS=$(mktemp) || exit 1
trap 'rm -f "$INSTRUMENTS"' EXIT
"$PYTHON" - "$UNIVERSE" > "$INSTRUMENTS" <<'PY'
import base64
import csv
import io
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    payload = json.load(handle)
rows = list(
    csv.DictReader(
        io.StringIO(base64.b64decode(payload["nifty200_source_csv_base64"]).decode())
    )
)
for row in rows:
    isin = (row.get("ISIN Code") or "").strip()
    symbol = (row.get("Symbol") or "").strip()
    if isin and symbol:
        print(f"{isin}:NSE:{symbol}")
PY
mapfile -t lines < "$INSTRUMENTS"
[ "${#lines[@]}" -gt 0 ] || { echo "capture_invalid: no universe instruments" >&2; exit 2; }

# --- Sub-step 1: raw session cache -----------------------------------------
RAW_OUT="$LOG/capture-sessions-$STAMP.json"
RAW_ERR="$LOG/capture-sessions-$STAMP.err"
CHECKPOINT="$LOG/capture-sessions-$STAMP.checkpoint.json"
: > "$RAW_OUT"
"$DOPPLER" run --project "$PROJECT" --config "$CONFIG" -- \
  "$PYTHON" "$RAW" \
  --storage-root "$STORE" \
  --universe-snapshot "$UNIVERSE" \
  --start "$START" --end "$STAMP" \
  --checkpoint "$CHECKPOINT" --delay 1 \
  > "$RAW_OUT" 2> "$RAW_ERR"
raw_code=$?

# --- Sub-step 2: adjusted daily store --------------------------------------
# The retained adjusted history decides the range: only sessions newer than the
# newest retained dataset (if any) are requested. Nothing is re-downloaded.
ADJUSTED_NEWEST=$("$PYTHON" - "$STORE" <<'PY'
import glob
import os
import sys
from datetime import date, datetime

root = os.path.join(sys.argv[1], "adjusted_daily", "provider=bharatstock")
newest = None
for path in sorted(glob.glob(os.path.join(root, "**", "*.parquet"), recursive=True)):
    try:
        import pyarrow.parquet as pq

        values = pq.read_table(path, columns=["session"]).column("session").to_pylist()
    except Exception:  # noqa: BLE001 - an unreadable dataset is skipped
        continue
    for value in values:
        if isinstance(value, datetime):
            value = value.date()
        elif isinstance(value, str):
            try:
                value = date.fromisoformat(value)
            except ValueError:
                continue
        if type(value) is not date:
            continue
        if newest is None or value > newest:
            newest = value
print("" if newest is None else newest.isoformat())
PY
)
adj_discovery_code=$?

ADJ_BUDGET=$("$PYTHON" - <<'PY'
from equity_data_downloader.core import _CALL_CONFIGURATION

print(int(_CALL_CONFIGURATION["max_requests"]))  # pyright: ignore[reportPrivateUsage]
PY
)
adj_budget_code=$?

ADJ_START=$START
ADJ_STATUS=INCOMPLETE
ADJ_ERROR=""
ADJ_INSTRUMENTS=0
ADJ_BATCHES=0
ADJ_CONFIGURED_MAX=0
codes=()

if [ "$adj_discovery_code" -ne 0 ]; then
  ADJ_ERROR="ADJUSTED_DISCOVERY_FAILED"
elif [ "$adj_budget_code" -ne 0 ]; then
  ADJ_ERROR="ADJUSTED_BUDGET_UNREADABLE"
else
  if [ -n "$ADJUSTED_NEWEST" ]; then
    if [[ ! "$ADJUSTED_NEWEST" < "$STAMP" ]]; then
      ADJ_STATUS=SKIPPED
    else
      ADJ_START=$(date -d "$ADJUSTED_NEWEST + 1 day" +%F)
    fi
  fi
  if [ "$ADJ_STATUS" != "SKIPPED" ]; then
    for ((offset = 0; offset < ${#lines[@]}; offset += 100)); do
      args=()
      batch=0
      for line in "${lines[@]:offset:100}"; do
        args+=(--instrument "$line")
        batch=$((batch + 1))
      done
      "$DOPPLER" run --project "$PROJECT" --config "$CONFIG" -- \
        "$DOWNLOADER" "${args[@]}" --start "$ADJ_START" --end "$STAMP" \
        --storage-root "$STORE" \
        >> "$LOG/capture-adjusted-$STAMP.json" 2>> "$LOG/capture-adjusted-$STAMP.err"
      codes+=("$?")
      ADJ_BATCHES=$((ADJ_BATCHES + 1))
      ADJ_INSTRUMENTS=$((ADJ_INSTRUMENTS + batch))
    done
    ADJ_CONFIGURED_MAX=$((ADJ_BUDGET * ADJ_BATCHES))
    ADJ_STATUS=COMPLETE
    if [ "$ADJ_BATCHES" -eq 0 ]; then
      ADJ_STATUS=INCOMPLETE
      ADJ_ERROR="ADJUSTED_NO_BATCHES"
    fi
    if [ "${#codes[@]}" -gt 0 ]; then
      for code in "${codes[@]}"; do
        if [ "$code" -ne 0 ]; then
          ADJ_STATUS=INCOMPLETE
          ADJ_ERROR="ADJUSTED_BATCH_FAILED"
        fi
      done
    fi
  fi
fi

ADJ_STAGE="$LOG/capture-adjusted-stage-$STAMP.json"
"$PYTHON" - "$ADJ_STAGE" "$ADJ_STATUS" "$ADJ_START" "$STAMP" \
  "$ADJ_INSTRUMENTS" "$ADJ_BATCHES" "$ADJ_CONFIGURED_MAX" "${ADJUSTED_NEWEST}" \
  "$ADJ_ERROR" ${codes[@]+"${codes[@]}"} <<'PY'
import json
import sys
import time

(
    path,
    status,
    start,
    end,
    instruments,
    batches,
    configured_max,
    newest_before,
    error,
) = sys.argv[1:10]
codes = [int(value) for value in sys.argv[10:]]
payload = {
    "schema": "adjusted-capture-stage@v1",
    "status": status,
    "range": {"start": start, "end": end},
    "newest_retained_before": newest_before or None,
    "requests_used": 0 if status == "SKIPPED" else int(instruments),
    "requests_used_basis": "INSTRUMENTS_SUBMITTED",
    "requests_configured_max": int(configured_max),
    "requests_configured_max_basis": "DOWNLOADER_MAX_REQUESTS_PER_INVOCATION * BATCHES",
    "instruments_submitted": 0 if status == "SKIPPED" else int(instruments),
    "batches": int(batches),
    "batch_exit_codes": codes,
    "error": error or None,
    "completed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
}
with open(path, "w", encoding="utf-8") as handle:
    json.dump(payload, handle, sort_keys=True, indent=2)
    handle.write("\n")
PY
adj_stage_code=$?

# --- Composite receipt ------------------------------------------------------
RECEIPT="$LOG/capture-$STAMP.json"
RECEIPT_STATUS=$("$PYTHON" - "$RAW_OUT" "$ADJ_STAGE" "$RECEIPT" "$STAMP" "$raw_code" \
  "$SCRIPT_PATH" "$STARTED_AT" <<'PY'
import hashlib
import json
import sys
import time

raw_path, adj_path, receipt_path, stamp, raw_code, script_path, started_at = (
    sys.argv[1:8]
)
try:
    with open(raw_path, encoding="utf-8") as handle:
        raw_value = json.load(handle)
    raw = raw_value if isinstance(raw_value, dict) else {}
except (OSError, ValueError):
    raw = {}
try:
    with open(adj_path, encoding="utf-8") as handle:
        adj_value = json.load(handle)
    adjusted = adj_value if isinstance(adj_value, dict) else {}
except (OSError, ValueError):
    adjusted = {"status": "INCOMPLETE", "error": "ADJUSTED_STAGE_UNREADABLE"}

raw_status = raw.get("status")
try:
    failed = int(raw.get("failed") or 0)
    remaining = raw.get("remaining_pending")
    if not isinstance(remaining, int):
        remaining = int(raw.get("pending_symbols") or 0)
except (TypeError, ValueError):
    failed, remaining = 1, 1
adjusted_status = adjusted.get("status")
complete = (
    raw_status in {"COMPLETE", "SKIPPED"}
    and int(raw_code) == 0
    and adjusted_status in {"COMPLETE", "SKIPPED"}
    and failed == 0
    and remaining == 0
)
try:
    script_sha256 = hashlib.sha256(open(script_path, "rb").read()).hexdigest()
except OSError:
    script_sha256 = None
symbols = raw.get("symbols")
symbols = symbols if isinstance(symbols, dict) else {}
failed_isins = raw.get("failed_isins")
failed_isins = failed_isins if isinstance(failed_isins, list) else []
raw_requests = int(raw.get("requests_used") or 0)
raw_max = int(raw.get("requests_configured_max") or 0)
adj_requests = int(adjusted.get("requests_used") or 0)
adj_max = int(adjusted.get("requests_configured_max") or 0)
receipt = {
    "schema": "provider-capture@v2",
    "stamp": stamp,
    "status": "COMPLETE" if complete else "INCOMPLETE",
    "failed": failed,
    "remaining_pending": remaining,
    "latest_session": raw.get("latest_session"),
    "symbols": symbols,
    "symbols_total": len(symbols),
    "symbols_complete": sum(
        1
        for record in symbols.values()
        if isinstance(record, dict) and record.get("status") == "COMPLETE"
    ),
    "symbols_skipped": sum(
        1
        for record in symbols.values()
        if isinstance(record, dict) and record.get("status") == "SKIPPED"
    ),
    "failed_isins": failed_isins,
    "universe_snapshot": raw.get("universe_snapshot"),
    "universe_snapshot_sha256": raw.get("universe_snapshot_sha256"),
    "quota": {
        "raw": {
            "requests_used": raw_requests,
            "requests_configured_max": raw_max,
            "max_requests_per_member": raw.get("max_requests_per_member"),
            "basis": raw.get("requests_configured_max_basis"),
        },
        "adjusted": {
            "requests_used": adj_requests,
            "requests_configured_max": adj_max,
            "basis": adjusted.get("requests_configured_max_basis"),
        },
    },
    "stages": {
        "raw": {
            "status": raw_status,
            "exit_code": int(raw_code),
            "requests_used": raw_requests,
            "requests_configured_max": raw_max,
            "sessions_written": raw.get("sessions_written"),
            "latest_session": raw.get("latest_session"),
        },
        "adjusted": {
            "status": adjusted_status,
            "requests_used": adj_requests,
            "requests_configured_max": adj_max,
            "batches": adjusted.get("batches"),
            "batch_exit_codes": adjusted.get("batch_exit_codes"),
            "range": adjusted.get("range"),
            "newest_retained_before": adjusted.get("newest_retained_before"),
            "error": adjusted.get("error"),
        },
    },
    "requests_used": raw_requests + adj_requests,
    "requests_configured_max": raw_max + adj_max,
    "runtime": {
        "raw": raw.get("runtime"),
        "composite": {
            "path": script_path,
            "sha256": script_sha256,
            "python": sys.version.split()[0],
        },
    },
    "timestamps": {
        "started_at": started_at,
        "completed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    },
    "sessions": raw,
    "adjusted": adjusted,
}
with open(receipt_path, "w", encoding="utf-8") as handle:
    json.dump(receipt, handle, sort_keys=True, indent=2)
    handle.write("\n")
print("1" if complete else "0")
PY
)
receipt_code=$?

[ "$adj_stage_code" -eq 0 ] || exit 2
[ "$receipt_code" -eq 0 ] || exit 2
[ "$RECEIPT_STATUS" = "1" ] || exit 1
exit 0
