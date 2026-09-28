# Dedicated job image; no host Docker socket, owner home, or provider data mounts.
FROM ghcr.io/actions/actions-runner@sha256:e5496277be5d09bc968b3d64911b74e219ac4a3f2edce956a3ecf9271bea1ef4
USER root
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-venv git curl jq ca-certificates gh zstd unzip libatomic1 podman \
    && rm -rf /var/lib/apt/lists/*
USER 1000:1000
ENV HOME=/ci/home SWING_CI_ARTIFACTS=/ci/artifacts \
    ACTIONS_RUNNER_PRINT_LOG_TO_STDOUT=0
WORKDIR /home/runner
