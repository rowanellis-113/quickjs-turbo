Public API strict-reference ownership fixture
=============================================
Uses the installed exported qjs target. No private headers/counters and no JS
execution in finalizers. Each process verifies1152 immediate C finalizers,
distinct/same references,exactly-two alias releases,one-last/one-held operands,
held roots across explicit GC,and normal shutdown. Five startup modes have
the same semantic expectations;route coverage comes from separate profiles.

  cmake -S tests/embedding/reference-equality -B build/reference-host -G Ninja -DCMAKE_PREFIX_PATH=<installed-sdk>
  cmake --build build/reference-host --parallel 1
  ctest --test-dir build/reference-host --output-on-failure

Native mode,reference-disabled,disable0,large-explicit,and complete C fallback
are registered. Large-explicit does not by itself prove this small fixture
executes a large function;tests/test_vm_large_code.js covers that.
The fixture uses the pinned NG0.15.1 public API.
