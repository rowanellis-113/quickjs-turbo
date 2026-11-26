# ⚡ QuickJS-Turbo

[![CI](https://github.com/rowanellis-113/quickjs-turbo/actions/workflows/ci.yml/badge.svg)](https://github.com/rowanellis-113/quickjs-turbo/actions/workflows/ci.yml)
[![Test262](https://github.com/rowanellis-113/quickjs-turbo/actions/workflows/test262.yml/badge.svg)](https://github.com/rowanellis-113/quickjs-turbo/actions/workflows/test262.yml)
[![Release](https://img.shields.io/github/v/release/rowanellis-113/quickjs-turbo?include_prereleases&label=release)](https://github.com/rowanellis-113/quickjs-turbo/releases)
[![Benchmarks](https://img.shields.io/badge/benchmarks-perf--site-f59e0b)](https://rowanellis-113.github.io/quickjs-turbo/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

**Near-V8 `--jitless` speed in a QuickJS-sized binary. Zero JIT. 100% `quickjs.h` ABI drop-in (`txiki.js v26.11.0` aligned).**

QuickJS-Turbo supercharges [QuickJS-NG](https://github.com/quickjs-ng/quickjs) `0.17.0` with native register-frame assembly VMs, adaptive inline caches, Hybrid RC + Partial Cycle GC, and specialized numeric/string/JSON/RegExp builtins — delivering **`1.73×–2.27×` V8-v7**, **`1.53×–1.96×` `micro56`**, and **`1.50×–1.66×` `JetStream-17`** over same-host Stock QuickJS-NG `0.17.0` (**`1.18×–1.48×` vs Bellard 2026**) with zero runtime code generation and zero `RWX` pages.

```text
Reference Linux x86-64 Cohort (v0.17.0-turbo.3, Ryzen 3 3300X, GCC 13.3, CPU2 serial, zero JIT)

V8-v7 Throughput (monotonic-clock verified, 4 ABBA rounds, higher is better)
V8 --jitless (Node 24)   ████████████████████████  2,164  (462.5 MiB Peak RSS)
QuickJS-Turbo (turbo.3)  █████████████████████     1,866  (1.73x NG 0.17 · 1.39x Bellard · 86.2% V8 --jitless · 157.4 MiB RSS)
Bellard QuickJS 2026     ███████████████           1,347  (146.8 MiB Peak RSS)
QuickJS-NG 0.17.0        ████████████              1,082  (155.3 MiB Peak RSS)

micro56 Geomean (56 uniform ns/op cases, lower is better)   JetStream-17 Body Geomean (17 workloads, lower is better)
QuickJS-Turbo (turbo.3)  40.33 ns  (1.53x NG · 1.015x V8!)  V8 --jitless (Node 24)   127.4 ms  (80.0 MiB median RSS)
V8 --jitless (Node 24)   40.91 ns  (sort: 0.73 vs 0.75 us)  QuickJS-Turbo (turbo.3)  153.9 ms  (1.56x NG · 1.34x Bel · 10.1 MiB RSS)
Bellard QuickJS 2026     58.50 ns                           Bellard QuickJS 2026     206.4 ms
QuickJS-NG 0.17.0        61.76 ns                           QuickJS-NG 0.17.0        239.9 ms
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

- **Zero JIT, `W^X` Safe**: Ahead-of-time assembly VMs use zero `RWX` memory and ship with full DWARF CFI and Win64 SEH stack unwinding for iOS, consoles, containers, and edge workers.
- **Register VM, Adaptive ICs & Fast Builtins**: Replaces the C switch loop with register-pinned assembly dispatch, adaptive Property ICs, fast `dtoa`/`atod`, native string slicing, and specialized RegExp/JSON workers — up to **`7.01×`** `json-stringify-inspector`, **`4.90×`** `float_to_string`, **`4.68×`** RegExp, **`3.94×`** `prop_read`, and **`4.24×`** `typed_array_read`.
- **Deterministic RC + Fewer GC Pauses**: Keeps QuickJS's immediate reference counting while generational partial cycle GC cuts full-heap cycle scans by **`85.8%`** (**`1.50×`** faster cyclic object churn) and bounds Windows TypeScript peak working set (`~149–150 MiB`, matching Stock NG `147 MiB`).
- **100% `quickjs.h` Drop-In ABI**: Zero header or public struct ABI changes (`82,220` Test262 cases with `0` regressions; `txiki.js v26.11.0` / `BC_VERSION 29` compatible; **`96.29 KiB`** initial runtime + context heap with zero cold bloat), plus optional `quickjs-turbo.h` density controls.

### Benchmarks Across Platforms

| Same-Host Cohort | Turbo V8-v7 | `micro56` (`ns/op`) | `JetStream-17` (body) | vs Same-Host NG `0.17.0` / Bellard `2026-06-04` |
| :--- | ---: | ---: | ---: | :--- |
| **Linux `x86-64`** *(v0.17.0-turbo.3, Ryzen 3 3300X, GCC 13.3)* | **1,866** *(mono)* | **40.33 ns** *(1.015× V8!)* | **153.9 ms** *(10.1 MiB RSS)* | **1.73× / 1.39×** V8 · **1.53× / 1.45×** `micro56` · **1.56× / 1.34×** JS17 |
| **Windows `x86-64`** *(v0.17.0-turbo.3, MinGW / MSVC `/MT`)* | **1,986 / 1,942** | **43.68 / 46.73 ns** | **160.3 / 173.5 ms** | **1.90× / 2.27×** V8 · **1.63× / 1.96×** `micro56` · **1.55× / 1.66×** JS17 *(vs NG)* |
| **Linux `ARM64`** *(v0.17.0-turbo.2 Graviton2 hardware; turbo.3 QEMU verified)* | **1,259** *(8/8 wins)* | *idx 61.97 (44/57)* | **228.9 ms** *(15/17 wins)* | **1.76× / 1.48×** V8 · **1.50× / 1.46×** micro · **1.50× / 1.34×** JS17 |
| **macOS `x86-64`** *(v0.15.1-turbo.6–.8 Intel i5 hardware)* | **1,742** | *1.17× micro72* | **1.34×** vs Bellard | **1.47×** V8 vs `PORTABLE` · **1.45×** vs Bellard `-O3` |

> Notes on measurement integrity: (1) Linux `x86-64` V8-v7 is recomputed from `performance.now()` on identical iterations (eliminating WSL2 periodic wall-clock backward jumps); under monotonic timing, `v0.17.0-turbo.3` reaches **86.2%** of Node 24 `V8 --jitless` (**2.94× lower Peak RSS**), beats `V8 --jitless` on `NavierStokes` (`1.62×`), `Crypto` (`1.28×`), and `Splay` (`1.05×`), **surpasses `V8 --jitless` on `micro56`** (`40.33` vs `40.91 ns/op`, `sort_bench` `0.73` vs `0.75 sum_us`), and runs `JetStream-17` at **7.9× lower median RSS** (`10.1 MiB` vs `80.0 MiB`). (2) `micro56` separates the 56 uniform `ns/op` cases from `sort_bench` (`sum_us`); the legacy 57-case composite is reported separately as a dimensionless `micro57` index. Explore interactive charts on **[`perf-site` →](https://rowanellis-113.github.io/quickjs-turbo/)**.

### Supported Targets

| Platform | Backend | Toolchains | Notes |
| :--- | :--- | :--- | :--- |
| **Linux `x86-64`** | `LINUX_X86_64` | GCC 13/14+ (`glibc` & `musl`) | Native ELF ASM VM, inline object props, fast `dtoa`/`atod`/slice, PIE + DWARF CFI |
| **macOS `x86-64`** | `MACOS_X86_64` | Apple Clang 15+ | Native Mach-O ASM VM, PIE + DWARF CFI, `AUTO`-selected |
| **Windows `x86-64`** | `WIN_X86_64` | MSVC / `clang-cl` / MinGW | Unified native ASM VM (zero GNU binutils on MSVC) + SEH unwind |
| **Linux `ARM64`** | `LINUX_AARCH64` | GCC 13/14+ (`glibc` & `musl`) | Native ELF ASM VM (`161` native opcodes), 64B-aligned entry, `JSArena` append |
| **macOS `ARM64` & Sanitizers** | `PORTABLE` | Clang / GCC / MSVC | `AUTO` fallback + ASan / UBSan / TSan / MSan / Fuzz *(macOS ARM64 SDK is cross-compiled on Intel CI with `lipo` + consumer link checks; Apple Silicon native runtime validation pending)* |

---

## ABI Contract & Proposed Baseline JIT Roadmap

QuickJS-Turbo ships today as a **strict Zero-JIT, `0 RWX` register-frame interpreter** built on a verified **two-layer ABI contract**. That same internal ABI also provides a clean foundation for a **proposed, opt-in bytecode-driven Baseline JIT** (future roadmap; not shipped in `v0.17.0-turbo.3`).

### 1. Shipping ABI Contracts (Production Today)

- **100% Drop-In Public C ABI (`quickjs.h`)**: Upstream QuickJS-NG `0.17.0` headers, public struct layouts (`16 B JSValue`), and bytecode wire format (`BC_VERSION 29`, verified on unmodified `txiki.js v26.11.0`) remain untouched. All runtime tuning (`quickjs-turbo.h`) is strictly additive.
- **Pinned Native Register-Frame ABI**: Both `LINUX_AARCH64` (`x19` state, `x20` PC, `x21` SP, `x22` frame, `x23` locals, `x24` args, `x25` dispatch table) and `x86-64` (`LINUX_X86_64` / `MACOS_X86_64` / `WIN_X86_64`) execute over a bounded `JSFrame` segment arena, pre-validated bytecode admission (`FRAME_KIND` + jump-target `boundaries` bitmap), and **Clean/Dirty lazy stack-frame publication** at call/GC/exception safepoints.
- **Verified Binary & Unwind Hygiene**: Every internal struct offset and generated boundary is SHA-256 verified at build time (`core-fields.json` + `511` source receipts), with complete DWARF CFI FDEs (ELF/Mach-O) and Win64 SEH `.pdata`/`.xdata` unwind metadata.

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
