#!/usr/bin/env bash
# Project-owned restic incremental backup of the private data root.
#
# The repository, password scope, retention, manifest and restore procedure are
# owned by this project, not by the workstation-wide restic backup.
#
# Exit codes: 0 success, 1 operational failure, 2 invalid input.
set -uo pipefail

STORAGE_ROOT=${SWING_STORAGE_ROOT:-$HOME/SwingTradingAIAssistantData}
REPOSITORY=${SWING_RESTIC_REPOSITORY:-rclone:gdrive:Backups/SwingTradingAIAssistantData-restic}
RESTIC_BIN=${SWING_RESTIC_BIN:-restic}
RCLONE_BIN=${SWING_RCLONE_BIN:-$(command -v rclone || true)}
STATE_DIR=${SWING_BACKUP_STATE_DIR:-$HOME/.local/state/swing-trading-ai-assistant/backup}
MANIFEST_REMOTE=${SWING_BACKUP_MANIFEST_REMOTE-gdrive:Backups/SwingTradingAIAssistantData-restic-manifests}
TAG=${SWING_BACKUP_TAG:-swing-trading-ai-assistant}
KEEP_DAILY=${SWING_BACKUP_KEEP_DAILY:-7}
KEEP_WEEKLY=${SWING_BACKUP_KEEP_WEEKLY:-4}
KEEP_MONTHLY=${SWING_BACKUP_KEEP_MONTHLY:-6}
PRUNE=0
FULL_CHECK=0
DRY_RUN=0
SNAPSHOT=latest
TARGET=""
COMMAND=backup

usage() {
  cat <<'USAGE'
Usage: scripts/backup_data_root_restic.sh [COMMAND] [options]

Commands:
  backup      Run one incremental restic backup, retention and check (default)
  restore     Restore one snapshot into an empty directory
  check       Run restic check on the repository
  init        Initialize a new empty repository
  snapshots   List repository snapshots

Options:
  --storage-root PATH      data root (default $SWING_STORAGE_ROOT)
  --repository REPO        restic repository (default $SWING_RESTIC_REPOSITORY)
  --state-dir PATH         manifest directory (default $SWING_BACKUP_STATE_DIR)
  --manifest-remote DEST   rclone destination for manifests (empty disables)
  --keep-daily N           retain N daily snapshots (default 7)
  --keep-weekly N          retain N weekly snapshots (default 4)
  --keep-monthly N         retain N monthly snapshots (default 6)
  --prune                  prune unreferenced data after retention
  --full-check             read all pack data during restic check
  --snapshot ID            snapshot for restore (default latest)
  --target DIR             empty absolute restore target
  --dry-run                print the plan without writing
  -h, --help
USAGE
}

fail() {
  echo "backup_failed: $*" >&2
  exit 1
}

invalid() {
  echo "backup_invalid: $*" >&2
  exit 2
}

info() {
  echo "backup: $*"
}

warn() {
  echo "backup_warning: $*" >&2
}

if [ "$#" -gt 0 ]; then
  case "$1" in
    backup|restore|check|init|snapshots) COMMAND=$1; shift ;;
    -*) ;;
    *) invalid "unknown command: $1" ;;
  esac
fi

need_value() {
  [ "$#" -ge 2 ] || invalid "missing value for $1"
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --storage-root) need_value "$@"; STORAGE_ROOT=$2; shift 2 ;;
    --repository) need_value "$@"; REPOSITORY=$2; shift 2 ;;
    --state-dir) need_value "$@"; STATE_DIR=$2; shift 2 ;;
    --manifest-remote) need_value "$@"; MANIFEST_REMOTE=$2; shift 2 ;;
    --keep-daily) need_value "$@"; KEEP_DAILY=$2; shift 2 ;;
    --keep-weekly) need_value "$@"; KEEP_WEEKLY=$2; shift 2 ;;
    --keep-monthly) need_value "$@"; KEEP_MONTHLY=$2; shift 2 ;;
    --snapshot) need_value "$@"; SNAPSHOT=$2; shift 2 ;;
    --target) need_value "$@"; TARGET=$2; shift 2 ;;
    --prune) PRUNE=1; shift ;;
    --full-check) FULL_CHECK=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) invalid "unknown argument: $1" ;;
  esac
