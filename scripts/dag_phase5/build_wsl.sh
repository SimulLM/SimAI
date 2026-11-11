#!/usr/bin/env bash
# Run from the project root. Publish artifacts into a new evidence directory.
set -euo pipefail

repo=$(pwd -P)
evidence=$(realpath -m "${1:?provide a new evidence directory}")
case "$evidence" in
    "$repo"/.cache/*|"$repo"/results/dag/phase5/*) ;;
    *) echo "evidence must be inside the project cache or phase-5 results" >&2; exit 2 ;;
esac
mkdir -p "$(dirname "$evidence")"
mkdir "$evidence"
build_root=$(mktemp -d /tmp/simai-phase5-XXXXXXXX)
printf '%s\n' "$build_root" > "$evidence/build-root.txt"

git_repo() {
    git -c safe.directory="$repo" -C "$repo" "$@"
}

{
    uname -a
    gcc --version
    cmake --version
    python3 --version
    printf 'build_root=%s\n' "$build_root"
    git_repo rev-parse HEAD
    git_repo diff HEAD --ignore-cr-at-eol --exit-code -- astra-sim-alibabacloud example
    git_repo archive HEAD astra-sim-alibabacloud example | tar -x -C "$build_root"
    for name in SimCCL ns-3-alibabacloud aicb; do
        revision=$(git_repo rev-parse "HEAD:$name")
        printf '%s %s\n' "$name" "$revision"
        mkdir "$build_root/$name"
        git --git-dir="$repo/.git/modules/$name" archive "$revision" | tar -x -C "$build_root/$name"
    done
} > "$evidence/build-inputs.log" 2>&1

analytical="$build_root/analytical"
astra="$build_root/astra-sim-alibabacloud"
ns3="$astra/extern/network_backend/ns3-interface"
mkdir -p "$(dirname "$ns3")"
mv "$build_root/ns-3-alibabacloud" "$ns3"
export SIMAI_NCCL_VERSION=v2.30

(
    set -ex
    cmake -S "$astra/build/simai_analytical" -B "$analytical" -DUSE_ANALYTICAL=TRUE
    cmake --build "$analytical" --parallel 4
    cp "$analytical/simai_analytical/SimAI_analytical" "$evidence/"
) > "$evidence/analytical-build.log" 2>&1 &
analytical_pid=$!

(
    set -ex
    cd "$ns3/simulation"
    cp "$astra"/astra-sim/network_frontend/ns3/{AstraSimNetwork.cc,*.h} scratch/
    cp -r "$astra/astra-sim" src/applications/
    mkdir -p src/applications/SimCCL/mock
    cp -r "$build_root/SimCCL/src/mock/$SIMAI_NCCL_VERSION/." src/applications/SimCCL/mock/
    python3 ns3 configure -d debug --enable-mtp
    python3 ns3 build AstraSimNetwork -j 5
    cp build/scratch/ns3.36.1-AstraSimNetwork-debug "$evidence/SimAI_simulator"
) > "$evidence/ns3-build.log" 2>&1 &
ns3_pid=$!

analytical_status=0
ns3_status=0
wait "$analytical_pid" || analytical_status=$?
wait "$ns3_pid" || ns3_status=$?
printf 'analytical=%s\nns3=%s\n' "$analytical_status" "$ns3_status" > "$evidence/build-status.txt"
if (( analytical_status || ns3_status )); then
    exit 1
fi
(cd "$evidence" && sha256sum SimAI_analytical SimAI_simulator > binaries.sha256)
