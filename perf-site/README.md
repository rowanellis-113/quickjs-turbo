# QuickJS-Turbo Performance & Landing Site (`perf-site`)

Static, zero-build landing page, ABI/JIT architecture overview, and historical benchmark archive for **QuickJS-Turbo**.

## Local Preview

```sh
python3 -m http.server 8080 --directory perf-site
# Open http://localhost:8080
```

## Updating Benchmark History for a New Release

All architectural milestone snapshots and cross-platform benchmark cohorts live in [`data/benchmarks.json`](data/benchmarks.json):

1. Update `"updatedAt"`, `"latestVersion"`, and `"upstream"`.
2. Keep `"versionHistory"` concise and milestone-driven:
   - Append a new entry **only** when a release introduces a measurable V8-v7 architectural milestone or upstream rebase (e.g. `v0.17.0-turbo.1`).
   - Set `"baselineVersion"` (`"0.15.1"` or `"0.17.0"`), `"baselineV8Score"`, and `"baselineSubtests"` when comparing against a new pinned upstream release so chart ratios stay apples-to-apples.
3. Update refreshed platform cohorts under `"platforms"` (including optional per-platform `"jetstream17"` workload breakdowns rendered dynamically by [`app.js`](app.js)) while keeping each platform's hardware, toolchain, and comparison baseline explicitly labeled.
4. Keep the `#abi-jit` section in [`index.html`](index.html) synchronized with [`vm/docs/architecture/common/ABI-AND-BASELINE-JIT.txt`](../vm/docs/architecture/common/ABI-AND-BASELINE-JIT.txt).

## Deployment

Pushing changes under `perf-site/**` to `main` automatically deploys to GitHub Pages via [`.github/workflows/pages.yml`](../.github/workflows/pages.yml).
