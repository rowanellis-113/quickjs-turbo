"use strict";
let checks = 0;
function equal(a, b, label) {
  if (!Object.is(a, b)) throw Error(label + ": " + String(a) + " != " + String(b));
  checks++;
}
function read(a, k) {
  let value = a[k];
  return value;
}
function write(a, k, v) {
  a[k] = v;
  return a;
}
function method(a, k, v) {
  let value = a[k](v);
  return value;
}
function inspectThis(v) {
  equal(this.tag, 37, "indexed method receiver");
  return v + 1;
}
function sparse(v) {
  let a = [v, 0, v + 1];
  delete a[1];
  return a;
}
function ordinaryInstance(value, ctor) {
  let out = value instanceof ctor;
  return out;
}
let sum = 0;
for (let n = 0; n < 64; n++) {
  const a = sparse(n);
  equal(read(a, 0), n, "sparse own0");
  equal(read(a, 2), n + 1, "sparse own2");
  equal(write(a, 2, n + 2), a, "sparse write identity");
  equal(read(a, 2), n + 2, "sparse own store");
  sum += read(a, 0);
  a.tag = 37;
  write(a, 0, inspectThis);
  equal(method(a, 0, n), n + 1, "indexed method");
  const value = { n };
  value.self = value;
  write(a, 2, value);
  equal(read(a, 2), value, "sparse reference store");
  write(a, 2, 0);
  gc();
}
equal(sum, 2016, "sparse checksum");
const dense = [{ tag: 1 }, 2, 3];
equal(read(dense, 0), dense[0], "dense reference");
write(dense, 1, 9);
equal(read(dense, 1), 9, "dense primitive store");
write(dense, 3, 4);
equal(dense.length, 4, "array append");
const high = [];
high[65537] = 9;
equal(read(high, 65537), 9, "large sparse index");
write(high, 65537, 11);
equal(high[65537], 11, "large sparse store");
const negative = [];
negative[-1] = 8;
equal(read(negative, -1), 8, "negative property");
const max = [];
max[4294967295] = 17;
equal(read(max, 4294967295), 17, "nonarray-index number");
const symbol = Symbol("index"),
  plain = { [symbol]: 23 };
equal(read(plain, symbol), 23, "symbol property");
let conversions = 0;
const key = {
  toString() {
    conversions++;
    gc();
    return "2";
  },
};
const keyed = sparse(4);
equal(read(keyed, key), 5, "converting get key");
equal(conversions, 1, "get key once");
write(keyed, key, 29);
equal(conversions, 2, "put key once");
equal(keyed[2], 29, "converting store");
keyed[2] = inspectThis;
keyed.tag = 37;
equal(method(keyed, key, 7), 8, "converting method key");
equal(conversions, 3, "method key once");
let gets = 0,
  sets = 0;
const inherited = Object.create(Array.prototype);
Object.defineProperty(inherited, "1", {
  get() {
    gets++;
    gc();
    return 41;
  },
  set(v) {
    sets++;
    gc();
    equal(v, 42, "inherited setter value");
  },
});
const hole = sparse(0);
Object.setPrototypeOf(hole, inherited);
equal(read(hole, 1), 41, "hole prototype getter");
write(hole, 1, 42);
equal(gets, 1, "getter once");
equal(sets, 1, "setter once");
const frozen = sparse(1);
Object.defineProperty(frozen, "2", { writable: false });
let threw = false;
try {
  write(frozen, 2, 9);
} catch (e) {
  threw = e instanceof TypeError;
}
equal(threw, true, "readonly sparse store");
Object.preventExtensions(frozen);
threw = false;
try {
  write(frozen, 7, 1);
} catch (e) {
  threw = e instanceof TypeError;
}
equal(threw, true, "nonextensible store");
const readonly = [1, 2];
Object.defineProperty(readonly, "length", { writable: false });
threw = false;
try {
  write(readonly, 2, 3);
} catch (e) {
  threw = e instanceof TypeError;
}
equal(threw, true, "readonly length");
let traps = 0;
const proxy = new Proxy(sparse(2), {
  get(a, k, r) {
    traps++;
    gc();
    return Reflect.get(a, k, r);
  },
  set(a, k, v, r) {
    traps++;
    gc();
    return Reflect.set(a, k, v, r);
  },
});
equal(read(proxy, 0), 2, "proxy get");
write(proxy, 2, 7);
equal(proxy[2], 7, "proxy set");
equal(traps, 3, "proxy operations once");
for (const C of [
  Int8Array,
  Uint8Array,
  Uint8ClampedArray,
  Int16Array,
  Uint16Array,
  Int32Array,
  Uint32Array,
  Float32Array,
  Float64Array,
]) {
  const a = new C(4);
  write(a, 1, 123);
  equal(read(a, 1), 123, "typed store/read");
  equal(read(a, 4), undefined, "typed bounds");
}
const uint = new Uint32Array([4294967295]);
equal(read(uint, 0), 4294967295, "uint32 double");
const big = new BigInt64Array(2);
write(big, 0, 17n);
equal(read(big, 0), 17n, "BigInt typed fallback");
const marker = {};
const broken = {
  toString() {
    gc();
    throw marker;
  },
};
threw = false;
try {
  read(keyed, broken);
} catch (e) {
  threw = e === marker;
}
equal(threw, true, "get key exception");
threw = false;
try {
  write(keyed, broken, { self: keyed });
} catch (e) {
  threw = e === marker;
}
equal(threw, true, "put key exception");
function A() {}
function B() {}
const a = new A();
for (let n = 0; n < 96; n++) {
  equal(ordinaryInstance(a, A), true, "default instanceof hit");
  equal(ordinaryInstance(a, B), false, "default instanceof miss");
  equal(ordinaryInstance(A, A), false, "aliased operands");
}
const original = A.prototype;
A.prototype = {};
equal(ordinaryInstance(a, A), false, "live constructor prototype");
A.prototype = original;
equal(ordinaryInstance(a, A.bind(null)), true, "bound constructor fallback");
let hasCalls = 0;
const custom = {
  get [Symbol.hasInstance]() {
    hasCalls++;
    gc();
    return function (v) {
      gc();
      return v === a;
    };
  },
};
equal(ordinaryInstance(a, custom), true, "custom hasInstance");
equal(hasCalls, 1, "hasInstance getter once");
const wrapped = new Proxy(A, {
  get(t, k, r) {
    gc();
    return Reflect.get(t, k, r);
  },
});
equal(ordinaryInstance(a, wrapped), true, "proxy constructor");
let deep = a;
for (let i = 0; i < 40; i++) deep = Object.create(deep);
equal(ordinaryInstance(deep, A), true, "deep prototype fallback");
threw = false;
try {
  ordinaryInstance(a, 1);
} catch (e) {
  threw = e instanceof TypeError;
}
equal(threw, true, "noncallable RHS");
A.prototype = 1;
threw = false;
try {
  ordinaryInstance(a, A);
} catch (e) {
  threw = e instanceof TypeError;
}
equal(threw, true, "primitive constructor prototype");
A.prototype = original;
gc();
print("LINUX_INDEXED_OK checks=" + checks);
