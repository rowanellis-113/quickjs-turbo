# ⚡ QuickJS-Turbo

[![CI](https://github.com/rowanellis-113/quickjs-turbo/actions/workflows/ci.yml/badge.svg)](https://github.com/rowanellis-113/quickjs-turbo/actions/workflows/ci.yml)
[![Test262](https://github.com/rowanellis-113/quickjs-turbo/actions/workflows/test262.yml/badge.svg)](https://github.com/rowanellis-113/quickjs-turbo/actions/workflows/test262.yml)
[![Release](https://img.shields.io/github/v/release/rowanellis-113/quickjs-turbo?include_prereleases&label=release)](https://github.com/rowanellis-113/quickjs-turbo/releases)
[![Benchmarks](https://img.shields.io/badge/benchmarks-perf--site-f59e0b)](https://rowanellis-113.github.io/quickjs-turbo/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

**`V8 --jitless` speed in a QuickJS-sized binary.** Zero JIT · `0 RWX` · 100% `quickjs.h` drop-in on [QuickJS-NG](https://github.com/quickjs-ng/quickjs) `0.17.0`.

| Speed | Memory | Footprint & Safety | Compatibility |
| :--- | :--- | :--- | :--- |
| **99.2%–100.1%** of `V8 --jitless` *(Linux x86-64 V8-v7 Default/Density)*<br>*(1.86×–2.50× vs NG 0.17)* | **2.9×–8.1×** less RAM<br>than `V8 --jitless` | **96.3 KiB** cold heap<br>Zero JIT · `0 RWX` · CET-IBT | **100%** `quickjs.h` ABI<br>82k+ Test262 (`0` reg) |

```text
Linux x86-64 (v0.17.0-turbo.4 · Ryzen 3 3300X · GCC 13.3 · zero JIT)

V8-v7 Score (higher is better)                      Peak RSS
V8 --jitless (Node 24)  ████████████████████  2,178   462.8 MiB
QuickJS-Turbo (turbo.4) ████████████████████  2,160*  157.4 MiB  (2.9x less RAM)
Bellard QuickJS 2026    ████████████          1,348   146.8 MiB
QuickJS-NG 0.17.0       ██████████            1,109   155.4 MiB

* Density mode: 2,181 (100.1% V8 --jitless)
  micro56: 40.04 vs 40.79 ns (beats V8) · JetStream-17: 142.6 ms (1.67x NG · 7.8x less RSS)
```

---

## Benchmarks

Same-host cohorts only — raw scores are never mixed across CPUs, OSes, or sessions.

| Platform | Backend | V8-v7 *(vs NG / Bellard)* | `micro56` | `JetStream-17` | vs `V8 --jitless` |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Linux `x86-64`** | `LINUX_X86_64` | **2,160** *(1.95× / 1.60×)* | **40.0 ns** *(1.54×)* | **142.6 ms** *(1.67×)* | **99.2%** V8-v7 · **102%** micro56 · **7.8×** less RSS |
| **Windows `x86-64`** | `WIN_X86_64` | **2,299** MinGW / **2,178** MSVC | **39.8 / 41.8 ns** | **135.7 / 145.2 ms** | **2.22×–2.50×** NG *(8/8 V8 · 17/17 JS17)* |
| **Linux `ARM64`** | `LINUX_AARCH64` | **1,320** *(1.86× / 1.57×)* | **66.2 ns** *(1.50×)* | **220.5 ms** *(1.57×)* | **95.5%** V8-v7 · **97%** micro56 · **8.1×** less RSS |
| **macOS `x86-64`** | `MACOS_X86_64` | **2,055** *(1.96× / 1.69×)* | **45.5 ns** *(1.66×)* | **152.4 ms** *(1.68×)* | **92.9%** V8-v7 · **93%** micro56 · **6.0×** less RSS |

📊 **[Explore interactive charts & per-workload breakdowns on `perf-site` →](https://rowanellis-113.github.io/quickjs-turbo/)**

<details>
<summary>Measurement notes &amp; verified binary details</summary>

- **Linux `x86-64`** (`6ed860a`, SHA-256 `d039a99a9b8d`, Ryzen 3 3300X, GCC 13.3, CPU2 serial): monotonic-clock 4-ABBA V8-v7 reaches **2,159.8 Default / 2,180.9 Density** vs Node 24 `V8 --jitless` (`2,177.9`, **2.94×** lower RSS; wins 4/8 subtests: `NavierStokes 1.83×`, `Crypto 1.43×`, `Splay 1.23×`, `Richards 1.04×`); `micro56` `40.04` vs `40.79 ns/op`; `JetStream-17` `142.61 ms` (`17/17` sweep vs NG, `6/17` wins vs V8 at `10.2` vs `80.1 MiB` median RSS).
- **Windows `x86-64`** (`6ed860a`, MinGW GCC 13.1 `38be95760794` / MSVC 14.50 `/MT` `b583f8fad0d2`, `KERNEL32.dll`-only PE imports): `8/8` V8-v7 sweep vs both NG and Bellard; `17/17` JetStream-17 sweep vs NG (`1.82×` MinGW / `1.95×` MSVC, `json-stringify-inspector 6.97×`); `sort_bench` `4.21×` faster on MSVC.
- **Linux `ARM64`** (`6ed860a`, SHA-256 `91c2ed014d0f`, AWS Graviton2 Neoverse-N1, GCC 13.4, CPU1): 4-engine cohort `1,320.5` V8-v7 (`8/8` sweep), `66.16 ns/op` `micro56`, `220.48 ms` `JetStream-17`. Paired ABBA vs Node `v24.13.0 --jitless`: **95.5%** V8-v7 (`1,313.9` vs `1,375.1`, **1.67×** lower RSS, wins 4/8), **96.9%** `micro56` (`sort_bench 1.34×`), **83.7% body / 90.3% cold** `JetStream-17` (**8.10×** lower RSS, wins 5/17). Native ARM64 Test262: `81,924` cases (`0` regressions).
- **macOS `x86-64`** (`v0.17.0-turbo.5`, benchmarked SHA-256 `c013c6bbdc37`; CFI-unwind-hardened final binary `2da16defd795` has identical executable code; MacBookPro14,1 i5-7360U, Darwin 22.6, Apple Clang 15.0): same-host suites reach **2,054.5** V8-v7 *(5-engine 2-ABBA)* (`1.96×` NG `1,049.5` · `1.69×` Bellard `-O3` `1,215.5` · `1.44×` PORTABLE `1,427.5` [`8/8` sweep against all three] · **92.9%** of Node `v26.4 --jitless` `2,211.5` at **2.26×** lower RSS; wins `NavierStokes 1.93×`, `Crypto 1.50×`), **45.49 ns/op** `micro56` *(4-engine 2-ABBA)* (`1.66×` NG [`55/57`], `1.59×` Bellard `-O3` `72.48 ns/op`, `sort_bench 3.52×`) plus separate paired 2-ABBA vs Node (`45.53` vs `42.17 ns/op` [**92.6%**] at `26.9×` lower RSS), and **152.40 ms** `JetStream-17` *(5-engine same-session per-workload aggregate)* (`1.68×` NG [`16/17`], `1.52×` Bellard `-O3` [`16/17`], `5/17` wins vs Node at **6.00×** lower median RSS [`12.45` vs `74.66 MiB`]). `962/962` CTest (including Darwin `libunwind` CVM unwind recovery) + `133`-file receipt-driven zero-Python pregen + dual-prefix SDK C/C++11 consumer verified.
- **Suite definition**: `micro56` covers the 56 uniform `ns/op` cases separately from `sort_bench` (`sum_us`). Full methodology and receipts live in [`PRODUCT-BASELINE.txt`](vm/docs/architecture/common/PRODUCT-BASELINE.txt).

</details>

---

## Why QuickJS-Turbo?

- **Zero JIT & `0 RWX` by Design** — Ahead-of-time assembly VMs with full DWARF CFI, Win64 SEH unwind, and `139/139` Linux CET-IBT `endbr64` targets. Safe on iOS, consoles, locked-down containers, and edge workers.
- **Native Register VM, CVM & Property ICs** — Register-pinned dispatch (`x86-64`, `Win64`, `ARM64`), zero-spill native coroutine executors, Tier-5 VA constructors, fused loops, and adaptive Property ICs.
- **Fast Builtins & Deterministic Hybrid GC** — Zero-JIT RegExp (`5.9×`), 256-bit BigInt (beats `V8 --jitless` on `bigint-noble-ed25519`), fast JSON/dtoa/atod, and generational partial cycle GC (`-85.8%` full cycle scans).
- **100% `quickjs.h` Drop-In ABI** — Unmodified QuickJS-NG `0.17.0` (`BC_VERSION 29` / `txiki.js v26.11.0`), `96.29 KiB` cold runtime, and optional `quickjs-turbo.h` density & slab-purge APIs (`JS_PurgePropertyIC`).

---

## Quick Start

**Prebuilt SDKs** (`libqjs`, `qjs`, `qjsc` for Linux `x86-64`/`ARM64`, Windows `MSVC`/`MinGW`, macOS): download from **[GitHub Releases](https://github.com/rowanellis-113/quickjs-turbo/releases)**.

### Build from Source

Requires CMake `3.20+`, Ninja, Python `3.9+` *(3.10+ for format tools)*, and GCC `13+` / MSVC / MinGW / Clang.

```sh
# Linux x86-64
bash vm/tools/x86/linux/build/product-linux.sh build/linux out/sdk

# Linux ARM64
bash vm/tools/arm64/build/product-linux-aarch64.sh build/arm64 out/sdk

# macOS x86-64 (native Mach-O VM)
bash vm/tools/x86/macos/build/product-macos.sh build/macos-x86_64 out/sdk

# Windows x86-64 (MSVC / clang-cl / MinGW) or macOS ARM64 (PORTABLE)
cmake -S vm -B build/release -G Ninja -DCMAKE_BUILD_TYPE=Release && cmake --build build/release --parallel
```

### Embed in CMake & C

```cmake
# Vendor via add_subdirectory(vendor/quickjs-turbo/vm) or find_package(quickjs-turbo CONFIG REQUIRED)
target_link_libraries(my_app PRIVATE quickjs-turbo::qjs)
```

```c
#include "quickjs.h"
#include "quickjs-turbo.h"

QJSTurboOptions opts;
QJS_TurboOptionsInit(&opts);
opts.own_bytecode_tail = QJS_TURBO_OFF; /* PIC-only: zero tail copy overhead */
opts.property_ic_warmup = 16;           /* Lazy IC allocation after 16 hits  */
QJS_SetTurboDefaults(&opts);

JSRuntime *rt = JS_NewRuntime();
/* ... when worker is idle: */
JS_PurgePropertyIC(rt);                 /* Reclaim all Property IC slabs     */
```

<details>
<summary>Supported targets, static CRT (/MT) &amp; Python-free pregen builds</summary>

| Platform | Backend | Toolchains | Notes |
| :--- | :--- | :--- | :--- |
| **Linux `x86-64`** | `LINUX_X86_64` | GCC 13/14+ (`glibc` / `musl`) | Native ELF VM + CVM, Tier-5 constructors, PIE + CFI + CET `endbr64` |
| **Windows `x86-64`** | `WIN_X86_64` | MSVC / `clang-cl` / MinGW | Unified ASM VM + CVM, native PE TLS (MinGW), SEH unwind, `/MT` `KERNEL32`-only |
| **Linux `ARM64`** | `LINUX_AARCH64` | GCC 13/14+ (`glibc` / `musl`) | Native ELF VM (`161` ops) + zero-spill CVM + Tier-5 constructors |
| **macOS `x86-64`** | `MACOS_X86_64` | Apple Clang 15+ | Native Mach-O ASM VM + CVM, PIE + full DWARF CFI + Clang spill tuning |
| **macOS `ARM64` & Sanitizers** | `PORTABLE` | Clang / GCC / MSVC | `AUTO` fallback + ASan/UBSan/TSan/MSan/Fuzz *(ARM64 SDK cross-compiled on CI; native Apple Silicon runtime tests pending)* |

- **Windows static CRT (`/MT`, `KERNEL32.dll` only)**: add `-DCMAKE_MSVC_RUNTIME_LIBRARY=MultiThreaded`.
- **Offline / Python-free builds**: export once with `python3 vm/tools/common/export-pregen.py --source vm --build <build-dir> --output <pregen-dir>`, then configure downstream with `-DQJS_USE_PREGEN_ASM=ON -DQJS_PREGEN_DIR=<pregen-dir>`.

</details>

---

> [!TIP]
> **Building an AI sandbox or plugin runtime?** QuickJS-Turbo is a raw C engine (`quickjs.h`). If you need OS process isolation, CPU/memory quotas, egress control, and Web-standard ESM + `fetch()` out of the box, use **[Capsid](https://github.com/rowanellis-113/capsid)** (*[Docs →](https://rowanellis-113.github.io/capsid/)*) — built on QuickJS-Turbo.

---

## Documentation

All optimizations live inside [`vm/`](vm/), keeping upstream QuickJS-NG `0.17.0` byte-for-byte pristine at repo root.

- **Guides & Architecture**: [Docs Index](vm/docs/architecture/common/README.txt) · [Build & Embedding](vm/docs/architecture/common/BUILDING.txt) · [Optimizations](vm/docs/architecture/common/OPTIMIZATIONS.txt) · [Hybrid GC](vm/docs/architecture/common/HYBRID-GC.txt) · [ABI Contract & Proposed Opt-In Baseline JIT](vm/docs/architecture/common/ABI-AND-BASELINE-JIT.txt)
- **Hardware Baselines**: [All Platforms](vm/docs/architecture/common/PRODUCT-BASELINE.txt) · [Linux x86-64](vm/docs/architecture/x86/linux/LINUX-FINAL-REVIEW.txt) · [Windows x86-64](vm/docs/architecture/x86/win64/WIN-X86-64.txt) · [macOS x86-64](vm/docs/architecture/x86/macos/MACOS-X86-64.txt) · [Linux ARM64](vm/docs/architecture/arm64/LINUX-AARCH64-HARDWARE.txt)
- **Policy**: [Measurement & Contribution Rules](vm/AGENTS.md)

## License

MIT — see [`LICENSE`](LICENSE) and [`vm/THIRD_PARTY_NOTICES.txt`](vm/THIRD_PARTY_NOTICES.txt). Built on **Fabrice Bellard**, **Charlie Gordon**, and **[QuickJS-NG](https://github.com/quickjs-ng/quickjs)**.
