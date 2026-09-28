#!/usr/bin/env bash
# Host-only controller. Never run this inside a CI job or mount its state in one.
set -euo pipefail
umask 077
for tool in gh python3 flock timeout; do command -v "$tool" >/dev/null; done
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
runtime=$(python3 "$script_dir/container_runtime.py")
runtime_name=${runtime##*/}
userns=()
remove_args=(--force)
job_env=(-e SWING_CONTAINER_RUNTIME="$runtime_name")
if [[ $runtime_name == podman ]]; then
    userns=(--userns=keep-id:uid=1000,gid=1000)
    remove_args+=(--time=0)
    job_env+=(-e CONTAINER_HOST=unix:///ci/podman.sock)
else
    job_env+=(-e DOCKER_HOST=tcp://engine:2375)
fi
repo=krunaldodiya/SwingTradingAIAssistant
state=${SWING_CI_STATE:-"$HOME/.local/state/swing-ci"}
image=${SWING_CI_RUNNER_IMAGE:?Set the reviewed runner image ID (sha256:...)}
[[ $image =~ ^sha256:[a-f0-9]{64}$ ]] || { echo 'Immutable runner image ID required' >&2; exit 2; }
[[ ! -L $state ]] || { echo 'State must not be a symlink' >&2; exit 2; }
mkdir -p "$state/jobs"
chmod 700 "$state" "$state/jobs"
exec 9>"$state/controller.lock"
flock -n 9 || { echo 'A controller is already running' >&2; exit 2; }
engine_image=docker.io/library/docker@sha256:3f3c01aaaebf7cce837356b688b7c059a4749f10bd7660dec7c58fc454a283f0
if [[ $runtime_name == podman ]]; then
    engine_image=quay.io/podman/stable@sha256:3f78736de8afc424df48270f8e86194887c5cf8b23dc10b420da90457b7d37e6
fi
name=swing-ci-$(cat /proc/sys/kernel/random/uuid)
network=$name-net
volume=$name-work
engine=$name-engine
runner=$name-runner
job_dir=$state/jobs/$name
mkdir "$job_dir"
timeout --kill-after=2s 10s "$runtime" version --format '{{json .}}' > "$job_dir/runtime-version.json"
python3 -c 'import json,sys; from pathlib import Path; Path(sys.argv[1]).write_text(json.dumps({"runtime":sys.argv[2],"executable":sys.argv[3],"version":json.loads(Path(sys.argv[4]).read_text())})+"\n")' "$job_dir/runtime.json" "$runtime_name" "$runtime" "$job_dir/runtime-version.json"
runner_id=''
runner_attempted=false
cleanup_failed() {
    if [[ $status == 0 ]]; then status=1; fi
}
cleanup() {
    status=$?
    trap - EXIT
    trap '' INT TERM
    # Every external cleanup call is bounded; worst-case total stays below 90s.
    # Erase registration even when evidence must be retained or teardown fails.
    rm -f "$job_dir/jit" "$job_dir/registration.json" || status=1
    if [[ -n $runner_id ]]; then
        timeout --kill-after=2s 5s gh api --method DELETE "repos/$repo/actions/runners/$runner_id" \
            > /dev/null 2> "$job_dir/unregister.log" || true
    fi
    if [[ $runner_attempted == true ]]; then
        if ! runner_names=$(timeout --kill-after=2s 5s "$runtime" ps --all --filter "name=$runner" --format '{{.Names}}'); then
            echo 'Runner state unavailable; retaining job resources for recovery' >&2
            printf '1\n' > "$job_dir/controller-exit"
            exit 1
        fi
        if [[ -z $runner_names ]]; then
            runner_attempted=false
            cleanup_failed
        elif [[ $runner_names != "$runner" ]]; then
            echo 'Runner state ambiguous; retaining job resources for recovery' >&2
            printf '1\n' > "$job_dir/controller-exit"
            exit 1
        fi
    fi
    if [[ $runner_attempted == true ]]; then
        if ! timeout --kill-after=2s 20s "$runtime" cp "$runner:/ci/artifacts" "$job_dir/receipts"; then
            echo 'Receipt copy failed; retaining job containers and volume for recovery' >&2
            printf '1\n' > "$job_dir/controller-exit"
            exit 1
        fi
        timeout --kill-after=2s 3s "$runtime" logs "$runner" > "$job_dir/runner.log" 2>&1 || true
        timeout --kill-after=2s 10s "$runtime" rm "${remove_args[@]}" "$runner" >/dev/null || cleanup_failed
    fi
    timeout --kill-after=2s 3s "$runtime" logs "$engine" > "$job_dir/engine.log" 2>&1 || true
    timeout --kill-after=2s 10s "$runtime" rm -v "${remove_args[@]}" "$engine" >/dev/null 2>&1 || cleanup_failed
    timeout --kill-after=2s 5s "$runtime" volume rm "$volume" >/dev/null 2>&1 || cleanup_failed
    timeout --kill-after=2s 5s "$runtime" network rm "$network" >/dev/null 2>&1 || cleanup_failed
    printf '%s\n' "$status" > "$job_dir/controller-exit"
    exit "$status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

"$runtime" network create "$network" >/dev/null
"$runtime" volume create "$volume" >/dev/null
"$runtime" run --rm "${userns[@]}" --user 0:0 --mount "type=volume,src=$volume,dst=/ci" \
    --entrypoint /bin/bash "$image" -c 'mkdir -p /ci/home /ci/work /ci/artifacts; chown -R 1000:1000 /ci; chmod 700 /ci/home /ci/artifacts'
# Each job has its own nested engine; neither backend mounts the host socket.
if [[ $runtime_name == podman ]]; then
    "$runtime" run -d --name "$engine" "${userns[@]}" --user 0:0 \
        --network "$network" --privileged --memory 4g --cpus 4 \
        --mount "type=volume,src=$volume,dst=/ci" --entrypoint /bin/sh "$engine_image" -c '
        umask 007
        podman --storage-driver=vfs --cgroup-manager=cgroupfs --events-backend=file \
            system service --time=0 unix:///ci/podman.sock & pid=$!
        for i in $(seq 1 50); do
            if [ -S /ci/podman.sock ]; then
                chgrp 1000 /ci/podman.sock; chmod 660 /ci/podman.sock
                wait "$pid"; exit $?
            fi
            sleep .1
        done
        kill "$pid"; exit 1' >/dev/null
else
    "$runtime" run -d --name "$engine" --network "$network" --network-alias engine \
        --privileged --memory 4g --cpus 4 -e DOCKER_TLS_CERTDIR= \
        --mount "type=volume,src=$volume,dst=/ci" "$engine_image" >/dev/null
fi
ready=false
for _ in $(seq 1 30); do
    if "$runtime" run --rm "${userns[@]}" --user 1000:1000 --network "$network" \
        "${job_env[@]}" --mount "type=volume,src=$volume,dst=/ci" \
        --entrypoint "$runtime_name" "$image" info --format '{{json .}}' \
        > "$job_dir/engine-info.json" 2>/dev/null; then
        ready=true
        break
    fi
    sleep 2
done
[[ $ready == true ]] || { echo 'Nested container engine did not become ready' >&2; exit 1; }
# Registration credential stays in a private host file; no gh/PAT config enters the job.
gh api --method POST "repos/$repo/actions/runners/generate-jitconfig" \
    -f "name=$name" -F runner_group_id=1 -f 'labels[]=self-hosted' \
    -f 'labels[]=Linux' -f 'labels[]=X64' -f 'labels[]=swing-ci-linux' \
    -f work_folder=/ci/work > "$job_dir/registration.json"
runner_id=$(python3 -c 'import json,sys; from pathlib import Path; d=json.loads(Path(sys.argv[1]).read_text()); Path(sys.argv[2]).write_text(d["encoded_jit_config"]); print(d["runner"]["id"])' "$job_dir/registration.json" "$job_dir/jit")
rm "$job_dir/registration.json"
printf 'Starting disposable runner %s (id %s)\n' "$name" "$runner_id"
runner_attempted=true
"$runtime" run --name "$runner" "${userns[@]}" --user 1000:1000 "${job_env[@]}" --init --network "$network" --memory 8g --cpus 4 \
    --mount "type=volume,src=$volume,dst=/ci" \
    --mount "type=bind,src=$job_dir/jit,dst=/run/runner-jit,readonly" \
    --entrypoint /bin/bash "$image" \
    -c 'exec ./run.sh --jitconfig "$(cat /run/runner-jit)"'
