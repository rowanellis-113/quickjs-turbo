# QuickJS-Turbo Performance & Landing Site (`perf-site`)

Static, zero-build landing page and historical benchmark archive for **QuickJS-Turbo**.

## Local Preview

```sh
python3 -m http.server 8080 --directory perf-site
# Open http://localhost:8080
```

## Updating Benchmark History for a New Release

All architectural milestone snapshots and cross-platform benchmark cohorts live in [`data/benchmarks.json`](data/benchmarks.json):

1. Update `"updatedAt"` and `"latestVersion"`.
2. Keep `"versionHistory"` concise and milestone-driven:
   - Append a new entry **only** when a release introduces a measurable V8-v7 architectural milestone on the Linux x86-64 reference cohort.
   - For embedding, density, portability, or maintenance releases that preserve the existing throughput plateau (such as `v0.15.1-turbo.5` through `v0.15.1-turbo.8`), update the latest milestone range (e.g. `v0.15.1-turbo.4 → .8`) and its highlights rather than appending flat duplicate dots.
3. Update any refreshed platform cohort under `"platforms"` while keeping each platform's hardware, toolchain, and comparison baseline explicitly labeled.

## Deployment

Pushing changes under `perf-site/**` to `main` automatically deploys to GitHub Pages via [`.github/workflows/pages.yml`](../.github/workflows/pages.yml).
