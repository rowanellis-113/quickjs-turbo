# ⚡ QuickJS-Turbo

[![CI](https://github.com/rowanellis-113/quickjs-turbo/actions/workflows/ci.yml/badge.svg)](https://github.com/rowanellis-113/quickjs-turbo/actions/workflows/ci.yml)
[![Test262](https://github.com/rowanellis-113/quickjs-turbo/actions/workflows/test262.yml/badge.svg)](https://github.com/rowanellis-113/quickjs-turbo/actions/workflows/test262.yml)
[![Release](https://img.shields.io/github/v/release/rowanellis-113/quickjs-turbo?include_prereleases&label=release)](https://github.com/rowanellis-113/quickjs-turbo/releases)
[![Benchmarks](https://img.shields.io/badge/benchmarks-perf--site-f59e0b)](https://rowanellis-113.github.io/quickjs-turbo/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

**`V8 --jitless` parity in a QuickJS-sized binary. Zero JIT. 100% `quickjs.h` ABI drop-in (`txiki.js v26.11.0` aligned).**

QuickJS-Turbo supercharges [QuickJS-NG](https://github.com/quickjs-ng/quickjs) `0.17.0` with native register-frame assembly VMs, zero-spill CVM coroutine executors, Tier-5 straight-line VA constructor compilers, adaptive inline caches, Hybrid RC + Partial Cycle GC, zero-JIT RegExp scanning, and 256-bit BigInt / numeric / string / JSON fast paths — delivering **`1.86×–2.50×` V8-v7**, **`1.50×–2.18×` `micro56`**, and **`1.57×–1.95×` `JetStream-17`** over same-host Stock QuickJS-NG `0.17.0` (**`1.37×–1.66×` vs Bellard 2026**) with zero runtime code generation and zero `RWX` pages.

```text
Reference Linux x86-64 Cohort (v0.17.0-turbo.4, Ryzen 3 3300X, GCC 13.3, CPU2 serial, zero JIT)

V8-v7 Throughput (monotonic-clock verified, 4 ABBA rounds, higher is better)
V8 --jitless (Node 24)   ████████████████████████  2,178  (462.8 MiB Peak RSS)
QuickJS-Turbo (turbo.4)  ████████████████████████  2,160  (1.95x NG · 1.60x Bellard · 99.2% Def / 100.1% Dens V8 · 157.4 MiB RSS)
Bellard QuickJS 2026     ███████████████           1,348  (146.8 MiB Peak RSS)
QuickJS-NG 0.17.0        ████████████              1,109  (155.4 MiB Peak RSS)

micro56 Geomean (56 uniform ns/op cases, lower is better)   JetStream-17 Body Geomean (17 workloads, lower is better)
QuickJS-Turbo (turbo.4)  40.04 ns  (1.55x NG · 1.019x V8!)  V8 --jitless (Node 24)   125.7 ms  (80.1 MiB median RSS)
V8 --jitless (Node 24)   40.79 ns  (sort: 0.77 vs 0.74 us)  QuickJS-Turbo (turbo.4)  142.6 ms  (1.67x NG [17/17] · 1.42x Bel · 10.2 MiB RSS)
Bellard QuickJS 2026     58.38 ns                           Bellard QuickJS 2026     202.1 ms
QuickJS-NG 0.17.0        61.84 ns                           QuickJS-NG 0.17.0        238.8 ms
```

---

## Building an AI Sandbox or Plugin Runtime? Use Capsid Instead

**QuickJS-Turbo** is a raw C engine (`quickjs.h`). It executes JavaScript fast, but *you* still have to build process isolation, memory/CPU limits, timeouts, network policies, and Web APIs.

If you need to **safely run untrusted or AI-generated JavaScript in production**, don't build a sandbox from scratch — use **[Capsid](https://github.com/rowanellis-113/capsid)**:

```js
// Runs inside an OS-isolated Capsid worker behind a Host-controlled boundary
export default {
  fetch(request) {
    return Response.json({ ok: true, url: request.url });
  },
};
```

- **Host-Controlled Security Boundary**: OS process isolation, capability-based bindings, and strict egress control.
- **High-Density Multi-Tenancy**: Sub-millisecond cold start, per-request deadlines, resource quotas, and automatic worker reclamation.
- **Web-Standard Ergonomics**: Self-contained ESM apps with `fetch(Request)` and WebSockets — zero Node.js bloat.

👉 **[Explore Capsid on GitHub →](https://github.com/rowanellis-113/capsid)** · **[Read the Capsid Docs →](https://rowanellis-113.github.io/capsid/)**

---

## Why QuickJS-Turbo?

- **Zero JIT, `W^X` & CET-IBT Clean**: Ahead-of-time assembly VMs use zero `RWX` memory and ship with full DWARF CFI, Win64 SEH stack unwinding, and `139/139` Linux CVM CET-IBT `endbr64` indirect jump targets for iOS, consoles, containers, and edge workers.
- **Native Register VM, Zero-Spill CVM & Tier-5 Constructors**: Replaces the C switch loop with register-pinned assembly dispatch, zero-spill native CVM coroutine executors across Linux `x86-64`, `Win64`, and `ARM64`, Tier-5 straight-line VA constructor compilers, fused compare-branch/pre-dec loops, native PE TLS on Win64 MinGW, and adaptive Property ICs — up to **`6.97×`** `json-stringify-inspector`, **`5.93×`** RegExp, **`5.00×`** `empty_loop`, **`4.84×`** `float_to_string`, **`4.60×`** `prop_read`, and **`4.21×`** `sort_bench`.
- **Zero-JIT RegExp, 256-bit BigInt & Deterministic Hybrid GC**: Adds zero-JIT range/sticky/greedy RegExp scanning, 256-bit/Curve25519 BigInt kernels (`bigint-noble-ed25519` beats `V8 --jitless` on both Linux `x86-64` [`1.16×`] and `ARM64` [`1.08×`]), fast `dtoa`/`atod`/DataView/slice/array-splice, and generational partial cycle GC (`-85.8%` full cycle scans; **`7.8×–8.1×` lower median JetStream-17 RSS vs `V8 --jitless`**).
- **100% `quickjs.h` Drop-In ABI**: Zero header or public struct ABI changes (`82,220` x86-64 + `81,924` native ARM64 Test262 with `0` regressions; `4,718/4,718` cross-platform CTest; `txiki.js v26.11.0` / `BC_VERSION 29` compatible; **`96.29 KiB`** initial runtime + context heap with zero cold bloat), plus optional `quickjs-turbo.h` density controls.

### Benchmarks Across Platforms

| Same-Host Cohort | Turbo V8-v7 | `micro56` (`ns/op`) | `JetStream-17` (body) | vs Same-Host NG `0.17.0` / Bellard `2026-06-04` |
| :--- | ---: | ---: | ---: | :--- |
| **Linux `x86-64`** *(v0.17.0-turbo.4, Ryzen 3 3300X, GCC 13.3)* | **2,160** *(mono; 99.2% / 100.1% V8)* | **40.04 ns** *(1.019× V8!)* | **142.6 ms** *(17/17 NG · 10.2 MiB)* | **1.95× / 1.60×** V8 · **1.55× / 1.46×** `micro56` · **1.67× / 1.42×** JS17 |
| **Windows `x86-64`** *(v0.17.0-turbo.4, MinGW / MSVC `/MT`)* | **2,299 / 2,178** *(8/8 vs both)* | **39.76 / 41.79 ns** *(sort 0.58/0.48)* | **135.7 / 145.2 ms** *(17/17 NG)* | **2.22× / 2.50×** V8 · **1.78× / 2.18×** `micro56` · **1.82× / 1.95×** JS17 *(vs NG)* |
| **Linux `ARM64`** *(v0.17.0-turbo.4, AWS Neoverse-N1, GCC 13.4)* | **1,320** *(8/8 · 95.5% V8)* | **66.16 ns** *(96.9% V8 · sort 0.98)* | **220.5 ms** *(15/17 NG · 10.9 MiB)* | **1.86× / 1.57×** V8 · **1.50× / 1.45×** `micro56` · **1.57× / 1.37×** JS17 |
| **macOS `x86-64`** *(v0.15.1-turbo.6–.8 Intel i5 hardware)* | **1,742** | *1.17× micro72* | **1.34×** vs Bellard | **1.47×** V8 vs `PORTABLE` · **1.45×** vs Bellard `-O3` |

> Notes on measurement integrity: (1) All `v0.17.0-turbo.4` cohorts are freshly measured on final commit `6ed860a` binaries with recorded SHA-256s; Linux `x86-64` and `ARM64` V8-v7 use `performance.now()` monotonic recomputation on identical iterations (eliminating WSL2 wall-clock jumps). On Linux `x86-64`, `v0.17.0-turbo.4` reaches **99.2% Default (`2,159.8`) / 100.1% Density (`2,180.9`)** of Node 24 `V8 --jitless` (`2,177.9`, **2.94× lower Peak RSS**), beats `V8 --jitless` on **4/8** V8-v7 subtests (`NavierStokes 1.83×`, `Crypto 1.43×`, `Splay 1.23×`, `Richards 1.04×`), surpasses `V8 --jitless` on `micro56` (`40.04` vs `40.79 ns/op`), and wins **6/17** `JetStream-17` workloads at **7.83× lower median RSS** (`10.2` vs `80.1 MiB`). (2) On real AWS Neoverse-N1 `ARM64`, paired ABBA vs Node `v24.13.0 --jitless` reaches **95.5%** V8-v7 (`1,313.9` vs `1,375.1`, **1.67× lower RSS**, winning `NavierStokes 1.48×`, `Crypto 1.27×`, `Splay 1.19×`, `RayTrace 1.04×`), **96.9%** `micro56` (`sort_bench 1.34×` faster), and **83.7% body / 90.3% cold** `JetStream-17` (**8.10× lower median RSS**, winning **5/17** workloads). (3) `micro56` separates the 56 uniform `ns/op` cases from `sort_bench` (`sum_us`); the legacy 57-case composite is reported separately as a dimensionless `micro57` index. Explore interactive charts on **[`perf-site` →](https://rowanellis-113.github.io/quickjs-turbo/)**.

### Supported Targets

| Platform | Backend | Toolchains | Notes |
| :--- | :--- | :--- | :--- |
| **Linux `x86-64`** | `LINUX_X86_64` | GCC 13/14+ (`glibc` & `musl`) | Native ELF ASM VM + CVM, Tier-5 VA constructors, fused loops, PIE + DWARF CFI + CET-IBT `endbr64` |
| **macOS `x86-64`** | `MACOS_X86_64` | Apple Clang 15+ | Native Mach-O ASM VM, PIE + DWARF CFI, `AUTO`-selected |
| **Windows `x86-64`** | `WIN_X86_64` | MSVC / `clang-cl` / MinGW | Unified native ASM VM + CVM (zero GNU binutils on MSVC, native PE TLS on MinGW) + SEH unwind |
| **Linux `ARM64`** | `LINUX_AARCH64` | GCC 13/14+ (`glibc` & `musl`) | Native ELF ASM VM (`161` ops) + zero-spill AArch64 CVM + Tier-5 VA constructors + `JSArena` append |
| **macOS `ARM64` & Sanitizers** | `PORTABLE` | Clang / GCC / MSVC | `AUTO` fallback + ASan / UBSan / TSan / MSan / Fuzz *(macOS ARM64 SDK is cross-compiled on Intel CI with `lipo` + consumer link checks; Apple Silicon native runtime validation pending)* |

---

## ABI Contract & Proposed Baseline JIT Roadmap

QuickJS-Turbo ships today as a **strict Zero-JIT, `0 RWX` register-frame interpreter** built on a verified **two-layer ABI contract**. That same internal ABI also provides a clean foundation for a **proposed, opt-in bytecode-driven Baseline JIT** (future roadmap; not shipped in `v0.17.0-turbo.4`).

### 1. Shipping ABI Contracts (Production Today)

- **100% Drop-In Public C ABI (`quickjs.h`)**: Upstream QuickJS-NG `0.17.0` headers, public struct layouts (`16 B JSValue`), and bytecode wire format (`BC_VERSION 29`, verified on unmodified `txiki.js v26.11.0`) remain untouched. All runtime tuning (`quickjs-turbo.h`) is strictly additive.
- **Pinned Native Register-Frame & CVM ABI**: Both `LINUX_AARCH64` (`x19` state, `x20` PC, `x21` SP, `x22` frame, `x23` locals, `x24` args, `x25` dispatch table) and `x86-64` (`LINUX_X86_64` / `MACOS_X86_64` / `WIN_X86_64`) execute over a bounded `JSFrame` segment arena, pre-validated bytecode admission (`FRAME_KIND` + jump-target `boundaries` bitmap), zero-spill native CVM coroutine segments, and **Clean/Dirty lazy stack-frame publication** at call/GC/exception safepoints.
- **Verified Binary & Unwind Hygiene**: Every internal struct offset and generated boundary is SHA-256 verified at build time (`core-fields.json` + `511` source receipts), with complete DWARF CFI FDEs (ELF/Mach-O), Linux CET-IBT `endbr64` CVM targets (`139/139`), and Win64 SEH `.pdata`/`.xdata` unwind metadata.

### 2. Proposed Optional Bytecode-Driven Baseline JIT (Future Roadmap)

Symbol-level hardware sampling (`perf` on Graviton2 & x86-64) shows `JS_FrameInterp` accounts for **53%–98%** of CPU samples across compute and object workloads — motivating an optional future tier targeting indirect dispatch, operand decode, and `[sp]` stack traffic without introducing an AST:

```text
Proposed Opt-In Tier (Future Roadmap — Not Enabled by Default):

JSFunctionBytecode (No AST)
   │  Single-pass linear scan reusing FRAME_KIND & jump-target boundaries bitmap
   ▼
Proposed 1-Pass Virtual Operand Stack (2–4 reg TOS cache) + Copy-and-Patch Stencils
   │  Targets indirect dispatch, bytecode fetch/decode, PC updates, and [sp] round-trips
   ▼
Shared Register-Frame ABI (Zero-Bridge Interop with Native ASM VM)
   ├─ Proposed direct-baked Property ICs (PC/RIP-relative IC slot pointers)
   ├─ Proposed monomorphic Call IC + Loop OSR ({pc_offset -> jit_loop_entry})
   └─ Cold bailout stubs reusing existing Clean/Dirty slow paths & Hybrid RC/GC
   ▼
Proposed Strict W^X Code Arena (RW -> RX, never simultaneous RWX · Hotness-gated -> 0 B cold bloat)
```

- **Why No AST**: Compiles directly from `JSFunctionBytecode` (like V8 Sparkplug, JSC Baseline, and CPython Copy-and-Patch) so scopes, closures (`JSVarRef`), TDZ, and `try/catch` tables stay lowered in bytecode, preserving the **`96.29 KiB`** initial runtime + context heap and sub-ms parse speed.
- **Strict Opt-In Governance**: The default production configuration will remain **`0 RWX` / Zero JIT**; any future Baseline JIT tier will be gated behind explicit compile-time and runtime switches and phased stopping criteria (`Phase 0` PoC → `Phase 2` Test262 gate).

See **[ABI-AND-BASELINE-JIT.txt](vm/docs/architecture/common/ABI-AND-BASELINE-JIT.txt)** for the full register contract, Copy-and-Patch design, and phased stopping criteria.

---

## Quick Start

### 1. Download Prebuilt SDK

Grab ready-to-link static libraries (`libqjs`) and `qjs` / `qjsc` CLIs for Linux (`x86-64`, `ARM64`), Windows (`MSVC /MD`, `MSVC /MT`, `MinGW`), and macOS from **[GitHub Releases](https://github.com/rowanellis-113/quickjs-turbo/releases)**.

### 2. Or Build from Source in One Command

Requires CMake `3.20+`, Ninja, Python `3.10+`, and a C11 compiler (`GCC 13+` on Linux, `MSVC` or `MinGW GCC 13+` on Windows, Clang on macOS).

```sh
# Linux x86-64
bash vm/tools/x86/linux/build/product-linux.sh build/linux out/sdk

# Linux ARM64
bash vm/tools/arm64/build/product-linux-aarch64.sh build/arm64 out/sdk

# macOS x86-64 (native Mach-O assembly VM)
bash vm/tools/x86/macos/build/product-macos.sh build/macos-x86_64 out/sdk

# macOS ARM64 / Portable C
cmake -S vm -B build/portable -G Ninja -DCMAKE_BUILD_TYPE=Release && cmake --build build/portable
```

```powershell
# Windows x86-64 (MSVC / clang-cl / MinGW — AUTO selects WIN_X86_64)
cmake -S vm -B build/win-x86_64 -G Ninja -DCMAKE_BUILD_TYPE=Release -DQJS_FRAME_BACKEND=AUTO -DQJS_PROPERTY_IC=ON
cmake --build build/win-x86_64 --parallel

# Static CRT (/MT, KERNEL32.dll-only imports)
cmake -S vm -B build/win-msvc-mt -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_MSVC_RUNTIME_LIBRARY=MultiThreaded
cmake --build build/win-msvc-mt --parallel
```

### 3. Embed via CMake & Configure via `quickjs-turbo.h`

```cmake
# Either via add_subdirectory(vendor/quickjs-turbo/vm) or find_package(quickjs-turbo CONFIG REQUIRED)
target_link_libraries(my_app PRIVATE quickjs-turbo::qjs)
```

```c
#include "quickjs.h"
#include "quickjs-turbo.h"

QJSTurboOptions opts;
QJS_TurboOptionsInit(&opts);
opts.own_bytecode_tail = QJS_TURBO_OFF; /* PIC-only: zero tail copy overhead */
opts.property_ic_warmup = 16;           /* Lazy IC allocation after 16 accesses */
QJS_SetTurboDefaults(&opts);

JSRuntime *rt = JS_NewRuntime();
QJSTurboInfo info;
QJS_GetTurboInfo(rt, &info);            /* Structured backend & IC telemetry */
/* ... when worker becomes idle: */
JS_PurgePropertyIC(rt);                 /* Reclaim all Property IC slabs */
```

For offline or cross-compilation builds without Python at build time, export a SHA256-verified assembly bundle with `python3 vm/tools/common/export-pregen.py --source vm --build <build-dir> --output <pregen-dir>` and configure downstream with `-DQJS_USE_PREGEN_ASM=ON -DQJS_PREGEN_DIR=<pregen-dir>`.

---

## Architecture & Docs

All QuickJS-Turbo optimizations live cleanly inside [`vm/`](vm/), keeping upstream QuickJS-NG `0.17.0` byte-for-byte pristine at the repository root for effortless upstream tracking and side-by-side A/B benchmarking.

- **[Documentation Index](vm/docs/architecture/common/README.txt)** · **[Build, Static CRT & Embedding Guide](vm/docs/architecture/common/BUILDING.txt)** · **[ABI & Baseline JIT Design](vm/docs/architecture/common/ABI-AND-BASELINE-JIT.txt)**
- **[Benchmark Baselines](vm/docs/architecture/common/PRODUCT-BASELINE.txt)** · **[Linux x86-64](vm/docs/architecture/x86/linux/LINUX-FINAL-REVIEW.txt)** · **[Windows x86-64](vm/docs/architecture/x86/win64/WIN-X86-64.txt)** · **[macOS x86-64](vm/docs/architecture/x86/macos/MACOS-X86-64.txt)** · **[Linux ARM64](vm/docs/architecture/arm64/LINUX-AARCH64-HARDWARE.txt)**
- **[Optimization Deep Dive](vm/docs/architecture/common/OPTIMIZATIONS.txt)** · **[Hybrid RC & Cycle GC](vm/docs/architecture/common/HYBRID-GC.txt)** · **[Contributor & Measurement Policy](vm/AGENTS.md)**

---

## License

MIT — see [`LICENSE`](LICENSE) and [`vm/THIRD_PARTY_NOTICES.txt`](vm/THIRD_PARTY_NOTICES.txt). Built on the shoulders of **Fabrice Bellard**, **Charlie Gordon**, and the **[QuickJS-NG](https://github.com/quickjs-ng/quickjs)** maintainers.
