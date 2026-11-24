# ⚡ QuickJS-Turbo

[![CI](https://github.com/rowanellis-113/quickjs-turbo/actions/workflows/ci.yml/badge.svg)](https://github.com/rowanellis-113/quickjs-turbo/actions/workflows/ci.yml)
[![Test262](https://github.com/rowanellis-113/quickjs-turbo/actions/workflows/test262.yml/badge.svg)](https://github.com/rowanellis-113/quickjs-turbo/actions/workflows/test262.yml)
[![Release](https://img.shields.io/github/v/release/rowanellis-113/quickjs-turbo?include_prereleases&label=release)](https://github.com/rowanellis-113/quickjs-turbo/releases)
[![Benchmarks](https://img.shields.io/badge/benchmarks-perf--site-f59e0b)](https://rowanellis-113.github.io/quickjs-turbo/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

**Near-V8 `--jitless` speed in a QuickJS-sized binary. Zero JIT. 100% `quickjs.h` drop-in (`txiki.js v26.11.0` aligned).**

QuickJS-Turbo supercharges [QuickJS-NG](https://github.com/quickjs-ng/quickjs) `0.17.0` with native register-frame virtual machines, adaptive inline caches, Hybrid RC + Partial Cycle GC, and specialized builtins — delivering **`1.72×–2.13×` the V8-v7 throughput of QuickJS-NG `0.17.0`** (**`1.33×–1.49×` vs Bellard 2026**) without runtime code generation or `RWX` memory.

```text
V8-v7 Throughput (Reference Linux x86-64 host, single-core, zero JIT)

V8 --jitless (Node 24)   ████████████████████████  2,401  (465 MiB Peak RSS)
QuickJS-Turbo (0.17.0)   █████████████████████     2,077  (1.72x vs NG 0.17.0 · 1.39x vs Bellard · 86.5% of V8 --jitless · 157 MiB RSS)
Bellard QuickJS 2026     ███████████████           1,496  (147 MiB Peak RSS)
QuickJS-NG 0.17.0        ████████████              1,208  (155 MiB Peak RSS)
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

- **Zero JIT, `W^X` Safe**: Ahead-of-time assembly VMs use zero `RWX` memory and include full DWARF CFI and Win64 SEH stack unwinding for iOS, consoles, containers, and edge workers.
- **Register VM & Inline Caches**: Replaces the C interpreter loop with register-pinned assembly dispatch, adaptive Property ICs, and fast builtins — up to **`5.17×`** faster RegExp, **`3.40×`** property reads, and **`2.88×`** TypedArray reads.
- **Deterministic RC + Fewer GC Pauses**: Keeps QuickJS's immediate reference counting while generational partial cycle GC cuts full-heap cycle scans by **`86%`** (**`1.50×`** faster cyclic object churn).
- **100% `quickjs.h` Drop-In**: Zero header or ABI changes (`82,220` Test262 cases with `0` regressions; `txiki.js v26.11.0` compatible), plus optional `quickjs-turbo.h` controls that cut cold-worker heap by **`33.8%`**.

### Benchmarks Across Platforms

| Same-Host Cohort | Turbo V8-v7 | vs QuickJS-NG `0.17.0` | vs Bellard `2026-06-04` |
| :--- | ---: | :--- | :--- |
| **Linux `x86-64`** *(Ryzen 3 3300X, GCC 13)* | **2,077** | **1.72×** V8-v7 · **1.42×** micro | **1.39×** V8-v7 · **1.35×** micro |
| **Linux `ARM64`** *(AWS Graviton2, GCC 13)* | **1,260** | **1.76×** V8-v7 · **1.42×** micro | **1.49×** V8-v7 · **1.37×** micro |
| **Windows `x86-64`** *(MinGW / MSVC)* | **1,969 / 1,901** | **1.83× / 2.13×** V8-v7 · **1.45× / 1.76×** micro | **1.37× / 1.33×** V8-v7 · **1.34× / 1.27×** micro |
| **macOS `x86-64`** *(Intel i5, Clang 15)* | **1,742** | **1.47×** vs `PORTABLE` | **1.45×** V8-v7 · **1.34×** JetStream |

> On Linux `x86-64`, QuickJS-Turbo reaches **86.5%** of Node 24 `V8 --jitless` V8-v7 throughput (**93.0%** on microbenchmarks, beating V8 `--jitless` on TypedArrays, dense arrays, `NavierStokes`, and `Crypto`) at **2.96× lower Peak RSS** (`157 MiB` vs `465 MiB`). Explore interactive subtest & release charts on **[`perf-site` →](https://rowanellis-113.github.io/quickjs-turbo/)**.

### Supported Targets

| Platform | Backend | Toolchains | Notes |
| :--- | :--- | :--- | :--- |
| **Linux `x86-64`** | `LINUX_X86_64` | GCC 13/14+ (`glibc` & `musl`) | Native ELF ASM VM, inline object props, PIE + DWARF CFI |
| **macOS `x86-64`** | `MACOS_X86_64` | Apple Clang 15+ | Native Mach-O ASM VM, PIE + DWARF CFI, `AUTO`-selected |
| **Windows `x86-64`** | `WIN_X86_64` | MSVC / `clang-cl` / MinGW | Unified native ASM VM (zero GNU binutils on MSVC) + SEH unwind |
| **Linux `ARM64`** | `LINUX_AARCH64` | GCC 13/14+ (`glibc` & `musl`) | Native ELF ASM VM, 64B-aligned entry, `JSArena` string append |
| **macOS `ARM64` & Sanitizers** | `PORTABLE` | Clang / GCC / MSVC | Automatic `AUTO` fallback + ASan / UBSan / TSan / MSan / Fuzz |

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

- **[Documentation Index](vm/docs/architecture/common/README.txt)** · **[Build, Static CRT & Embedding Guide](vm/docs/architecture/common/BUILDING.txt)**
- **[Benchmark Baselines](vm/docs/architecture/common/PRODUCT-BASELINE.txt)** · **[Linux x86-64](vm/docs/architecture/x86/linux/LINUX-FINAL-REVIEW.txt)** · **[Windows x86-64](vm/docs/architecture/x86/win64/WIN-X86-64.txt)** · **[macOS x86-64](vm/docs/architecture/x86/macos/MACOS-X86-64.txt)** · **[Linux ARM64](vm/docs/architecture/arm64/LINUX-AARCH64-HARDWARE.txt)**
- **[Optimization Deep Dive](vm/docs/architecture/common/OPTIMIZATIONS.txt)** · **[Hybrid RC & Cycle GC](vm/docs/architecture/common/HYBRID-GC.txt)** · **[Contributor & Measurement Policy](vm/AGENTS.md)**

---

## License

MIT — see [`LICENSE`](LICENSE) and [`vm/THIRD_PARTY_NOTICES.txt`](vm/THIRD_PARTY_NOTICES.txt). Built on the shoulders of **Fabrice Bellard**, **Charlie Gordon**, and the **[QuickJS-NG](https://github.com/quickjs-ng/quickjs)** maintainers.
