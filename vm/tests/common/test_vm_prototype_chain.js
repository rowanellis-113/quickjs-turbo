"use strict";

function check(actual, expected, label) {
  if (actual !== expected) throw new Error(label + ": " + actual + " != " + expected);
}
function invoke(o) {
  return o.m();
}
function one() {
  return this.n;
}
function two() {
  return this.n + 20;
}

const holder = { m: one };
const middle = Object.create(holder);
const base = Object.create(middle);
base.n = 7;
for (let i = 0; i < 2048; i++) check(invoke(base), 7, "depth2 warm");
middle.m = two;
check(invoke(base), 27, "intermediate shadow");
delete middle.m;
check(invoke(base), 7, "delete shadow");
holder.m = two;
check(invoke(base), 27, "live holder replacement");
holder.m = one;
Object.setPrototypeOf(middle, { m: two });
check(invoke(base), 27, "replace prototype");
Object.setPrototypeOf(middle, holder);

Object.defineProperty(middle, "m", {
  configurable: true,
  get() {
    check(this, base, "getter receiver");
    gc();
    return two;
  },
});
check(invoke(base), 27, "getter and GC");
delete middle.m;
check(invoke(base), 7, "descriptor removed");
let traps = 0;
const proxy = new Proxy(
  {},
  {
    get(target, key, receiver) {
      if (key === "m") {
        traps++;
        check(receiver, base, "proxy receiver");
        gc();
        return two;
      }
      return Reflect.get(target, key, receiver);
    },
  },
);
Object.setPrototypeOf(middle, proxy);
check(invoke(base), 27, "proxy prototype");
check(traps, 1, "proxy count");
Object.setPrototypeOf(middle, holder);

const array = [];
array.n = 11;
Object.setPrototypeOf(array, middle);
for (let i = 0; i < 128; i++) check(invoke(array), 11, "exotic array receiver");
const typed = new Int16Array(2);
typed.n = 13;
Object.setPrototypeOf(typed, middle);
for (let i = 0; i < 128; i++) check(invoke(typed), 13, "exotic typed receiver");

let long = holder;
for (let i = 0; i < 48; i++) long = Object.create(long);
long.n = 17;
for (let i = 0; i < 128; i++) check(invoke(long), 17, "long-chain fallback");
const empty = Object.create(null);
empty.n = 23;
let threw = false;
try {
  invoke(empty);
} catch (e) {
  threw = e instanceof TypeError;
}
check(threw, true, "missing method");
for (let i = 0; i < 128; i++) {
  const transient = Object.create(middle);
  transient.n = i;
  check(invoke(transient), i, "last receiver operand");
}
Object.defineProperty(middle, "m", {
  configurable: true,
  get() {
    throw new RangeError("marker");
  },
});
threw = false;
try {
  invoke(base);
} catch (e) {
  threw = e instanceof RangeError && e.message === "marker";
}
check(threw, true, "getter exception");
delete middle.m;
gc();
for (let i = 0; i < 512; i++) check(invoke(base), 7, "after GC");
check("abc".charCodeAt(1), 98, "string method");
check((123).toString(), "123", "number method");
print("LIVE CHAIN SEMANTICS PASSED");
