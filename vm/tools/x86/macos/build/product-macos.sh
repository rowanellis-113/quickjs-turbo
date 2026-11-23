#!/usr/bin/env bash
# Build the macOS x86-64 native backend using ordinary CMake and Ninja.
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/../../../.." && pwd)
task_repo=$(dirname -- "$task_root")
task_build=${1:-"$task_repo/build/macos-x86_64-native"}
task_prefix=${2:-"$task_build/install"}
task_build=$(python3 -c 'import os,sys; print(os.path.abspath(sys.argv[1]))' "$task_build")
task_prefix=$(python3 -c 'import os,sys; print(os.path.abspath(sys.argv[1]))' "$task_prefix")
cmake -S "$task_root" -B "$task_build" -G Ninja \
    -DCMAKE_BUILD_TYPE=Release -DQJS_FRAME_BACKEND=MACOS_X86_64 \
    -DQJS_FRAME_BUILD_TESTS=ON -DQJS_BACKPORT_CONTEXT_OOM=ON \
    -DQJS_FRAME_EXPERIMENTAL_COMPARE=ON \
    -DQJS_BACKPORT_COMPUTED_ASSIGN=ON -DQJS_BACKPORT_VALUE64_INIT=ON \
    -DQJS_BACKPORT_MIXED_NUMBERS=ON -DQJS_BACKPORT_MAP_POINTER_HASH=ON \
    -DQJS_PROPERTY_IC=ON -DQJS_BACKPORT_PORTABLE_REGEXP=ON \
    -DCMAKE_INSTALL_PREFIX="$task_prefix"
cmake --build "$task_build" --parallel "${QJS_BUILD_JOBS:-1}"
ctest --test-dir "$task_build" --output-on-failure --parallel "${QJS_BUILD_JOBS:-1}"
cmake --install "$task_build"
printf '%s\n' "macOS x86-64 native build/tests/install finished: $task_prefix"
