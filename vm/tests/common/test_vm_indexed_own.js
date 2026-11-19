"use strict";
function equal(a, b) {
  if (!Object.is(a, b)) throw Error(String(a) + " != " + String(b));
}
function get(a, k) {
  return a[k];
}
function put(a, k, v) {
  a[k] = v;
  return a[k];
}
function method(a, k) {
  return a[k]();
}
function shapeArray(reverse = false) {
  const a = [];
  Object.defineProperty(a, reverse ? 31 : 0, { value: 0, writable: true, configurable: true });
  for (let j = 0; j < 32; j++) {
    const i = reverse ? 31 - j : j;
    a[i] = i + 0.25;
  }
  return a;
}
for (const reverse of [false, true]) {
  const a = shapeArray(reverse);
  for (let j = 0; j < 300; j++) {
    const i = j % 32;
    equal(get(a, i), i + 0.25);
    equal(put(a, i, i + 0.25), i + 0.25);
  }
  const values = [
    undefined,
    null,
    true,
    false,
    NaN,
    -0,
    1.75,
    "value",
    Symbol("key"),
    {},
    [],
    () => 42,
    1n,
  ];
  for (const value of values) {
    a[3] = 0;
    equal(put(a, 3, value), value);
    equal(get(a, 3), value);
    put(a, 3, 0);
  }
  a[4] = function () {
    return this;
  };
  equal(method(a, 4), a);
  a[7] = a;
  equal(get(a, 7), a);
  put(a, 7, 21);
  equal(a[7], 21);
  for (let n = 0; n < 60; n++) {
    delete a[5];
    a[5] = n;
    equal(get(a, 5), n);
    equal(put(a, 5, n + 1), n + 1);
    a["extra" + n] = n;
  }
  let reads = 0,
    writes = 0;
  Object.defineProperty(a, 6, {
    configurable: true,
    get() {
      reads++;
      return 91;
    },
    set(v) {
      writes += v;
    },
  });
  equal(get(a, 6), 91);
  put(a, 6, 2);
  equal(reads, 2);
  equal(writes, 2);
  Object.defineProperty(a, 8, { value: 12, writable: false });
  let threw = false;
  try {
    put(a, 8, 13);
  } catch (e) {
    threw = e instanceof TypeError;
  }
  equal(threw, true);
  equal(get(a, 8), 12);
  Object.defineProperty(a, "length", { writable: false });
  equal(put(a, 9, 44), 44);
  threw = false;
  try {
    put(a, 40, 1);
  } catch (e) {
    threw = e instanceof TypeError;
  }
  equal(threw, true);
}
const prototype = [];
let seen = 0;
Object.defineProperty(prototype, 3, {
  configurable: true,
  get() {
    return 77;
  },
  set(v) {
    seen = v;
  },
});
const inherited = [];
Object.defineProperty(inherited, 0, { value: 1, writable: true, configurable: true });
Object.setPrototypeOf(inherited, prototype);
equal(get(inherited, 3), 77);
put(inherited, 3, 19);
equal(seen, 19);
equal(Object.hasOwn(inherited, 3), false);
const frozen = Object.freeze(shapeArray());
let threw = false;
try {
  put(frozen, 1, 2);
} catch (e) {
  threw = e instanceof TypeError;
}
equal(threw, true);
const a = shapeArray();
for (const key of [-1, 2147483647, 2147483648, 4294967295, "01", Symbol("x")]) {
  a[key] = 123;
  equal(get(a, key), 123);
  equal(put(a, key, 124), 124);
}
const typed = new Int32Array(8);
equal(put(typed, 3, 17), 17);
equal(get(typed, 3), 17);
equal(get(typed, 99), undefined);
let proxyGets = 0,
  proxySets = 0;
const proxy = new Proxy(shapeArray(), {
  get(t, k, r) {
    proxyGets++;
    return Reflect.get(t, k, r);
  },
  set(t, k, v, r) {
    proxySets++;
    return Reflect.set(t, k, v, r);
  },
});
equal(get(proxy, 2), 2.25);
equal(put(proxy, 2, 9), 9);
equal(proxyGets, 2);
equal(proxySets, 1);
const ordinary = { 0: 1 };
equal(put(ordinary, 0, 2), 2);
print("INDEXED_OWN_SEMANTICS passed");
