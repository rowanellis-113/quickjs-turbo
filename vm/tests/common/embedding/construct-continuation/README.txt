Public API constructor ownership/reentry/OOM regression.
Build against an installed SDK,using its exported qjs target:
  cmake -S tests/embedding/construct-continuation -B build/construct-host -G Ninja -DCMAKE_PREFIX_PATH=<sdk>
  cmake --build build/construct-host
  ctest --test-dir build/construct-host --output-on-failure

Each fresh mode executes768 host callbacks which force GC,reenter a JS function
that constructs an instance,and then verify the original borrowed argument.
Tests include normal/class cyclic instances,object return overrides,host throws,
three memory limits armed inside a live constructor,and calls after each OOM.
All771 host objects must finalize exactly once;finalizers only count objects.
The fixture uses public quickjs.h APIs,no engine struct or private symbol.
Native,constructorOFF(presence0),propertyICOFF,registerC and fullC modes are run.
