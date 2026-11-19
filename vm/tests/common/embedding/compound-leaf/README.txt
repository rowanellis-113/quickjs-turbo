Compound leaf public embedding regression
=========================================
Build the engine with tools/build-baseline.ps1 and install it with ordinary
cmake --install <build> --prefix <sdk>. Configure this directory with
cmake -S tests/embedding/compound-leaf -B <host> -G Ninja
  -DCMAKE_PREFIX_PATH=<sdk> -DCMAKE_BUILD_TYPE=Release
  -DCMAKE_C_COMPILER=<matching compiler>
Then cmake --build <host> --parallel 1 and ctest --test-dir <host> -j 1.
Use the matching 64-bit compiler environment. The exported qjs target carries
the GNU linker script; the fixture selects DWARF4 for the PE consumer.

Five modes: native, compound-OFF, property-IC-OFF, register-C and legacy-C.
Each process runs ordinary and always-moving/quarantined reallocators.
Checks include temporary/aliased finalizer ownership, getter GC and reentry,
actual backing-buffer relocation, real coercion OOM/recovery, live foreign
realm mutation, byte-identical serialization before/after warming and readback,
third-interrupt GC/cleanup and soft-stack-limit recovery.
Finalizers only count destruction; they never execute JavaScript.
COMPOUND_HOST_OK reports actual coverage, not performance or all-OOM proof.

Both Windows C toolchains with native PropertyIC share the complete compound lane. PORTABLE
retains ordinary compatible execution. GNU alone also has the character leaf. QJS_DISABLE_FRAME_COMPOUND_LEAF is a process
environment presence switch, including value 0; set it before VM startup.

The final-owner cases include ordinary receivers holding a custom finalizer
token, driven by small JS callers. This permits native-path last-owner and
alias coverage while retaining all original custom-receiver fallback cases.
Wire warming/readback uses direct JS method calls, so private leaf metadata
is exercised before the byte-identical public serialization check.
Private noinline C markers support coverage observation; no engine ABI is used
by the public fixture itself.
