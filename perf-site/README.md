# QuickJS-Turbo Performance & Landing Site (`perf-site`)

Static, zero-build landing page and historical benchmark archive for **QuickJS-Turbo**.

## Local Preview

```sh
python3 -m http.server 8080 --directory perf-site
# Open http://localhost:8080
```

## Updating Benchmark History for a New Release

All historical release snapshots and cross-platform benchmark cohorts live in [`data/benchmarks.json`](data/benchmarks.json):

1. Update `"updatedAt"` and `"latestVersion"`.
2. Append a new object to `"versionHistory"` with the measured Linux x86-64 V8-v7 score, Peak RSS, 8 subtests, and release highlights — keep prior entries intact so the historical trajectory stays complete.
3. Update any refreshed platform cohort under `"platforms"` while keeping each platform's hardware, toolchain, and comparison baseline explicitly labeled.

## Deployment

Pushing changes under `perf-site/**` to `main` automatically deploys to GitHub Pages via [`.github/workflows/pages.yml`](../.github/workflows/pages.yml).
