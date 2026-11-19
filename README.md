# ⚡ QuickJS-Turbo

[![CI](https://github.com/rowanellis-113/quickjs-turbo/actions/workflows/ci.yml/badge.svg)](https://github.com/rowanellis-113/quickjs-turbo/actions/workflows/ci.yml)
[![Test262](https://github.com/rowanellis-113/quickjs-turbo/actions/workflows/test262.yml/badge.svg)](https://github.com/rowanellis-113/quickjs-turbo/actions/workflows/test262.yml)
[![Release](https://img.shields.io/github/v/release/rowanellis-113/quickjs-turbo?include_prereleases&label=release)](https://github.com/rowanellis-113/quickjs-turbo/releases)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

**QuickJS-Turbo** is a high-performance, zero-JIT JavaScript engine built as a non-intrusive overlay on [QuickJS-NG](https://github.com/quickjs-ng/quickjs) `0.15.1` (`bf8988fc401e737f9946cd10a3463b48aab0fd7e`).

It delivers **~1.95× V8-v7** and **~1.67× JetStream** speedups over stock QuickJS-NG `0.15.1` (**~1.33× / 1.25×** over Bellard QuickJS `2026`), reaching **~82% of V8 `--jitless`** throughput — while preserving a compact static binary, strict `W^X` memory safety (zero `RWX` JIT pages), and 100% `quickjs.h` C API compatibility.

> [!TIP]
> **Looking to run untrusted or AI-generated JavaScript in production?**
> **QuickJS-Turbo** is the embeddable C engine (`quickjs.h`). If you want a complete **Host-controlled sandboxed runtime** — with OS process isolation, capability/egress policies, resource & deadline enforcement, HTTP `fetch(request)`, and WebSockets — check out **[Capsid](https://github.com/rowanellis-113/capsid)** ([Documentation](https://rowanellis-113.github.io/capsid/)).

---

## Why QuickJS-Turbo?

- **Fast Where JITs Are Disallowed or Too Heavy**: Native register-frame VMs for **Linux x86-64**, **Windows x86-64** (`MSVC` & `MinGW`), and **Linux ARM64**, plus an automatic `PORTABLE` C fallback (`macOS` and other targets) — all without `RWX` codegen, respecting `W^X`, PIE/PIC, DWARF CFI, and Win64 SEH unwind guarantees.
- **Built for High-Density Embedded Workloads**: Keeps QuickJS's tiny footprint and fast cold startup while accelerating property inline caches, object allocation, RegExp execution, JSON parsing/stringification, array/TypedArray loops, and small calls.
- **100% Drop-In QuickJS-NG Compatibility**: Preserves the upstream `quickjs.h` C ABI and passes `81,152` Test262 cases with **`0` regressions** and **`31` upstream failures fixed** (`65` inherited vs. `96` in stock QuickJS-NG `0.15.1`).
- **Clean Zero-Conflict Upstream Overlay**: Upstream QuickJS-NG remains byte-for-byte untouched at the repository root (enforced via automated 19-file SHA-256 pins); every Turbo enhancement lives inside [`vm/`](vm/).

---

## Performance at a Glance

### Linux x86-64 vs. QuickJS-NG, Bellard QuickJS & V8 `--jitless`

| Engine | V8-v7 Score (↑ faster) | vs. Stock NG | JetStream-17 Index (↓ lower) | JetStream-17 Speedup (↑) |
| :--- | ---: | ---: | ---: | ---: |
| **QuickJS-NG `0.15.1`** *(Stock)* | `993.7` | `1.00×` | `100.0` | `1.00×` |
| **Bellard QuickJS `2026`** *(`-O2`)* | `1,465.7` | `1.47×` | `74.8` | `1.34×` |
| **QuickJS-Turbo** *(`LINUX_X86_64`)* | **`1,942.7`** | **`1.95×`** | **`59.9`** | **`1.67×`** |
| **V8 `--jitless`** *(Node.js `24.13.0`)* | `2,374.9` | `2.39×` | `46.2` | `2.16×` |

### Cross-Platform Summary (Relative to Bellard QuickJS `2026` = `1.00×`, ↑ higher is faster)

| Platform & Toolchain | V8-v7 | JetStream | Microbench (57 cases) |
| :--- | ---: | ---: | ---: |
| **Windows x86-64** (`WIN64` MSVC) | **`1.40×`** | **`1.38×`** *(9-app)* | **`1.33×`** |
| **Windows x86-64** (`WIN64` MinGW GCC) | **`1.61×`** *(~`1.94×` vs. Stock NG)* | **`1.46×`** *(9-app)* | **`1.46×`** |
| **Linux ARM64** (`LINUX_AARCH64`, AWS Graviton2) | **`1.50×`** | **`1.26×`** *(17-app)* | **`1.25×`** |

<details>
<summary>Per-benchmark highlights &amp; measurement methodology</summary>

- **Measurement Protocol**: Controlled serial, single-core execution (pinned CPU affinity, interleaved forward/reverse ABBA blocks, normal OS ASLR, zero PGO or profile-guided layout tuning) with `QJS_EXPERIMENT_ALLOCATOR=256`. JetStream-17 and JetStream-9 are fixed CLI subsets (not full browser JetStream 2 totals). Full logs and per-case regressions live under [`vm/docs/architecture/`](vm/docs/architecture/).
- **Linux x86-64 Highlights vs. Stock QuickJS-NG `0.15.1`** ([`PRODUCT-BASELINE.txt`](vm/docs/architecture/common/PRODUCT-BASELINE.txt), [`LINUX-FINAL-REVIEW.txt`](vm/docs/architecture/x86/linux/LINUX-FINAL-REVIEW.txt)):
  - **V8-v7**: `RegExp` `256.5 → 1,716.3` (**`6.69×`**), `NavierStokes` `1,161.0 → 2,600.2` (**`2.24×`**), `Richards` `763.2 → 1,428.3` (**`1.87×`**), `Crypto` `843.6 → 1,543.3` (**`1.83×`**), `DeltaBlue` `853.3 → 1,325.0` (**`1.55×`**), `EarleyBoyer` `1,714.5 → 2,618.3` (**`1.53×`**).
  - **JetStream-17**: `json-stringify-inspector` `140.6 ms → 23.4 ms` (**`6.02×`**), `json-parse-inspector` `131.1 ms → 39.0 ms` (**`3.36×`**), `cdjs` `559.9 ms → 287.1 ms` (**`1.95×`**), `pdfjs` `312.7 ms → 164.8 ms` (**`1.90×`**), `crypto` `145.1 ms → 78.5 ms` (**`1.85×`**).
  - **Microbenchmarks (`57` cases, `-30.88%` geomean elapsed)**: `typed_array_write` `31.7 ns → 5.5 ns` (**`5.78×`**), `array_write` `26.4 ns → 4.6 ns` (**`5.74×`**), `prop_read` `15.9 ns → 5.6 ns` (**`2.84×`**), `string_to_float` `165.8 ns → 78.6 ns` (**`2.11×`**), `func_call` `27.6 ns → 15.5 ns` (**`1.78×`**).
- **Windows x86-64** (`CPU 2`, normal ASLR): Paired V8-v7 screens against Stock QuickJS-NG `0.15.1` score **`1,917.8`–`1,935.4`** vs. **`985.7`–`997.3`** (**`~1.94×`**); V8 `--jitless` scores `2.00×` / `2.00×` / `1.89×` relative to Bellard QuickJS `2026`.
- **Linux ARM64** (AWS Graviton2 `Neoverse-N1`, `ASLR=2`): V8-v7 blocks `1.49×`–`1.50×`, JetStream-17 blocks `1.26×`–`1.28×`, Microbench blocks `1.25×`–`1.29×` vs. Bellard QuickJS `2026` ([`LINUX-AARCH64-HARDWARE.txt`](vm/docs/architecture/arm64/LINUX-AARCH64-HARDWARE.txt)).

</details>

---

## Running Untrusted or AI Code? Meet Capsid

If you want a ready-to-deploy **application runtime** rather than wiring `JS_NewRuntime()` and sandboxing from scratch, use **[Capsid](https://github.com/rowanellis-113/capsid)** ([Documentation](https://rowanellis-113.github.io/capsid/)):

```js
// Self-contained ESM running behind a Host-controlled Capsid boundary
export default {
  fetch(request) {
    return Response.json({
      message: "hello from Capsid",
      path: new URL(request.url).pathname,
    });
  },
};
```

| Need | Choose | What You Get |
| :--- | :--- | :--- |
| **Embed a fast JS engine in C/C++** | **QuickJS-Turbo** *(this repo)* | Drop-in `quickjs.h` / `qjs::qjs` CMake SDK, native register VMs, zero JIT (`W^X`-safe), CLI (`qjs`, `qjsc`) |
| **Safely run untrusted / AI-generated JS** | **[Capsid](https://github.com/rowanellis-113/capsid)** | OS-isolated worker processes, Host-controlled capabilities & egress policy, deadlines/limits, Web-standard `fetch(Request)` / WebSocket, public C ABI & managed pools |

---

## Quick Start & Embedding

### Prebuilt SDKs

Download ready-to-link static SDKs and CLI binaries (including `SHA256SUMS.txt` and `quickjs-turbo-version.json`) from **[GitHub Releases](https://github.com/rowanellis-113/quickjs-turbo/releases)** for Linux `x86-64`, Linux `ARM64`, Windows `x86-64` (`MSVC /MD`, `MSVC /MT` static CRT, `MinGW`), and `macOS ARM64` (`PORTABLE`).

### Build from Source

**Prerequisites**: Python `3.10+`, CMake `3.20+`, Ninja, and a C11 compiler (`GCC 13+` & GNU binutils on Linux; `MSVC` or `MinGW GCC 13+` on Windows; Apple Clang on macOS). No Node.js, profiler, or prior engine build is required.

#### Linux x86-64 (`GCC 13+`)

```sh
bash vm/tools/x86/linux/build/product-linux.sh build/linux-native out/sdk-linux-native
QJS_EXPERIMENT_ALLOCATOR=256 ./out/sdk-linux-native/bin/qjs -e 'print(1 + 2)'
```

#### Windows x86-64 (`MSVC` or `MinGW`)

```powershell
# MSVC dynamic CRT (/MD)
./vm/tools/x86/win64/build/build-baseline.ps1 -Toolchain msvc -Backend WIN64 -Test
./vm/tools/x86/win64/build/run-baseline.ps1 -Toolchain msvc -Arguments @('-e', 'print(1 + 2)')

# MSVC static CRT (/MT) with compile-time allocator default (no env var needed)
./vm/tools/x86/win64/build/build-baseline.ps1 -Toolchain msvc -MsvcRuntime MT -DefaultExperimentAllocator 256 -Backend WIN64 -Test

# MinGW-w64 GCC 13+
./vm/tools/x86/win64/build/build-baseline.ps1 -Toolchain mingw -Backend WIN64 -Test
```

#### Linux ARM64 & Portable C (`macOS` / Cross-Platform)

```sh
# Native Linux ARM64 (or cross-compile on x86-64)
bash vm/tools/arm64/build/product-linux-aarch64.sh build/arm64 out/sdk-arm64
QJS_EXPERIMENT_ALLOCATOR=256 ./out/sdk-arm64/bin/qjs -e 'print(42)'

# Portable C build on macOS or any POSIX/CMake host
cmake -S vm -B build/turbo-portable -G Ninja -DCMAKE_BUILD_TYPE=Release -DQJS_FRAME_BACKEND=PORTABLE -DQJS_FRAME_BUILD_TESTS=ON
cmake --build build/turbo-portable --parallel && ctest --test-dir build/turbo-portable --output-on-failure
```

### Embed via CMake (`find_package(qjs)`)

```sh
cmake -S vm/tests/common/consumer -B build/consumer -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_PREFIX_PATH="$PWD/out/sdk-linux-native"
cmake --build build/consumer && ctest --test-dir build/consumer --output-on-failure
```

Link `qjs` / `qjs::qjs` via `find_package(qjs CONFIG REQUIRED)`. For sandboxed C/C++ hosts that scrub environment variables or use static CRT on Windows, pass `-DQJS_DEFAULT_EXPERIMENT_ALLOCATOR=256`, `-DCMAKE_MSVC_RUNTIME_LIBRARY=MultiThreaded`, and `-DQJS_BUILD_CLI=OFF` (library-only SDK). Otherwise, set `QJS_EXPERIMENT_ALLOCATOR=256` in the environment when using the pooled allocator. See [`BUILDING.txt`](vm/docs/architecture/common/BUILDING.txt) for full CMake options and QEMU cross-testing instructions.

---

## How It Works (`vm/` Overlay)

1. **Native Register-Frame VMs**: Specialized SysV ELF (`x86-64`), Win64 PE/COFF (`x86-64`), and AAPCS64 (`ARM64`) dispatch engines keep hot interpreter state in physical CPU registers with complete `.eh_frame` CFI / `.pdata` SEH unwind tables.
2. **Adaptive Inline Caches & Object Model**: Polymorphic property/method ICs, inline object property storage, shape/prototype epoch guards, and direct field fast paths.
3. **Specialized Runtime Builtins**: Accelerated RegExp executor, fast JSON parser/serializer, zero-copy string concat, dense array/TypedArray loops, `Array.prototype.sort`, empty-args `apply`, `instanceof` epoch guards, and pooled small allocations.
4. **Side-by-Side Upstream Preservation**: Running `cmake -S .` builds pristine stock QuickJS-NG `0.15.1` from the exact same checkout, while `cmake -S vm` enables QuickJS-Turbo.

```text
quickjs-turbo/
├── CMakeLists.txt, quickjs.c, quickjs.h, ...   # Untouched QuickJS-NG 0.15.1 upstream core
├── tests/, examples/, docs/, gen/              # Untouched upstream tests, examples, docs & gen snapshots
├── .github/workflows/                          # QuickJS-Turbo CI, Test262 & SDK release pipelines
└── vm/                                         # All QuickJS-Turbo optimizations, VMs, tests & CI scripts
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

## Versioning, Releases & Contributing

- **Versioning (`v<upstream>-turbo.<N>`)**: [`vm/VERSION`](vm/VERSION) tracks the QuickJS-Turbo release version starting at `0.15.1-turbo.1` (Git tag `v0.15.1-turbo.1`). The prefix must match `QJS_UPSTREAM_VERSION` in [`QuickJSUpstreamPin.cmake`](vm/cmake/QuickJSUpstreamPin.cmake), while `.turbo.<N>` increments independently for each QuickJS-Turbo release (optional `-alpha.<K>`, `-beta.<K>`, or `-rc.<K>` suffix for prereleases).
- **Automated Verification**: Every push and pull request to `main` runs both [`ci.yml`](.github/workflows/ci.yml) (formatting, receipts, contracts, native/portable/sanitizer builds & SDK consumers) and [`test262.yml`](.github/workflows/test262.yml) (`81,152` Test262 cases across Linux `x86-64`, Linux `ARM64`, `PORTABLE`, Windows `MSVC`, and Windows `MinGW`).
- **Publishing a Release**: [`release.yml`](.github/workflows/release.yml) builds multi-platform SDK archives with `quickjs-turbo-version.json` and `SHA256SUMS.txt` automatically on pushing a matching `v*-turbo.*` tag (e.g., `git tag -a v0.15.1-turbo.1 -m "..." && git push origin v0.15.1-turbo.1`) or via GitHub Actions `workflow_dispatch` on `main` (`publish_release=true`).

<details>
<summary>Contributor contracts &amp; verification commands</summary>

1. Keep all product changes inside [`vm/`](vm/) (aside from `README.md` and `.github/`), preserving the one-way dependency DAG `common/ → {arm64/, x86/}` and all 19 pinned upstream SHA-256 checksums.
2. Run architecture boundary, layout, ABI, release-version, and formatter contract checks before opening a PR:

```sh
python -B vm/tests/common/test_arch_boundaries.py
python -B vm/tests/common/validate_layout.py --require-native
python -B vm/tests/common/test_property_ic_generator.py
python -B vm/tests/x86/common/test_vm_abi.py
python -B vm/ci/release_version.py
python -B vm/ci/test_ci_helpers.py
npm --prefix vm run format:check
python -B vm/tests/common/test_format_contract.py
```

3. See [`vm/AGENTS.md`](vm/AGENTS.md) for benchmark methodology, [`FORMAT.txt`](vm/docs/architecture/common/FORMAT.txt) for formatting setup, and [`vm/README.md`](vm/README.md) / [`docs/docs/intro.md`](docs/docs/intro.md) for component and upstream C API documentation.

</details>

---

## License & Acknowledgements

QuickJS-Turbo is licensed under the **MIT License** — see [`LICENSE`](LICENSE) and [`vm/THIRD_PARTY_NOTICES.txt`](vm/THIRD_PARTY_NOTICES.txt).

Built with deep appreciation for:
- **Fabrice Bellard** and **Charlie Gordon** — creators of the original QuickJS engine.
- **Saúl Ibarra Corretgé (`@saghul`)**, **Ben Noordhuis (`@bnoordhuis`)**, and the **QuickJS-NG contributors** — maintainers of the upstream QuickJS-NG project on which QuickJS-Turbo is based.