done

case "$KEEP_DAILY$KEEP_WEEKLY$KEEP_MONTHLY" in
  *[!0-9]*) invalid "retention values must be non-negative integers" ;;
esac
[ -n "$KEEP_DAILY" ] && [ -n "$KEEP_WEEKLY" ] && [ -n "$KEEP_MONTHLY" ] \
  || invalid "retention values must be set"
if [ "$KEEP_DAILY" -eq 0 ] && [ "$KEEP_WEEKLY" -eq 0 ] && [ "$KEEP_MONTHLY" -eq 0 ]; then
  invalid "at least one retention window must be non-zero"
fi

PASSWORD_READY=0
if [ -n "${SWING_RESTIC_PASSWORD:-}" ]; then
  export RESTIC_PASSWORD="$SWING_RESTIC_PASSWORD"
  unset RESTIC_PASSWORD_FILE RESTIC_PASSWORD_COMMAND 2>/dev/null || true
  PASSWORD_READY=1
fi

validate_storage_root() {
  [ -d "$STORAGE_ROOT" ] || invalid "storage root unavailable: $STORAGE_ROOT"
  case "$STORAGE_ROOT" in
    /*) ;;
    *) invalid "storage root must be absolute: $STORAGE_ROOT" ;;
  esac
  [ -L "$STORAGE_ROOT" ] && invalid "storage root must not be a symlink: $STORAGE_ROOT"
  [ "$(stat -c %u "$STORAGE_ROOT" 2>/dev/null || true)" = "$(id -u)" ] \
    || invalid "storage root must be owned by the invoking user: $STORAGE_ROOT"
  MODE=$(stat -c %a "$STORAGE_ROOT" 2>/dev/null || true)
  [ "$MODE" = "700" ] \
    || invalid "storage root must be mode 0700 (found ${MODE:-unknown}): $STORAGE_ROOT"
}

count_source() {
  FILES=$(find "$STORAGE_ROOT" -type f 2>/dev/null | wc -l)
  DIRS=$(find "$STORAGE_ROOT" -type d 2>/dev/null | wc -l)
  LINKS=$(find "$STORAGE_ROOT" -type l 2>/dev/null | wc -l)
  SIZE=$(du -sh "$STORAGE_ROOT" 2>/dev/null | cut -f1)
}

[ -n "$REPOSITORY" ] || invalid "repository is required"
case "$REPOSITORY" in
  *://*@*) invalid "repository must not embed credentials: $REPOSITORY" ;;
esac

if [ "$DRY_RUN" -eq 1 ]; then
  info "dry run, nothing will be written"
  if [ "$COMMAND" = "backup" ]; then
    validate_storage_root
    count_source
    info "source $STORAGE_ROOT ($SIZE, $FILES files, $DIRS dirs, $LINKS symlinks)"
  fi
  info "repository $REPOSITORY"
  info "retention daily=$KEEP_DAILY weekly=$KEEP_WEEKLY monthly=$KEEP_MONTHLY prune=$PRUNE"
  if [ "$PASSWORD_READY" -eq 1 ]; then
    info "restic password is available"
  else
    info "restic password is missing: a real run would fail"
  fi
  if [ "$COMMAND" = "restore" ]; then
    info "restore snapshot=$SNAPSHOT target=${TARGET:-<missing>}"
  fi
  exit 0
fi

[ "$PASSWORD_READY" -eq 1 ] || invalid "SWING_RESTIC_PASSWORD is required"

RESTIC_OPTS=()
case "$REPOSITORY" in
  rclone:*)
    if [ -n "$RCLONE_BIN" ] && [ "${RCLONE_BIN#*/}" != "$RCLONE_BIN" ]; then
      RESTIC_OPTS+=("-o" "rclone.program=$RCLONE_BIN")
    fi
    ;;
esac

restic_run() {
  "$RESTIC_BIN" --repo "$REPOSITORY" \
    ${RESTIC_OPTS[@]+"${RESTIC_OPTS[@]}"} "$@"
}

