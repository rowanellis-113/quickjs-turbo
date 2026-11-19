#!/usr/bin/env bash
# ARM64 common optimized PORTABLE, on native hardware or through QEMU.
# This script does not enable or claim an AArch64 register interpreter.
set -euo pipefail
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/../../.." && pwd)
task_repo=$(dirname -- "$task_root")
task_build=$(realpath -m -- "${1:-$task_repo/build/linux-aarch64-portable}")
task_prefix=$(realpath -m -- "${2:-$task_build/install}")
task_args=(-S "$task_root" -B "$task_build" -G Ninja
    -DCMAKE_BUILD_TYPE=Release -DQJS_FRAME_BACKEND=PORTABLE
    -DQJS_FRAME_BUILD_TESTS=ON -DQJS_BUILD_LIBC=ON -DQJS_AARCH64_BUILD_ABI_CHECKS=ON
    -DQJS_BACKPORT_CONTEXT_OOM=ON -DQJS_FRAME_EXPERIMENTAL_ALLOCATOR=ON
    -DQJS_BACKPORT_COMPUTED_ASSIGN=ON -DQJS_BACKPORT_VALUE64_INIT=ON
    -DQJS_BACKPORT_MIXED_NUMBERS=ON -DQJS_BACKPORT_MAP_POINTER_HASH=ON
    -DQJS_PROPERTY_IC=ON -DQJS_BACKPORT_PORTABLE_REGEXP=ON
    -DCMAKE_EXPORT_COMPILE_COMMANDS=ON -DCMAKE_INSTALL_PREFIX="$task_prefix")
if [[ -n ${QJS_TOOLCHAIN_FILE:-} ]]; then
    task_args+=(-DCMAKE_TOOLCHAIN_FILE="$QJS_TOOLCHAIN_FILE")
else
    case $(uname -m) in
        aarch64 | arm64) ;;
        amd64 | *_64)
            command -v qemu-aarch64 > /dev/null
            command -v aarch64-linux-gnu-gcc > /dev/null
            task_args+=(-DCMAKE_TOOLCHAIN_FILE="$task_root/cmake/arm64/toolchains/linux-aarch64-gcc.cmake")
            ;;
        *)
            printf '%s\n' 'Supply QJS_TOOLCHAIN_FILE for this host.' >&2
            exit 2
            ;;
    esac
fi
cmake "${task_args[@]}"
cmake --build "$task_build" --parallel "${QJS_BUILD_JOBS:-1}"
ctest --test-dir "$task_build" --output-on-failure --parallel 1
cmake --install "$task_build"
python3 -B "$task_root/tools/arm64/verify/record-portable.py" \
    --source "$task_root" --build "$task_build" --prefix "$task_prefix"
printf '%s\n' "ARM64 PORTABLE build/tests/install finished: $task_prefix" \
    'PORTABLE uses the common C interpreter; the receipt records native or emulated execution.'
