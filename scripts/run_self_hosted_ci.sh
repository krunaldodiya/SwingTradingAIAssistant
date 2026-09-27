#!/usr/bin/env bash
# Host-only controller. Never run this inside a CI job or mount its state in one.
set -euo pipefail
umask 077
for tool in docker gh python3 flock; do command -v "$tool" >/dev/null; done
repo=krunaldodiya/SwingTradingAIAssistant
state=${SWING_CI_STATE:-"$HOME/.local/state/swing-ci"}
image=${SWING_CI_RUNNER_IMAGE:?Set the reviewed runner image ID (sha256:...)}
[[ $image =~ ^sha256:[a-f0-9]{64}$ ]] || { echo 'Immutable runner image ID required' >&2; exit 2; }
[[ ! -L $state ]] || { echo 'State must not be a symlink' >&2; exit 2; }
mkdir -p "$state/jobs"
chmod 700 "$state" "$state/jobs"
exec 9>"$state/controller.lock"
flock -n 9 || { echo 'A controller is already running' >&2; exit 2; }
engine_image=docker@sha256:3f3c01aaaebf7cce837356b688b7c059a4749f10bd7660dec7c58fc454a283f0
name=swing-ci-$(cat /proc/sys/kernel/random/uuid)
network=$name-net
volume=$name-work
engine=$name-engine
runner=$name-runner
job_dir=$state/jobs/$name
mkdir "$job_dir"
runner_id=''
cleanup() {
    status=$?
    trap - EXIT
    # Preserve receipts before removing only this job's disposable resources.
    if docker container inspect "$runner" >/dev/null 2>&1; then
        if ! docker cp "$runner:/ci/artifacts" "$job_dir/receipts"; then
            echo 'Receipt copy failed; retaining job containers and volume for recovery' >&2
            exit 1
        fi
        docker logs "$runner" > "$job_dir/runner.log" 2>&1 || true
        docker rm -f "$runner" >/dev/null
    fi
    docker logs "$engine" > "$job_dir/engine.log" 2>&1 || true
    docker rm -fv "$engine" >/dev/null 2>&1 || true
    docker volume rm "$volume" >/dev/null 2>&1 || true
    docker network rm "$network" >/dev/null 2>&1 || true
    rm -f "$job_dir/jit" "$job_dir/registration.json"
    if [[ -n $runner_id ]]; then
        # Ephemeral runners normally unregister themselves after one job.
        gh api --method DELETE "repos/$repo/actions/runners/$runner_id" \
            > /dev/null 2> "$job_dir/unregister.log" || true
    fi
    printf '%s\n' "$status" > "$job_dir/controller-exit"
    exit "$status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

docker network create "$network" >/dev/null
docker volume create "$volume" >/dev/null
docker run --rm --user 0:0 --mount "type=volume,src=$volume,dst=/ci" \
    --entrypoint /bin/bash "$image" -c 'mkdir -p /ci/home /ci/work /ci/artifacts; chown -R 1000:1000 /ci; chmod 700 /ci/home /ci/artifacts'
# Job-scoped nested engine: no host Docker socket or owner directories are mounted.
# DinD needs --privileged for nested containers; it is not a VM security boundary.
docker run -d --name "$engine" --network "$network" --network-alias engine \
    --privileged --memory 4g --cpus 4 -e DOCKER_TLS_CERTDIR= \
    --mount "type=volume,src=$volume,dst=/ci" "$engine_image" >/dev/null
ready=false
for _ in $(seq 1 30); do
    if docker run --rm --network "$network" --entrypoint docker "$image" \
        info --format '{{json .SecurityOptions}}' > "$job_dir/docker-security.json" 2>/dev/null; then
        ready=true
        break
    fi
    sleep 2
done
[[ $ready == true ]] || { echo 'Nested Docker did not become ready' >&2; exit 1; }
# Registration credential stays in a private host file; no gh/PAT config enters the job.
gh api --method POST "repos/$repo/actions/runners/generate-jitconfig" \
    -f "name=$name" -F runner_group_id=1 -f 'labels[]=self-hosted' \
    -f 'labels[]=Linux' -f 'labels[]=X64' -f 'labels[]=swing-ci-linux' \
    -f work_folder=/ci/work > "$job_dir/registration.json"
runner_id=$(python3 -c 'import json,sys; from pathlib import Path; d=json.loads(Path(sys.argv[1]).read_text()); Path(sys.argv[2]).write_text(d["encoded_jit_config"]); print(d["runner"]["id"])' "$job_dir/registration.json" "$job_dir/jit")
rm "$job_dir/registration.json"
printf 'Starting disposable runner %s (id %s)\n' "$name" "$runner_id"
docker run --name "$runner" --init --network "$network" --memory 8g --cpus 4 \
    --mount "type=volume,src=$volume,dst=/ci" \
    --mount "type=bind,src=$job_dir/jit,dst=/run/runner-jit,readonly" \
    --entrypoint /bin/bash "$image" \
    -c 'exec ./run.sh --jitconfig "$(cat /run/runner-jit)"'
