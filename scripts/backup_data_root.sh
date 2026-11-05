#!/usr/bin/env bash
# Encrypted, verified backup of the private data root to an rclone remote.
#
#   create archive -> encrypt -> verify decrypt -> write manifests -> upload
#   -> verify the remote -> replace the previous snapshot -> remove staging
#
# The previous snapshot is replaced only after the uploaded bytes are verified,
# so a failed verification can never leave the remote without a trusted backup.
# The passphrase is never uploaded unless asked, and the remote passphrase file
# is never deleted.
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
STAGING_OWNED=0
UPLOAD_DIR=""
ARCHIVE=""
ENCRYPTED=""
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
  --staging DIR           working directory (default a fresh temp dir). Only the
                          files this script creates are removed from a caller dir.
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
    if [ "$STAGING_OWNED" -eq 1 ]; then
      rm -rf "$STAGING"
    else
      [ -n "$UPLOAD_DIR" ] && rm -rf "$UPLOAD_DIR"
      [ -n "$ARCHIVE" ] && rm -f "$STAGING/$ARCHIVE"
      [ -n "$ENCRYPTED" ] && rm -f "$STAGING/$ENCRYPTED"
      rm -f "$STAGING/verify.tar.gz"
    fi
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
  info "remote $REMOTE (previous snapshot in that folder is replaced after verification)"
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
  STAGING_OWNED=1
else
  mkdir -p "$STAGING" || fail "cannot create staging directory"
  STAGING_OWNED=0
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
# The plaintext archive has served its purpose; only the encrypted copy is kept.
rm -f "$STAGING/$ARCHIVE"

ARCHIVE_HASH=$(sha256sum "$STAGING/$ENCRYPTED" | cut -d' ' -f1)
SNAPSHOT=$(date -u +%Y-%m-%dT%H:%M:%SZ)

if [ "$UPLOAD_KEY" -eq 1 ]; then
  KEY_FILE_NAME="RECOVERY-KEY.txt"
  KEY_LINE="\"recovery_key_file\": \"RECOVERY-KEY.txt\","
  RESTORE_DOWNLOADS="Download the archive, SHA256SUMS and RECOVERY-KEY.txt from this folder."
  RESTORE_DECRYPT="--passphrase-file RECOVERY-KEY.txt"
else
  KEY_FILE_NAME=""
  KEY_LINE="\"recovery_key_file\": null,
  \"recovery_key_storage\": \"OFFLINE - not stored beside the archive\","
  RESTORE_DOWNLOADS="Download the archive and SHA256SUMS. The passphrase is held offline, not in this folder."
  RESTORE_DECRYPT="--passphrase-file <your recovery key>"
fi

printf '%s  %s\n' "$ARCHIVE_HASH" "$ENCRYPTED" > "$UPLOAD_DIR/SHA256SUMS"
cat > "$UPLOAD_DIR/VERIFICATION.json" <<JSON
{
  "archive": "$ENCRYPTED",
  "archive_bytes": $(stat -c %s "$STAGING/$ENCRYPTED"),
  "archive_sha256": "$ARCHIVE_HASH",
  "decryption_verified": true,
  $KEY_LINE
  "encryption": "gpg symmetric AES256",
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

$RESTORE_DOWNLOADS Restore into a NEW empty directory:

\`\`\`sh
sha256sum --check SHA256SUMS
gpg --batch --pinentry-mode loopback $RESTORE_DECRYPT --output $ARCHIVE --decrypt $ENCRYPTED
mkdir -m 700 restored-data
tar --extract --gzip --preserve-permissions --file $ARCHIVE --directory restored-data
\`\`\`

The archive contains the folder contents (top-level entries), so extraction into a fresh directory yields the data root directly.
Archive SHA-256: $ARCHIVE_HASH
RESTORE

cp "$STAGING/$ENCRYPTED" "$UPLOAD_DIR/" || fail "cannot stage encrypted archive"
if [ "$UPLOAD_KEY" -eq 1 ]; then
  cp "$PASSPHRASE_FILE" "$UPLOAD_DIR/$KEY_FILE_NAME" || fail "cannot stage passphrase"
  info "WARNING: the passphrase is being uploaded beside the archive"
fi

info "uploading to $REMOTE"
"$RCLONEBIN" copy "$UPLOAD_DIR" "$REMOTE" --stats-one-line || fail "upload failed"

if ! REMOTE_FILES=$("$RCLONEBIN" lsf "$REMOTE" --files-only); then
  fail "cannot list $REMOTE; leaving the previous snapshot untouched"
fi
OLD_ARCHIVES=()
while IFS= read -r name; do
  [ -n "$name" ] || continue
  case "$name" in
    *.tar.gz.gpg) [ "$name" = "$ENCRYPTED" ] || OLD_ARCHIVES+=("$name") ;;
  esac
done <<< "$REMOTE_FILES"

# Verify the uploaded bytes before removing anything from the remote.
EXCLUDE=()
if [ "$UPLOAD_KEY" -eq 0 ]; then
  EXCLUDE+=(--exclude "/RECOVERY-KEY.txt")
fi
for old in "${OLD_ARCHIVES[@]}"; do
  EXCLUDE+=(--exclude "/$old")
done
"$RCLONEBIN" check "$UPLOAD_DIR" "$REMOTE" --checksum "${EXCLUDE[@]}" \
  || fail "remote verification failed; the previous snapshot was left in place"

for old in "${OLD_ARCHIVES[@]}"; do
  "$RCLONEBIN" deletefile "$REMOTE/$old" || fail "cannot remove previous snapshot $old"
  info "removed previous snapshot $old"
done

info "done: $REMOTE/$ENCRYPTED"
info "sha256 $ARCHIVE_HASH"
info "files $FILES, dirs $DIRS, symlinks $LINKS, entries $ENTRIES"
