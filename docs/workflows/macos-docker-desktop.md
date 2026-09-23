# macOS Docker Desktop: verified host storage

Issue [#217](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/217).
This receipt covers one Intel Mac and the exact images below. It does not
validate native macOS Python, Apple Silicon, Windows, every Docker version,
live provider access, or recovery of a market-capture transaction.

## Verified configuration

| Component | Observed identity |
| --- | --- |
| Host | macOS 26.7, build 25G229, Intel x86_64 |
| Docker Desktop | 4.92.0 (240144) |
| Client / Linux engine | 29.8.0 / 29.8.0, linux/amd64 |
| File sharing | gRPC FUSE; mounted filesystem `fuse.grpcfuse` |
| Validation source | `25ca85b21700b580d62b84959cd4e83582801adb` |
| Host root | `~/SwingTradingAIAssistantData`, owner UID 501, GID 0, mode `0700` |
| Container invocation | Explicit host owner UID/GID, private root ownership initialized as below |

The registry is `ghcr.io/krunaldodiya/swingtradingaiassistant`.

| Role | Immutable digest | Source |
| --- | --- | --- |
| Previous | `sha256:0483beb72f3e94bdac88c5e61d7d6a5543d6051c6f80c6924d52a781336a81bd` | `7e43491210d34a386e2bc14aa7c8b0d96e13b282` |
| Current | `sha256:68f6bf010dd5a50be0a4eb3fb37a9c95b74059077cbc84320486342ee6d03a5b` | `25ca85b21700b580d62b84959cd4e83582801adb` |

Both private digest pulls succeeded. Source labels, repository digests and
manifest configuration digests matched their Linux publication receipts from
runs [35834652653](https://github.com/krunaldodiya/SwingTradingAIAssistant/actions/runs/35834652653)
and [35892316491](https://github.com/krunaldodiya/SwingTradingAIAssistant/actions/runs/35892316491).
Docker's local image ID here is the manifest digest; the publication receipt's
image ID is the configuration digest. Compare like identities.

## Setup and ownership

Docker Desktop's user CLI installation needs this entry in `~/.zshrc`:

```sh
export PATH="$HOME/.docker/bin:$PATH"
```

Open a new terminal after updating it. Authenticate to private GHCR using the
[existing publication guidance](published-oci.md); never embed credentials in
commands, images, receipts or the data root.

In Docker Desktop **Settings > General**, select **gRPC FUSE** for file sharing
and apply/restart. Verify the selected backend before drawing conclusions.
Docker documents this choice in its
[settings guide](https://docs.docker.com/desktop/settings-and-maintenance/settings/).
On this host the default VirtioFS backend translated ownership to the caller's
UID and admitted the wrong UID. It did not pass this issue's mount matrix.

Before running against existing data, verify that the host path and its
components are not symlinks, the root belongs to the current host user and its
mode is `0700`. Stop on a mismatch; do not recursively change owners or loosen
permissions. Keep the existing host directory and backup intact.

Fresh gRPC FUSE mounts initially reported root UID 0. Explicitly setting the
mount root to its **existing host** UID/GID made the identity stable across
containers and a full Desktop relaunch. After the host checks, initialize only
the root's guest ownership using the published image (set `IMAGE` to one exact
digest above):

```sh
HOST_DATA="$HOME/SwingTradingAIAssistantData"
HOST_UID="$(stat -f '%u' "$HOST_DATA")"
HOST_GID="$(stat -f '%g' "$HOST_DATA")"
test "$HOST_UID" = "$(id -u)" || exit 1
test "$(stat -f '%Lp' "$HOST_DATA")" = 700 || exit 1
test -d "$HOST_DATA" && test ! -L "$HOST_DATA" || exit 1
docker run --rm --network none --read-only --cap-drop ALL \
  --security-opt no-new-privileges --user "$HOST_UID:$HOST_GID" \
  --mount "type=bind,src=$HOST_DATA,dst=/data" \
  --entrypoint python "$IMAGE" -c \
  'import os; os.chown("/data", int(os.sys.argv[1]), int(os.sys.argv[2]))' \
  "$HOST_UID" "$HOST_GID"
```

Check host UID, GID, mode and root inode again: they must remain unchanged.
This is non-recursive ownership initialization, not a waiver of application
checks. Use the same owner UID/GID for subsequent commands. Never replace a
storage refusal with a root container, `chmod 777`, or copied container data.

The existing host root initially had no ingestion lock. An offline normal
`market-data download --storage-root /data` invocation created its private
lock and returned `UNAVAILABLE` with zero provider attempts. This was not a
successful market download. Existing roots must use the normal downloader
initialization path; do not handcraft a lock or bypass nonempty-root refusal.

Use the mounted command from [published OCI guidance](published-oci.md), with
`--user "$HOST_UID:$HOST_GID"`, the host root bound to `/data`, and
`--storage-root /data`. Provider credentials and real captures require their
existing governed workflow; this verification supplied no provider credential.

## Observed acceptance results

Both images passed installed `market-data --help` and `equity-data-download
--help`. Their installed provider-free demo was run with `--scenario complete`
and `--scenario malformed`, network disabled, read-only container filesystem,
a bounded temporary `/tmp`, dropped capabilities and no new privileges.

| Fixture | Previous image | Current image |
| --- | --- | --- |
| Complete exit | 0 | 0 |
| Complete stdout SHA-256 | `c090f02c98f7195f8fadb2ba33d80757146c150420cb0e3d58297812a535b672` | `105e5b437f1daca41539b955088842b704b1ee49518036668a53a6bdebbfeef0` |
| Result identity | `3265f50751b26a0bf5c8fab13d3f3d90f500a8c44b38440402daf7af6c0bcb97` | `1d327b0649fadeaf1adbb2bc2ab068efe68a47c54bd9c7e20a5a7029471d2b2f` |
| Malformed | Exit 2, empty stdout, `request_invalid` stderr | Same |

All outputs and result identities matched the same-digest Linux baselines.
These fixtures test research behavior on synthetic data, not live market facts.

The current image's initialized gRPC FUSE mount matrix used disposable host
directories and the actual `research-current --storage-root /data` CLI:

| Case | Result |
| --- | --- |
| Private `0700`, owner UID 501 | Storage admitted; expected offline `calendar / HTTP_FAILURE` |
| Same root, UID 502 | `storage / STORAGE_UNSAFE_OR_HELD` |
| Broad `0755` | Same storage refusal |
| Read-only mount | Same storage refusal |
| Symlink selected root | Same storage refusal |

The actual data root was also bound to `/data` and passed storage admission.
Following the Desktop relaunch, UID 501 was again admitted and UID 502 refused.
Root UID/GID/mode stayed 501/0/0700. These are application refusal checks, not
a sandbox claim against someone controlling the Docker daemon or the host user.

A new retained synthetic result was written through the bind mount under
`issue217-desktop-synthetic-88fd86fa92/synthetic-result.json`. The verification
helper explicitly received `--storage-root /data`; it did not invoke a live
capture. Its SHA-256 is the previous-image complete stdout hash above.
Container recreation, old-to-new image upgrade, digest rollback and Desktop
relaunch preserved both that hash and the host inode. A separate synthetic
write in the same dedicated test directory was interrupted with SIGKILL
(exit 137); the committed fixture remained unchanged. No real capture
transaction, interrupted market download or historical-data migration is claimed.

Published build provenance uses only the exact wheel and hash-locked
requirements; the final application copy is `/opt/app`. Image configuration
had no credential environment keys. Inspected owner-data/credential paths
(`/data`, `/Users`, Docker config and the app user's market-data directory)
were absent in the exact images. Combined with immutable digest verification,
this establishes exclusion of the owner's captures and registry/provider
credentials from this build; it is not an exhaustive dependency secret scan.

## Restart limitation and recovery

One `docker desktop restart` failed: the backend remained starting with an
unreachable engine and no new guest boot log. Normal stop also timed out.
With no application containers running, `docker desktop stop --force` followed
by a fresh start recovered the runtime without resetting or deleting its VM
disk. Root ownership, fixture hash/inode, positive admission and wrong-UID
refusal were checked again after recovery. This failed attempt is retained;
seamless Desktop restart reliability is not claimed. Do not force-stop active
captures as routine troubleshooting. Preserve data and inspect runtime status
and logs before choosing recovery.

Detailed local operational receipts are retained under the repository's private
Git metadata in `issue217-evidence`: Desktop fixture, initialized mount, root
mapping, persistence and post-relaunch JSON receipts. They contain synthetic
results or redacted metadata. Colima failures and unsuccessful Desktop mount
configurations remain historical evidence; none supplies a passing verdict for
the configuration documented here. Repository changes are Markdown-only;
`git diff --check` is the applicable change gate. The host runtime experiments
above are issue acceptance work, not a justification for a full repository suite.
