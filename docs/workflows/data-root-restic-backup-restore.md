# Data-root restic backup and restore

Status: project-owned incremental backup under [Issue #435](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/435) and [Plan 82](../plans/82-project-owned-restic-data-backup.md).

This is the project’s own backup of `~/SwingTradingAIAssistantData`. It does not
use the workstation-wide restic repository, the workstation restic password, or
the old full GPG snapshot.

## Paths and credentials

| Item | Value |
|---|---|
| Source | `SWING_STORAGE_ROOT` (default `~/SwingTradingAIAssistantData`) |
| Restic repository | `SWING_RESTIC_REPOSITORY` (default `rclone:gdrive:Backups/SwingTradingAIAssistantData-restic`) |
| Password | Doppler `SWING_RESTIC_PASSWORD` in `swing-trading` / `dev_backup` |
| Manifest directory | `SWING_BACKUP_STATE_DIR` (default `~/.local/state/swing-trading-ai-assistant/backup`) |
| Manifest remote | `SWING_BACKUP_MANIFEST_REMOTE` (default `gdrive:Backups/SwingTradingAIAssistantData-restic-manifests`) |

The password is never written to the manifest, the repository path, or command
output. Losing it makes the restic repository unrecoverable.

## Commands

Run through Doppler so the password is injected:

```bash
doppler run --project swing-trading --config dev_backup -- \
  scripts/backup_data_root_restic.sh backup --prune
```

Other modes:

```bash
# Plan only; no repository or manifest writes.
scripts/backup_data_root_restic.sh backup --dry-run

# Verify the repository.
scripts/backup_data_root_restic.sh check
scripts/backup_data_root_restic.sh check --full-check

# List snapshots.
scripts/backup_data_root_restic.sh snapshots

# Restore one snapshot into a new empty directory.
mkdir -m 700 /absolute/restore-target
scripts/backup_data_root_restic.sh restore --snapshot latest \
  --target /absolute/restore-target
```

`backup` initializes a missing repository, then runs `restic backup`, retention
and `restic check`. `--prune` reclaims unreferenced data after retention; the
installed timer uses it explicitly.

## Schedule

`swing-data-backup.timer` runs at **22:00 IST daily** with `Persistent=true`, after
the nightly research pass. `swing-data-backup.service` runs:

```text
doppler run --project <project> --config <config> -- \
  scripts/backup_data_root_restic.sh backup --prune
```

Install or repair the project timers with:

```bash
scripts/install_research_schedule.sh
scripts/install_research_schedule.sh --check
systemctl --user list-timers swing-data-backup.timer --no-pager
```

## Manifest

Every successful backup writes:

- `VERIFICATION.json` — schema `data-root-restic-backup@v1`, repository,
  snapshot ID, snapshot time, source counts, `files_new`, `files_changed`,
  `data_added_bytes`, restic version, retention, check result.
- `RESTORE.md` — exact restore commands and the restored-path layout.

The manifest is uploaded with `rclone copy --update`. A manifest upload failure
does not invalidate the snapshot; the local manifest remains and the next run
retries.

## Restore and verification

Restic preserves absolute paths under the restore target. A snapshot of
`/home/<user>/SwingTradingAIAssistantData` restores to:

```text
<target>/home/<user>/SwingTradingAIAssistantData
```

Verify a restore before replacing anything:

```bash
find <target>/home/<user>/SwingTradingAIAssistantData -type f | wc -l
find <target>/home/<user>/SwingTradingAIAssistantData -type d | wc -l
```

The restore drill required by Plan 82 compares those counts and sample file
hashes with the source. A backup is not accepted until that drill passes.

## Retention

Default retention is 7 daily, 4 weekly and 6 monthly snapshots. At least one
window must be non-zero. `--prune` is explicit and removes unreferenced pack
data; it never runs unless requested.

## Failure rules

- Missing password or missing/unsafe storage root: exit `2`, no repository effect.
- Wrong repository password or unreadable repository: exit `1`, no snapshot claim.
- Restic backup failure: exit `1`, previous snapshots untouched.
- Retention or check failure after a successful snapshot: exit `1`; the snapshot
  remains and the failure is reported.
- Manifest upload failure: the snapshot remains valid; the local manifest is
  kept and the failure is reported.

## Transition completed

The full `scripts/backup_data_root.sh` feature, its tests and its documentation
were removed after the restic backup, timer and restore drill passed (Issue #435).
The old `gdrive:SwingTradingAIAssistantData` archive and recovery key were deleted
after that verification and owner confirmation.

The workstation-global restic backup excludes `~/SwingTradingAIAssistantData`;
this project-owned restic repository is the authoritative data-root backup.
