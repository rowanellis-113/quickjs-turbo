import * as std from "qjs:std";

function assert(ok, message) {
  if (!ok) throw Error(message || "wide operand stack assertion");
}
function concatFunction(count, expression) {
  return new Function("return 'p'.concat(" + Array(count).fill(expression).join(",") + ")");
}

// For this producer the receiver/function plus N arguments need N+2 slots.
// Exercise both old/new admission edges and the unchanged C fallback.
for (const count of [32, 254, 255, 256, 300, 510, 511, 600]) {
  const fn = concatFunction(count, "0");
  assert(fn() === "p" + "0".repeat(count), "numeric arguments " + count);
}
for (const literal of ["'x'", "'\\u0100'"]) {
  const fn = concatFunction(256, literal);
  assert(fn() === "p" + (literal === "'x'" ? "x" : "\u0100").repeat(256), "flat string arguments");
}

// Every object is owned only by the argument operand area. GC and nested JS
// run while the C builtin consumes that area, including a full512-slot frame.
const originalToString = Object.getOwnPropertyDescriptor(Object.prototype, "toString");
const marker = new Error("wide coercion marker");
let calls = 0,
  throwAt = 0;
function reenter(value) {
  return value + 1;
}
try {
  Object.defineProperty(Object.prototype, "toString", {
    configurable: true,
    writable: true,
    value: function () {
      std.gc();
      assert(reenter(41) === 42, "nested JS after GC");
      if (++calls === throwAt) throw marker;
      return "z";
    },
  });
  for (const count of [255, 256, 300, 510, 511]) {
    const fn = concatFunction(count, "{}");
    calls = 0;
    assert(fn() === "p" + "z".repeat(count), "object arguments " + count);
    assert(calls === count, "coercion count " + count);
    calls = 0;
    throwAt = 127;
    let caught = false;
    try {
      fn();
    } catch (error) {
      caught = error === marker;
    }
    assert(caught && calls === throwAt, "wide exception identity and order");
    throwAt = 0;
    calls = 0;
    std.gc();
    assert(fn() === "p" + "z".repeat(count), "wide exception recovery");
    assert(calls === count, "recovered coercion count");
  }
} finally {
  Object.defineProperty(Object.prototype, "toString", originalToString);
}
std.gc();
print("WIDE_STACK_GC_REENTRY_EXCEPTION_OK");
