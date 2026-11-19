Method IC learning public embedding regression
==============================================
Install the engine using ordinary cmake --install <engine-build> --prefix <sdk>.
Configure with the matching compiler and exported qjs target:
  cmake -S tests/embedding/method-ic -B <host> -G Ninja
    -DCMAKE_PREFIX_PATH=<sdk> -DCMAKE_BUILD_TYPE=Release
    -DCMAKE_C_COMPILER=<matching compiler> -DFRAME_SOURCE_ROOT=<this-repository>
  cmake --build <host> --parallel 1
  ctest --test-dir <host> -j 1 --output-on-failure
The Windows C compiler requires its ordinary 64-bit environment. The exported qjs target carries
the platform linker recipe. Keep environment switches clear before ctest.

Eighteen tests run three public API hosts in six fresh modes: native,
compound-disabled, method-learning-disabled, property-IC-disabled, register-C,
and full C. QJS_DISABLE_METHOD_IC_LEARNING presence, including value 0,
disables the new native cacheable method-miss route; set it before VM startup.
GNU, diagnostics, compiled NoIC and PORTABLE omit the new route.

The method host evaluates the unchanged strict property/prototype fixtures
with public eval, gc and print. The original compound host checks ordinary
and moving allocators, ownership, GC, host reentry and interrupts. The original
property host checks prototype finalizers, cycles and growth allocation failure.
These are bounded checks; actual native-entry proofs, full262, application
timings and memory measurements are separately recorded in
docs/frame/BASELINE-0151-METHOD-IC-LEARNING-20261031.txt/.json.
