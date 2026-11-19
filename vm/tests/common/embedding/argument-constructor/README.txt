Public API argument-constructor ownership/reentry/OOM regression.
Build against an ordinary installed SDK and its exported qjs target:
  cmake -S tests/embedding/argument-constructor -B build/argument-construct-host -G Ninja -DCMAKE_PREFIX_PATH=<sdk>
  cmake --build build/argument-construct-host
  ctest --test-dir build/argument-construct-host --output-on-failure

Each of seven fresh modes requires771 host objects finalized exactly once,
768 GC-forcing host callbacks with JS constructor reentry,three memory limits
armed inside a live argument constructor and successful post-OOM calls.
The constructors read arguments and are called by small native-eligible JS
callers. Runtime,constructor,IC,register-C and full-C fallbacks remain tested;
the two extra modes disable only the new argument constructor admission and
argument borrowing,including environment value0 as a presence switch.
Only public quickjs.h APIs are used. This fixture does not claim moving-
allocator/all-PC/all-OOM coverage or that every backend runs the fastpath.

The seven additional cross-realm tests warm a foreign argument constructor,
then change the public stack limit inside its small caller at eight fixed
boundaries. Stack-entry errors must use a caller-realm error prototype.
Actual successes/failures can vary by backend C-stack depth; foreign errors
are never accepted. The diagnostic prototype difference was reproduced on
R3 after the complete262 pass; these tests protect the conservative fallback.
