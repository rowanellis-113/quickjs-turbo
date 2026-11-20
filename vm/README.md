# ⚡ QuickJS-Turbo (`vm/` Overlay & Build Guide)

## Overview

`vm/` contains the **QuickJS-Turbo** optimizations, native register-frame VMs,
specialized builtins, CMake build rules, tests, and architecture documentation
layered cleanly over unmodified QuickJS-NG `0.15.1`.

See the repository root [README.md](../README.md) for the project overview,
4-engine benchmark comparisons (QuickJS-NG, Bellard QuickJS 2026, QuickJS-Turbo,
V8 `--jitless`), and contributing guidelines.

## Getting started

This checkout keeps upstream QuickJS-NG 0.15.1 untouched at the repository
root and consolidates all interpreter optimizations and build rules under `vm/`.
The product configuration supports native Windows x86-64 with MSVC or MinGW GCC,
native Linux x86-64 with GCC 13+, and a portable C fallback. See [integrated components](docs/architecture/common/OPTIMIZATIONS.txt)
and [Hybrid RC and generational partial cycle GC](docs/architecture/common/HYBRID-GC.txt).
Linux ARM64/glibc also has an explicit AAPCS64 register backend and a common C
fallback. See [ARM64 build and release scope](docs/architecture/arm64/LINUX-AARCH64-RELEASE.txt).
The [ARM64 hardware report](docs/architecture/arm64/LINUX-AARCH64-HARDWARE.txt) records native
execution, compatibility, real hardware scores and retained performance costs.
The [ARM64 return optimization](docs/architecture/arm64/LINUX-AARCH64-NATIVE-RETURN.txt) records the
latest qualified return-path increment and its measured case costs.
The accepted cross-platform configuration and measurement boundaries are recorded
in the [product baseline](docs/architecture/common/PRODUCT-BASELINE.txt).
Use this fork's source checkout or release archive; cloning the upstream URL
alone does not include these optimizations.

With Python 3.10+, CMake 3.20+, Ninja and the compiler tools installed, run from
the repository root in PowerShell:

```powershell
# MSVC: Visual Studio C++ tools, Windows SDK, and GNU x86-64 COFF binutils.
./vm/tools/x86/win64/build/build-baseline.ps1 -Toolchain msvc -Backend WIN64 -Test
./vm/tools/x86/win64/build/run-baseline.ps1 -Toolchain msvc -Arguments @('-e', 'print(1 + 2)')

# Or MinGW GCC with its matching binutils on PATH.
./vm/tools/x86/win64/build/build-baseline.ps1 -Toolchain mingw -Backend WIN64 -Test
./vm/tools/x86/win64/build/run-baseline.ps1 -Toolchain mingw -Arguments @('examples/hello.js')
```

On Linux x86-64 (including native Ubuntu under WSL2), install GCC 13+, GNU
binutils, Python 3.10+, CMake 3.20+ and Ninja, then run:

```sh
bash vm/tools/x86/linux/build/product-linux.sh build/linux-native out/sdk-linux-native
QJS_EXPERIMENT_ALLOCATOR=256 ./out/sdk-linux-native/bin/qjs -e 'print(1 + 2)'
```

The Linux command builds the product configuration, runs local CTest checks and
installs an SDK. Its support boundaries and validation scope are in
[Linux port status](docs/architecture/x86/linux/LINUX-PORT.txt) and [qualification](docs/architecture/x86/linux/LINUX-RELEASE.txt);
measured scores and known costs are in
[current Linux comparison](docs/architecture/x86/linux/LINUX-FINAL-REVIEW.txt). Earlier measurements remain in
[Linux performance](docs/architecture/x86/linux/LINUX-PERFORMANCE.txt). Comparison workloads are optional.

For Linux ARM64, use native GCC on ARM or the documented GNU cross toolchain
and QEMU on x86-64:

```sh
bash vm/tools/arm64/build/product-linux-aarch64.sh build/arm64 out/sdk-arm64
# On a real ARM64 host:
QJS_EXPERIMENT_ALLOCATOR=256 ./out/sdk-arm64/bin/qjs -e 'print(42)'
# On an x86-64 host with the Ubuntu ARM64 sysroot:
QJS_EXPERIMENT_ALLOCATOR=256 qemu-aarch64 -cpu cortex-a53 -L /usr/aarch64-linux-gnu ./out/sdk-arm64/bin/qjs -e 'print(42)'
```

AUTO remains conservative on ARM64. The dedicated wrapper explicitly selects
LINUX_AARCH64 and runs the local tests before installation. For the C fallback,
use `vm/tools/arm64/build/product-linux-aarch64-portable.sh` instead.

The [build guide](docs/architecture/common/BUILDING.txt) covers dependencies, tool paths, portable
builds, tests, installation and embedding. No Node.js, profiler, benchmark corpus
or previous build is needed to compile the engine. Build products stay under
`build/` at the repository root; generated implementation belongs in the build
directory. Product sources are organized under `vm/src/` and `vm/asm/`; see
the [layout](docs/architecture/common/DIRECTORY-LAYOUT.txt).

The [documentation index](docs/architecture/common/README.txt) describes the product components;
the [upstream manual](../docs/docs/intro.md) covers the CLI and public API.
Formatting tools are optional for building; see [formatting](docs/architecture/common/FORMAT.txt).

## Authors

[@bnoordhuis], [@saghul], and many more [contributors].

[ECMAScript]: https://tc39.es/ecma262/
[original QuickJS project]: https://bellard.org/quickjs
[@bnoordhuis]: https://github.com/bnoordhuis
[@saghul]: https://github.com/saghul
[contributors]: https://github.com/quickjs-ng/quickjs/graphs/contributors
[project website]: https://quickjs-ng.github.io/quickjs/
