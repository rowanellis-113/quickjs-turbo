import { gc } from "qjs:std";
let checks = 0;
function equal(a, b) {
  checks++;
  if (!Object.is(a, b)) throw Error("object proto check " + checks + ": " + a + " != " + b);
}
function invoke(o, n) {
  return o.run(n);
}
function expectThrow(f, kind) {
  let thrown = false;
  try {
    f();
  } catch (e) {
    thrown = e instanceof kind;
  }
  equal(thrown, true);
}
const proto = {
  run(n) {
    return this.marker + n;
  },
};
const receiver = Object.create(proto);
receiver.marker = 17;
for (let i = 0; i < 128; i++) {
  equal(invoke(receiver, i), 17 + i);
  proto.run = function (n) {
    return this.marker - n;
  };
  equal(invoke(receiver, i), 17 - i);
  receiver.run = function (n) {
    return this.marker * 2 + n;
  };
  equal(invoke(receiver, i), 34 + i);
  delete receiver.run;
  delete proto.run;
  expectThrow(() => invoke(receiver, i), TypeError);
  proto.run = function (n) {
    return this.marker + n;
  };
}
const token = { value: 91 };
proto.run = function () {
  return token;
};
for (let i = 0; i < 128; i++) {
  equal(invoke(receiver, i), token);
  gc();
}
let getters = 0;
Object.defineProperty(receiver, "run", {
  configurable: true,
  get() {
    getters++;
    gc();
    return function (n) {
      return this.marker + 100 + n;
    };
  },
});
for (let i = 0; i < 64; i++) equal(invoke(receiver, i), 117 + i);
equal(getters, 64);
delete receiver.run;
Object.defineProperty(proto, "run", {
  configurable: true,
  get() {
    getters++;
    gc();
    return function (n) {
      return this.marker + 200 + n;
    };
  },
});
for (let i = 0; i < 64; i++) equal(invoke(receiver, i), 217 + i);
equal(getters, 128);
Object.defineProperty(receiver, "run", {
  configurable: true,
  get() {
    throw new RangeError("own shadow");
  },
});
expectThrow(() => invoke(receiver, 0), RangeError);
delete receiver.run;
Object.defineProperty(proto, "run", { configurable: true, value: 1 });
expectThrow(() => invoke(receiver, 0), TypeError);
Object.defineProperty(proto, "run", {
  configurable: true,
  writable: true,
  value(n) {
    return this.marker + n;
  },
});
for (let i = 0; i < 96; i++) {
  const next = {
    run(n) {
      return this.marker + 300 + n;
    },
  };
  Object.setPrototypeOf(receiver, next);
  equal(invoke(receiver, i), 317 + i);
  Object.setPrototypeOf(receiver, proto);
  equal(invoke(receiver, i), 17 + i);
  if (!(i & 7)) gc();
}
let traps = 0;
const proxy = new Proxy(
  {
    run(n) {
      return this.marker + 400 + n;
    },
  },
  {
    get(t, k, r) {
      traps++;
      gc();
      return Reflect.get(t, k, r);
    },
  },
);
Object.setPrototypeOf(receiver, proxy);
equal(invoke(receiver, 2), 419);
equal(traps, 1);
const proxied = new Proxy(receiver, {
  get(t, k, r) {
    return Reflect.get(t, k, r);
  },
});
equal(invoke(proxied, 3), 420);
Object.setPrototypeOf(receiver, null);
expectThrow(() => invoke(receiver, 0), TypeError);
const deep = Object.create(proto);
Object.setPrototypeOf(receiver, deep);
equal(invoke(receiver, 4), 21);
Object.setPrototypeOf(receiver, proto);
const bound = function (n) {
  return this.marker + n;
}.bind({ marker: 500 });
proto.run = bound;
equal(invoke(receiver, 3), 503);
proto.run = new Proxy(
  function (n) {
    return this.marker + n;
  },
  {
    apply(fn, t, args) {
      gc();
      return Reflect.apply(fn, t, args) + 600;
    },
  },
);
equal(invoke(receiver, 3), 620);
proto.run = function (n) {
  "use strict";
  return this === receiver && n === 9;
};
equal(invoke(receiver, 9), true);
const locked = Object.freeze({
  run(n) {
    return this.marker + n;
  },
});
Object.setPrototypeOf(receiver, locked);
equal(invoke(receiver, 2), 19);
const indexProto = {
  0(n) {
    return this.marker + n;
  },
};
const indexed = Object.create(indexProto);
indexed.marker = 700;
equal(indexed[0](3), 703);
const symbol = Symbol("method");
indexProto[symbol] = function (n) {
  return this.marker + n;
};
equal(indexed[symbol](4), 704);
const arrayProto = Object.create(Array.prototype);
arrayProto.run = function (n) {
  return this.length + n;
};
const array = [1, 2];
Object.setPrototypeOf(array, arrayProto);
equal(invoke(array, 5), 7);
equal("abcd".slice(1), "bcd");
equal(JSON.stringify({ a: 1, b: [2, 3] }), '{"a":1,"b":[2,3]}');
print("OBJECT_PROTO_BOUNDARY_PASS checks=" + checks);
