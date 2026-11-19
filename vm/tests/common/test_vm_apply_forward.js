"use strict";
let applyTestCollections = 0;
function collectApplyTest() {
  if (typeof std !== "undefined" && typeof std.gc === "function") {
    std.gc();
    ++applyTestCollections;
  } else if (typeof gc === "function") {
    gc();
    ++applyTestCollections;
  }
}
// The measured workload is separate. This fixture checks observable contracts.
function check(value, message) {
  if (!value) throw Error(message);
}
function invoke(fn, receiver, list) {
  const value = fn.apply(receiver, list);
  return value;
}
function tailInvoke(fn, receiver, list) {
  return fn.apply(receiver, list);
}
function sum(a, b) {
  return this.base + a + b;
}
const receiver = { base: 10 };
sum.call(receiver, 1, 2);
if (typeof __applyGate === "function") __applyGate("before-simple");
for (let i = 0; i < 100; ++i) {
  check(invoke(sum, receiver, [i, 2]) === 12 + i, "dense actuals");
  check(tailInvoke(sum, receiver, [i, 3]) === 13 + i, "tail actuals");
}
function unmapped(a, b) {
  return invoke(sum, receiver, arguments);
}
check(unmapped(4, 5) === 19, "strict unmapped arguments");
if (typeof __applyGate === "function") __applyGate("after-simple");

function values(a, b, c) {
  return [this, a, b, c];
}
values.call(receiver, 1, 2, 3);
let v = invoke(values, receiver, []);
check(v[0] === receiver && v[1] === undefined && v[3] === undefined, "empty/formals");
v = invoke(values, receiver, [1, 2, 3, 4, 5]);
check(v[1] === 1 && v[3] === 3, "extra actuals");
check(invoke(values, 7, [1])[0] === 7, "primitive strict this fallback");
check(invoke(values, null, [1])[0] === null, "null strict this fallback");
check(invoke(values, undefined, null)[1] === undefined, "null list");
check(invoke(values, receiver, undefined)[2] === undefined, "undefined list");

let source;
function mutate(a, b) {
  source.length = 0;
  for (let i = 0; i < 80; ++i) source.push({ i });
  collectApplyTest();
  return [a, b];
}
source = [1, 2];
mutate.call(receiver, 1, 2);
for (let i = 0; i < 25; ++i) {
  source = [{ value: i }, { value: i + 1 }];
  const first = source[0],
    second = source[1];
  const result = invoke(mutate, receiver, source);
  check(
    result[0] === first && result[1] === second,
    "owned snapshot after dense backing reallocation/GC",
  );
}
function capture(a) {
  source.length = 0;
  collectApplyTest();
  return function () {
    return a;
  };
}
source = [0];
capture.call(receiver, 0);
source = [{ value: 77 }];
const captured = invoke(capture, receiver, source);
source = null;
collectApplyTest();
check(captured().value === 77, "captured actual detached from discarded list");

let order = [];
const proxy = new Proxy([2, 3], {
  get(target, key, self) {
    order.push(String(key));
    return Reflect.get(target, key, self);
  },
});
check(invoke(sum, receiver, proxy) === 15, "proxy list fallback");
check(order.join(",") === "length,0,1", "proxy exact original read order");
order = [];
const getterList = {
  get length() {
    order.push("length");
    collectApplyTest();
    return 2;
  },
  get 0() {
    order.push("0");
    return 5;
  },
  get 1() {
    order.push("1");
    return 6;
  },
};
check(
  invoke(sum, receiver, getterList) === 21 && order.join(",") === "length,0,1",
  "getter list fallback",
);
const sparse = [1, , 3];
check(invoke(values, receiver, sparse)[2] === undefined, "sparse list fallback");
const changedLength = [1, 2];
changedLength.length = 4;
check(invoke(values, receiver, changedLength)[3] === undefined, "length exceeds dense count");
const accessorArray = [1, 2];
Object.defineProperty(accessorArray, "0", {
  get() {
    collectApplyTest();
    return 9;
  },
});
check(invoke(sum, receiver, accessorArray) === 21, "accessor array fallback");
globalThis.probeInvoke = invoke;
globalThis.probeReceiver = receiver;
globalThis.probeSum = sum;
const mapped = Function("a", "b", "a=7; return probeInvoke(probeSum,probeReceiver,arguments)");
check(mapped(1, 2) === 19, "mapped arguments fallback");
delete globalThis.probeInvoke;
delete globalThis.probeReceiver;
delete globalThis.probeSum;

const nativeApply = Function.prototype.apply;
sum.apply = function (self, args) {
  check(this === sum && self === receiver, "custom apply receiver");
  return args[0] * 100;
};
check(invoke(sum, receiver, [8, 2]) === 800, "replaced apply");
delete sum.apply;
check(invoke(sum, receiver, [8, 2]) === 20, "restored apply");
let reads = 0;
Object.defineProperty(sum, "apply", {
  configurable: true,
  get() {
    ++reads;
    collectApplyTest();
    return nativeApply;
  },
});
check(invoke(sum, receiver, [8, 2]) === 20 && reads === 1, "live apply getter");
delete sum.apply;

