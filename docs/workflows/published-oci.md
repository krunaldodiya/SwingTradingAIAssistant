# Published OCI distribution and host data

Issue [#167](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/167) uses a Linux x86_64 image in private GHCR. The publication workflow runs only after a successful `CI` push run for the exact current `main` commit. It rebuilds the wheel from that commit, runs the native/OCI distribution verifier, publishes a commit-qualified tag, pulls the registry digest, and checks that the pulled image has the verified local image ID and CLI. Its retained `oci-publication-<commit>.json` receipt records source, wheel, requirements and image identities. Use the `ghcr.io/krunaldodiya/swingtradingaiassistant@sha256:...` **digest** from that receipt; a tag is only a discovery aid.

| Runtime | Evidence from this issue |
| --- | --- |
| Linux x86_64 native Python 3.11 wheel | Verified installed-wheel smoke. |
| Linux x86_64 Docker/OCI | Verified local conformance and post-publication digest pull/smoke. |
| macOS native Python | Existing POSIX path preserved, not revalidated here. |
| macOS Docker Desktop | Intel macOS 26.7 / Desktop 4.92.0 verified with initialized gRPC FUSE ownership; see [host receipt and limitations](macos-docker-desktop.md). Default VirtioFS did not pass. |
| Windows 11 x64, WSL2 Ubuntu and Docker Desktop | Exact tested configuration, pinned artifacts and governed CI are described in the [Windows host guide](windows-wsl2-docker-desktop.md) under [#208](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/208). Windows 10, NTFS private roots and native Windows Python remain unverified/unsupported. |
| Linux ARM64 or other architectures | No published image or support claim. |

## Keep captures on the host

The persistent data root is **`$HOME/SwingTradingAIAssistantData` on the host**. The native downloader already defaults to this directory. In Docker, explicitly bind this host directory to `/data` and pass `--storage-root /data` to every data-writing or data-reading command. `/data` is a view of the host directory, not a container-owned copy. Never build the host data root into an image, use `docker cp` as the normal storage path, or download into an unmounted container directory. A container's writable layer is disposable; existing sessions must remain under the host directory across image upgrades and rollback.

On Linux or macOS, create the directory with private permissions before the first run. On Windows, run these POSIX shell commands inside a WSL2 distribution and keep the directory on that distribution's Linux filesystem under its `$HOME`; do not use `/mnt/c` for the private root until the filesystem permissions have been validated. Docker Desktop must be configured to access that WSL2 distribution. These are deployment instructions, not Windows/macOS host conformance evidence.

```sh
HOST_DATA="$HOME/SwingTradingAIAssistantData"
install -d -m 700 "$HOST_DATA"
test -d "$HOST_DATA" && test ! -L "$HOST_DATA"
if ! stat -c '%a %u %g' "$HOST_DATA"; then
  stat -f '%Lp %u %g' "$HOST_DATA"  # macOS
fi
```

Set `IMAGE` to the exact published digest from the release receipt. Authenticate to private GHCR with your own least-privilege `read:packages` credential through Docker's supported login flow; do not put a token in the command line, image, build context, environment-file committed to Git, or data directory.

```sh
IMAGE='ghcr.io/krunaldodiya/swingtradingaiassistant@sha256:<published-digest>'
docker pull --platform linux/amd64 "$IMAGE"
docker run --rm --platform linux/amd64 --read-only \
  --tmpfs /tmp:rw,noexec,nosuid,nodev,size=64m \
  --cap-drop ALL --security-opt no-new-privileges \
  --user "$(id -u):$(id -g)" \
  --mount "type=bind,src=$HOST_DATA,dst=/data" \
  "$IMAGE" research-current --symbol PNB --storage-root /data \
  --contract-version v2 --question PRICE_BEHAVIOR --output json
```

For a downloader operation, use the same mount and select its installed entry point. Supply the instrument and market-day range required by that command; credentials remain in the existing host secret store and are passed only at run time through the governed credential path. The example deliberately does not include a token or trigger a live download.

```sh
docker run --rm --platform linux/amd64 --read-only \
  --tmpfs /tmp:rw,noexec,nosuid,nodev,size=64m \
  --cap-drop ALL --security-opt no-new-privileges \
  --user "$(id -u):$(id -g)" \
  --mount "type=bind,src=$HOST_DATA,dst=/data" \
  --entrypoint equity-data-download "$IMAGE" --help
# An actual invocation must include --storage-root /data as well as its instrument and dates.
```

The private-root admission checks require matching owner UID/GID, restrictive mode, safe path traversal and usable locking. A bind mount provided by a desktop VM may expose different ownership or permissions; stop if the tool returns `STORAGE_UNSAFE_OR_HELD` rather than relaxing the root or copying data into the image. Test the exact host before labelling it supported. Keep a backup of the host directory before upgrades. To upgrade, pull and smoke a new digest while leaving `$HOST_DATA` in place; to roll back, rerun the prior verified digest against the same host directory after checking its installed CLI. Never delete or recreate the host root as part of image rollback.

The image uses the same deterministic application and CLI contracts on Linux. Platform-specific mount integration and provider credentials are outside the synthetic distribution smoke. A successful Linux container test does not prove Docker Desktop behavior on another host.
