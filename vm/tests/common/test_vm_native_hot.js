import * as std from "qjs:std";
function check(x, y) {
  if (!Object.is(x, y)) throw Error(String(x) + " != " + String(y));
}
function add(a, b) {
  return a + b;
}
function sub(a, b) {
  return a - b;
}
function mul(a, b) {
  return a * b;
}
function mod(a, b) {
  return a % b;
}
function addLocal(a, b) {
  let x = a;
  x += b;
  return x;
}
function field(o, x) {
  o.value = x;
  return o.value;
}
function element(a, k, x) {
  a[k] = x;
  return a[k];
}
function constant() {
  return "native-constant";
}
function empty() {
  return "";
}
function nullish(x) {
  return x == null;
}

const values = [
  0,
  -0,
  1,
  -1,
  2147483647,
  -2147483648,
  2147483648,
  0.125,
  -2.75,
  1e100,
  Infinity,
  -Infinity,
  NaN,
  true,
  false,
  null,
  undefined,
  "2",
  "x",
];
for (const a of values)
  for (const b of values) {
    check(add(a, b), a + b);
    check(sub(a, b), a - b);
    check(mul(a, b), a * b);
    check(mod(a, b), a % b);
    check(addLocal(a, b), a + b);
  }
check(add(7n, 3n), 10n);
check(mul(7n, 3n), 21n);
check(addLocal(7n, 3n), 10n);
let coercions = 0;
const numeric = {
  valueOf() {
    coercions++;
    std.gc();
    return 0.5;
  },
};
check(add(numeric, 2), 2.5);
check(coercions, 1);
check(addLocal(numeric, 2), 2.5);
check(coercions, 2);
check(mul(numeric, 2), 1);
check(coercions, 3);

const o = { value: 1 },
  array = [1, 2, 3];
for (let i = 0; i < 128; i++) {
  check(field(o, i), i);
  check(element(array, i % 3, i), i);
  check(element(array, String(i % 3), i + 1), i + 1);
  check(constant(), "native-constant");
  check(empty(), "");
  std.gc();
}
const shared = { retained: 42 };
check(field(o, shared), shared);
std.gc();
check(o.value.retained, 42);
check(field(o, o), o);
check(o.value, o);
check(element(array, 0, shared), shared);
std.gc();
check(array[0].retained, 42);
check(element(array, 0, array), array);
check(array[0], array);
const growing = [];
check(element(growing, 0, 7), 7);
check(element(growing, 12, 8), 8);
check(growing.length, 13);
const typed = new Int16Array(2);
check(element(typed, 0, 65537), 1);
let setters = 0;
const setter = {
  set value(x) {
    setters += x;
  },
  get value() {
    return setters;
  },
};
check(field(setter, 3), 3);
check(setters, 3);
const readonly = Object.freeze({ value: 5 });
let threw = false;
try {
  field(readonly, 2);
} catch (e) {
  threw = e instanceof TypeError;
}
check(threw, true);
check(readonly.value, 5);
for (const value of values.concat([o, array, shared, Symbol("s")]))
  check(nullish(value), value == null);
// Atom-backed numeric literals allocate their decimal string in the old slow path.
function numericAtom() {
  return "123";
}
check(numericAtom(), "123");
print("native-hot PASS");

// Dedicated slow operations must preserve coercion order, exceptions and GC.
function divideSlow(a, b) {
  return a / b;
}
function compareSlow(a, b) {
  return [a < b, a <= b, a > b, a >= b, a == b, a != b, a === b, a !== b];
}
check(divideSlow(21n, 3n), 7n);
check(sub(21n, 3n), 18n);
check(mod(21n, 4n), 1n);
check(divideSlow(-1, 0), -Infinity);
check(divideSlow(0, 0), NaN);
check(JSON.stringify(compareSlow(3n, 3n)), "[false,true,false,true,true,false,true,false]");
check(JSON.stringify(compareSlow("3", 3)), "[false,true,false,true,true,false,false,true]");
let operationOrder = "";
function reenterSlow(x) {
  return x + 1;
}
const leftSlow = {
  valueOf() {
    operationOrder += "L";
    std.gc();
    return reenterSlow(6);
  },
};
const rightSlow = {
  valueOf() {
    operationOrder += "R";
    std.gc();
    return reenterSlow(2);
  },
};
check(add(leftSlow, rightSlow), 10);
check(operationOrder, "LR");
operationOrder = "";
check(mul(leftSlow, rightSlow), 21);
check(operationOrder, "LR");
operationOrder = "";
check(divideSlow(leftSlow, rightSlow), 7 / 3);
check(operationOrder, "LR");
const stopSlow = {
  valueOf() {
    std.gc();
    throw "slow-coercion-stop";
  },
};
for (const op of [add, sub, mul, mod, divideSlow, compareSlow]) {
  let caught = false;
  try {
    op(leftSlow, stopSlow);
  } catch (e) {
    caught = e === "slow-coercion-stop";
  }
  check(caught, true);
  std.gc();
}
for (const op of [add, sub, mul, mod, divideSlow]) {
  let caught = false;
  try {
    op(3n, 2);
  } catch (e) {
    caught = e instanceof TypeError;
  }
  check(caught, true);
}
print("numeric-boundary PASS");

