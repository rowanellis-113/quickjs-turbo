# ⚡ QuickJS-Turbo

**QuickJS-Turbo (`quickjs-turbo`)** is a high-performance, zero-JIT JavaScript engine built on top of [QuickJS-NG](https://github.com/quickjs-ng/quickjs) `0.15.1` (`bf8988fc401e737f9946cd10a3463b48aab0fd7e`).

It keeps upstream QuickJS-NG untouched at the repository root and concentrates native register-frame VMs, adaptive inline caches, specialized native builtins, and build contracts under [`vm/`](vm/) — delivering **~1.95× V8-v7** and **~1.67× JetStream-17** throughput over stock QuickJS-NG `0.15.1` on Linux x86-64 (**~1.33× / 1.25×** over Bellard QuickJS `2026`), reaching **~82% of V8 `--jitless`** performance without runtime code generation or `W^X` violations.

---

## Project Purpose & Design Goals

- **Interpreter-class speed near V8 `--jitless` — without a JIT**: Designed for environments where JIT compilation or writable-executable (`RWX`) memory is prohibited, impractical, or too heavy (iOS, consoles, sandboxed plugins, edge/serverless workers, CLI tools, embedded devices), while preserving fast cold startup and a compact static footprint.
- **100% Drop-In QuickJS-NG API & Semantic Compatibility**: Preserves the upstream `quickjs.h` public C ABI, bytecode compatibility boundaries, strict ECMAScript compliance (fixing `31` upstream Test262 failures with `0` regressions), and an automatic `PORTABLE` C fallback on unsupported hosts or sanitizer/shared builds.
- **Strict Security & Unwind Guarantees**: Enforces `W^X` (no writable+executable sections, non-executable stack), PIE/PIC, full DWARF CFI on Linux ELF64 (`x86_64` and `aarch64`), and complete `.pdata`/`.xdata` SEH unwind data on Windows (`MSVC` and `MinGW`).
- **Zero-Conflict Upstream Sync (`vm/` Overlay)**: Every optimization, assembly VM, codegen tool, CMake rule, and test suite is isolated inside [`vm/`](vm/). Upstream QuickJS-NG stays byte-for-byte pristine (enforced by automated 19-file SHA-256 pins and Git boundary checks), enabling frictionless upstream updates and side-by-side stock vs. Turbo builds from one tree.

---

## Performance Benchmarks

All cross-engine comparisons below were measured under controlled serial, single-core execution (pinned CPU affinity, interleaved forward/reverse ABBA blocks, normal OS ASLR, no PGO/layout tuning). QuickJS-Turbo runs with its product allocator setting `QJS_EXPERIMENT_ALLOCATOR=256`.

> **Measurement Scope**: JetStream-17 and JetStream-9 are fixed CLI subsets (not official browser JetStream 2 total scores). Individual microbenchmarks and real workloads still vary — full per-case measurements and retained regressions are published transparently under [`vm/docs/architecture/`](vm/docs/architecture/).

### 1. Linux x86-64 (4-Engine Same-Cohort Comparison)

Measured on Ubuntu 24.04 (WSL2, native ELF64, GCC 13.3, CPU 2 serial, `2` reversed ABBA blocks; source: [`PRODUCT-BASELINE.txt`](vm/docs/architecture/common/PRODUCT-BASELINE.txt)):

| Engine | V8-v7 Score (8 cases, ↑ higher is faster) | vs Stock NG | JetStream-17 Elapsed Index (↓ lower is faster) | JetStream-17 Throughput (↑) |
| --- | ---: | ---: | ---: | ---: |
| **QuickJS-NG `0.15.1`** *(Stock / Original)* | `993.7` | `1.00×` | `100.0` | `1.00×` |
| **Bellard QuickJS `2026`** *(`2026-06-04`, `-O2`)* | `1,465.7` | `1.47×` | `74.8` | `1.34×` |
| **QuickJS-Turbo** *(`LINUX_X86_64`)* | **`1,942.7`** | **`1.95×`** | **`59.9`** | **`1.67×`** |
| **V8 `--jitless`** *(Node.js `24.13.0` / Ignition)* | `2,374.9` | `2.39×` | `46.2` | `2.16×` |

- **vs Stock QuickJS-NG `0.15.1`**: **`1.95×`** on V8-v7 (`1,942.7` vs `993.7`) and **`1.67×`** throughput on JetStream-17.
- **vs Bellard QuickJS `2026`**: **`1.33×`** on V8-v7 (`1,942.7` vs `1,465.7`) and **`1.25×`** throughput on JetStream-17.
- **vs V8 `--jitless`**: Achieves **`81.8%`** of V8 `--jitless` score on V8-v7 (`1,942.7` vs `2,374.9`) and **`77.1%`** on JetStream-17 without bytecode JIT tiers or V8 runtime overhead.

#### Highlighted Linux x86-64 Case Speedups vs Stock QuickJS-NG `0.15.1`

From the paired ELF64 archive screen ([`LINUX-FINAL-REVIEW.txt`](vm/docs/architecture/x86/linux/LINUX-FINAL-REVIEW.txt)):

- **V8-v7 Suite**: `RegExp` `256.5 → 1,716.3` (**`6.69×`**), `NavierStokes` `1,161.0 → 2,600.2` (**`2.24×`**), `Richards` `763.2 → 1,428.3` (**`1.87×`**), `Crypto` `843.6 → 1,543.3` (**`1.83×`**), `DeltaBlue` `853.3 → 1,325.0` (**`1.55×`**), `EarleyBoyer` `1,714.5 → 2,618.3` (**`1.53×`**).
- **JetStream-17 Applications**: `json-stringify-inspector` `140.6 ms → 23.4 ms` (**`6.02×`**), `json-parse-inspector` `131.1 ms → 39.0 ms` (**`3.36×`**), `cdjs` `559.9 ms → 287.1 ms` (**`1.95×`**), `crypto` `145.1 ms → 78.5 ms` (**`1.85×`**), `pdfjs` `312.7 ms → 164.8 ms` (**`1.90×`**).
- **Microbenchmarks (57 cases, `-30.88%` geomean elapsed)**: `typed_array_write` `31.7 ns → 5.5 ns` (**`5.78×`**), `array_write` `26.4 ns → 4.6 ns` (**`5.74×`**), `prop_read` `15.9 ns → 5.6 ns` (**`2.84×`**), `string_to_float` `165.8 ns → 78.6 ns` (**`2.11×`**), `func_call` `27.6 ns → 15.5 ns` (**`1.78×`**).

---

### 2. Windows x86-64 (`WIN64` MSVC & MinGW Comparison)

Measured on Windows x86-64 (CPU 2 / affinity mask 4, serial forward/reverse ABBA blocks, normal ASLR), throughput normalized to **Bellard QuickJS `2026-06-04` = `1.00×`** (↑ higher is faster):

| Benchmark Suite | Bellard QuickJS `2026` | QuickJS-Turbo (`WIN64` MSVC) | QuickJS-Turbo (`WIN64` MinGW) | V8 `--jitless` *(Node `24.13.0`)* |
| --- | ---: | ---: | ---: | ---: |
| **V8-v7 (8 cases)** | `1.00×` | **`1.40×`** | **`1.61×`** | `2.00×` |
| **JetStream (9-app cohort)** | `1.00×` | **`1.38×`** | **`1.46×`** | `2.00×` |
| **QuickJS Microbench (57 cases)** | `1.00×` | **`1.33×`** | **`1.46×`** | `1.89×` |

In paired V8-v7 screens against **Stock QuickJS-NG `0.15.1`**, `WIN64` MinGW scores **`1,917.8`–`1,935.4`** vs **`985.7`–`997.3`** (**`~1.94×`**, [`LINUX-FINAL-REVIEW.txt`](vm/docs/architecture/x86/linux/LINUX-FINAL-REVIEW.txt)).

---

### 3. Linux ARM64 (`LINUX_AARCH64` on AWS Graviton2 / Neoverse-N1)

Measured on physical AWS Graviton2 (`Neoverse-N1`, Linux/glibc, GCC 13, `QJS_EXPERIMENT_ALLOCATOR=256`, CPU 1 serial ABBA blocks, `ASLR=2`), geometric mean throughput over **Bellard QuickJS `2026` (`1.00×`)**:

| Benchmark Suite | Bellard QuickJS `2026` | QuickJS-Turbo (`LINUX_AARCH64`) |
| --- | ---: | ---: |
| **V8-v7 (8 cases)** | `1.00×` | **`1.50×`** *(blocks: `1.49×`–`1.50×`)* |
| **JetStream-17 (17 apps)** | `1.00×` | **`1.26×`** *(blocks: `1.26×`–`1.28×`)* |
| **QuickJS Microbench (57 cases, elapsed)** | `1.00×` | **`1.25×`** *(blocks: `1.25×`–`1.29×`)* |

*(See [`LINUX-AARCH64-HARDWARE.txt`](vm/docs/architecture/arm64/LINUX-AARCH64-HARDWARE.txt) and [`LINUX-AARCH64-NATIVE-RETURN.txt`](vm/docs/architecture/arm64/LINUX-AARCH64-NATIVE-RETURN.txt) for earlier physical-hardware reports and per-case breakdowns.)*

---

### 4. Correctness & Compatibility

- **Test262**: Across all verified `81,152`-case runs (Windows MSVC/MinGW/Portable & Linux x86-64/ARM64), QuickJS-Turbo introduces **`0` new failures** and **fixes `31` upstream QuickJS-NG `0.15.1` failures** (`65` inherited failures vs `96` in stock QuickJS-NG `0.15.1`).
- **CTest & Contract Suites**: Passes platform native/instrumented/portable CTest suites alongside automated CMake, ABI layout, ELF/COFF unwind, source SHA-256 receipt, and architecture boundary tests.

---

## Architecture Highlights

1. **Native Register-Frame Virtual Machines (`vm/asm/`, `vm/tools/`)**:
   - **x86-64 Linux (SysV ELF)**, **x86-64 Windows (Win64 PE/COFF, MSVC & MinGW)**, and **ARM64 Linux (AAPCS64)**: dedicated assembly dispatch loops and physical register frame activations eliminate redundant stack shuffling across hot opcodes, calls, returns, tail calls, and forwarding while maintaining full C interoperability and exact unwind tables.
2. **Adaptive Inline Caches & Object Model (`vm/src/common/property/`)**:
   - Polymorphic property inline caches (`PropertyIC`), method caches, inline object property storage, shape/prototype epoch guards, and direct field fast paths.
3. **Specialized Runtime Subsystems (`vm/src/common/`)**:
   - **RegExp & Unicode**: Specialized bytecode RegExp executor, case-fold tables, literal/flag caches, and wire compatibility ([`REGEXP.txt`](vm/docs/architecture/common/REGEXP.txt)).
   - **JSON & Strings**: Fast JSON parser/serializer capsules and zero-copy rope concatenation.
   - **Arrays, Sort, Calls & BigInt**: Dense array & TypedArray fast paths, `OP_array_from` / `for_of_next` fast workers, optimized default `Array.prototype.sort`, empty-args `apply` frame reuse, `instanceof` epoch leaf, and BigInt division/modulo fast paths.
   - **Compiler & Allocator**: Lexical compiler TDZ/slot planning ([`COMPILER-PLAN.txt`](vm/docs/architecture/common/COMPILER-PLAN.txt)), resolved symbol condition guards, and opt-in pooled small-object allocation (`QJS_EXPERIMENT_ALLOCATOR=256`).

---

## Repository Layout (`Zero-Conflict vm/ Overlay`)

```text
quickjs-turbo/
├── CMakeLists.txt, quickjs.c, quickjs.h, ...   # Untouched QuickJS-NG 0.15.1 upstream core
├── tests/, examples/, docs/, gen/              # Untouched upstream tests, examples, docs & gen snapshots
├── .github/workflows/                          # QuickJS-Turbo CI, Test262 & SDK release pipelines
└── vm/                                         # All QuickJS-Turbo modifications & build/CI/test assets
    ├── CMakeLists.txt                          # Product CMake entry (-S vm)
    ├── VERSION                                 # QuickJS-Turbo release version (v<upstream>-turbo.<N>)
    ├── src/{common,arm64,x86}/                 # C fast paths, ABI manifests & extracted workers
    ├── asm/{arm64,x86}/                        # Native assembly VM & bridge templates
    ├── cmake/{common,arm64,x86}/               # Backend policies, ABI probes, epochs & test registration
    ├── tools/{common,arm64,x86}/               # Codegen, ELF/COFF adapters, formatters & build wrappers
    ├── tests/{common,arm64,x86}/               # Native, C/API, JS semantics, ABI & DAG boundary tests
    ├── docs/architecture/{common,arm64,x86}/   # Architecture contracts, build guide & benchmark records
    └── ci/                                     # CI version, PE import & Test262 verification helpers
```

---

## Quick Start & Building

**Prerequisites**: Python `3.10+`, CMake `3.20+`, Ninja, and a supported C11 toolchain (MSVC / MinGW GCC on Windows; GCC `13+` & GNU binutils on Linux x86-64 / ARM64). No Node.js, profiler, or prior engine build is required.

### Windows x86-64 (`MSVC` & `MinGW`)

Run from the repository root in PowerShell:

```powershell
# MSVC dynamic CRT (/MD) (Visual Studio C++ tools, Windows SDK, plus GNU x86-64 COFF as/objdump)
./vm/tools/x86/win64/build/build-baseline.ps1 -Toolchain msvc -Backend WIN64 -Test
./vm/tools/x86/win64/build/run-baseline.ps1 -Toolchain msvc -Arguments @('-e', 'print(1 + 2)')

# MSVC static CRT (/MT) with compile-time default allocator for scrubbed-env hosts
./vm/tools/x86/win64/build/build-baseline.ps1 -Toolchain msvc -MsvcRuntime MT -DefaultExperimentAllocator 256 -Backend WIN64 -Test

# MinGW-w64 GCC (GCC 13+ & matching binutils on PATH)
./vm/tools/x86/win64/build/build-baseline.ps1 -Toolchain mingw -Backend WIN64 -Test
./vm/tools/x86/win64/build/run-baseline.ps1 -Toolchain mingw -Arguments @('examples/hello.js')
```

### Linux x86-64 (`GCC 13+`)

```sh
bash vm/tools/x86/linux/build/product-linux.sh build/linux-native out/sdk-linux-native
QJS_EXPERIMENT_ALLOCATOR=256 ./out/sdk-linux-native/bin/qjs -e 'print(1 + 2)'
```

### Linux ARM64 (`GCC 13+`, Native or Cross + QEMU)

```sh
bash vm/tools/arm64/build/product-linux-aarch64.sh build/arm64 out/sdk-arm64

# On a real ARM64 host:
QJS_EXPERIMENT_ALLOCATOR=256 ./out/sdk-arm64/bin/qjs -e 'print(42)'

# Or via QEMU on an x86-64 host:
QJS_EXPERIMENT_ALLOCATOR=256 qemu-aarch64 -cpu cortex-a53 -L /usr/aarch64-linux-gnu ./out/sdk-arm64/bin/qjs -e 'print(42)'
```

For the portable C fallback on ARM64, use `bash vm/tools/arm64/build/product-linux-aarch64-portable.sh`.

### Portable C Build & Stock Side-by-Side Comparison

```sh
# QuickJS-Turbo portable C build (Linux / macOS / Windows)
cmake -S vm -B build/turbo-portable -G Ninja -DCMAKE_BUILD_TYPE=Release -DQJS_FRAME_BACKEND=PORTABLE -DQJS_FRAME_BUILD_TESTS=ON
cmake --build build/turbo-portable --parallel
ctest --test-dir build/turbo-portable --output-on-failure

# Pristine Stock QuickJS-NG 0.15.1 from the exact same checkout (direct A/B reference)
cmake -S . -B build/stock-ng -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build build/stock-ng --parallel
```

### Embedding via Installed CMake SDK

```sh
cmake --install build/linux-native --prefix out/sdk
cmake -S vm/tests/common/consumer -B build/consumer -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_PREFIX_PATH="$PWD/out/sdk"
cmake --build build/consumer && ctest --test-dir build/consumer --output-on-failure
```

Consumer targets link cleanly via CMake (`find_package(qjs CONFIG REQUIRED)`, `target_link_libraries(your_app PRIVATE qjs)` or `qjs::qjs`). For static-CRT C/C++11 hosts or sandboxed workers that clear environment variables, configure with `-DCMAKE_MSVC_RUNTIME_LIBRARY=MultiThreaded`, `-DQJS_DEFAULT_EXPERIMENT_ALLOCATOR=256`, and optionally `-DQJS_BUILD_CLI=OFF` for a library-only build. Otherwise, set `QJS_EXPERIMENT_ALLOCATOR=256` before runtime creation when using the pooled allocator. See [`BUILDING.txt`](vm/docs/architecture/common/BUILDING.txt) for full options and cross-compilation details.

### Versioning & Releases

- **Version Scheme (`v<upstream>-turbo.<N>`)**: [`vm/VERSION`](vm/VERSION) tracks the product release version starting at `0.15.1-turbo.1` (tag `v0.15.1-turbo.1`), where `<upstream>` must match `QJS_UPSTREAM_VERSION` in [`QuickJSUpstreamPin.cmake`](vm/cmake/QuickJSUpstreamPin.cmake) and `<N>` increments independently for each QuickJS-Turbo release (`-alpha.<K>`, `-beta.<K>`, or `-rc.<K>` optional for prereleases).
- **Automated Test262 & CI Gates**: Every push/PR to `main` runs both [`ci.yml`](.github/workflows/ci.yml) (formatting, receipts, contracts, native/portable/sanitizer builds) and [`test262.yml`](.github/workflows/test262.yml) across Linux `x86-64`, Linux `ARM64`, `PORTABLE`, Windows `MSVC`, and Windows `MinGW`.
- **Publishing a Release**: [`release.yml`](.github/workflows/release.yml) builds versioned SDK archives with embedded `quickjs-turbo-version.json` and `SHA256SUMS.txt` either when pushing a validated tag (`git tag -a v0.15.1-turbo.1 -m "..." && git push origin v0.15.1-turbo.1`) or via manual GitHub Actions `workflow_dispatch` on `main` with `publish_release=true`.

---

## Contributing

Contributions — from fast-path optimizations, architecture ports, and bug fixes to benchmark methodology improvements and upstream sync updates — are very welcome. Please follow these engineering and verification contracts before opening a PR:

1. **Respect the `vm/` Overlay & One-Way Architecture DAG**:
   - Keep all modifications inside [`vm/`](vm/). Upstream files outside `vm/` (aside from `README.md` and `.github/`) must remain byte-for-byte identical to pinned QuickJS-NG `bf8988fc401e737f9946cd10a3463b48aab0fd7e`.
   - Maintain the strict dependency hierarchy `common/ → {arm64/, x86/}` across `src/`, `asm/`, `tools/`, `cmake/`, and `tests/`. Verify with:
     ```sh
     python -B vm/tests/common/test_arch_boundaries.py
     ```
2. **Validate Build, Layout & ABI Contracts**:
   - Both native backends and the `PORTABLE` C fallback must compile cleanly with zero warnings treated lightly, preserve full unwind/CFI (`ELF64` & `Win64`), and pass layout/ABI checks:
     ```sh
     python -B vm/tests/common/validate_layout.py --require-native
     python -B vm/tests/common/test_property_ic_generator.py
     python -B vm/tests/x86/common/test_vm_abi.py
     python -B vm/tests/x86/win64/test_vm_build.py --cmake cmake
     ```
3. **Follow Rigorous Performance Measurement Standards**:
   - See [`vm/AGENTS.md`](vm/AGENTS.md) for the full measurement protocol: pin a single CPU core, run serial paired forward/reverse (`ABBA`) blocks under normal ASLR without PGO, price gains and regressions against **both** current QuickJS-Turbo and stock QuickJS-NG `0.15.1`, and report negative/neutral results candidly without cherry-picking runs.
4. **Formatting & Signed Source Receipts**:
   - Install formatter dependencies per [`FORMAT.txt`](vm/docs/architecture/common/FORMAT.txt) and ensure all checks pass before submitting:
     ```sh
     npm --prefix vm run format:check
     python -B vm/tests/common/test_format_contract.py
     ```
   - Never bypass frozen manifests (`native-frozen.json`, `js-frozen.json`) or refresh compiled symbol fingerprints merely to force an unreviewed compiler profile through CI.

---

## Documentation Index

- **Turbo Build & Component Index**: [`vm/README.md`](vm/README.md) · [`vm/docs/architecture/common/README.txt`](vm/docs/architecture/common/README.txt)
- **Detailed Build & Cross-Compile Guide**: [`vm/docs/architecture/common/BUILDING.txt`](vm/docs/architecture/common/BUILDING.txt)
- **Integrated Optimizations**: [`vm/docs/architecture/common/OPTIMIZATIONS.txt`](vm/docs/architecture/common/OPTIMIZATIONS.txt)
- **Engineering & Benchmarking Policy**: [`vm/AGENTS.md`](vm/AGENTS.md)
- **Formatting & Contracts**: [`vm/docs/architecture/common/FORMAT.txt`](vm/docs/architecture/common/FORMAT.txt)
- **Upstream QuickJS Manual & Public C API**: [`docs/docs/intro.md`](docs/docs/intro.md)

---

## License & Acknowledgements

QuickJS-Turbo is licensed under the **MIT License** — see [`LICENSE`](LICENSE) and [`vm/THIRD_PARTY_NOTICES.txt`](vm/THIRD_PARTY_NOTICES.txt).

Built with deep appreciation for:
- **Fabrice Bellard** and **Charlie Gordon** — creators of the original QuickJS engine.
- **Saúl Ibarra Corretgé (`@saghul`)**, **Ben Noordhuis (`@bnoordhuis`)**, and the **QuickJS-NG contributors** — maintainers of the upstream QuickJS-NG project on which QuickJS-Turbo is based.
