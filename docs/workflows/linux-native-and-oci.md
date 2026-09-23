# Linux native wheel and local OCI workflow

This is the first bounded distribution slice of [issue #167](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/167#issuecomment-5789001303). It exercises the existing `market-data` CLI from one built wheel on native Linux x86_64 and in a locally built OCI image. The synthetic research example is fixed at 2026-08-26, denies network access, and is not a claim about today's market or provider integration.

| Path | Current claim |
| --- | --- |
| Linux x86_64, clean installed wheel | Verified by the distribution receipt. |
| Linux x86_64, local OCI image | Verified from the same wheel and hash-checked runtime lock export. No registry image is published in this slice. |
| Native macOS | Existing application path is preserved; this slice does not revalidate or expand its support claim. |
| macOS Docker Desktop, Windows WSL2/Docker Desktop, other architectures | Pending later #167 conformance slices; no support claim from the Linux receipt. |

## Build and verify

Use a clean checkout of the intended commit. Docker, `uv`, and Python 3.11 must be available. The verifier creates a temporary Docker build context containing only the wheel and hash-checked requirements exported from `uv.lock`; it passes no owner data or credentials to the build. It builds a versioned local image and writes a receipt with the exact source commit/tree, wheel and requirements SHA-256 values, local image ID, and exercised results.

```sh
uv sync --python 3.11 --extra dev --frozen
uv build --no-build-isolation --python .venv/bin/python
uv run --no-sync --extra dev python scripts/verify_linux_distribution.py \
  --wheel dist/swing_trading_ai_assistant-*.whl \
  --prior-commit "$(git rev-parse HEAD^)" \
  --receipt dist/linux-distribution-receipt.json
```

The receipt's `source_dirty` must be `false` before treating its source revision as an exact committed release candidate. The verifier compares native and OCI `market-data --help`, the positive V2 synthetic CLI result, and the malformed request's exit 2 and empty stdout. It runs the image without network access, all Linux capabilities, privilege escalation, or a writable root filesystem. It also checks wrong UID, broad-mode, read-only and symlinked private roots; a matching owner UID/GID reaches the calendar stage while an unsafe root stops at `STORAGE_UNSAFE_OR_HELD`. A wrong wheel digest is rejected during image build and substituted runtime source cannot produce a public CLI result. An interrupted uncached build cannot replace the current image, an interrupted container run fails, and the current fixture still runs afterward. The prior commit is built into a separate wheel, installed into a clean environment, and its CLI run to demonstrate rollback; the lock must match for this first slice. This is Linux evidence only.

The locally built image tag is reported in the receipt, for example `swing-trading-ai-assistant:0.1.0-<commit-prefix>`. Check the image ID before use:

```sh
docker image inspect 'swing-trading-ai-assistant:0.1.0-<commit-prefix>' \
  --format '{{.Id}} {{.Config.User}}'
```

The image defaults to numeric user/group `10001:10001` and the existing `market-data` entry point. A synthetic run uses its installed Python module and no provider credential:

```sh
docker run --rm --network none --read-only \
  --tmpfs /tmp:rw,noexec,nosuid,nodev,size=64m \
  --cap-drop ALL --security-opt no-new-privileges \
  --entrypoint python 'swing-trading-ai-assistant:0.1.0-<commit-prefix>' \
  -m swing_trading_ai_assistant._examples.single_stock_research_demo \
  --question PRICE_BEHAVIOR
```

## Native installation and private storage

For a persistent native install, export the same locked runtime dependencies and install them with their hashes into a clean Python 3.11 environment. Install the built wheel without resolving a second dependency set. Choose an application-specific destination; do not replace an existing environment in place.

```sh
uv export --locked --no-dev --format requirements-txt --no-emit-project \
  --no-header --no-annotate > dist/runtime-requirements.txt
APP_VENV="$HOME/.local/share/swing-trading-ai-assistant/venvs/0.1.0-<commit-prefix>"
uv venv --python 3.11 "$APP_VENV"
uv pip install --python "$APP_VENV/bin/python" --link-mode copy \
  --require-hashes -r dist/runtime-requirements.txt
uv pip install --python "$APP_VENV/bin/python" --link-mode copy \
  --no-deps dist/swing_trading_ai_assistant-*.whl
"$APP_VENV/bin/market-data" --help
```

The copy install mode is deliberate: the source-at-rest verifier rejects multiply linked runtime files. Keep an existing versioned environment until the new one has passed its smoke. The wheel also contains the explicitly synthetic demonstration module used by the conformance check; it adds no provider or production research command.

For a container command that uses an owner-private data root, create the host directory as the current user with mode `0700` and mount it at `/data`. Match the container process UID/GID to the host owner. Do not copy the directory into the image or use a broad-mode or symlinked root.

```sh
PRIVATE_ROOT="/absolute/path/to/owner-private-data"
docker run --rm --read-only --tmpfs /tmp:rw,noexec,nosuid,nodev,size=64m \
  --cap-drop ALL --security-opt no-new-privileges \
  --user "$(id -u):$(id -g)" \
  --mount "type=bind,src=$PRIVATE_ROOT,dst=/data" \
  'swing-trading-ai-assistant:0.1.0-<commit-prefix>' \
  research-current --symbol PNB --storage-root /data \
  --contract-version v2 --question PRICE_BEHAVIOR --output json
```

That last command is the existing production CLI: its usual provider authorization and evidence gates still apply. The Linux conformance run does not supply credentials or claim a successful live acquisition. Keep secrets in the existing credential boundary; no key belongs in the wheel, image, build context, receipt, or command documentation.

There is no private-data migration in this slice. Back up the host private root using the existing governed backup process before changing a real installation. Roll back code by selecting the prior native environment or prior local image ID and leaving the private root untouched; re-run its installed-artifact smoke before use. Registry publication, multi-host parity, platform adapters, performance comparisons, and full install/upgrade/troubleshooting guidance remain open under #167.
