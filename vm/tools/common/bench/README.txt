JetStream 3.0: ten application workloads in QuickJS shells
=========================================================

Source: https://github.com/WebKit/JetStream
Pinned branch snapshot: 06785cf861ac44855f168cbbe829278c2802e6de
jetstream10.json fixes the selection, original file hashes and rationale.
The workload sources are not copied into the engine repository or rewritten.

The subset covers Air, DeltaBlue, Babylon, CDJS, FlightPlanner,
OfflineAssembler, PDF.js, Octane TypeScript, RSA Crypto and Richards.
Basic was replaced solely because its RegExp legacy statics are unavailable
in all ten reference images. Preserve that compatibility failure separately;
never replace a workload based on its performance result.

Fetch the corpus outside the product source tree. This Windows cohort pins
CRLF text checkout bytes; compressed .z data stays binary. Reproduce those
bytes explicitly so the same manifest also works on another host:
  git -c core.autocrlf=true clone --filter=blob:none --sparse --branch JetStream3.0 https://github.com/WebKit/JetStream.git /path/to/JetStream
  git -C /path/to/JetStream config core.autocrlf true
  git -C /path/to/JetStream fetch --depth 1 origin 06785cf861ac44855f168cbbe829278c2802e6de
  git -C /path/to/JetStream checkout --detach 06785cf861ac44855f168cbbe829278c2802e6de
  git -C /path/to/JetStream sparse-checkout set ARES-6 cdjs Octane RexBench

Python 3 uses only its standard library. Supply an image manifest:
  {"images":[{"name":"native-b2","toolchain":"default","path":"/path/to/qjs.exe",
    "sha256":"<actual SHA256>","environment":{"QJS_EXPERIMENT_ALLOCATOR":"256"}}]}
Add original and previous images with an empty environment. Inherited QJS_*
controls are removed, then only each declared image environment is applied.
For shells that need DLLs outside their executable directory, add an explicit
"runtime_paths": ["C:/path/to/toolchain/bin"] to that image. These must be
existing absolute directories; no developer-machine paths are injected.
"required_modules": ["libwinpthread-1.dll"] optionally asserts required loaded
DLLs. CRT names are toolchain-specific; do not assume MSVCRT for a UCRT build.
The extra runner also requires "engine": "quickjs-ng" (or the documented
reference engine name) in each image. These runners use Windows process APIs.

  python -B tools/common/bench/jetstream10.py prepare --corpus /path/to/JetStream --output /path/to/results
  python -B tools/common/bench/jetstream10.py quick --corpus /path/to/JetStream --output /path/to/results --images /path/to/images.json
  python -B tools/common/bench/jetstream10.py stable --corpus /path/to/JetStream --output /path/to/results --images /path/to/images.json --rounds 2

Use --cases and --only-images for explicitly recorded focused cohorts.
Quick measures one whole original runIteration. Stable reports one cold
iteration, then two timed iterations after that warmup; process samples are
repeated in reversed order. Workload sizes and internal loop counts remain
unchanged. Loading, cold execution and warm execution are separate metrics.
On Windows all timed child processes use logical CPU 2, one at a time.
Images, source inputs, adapters, commands, environment, raw logs and every
sample are recorded. Corpus or executable hash mismatches stop the run.

The shell adapter only supplies file loading, timing, preloaded strings and
the upstream deterministic random generator. It calls original init,
prepareForNextIteration, runIteration and validate methods. Native assertions
remain enabled. Babylon additionally checks AST structure outside timing.
TypeScript here is the historical Octane compiler/typecheck/emit workload,
distinct from the modern TypeScript 5.9.3 transpileModule library benchmark.

These are custom subset timings, not official JetStream scores. The browser
driver's startup/worst-case aggregation and full default iteration counts
are not reproduced. Do not compare these numbers to browserbench.org scores
or interpret them as full Capsid throughput. Keep exceptionally long tasks
separate rather than hiding their sample count or inflating an aggregate.

Additional eight workloads (2026-11-05)
=====================================
jetstream-extra8.json pins eight additional cases at the SAME corpus revision:
json-parse-inspector, json-stringify-inspector, acorn-wtb, prettier-wtb,
async-fs, lazy-collections, js-tokens, bigint-noble-ed25519.
Extend the existing sparse checkout with:
  git -C /path/to/JetStream sparse-checkout add SeaMonster bigint generators web-tooling-benchmark

The original source bodies, internal work sizes, prepare/reset ordering, and
native assertions are unchanged. Text checkout bytes are pinned as before;
compressed inputs are decompressed losslessly before measurement. The WTB
preload includes its upstream unused source-map Wasm bytes, but neither Acorn
nor Prettier executes WebAssembly. Noble uses the SAME upstream JavaScript
WebCrypto implementation in every engine, including Node.

The Windows-only extra runner accepts QuickJS-NG, Bellard QuickJS, JSC and
Node image records with name, engine, path, sha256, arguments, environment,
modules_and_symbols and (for native products) toolchain fields. The supported
engine names are quickjs-ng, quickjs-bellard, jsc and node. Use --jitless for
Node and disable all JS/RegExp JIT tiers for the LLInt comparison.

  python -B tools/common/bench/jetstream-extra.py compatibility --corpus /path/to/JetStream --output /path/to/extra-results --images /path/to/images.json
  python -B tools/common/bench/jetstream-extra.py bench --corpus /path/to/JetStream --output /path/to/extra-results --images /path/to/images.json --proof /path/to/compatibility-.../RESULTS.json --iterations 12

