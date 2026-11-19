Dense spread call public embedding regression
===========================================
Build the product and install it with cmake --install <build> --prefix <sdk>.
Configure this directory with the same compiler:
  cmake -S tests/embedding/core-spread -B build/core-spread-host -G Ninja -DCMAKE_PREFIX_PATH=<sdk> -DCMAKE_BUILD_TYPE=Release
  cmake --build build/core-spread-host --parallel 1
  ctest --test-dir build/core-spread-host --output-on-failure -j 1

Use the installed exported qjs target,including its GNU linker recipe.
Five fresh process modes;each uses normal and always-moving allocators.
Checks argument/source lifetimes,alias returns,legal callback reentry/GC,
foreign iterator realms,immediate finalization,interrupt recovery and OOM.
The locked upstream treats memory limit0 as unlimited;the OOM case uses1.
Finalizers do not execute JS. Each allocator run balances387 native owners.

JS regression:tests/test_vm_core_spread_call.js is a standard module
with3498 checks and awaited async/generator fallback checks. It is included
by the unchanged tests.conf testdir;it can also run with qjs -m <file>.
QJS_DISABLE_CORE_SPREAD_CALL presence(including0) disables the new lane;
the original fallback remains. Set mode before starting a new process.
