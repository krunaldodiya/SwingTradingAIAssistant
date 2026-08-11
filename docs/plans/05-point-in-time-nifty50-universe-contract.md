# Point-in-time Nifty 50 universe contract

`Nifty50UniverseSnapshotV1` is offline, vendor-neutral evidence supplied by a
caller. It never downloads or scrapes membership and makes no claim that a
current list is historical authority.

Each canonical JSON object names exactly 50 constituents, sorted by ISIN. ISIN
is the stable identity; `symbol` is only the historical source alias. Sector is
an opaque bounded source label. The schema records inclusive effective dates
and separate membership and sector source, release, published and retrieved
timestamps. Both publication timestamps must be no later than retrieval.

Objects are canonical UTF-8 JSON, bounded to 64 KiB and retained immutably at
`universe_snapshots/sha256=<digest>/snapshot.json` under `StorageRootLease`.
The catalog contains metadata only. Replays must match exact bytes; unsafe root,
symlink, missing, changed, or corrupt objects fail closed.

Resolution needs both `as_of` and `knowledge_cutoff`: it selects exactly one
snapshot covering the date whose membership *and* sector publication and
retrieval timestamps were known by that cutoff. Missing coverage, stale
knowledge, ambiguity, and corrupt evidence are distinct failures. It never
backfills a current universe into a historical query.

## Catalog v3 migration and recovery

Plan 04's v2 public-preview boundary remains compatible and frozen.  V3 adds
only `universe_snapshots`, with migration ID
`swing-trading-catalog-v3-universe-snapshots`, version `3`, and the exact
SHA-256 checksum of the canonical v3 DDL embedded in `catalog.py`.  The table
records the complete source/release/timestamp tuple, SHA-256, byte count, and
the only permitted path
`universe_snapshots/sha256=<digest>/snapshot.json`; its primary key is the
digest.  Empty catalogs create through v3; valid v1 and v2 catalogs migrate
transactionally, validate the whole resulting signature, and roll back both
DDL and ledger row on any error.  Catalogs with an unknown relation, migration,
checksum, or signature fail closed.  A failed post-commit object revalidation
conditionally removes only its exact v3 row, never another snapshot's data.

The retained object chain is owner-private (0700 directories and a 0400,
single-link regular file), descriptor-validated at every checkpoint, fsynced
after directory creation, publication, and cleanup.  A later path replacement,
mode change, hardlink, checksum mismatch, or stale point-in-time evidence is a
typed failure rather than a fallback to current constituents.

ARK-141 must bind a retained provider instrument snapshot by constituent ISIN
under the same cutoff. It must not join to a current symbol.
