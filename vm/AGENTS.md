<!-- UTF-8. PowerShell: Get-Content -LiteralPath AGENTS.md -Encoding UTF8 -->
# QuickJS-NG engineering guide

Upstream QuickJS-NG 0.15.1 at the revision in
`vm/cmake/QuickJSUpstreamPin.cmake` remains untouched outside `vm/`. Keep those
upstream files byte-for-byte unmodified at the repository root. Preserve
existing notices and consolidate all product changes inside `vm/`.

## Source and build ownership

- Product builds invoke CMake with `-S vm`; common implementation belongs under
  `vm/src/`; platform-specific C and assembly belong under their architecture,
  operating system and compiler directories (`vm/src/{arm64,x86}/`,
  `vm/asm/{arm64,x86}/`).
- Source and generator catalogues, backend hashes, ABI declarations and native
  inputs are part of the build contract. Update and verify them with changes.
- Native Win64 supports MSVC and MinGW; native Linux x86-64 supports GCC 13+.
  Linux uses measured SysV/ELF contracts. `PORTABLE` is the fallback; `AUTO`
  selects a supported backend without making unsupported platforms fail.
- Use fresh build directories for compiler or generator changes. Native epochs,
  generated checks, COFF relocation handling and unwind validation are required.
- The interpreter is sensitive to function and section layout. Do not assume a
  source-level cleanup is performance neutral: inspect the linked code and test.

## Measurement and profile

- Bind the source revision, dirty state, toolchain, flags, workload and binary
  hashes before measurements. Use serial runs on CPU 2 (affinity mask 4), one
  build job and normal ASLR; do not rely on PGO or address tuning to hide costs.
- Run a quick paired benchmark first. Only extend promising or concerning cases
  to stable, interleaved measurements. Keep raw samples and negative results.
- Compare the current candidate with both the accepted product and the stock
  upstream engine. Report elapsed time and throughput separately. The added
  cost relative to stock is `(candidate time - prior time) / stock time`; use
  that cost, the product benefit and noise when deciding whether to accept it.
- Inspect actual loaded binaries, function bounds, executable sections and
  unwind data. Use matching symbols with AMD uProf, WPR/WPA or xperf to attribute
  real samples before changing a hot path. Do not infer causality from a single
  benchmark or compare results from different corpus or measurement settings.
- Track memory/working set and allocation as well as speed when a change can
  affect them. Preserve known performance history outside the product tree.

For paired timing, use the same immutable workload bytes, feature switches,
allocator settings, warmup and validation on every image. Run the images in
one order and then its reverse; retain per-case, per-block measurements and
process identities. Run suites independently and use a geometric mean of
per-case throughput ratios when an aggregate is useful. A quick screen is a
filter, not a stable performance claim. Repeat concerning cases with their
original calibration before deciding whether a regression is real.

Repeated launches on Windows may reuse a natural image base. Record actual
bases rather than treating launches as independent layout samples. If an image
shows a persistent unexplained regression, use a preset cohort of byte-identical
copies with balanced original-image controls and retain every result. Do not
select favorable addresses or copies. Identical code and payloads do not prove
identical timing; check the actual product build before accepting its baseline.
Debug records can also move mapped read-only data and unwind addresses when a
PDB path changes length. Compare linked payloads separately from object code;
preserve a failed equivalence result and measure the actual product image.

For a profile, first reproduce the case in an unprofiled measurement. Use a
bounded host that executes the original workload body, warms it, signals READY,
and waits for GO. Record the real child PID, binary/module paths and hashes,
natural load bases and affinity before GO. A typical AMD uProf capture uses
time-based sampling on CPU 2, a delayed seven-second capture, and a workload
window long enough to contain the entire capture. Confirm the collected window,
target PID, sample count and CPU before interpreting it. WPR/WPA or xperf can
provide complementary scheduling, CPU and memory evidence when useful.

