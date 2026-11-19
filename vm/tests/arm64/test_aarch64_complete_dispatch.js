/* Complete C semantic routing under an extended caller. MIT. */
function catchRun(f) {
  try {
    return { ok: true, value: f() };
  } catch (e) {
    return { ok: false, error: e };
  }
}
function setNameLeaf() {
  return String.prototype.valueOf.call({
    toString: function () {
      return "str";
    },
  });
}
let out = catchRun(setNameLeaf);
if (out.ok || !(out.error instanceof TypeError))
  throw Error("complete set_name changed the original exception");
function currentFunctionLeaf() {
  let fn = function Self() {
    return Self;
  };
  return fn() === fn;
}
out = catchRun(currentFunctionLeaf);
if (!out.ok || out.value !== true) throw Error("complete THIS_FUNC identity");
for (let i = 0; i < 32; i++) {
  out = catchRun(function () {
    return {
      named: function () {
        return i;
      },
    }.named();
  });
  if (!out.ok || out.value !== i) throw Error("complete nested named closure");
}
print("AARCH64_COMPLETE_DISPATCH_OK");
