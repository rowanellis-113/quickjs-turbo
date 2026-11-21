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
- **True Drop-In Compatibility**: Unmodified `quickjs.h` C API/ABI. Validated on every commit against **`81,152` Test262 cases** (`0` regressions, **`31` upstream bugs fixed**).
- **Cross-Platform Native Speed**: Dedicated assembly VMs for **Linux `x86-64`** (`2.08×` V8-v7), **Windows `x86-64`** (`MSVC` & `MinGW`, `1.94×` V8-v7), and **Linux `ARM64`** (`1.50×` over Bellard QuickJS `2026` on Graviton2, 64-byte aligned VM entry), plus an automatic `PORTABLE` C fallback for macOS and other targets.

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

# macOS / Portable C
cmake -S vm -B build/portable -G Ninja -DCMAKE_BUILD_TYPE=Release && cmake --build build/portable
```

```powershell
# Windows x86-64 (MSVC or MinGW)
./vm/tools/x86/win64/build/build-baseline.ps1 -Toolchain msvc -Backend WIN64 -Test
```

Link into any C/C++ CMake project with `find_package(qjs CONFIG REQUIRED)` and `target_link_libraries(app PRIVATE qjs::qjs)`.

---

## Architecture & Docs

All QuickJS-Turbo optimizations live cleanly inside [`vm/`](vm/), keeping upstream QuickJS-NG `0.15.1` byte-for-byte pristine at the repository root for effortless upstream tracking and side-by-side A/B benchmarking.

- **[Build, Static CRT & Embedding Guide](vm/docs/architecture/common/BUILDING.txt)**
- **[Benchmark Suites & Methodology](vm/docs/architecture/common/PRODUCT-BASELINE.txt)** · **[x86-64 Report](vm/docs/architecture/x86/linux/LINUX-FINAL-REVIEW.txt)** · **[ARM64 Report](vm/docs/architecture/arm64/LINUX-AARCH64-HARDWARE.txt)**
- **[Optimization Deep Dive](vm/docs/architecture/common/OPTIMIZATIONS.txt)** · **[Hybrid RC & Cycle GC](vm/docs/architecture/common/HYBRID-GC.txt)** · **[Contributor & Measurement Policy](vm/AGENTS.md)**

---

## License

MIT — see [`LICENSE`](LICENSE) and [`vm/THIRD_PARTY_NOTICES.txt`](vm/THIRD_PARTY_NOTICES.txt). Built on the shoulders of **Fabrice Bellard**, **Charlie Gordon**, and the **[QuickJS-NG](https://github.com/quickjs-ng/quickjs)** maintainers.