For example, after preparing the READY/GO host, the capture command can use
`AMDuProfCLI collect --duration 7 --affinity 2 --limit-data 48M --config tbp
--call-graph 1:48:user:fpo --start-delay 3 -o <session> <qjs> --std <host>`.
Check the installed profiler's supported options and the resulting schedule;
the command alone does not prove that useful samples were collected.

Use matching PDBs for MSVC or DWARF/COFF symbols for MinGW. If a profiler needs
a debug-stripped translation copy, verify all non-debug sections against the
original and use that copy only for offline symbolization; never execute it as
the measured image. Map sampled instruction addresses to the actual loaded
image and its function/unwind ranges. Self-sample percentages identify where
to investigate; they are not call counts, inclusive costs or additive estimates
of removable time. Check dynamic path selection and generated source before
attributing a regression to an instruction or data structure.

An extra profile loop can change caller depth and frame-arena occupancy even
when it runs the original workload body. For capacity-sensitive admission,
verify path rates in the unchanged suite/calibration callers, for example by
reading existing counters at result-callback boundaries. Keep these observer
runs out of speed results, and report their context separately from extra-loop
profiles. A large reduction in fallback counts is not itself a speedup.

On Linux, use the documented product build rather than the manual foundation
tools. Qualify the actual installed ELF image, SysV aggregate calls, PIE/PIC,
nonexecutable stack and complete CFI. Keep all 19 source pins byte-identical.
Read docs/architecture/x86/linux/LINUX-MECHANISM-COVERAGE.txt before calling a mechanism missing; a
Win64 configuration switch is not necessarily the Linux implementation switch.

For Linux sampling, a root collector may attach perf cpu-clock:u at 499 Hz
with DWARF call graphs to an ordinary user engine pinned to CPU 2. Use READY/GO,
a three-second delay and a bounded seven-second window fully inside the real
workload. Verify PID, UID, mapped image/hash, CPU, window and lost samples.
Hardware PMU events may be unavailable under WSL; do not invent hardware data.
Separate profiles that repeat the original body from original calibrated scores.
Use tools/bench/linux-selected.py with explicit immutable external corpora and
tools/elf/screen.py --all for the exact upstream micro list. Report original
V8-v7 scores, JetStream body milliseconds and micro ns/op, with actual engine
peak RSS. Keep adaptive calibration N and multimodal samples when they matter.

Do not change runtime private memory, registers or controls through a debugger
to force admission. Read-only original-caller observations are separate from
speed data. Reject a local heuristic when complete suite costs erase its gain;
do not start an unbounded port-time optimization campaign. The six original
completion gates in docs/architecture/x86/linux/LINUX-PORT.txt remain the release audit contract.

For independent optional builtin workers, retain inherited function entries
and use compatible existing late code/readonly/writable input families. A new
zeroed static in ordinary BSS can disturb inherited layout. Compare old function
RVAs and normal data/VM positions, then measure the actual installed image;
relative-layout preservation alone is not a speed guarantee. On GNU PE, check
header/first-section overlap before launch: an extra section can exceed the
header page before the nominal section-count limit is reached.

Bind private compiler-clone signatures to the actual original caller/callee.
Do not identify a compiler by the presence of a generic symbol alongside its
clones. An unrecognized optional per-builtin shape must retain the original
path without emitting references through a guessed ABI. Test that fallback by
proving the input core bytes remain unchanged. Keep pinned-source review gates.

## Correctness and review

The optional async-generator worker lives in `src/promise/generator-capability.inc`
and `tools/generate/generator-capability.py`, with its reviewed compiler contract
in `src/x86/win64/abi/generator-capability.json`. A private generator request
can own its public output Promise directly: two undefined `resolving_funcs`
slots identify this case, while `request.promise` retains its original GC and
release ownership. Every helper that can settle such a request must remain in
the same owner. Do not export an inherited `js_async_generator_*` helper that
assumes those slots contain functions; the generator enforces this boundary.

