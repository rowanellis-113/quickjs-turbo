Product documentation
=====================

1. Core guides, baselines & formatting
-------------------------------------
BUILDING.txt: configuration, native/portable builds, Test262, installation, and embedding.
DIRECTORY-LAYOUT.txt: owned sources, generators, backends, and test directories under vm/.
FORMAT.txt: pinned formatters (clang-format, Ruff, cmakelang, Prettier, shfmt, PSScriptAnalyzer, Meson) and frozen input rules.
PRODUCT-BASELINE.txt: current v0.17.0-turbo.1 cross-platform baseline, verified scores, heap footprint, and v0.15.1 history.
OPTIMIZATIONS.txt: integrated cross-architecture optimization components, controls, and boundaries.
HYBRID-GC.txt: Hybrid Reference Counting, generational partial cycle GC, synchronous Fast RC, and ablation controls.

2. Shared subsystem notes (`common/subsystems/`)
------------------------------------------------
ARRAY-SORT.txt: default primitive-string MSD radix sorter and bounds.
ASYNC-GENERATORS.txt: async-generator output-Promise capability elision and controls.
COMPILER-PLAN.txt: bounded lexical TDZ planning and private projection.
COROUTINES.txt: persistent coroutine resume segments on MSVC WIN_X86_64.
REGEXP.txt: guarded RegExp flags batching and upgrade checklist.
SYMBOL-CONDITIONS.txt: resolved Symbol condition folding and controls.

3. x86-64 backends (`x86/`)
---------------------------
x86/win64/WIN-X86-64.txt: unified Windows x86-64 native VM (`MSVC` / `clang-cl` / `MinGW`), SEH unwind, `/MT`, and benchmarks.
x86/macos/MACOS-X86-64.txt: macOS x86-64 native Mach-O ASM VM (`MACOS_X86_64`), Mach-O verification, and hardware cohort.
x86/linux/LINUX-PORT.txt: Linux x86-64 native port scope, build command, and six completion gates.
x86/linux/LINUX-RELEASE.txt: Linux x86-64 current qualification, toolchains, and Test262/CTest bindings.
x86/linux/LINUX-FINAL-REVIEW.txt: Linux x86-64 v0.17.0-turbo.1 5-engine benchmark cohort, hotspots, and historical deltas.
x86/linux/LINUX-MECHANISMS.json & LINUX-MECHANISM-COVERAGE.txt: mechanism route inventory and GNU coverage boundaries.
x86/linux/workers/LINUX-*.txt: 29 per-worker Linux x86-64 bring-up and ABI notes.

4. ARM64 backend (`arm64/`)
---------------------------
arm64/LINUX-AARCH64.txt: Linux AArch64 portable C cross/native build and ABI foundation checks.
arm64/LINUX-AARCH64-RELEASE.txt: Linux AArch64 native register VM qualification, QEMU CTest/Test262, and toolchain boundaries.
arm64/LINUX-AARCH64-HARDWARE.txt: AWS Graviton2 (Neoverse-N1) hardware benchmarks (v0.17.0-turbo.1) and historical costs.
arm64/LINUX-AARCH64-MECHANISMS.json: AArch64 GNU mechanism inventory and test mapping.
arm64/workers/LINUX-AARCH64-*.txt: 27 per-worker AArch64 ABI and codegen notes.
