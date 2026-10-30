#!/usr/bin/env bash
# Install (or reinstall) the repository-owned research scheduling units.
#
# Two independent schedules live here, both owned by this repository:
#   swing-daily-scan.timer    runs the after-close Nifty 200 research pass
#   research-ledger-sync.timer mirrors the private ledger to Google Drive hourly
#
# The unit templates are tracked under scripts/systemd/. This installer renders
# them with this checkout's absolute paths and writes the result into the user
# systemd directory, so deleting a home directory cannot lose either schedule:
# re-running this script restores both from version-controlled source.
#
# Usage:
#   scripts/install_research_schedule.sh            # install and enable both
#   scripts/install_research_schedule.sh --status   # show current state
#   scripts/install_research_schedule.sh --uninstall
#   scripts/install_research_schedule.sh --check    # verify units are installed
#
# Environment overrides:
#   SWING_STORAGE_ROOT, SWING_DOPPLER_PROJECT, SWING_DOPPLER_CONFIG,
#   SWING_LEDGER_ROOT, SWING_SYNC_LOG_DIR
set -eu

REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
UNIT_SRC="$REPO/scripts/systemd"
UNIT_DST="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
STORE=${SWING_STORAGE_ROOT:-$HOME/SwingTradingAIAssistantData}
LEDGER=${SWING_LEDGER_ROOT:-$HOME/SwingTradingAIAgentLedgerVault}
LOGDIR=${SWING_SYNC_LOG_DIR:-$HOME/.local/state/rclone}
PROJECT=${SWING_DOPPLER_PROJECT:-swing-trading}
CONFIG=${SWING_DOPPLER_CONFIG:-dev}

SCAN_SERVICE=swing-daily-scan.service
SCAN_TIMER=swing-daily-scan.timer
SYNC_SERVICE=research-ledger-sync.service
SYNC_TIMER=research-ledger-sync.timer

status() {
  systemctl --user list-timers "$SCAN_TIMER" "$SYNC_TIMER" --no-pager 2>/dev/null || true
}

verify() {
  local failed=0
  for unit in "$SCAN_TIMER" "$SYNC_TIMER"; do
    if systemctl --user is-enabled "$unit" >/dev/null 2>&1; then
      echo "enabled: $unit"
    else
      echo "MISSING: $unit" >&2
      failed=1
    fi
  done
  for unit in "$SCAN_SERVICE" "$SYNC_SERVICE"; do
    if [ -f "$UNIT_DST/$unit" ]; then
      echo "installed: $unit"
    else
      echo "MISSING: $unit" >&2
      failed=1
    fi
  done
  return "$failed"
}

case "${1:-}" in
  --status)
    status
    exit 0
    ;;
  --check)
    verify
    exit $?
    ;;
  --uninstall)
    for unit in "$SCAN_TIMER" "$SYNC_TIMER"; do
      systemctl --user disable --now "$unit" 2>/dev/null || true
    done
    rm -f "$UNIT_DST/$SCAN_TIMER" "$UNIT_DST/$SCAN_SERVICE"
    rm -f "$UNIT_DST/$SYNC_TIMER" "$UNIT_DST/$SYNC_SERVICE"
    systemctl --user daemon-reload
    echo "removed the daily scan and ledger sync units"
    exit 0
    ;;
  "")
    ;;
  *)
    echo "unknown option: $1" >&2
    exit 2
    ;;
esac

render() {
  sed -e "s|@REPO@|$REPO|g" \
      -e "s|@STORE@|$STORE|g" \
      -e "s|@PROJECT@|$PROJECT|g" \
      -e "s|@CONFIG@|$CONFIG|g" \
      -e "s|@LEDGER@|$LEDGER|g" \
      -e "s|@LOGDIR@|$LOGDIR|g" \
      "$1"
}

mkdir -p "$UNIT_DST" "$LOGDIR"
render "$UNIT_SRC/$SCAN_SERVICE" > "$UNIT_DST/$SCAN_SERVICE"
render "$UNIT_SRC/$SCAN_TIMER" > "$UNIT_DST/$SCAN_TIMER"
render "$UNIT_SRC/$SYNC_SERVICE" > "$UNIT_DST/$SYNC_SERVICE"
render "$UNIT_SRC/$SYNC_TIMER" > "$UNIT_DST/$SYNC_TIMER"
chmod 644 "$UNIT_DST/$SCAN_SERVICE" "$UNIT_DST/$SCAN_TIMER"
chmod 644 "$UNIT_DST/$SYNC_SERVICE" "$UNIT_DST/$SYNC_TIMER"
systemctl --user daemon-reload
systemctl --user enable --now "$SCAN_TIMER"
systemctl --user enable --now "$SYNC_TIMER"
status
