Sparse Array.length deletion / installed public C consumer
========================================================
The pinned upstream can skip surviving high numeric properties when deletion
compacts a sparse Array's property storage. The hard regression also lives in
tests/test_builtin.js. This public-only C host additionally checks legal finalizers,
alias/last-reference balance, mutating and throwing valueOf callbacks, GC and JS
reentry, and nonconfigurable/readonly rollback for direct/Reflect/define setters.

Use the same compiler/architecture as the installed qjs target, with its normal
toolchain environment. No private headers or hand-written linker flags are used.
  cmake -S tests/embedding/array-length -B build/array-length-host -G Ninja -DCMAKE_PREFIX_PATH=<installed-prefix>
  cmake --build build/array-length-host --parallel 1
  ctest --test-dir build/array-length-host -j 1 --output-on-failure

Four fresh-process modes: default, runtime IC disabled, register interpreter
disabled, and native frame paths disabled. Each releases all19 owners; finalizers
only count events and never execute JS. The uncorrected pinned parent fails the
first retained-high-key assertion. All declared backports disabled intentionally
keeps pristine upstream behavior; that stock configuration is not claimed fixed.

This is a focused correctness consumer. Passing it does not establish all-PC
unwind, all OOM points, other operating systems, or performance qualification.
