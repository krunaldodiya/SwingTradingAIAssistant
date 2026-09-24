# Windows WSL2 and Docker Desktop distribution

Issue [#208](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/208)
validates the existing Linux artifacts on a real Windows host. Support is
limited to the recorded Windows 11 Pro x64, build 26200, Ubuntu 26.04 under
WSL2 2.7.14.0 (kernel 6.18.33.2), Docker Desktop 4.92.0 / engine 29.8.0,
and WSL's Linux filesystem. Windows 10, ARM64, native Windows Python, NTFS
private roots (`/mnt/c`, `/mnt/d`), and other Desktop backends remain unverified.
The issue's final receipts and independent reviews govern completion; an
intermediate local pass does not establish CI or merge admission.

## Artifacts and reproducible check

The source is `25ca85b21700b580d62b84959cd4e83582801adb`, version `0.1.0`.
The independently built WSL wheel matches the published Linux wheel exactly:

| Artifact | SHA-256 |
| --- | --- |
| Wheel | `f3c790add4731d4f25a389a739fdc9d2cb0494c1dabae4ef052f780eba2c0c49` |
| Runtime requirements | `04fcc498a40f141db3afac2d51500045c4975cf3dcc6f779b3ed9bc440526030` |
| Published OCI manifest | `68f6bf010dd5a50be0a4eb3fb37a9c95b74059077cbc84320486342ee6d03a5b` |
| Positive public stdout | `105e5b437f1daca41539b955088842b704b1ee49518036668a53a6bdebbfeef0` |

The baseline is the [Linux publication receipt from run 35892316491](https://github.com/krunaldodiya/SwingTradingAIAssistant/actions/runs/35892316491).
The CLI's positive result identity is
`1d327b0649fadeaf1adbb2bc2ab068efe68a47c54bd9c7e20a5a7029471d2b2f`.
The malformed request exits 2 with empty stdout. These are fixed synthetic
2026-08-26 observations, not current market research.

From a clean committed Windows checkout, run in PowerShell:

```powershell
./scripts/verify_windows_distribution.ps1
```

The wrapper records Windows, WSL, Desktop and runner identity, clones the exact
verifier commit onto WSL's Linux filesystem with LF source bytes, and executes
the Python verifier there. Each invocation has a separate directory under
`artifacts/windows-distribution/`; inspect `windows-distribution-receipt.json`
and both installed-test logs. Only `status: PASS` represents a completed run.
The receipt binds the verifier commit/tree separately from the older pinned
release commit, wheel, lock and published digest. WSL source clones remain at
`~/.local/share/issue208/runs/` for diagnosis; disposable synthetic data and
temporary environments are removed when that invocation ends.

The clean wheel smoke runs before exposing pytest tooling. The subsequent
installed-artifact checks use the release's existing deterministic research
tests, with only locked pytest modules on `PYTHONPATH`, never application
`src/`. They exercise retention, exact reuse, source/provenance substitution,
interrupted publication and recovery, failure ordering and public sanitization.
The container suite writes its separate synthetic roots through an owner-mapped
WSL bind mount. Its aggregate retained test data exceeds a single command's
64 MiB `/tmp`; the application's temporary-filesystem limit is unchanged.
These focused checks supplement the required repository CI; they do not replace
its full suite or coverage gate.

## Prepare WSL and install

Enable Docker Desktop's integration for the Ubuntu WSL2 distribution and use
Linux containers. The normal WSL user must be non-root. Python on Windows does
not satisfy the Linux installation requirement. Inside Ubuntu, install the
same already-approved `uv` version and Python 3.11 used by the distribution:

```sh
set -eu
umask 077
mkdir -p "$HOME/.local/share/issue208/tools"
cd "$HOME/.local/share/issue208/tools"
curl -fL -o uv.tar.gz https://github.com/astral-sh/uv/releases/download/0.9.24/uv-x86_64-unknown-linux-gnu.tar.gz
echo 'fb13ad85106da6b21dd16613afca910994446fe94a78ee0b5bed9c75cd066078  uv.tar.gz' | sha256sum -c -
tar -xzf uv.tar.gz
export PATH="$HOME/.local/share/issue208/tools/uv-x86_64-unknown-linux-gnu:$PATH"
uv python install 3.11
```

For a persistent installation, use the [native wheel instructions](linux-native-and-oci.md#native-installation-and-private-storage)
inside WSL, building the exact source revision above in a Linux-filesystem
checkout. Install hash-locked dependencies and the matching wheel with
`--link-mode copy`, into a new versioned environment. The observed WSL Python
was 3.11.14; the published image contains its own 3.11 runtime. Invoke the
installed `market-data --help`, then the installed synthetic demo before
selecting the environment for actual research. The Windows verifier performs
these steps in disposable environments and leaves no production install active.

Authenticate Docker to the private registry using its supported login flow;
never put a credential in this repository or the data root. A successful Git
SSH connection is not GHCR authentication. The observed initial `unauthorized`
pull was resolved by the owner's Docker login; no credential was included in
the wheel, image, test fixture or receipt.

## Private data and image use

Keep captures at **`$HOME/SwingTradingAIAssistantData` inside Ubuntu**. This is
persistent host storage in the WSL virtual disk, independent of a container's
writable layer. Do not place it under `/mnt/c` or `/mnt/d`. For an existing
root, inspect owner, mode and symlinks before use; do not repair it recursively.
For a new root only:

```sh
HOST_DATA="$HOME/SwingTradingAIAssistantData"
install -d -m 700 "$HOST_DATA"
test -d "$HOST_DATA" && test ! -L "$HOST_DATA"
stat -c '%a %u %g' "$HOST_DATA"
IMAGE='ghcr.io/krunaldodiya/swingtradingaiassistant@sha256:68f6bf010dd5a50be0a4eb3fb37a9c95b74059077cbc84320486342ee6d03a5b'
docker pull --platform linux/amd64 "$IMAGE"
docker run --rm --network none --read-only \
  --tmpfs /tmp:rw,noexec,nosuid,nodev,size=64m \
  --cap-drop ALL --security-opt no-new-privileges \
  --user "$(id -u):$(id -g)" \
  --mount "type=bind,src=$HOST_DATA,dst=/data" \
  "$IMAGE" research-current --symbol PNB --storage-root /data \
  --contract-version v2 --question PRICE_BEHAVIOR --output json
```

With a safe root and network disabled, the observed result stops at
`calendar / HTTP_FAILURE`. This proves storage admission, not a download.
Wrong owner, broad `0755` mode, read-only mount and a selected symlink stop at
`storage / STORAGE_UNSAFE_OR_HELD`. UID/GID mapping is required; running the
application as root or loosening permissions is not a remedy. Real provider
access still requires the existing authorization and evidence workflow.

## Upgrade, rollback and backup

Keep the previous versioned WSL environment and OCI digest. Smoke the new
artifact before selecting it, and leave the private root in place. The checked
prior source is `7e43491210d34a386e2bc14aa7c8b0d96e13b282`; its image is
`ghcr.io/krunaldodiya/swingtradingaiassistant@sha256:0483beb72f3e94bdac88c5e61d7d6a5543d6051c6f80c6924d52a781336a81bd`.
Select that digest or prior environment to roll back code. Never recreate the
data root as part of code rollback.

The conformance helper backs up a disposable private synthetic directory with
`tar -cf`, restores it into a separate private directory with `tar -xf`, and
compares the content hash. Old/new/old containers read the unchanged host file,
and its inode is checked after the sequence. Application-level interrupted
publication and retained-evidence reuse are tested separately. This does not
claim a live market-capture restore, schema migration, or restored inode-bound
provenance admission. Before a real upgrade, quiesce writers and use the existing
governed backup process for the WSL data root. Restore into a separate location
for validation before replacing anything. The existing Google Drive backup was
not needed or restored for #208.

## Governed Windows CI

The manually triggered **Windows distribution conformance** workflow accepts
only `main`, has no caller-supplied code or artifact inputs, and uses pinned
checkout/upload actions. Its release constants deliberately require a reviewed
change when testing a new published artifact. It uploads the runner identity,
artifact hashes, progress/failure receipt and installed-test logs for 90 days.
Keep long-lived release evidence linked from the issue before artifact expiry.

The owner authorized runner `swing-windows11-wsl2`, label
`swing-windows-conformance`, installed at `D:\actions-runner-swing` under the
same Windows user as Docker Desktop and Ubuntu. No always-on Windows service
was installed. The runner normally remains offline. After queuing the `main`
workflow, start one job from PowerShell:

```powershell
cd D:\actions-runner-swing
./run.cmd --once
```

Keep this private repository's runner restricted to trusted reviewed code.
Labels and a job's `if` condition are routing controls, not a sandbox against
someone able to change workflows. Do not add pull-request triggers or leave
the listener running for unrelated work. Docker access has host-level power;
no provider credentials or real data are needed by this workflow.

## Troubleshooting and evidence limits

- `unauthorized` from GHCR: complete Docker's login flow, then retry the exact
  digest. GitHub CLI login and Docker registry login are separate.
- Missing Docker engine or WSL integration: start Desktop, select Linux
  containers and enable Ubuntu integration; verify `docker version` in WSL.
- Missing Python/uv: prepare the pinned Linux tools above. Do not substitute
  native Windows Python for POSIX storage checks.
- Runtime identity failure: use a clean LF checkout and copy-installed wheel.
  Do not edit installed source, refresh manifests to conceal drift, or use
  hard-linked runtime files.
- Storage refusal: inspect Linux owner/mode, mount writability and symlinks.
  Preserve the refusal; do not relax the application's checks.

Initial harness failures included Windows backslash conversion, unprivileged
inspection of `/root`, and missing Git ancestry in an exported source tree.
They were corrected in the conformance tooling, without application changes.
An early container-suite run used `/tmp` for every retained test root and failed
after 39 passes with only 2,928,640 bytes free out of 67,108,864. The harness now
uses private host storage for these roots, as required for normal data use.
The positive fixture does not exercise a real provider; the image-path and
environment inspection is not an exhaustive third-party dependency secret
scan. Container kill/recreation is tested; a full Windows reboot or Desktop
restart reliability claim is outside this receipt.
