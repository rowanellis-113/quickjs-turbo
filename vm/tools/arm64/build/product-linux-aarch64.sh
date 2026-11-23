#!/usr/bin/env bash
# Linux/glibc AAPCS64 product build;ordinary CMake source generation. MIT.
set -euo pipefail
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/../../.." && pwd)
task_repo=$(dirname -- "$task_root")
task_build=$(realpath -m -- "${1:-$task_repo/build/linux-aarch64-native}")
task_prefix=$(realpath -m -- "${2:-$task_build/install}")
task_args=(-S "$task_root" -B "$task_build" -G Ninja
    -DCMAKE_BUILD_TYPE=Release -DQJS_FRAME_BACKEND=LINUX_AARCH64
    -DQJS_FRAME_BUILD_TESTS=ON -DQJS_BUILD_LIBC=ON
    -DQJS_BACKPORT_CONTEXT_OOM=ON
    -DQJS_BACKPORT_COMPUTED_ASSIGN=ON -DQJS_BACKPORT_VALUE64_INIT=ON
    -DQJS_BACKPORT_MIXED_NUMBERS=ON -DQJS_BACKPORT_MAP_POINTER_HASH=ON
    -DQJS_PROPERTY_IC=ON -DQJS_BACKPORT_PORTABLE_REGEXP=ON
    -DQJS_AARCH64_VM_INSTRUMENT=OFF -DCMAKE_INSTALL_PREFIX="$task_prefix")
if [[ -n ${QJS_TOOLCHAIN_FILE:-} ]]; then
    task_args+=(-DCMAKE_TOOLCHAIN_FILE="$QJS_TOOLCHAIN_FILE")
else
    case $(uname -m) in
        aarch64 | arm64) ;;
        amd64 | *_64) task_args+=(-DCMAKE_TOOLCHAIN_FILE="$task_root/cmake/arm64/toolchains/linux-aarch64-gcc.cmake") ;;
        *)
            printf '%s\n' 'Supply QJS_TOOLCHAIN_FILE for this host,or use the portable CMake backend.' >&2
            exit 2
            ;;
    esac
fi
cmake "${task_args[@]}"
cmake --build "$task_build" --parallel "${QJS_BUILD_JOBS:-1}"
ctest --test-dir "$task_build" --output-on-failure --parallel 1
cmake --install "$task_build"
printf '%s\n' "Linux AArch64 build/tests/install finished: $task_prefix" \
    'Functional qualification and hardware-performance boundaries: docs/architecture/arm64/LINUX-AARCH64-RELEASE.txt.'