const token = {};
function thrower(a) {
  collectApplyTest();
  throw a;
}
try {
  thrower(token);
} catch (e) {
  check(e === token, "warm thrower");
}
for (let i = 0; i < 25; ++i) {
  try {
    invoke(thrower, receiver, [token]);
    check(false, "missing exception");
  } catch (e) {
    check(e === token, "exception identity/unwind");
  }
  check(invoke(sum, receiver, [1, 2]) === 13, "recovery after exception");
}
try {
  invoke(sum, receiver, {
    get length() {
      throw token;
    },
  });
  check(false, "missing length throw");
} catch (e) {
  check(e === token, "length exception fallback");
}
check(invoke(Math.max, receiver, [3, 4, 2]) === 4, "native target fallback");
function recursive(n) {
  if (n === 0) return this.base;
  return invoke(recursive, this, [n - 1]);
}
recursive.call(receiver, 0);
check(invoke(recursive, receiver, [100]) === 10, "nested same activation cleanup");
collectApplyTest();
if (typeof __applyGate === "function") __applyGate("after-semantics");
print("APPLY_SEMANTICS_OK collections=" + applyTestCollections);

("use strict");
// Additional admission boundaries; kept separate from the already sealed fixture.
function extraCheck(value, message) {
  if (!value) throw Error(message);
}
function extraInvoke(fn, receiver, list) {
  const value = fn.apply(receiver, list);
  return value;
}
const extraReceiver = { base: 10 };
class ApplyBase {
  constructor(a) {
    this.value = a;
  }
}
class ApplyDerived extends ApplyBase {
  constructor(a) {
    super(a);
  }
}
new ApplyBase(1);
new ApplyDerived(1);
for (const ctor of [ApplyBase, ApplyDerived]) {
  let caught = false;
  try {
    extraInvoke(ctor, extraReceiver, [2]);
  } catch (e) {
    extraCheck(e instanceof TypeError, "class constructor error kind");
    caught = true;
  }
  extraCheck(caught, "class called without new");
}
function extraTarget(a, b) {
  return this.base + a + b;
}
extraTarget.call(extraReceiver, 1, 2);
const frozen = Object.freeze([3, 4]);
extraCheck(extraInvoke(extraTarget, extraReceiver, frozen) === 17, "frozen dense source");
const crowded = [3, 4];
for (let i = 0; i < 40; i++) crowded["extra" + i] = i;
extraCheck(extraInvoke(extraTarget, extraReceiver, crowded) === 17, "large source shape fallback");
function changedArguments(a, b) {
  Object.defineProperty(arguments, "length", {
    get() {
      collectApplyTest();
      return 2;
    },
  });
  return extraInvoke(extraTarget, extraReceiver, arguments);
}
extraCheck(changedArguments(3, 4) === 17, "unmapped arguments length accessor fallback");
extraCheck(extraTarget.apply(extraReceiver, [3, 4], 99) === 17, "extra apply operands fallback");
const bound = extraTarget.bind(extraReceiver, 3);
extraCheck(extraInvoke(bound, extraReceiver, [4]) === 17, "bound target fallback");
const proxyTarget = new Proxy(extraTarget, {
  apply(fn, self, args) {
    return Reflect.apply(fn, self, args) + 1;
  },
});
extraCheck(extraInvoke(proxyTarget, extraReceiver, [3, 4]) === 18, "proxy target fallback");
const nonStrict = Function("a", "this.value=a;return this");
nonStrict.call(extraReceiver, 1);
extraCheck(
  extraInvoke(nonStrict, extraReceiver, [9]) === extraReceiver && extraReceiver.value === 9,
  "sloppy object this",
);
extraCheck(extraTarget.apply.call(extraTarget, extraReceiver, [3, 4]) === 17, "apply via call");
const applyBound = Function.prototype.apply.bind(extraTarget);
extraCheck(applyBound(extraReceiver, [3, 4]) === 17, "bound apply fallback");

// Alternate call depths after warming the arena, keeping parent locals live.
// The callee must own its actuals across source growth, GC and nested calls.
(() => {
  let segmentSource,
    reentering = false;
  function SegmentConstructor() {
    segmentSource = arguments;
    this.initialize.apply(this, arguments);
  }
  SegmentConstructor.prototype.initialize = function (a, b, c) {
    for (let i = 0; i < 32; i++) segmentSource[i] = { changed: i };
    collectApplyTest();
    if (!reentering && a % 7 === 0) {
      reentering = true;
      const nested = new SegmentConstructor(a + 1, b, c);
      extraCheck(nested.value === a + 1 + b + c, "nested segment snapshot");
      reentering = false;
    }
    this.value = a + b + c;
  };
  function atDepth(n, a, b, c) {
    const p0 = n,
      p1 = n + 1,
      p2 = n + 2,
      p3 = n + 3,
      p4 = n + 4,
      p5 = n + 5,
      p6 = n + 6,
      p7 = n + 7;
    if (n) {
      const value = atDepth(n - 1, a, b, c);
      return value + p0 + p1 + p2 + p3 + p4 + p5 + p6 + p7;
    }
    return new SegmentConstructor(a, b, c).value;
  }
  for (let i = 0; i < 48; i++) {
    const depth = (i * 7) % 16;
    extraCheck(
      atDepth(depth, i, i + 1, i + 2) === 3 * i + 3 + 4 * depth * depth + 32 * depth,
      "segment depth/parent restoration",
    );
  }
  segmentSource = null;
  collectApplyTest();
})();
print("APPLY_EXTRA_SEMANTICS_OK");
