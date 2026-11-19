"use strict";
let checks = 0;
function equal(actual, expected, label) {
  checks++;
  if (!Object.is(actual, expected)) throw Error(label + ": " + actual + " != " + expected);
}
function ref(fn, label) {
  checks++;
  try {
    fn();
  } catch (e) {
    if (e instanceof ReferenceError) return;
    throw e;
  }
  throw Error(label + ": missing ReferenceError");
}
function initialized(flag) {
  let x = flag ? 3 : 8;
  let y = x + 2;
  if (flag) y += x;
  return y + x;
}
equal(initialized(true), 11, "branch initialized");
equal(initialized(false), 18, "branch initialized2");
ref(function () {
  return x;
  let x = 1;
}, "before declaration");
ref(function () {
  return typeof x;
  let x = 1;
}, "typeof before declaration");
function switching(key) {
  switch (key) {
    case 0:
      let x = 17;
      return x + x;
    case 1:
      return x;
    default:
      return 4;
  }
}
equal(switching(0), 34, "switch initialized");
equal(switching(3), 4, "switch default");
ref(() => switching(1), "switch bypass initialization");
function loopReset(n) {
  let sum = 0,
    errors = 0;
  for (let i = 0; i < n; i++) {
    if (i & 1) {
      try {
        sum += x;
      } catch (e) {
        if (!(e instanceof ReferenceError)) throw e;
        errors++;
      }
    }
    let x = i;
    sum += x + x;
    if (i % 3 === 0) continue;
    sum += x;
  }
  return sum * 1000 + errors;
}
equal(loopReset(8), 75004, "loop lexical reset and continue");
function catches(flag) {
  let count = 0;
  try {
    if (flag) throw 1;
    let x = 9;
    count += x + x;
  } catch (e) {
    let y = 5;
    count += y + y;
  }
  let z = 3;
  return count + z + z;
}
equal(catches(false), 24, "normal try");
equal(catches(true), 16, "catch seeded unknown");
function finallyPath(flag) {
  let x = 1;
  try {
    if (flag) return x + x;
    x = 7;
  } finally {
    x++;
  }
  return x + x;
}
equal(finallyPath(true), 2, "finally early return");
equal(finallyPath(false), 16, "finally fallthrough");
function captured() {
  let x = 1;
  function set() {
    x = 9;
  }
  let before = x;
  set();
  return before + x;
}
equal(captured(), 10, "captured local mutation");
ref(function () {
  function read() {
    return x;
  }
  read();
  let x = 4;
}, "captured TDZ");
function directEval() {
  let x = 3;
  let y = x;
  eval("x=7");
  return x + y;
}
equal(directEval(), 10, "direct eval write");
ref(function () {
  eval("x");
  let x = 5;
}, "eval TDZ");
function reentry() {
  let x = 2;
  const object = {
    valueOf() {
      x = 11;
      return 1;
    },
  };
  return x + object + x;
}
equal(reentry(), 14, "coercion reentry into captured local");
function* generator() {
  yield 1;
  let x = 8;
  yield x + x;
}
const gen = generator();
equal(gen.next().value, 1, "generator first");
equal(gen.next().value, 16, "generator after resume");
class Parent {
  constructor() {
    this.value = 7;
  }
}
class Child extends Parent {
  constructor(early) {
    if (early) this.bad = 1;
    super();
    let x = this.value;
    this.value = x + x;
  }
}
equal(new Child(false).value, 14, "derived ctor initialized");
ref(() => new Child(true), "derived ctor this before super");
let declarations = Array.from({ length: 80 }, (_, i) => "let v" + i + "=" + i + ";").join("");
let reads = Array.from({ length: 80 }, (_, i) => "v" + i).join("+");
equal(
  Function(declarations + "return " + reads + ";")(),
  3160,
  "first64 tracked and later locals preserved",
);
let branches = Array.from({ length: 300 }, (_, i) => "if(n===" + i + ")x+=" + i + ";").join("");
let large = Function("n", "let x=1;" + branches + "return x+x;");
equal(large(299), 600, "over256 basic blocks original fallback");
for (let i = 0; i < 100; i++) {
  equal(initialized(Boolean(i & 1)), i & 1 ? 11 : 18, "repeated branch");
  ref(() => switching(1), "repeated switch TDZ");
}
if (typeof std === "object" && std.gc) std.gc();
console.log(JSON.stringify({ passed: true, checks }));

{
  const entryRequire = (value, label) => {
    if (!value) throw Error("entry init: " + label);
  };
  function firstUse(n) {
    let a = n + 1;
    const b = a * 2;
    let c = b - 1;
    return c;
  }
  for (let i = 0; i < 100; i++) entryRequire(firstUse(i) === 2 * i + 1, "first entry local");
  function repeated(n) {
    let out = [];
    for (let i = 0; i < n; i++) {
      let value = { i };
      out.push(value.i);
    }
    return out.join(",");
  }
  entryRequire(repeated(4) === "0,1,2,3", "loop reinitialization");
  function recur(n) {
    let keep = n;
    return n ? recur(n - 1) + keep : 0;
  }
  entryRequire(recur(20) === 210, "fresh frame reuse");
  function badRead() {
    return value;
    let value = 1;
  }
  function badWrite() {
    value = 1;
    const value = 2;
  }
  // Preserve observed pinned-NG error types; entry-error-type-probe/RESULTS.json binds original/stock/ON/OFF evidence.
  for (const [fn, kind] of [
    [badRead, ReferenceError],
    [badWrite, TypeError],
  ]) {
    let caught = false;
    try {
      fn();
    } catch (e) {
      caught = e instanceof kind;
    }
    entryRequire(caught, "pinned TDZ error type");
  }
  const named = function localName(n) {
    let held = localName;
    return held === localName && n === 7;
  };
  entryRequire(named(7), "implicit function-name owner");
  function implicit(a) {
    let own = arguments;
    return own[0] === a;
  }
  entryRequire(implicit(19), "implicit arguments prologue");
  function ctorProbe() {
    let own = new.target;
    this.ok = own === ctorProbe;
  }
  entryRequire(new ctorProbe().ok === true, "implicit new.target prologue");
  class EntryBase {
    constructor() {
      this.value = 3;
    }
  }
  class EntryDerived extends EntryBase {
    constructor() {
      let value = 7;
      super();
      this.value += value;
    }
  }
  entryRequire(new EntryDerived().value === 10, "derived this init once");
  function alias() {
    let value = 13;
    let get = () => value;
    value = 17;
    return get();
  }
  entryRequire(alias() === 17, "captured cell fallback");
  function evalProbe() {
    let value = 23;
    return eval("value");
  }
  entryRequire(evalProbe() === 23, "direct eval fallback");
  if (typeof std === "object" && std.gc) std.gc();
  console.log("ENTRY_INIT_SEMANTICS_OK");
}
