# ⚡ QuickJS-Turbo (`vm/` Overlay & Build Guide)

## Overview

`vm/` contains all **QuickJS-Turbo** optimizations, native register-frame VMs,
zero-spill native CVM coroutine executors, Tier-5 VA constructor compilers,
specialized builtins, ABI contracts, CMake build rules, tests, and architecture
documentation layered cleanly over unmodified QuickJS-NG `0.17.0` (`7b5f588e0f`).

See the repository root [README.md](../README.md) for the project overview,
cross-platform benchmark comparisons (V8-v7, `micro56`/`sort_bench`, and
`JetStream-17` across QuickJS-NG `0.17.0`, Bellard QuickJS `2026-06-04`,
QuickJS-Turbo, and `V8 --jitless` on Linux x86-64, Windows x86-64, macOS x86-64,
and AWS Neoverse-N1 Linux ARM64), ABI & proposed Baseline JIT overview, and
embedding quick start.

## Getting Started

All upstream files outside `vm/` stay untouched at the repository root. The
product configuration (`-S vm`) automatically selects the native register-frame
ASM VM on supported platforms via `-DQJS_FRAME_BACKEND=AUTO`:

- **Linux `x86-64`** (`LINUX_X86_64`, `glibc` & `musl`, GCC 13/14+, native ASM VM + CET-IBT `endbr64` CVM)
- **macOS `x86-64`** (`MACOS_X86_64`, Apple Clang 15+, Mach-O ASM VM + CVM, full DWARF CFI + Clang `indirectbr` spill tuning)
- **Windows `x86-64`** (`WIN_X86_64`, MSVC / `clang-cl` + `ml64` with zero GNU binutils, or MinGW GCC 13+ with native PE TLS)
- **Linux `ARM64`** (`LINUX_AARCH64`, `glibc` & `musl`, GCC 13/14+, `161` native opcodes + zero-spill AArch64 CVM + Tier-5 VA constructors)
- **`PORTABLE` fallback**: auto-selected on macOS ARM64 *(cross-compiled and link-checked on Intel CI; Apple Silicon native runtime validation pending)*, shared builds, Sanitizers, and `FORCE_GC_AT_MALLOC`.

Embedders can link `quickjs-turbo::qjs` (with local host-LTO isolation and
`add_subdirectory()` support), configure density/IC behavior via `quickjs-turbo.h`
(`JS_PurgePropertyIC`), and export Python-free offline assembly bundles with
`QJS_USE_PREGEN_ASM`. See [OPTIMIZATIONS.txt](docs/architecture/common/OPTIMIZATIONS.txt),
[HYBRID-GC.txt](docs/architecture/common/HYBRID-GC.txt), and
[ABI-AND-BASELINE-JIT.txt](docs/architecture/common/ABI-AND-BASELINE-JIT.txt).

### Windows x86-64 (`WIN_X86_64`)

```powershell
cmake -S vm -B build/win-x86_64 -G Ninja -DCMAKE_BUILD_TYPE=Release -DQJS_FRAME_BACKEND=AUTO -DQJS_PROPERTY_IC=ON
cmake --build build/win-x86_64 --parallel

# Static CRT (/MT, zero VC++ redistributable runtime DLLs):
cmake -S vm -B build/win-msvc-mt -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_MSVC_RUNTIME_LIBRARY=MultiThreaded
cmake --build build/win-msvc-mt --parallel
```

See [WIN-X86-64.txt](docs/architecture/x86/win64/WIN-X86-64.txt) for ABI, SEH unwind, `/MT` PE import checks, and benchmarks.

### Linux x86-64 (`LINUX_X86_64`)

```sh
bash vm/tools/x86/linux/build/product-linux.sh build/linux-native out/sdk-linux-native
QJS_EXPERIMENT_ALLOCATOR=512 ./out/sdk-linux-native/bin/qjs -e 'print(1 + 2)'
```

See [LINUX-PORT.txt](docs/architecture/x86/linux/LINUX-PORT.txt), [LINUX-RELEASE.txt](docs/architecture/x86/linux/LINUX-RELEASE.txt), and [LINUX-FINAL-REVIEW.txt](docs/architecture/x86/linux/LINUX-FINAL-REVIEW.txt).

### macOS x86-64 (`MACOS_X86_64`)

```sh
bash vm/tools/x86/macos/build/product-macos.sh build/macos-x86_64 out/sdk-macos-x86_64
```

See [MACOS-X86-64.txt](docs/architecture/x86/macos/MACOS-X86-64.txt).

### Linux ARM64 (`LINUX_AARCH64`)

```sh
bash vm/tools/arm64/build/product-linux-aarch64.sh build/arm64 out/sdk-arm64
# Portable C fallback on ARM64:
bash vm/tools/arm64/build/product-linux-aarch64-portable.sh build/arm64-c out/sdk-arm64-c
```

See [LINUX-AARCH64-RELEASE.txt](docs/architecture/arm64/LINUX-AARCH64-RELEASE.txt) and [LINUX-AARCH64-HARDWARE.txt](docs/architecture/arm64/LINUX-AARCH64-HARDWARE.txt).

## Documentation Index

- [Product Baseline](docs/architecture/common/PRODUCT-BASELINE.txt) · [ABI & Baseline JIT](docs/architecture/common/ABI-AND-BASELINE-JIT.txt) · [Build & Embed Guide](docs/architecture/common/BUILDING.txt) · [Directory Layout](docs/architecture/common/DIRECTORY-LAYOUT.txt)
- [Documentation Index](docs/architecture/common/README.txt) · [Formatting & Contracts](docs/architecture/common/FORMAT.txt) · [Upstream Manual](../docs/docs/intro.md)

## Authors

Built on QuickJS-NG by [@bnoordhuis], [@saghul], and [contributors], and the [original QuickJS project] by Fabrice Bellard and Charlie Gordon.

[original QuickJS project]: https://bellard.org/quickjs
[@bnoordhuis]: https://github.com/bnoordhuis
[@saghul]: https://github.com/saghul
[contributors]: https://github.com/quickjs-ng/quickjs/graphs/contributors