Keep real, fresh CData recovery functions and the original reaction job,
context, FIFO and interrupt polls. `CallSite.getFunction()` can expose recovery
function identity and properties. Pending/rejected await fallback and late hook
changes still have to settle both ordinary and capability-free requests safely.
The process switches provide original, clone and component controls; a missing
intrinsic or an unknown compiler/caller/callee profile retains the original path.
New platforms need their own reviewed routing and ABI proof. No assembly or
public layout change is required by this worker.

The async capability tests include both generator and ordinary async semantics,
public allocator/GC/hook/realm checks, fresh-runtime OOM sweeps and an unknown
profile input-retention check. Ordinary async output-capability elision is not
enabled by this worker. Asynchronous CLI tests must exit nonzero on failure;
CTest also requires the explicit success marker and rejects a failure marker.

- Build and test both native toolchains and the portable fallback, including
  public consumers, generator and ABI contracts, exceptions, GC, reentry,
  ownership, OOM, realm and callback behavior where relevant.
- Use the same Test262 corpus and known-error list as the accepted baseline;
  report total, pre-existing, fixed and newly introduced failures separately.
- Preserve generation/extraction contracts and source notices. Document any
  formatter exclusions and verify their frozen hashes or regeneration rules.
- A commit should describe the final change, its compatibility boundaries and
  validation, not an experimental narrative. Do not rewrite old baseline tags.

## Bounded compiler planning

Compiler planning uses existing bytecodes before the inherited final resolver. Keep the first64 uncaptured-cell, control-flow/prologue and stack bounds; no runtime metadata or frame extension. Prove newly compiled output independently, including old-value release and loop reinitialization. Native FD projection and all compiler-generated code/RO stay outside the core TU, with exact pinned private types and a tested portable fallback.

QJS_DISABLE_TDZ_PLAN and QJS_DISABLE_TDZ_INIT are compile-time controls tested by presence (0 also disables). They affect new compilation; do not treat cached/serialized code as rerun with a different control. BothOFF bytecode equality proves semantics ancestry, not whole-binary timing equivalence. Retain accepted/stock timing controls and inspect actual native feature routes after every core/compiler change.

Private-function fingerprint normalization must validate every reviewed local transfer or function-address target before ignoring its displacement. All remaining bytes, registers, relocations and exact caller/callee profiles remain checked. Unknown code or table metadata retains original input; never update raw hashes merely to force admission.

Prefer a different measured opportunity when a bounded candidate cannot justify its cost. Preserve the negative result and the accepted baseline; repeated layout or tiny-path variants are not a completion requirement. Distinguish representation and ownership tradeoffs from demonstrated missing mechanisms. A parked result does not prove an architectural performance ceiling.


Long regexp admission composes the existing guarded large-code validator with
the existing register-frame regexp opcode. OP_regexp is a one-byte stack
operation; it consumes two owning values and has no immediate cpool operands.
Keep the short validator, native opcode worker, 64KiB bitmap/stack guard and
selective frame layouts unchanged. QJS_DISABLE_FRAME_LONG_REGEXP, by presence
including 0, retains original admission when a bytecode is first classified;
QJS_DISABLE_FRAME_REGEXP and a disabled register interpreter also retain it.
Use fresh processes for component ablations. The large-code semantic fixture
covers fresh literal identity, getter/GC reentry, exceptions and iterator/spread
composition with both explicit disable values. A base-validator rejection is
not the final backend decision: inspect all appended cohort selectors first.

Keep independent scalar configuration and new workers out of the inherited core
translation unit. Even a cold atomic/environment initializer can grow an old
function and shift the VM. Append new assembly workers after inherited entries;
compare actual VM bytes/addresses, table positions and constructor deltas before
crediting a mechanism. Address preservation is evidence, not a speed guarantee.
Retain observing/overflow/TDZ/-0 fallback and test live captured cells under GC.
For native scalar child leaves, see docs/architecture/x86/linux/LINUX-SCALAR-LEAVES.txt.

