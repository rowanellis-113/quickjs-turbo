Public installed-SDK regression for RegExp.prototype.test ordering and ownership.

Configure with the matching compiler and installed exported qjs CMake target;
do not manually reconstruct the archive's Windows linker recipe.
  cmake -S tests/embedding/regexp-test -B build/regexp-test -DCMAKE_PREFIX_PATH=<sdk>
  cmake --build build/regexp-test --parallel 1
  ctest --test-dir build/regexp-test -j 1 --output-on-failure

Four fresh processes cover default, PropertyIC runtime OFF, register C and
full C modes, each using pool256. The host uses only public API and performs
GC/reentry from ordinary callbacks; finalizers only count releases.

The fixture requires conversion before exec lookup, owns dynamically produced
strings across getter/callback GC/reentry, and checks immediate custom-result
lastref, retained alias, exception identity/release and native lastIndex.
Two contexts also check builtin TypeError realm and foreign callback identity.
Every process must finalize all64 custom owners. This is not allOOM/allPC,
otherOS, shared-library or complete SDK qualification.

Exception lastref is checked after its catch-containing helper returns. A
separate parent/candidate/default/fullC public control verified one catch-bound
owner may remain until return; all owners release after return and GC. Strict
immediate custom-exec result lastref/alias assertions remain unchanged.
