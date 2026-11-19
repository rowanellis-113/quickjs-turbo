Public installed-SDK character predicate qualification
=====================================================
This standalone consumer includes only quickjs.h and links the exported qjs
CMake target. Use the same compiler/runtime as the installed SDK.

  cmake --install <engine-build> --prefix <sdk-prefix>
  cmake -S tests/embedding/character-leaf -B <consumer-build> -G Ninja -DCMAKE_PREFIX_PATH=<sdk-prefix> -DCMAKE_BUILD_TYPE=Release
  cmake --build <consumer-build> --parallel 1
  ctest --test-dir <consumer-build> -j 1 --output-on-failure

Run inside the matching compiler environment;set CMAKE_C_COMPILER and
CMAKE_MAKE_PROGRAM explicitly when needed. GNU consumers use DWARF4 symbols.
Five process modes request native,new-entry OFF(value0),runtime PIC OFF,
register OFF,and full C. Each exercises ordinary and always-moving allocators.
Coverage includes simultaneous last receiver/callee and extra owners,legitimate
coercion/reentry/GC,real OOM/recovery,interrupts,wire,foreign realm and softstack.
Public C-root admission prepares fresh functions before their single JS->JS
method call. Wire/read-wire and cross-realm calls also use native JS callers;
the foreign callee is warmed before transfer and remains live after contextfree.
Semantic success alone does not prove a native path;the baseline audit binds
separate read-only ON/OFF last-owner and writer/classification observations.