Compatibility runs one whole iteration and validates every selected image.
Bench requires the successful matching compatibility report: identical cases,
images, host scripts and input hashes. It runs two exactly reversed blocks;
each child gets one cold iteration, one further warmup, then the requested
number of measured full iterations. Selection is fixed before seeing times.
All roles of the same engine use the same per-case host path and identical
host bytes within a cohort, with a common working directory. This also fixes
the script filename metadata and scriptArgs rather than varying them by role.
The first 2026-11-05 extra-eight baseline used per-role host paths; retain it
as historical evidence and establish a new cohort after this harness change.
The parent observes the actual PID, loaded modules/hashes and CPU2 affinity
at READY/GO. Standard input is used only outside measured intervals. Timed
execution must not overlap builds or the product-only disk cleanup.

Primary time is mean runIteration body time, excluding prepare/reset; the
complete warm cycle including prepare and awaits is recorded separately.
Load time includes host file loading, compilation and evaluation; init and
cold time are separate. No official JetStream score or population tail-latency
claim is made from this small cohort. Do not merge it with old-path timings.
Windows peak working set and private usage are observed after measured work,
before supplemental validation; they include startup/load/cold/warmup costs
and are not interchangeable with the engine's allocator/live-heap counters.

After timing: JSON round trips and two independent 32-bit UTF-16 fingerprints,
Acorn token/AST counts, Prettier output lengths/fingerprints, and native
generator/filesystem checks are compared across engines. Noble's unchanged
bundle is re-evaluated outside timing to expose its module API, then Ed25519
RFC 8032 section 7.1 TEST 1 and rejection of a modified message are checked:
  https://www.rfc-editor.org/rfc/rfc8032.html#section-7.1
These are bounded checks, not exhaustive correctness qualification. All
incompatibilities and failed attempts remain in the output directory.


Linux native and explicit Cross-Target runners
========================================
linux-selected.py uses the retained external JetStream17 and original V8-v7
harnesses. The engine source is not a corpus bundle. Copy the qualified
comparisons/jetstream17,comparisons/bench-v8 harness directories and the pinned
JetStream Git checkout to the test host without changing their recorded bytes.
The loader verifies each declared corpus hash before running the original body.

Use a JSON array of engines,with existing absolute binary paths:
  [{"name":"arm-native","binary":"/absolute/sdk/bin/qjs",
    "sha256":"<actual SHA256>","guest_machine":183,
    "arguments":["--stack-size","2048k"],
    "env":{"QJS_EXPERIMENT_ALLOCATOR":"256"}}]
On a real Linux 64-bit target host,omit runner. To execute that same ELF on an host-64
Linux host,add an explicit argv list:
  "runner":["/usr/bin/qemu-target","-cpu","cortex-a53","-L","/usr/target-linux-gnu"]
The target ELF and runner are hashed separately. The READY/GO observer verifies
the actual process image,CPU and PID role. Kernel ASLR and host platform are
recorded. An explicit engine hash mismatch fails before execution.

First validate all17 original JetStream bodies across the selected images:
  python3 -B tools/common/bench/linux-selected.py jetstream compatibility --harness /absolute/comparisons/jetstream17 --corpus /absolute/JetStream --engines /absolute/engines.json --output /absolute/results/compatibility
Original supplemental fingerprints,AST/token counts,JSON,generator andcrypto
checks must match. The historically excluded OfflineAssembler remains excluded.
The selection is independent of timing results;--cases is an explicit subset.

Quick timing uses one block,before spending time on a reversed pair:
  python3 -B tools/common/bench/linux-selected.py jetstream bench --harness /absolute/comparisons/jetstream17 --corpus /absolute/JetStream --engines /absolute/engines.json --proof /absolute/results/compatibility/RESULT.json --output /absolute/results/quick --iterations 1 --blocks 1
  python3 -B tools/common/bench/linux-selected.py v8 bench --harness /absolute/comparisons/bench-v8 --engines /absolute/engines.json --output /absolute/results/v8-quick --blocks 1
V8-v7 retains its original eight-case calibration,assertions andaggregate score.
For stable native measurement,use --blocks 2 (the unchanged default),which
reverses case/engine order exactly. JetStream --iterations controls complete
original iterations;it never shrinks the workload. V8 ignores that option and
keeps its own calibration. Fresh result directories retain all modes/attempts.

Default affinity is CPU2. --cpu explicitly selects another allowed CPU when a
target's cpuset orsmall board lacks CPU2;use the same CPU throughout a cohort.
--timeout bounds each process. Failure returns nonzero andkills the owned
process group,including GNU time andthe emulator,to avoid orphaned workloads.

Emulated elapsed times/scores include QEMU/TCG. Memory fields are explicitly
host_emulator_* andinclude emulator state;they are not guest-only engine RSS.
Do not use those rows as physical target speed,memory or PMU results. Native and
emulated processes can validate equal outputs,but their times cannot establish
cross-ISA hardware parity. Keep the quick filter andstable results separate.

Ctrl-C also reaps the owned benchmark process group before interruption exits.
Repeat uncertain/noisy native cohorts;two reversed blocks alone do not establish statistical significance.
