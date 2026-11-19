"use strict";
function eq(actual, expected, label) {
  if (actual !== expected) throw Error(label + ": " + actual + " != " + expected);
}
function sum(it) {
  let n = 0;
  for (const value of it) n += value;
  return n;
}
function callSum(it) {
  let n = sum(it);
  return n;
}
function first(it) {
  for (const value of it) return value;
  return -1;
}
function next() {
  let value = this.results[this.index];
  this.index++;
  return value;
}
function identity() {
  return this;
}
function make(values) {
  return {
    index: 0,
    results: values.map((value) => ({ value, done: false })).concat({ done: true }),
    next,
    [Symbol.iterator]: identity,
  };
}
let checksum = 0;
for (let i = 0; i < 64; i++) {
  eq(sum([1, 2, 3]), 6, "dense");
  eq(sum(make([i, i + 1, i + 2])), 3 * i + 3, "native JS next root");
  eq(callSum(make([i, i + 1])), 2 * i + 1, "native JS next child");
  checksum += callSum(make([i, i + 1]));
}
let order = "";
let getterResult = {
  get done() {
    gc();
    order += "d";
    return false;
  },
  get value() {
    gc();
    order += "v";
    return 7;
  },
};
let g = {
  index: 0,
  results: [
    getterResult,
    {
      get done() {
        order += "D";
        return true;
      },
      get value() {
        throw Error("done value observed");
      },
    },
  ],
  next,
  [Symbol.iterator]: identity,
};
eq(callSum(g), 7, "getters");
eq(order, "dvD", "done before value");
let inherited = Object.create({ done: false, value: 9 });
eq(
  sum({ index: 0, results: [inherited, { done: true }], next, [Symbol.iterator]: identity }),
  9,
  "inherited result",
);
let proxyResult = new Proxy(
  { done: false, value: 11 },
  {
    get(o, k) {
      gc();
      return o[k];
    },
  },
);
eq(
  sum({ index: 0, results: [proxyResult, { done: true }], next, [Symbol.iterator]: identity }),
  11,
  "proxy result",
);
let closed = 0;
let early = make([3, 4]);
early.return = function () {
  gc();
  closed++;
  return { done: true };
};
eq(first(early), 3, "close result");
eq(closed, 1, "return closes");
let marker = {};
let broken = {
  next: function () {
    return this.absent.member;
  },
  return: function () {
    closed++;
    return { done: true };
  },
  [Symbol.iterator]: identity,
};
try {
  sum(broken);
  throw Error("no next exception");
} catch (e) {
  if (!(e instanceof TypeError)) throw e;
}
eq(closed, 1, "next exception skips close");
let bad = {
  next: function () {
    return 42;
  },
  return: broken.return,
  [Symbol.iterator]: identity,
};
try {
  sum(bad);
  throw Error("primitive next accepted");
} catch (e) {
  if (!(e instanceof TypeError)) throw e;
}
eq(closed, 1, "primitive next skips close");
let failure = {
  index: 0,
  results: [
    {
      get done() {
        gc();
        throw marker;
      },
    },
  ],
  next,
  return: broken.return,
  [Symbol.iterator]: identity,
};
try {
  sum(failure);
  throw Error("done exception swallowed");
} catch (e) {
  eq(e, marker, "done exception");
}
eq(closed, 1, "done exception skips close");
let final = { done: true },
  active = { done: false, value: 0 };
function outerNext() {
  this.index++;
  if (this.index > 1) return final;
  this.active.value = callSum(this.child);
  return this.active;
}
for (let i = 0; i < 16; i++)
  eq(
    callSum({
      index: 0,
      active: { ...active },
      child: make([1, 2, 3]),
      next: outerNext,
      [Symbol.iterator]: identity,
    }),
    6,
    "nested checkpoint",
  );
let sparse = [1, , 3];
Object.defineProperty(Array.prototype, "1", {
  configurable: true,
  get() {
    gc();
    return 5;
  },
});
try {
  eq(sum(sparse), 9, "sparse prototype");
} finally {
  delete Array.prototype[1];
}
let array = [1, 2, 3],
  iter = array.values();
eq(iter.next().value, 1, "preconsumed array iterator");
array.length = 1;
eq(sum(iter), 0, "shrunken completion");

function nextReadonly(a, b, c, d, e, f, g, h, i, j) {
  if (j !== undefined) throw Error("next missing");
  let out = this.results[this.index];
  this.index++;
  return out;
}
function nextWritable(a, b, c, d, e, f, g, h, i, j) {
  j = this.results[this.index];
  this.index++;
  return j;
}
function nextCaptured(a, b, c, d, e, f, g, h, i, j) {
  this.saved = () => j;
  j = this.results[this.index];
  this.index++;
  return j;
}
function nextLocalCaptured() {
  let held = this.results[this.index];
  this.index++;
  this.saved = () => held;
  return held;
}
function nextArguments() {
  if (arguments.length !== 0) throw Error("next actual argc");
  let out = this.results[this.index];
  this.index++;
  return out;
}
const names = Array.from({ length: 98 }, (_, i) => "a" + i);
const nextLarge = Function(
  ...names,
  "'use strict';if(a0!==undefined||a97!==undefined)throw Error('next large missing');let out=this.results[this.index];this.index++;return out;",
);
for (const implementation of [
  nextReadonly,
  nextWritable,
  nextCaptured,
  nextLocalCaptured,
  nextArguments,
  nextLarge,
]) {
  for (let n = 0; n < 12; n++) {
    let it = make([1, 2, 3]);
    it.next = implementation;
    eq(callSum(it), 6, "next arity/capture");
    if (it.saved) eq(it.saved().done, true, "escaped next closure");
    gc();
  }
}

gc();
print("LINUX_ITERATORS_OK checksum=" + checksum);
