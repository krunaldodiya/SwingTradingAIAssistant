#!/usr/bin/env bash
# Encrypted, verified backup of the private data root to an rclone remote.
#
# The procedure used to live only in a RESTORE.md on the remote, so every backup
# was a remembered sequence. This script makes it repeatable:
#
#   create archive -> encrypt -> verify decrypt -> write manifests
#   -> upload -> verify remote -> remove staging
#
# It never uploads the passphrase unless asked, and it never deletes the remote
# passphrase file. Replacing the previous snapshot is deliberate: one snapshot
# per remote folder, so a restore can never pick a stale archive by accident.
#
# Exit codes: 0 success, 1 failure, 2 invalid input.
set -uo pipefail

STORAGE_ROOT=${SWING_STORAGE_ROOT:-$HOME/SwingTradingAIAssistantData}
REMOTE=${BACKUP_REMOTE:-gdrive:SwingTradingAIAssistantData}
PASSPHRASE_FILE=${BACKUP_PASSPHRASE_FILE:-}
GPGBIN=${BACKUP_GPG_BIN:-gpg}
RCLONEBIN=${BACKUP_RCLONE_BIN:-rclone}
TARBIN=${BACKUP_TAR_BIN:-tar}
STAMP=${BACKUP_STAMP:-$(date -u +%Y%m%d)}
STAGING=""
KEEP_LOCAL=0
DRY_RUN=0
UPLOAD_KEY=0

usage() {
  cat <<'USAGE'
Usage: scripts/backup_data_root.sh --passphrase-file PATH [options]

  --storage-root PATH     data root to archive (default $SWING_STORAGE_ROOT or
                          ~/SwingTradingAIAssistantData)
  --remote DEST           rclone destination (default gdrive:SwingTradingAIAssistantData)
  --passphrase-file PATH  file holding the gpg passphrase (required)
  --stamp YYYYMMDD        snapshot label (default today, UTC)
  --staging DIR           working directory (default a fresh temp dir)
  --keep-local            keep the encrypted archive after upload
  --upload-key            also upload the passphrase file (legacy behaviour)
  --dry-run               print the plan and exit without writing anything
  -h, --help
USAGE
}

fail() {
  echo "backup_failed: $*" >&2
  exit 1
}

info() {
  echo "backup: $*"
}

cleanup() {
  if [ -n "$STAGING" ] && [ "$DRY_RUN" -eq 0 ] && [ "$KEEP_LOCAL" -eq 0 ]; then
    rm -rf "$STAGING"
  fi
}
trap cleanup EXIT

while [ "$#" -gt 0 ]; do
  case "$1" in
    --storage-root) STORAGE_ROOT=${2:?missing value}; shift 2 ;;
    --remote) REMOTE=${2:?missing value}; shift 2 ;;
    --passphrase-file) PASSPHRASE_FILE=${2:?missing value}; shift 2 ;;
    --stamp) STAMP=${2:?missing value}; shift 2 ;;
    --staging) STAGING=${2:?missing value}; shift 2 ;;
    --keep-local) KEEP_LOCAL=1; shift ;;
    --upload-key) UPLOAD_KEY=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; echo "backup_invalid: unknown argument $1" >&2; exit 2 ;;
  esac
done

[ -d "$STORAGE_ROOT" ] || { echo "backup_invalid: storage root unavailable: $STORAGE_ROOT" >&2; exit 2; }
case "$STAMP" in
  [0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]) ;;
  *) echo "backup_invalid: stamp must be YYYYMMDD" >&2; exit 2 ;;
esac

FILES=$(find "$STORAGE_ROOT" -type f | wc -l)
DIRS=$(find "$STORAGE_ROOT" -type d | wc -l)
LINKS=$(find "$STORAGE_ROOT" -type l | wc -l)
SIZE=$(du -sh "$STORAGE_ROOT" 2>/dev/null | cut -f1)

ARCHIVE="SwingTradingAIAssistantData-$STAMP.tar.gz"
ENCRYPTED="$ARCHIVE.gpg"

if [ "$DRY_RUN" -eq 1 ]; then
  info "dry run, nothing will be written"
  info "source $STORAGE_ROOT ($SIZE, $FILES files, $DIRS dirs, $LINKS symlinks)"
  info "archive $ENCRYPTED"
  info "remote $REMOTE (previous snapshot in that folder will be replaced)"
  if [ -n "$PASSPHRASE_FILE" ] && [ -r "$PASSPHRASE_FILE" ]; then
    info "passphrase file readable"
  else
    info "passphrase file missing or unreadable: a real run would fail"
  fi
  exit 0
fi

[ -n "$PASSPHRASE_FILE" ] || { echo "backup_invalid: --passphrase-file is required" >&2; exit 2; }
[ -r "$PASSPHRASE_FILE" ] || { echo "backup_invalid: passphrase file unreadable" >&2; exit 2; }

if [ -z "$STAGING" ]; then
  STAGING=$(mktemp -d) || fail "cannot create staging directory"
else
  mkdir -p "$STAGING" || fail "cannot create staging directory"
fi
chmod 700 "$STAGING"
UPLOAD_DIR="$STAGING/upload"
mkdir -p "$UPLOAD_DIR" || fail "cannot create upload directory"

