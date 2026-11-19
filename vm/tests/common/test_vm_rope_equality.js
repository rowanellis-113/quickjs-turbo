import * as std from "qjs:std";
function assert(ok, message) {
  if (!ok) throw Error(message || "rope equality");
}
function equal(a, b) {
  assert(a === b, String(a) + " != " + String(b));
}
function build(text) {
  let value = "";
  for (let i = 0; i < text.length; ++i) value = value + text.charAt(i);
  return value;
}
for (let text of ["obj", "endobj", "01", "1", "0", "1.5", "0x10", "\u03a9x", "\ud800x"]) {
  let value = build(text);
  let flat = text;
  assert(value == flat && flat == value);
  assert(!(value != flat) && !(flat != value));
  assert(value === flat && Object.is(value, flat));
  assert(!(value == text + "different"));
  assert(value != null && value != undefined);
  let calls = 0;
  let fromFlat = {
    [Symbol.toPrimitive](hint) {
      equal(hint, "default");
      ++calls;
      std.gc();
      return flat;
    },
  };
  let fromRope = {
    [Symbol.toPrimitive](hint) {
      equal(hint, "default");
      ++calls;
      std.gc();
      return value;
    },
  };
  assert(value == fromFlat && fromFlat == value && flat == fromRope && fromRope == flat);
  equal(calls, 4);
  assert(!(fromFlat == fromRope));
  equal(calls, 4);
}
for (let length of [8192, 8193, 10000]) {
  let left = "x".repeat(length);
  let value = left + "b";
  let flat = [left, "b"].join("");
  assert(value == flat && flat == value && !(value != flat));
}
for (let [text, number] of [
  ["01", 1],
  ["1.5", 1.5],
  ["0x10", 16],
  ["-0", 0],
]) {
  let value = build(text);
  assert(value == number && number == value);
  assert(!(value === number));
}
let one = build("01");
assert(one == true && true == one && one == 1n && 1n == one);
let bad = build("12x");
assert(!(bad == 12n) && !(12n == bad));
let symbol = Symbol("x");
assert(!(bad == symbol) && !(symbol == bad));
let raised = 0;
let broken = {
  [Symbol.toPrimitive]() {
    ++raised;
    throw new RangeError("expected");
  },
};
try {
  one == broken;
  throw Error("missing throw");
} catch (e) {
  assert(e instanceof RangeError);
}
equal(raised, 1);
std.gc();
print("ROPE_EQUALITY_SMOKE_PASSED");
