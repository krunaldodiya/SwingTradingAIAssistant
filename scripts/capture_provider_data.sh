#!/usr/bin/env bash
# Independent provider capture, run before research.
#
# Sub-step 1 writes the raw session cache research reads. Sub-step 2 updates the
# adjusted-daily benchmark store. Both read only the retained universe snapshot
# and the date; neither reads the exchange calendar, pair state, safety policy,
# or research result. Existing data is reused; capture is additive.
set -u

REPO=${SWING_REPO:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}
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

RAW_OUT="$LOG/capture-sessions-$STAMP.json"
RAW_ERR="$LOG/capture-sessions-$STAMP.err"
CHECKPOINT="$LOG/capture-sessions-$STAMP.checkpoint.json"
"$DOPPLER" run --project "$PROJECT" --config "$CONFIG" -- \
  "$PYTHON" "$RAW" \
  --storage-root "$STORE" \
  --universe-snapshot "$UNIVERSE" \
  --start "$START" --end "$STAMP" \
  --checkpoint "$CHECKPOINT" --delay 1 \
  > "$RAW_OUT" 2> "$RAW_ERR"
raw_code=$?

codes=()
for ((offset = 0; offset < ${#lines[@]}; offset += 100)); do
  args=()
  for line in "${lines[@]:offset:100}"; do
    args+=(--instrument "$line")
  done
  "$DOPPLER" run --project "$PROJECT" --config "$CONFIG" -- \
    "$DOWNLOADER" "${args[@]}" --start "$START" --end "$STAMP" \
    --storage-root "$STORE" \
    >> "$LOG/capture-adjusted-$STAMP.json" 2>> "$LOG/capture-adjusted-$STAMP.err"
  codes+=("$?")
done

RECEIPT="$LOG/capture-$STAMP.json"
"$PYTHON" - "$RAW_OUT" "$RECEIPT" "$STAMP" "$raw_code" "${codes[@]}" <<'PY'
import json
import sys

raw_path, receipt_path, stamp, raw_code = sys.argv[1:5]
codes = [int(code) for code in sys.argv[5:]]
try:
    with open(raw_path, encoding="utf-8") as handle:
        raw = json.load(handle)
except (OSError, ValueError):
    raw = {}
complete = (
    raw.get("status") == "COMPLETE"
    and int(raw_code) == 0
    and bool(codes)
    and all(code == 0 for code in codes)
)
receipt = {
    "schema": "provider-capture@v1",
    "stamp": stamp,
    "status": "COMPLETE" if complete else "INCOMPLETE",
    "latest_session": raw.get("latest_session"),
    "sessions": raw,
    "adjusted": {
        "batch_exit_codes": codes,
        "instruments": raw.get("members", 0),
        "requests": len(codes),
    },
    "requests_used": int(raw.get("requests_used") or 0) + len(codes),
}
with open(receipt_path, "w", encoding="utf-8") as handle:
    json.dump(receipt, handle, sort_keys=True, indent=2)
    handle.write("\n")
PY
receipt_code=$?

[ "$raw_code" -eq 0 ] && [ "$receipt_code" -eq 0 ] && [ "${#codes[@]}" -gt 0 ] || exit 1
for code in "${codes[@]}"; do
  [ "$code" -eq 0 ] || exit 1
done
exit 0