info "archiving $STORAGE_ROOT ($SIZE)"
"$TARBIN" --create --gzip --preserve-permissions \
  --file "$STAGING/$ARCHIVE" -C "$STORAGE_ROOT" . || fail "tar failed"

info "encrypting (gpg symmetric AES256)"
"$GPGBIN" --batch --yes --pinentry-mode loopback \
  --passphrase-file "$PASSPHRASE_FILE" --symmetric --cipher-algo AES256 \
  --output "$STAGING/$ENCRYPTED" "$STAGING/$ARCHIVE" || fail "gpg failed"

info "verifying decryption"
"$GPGBIN" --batch --quiet --pinentry-mode loopback \
  --passphrase-file "$PASSPHRASE_FILE" --decrypt \
  --output "$STAGING/verify.tar.gz" "$STAGING/$ENCRYPTED" || fail "decrypt failed"
SOURCE_HASH=$(sha256sum "$STAGING/$ARCHIVE" | cut -d' ' -f1)
ROUNDTRIP_HASH=$(sha256sum "$STAGING/verify.tar.gz" | cut -d' ' -f1)
[ "$SOURCE_HASH" = "$ROUNDTRIP_HASH" ] || fail "decrypted archive differs from source"
ENTRIES=$("$TARBIN" -tzf "$STAGING/verify.tar.gz" | wc -l)
EXPECTED=$((FILES + DIRS))
[ "$ENTRIES" -ge "$EXPECTED" ] || fail "archive lists $ENTRIES entries, expected at least $EXPECTED"
rm -f "$STAGING/verify.tar.gz"

ARCHIVE_HASH=$(sha256sum "$STAGING/$ENCRYPTED" | cut -d' ' -f1)
SNAPSHOT=$(date -u +%Y-%m-%dT%H:%M:%SZ)

printf '%s  %s\n' "$ARCHIVE_HASH" "$ENCRYPTED" > "$UPLOAD_DIR/SHA256SUMS"
cat > "$UPLOAD_DIR/VERIFICATION.json" <<JSON
{
  "archive": "$ENCRYPTED",
  "archive_bytes": $(stat -c %s "$STAGING/$ENCRYPTED"),
  "archive_sha256": "$ARCHIVE_HASH",
  "decryption_verified": true,
  "encryption": "gpg symmetric AES256",
  "recovery_key_file": "RECOVERY-KEY.txt",
  "snapshot_utc": "$SNAPSHOT",
  "source": "$STORAGE_ROOT",
  "source_directories_including_root": $DIRS,
  "source_regular_files": $FILES,
  "source_symbolic_links": $LINKS,
  "tar_listing_verified": true,
  "tar_entries_verified": $ENTRIES
}
JSON

cat > "$UPLOAD_DIR/RESTORE.md" <<RESTORE
# SwingTradingAIAssistantData backup — $STAMP

Snapshot UTC: $SNAPSHOT. Complete source folder including hidden files:
$FILES regular files and $DIRS directories including the root; $LINKS symbolic links.
The archive was encrypted locally and its decryption plus tar listing were verified.

Download the archive, SHA256SUMS and RECOVERY-KEY.txt from this folder. Restore into a NEW empty directory:

\`\`\`sh
sha256sum --check SHA256SUMS
chmod 600 RECOVERY-KEY.txt
gpg --batch --pinentry-mode loopback --passphrase-file RECOVERY-KEY.txt --output $ARCHIVE --decrypt $ENCRYPTED
mkdir -m 700 restored-data
tar --extract --gzip --preserve-permissions --file $ARCHIVE --directory restored-data
\`\`\`

The archive contains the folder contents (top-level entries), so extraction into a fresh directory yields the data root directly.
Archive SHA-256: $ARCHIVE_HASH
RESTORE

cp "$STAGING/$ENCRYPTED" "$UPLOAD_DIR/" || fail "cannot stage encrypted archive"
if [ "$UPLOAD_KEY" -eq 1 ]; then
  cp "$PASSPHRASE_FILE" "$UPLOAD_DIR/RECOVERY-KEY.txt" || fail "cannot stage passphrase"
  info "WARNING: the passphrase is being uploaded beside the archive"
fi

info "uploading to $REMOTE"
"$RCLONEBIN" copy "$UPLOAD_DIR" "$REMOTE" --stats-one-line || fail "upload failed"

# Replace the previous snapshot without touching the remote passphrase file.
for old in $("$RCLONEBIN" lsf "$REMOTE" --files-only 2>/dev/null | grep -E '\.tar\.gz\.gpg$' || true); do
  if [ "$old" != "$ENCRYPTED" ]; then
    "$RCLONEBIN" deletefile "$REMOTE/$old" || fail "cannot remove previous snapshot $old"
    info "removed previous snapshot $old"
  fi
done

EXCLUDE=()
if [ "$UPLOAD_KEY" -eq 0 ]; then
  EXCLUDE=(--exclude "RECOVERY-KEY.txt")
fi
"$RCLONEBIN" check "$UPLOAD_DIR" "$REMOTE" --checksum "${EXCLUDE[@]}" \
  || fail "remote verification failed"

info "done: $REMOTE/$ENCRYPTED"
info "sha256 $ARCHIVE_HASH"
info "files $FILES, dirs $DIRS, symlinks $LINKS, entries $ENTRIES"