// Construction must preserve new.target, return selection, reentry and errors
// while the caller resumes in the VM. Constructor bodies keep their old path.
function constructOne(C, x) {
  return new C(x);
}
function OrdinaryConstructor(x) {
  this.value = x;
  this.target = new.target;
}
const constructed = constructOne(OrdinaryConstructor, 37);
check(constructed.value, 37);
check(constructed.target, OrdinaryConstructor);
check(Object.getPrototypeOf(constructed), OrdinaryConstructor.prototype);
function PrimitiveConstructor(x) {
  this.value = x;
  return 9;
}
function ObjectConstructor(x) {
  return { returned: x };
}
check(constructOne(PrimitiveConstructor, 41).value, 41);
check(constructOne(ObjectConstructor, 43).returned, 43);
check(constructOne(OrdinaryConstructor.bind(null), 47).value, 47);
let constructorCalls = 0;
const proxyConstructor = new Proxy(OrdinaryConstructor, {
  construct(target, args, newTarget) {
    constructorCalls++;
    std.gc();
    check(newTarget, proxyConstructor);
    return Reflect.construct(target, args, newTarget);
  },
});
check(constructOne(proxyConstructor, 53).value, 53);
check(constructorCalls, 1);
function ReenterConstructor(x) {
  std.gc();
  this.value = reenterSlow(x);
}
check(constructOne(ReenterConstructor, 61).value, 62);
function ThrowConstructor() {
  std.gc();
  throw "constructor-stop";
}
let constructorThrew = false;
try {
  constructOne(ThrowConstructor, 0);
} catch (e) {
  constructorThrew = e === "constructor-stop";
}
check(constructorThrew, true);
constructorThrew = false;
try {
  constructOne(() => 0, 0);
} catch (e) {
  constructorThrew = e instanceof TypeError;
}
check(constructorThrew, true);

function indexedRead(a, k) {
  return a[k];
}
function indexedCall(a, k) {
  return a[k]();
}
function constructAndAccess(n) {
  const a = new Int32Array(4);
  let sum = 0;
  for (let i = 0; i < n; i++) {
    a[i & 3] = i;
    sum += a[i & 3];
  }
  return sum;
}
check(constructAndAccess(128), 8128);
const int32 = new Int32Array(4);
for (const value of [-2147483648, -1, 0, 1, 2147483647]) {
  check(element(int32, 0, value), value);
  check(indexedRead(int32, 0), value);
}
// Non-int stores and property keys must still coerce in the original order.
for (const value of [2147483648, 4294967297, -0, 1.75, NaN, Infinity, "3", true, null])
  check(element(int32, 0, value), value | 0);