ensure_repository() {
  restic_run cat config >/dev/null 2>&1
  local code=$?
  case "$code" in
    0) return 0 ;;
    10)
      info "initializing repository $REPOSITORY"
      restic_run init >/dev/null 2>&1 \
        || fail "repository could not be initialized: $REPOSITORY"
      ;;
    *)
      fail "repository is unreadable (restic exit $code); refusing to initialize: $REPOSITORY"
      ;;
  esac
}

case "$COMMAND" in
  init)
    restic_run cat config >/dev/null 2>&1
    code=$?
    case "$code" in
      0) fail "repository is already initialized: $REPOSITORY" ;;
      10)
        restic_run init || fail "restic init failed"
        info "initialized $REPOSITORY"
        exit 0
        ;;
      *)
        fail "repository is unreadable (restic exit $code); refusing to initialize: $REPOSITORY"
        ;;
    esac
    ;;
  snapshots)
    restic_run snapshots || fail "cannot list snapshots"
    exit 0
    ;;
  check)
    CHECK_ARGS=(check)
    [ "$FULL_CHECK" -eq 1 ] && CHECK_ARGS+=(--read-data)
    restic_run "${CHECK_ARGS[@]}" || fail "restic check failed"
    info "check passed for $REPOSITORY"
    exit 0
    ;;
  restore)
    [ -n "$TARGET" ] || invalid "--target is required for restore"
    case "$TARGET" in
      /*) ;;
      *) invalid "--target must be absolute" ;;
    esac
    STORAGE_ROOT_GUARD=${STORAGE_ROOT%/}
    [ -n "$STORAGE_ROOT_GUARD" ] || STORAGE_ROOT_GUARD=/
    case "$TARGET" in
      "$STORAGE_ROOT_GUARD"|"$STORAGE_ROOT_GUARD"/*)
        invalid "restore target must not be inside the data root"
        ;;
    esac
    [ -L "$TARGET" ] && invalid "restore target must not be a symlink"
    SNAPSHOT_PATH=$(
      restic_run snapshots --json | python3 -c '
import json
import sys

wanted = sys.argv[1]
items = json.load(sys.stdin)
if not isinstance(items, list) or not items:
    raise SystemExit(1)
selected = None
if wanted == "latest":
    selected = max(items, key=lambda item: item.get("time", ""))
else:
    for item in items:
        if item.get("id") == wanted or item.get("short_id") == wanted:
            selected = item
            break
if selected is None:
    raise SystemExit(1)
paths = selected.get("paths") or []
if not paths:
    raise SystemExit(1)
print(paths[0])
' "$SNAPSHOT"
    ) || fail "cannot resolve snapshot path"
    if [ -e "$TARGET" ]; then
      [ -d "$TARGET" ] || invalid "restore target is not a directory"
      [ "$(stat -c %u "$TARGET")" = "$(id -u)" ] \
        || invalid "restore target must be owned by the invoking user"
      [ -z "$(ls -A "$TARGET")" ] || invalid "restore target must be empty"
      chmod 700 "$TARGET" || fail "cannot secure restore target"
    else
      mkdir -m 700 "$TARGET" || fail "cannot create restore target"
    fi
    info "restoring snapshot $SNAPSHOT from $REPOSITORY"
    restic_run restore "$SNAPSHOT" --target "$TARGET" --verify \
      || fail "restore failed"
    RESTORED="$TARGET$SNAPSHOT_PATH"
    info "restored to $RESTORED"
    if [ -d "$RESTORED" ]; then
      info "restored files $(find "$RESTORED" -type f | wc -l), directories $(find "$RESTORED" -type d | wc -l)"
    else
      warn "expected restored path not found: $RESTORED"
    fi
    exit 0
    ;;
  backup)
    validate_storage_root
    count_source
    ;;
  *)
    invalid "unknown command: $COMMAND"
    ;;
esac

mkdir -m 700 -p "$STATE_DIR" || fail "cannot create state directory"
JSON="$STATE_DIR/restic-backup.json"
ERR="$STATE_DIR/restic-backup.err"

ensure_repository

HOST=$(hostname 2>/dev/null || echo unknown)
info "backup source $STORAGE_ROOT ($SIZE, $FILES files, $DIRS dirs, $LINKS symlinks)"
info "repository $REPOSITORY"

if ! restic_run backup "$STORAGE_ROOT" --tag "$TAG" --host "$HOST" --json \
    > "$JSON" 2> "$ERR"; then
  warn "restic backup failed"
  tail -n 20 "$ERR" >&2 || true
  fail "backup produced no snapshot"
fi

SUMMARY=$(python3 - "$JSON" <<'PY'
import json
import sys

summary = None
with open(sys.argv[1], encoding="utf-8") as handle:
    for line in handle:
        line = line.strip()
        if not line:
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if value.get("message_type") == "summary":
            summary = value
if not isinstance(summary, dict):
    raise SystemExit(1)
for key in (
    "snapshot_id",
    "files_new",
    "files_changed",
    "data_added",
    "total_files_processed",
    "total_bytes_processed",
    "backup_end",
):
    print(summary.get(key, ""))
PY
) || fail "restic summary is missing"

mapfile -t SUMMARY_FIELDS <<< "$SUMMARY"
SNAPSHOT_ID=${SUMMARY_FIELDS[0]:-}
FILES_NEW=${SUMMARY_FIELDS[1]:-0}
FILES_CHANGED=${SUMMARY_FIELDS[2]:-0}
DATA_ADDED=${SUMMARY_FIELDS[3]:-0}
TOTAL_FILES=${SUMMARY_FIELDS[4]:-0}
TOTAL_BYTES=${SUMMARY_FIELDS[5]:-0}
SNAPSHOT_TIME=${SUMMARY_FIELDS[6]:-$(date -u +%Y-%m-%dT%H:%M:%SZ)}

case "$SNAPSHOT_ID" in
  [0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f]*) ;;
  *) fail "restic did not return a snapshot id" ;;
esac
LENGTH=${#SNAPSHOT_ID}
[ "$LENGTH" -eq 64 ] || fail "restic returned an invalid snapshot id"

restic_run cat snapshot "$SNAPSHOT_ID" >/dev/null 2>&1 \
  || fail "snapshot $SNAPSHOT_ID is not readable"

FORGET_ARGS=(forget --keep-daily "$KEEP_DAILY" --keep-weekly "$KEEP_WEEKLY" --keep-monthly "$KEEP_MONTHLY")
[ "$PRUNE" -eq 1 ] && FORGET_ARGS+=(--prune)
if ! restic_run "${FORGET_ARGS[@]}" > "$STATE_DIR/forget.log" 2>&1; then
  warn "retention failed; snapshot $SNAPSHOT_ID remains"
  tail -n 20 "$STATE_DIR/forget.log" >&2 || true
  fail "retention failed"
fi

CHECK_ARGS=(check)
[ "$FULL_CHECK" -eq 1 ] && CHECK_ARGS+=(--read-data)
if ! restic_run "${CHECK_ARGS[@]}" > "$STATE_DIR/check.log" 2>&1; then
  warn "check failed; snapshot $SNAPSHOT_ID remains"
  tail -n 20 "$STATE_DIR/check.log" >&2 || true
  fail "restic check failed"
fi

SNAPSHOT_TIME=${SNAPSHOT_TIME:-$(date -u +%Y-%m-%dT%H:%M:%SZ)}
CREATED_AT=$(date -u +%Y-%m-%dT%H:%M:%SZ)
RESTIC_VERSION=$("$RESTIC_BIN" version 2>/dev/null | head -n 1)
[ -n "$RESTIC_VERSION" ] || RESTIC_VERSION=unknown

if ! REPOSITORY="$REPOSITORY" SNAPSHOT_ID="$SNAPSHOT_ID" SNAPSHOT_TIME="$SNAPSHOT_TIME" \
HOST="$HOST" STORAGE_ROOT="$STORAGE_ROOT" FILES="$FILES" DIRS="$DIRS" LINKS="$LINKS" \
FILES_NEW="$FILES_NEW" FILES_CHANGED="$FILES_CHANGED" DATA_ADDED="$DATA_ADDED" \
TOTAL_FILES="$TOTAL_FILES" TOTAL_BYTES="$TOTAL_BYTES" RESTIC_VERSION="$RESTIC_VERSION" \
KEEP_DAILY="$KEEP_DAILY" KEEP_WEEKLY="$KEEP_WEEKLY" KEEP_MONTHLY="$KEEP_MONTHLY" \
PRUNE="$PRUNE" FULL_CHECK="$FULL_CHECK" CREATED_AT="$CREATED_AT" \
python3 - "$STATE_DIR" <<'PY'
import json
import os
import pathlib
import sys

state = pathlib.Path(sys.argv[1])
doc = {
    "schema": "data-root-restic-backup@v1",
    "repository": os.environ["REPOSITORY"],
    "snapshot_id": os.environ["SNAPSHOT_ID"],
    "snapshot_time_utc": os.environ["SNAPSHOT_TIME"],
    "host": os.environ["HOST"],
    "source": os.environ["STORAGE_ROOT"],
    "source_regular_files": int(os.environ["FILES"]),
    "source_directories_including_root": int(os.environ["DIRS"]),
    "source_symbolic_links": int(os.environ["LINKS"]),
    "files_new": int(os.environ["FILES_NEW"] or 0),
    "files_changed": int(os.environ["FILES_CHANGED"] or 0),
    "data_added_bytes": int(os.environ["DATA_ADDED"] or 0),
    "total_files_processed": int(os.environ["TOTAL_FILES"] or 0),
    "total_bytes_processed": int(os.environ["TOTAL_BYTES"] or 0),
    "restic_version": os.environ["RESTIC_VERSION"],
    "retention": {
        "keep_daily": int(os.environ["KEEP_DAILY"]),
        "keep_weekly": int(os.environ["KEEP_WEEKLY"]),
        "keep_monthly": int(os.environ["KEEP_MONTHLY"]),
        "prune": os.environ["PRUNE"] == "1",
    },
    "check": "PASS",
    "check_full": os.environ["FULL_CHECK"] == "1",
    "created_at_utc": os.environ["CREATED_AT"],
}
(state / "VERIFICATION.json").write_text(
    json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8"
)
restored_path = f"<target>{os.environ['STORAGE_ROOT']}"
(state / "RESTORE.md").write_text(
    f"""# SwingTradingAIAssistantData restic restore

Repository: `{os.environ['REPOSITORY']}`
Snapshot: `{os.environ['SNAPSHOT_ID']}`
Snapshot time: `{os.environ['SNAPSHOT_TIME']}`

The password is not in this file. It is the Doppler secret
`SWING_RESTIC_PASSWORD` in project `swing-trading`, config `dev_backup`.

```sh
export RESTIC_PASSWORD="<from Doppler>"
restic -r {os.environ['REPOSITORY']} snapshots
mkdir -m 700 restored-data
restic -r {os.environ['REPOSITORY']} restore {os.environ['SNAPSHOT_ID']} \\
  --target restored-data --verify
```

Restic preserves absolute paths under the target. The restored data root is:

```text
{restored_path}
```

Verify the restored tree before replacing anything:

```sh
find restored-data -type f | wc -l
find restored-data -type d | wc -l
```
""",
    encoding="utf-8",
)

PY
then
  fail "manifest write failed"
fi

if [ -n "$MANIFEST_REMOTE" ]; then
  if ! "$RCLONE_BIN" copy "$STATE_DIR" "$MANIFEST_REMOTE" \
      --include "VERIFICATION.json" --include "RESTORE.md" --update \
      > "$STATE_DIR/manifest-upload.log" 2>&1; then
    warn "manifest upload failed; local manifest kept at $STATE_DIR"
    tail -n 10 "$STATE_DIR/manifest-upload.log" >&2 || true
  fi
fi

rm -f "$JSON" "$ERR" "$STATE_DIR/forget.log" "$STATE_DIR/check.log" \
  "$STATE_DIR/manifest-upload.log"

info "done: snapshot $SNAPSHOT_ID"
info "files_new $FILES_NEW, files_changed $FILES_CHANGED, data_added $DATA_ADDED bytes"
info "check passed, retention daily=$KEEP_DAILY weekly=$KEEP_WEEKLY monthly=$KEEP_MONTHLY"
info "manifest $STATE_DIR/VERIFICATION.json"
