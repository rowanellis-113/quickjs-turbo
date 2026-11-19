import * as std from "qjs:std";
let checks = 0;
function eq(a, b) {
  checks++;
  if (!Object.is(a, b)) throw Error("pop check " + checks + ": " + String(a) + " != " + String(b));
}
function throws(f, type = TypeError) {
  let caught;
  try {
    f();
  } catch (e) {
    caught = e;
  }
  eq(caught instanceof type, true);
}
const pop = Array.prototype.pop;
const object = { v: 17 },
  symbol = Symbol("tail"),
  values = [
    0,
    -0,
    1,
    -1,
    2147483647,
    2147483648,
    NaN,
    Infinity,
    -Infinity,
    undefined,
    null,
    true,
    false,
    "latin",
    "宽字",
    123n,
    symbol,
    object,
  ];
for (let round = 0; round < 40; round++) {
  const a = values.slice();
  for (let i = values.length - 1; i >= 0; i--) {
    eq(a.pop(), values[i]);
    eq(a.length, i);
    eq(Object.hasOwn(a, i), false);
  }
  eq(a.pop(), undefined);
  eq(a.length, 0);
  eq(pop.call(a), undefined);
  a.push(object, symbol);
  eq(a.pop("ignored", object, symbol), symbol);
  eq(a.pop(), object);
  std.gc();
  eq(object.v, 17);
}
function ownedTemporary(i) {
  return [{ i, padding: "survives last receiver release" }].pop();
}
for (let i = 0; i < 250; i++) {
  const x = ownedTemporary(i);
  std.gc();
  eq(x.i, i);
}
let cyclic = [];
cyclic[0] = cyclic;
eq(cyclic.pop(), cyclic);
eq(cyclic.length, 0);
std.gc();
let proto = Object.create(Array.prototype);
Object.defineProperty(proto, "2", {
  get() {
    throw Error("dense own value must win");
  },
  configurable: true,
});
let dense = [1, 2, object];
Object.setPrototypeOf(dense, proto);
eq(dense.pop(), object);
eq(dense.length, 2);
let sparse = [1, ,];
eq(sparse.pop(), undefined);
eq(sparse.length, 1);
let inherited = Object.create(Array.prototype);
Object.defineProperty(inherited, "3", {
  get() {
    std.gc();
    return object;
  },
  configurable: true,
});
let holes = [1];
holes.length = 4;
Object.setPrototypeOf(holes, inherited);
eq(holes.pop(), object);
eq(holes.length, 3);
for (const n of [0, 1, 3]) {
  let a = Array.from({ length: n }, (_, i) => i);
  Object.defineProperty(a, "length", { writable: false });
  throws(() => a.pop());
  eq(a.length, n);
  if (n) eq(Object.hasOwn(a, n - 1), false);
  let frozen = Object.freeze(Array.from({ length: n }, (_, i) => i));
  throws(() => pop.call(frozen));
  eq(frozen.length, n);
  let sealed = Object.seal(Array.from({ length: n }, (_, i) => i));
  if (n) {
    throws(() => sealed.pop());
    eq(Object.hasOwn(sealed, n - 1), true);
  } else eq(sealed.pop(), undefined);
  eq(sealed.length, n);
  let nonext = Object.preventExtensions(Array.from({ length: n }, (_, i) => i));
  eq(nonext.pop(), n ? n - 1 : undefined);
  eq(nonext.length, n ? n - 1 : 0);
}
let fixed = [1, object];
Object.defineProperty(fixed, "1", { configurable: false });
throws(() => fixed.pop());
eq(fixed[1], object);
eq(fixed.length, 2);
let getter = [];
getter.length = 1;
Object.defineProperty(getter, "0", {
  get() {
    std.gc();
    return object;
  },
  configurable: true,
});
eq(getter.pop(), object);
eq(getter.length, 0);
let order = [];
let proxy = new Proxy([7, 8, 9], {
  get(t, k, r) {
    order.push("g" + String(k));
    std.gc();
    return Reflect.get(t, k, r);
  },
  deleteProperty(t, k) {
    order.push("d" + String(k));
    return Reflect.deleteProperty(t, k);
  },
  set(t, k, v, r) {
    order.push("s" + String(k));
    return Reflect.set(t, k, v, r);
  },
});
eq(pop.call(proxy), 9);
eq(order.join(","), "glength,g2,d2,slength");
let revoked = Proxy.revocable([], {});
revoked.revoke();
throws(() => pop.call(revoked.proxy));
let inner = [10, 11],
  log = [];
let generic = {
  0: object,
  get length() {
    log.push("length");
    std.gc();
    eq(inner.pop(), 11);
    return {
      valueOf() {
        log.push("coerce");
        std.gc();
        return 1;
      },
    };
  },
  set length(v) {
    log.push("set" + v);
    std.gc();
  },
};
eq(pop.call(generic), object);
eq(log.join(","), "length,coerce,set0");
eq(Object.hasOwn(generic, "0"), false);
let throwing = { 0: object, length: 1 };
Object.defineProperty(throwing, "length", {
  get() {
    throw "length-stop";
  },
});
try {
  pop.call(throwing);
  throw Error("must stop");
} catch (e) {
  eq(e, "length-stop");
}
eq(Object.hasOwn(throwing, "0"), true);
let huge = { 4294967295: object, length: 4294967296 };
eq(pop.call(huge), object);
eq(huge.length, 4294967295);
let bigArray = [];
bigArray.length = 2147483649;
eq(bigArray.pop(), undefined);
eq(bigArray.length, 2147483648);
for (const x of [null, undefined]) throws(() => pop.call(x));
for (const x of [true, false, 17, Symbol("boxed"), 13n]) eq(pop.call(x), undefined);
throws(() => pop.call("abc"));
throws(() => pop.call(""));
throws(() => pop.call(new Int16Array([1])));
let getPopCalls = 0,
  receiver = [1, object];
Object.defineProperty(receiver, "pop", {
  get() {
    getPopCalls++;
    std.gc();
    return pop;
  },
  configurable: true,
});
eq(receiver.pop(), object);
eq(getPopCalls, 1);
eq(receiver.length, 1);
let custom = [1, 2];
custom.pop = function () {
  std.gc();
  return this.length + 100;
};
eq(custom.pop(), 102);
eq(custom.length, 2);
let saved = Array.prototype.pop;
try {
  Array.prototype.pop = function () {
    return "replaced";
  };
  eq([1].pop(), "replaced");
  eq(saved.call([object]), object);
} finally {
  Array.prototype.pop = saved;
}
let bound = pop.bind([object]);
eq(bound(), object);
eq(bound(), undefined);
eq([1, 2, 3].shift(), 1);
eq(JSON.stringify([1, 2, 3]), "[1,2,3]");
print(JSON.stringify({ fixture: "dense-array-pop-boundary-r4406", checks, status: "passed" }));
