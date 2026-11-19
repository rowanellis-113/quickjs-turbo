"use strict";
let checks = 0;
function isInst(value, ctor) {
  return value instanceof ctor;
}
function check(value, message) {
  ++checks;
  if (!value) throw Error(message);
}
function throws(f, message) {
  let yes = false;
  try {
    f();
  } catch (e) {
    yes = isInst(e, TypeError);
  }
  check(yes, message);
}
function A() {}
function B() {}
const a = new A(),
  b = new B();
for (let i = 0; i < 20000; i++) {
  check(isInst(a, A), "ordinary true");
  check(!isInst(b, A), "ordinary false");
  check(!isInst(7, A), "primitive");
  check(isInst(Object.create(A.prototype), A), "explicit proto");
}
const defaultHasInstance = Function.prototype[Symbol.hasInstance];
function Own() {}
Object.defineProperty(Own, Symbol.hasInstance, { value: defaultHasInstance });
check(isInst(new Own(), Own), "own original intrinsic");
function Custom() {}
let calls = 0;
Object.defineProperty(Custom, Symbol.hasInstance, {
  value: function (v) {
    calls++;
    return v === a;
  },
});
check(isInst(a, Custom) && !isInst(b, Custom) && calls === 2, "custom method");
function Getter() {}
calls = 0;
Object.defineProperty(Getter, Symbol.hasInstance, {
  get() {
    calls++;
    return defaultHasInstance;
  },
});
check(isInst(new Getter(), Getter) && calls === 1, "own getter");
function Inherited() {}
calls = 0;
Object.setPrototypeOf(Inherited, {
  get [Symbol.hasInstance]() {
    calls++;
    return defaultHasInstance;
  },
});
check(isInst(new Inherited(), Inherited) && calls === 1, "inherited getter");
function Invalid() {}
Invalid.prototype = 3;
check(!isInst(0, Invalid), "primitive before invalid prototype");
throws(() => isInst({}, Invalid), "invalid prototype throws");
const arrow = () => 0;
check(!isInst(null, arrow), "arrow primitive");
throws(() => isInst({}, arrow), "arrow missing prototype");
arrow.prototype = {};
check(isInst(Object.create(arrow.prototype), arrow), "callable arrow assigned prototype");
const bound = A.bind(null);
check(isInst(a, bound), "bound constructor");
let gets = 0;
const proxyCtor = new Proxy(A, {
  get(t, k, r) {
    gets++;
    return Reflect.get(t, k, r);
  },
});
check(isInst(a, proxyCtor) && gets >= 2, "proxy constructor traps");
let protos = 0;
const proxyLeft = new Proxy(
  {},
  {
    getPrototypeOf() {
      protos++;
      return A.prototype;
    },
  },
);
check(isInst(proxyLeft, A) && protos === 1, "proxy left trap");
const revoked = Proxy.revocable({}, {});
revoked.revoke();
throws(() => isInst(revoked.proxy, A), "revoked proxy left");
let deep = A.prototype;
for (let i = 0; i < 64; i++) deep = Object.create(deep);
check(isInst(deep, A), "long prototype chain");
const before = isInst(a, A);
A.prototype = {};
check(before && !isInst(a, A), "prototype mutation live");
check(
  Object.getOwnPropertyDescriptor(Function.prototype, Symbol.hasInstance).configurable === false,
  "intrinsic descriptor",
);
// Both operands must survive GC and nested JS while the original operator is
// suspended. An exception must leave its operands for the complete unwinder.
function collectInstanceTest() {
  if (typeof std !== "undefined" && typeof std.gc === "function") std.gc();
}
function Reentrant() {}
let rejectInstance = false;
const instanceSentinel = { reason: "instanceof getter" };
Object.defineProperty(Reentrant, Symbol.hasInstance, {
  get() {
    collectInstanceTest();
    check(isInst(b, B), "getter nested instanceof");
    if (rejectInstance) throw instanceSentinel;
    return function (value) {
      collectInstanceTest();
      check(isInst(b, B), "method nested instanceof");
      return value.marker === 17;
    };
  },
});
for (let i = 0; i < 32; i++) {
  check(isInst({ marker: 17, payload: [i] }, Reentrant), "temporary operand GC root");
  rejectInstance = true;
  let caught = false;
  try {
    isInst({ marker: 17, payload: [i] }, Reentrant);
  } catch (error) {
    caught = error === instanceSentinel;
  } finally {
    collectInstanceTest();
    rejectInstance = false;
  }
  check(caught, "getter exception and operand cleanup");
  check(isInst(b, B), "recovery after instanceof exception");
}
print("INSTANCE-SEMANTICS-OK", checks);
