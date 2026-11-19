Global binding cell public embedding regression

Configure this independent CMake project with CMAKE_PREFIX_PATH pointing to
an installed build of qjs. It uses find_package(qjs CONFIG REQUIRED) and the
exported qjs target. Build,then run ctest --test-dir <build> --output-on-failure.

Five modes:default,binding-cell OFF(including value0),all IC OFF,register C,
full C. Each process checks the default allocator and a moving allocator.
It checks current values,ordinary global tag4,immediate finalization,legal
GC/reentry,foreign-realm lifetime,and recovery after a real256->384 property
buffer relocation followed by OOM. Retired buffers are poisoned/quarantined
until runtime destruction. This fixture calls no JS from a finalizer.

The CLI regression is tests/test_vm_global_binding.js. Run it as a module;
it invokes the unchanged stress program in global script scope. It also runs
through tests.conf local mode. Platform/build qualification is in
docs/frame/GLOBAL-BINDING-CELLS-20261028.txt/.json.
