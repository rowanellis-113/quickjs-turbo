# ⚡ QuickJS-Turbo

[![CI](https://github.com/rowanellis-113/quickjs-turbo/actions/workflows/ci.yml/badge.svg)](https://github.com/rowanellis-113/quickjs-turbo/actions/workflows/ci.yml)
[![Test262](https://github.com/rowanellis-113/quickjs-turbo/actions/workflows/test262.yml/badge.svg)](https://github.com/rowanellis-113/quickjs-turbo/actions/workflows/test262.yml)
[![Release](https://img.shields.io/github/v/release/rowanellis-113/quickjs-turbo?include_prereleases&label=release)](https://github.com/rowanellis-113/quickjs-turbo/releases)
[![Benchmarks](https://img.shields.io/badge/benchmarks-perf--site-f59e0b)](https://rowanellis-113.github.io/quickjs-turbo/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

**Near-V8 `--jitless` speed in a QuickJS-sized binary. Zero JIT by default. 100% `quickjs.h` ABI drop-in (`txiki.js v26.11.0` aligned).**

QuickJS-Turbo supercharges [QuickJS-NG](https://github.com/quickjs-ng/quickjs) `0.17.0` with native register-frame virtual machines, adaptive inline caches, Hybrid RC + Partial Cycle GC, and specialized numeric/JSON/RegExp builtins — delivering **`1.74×–2.13×` V8-v7**, **`1.45×–1.76×` micro57**, and **`1.50×–1.55×` JetStream-17** over Stock QuickJS-NG `0.17.0` (**`1.33×–1.48×` vs Bellard 2026**) without runtime code generation or `RWX` memory.

```text
Reference Linux x86-64 Cohort (Ryzen 3 3300X, GCC 13.3, CPU2 serial, zero JIT, 2026-11-25)

V8-v7 Throughput (higher is better)
V8 --jitless (Node 24)   ████████████████████████  2,360  (463 MiB Peak RSS)
QuickJS-Turbo (0.17.0)   █████████████████████     2,045  (1.74x vs NG 0.17.0 · 1.41x vs Bellard · 86.7% of V8 --jitless · 157 MiB RSS)
Bellard QuickJS 2026     ███████████████           1,449  (147 MiB Peak RSS)
QuickJS-NG 0.17.0        ████████████              1,173  (155 MiB Peak RSS)

micro57 Geomean (57 cases, lower is better)         JetStream-17 Body Geomean (17 workloads, lower is better)
QuickJS-Turbo (0.17.0)   35.67 ns  (1.54x NG · 1.01x V8!)   V8 --jitless (Node 24)   117.6 ms  (80.0 MiB RSS)
V8 --jitless (Node 24)   35.90 ns  (21x higher RSS)         QuickJS-Turbo (0.17.0)   143.2 ms  (1.55x NG · 1.34x Bel · 10.0 MiB RSS)
Bellard QuickJS 2026     52.06 ns                           Bellard QuickJS 2026     192.2 ms
QuickJS-NG 0.17.0        54.84 ns                           QuickJS-NG 0.17.0        222.3 ms
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

- **Zero JIT by Default, `W^X` Safe**: Ahead-of-time assembly VMs use zero `RWX` memory and ship with full DWARF CFI and Win64 SEH stack unwinding for iOS, consoles, containers, and edge workers.
- **Register VM, Adaptive ICs & Fast Builtins**: Replaces the C switch loop with register-pinned assembly dispatch, adaptive Property ICs, fast `dtoa`/`atod`, and specialized RegExp/JSON workers — up to **`6.09×`** `json-stringify-inspector`, **`4.95×`** RegExp, **`4.92×`** `float_to_string`, **`3.31×`** `prop_read`, and **`2.84×`** `typed_array_read`.
- **Deterministic RC + Fewer GC Pauses**: Keeps QuickJS's immediate reference counting while generational partial cycle GC cuts full-heap cycle scans by **`86%`** (**`1.50×`** faster cyclic object churn).
- **100% `quickjs.h` Drop-In ABI**: Zero header or public struct ABI changes (`82,220` Test262 cases with `0` regressions; `txiki.js v26.11.0` / `BC_VERSION 29` compatible; `98.6 KiB` empty runtime with zero cold bloat), plus optional `quickjs-turbo.h` density controls.

### Benchmarks Across Platforms

| Same-Host Cohort | Turbo V8-v7 | `micro57` (57 cases) | `JetStream-17` (17 cases) | vs QuickJS-NG `0.17.0` / Bellard `2026-06-04` |
| :--- | ---: | ---: | ---: | :--- |
| **Linux `x86-64`** *(Ryzen 3 3300X, GCC 13.3)* | **2,045** *(2,051 Dens)* | **35.67 ns** *(1.01× V8!)* | **143.2 ms** *(10 MiB RSS)* | **1.74× / 1.41×** V8 · **1.54× / 1.46×** micro · **1.55× / 1.34×** JS17 |
| **Linux `ARM64`** *(AWS Graviton2, GCC 13.4)* | **1,259** *(8/8 wins)* | **61.97 ns** *(44/57 wins)* | **228.9 ms** *(15/17 wins)* | **1.76× / 1.48×** V8 · **1.50× / 1.46×** micro · **1.50× / 1.34×** JS17 |
| **Windows `x86-64`** *(MinGW / MSVC)* | **1,969 / 1,901** | **46.04 / 48.76 ns** | *—* | **1.83× / 2.13×** V8 vs NG · **1.37× / 1.33×** vs Bellard |
| **macOS `x86-64`** *(Intel i5, Clang 15)* | **1,742** | *1.17× micro72* | **1.34×** vs Bellard | **1.47×** V8 vs `PORTABLE` · **1.45×** vs Bellard `-O3` |

> On Linux `x86-64`, QuickJS-Turbo reaches **86.7%** of Node 24 `V8 --jitless` V8-v7 throughput (beating `V8 --jitless` on `NavierStokes`, `Crypto`, `Richards`, and `Splay` at **2.94× lower Peak RSS**), **surpasses `V8 --jitless` on `micro57` overall** (`35.67 ns` vs `35.90 ns`, `21×` lower RSS), and runs **JetStream-17 at `8.0×` lower RSS** (`10.0 MiB` vs `80.0 MiB`), beating `V8 --jitless` on `lazy-collections`, `crypto`, `json-stringify-inspector`, `json-parse-inspector`, and `richards`. Explore interactive charts on **[`perf-site` →](https://rowanellis-113.github.io/quickjs-turbo/)**.

### Supported Targets

| Platform | Backend | Toolchains | Notes |
| :--- | :--- | :--- | :--- |
| **Linux `x86-64`** | `LINUX_X86_64` | GCC 13/14+ (`glibc` & `musl`) | Native ELF ASM VM, inline object props, PIE + DWARF CFI |
| **macOS `x86-64`** | `MACOS_X86_64` | Apple Clang 15+ | Native Mach-O ASM VM, PIE + DWARF CFI, `AUTO`-selected |
| **Windows `x86-64`** | `WIN_X86_64` | MSVC / `clang-cl` / MinGW | Unified native ASM VM (zero GNU binutils on MSVC) + SEH unwind |
| **Linux `ARM64`** | `LINUX_AARCH64` | GCC 13/14+ (`glibc` & `musl`) | Native ELF ASM VM (`161` native opcodes), 64B-aligned entry, `JSArena` append |
| **macOS `ARM64` & Sanitizers** | `PORTABLE` | Clang / GCC / MSVC | Automatic `AUTO` fallback + ASan / UBSan / TSan / MSan / Fuzz |

---

## ABI Contract & Baseline JIT Architecture

QuickJS-Turbo is engineered around a strict **two-layer ABI contract** — preserving 100% drop-in compatibility for embedders today while providing the exact runtime substrate required for an **optional, bytecode-driven Baseline JIT** without rewriting QuickJS's frontend or introducing an AST.

### 1. Public & Internal ABI Contracts

- **100% Drop-In Public C ABI (`quickjs.h`)**: Upstream QuickJS-NG `0.17.0` headers, public struct layouts, and bytecode wire format (`BC_VERSION 29`, verified on unmodified `txiki.js v26.11.0`) remain untouched. All runtime tuning (`quickjs-turbo.h`) is strictly additive.
- **Pinned Native Register-Frame ABI**: Both `LINUX_AARCH64` (`x19` state, `x20` PC, `x21` SP, `x22` frame, `x23` locals, `x24` args, `x25` dispatch table) and `x86-64` (`LINUX_X86_64` / `MACOS_X86_64` / `WIN_X86_64`) share a bounded `JSFrame` segment arena, pre-validated bytecode admission (`FRAME_KIND` + jump-target `boundaries` bitmap), and **Clean/Dirty lazy stack-frame publication** at call/GC/exception safepoints.
- **Verified Binary & Unwind Hygiene**: Every internal struct offset and generated boundary is SHA-256 verified at build time (`core-fields.json` + `511` source receipts), with complete DWARF CFI FDEs (ELF/Mach-O) and Win64 SEH `.pdata`/`.xdata` unwind metadata.

### 2. Optional Bytecode-Driven Baseline JIT (Architecture Direction)

Hardware profiling (`perf` on Graviton2 & x86-64) confirms that the native ASM interpreter is near the physical limit of pure interpretation: `JS_FrameInterp` still accounts for **53%–98%** of execution cycles due to indirect dispatch, operand decoding, and `[sp]` stack traffic. Because QuickJS-Turbo's ABI already solves ~70% of a Baseline JIT's runtime problem, an opt-in Baseline JIT tier can layer cleanly on top:

```text
JSFunctionBytecode (No AST!)
   │  Single-pass linear scan reusing FRAME_KIND & jump-target boundaries bitmap
   ▼
1-Pass Virtual Operand Stack (2–4 reg TOS cache) + Copy-and-Patch Stencils
   │  Eliminates indirect dispatch, bytecode fetch/decode, PC updates, and [sp] ping-pong
   ▼
Shared Register-Frame ABI (Zero-Bridge Interop with Native ASM VM)
   ├─ Direct-Baked Property ICs (PC/RIP-relative IC slot pointers, no pc-table lookup)
   ├─ Monomorphic Call IC + Loop OSR ({pc_offset -> jit_loop_entry})
   └─ Clean/Dirty Bailout Stubs (materializes constant pc -> reuses existing C/ASM slow paths)
   ▼
Strict W^X Code Arena (RW -> RX, never simultaneous RWX · Hotness-gated -> 0 B cold bloat)
```

- **Zero AST Required**: Compiles directly from `JSFunctionBytecode` (like V8 Sparkplug, JSC Baseline, and CPython Copy-and-Patch). Scopes, closures (`JSVarRef`), TDZ, and `try/catch` tables are already lowered in bytecode, preserving the **`98.6 KiB`** empty-worker heap and sub-ms parse speed.
- **Zero-Bridge ABI Sharing & Strict `W^X` Opt-In**: Compiled code shares the exact `JSFrame` layout, register conventions, and Hybrid RC + Partial Cycle GC with the native ASM VM, allowing seamless JIT ↔ Interpreter calls and Loop OSR. The default production build remains **`0 RWX` / Zero JIT**; Baseline JIT is designed as a compile- and runtime-gated opt-in tier for environments that permit `W^X` (`RW → RX`) code pages.

See **[ABI-AND-BASELINE-JIT.txt](vm/docs/architecture/common/ABI-AND-BASELINE-JIT.txt)** for the full register contract, Copy-and-Patch design, and phased stopping criteria (`Phase 0` → `Phase 2`).

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