let typedCoercions = 0;
const typedValue = {
  valueOf() {
    typedCoercions++;
    std.gc();
    return 4294967298;
  },
};
check(element(int32, 0, typedValue), 2);
check(typedCoercions, 1);
check(element(int32, "1", 7), 7);
check(indexedRead(int32, -1), undefined);
check(indexedRead(int32, 4), undefined);
check(element(int32, -1, 7), undefined);
check(element(int32, 4, 7), undefined);
check(indexedRead(int32, "01"), undefined);
const denseRead = [int32, shared, "dense-value", 5];
for (let i = 0; i < denseRead.length; i++) {
  check(indexedRead(denseRead, i), denseRead[i]);
  std.gc();
}
const cyclicRead = [];
cyclicRead[0] = cyclicRead;
check(indexedRead(cyclicRead, 0), cyclicRead);
std.gc();
check(indexedRead([19], 0), 19); // last object reference must use the C release
const methodsRead = [
  function () {
    return this.length;
  },
];
check(indexedCall(methodsRead, 0), 1);
let indexedThrew = false;
try {
  indexedCall(int32, 0);
} catch (e) {
  indexedThrew = e instanceof TypeError;
}
check(indexedThrew, true);
const sparseRead = [];
Object.defineProperty(sparseRead, 0, {
  get() {
    std.gc();
    return 23;
  },
});
check(indexedRead(sparseRead, 0), 23);
const rab = new ArrayBuffer(16, { maxByteLength: 32 });
const trackedRead = new Int32Array(rab);
const fixedRead = new Int32Array(rab, 4, 2);
check(element(trackedRead, 3, 71), 71);
rab.resize(8);
check(indexedRead(trackedRead, 3), undefined);
check(indexedRead(fixedRead, 0), undefined);
rab.resize(24);
check(element(trackedRead, 5, 73), 73);
check(element(fixedRead, 0, 79), 79);
const detachedBuffer = new ArrayBuffer(8);
const detachedRead = new Int32Array(detachedBuffer);
detachedBuffer.transfer();
check(indexedRead(detachedRead, 0), undefined);
check(element(detachedRead, 0, 3), undefined);
const detachOnConvert = new ArrayBuffer(8);
const convertedRead = new Int32Array(detachOnConvert);
check(
  element(convertedRead, 0, {
    valueOf() {
      detachOnConvert.transfer();
      std.gc();
      return 5;
    },
  }),
  undefined,
);
const immutableBuffer = new ArrayBuffer(8).transferToImmutable();
const immutableRead = new Int32Array(immutableBuffer);
check(indexedRead(immutableRead, 0), 0);
// This pinned upstream returns false for immutable indexed stores; the opcode
// leaves the element unchanged without throwing. Preserve that behavior.
check(element(immutableRead, 0, 3), 0);
check(indexedRead(immutableRead, 0), 0);
const sharedRead = new Int32Array(new SharedArrayBuffer(8));
check(element(sharedRead, 0, 83), 83);
check(indexedRead(sharedRead, 0), 83);
std.gc();
print("constructor-indexed PASS");

// Dedicated C boundaries must retain receiver, release order and exceptions.
function propertyReadSlow(o) {
  return o.value;
}
function propertyCallSlow(o) {
  return o.method(7);
}
function propertyWriteSlow(o, x) {
  o.value = x;
  return o.value;
}
function propertyDropSlow(fn) {
  fn();
  return 7;
}
const psProto = {
  get value() {
    std.gc();
    return this.marker;
  },
  method(x) {
    std.gc();
    return this.marker + x;
  },
};
const psReceiver = Object.create(psProto);
psReceiver.marker = 10;
check(propertyReadSlow(psReceiver), 10);
check(propertyCallSlow(psReceiver), 17);
psProto.method = function (x) {
  return this.marker - x;
};
check(propertyCallSlow(psReceiver), 3);
const psAccessor = {
  marker: 20,
  get method() {
    std.gc();
    return function (x) {
      check(this, psAccessor);
      return this.marker + x;
    };
  },
};
check(propertyCallSlow(psAccessor), 27);
const psBox = {
  set value(x) {
    std.gc();
    this.saved = reenterSlow(x);
  },
  get value() {
    std.gc();
    return this.saved;
  },
};
check(propertyWriteSlow(psBox, 41), 42);
const psTarget = {
  value: 1,
  marker: 30,
  method(x) {
    return this.marker + x;
  },
};
const psProxy = new Proxy(psTarget, {
  get(target, key, receiver) {
    std.gc();
    return Reflect.get(target, key, receiver);
  },
  set(target, key, value, receiver) {
    std.gc();
    return Reflect.set(target, key, value, receiver);
  },
});
check(propertyReadSlow(psProxy), 1);
check(propertyWriteSlow(psProxy, shared), shared);
check(propertyCallSlow(psProxy), 37);
for (const pair of [
  [
    () =>
      propertyReadSlow({
        get value() {
          std.gc();
          throw "property-get-stop";
        },
      }),
    "property-get-stop",
  ],
  [
    () =>
      propertyCallSlow({
        get method() {
          std.gc();
          throw "property-method-stop";
        },
      }),
    "property-method-stop",
  ],
  [
    () =>
      propertyWriteSlow(
        {
          set value(x) {
            std.gc();
            throw "property-put-stop";
          },
        },
        2,
      ),
    "property-put-stop",
  ],
  [
    () =>
      propertyReadSlow(
        new Proxy(
          {},
          {
            get() {
              std.gc();
              throw "property-proxy-stop";
            },
          },
        ),
      ),
    "property-proxy-stop",
  ],
]) {
  let psCaught;
  try {
    pair[0]();
  } catch (e) {
    psCaught = e;
  }
  check(psCaught, pair[1]);
}
const psCycle = {};
psCycle.self = psCycle;
check(
  propertyDropSlow(() => psCycle),
  7,
);
std.gc();
check(psCycle.self, psCycle);
print("property-boundaries PASS");
