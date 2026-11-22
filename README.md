# ⚡ QuickJS-Turbo

[![CI](https://github.com/rowanellis-113/quickjs-turbo/actions/workflows/ci.yml/badge.svg)](https://github.com/rowanellis-113/quickjs-turbo/actions/workflows/ci.yml)
[![Test262](https://github.com/rowanellis-113/quickjs-turbo/actions/workflows/test262.yml/badge.svg)](https://github.com/rowanellis-113/quickjs-turbo/actions/workflows/test262.yml)
[![Release](https://img.shields.io/github/v/release/rowanellis-113/quickjs-turbo?include_prereleases&label=release)](https://github.com/rowanellis-113/quickjs-turbo/releases)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

**Near-V8 `--jitless` speed in a QuickJS-sized binary. Zero JIT. 100% `quickjs.h` drop-in.**

QuickJS-Turbo supercharges [QuickJS-NG](https://github.com/quickjs-ng/quickjs) with native register-frame virtual machines, adaptive inline caches, and specialized builtins — delivering **~2× the throughput** without runtime code generation or `RWX` memory.

```text
V8-v7 Throughput (Linux x86-64, single-core, no JIT)

V8 --jitless (Node 24)   ████████████████████████  2,375
QuickJS-Turbo            █████████████████████     2,072  (2.08x vs QuickJS-NG · 87% of V8 --jitless)
Bellard QuickJS 2026     ███████████████           1,466
QuickJS-NG 0.15.1        ██████████                  994
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

- **Fast Where JITs Are Banned**: Strict `W^X` compliance (zero executable heap pages) with full DWARF CFI / Win64 SEH unwind support — ready for iOS, consoles, locked-down containers, CLI tools, and edge workers.
- **Up to 6.7× Faster on Hot Workloads**: Native register dispatch + inline caches deliver **`6.73×` RegExp**, **`6.40×` `JSON.stringify`**, **`5.74×` array writes**, and **`2.84×` property reads** over stock QuickJS-NG `0.15.1`.
- **Cross-Platform Object, Collection & Async Fast Paths**: Shared literal capacity reservation (**`2.98–3.49×`** on 5-field object literals), unified `Map`/`Set` string-key hashing + short-rope flattening (**`2.12–3.52×`** flat / **`1.58–2.52×`** rope lookups), capability-free ordinary `async` / `Promise.resolve` primitives (**`1.39–1.47×`**), and co-allocated inline object properties on Linux `x86-64` & `ARM64` (**`+2.38%`** V8-v7 / **`+8.79%`** Splay / **`-4.09%`** peak RSS on Linux `x86-64`).
- **Hybrid RC + Generational Partial Cycle GC**: Preserves deterministic immediate reference counting while cutting full-heap trial-deletion scans by ~86% (**`1.50×` faster cyclic garbage churn** / `-33.6%` time), accelerating string slices by **`~10–11%`** and deep-tree reclamation by **`7.4%`** with zero RSS bloat.
- **High-Density Memory Control (`quickjs-turbo.h`)**: Decouple `own_bytecode` tail copies (`own_bytecode_tail = QJS_TURBO_OFF`) while keeping native assembly Property ICs active, lazily allocate IC slabs via low-bit tagged warmup (`property_ic_warmup`, default `0`, `+0` bytes on `JSFunctionBytecode`, `-1` branch on x86-64 hot path), and reclaim idle worker IC slabs on demand with `JS_PurgePropertyIC(rt)`.
- **First-Class C API & CMake Embedding (`quickjs-turbo::qjs`)**: Configure per-process and per-runtime options programmatically (`QJS_SetTurboDefaults`, `JS_SetRuntimeTurboOptions`, `QJS_GetTurboInfo`) without `getenv()`/`constructor` races. `quickjs-turbo::qjs` isolates native ASM/bridge units locally (`-fno-lto` / `/GL-`) so host LTO stays enabled, automatically falls back to `PORTABLE` under ASan/UBSan/TSan/MSan/Fuzz in `AUTO` mode, supports `QJS_USE_PREGEN_ASM=ON` offline builds without Python, and works directly via `add_subdirectory()`.
- **True Drop-In Compatibility**: Unmodified `quickjs.h` C API/ABI. Validated on every commit against **`81,152` Test262 cases** (`0` regressions, **`31` upstream bugs fixed**).
- **Cross-Platform Native Speed**: Dedicated assembly VMs for **Linux `x86-64`** (`2.08×` V8-v7), **macOS `x86-64`** (`MACOS_X86_64`, Mach-O / Apple Clang, `1.45×` V8-v7 & `1.34×` JetStream 3.0 over Bellard QuickJS `2026`), **Windows `x86-64`** (both source-level `WIN_X86_64` for MSVC / `clang-cl` with zero GNU binutils and `WIN64` MSVC/MinGW, `1.94×` V8-v7), and **Linux `ARM64`** (`glibc` & `musl`, `1.50×` over Bellard QuickJS `2026` on Graviton2, 64-byte aligned VM entry), plus an automatic `PORTABLE` C fallback for macOS `ARM64` and instrumented builds.

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
# Windows x86-64 (MSVC / clang-cl native ASM VM, zero GNU binutils required)
cmake -S vm -B build/win-x86_64 -G Ninja -DCMAKE_BUILD_TYPE=Release -DQJS_FRAME_BACKEND=AUTO -DQJS_PROPERTY_IC=ON
cmake --build build/win-x86_64 --parallel

# Or legacy COFF-adapted Win64 product wrapper (MSVC or MinGW)
./vm/tools/x86/win64/build/build-baseline.ps1 -Toolchain msvc -Backend WIN64 -Test
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

All QuickJS-Turbo optimizations live cleanly inside [`vm/`](vm/), keeping upstream QuickJS-NG `0.15.1` byte-for-byte pristine at the repository root for effortless upstream tracking and side-by-side A/B benchmarking.

- **[Build, Static CRT & Embedding Guide](vm/docs/architecture/common/BUILDING.txt)**
- **[Benchmark Suites & Methodology](vm/docs/architecture/common/PRODUCT-BASELINE.txt)** · **[x86-64 Report](vm/docs/architecture/x86/linux/LINUX-FINAL-REVIEW.txt)** · **[ARM64 Report](vm/docs/architecture/arm64/LINUX-AARCH64-HARDWARE.txt)**
- **[Optimization Deep Dive](vm/docs/architecture/common/OPTIMIZATIONS.txt)** · **[Hybrid RC & Cycle GC](vm/docs/architecture/common/HYBRID-GC.txt)** · **[Contributor & Measurement Policy](vm/AGENTS.md)**

---

## License

MIT — see [`LICENSE`](LICENSE) and [`vm/THIRD_PARTY_NOTICES.txt`](vm/THIRD_PARTY_NOTICES.txt). Built on the shoulders of **Fabrice Bellard**, **Charlie Gordon**, and the **[QuickJS-NG](https://github.com/quickjs-ng/quickjs)** maintainers.