Retain microbench clock source, adaptive N and every mode. On this pinned Linux
host os.cputime counts user CPU, whereas os.now measures elapsed time; a separate
wall-clock diagnostic must be labeled and must not silently replace upstream
scores. Recheck a large apparent loss using the original calibration. Price
confirmed costs against both accepted and stock, even when the suite improves.

A local Linux improvement does not close MinGW performance parity. For a port
review, include the immutable source-platform SDK and current native build in
the same original whole-suite comparison, alongside prior/stock Linux. Verify
historical scores and rerun the actual retained image. Preserve all sample
modes and ranges; never use a favorable component/launch to declare parity.
Mechanism inventory alone does not prove the hot route is equally efficient.
Profile repeated classification and actual default decisions before assuming
an architectural ceiling. See docs/architecture/x86/linux/LINUX-FINAL-REVIEW.txt for the bounded source-platform review,
remaining per-case gaps and feature-work exit. docs/architecture/x86/linux/LINUX-SLOW-ROUTING.txt
retains the historical routing increment.

For an independent noncalling ELF continuation, prefer an executable input
section that can preserve inherited function entries and instruction bytes.
Retain the incoming publication token: a disabled or failing Dirty route must
reach its observing C boundary before user code or finalizers. Describe the
borrowed VM CFA explicitly and test an actual unwind through the new section.
Compare linked text, tables, segments and memory as well as paired timings;
preserved code alone does not prove unchanged performance. Audit every reader
of an inherited disable control before calling its result a pure ablation.
See docs/architecture/x86/linux/LINUX-STACK-INSERT.txt for the qualified example and shared switch.


Reference-slot replacement must preserve the complete incoming alias/dup or
transfer and finalizer protocol. Commit the new slot and PC/SP before the
last old-value release; never overwrite a slot after reentrant user code.
Reuse the original typed quota/publication owner unless a separately measured
release implementation justifies its cost. A family disable includes both
nonlast decrement and last dispatch; it is not a decrement-only ablation.
Check actual unused runtime padding and scratch leases against the measured
ABI. Keep normal and Dirty observing boundaries and real CFI. See
docs/architecture/x86/linux/LINUX-REFERENCE-SLOTS.txt for the qualified Linux example and its explicit
old continuation move; fixed main entries do not prove whole-image identity.

Keep independent new-path policy out of inherited inline initializers. A few getenv calls can change compiler inlining and move unrelated VM code; restore the old policy body and measure the actual ON/OFF image rather than choosing addresses. See docs/architecture/x86/linux/LINUX-VIRTUAL-ARGUMENTS.txt.

On the pinned Linux host, short user-CPU minima can be multimodal even for an immutable accepted image. Preserve the original full list/calibration/all modes, then use a separately labeled elapsed-clock diagnostic for a confirmed concern. Bind the exact one-line clock change and never mix the two timing panels or rename diagnostics as upstream scores.

For an independent ELF C worker,derive private types from the same actual core
input and callable declarations from the checked source owner. Bind hidden
aliases at the definition with the original type. Register generated C,header
and receipt as build inputs;check the actual object CET,nonwritable executable
section and complete FDE coverage. Verify a natural cross-module backtrace,
not only symbol presence. A module cleanup may trade performance across suites;
record the accepted cost explicitly and retain every original launch/mode.

For AArch64 captured-readonly admission,reuse the exact shared bounded graph
proof and cold classifier. Publishing kind7 requires coherent ordinary native
entry as well as forwarding. If a missing window cannot grow beside a caller
capture table,retain the original native owned-missing route when its controls
permit;clear uncommitted window scratch first. Test readonly and original owned
metadata/path expectations under both proof disable values,including zero
arity,captured recursion,GC/reentry and escaping closure detachment. Keep the
generic C FRAME_READONLY_ARGS rule unchanged and prove compiledOFF core/VM
identity. See docs/architecture/arm64/LINUX-AARCH64-FORWARDING.txt.
