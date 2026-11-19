"use strict";
function eq(a, b, name) {
  if (a !== b) throw Error(name + ": " + a + " != " + b);
}
function add(a, b, c) {
  return a + b + c;
}
function spread(f, list) {
  let value = f(...list);
  return value;
}
function prefixed(f, list) {
  let value = f(10, ...list);
  return value;
}
function method(o, list) {
  let value = o.f(...list);
  return value;
}
function applied(f, self, list) {
  let value = f.apply(self, list);
  return value;
}
function sumThis(a, b, c) {
  return this.base + a + b + c;
}
function missing(a, b, c, d, e, f, g, h, i, j) {
  return a + (j === undefined);
}
let receiver = { base: 7, f: sumThis },
  checksum = 0;
for (let n = 0; n < 64; n++) {
  eq(spread(add, [1, 2, 3]), 6, "single spread");
  eq(prefixed(add, [2, 3]), 15, "direct builder");
  eq(method(receiver, [1, 2, 3]), 13, "method spread");
  eq(applied(sumThis, receiver, [1, 2, 3]), 13, "intrinsic apply");
  eq(spread(missing, [n]), n + 1, "missing arity");
  checksum += applied(sumThis, receiver, [1, 2, 3]);
}
let list = [3, 4, 5];
function mutating(a, b, c) {
  list.length = 0;
  gc();
  return a + b + c;
}
eq(spread(mutating, list), 12, "owned spread snapshot");
list = [7, 8, 9];
eq(applied(mutating, receiver, list), 24, "owned apply snapshot");
let own = { tag: 17 };
list = [own, 2, 3];
function retained(v) {
  list.length = 0;
  gc();
  return v.tag;
}
eq(spread(retained, list), 17, "object snapshot");
let events = "";
let custom = {
  [Symbol.iterator]() {
    events += "i";
    let i = 0;
    return {
      next() {
        events += "n";
        return i < 3 ? { value: ++i, done: false } : { done: true };
      },
    };
  },
};
eq(spread(add, custom), 6, "custom iterator");
eq(events, "innnn", "iterator order");
let lengthReads = 0;
let arrayLike = {
  get length() {
    lengthReads++;
    gc();
    return 3;
  },
  0: 1,
  1: 2,
  2: 3,
};
eq(applied(sumThis, receiver, arrayLike), 13, "array-like length");
eq(lengthReads, 1, "length getter once");
let access = [1, 2, 3],
  reads = 0;
Object.defineProperty(access, "1", {
  get() {
    reads++;
    gc();
    return 8;
  },
});
eq(spread(add, access), 12, "element getter spread");
eq(reads, 1, "spread getter once");
eq(applied(sumThis, receiver, access), 19, "element getter apply");
eq(reads, 2, "apply getter once");
let saved = Array.prototype[Symbol.iterator];
Array.prototype[Symbol.iterator] = function* () {
  yield 4;
  yield 5;
  yield 6;
};
try {
  eq(spread(add, [1, 2, 3]), 15, "changed array iterator");
} finally {
  Array.prototype[Symbol.iterator] = saved;
}
const iteratorProto = Object.getPrototypeOf([].values()),
  savedNext = iteratorProto.next;
let nextReads = 0;
Object.defineProperty(iteratorProto, "next", {
  configurable: true,
  get() {
    nextReads++;
    return savedNext;
  },
});
try {
  eq(spread(add, [1, 2, 3]), 6, "next getter");
  eq(nextReads, 1, "next captured once");
} finally {
  Object.defineProperty(iteratorProto, "next", {
    configurable: true,
    writable: true,
    value: savedNext,
  });
}
function boundTarget(a, b, c) {
  return this.base + a + b + c;
}
const bound = boundTarget.bind(receiver, 1);
eq(spread(bound, [2, 3]), 13, "bound fallback");
eq(applied(bound, {}, [2, 3]), 13, "bound apply fallback");
const inheritedApply = Function.prototype.apply;
sumThis.apply = function () {
  gc();
  return 91;
};
eq(applied(sumThis, receiver, [1, 2, 3]), 91, "changed apply identity");
delete sumThis.apply;
eq(inheritedApply.call(sumThis, receiver, [1, 2, 3]), 13, "forwarded apply");
function raising() {
  throw Error("varargs failure");
}
function caught(f, it) {
  try {
    return f(...it);
  } catch (e) {
    return e.message;
  }
}
eq(caught(raising, [1, 2, 3]), "varargs failure", "spread exception");
try {
  applied(raising, receiver, [1, 2, 3]);
  throw Error("missing apply error");
} catch (e) {
  eq(e.message, "varargs failure", "apply exception");
  if (!e.stack.includes("apply")) throw Error("logical apply frame");
}
function constructor(a, b, c) {
  this.value = a + b + c;
}
function construct(C, a) {
  return new C(...a);
}
eq(construct(constructor, [1, 2, 3]).value, 6, "constructor original fallback");
const argsTarget = Function("a", "b", "return arguments.length+arguments[3]");
eq(spread(argsTarget, [1, 2, 3, 4]), 8, "argument target fallback");
eq(applied(argsTarget, receiver, [1, 2, 3, 4]), 8, "argument apply fallback");
function nestedNext() {
  let v = this.values[this.i++];
  return this.i <= this.values.length ? { value: spread(add, v), done: false } : { done: true };
}
let nested = {
  values: [
    [1, 2, 3],
    [4, 5, 6],
  ],
  i: 0,
  next: nestedNext,
  [Symbol.iterator]() {
    return this;
  },
};
let total = 0;
for (const v of nested) total += v;
eq(total, 21, "spread below checkpoint");
gc();
print("LINUX_VARARGS_OK checksum=" + checksum);
