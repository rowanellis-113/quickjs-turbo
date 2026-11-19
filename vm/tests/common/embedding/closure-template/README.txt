Closure template public embedding regression
============================================
Install the engine with ordinary cmake --install <engine-build> --prefix <sdk>.
Configure this directory with the matching compiler and exported qjs target:
  cmake -S tests/embedding/closure-template -B <host> -G Ninja
    -DCMAKE_PREFIX_PATH=<sdk> -DCMAKE_BUILD_TYPE=Release
    -DCMAKE_C_COMPILER=<matching compiler>
  cmake --build <host> --parallel 1
  ctest --test-dir <host> -j 1 --output-on-failure
The Windows C compiler requires its ordinary 64-bit environment. The exported target supplies
the platform linker recipe; GNU consumers use DWARF4 for PE diagnostics.

Ten tests: both hosts in fresh default, template-disabled, property-IC-disabled,
register-C and legacy-C processes. Presence of
QJS_DISABLE_CLOSURE_SHAPE_TEMPLATE, including value 0, disables the strategy;
set it before creating functions. OFF retains context fields and lifecycle hooks.

closure-owner runs ordinary and always-moving/quarantined allocators. It checks
two realms, captured values, cycles, per-instance function properties,
JS_SetClassProto replacement, bounded allocator reentry with GC, and blocked
allocation recovery. Every exercise must reclaim all 49 custom owners;
the custom allocator must release all active blocks at runtime destruction.
Finalizers only count destruction and never run JavaScript.

closure-fault tests 32 declared allocation positions during hot closure creation
using the same moving allocator. It reports how many failures actually occurred;
positions beyond the call's allocations do not inject a failure. It checks
borrowed-owner survival, failed/successful result cleanup, runtime recovery and
zero remaining allocator blocks. Captured-value results are checked without
injected faults. The fixed upstream ignores some property-definition OOM errors,
so this fixture makes no stronger metadata-semantics claim under injected OOM.

These are bounded correctness and ownership checks, not performance, all-PC,
all-OOM, worst-case memory or other-platform certification. main.c is included
by fault.c with a renamed main solely to share the same allocator callbacks;
each executable compiles one translation unit.
