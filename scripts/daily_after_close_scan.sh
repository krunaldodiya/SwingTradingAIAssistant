#!/usr/bin/env bash
# Daily after-close Nifty 200 scan and retained G09 diary page.
#
# This script is the project-owned version of the former ~/daily-scan/run.sh.
# It guards weekends, intraday hours, NSE closures, and duplicate same-day pages.
# Environment overrides:
#   SWING_REPO, SWING_STORAGE_ROOT, SWING_LOG_DIR, DOPPLER_BIN
#   SWING_DATE_OVERRIDE (YYYY-MM-DD, for tests/dry runs)
#   SWING_DRY_RUN=1 (print the decision, do not scan)
#   SWING_ALLOW_OVERWRITE=1 (allow a second page for the same date)
set -u

REPO=${SWING_REPO:-/home/krunaldodiya/WorkSpace/Code/SwingTradingAIAssistant}
STORE=${SWING_STORAGE_ROOT:-/home/krunaldodiya/SwingTradingAIAssistantData}
LOG=${SWING_LOG_DIR:-/home/krunaldodiya/daily-scan}
DOPPLER=${DOPPLER_BIN:-/home/krunaldodiya/.local/bin/doppler}
STAMP=${SWING_DATE_OVERRIDE:-$(date +%F)}
DRY_RUN=${SWING_DRY_RUN:-0}
mkdir -p "$LOG"

dow=$(date -d "$STAMP" +%u)
hour=$(date +%-H)
if [ "$dow" -ge 6 ]; then
  echo "$(date -Is) skipped: weekend (NSE closed)" >> "$LOG/skipped.log"
  [ "$DRY_RUN" = "1" ] && echo "SKIP weekend"
  exit 0
fi
if [ -z "${SWING_DATE_OVERRIDE:-}" ] && [ "$hour" -ge 8 ] && [ "$hour" -lt 20 ]; then
  echo "$(date -Is) skipped: 08:00-19:59 IST (intraday or provider not published)" >> "$LOG/skipped.log"
  [ "$DRY_RUN" = "1" ] && echo "SKIP intraday"
  exit 0
fi

holiday=$(
  python3 - "$STORE" "$STAMP" <<'PY'
import glob
import json
import os
import sys
from datetime import date

root, target = sys.argv[1], date.fromisoformat(sys.argv[2])
best = None
for path in sorted(glob.glob(os.path.join(root, "**", "calendar-schedules", "**", "*.json"), recursive=True)):
    try:
        if os.path.islink(path) or not os.path.isfile(path):
            continue
        with open(path) as handle:
            value = json.load(handle)
        if not isinstance(value, dict):
            continue
        if not (date.fromisoformat(value["covered_from"]) <= target <= date.fromisoformat(value["covered_to"])):
            continue
        as_of = str(value.get("as_of", ""))
        if best is None or as_of > best[0]:
            best = (as_of, value)
    except (OSError, ValueError, KeyError, TypeError):
        continue
if best is None:
    print("NO_COVERAGE")
    raise SystemExit(0)
value = best[1]
closures = {str(item.get("trade_date")) for item in value.get("closures", []) if isinstance(item, dict)}
sessions = {str(item.get("trade_date")) for item in value.get("sessions", []) if isinstance(item, dict)}
if str(target) in closures:
    print("CLOSED")
elif sessions and str(target) not in sessions:
    print("CLOSED")
else:
    print("TRADING")
PY
)
if [ "$holiday" = "CLOSED" ]; then
  echo "$(date -Is) skipped: NSE closure ($STAMP)" >> "$LOG/skipped.log"
  [ "$DRY_RUN" = "1" ] && echo "SKIP holiday"
  exit 0
fi
if [ "$holiday" = "NO_COVERAGE" ]; then
  echo "$(date -Is) warning: no schedule coverage for $STAMP; proceeding" >> "$LOG/skipped.log"
fi

PAGE="$LOG/scan-$STAMP.json"
if [ -f "$PAGE" ] && [ "${SWING_ALLOW_OVERWRITE:-0}" != "1" ]; then
  echo "$(date -Is) skipped: duplicate page for $STAMP" >> "$LOG/skipped.log"
  [ "$DRY_RUN" = "1" ] && echo "SKIP duplicate"
  exit 0
fi

if [ "$DRY_RUN" = "1" ]; then
  echo "WOULD_SCAN $STAMP"
  exit 0
fi

cd "$REPO" || exit 1
"$DOPPLER" run -- "$REPO/.venv/bin/signal-decisions" scan \
  --storage-root "$STORE" \
  --nifty200 --refresh --retain-decision-evidence --output json \
  > "$PAGE" 2> "$LOG/scan-$STAMP.err"
code=$?
echo "$(date -Is) exit_code=$code" >> "$LOG/scan-$STAMP.err"
exit "$code"
