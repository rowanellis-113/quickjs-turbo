Public installed-SDK object/null equality regression

Configure this directory with CMAKE_PREFIX_PATH pointing to an installed qjs SDK,
then build and run ctest. Always link the exported qjs target so its complete
platform linker recipe is inherited. Use an x64 VS developer environment for
MSVC, or explicitly select the MinGW compiler and Ninja with CMake.

Default checks use only public QuickJS-NG APIs and cover ordinary objects,
HTMLDDA, both operand orders, ==/!= with null/undefined, poisoned conversion,
and512 exactly timed finalizers per mode. Finalizers never execute JavaScript.
Release builds keep assertions enabled in main.c.

For this project's qualified static WIN64 engine, optionally configure with
-DQJS_OBJECT_NULL_NATIVE_COUNTERS=ON. This also proves the new native path is
hit and each process-level disable restores fallback. It requires matching
private observation symbols; leave OFF for generic/portable/shared SDKs.
Counter timings are diagnostic only. No engine configuration is changed here.

Example (use a new output path):
cmake -S tests/embedding/object-null -B build/object-null-host -G Ninja -DCMAKE_PREFIX_PATH=<installed-sdk>
cmake --build build/object-null-host
ctest --test-dir build/object-null-host --output-on-failure
