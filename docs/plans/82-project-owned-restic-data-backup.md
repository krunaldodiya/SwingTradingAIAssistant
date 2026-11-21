# Plan 82: project-owned restic incremental data backup

Status: **accepted bounded contract** under [Issue #435](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/435). Owner direction: 2026-11-21. Risk tier: R3 data integrity, encryption and restore provenance.

## Outcome

Replace the full GPG data-root snapshot with a project-owned, restic-backed incremental backup. The feature lives in this repository, owns its repository path, password scope, retention, verification and restore procedure, and does not depend on the workstation-wide restic backup.

## Safety sequence

The full-snapshot feature is not deleted first. The order is:

1. Implement the restic backup and its tests.
2. Create the project restic repository and run a real backup.
3. Run `restic check`.
4. Restore into a temporary directory and compare file counts and sample hashes.
5. Install and verify the project timer.
6. Only then remove the full snapshot feature, its tests/docs, the old Drive archive and its recovery key.
7. Only then add `~/SwingTradingAIAssistantData` to the workstation-global restic exclusion.

Until step 5 passes, the verified 2026-11-21 full snapshot remains the fallback.

## Scope

- New `scripts/backup_data_root_restic.sh`.
- New `tests/test_backup_data_root_restic.py`.
- New `scripts/systemd/swing-data-backup.service` and `.timer`.
- Updated `scripts/install_research_schedule.sh` and its installer tests.
- New `docs/workflows/data-root-restic-backup-restore.md`.
- Updated retained-backup guidance in `docs/workflows/automated-nifty100-scan.md`.
- Doppler secret `SWING_RESTIC_PASSWORD` in project `swing-trading`, config `dev_backup`.
- Restic repository: `rclone:gdrive:Backups/SwingTradingAIAssistantData-restic`.
- Manifest destination: `gdrive:Backups/SwingTradingAIAssistantData-restic-manifests`.

## Design

### Backup

- Source: `SWING_STORAGE_ROOT`, default `$HOME/SwingTradingAIAssistantData`.
- Repository: `SWING_RESTIC_REPOSITORY`, default `rclone:gdrive:Backups/SwingTradingAIAssistantData-restic`.
- Password: `SWING_RESTIC_PASSWORD`, injected by Doppler; the script never prints it.
- The script initializes a missing repository, then runs `restic backup` with the
  project tag and host, captures the JSON summary, applies retention
  (`7 daily`, `4 weekly`, `6 monthly`) and optionally prunes.
- `--dry-run` reports source counts, repository, password presence and retention
  without initializing or writing.
- A failure before a verified snapshot exits non-zero and leaves the previous
  snapshot usable.

### Manifest

Every successful backup writes a private `VERIFICATION.json` and `RESTORE.md`
under `SWING_BACKUP_STATE_DIR` (default
`$HOME/.local/state/swing-trading-ai-assistant/backup`). The manifest records:

- schema `data-root-restic-backup@v1`;
- repository and snapshot ID;
- snapshot time and host;
- source path and file/directory/symlink counts;
- restic summary counts (`files_new`, `files_changed`, `data_added`);
- restic version, retention and check result.

The manifest is uploaded with `rclone copy --update` to the manifest destination.
A failed manifest upload is reported but does not invalidate the encrypted
snapshot; the next run retries it.

### Restore

`restore --snapshot latest --target DIR` restores the exact restic snapshot into
an empty private directory. Restic preserves absolute paths under the target, so
the restored data root is resolved from the snapshot itself, not from the current
host's `STORAGE_ROOT`. The script prints that path and freshly counted files and
directories. `check` runs `restic check`; `snapshots` lists repository snapshots.
Only `backup` requires the live data root; restore, check, snapshots and init do
not.

### Schedule

- `swing-data-backup.timer`: daily at 22:00 IST, `Persistent=true`, `AccuracySec=1min`.
- `swing-data-backup.service`: oneshot, after the nightly scan, runs
  `doppler run --project <project> --config <config> -- scripts/backup_data_root_restic.sh backup --prune`.
- `TimeoutStartSec=3600`.

### Failure rules

- Missing or empty `SWING_RESTIC_PASSWORD`: exit 2, no repository effect.
- Missing or unsafe storage root: exit 2, no repository effect.
- Wrong repository password or unreadable repository: exit 1, no snapshot claim.
- Restic backup failure: exit 1, previous snapshots untouched.
- Retention/prune failure after a successful snapshot: exit 1, snapshot remains
  and is reported.
- Manifest upload failure: backup remains valid; the run reports the degraded
  manifest state.
- No destructive prune without `--prune`; the installed unit uses it explicitly.

## Acceptance

- First backup creates a snapshot and manifest.
- Unchanged rerun creates no new file data and reports zero new/changed files.
- Changed-file run uploads only the changed data.
- Restore drill reproduces file counts and sample file hashes.
- `restic check` passes.
- Missing password, invalid root, wrong password and failed restore fail closed.
- Focused tests pass; repository-wide gates apply to the final candidate.
- Timer installed and enabled.
- Documentation names the exact backup, check, restore and password-scope
  commands.

## Delivery evidence (2026-11-21)

- First snapshot `a798d82d10786aeb64bbb4410d821c6dcde17e983d9715947dc1559a6f77fa55`:
  90,165 files, 2,763 directories, full `restic check --read-data` passed.
- Restore drill matched 90,165 files, 2,763 directories, identical paths and sizes,
  and matching sample hashes; restic `--verify` passed.
- Incremental rerun: 0 new files, 0 changed files, 0 bytes added; repository grew
  471 bytes.
- `swing-data-backup.service` exercised successfully with Doppler `dev_backup`;
  `swing-data-backup.timer` enabled for 22:00 IST.
- Full `backup_data_root.sh` feature, test and docs removed; old Drive archive and
  recovery key removed; workstation-global restic excludes the data root.

## Non-goals

- No replacement of the separate ledger mirror.
- No workstation-global restic change inside this repository.
- No new market-data, provider or financial-research behavior.
- No deletion of the full snapshot before the restic backup and restore drill
  pass.
- No automatic deletion of the old Drive archive without explicit confirmation.

## Removal gate

After the restic backup and restore drill pass, a follow-up change removes:

- `scripts/backup_data_root.sh` and `tests/test_backup_data_root.py`;
- the full-snapshot section in `docs/workflows/automated-nifty100-scan.md`;
- the full-snapshot references in the post-install guide;
- `gdrive:SwingTradingAIAssistantData` archive, manifests and recovery key.

The global restic exclusion is a host-level change outside this repository and is
applied only after the project backup is verified.
