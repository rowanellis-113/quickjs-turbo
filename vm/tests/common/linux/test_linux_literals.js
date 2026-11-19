"use strict";
function eq(a, b, name) {
  if (a !== b) throw Error(name + ": " + String(a) + " != " + String(b));
}
function make(i) {
  return { a: i, b: i + 1, c: i + 2 };
}
function drive(n) {
  let sum = 0;
  for (let i = 0; i < n; i++) {
    let o = make(i);
    sum += o.a + o.b + o.c;
  }
  return sum;
}
for (let i = 0; i < 4; i++) eq(drive(64), 6240, "ordinary literal transitions");
let iterator = {
  i: 0,
  n: 64,
  next: advance,
  [Symbol.iterator]() {
    return this;
  },
};
function advance() {
  if (this.i >= this.n) return { done: true };
  let i = this.i++;
  return { value: { v: i, w: i + 1 }, done: false };
}
function consume(it) {
  let sum = 0;
  for (const o of it) sum += o.v + o.w;
  return sum;
}
eq(consume(iterator), 4096, "checkpoint literal transitions");
function nestedAdvance() {
  if (this.i++ >= 3) return { done: true };
  return { value: { v: drive(3), w: 0 }, done: false };
}
eq(
  consume({
    i: 0,
    next: nestedAdvance,
    [Symbol.iterator]() {
      return this;
    },
  }),
  54,
  "nested literal scope",
);
let setterCalls = 0;
Object.defineProperty(Object.prototype, "a", {
  configurable: true,
  set(v) {
    setterCalls++;
    throw Error("inherited setter");
  },
});
try {
  eq(drive(32), 1584, "literal defines own data");
} finally {
  delete Object.prototype.a;
}
eq(setterCalls, 0, "prototype setter skipped");
function duplicate(i) {
  return { a: { tag: i }, a: 0, b: i };
}
function duplicates(n) {
  let sum = 0;
  for (let i = 0; i < n; i++) {
    let v = duplicate(i);
    sum += v.a + v.b;
    gc();
  }
  return sum;
}
eq(duplicates(32), 496, "duplicate property RHS consumed once");
function custom(proto, i) {
  return { __proto__: proto, a: i, b: i + 1 };
}
function prototypes(n) {
  let sum = 0;
  let one = { tag: 1 },
    two = { tag: 2 };
  for (let i = 0; i < n; i++) {
    let p = i % 2 ? one : two;
    let v = custom(p, i);
    if (Object.getPrototypeOf(v) !== p) throw Error("prototype identity");
    sum += v.a + v.b;
  }
  return sum;
}
eq(prototypes(32), 1024, "live prototype guards");
const pressure = Function(
  "n",
  "let s=0;" + Array.from({ length: 280 }, () => "s+=({a:n,b:n+1}).a;").join("") + "return s",
);
function pressureDriver() {
  let value = pressure(3) + pressure(4);
  gc();
  return value;
}
eq(pressureDriver(), 1960, "bounded cache pressure");
function type(v) {
  return typeof v;
}
function isFunction(v) {
  return typeof v === "function";
}
function isUndefined(v) {
  return typeof v === "undefined";
}
function predicate(v) {
  return typeof v === "object" && v !== null;
}
function truth(v) {
  if (v) return 1;
  return 0;
}
function not(v) {
  return !v;
}
const proxy = new Proxy(function () {}, {});
const bound = function () {}.bind(null);
const rope = "x".repeat(512) + "y".repeat(512);
const values = [
  undefined,
  null,
  false,
  true,
  0,
  -0,
  1,
  -2,
  NaN,
  Infinity,
  0n,
  1n,
  {},
  [],
  function () {},
  () => 0,
  proxy,
  bound,
  Symbol("x"),
  "",
  "abc",
  rope,
];
function scalarDriver() {
  let count = 0;
  for (let n = 0; n < 8; n++) {
    for (const v of values) {
      eq(type(v), typeof v, "typeof value");
      eq(isFunction(v), typeof v === "function", "typeof function");
      eq(isUndefined(v), v === undefined, "typeof undefined");
      eq(predicate(v), typeof v === "object" && v !== null, "predicate");
      eq(truth(v), Boolean(v) ? 1 : 0, "truth");
      eq(not(v), !Boolean(v), "lnot");
      count++;
    }
  }
  return count;
}
eq(scalarDriver(), 176, "scalar kernels");

function acceptedPredicate(v) {
  return v != null && typeof v == "object";
}
function insertValue(o, v) {
  return (o.slot = v);
}
function shortTrue(v) {
  let n = 0;
  do {
    if (n) return n;
    n++;
  } while (v);
  return n;
}
const longTrue = Function(
  "v",
  "let n=0;do {if(n)return n;n++;" + "n+=0;".repeat(150) + "}while(v);return n",
);
const longFalse = Function("v", "let n=0;if(v){n++;" + "n+=0;".repeat(150) + "}return n");
function probeScalars() {
  let seen = 0;
  const box = {};
  for (let n = 0; n < 8; n++)
    for (const v of values) {
      eq(acceptedPredicate(v), v != null && typeof v == "object", "accepted primitive predicate");
      eq(Object.is(insertValue(box, v), v), true, "insert2 result");
      eq(Object.is(box.slot, v), true, "insert2 store");
      eq(shortTrue(v), 1, "short backwards truth");
      eq(longTrue(v), 1, "long backwards truth");
      eq(longFalse(v), Boolean(v) ? 1 : 0, "long forward truth");
      seen++;
    }
  return seen;
}
eq(probeScalars(), 176, "accepted scalar cohort");
gc();
print("LINUX_LITERALS_OK checksum=6240");
