#!/usr/bin/env bash
# Independent provider capture that runs before research.
#
# It reads only the retained official Nifty 200 universe snapshot and the
# calendar date. It never reads the composed exchange calendar, scanner pair
# state, safety eligibility, or research policy. A research or calendar failure
# therefore cannot prevent the provider data from being retained.
#
# The capture writes the existing adjusted-daily session store used by the
# benchmark and long-horizon research. It is bounded to two 100-member provider
# requests per run, resumable/idempotent through the downloader's retained
# request store, and logs its own quota-observable output per batch.
set -u

REPO=${SWING_REPO:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}
STORE=${SWING_STORAGE_ROOT:-$HOME/SwingTradingAIAssistantData}
DOPPLER=${DOPPLER_BIN:-$HOME/.local/bin/doppler}
PROJECT=${SWING_DOPPLER_PROJECT:-swing-trading}
CONFIG=${SWING_DOPPLER_CONFIG:-dev}
DOWNLOADER=${SWING_CAPTURE_DOWNLOADER:-$REPO/.venv/bin/equity-data-download}
START_DAYS=${SWING_CAPTURE_START_DAYS:-45}
LOG=${SWING_LOG_DIR:-$STORE/daily-scan}
STAMP=${SWING_DATE_OVERRIDE:-$(date +%F)}
UNIVERSE="$STORE/universe_snapshots/nifty-universe-v3.json"

[ -d "$STORE" ] || { echo "capture_invalid: storage root unavailable: $STORE" >&2; exit 2; }
[ -f "$UNIVERSE" ] || { echo "capture_invalid: universe snapshot unavailable: $UNIVERSE" >&2; exit 2; }
mkdir -p "$LOG" || exit 1

TMP=$(mktemp) || exit 1
trap 'rm -f "$TMP"' EXIT

python3 - "$UNIVERSE" > "$TMP" <<'PY'
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

mapfile -t lines < "$TMP"
[ "${#lines[@]}" -gt 0 ] || { echo "capture_invalid: no universe instruments" >&2; exit 2; }

START=$(date -d "$STAMP - $START_DAYS days" +%F) || exit 2
OUT="$LOG/capture-$STAMP.json"
ERR="$LOG/capture-$STAMP.err"
: > "$OUT"
: > "$ERR"
code=0

for ((offset = 0; offset < ${#lines[@]}; offset += 100)); do
  args=()
  for line in "${lines[@]:offset:100}"; do
    args+=(--instrument "$line")
  done
  if ! "$DOPPLER" run --project "$PROJECT" --config "$CONFIG" -- \
    "$DOWNLOADER" "${args[@]}" --start "$START" --end "$STAMP" \
    --storage-root "$STORE" >> "$OUT" 2>> "$ERR"; then
    code=1
  fi
done

echo "capture_instruments=${#lines[@]} start=$START end=$STAMP exit=$code" >> "$ERR"
exit "$code"
