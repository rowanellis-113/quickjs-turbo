import * as std from "qjs:std";
let checks = 0;
function eq(a, b, label) {
  checks++;
  if (!Object.is(a, b)) throw Error(label + ": " + a + " != " + b);
}
const intrinsic = String.prototype.localeCompare;
const descriptor = Object.getOwnPropertyDescriptor(String.prototype, "localeCompare");
const f = function (other) {
  return this.left.localeCompare(other.right);
};
const alias = function (other) {
  return this.left.compareAlias(other.right);
};
const pairs = [
  ["a", "b"],
  ["same", "same"],
  ["b", "a"],
  ["", ""],
  ["", "x"],
  ["x", ""],
  ["a\0x", "a\0z"],
  ["é", "à"],
  ["ÿ", "þ"],
  ["a".repeat(96), "a".repeat(95) + "b"],
];
for (let i = 0; i < 384; i++)
  for (const [a, b] of pairs) {
    const x = { left: a, f },
      y = { right: b };
    if (i % 3 === 0) {
      x.extra = i;
      y.extra = "value";
    }
    eq(x.f(y), intrinsic.call(a, b), "flat exact " + i);
    eq(x.f(y, { unused: i }, []), intrinsic.call(a, b), "extra args " + i);
  }
for (const [a, b] of [
  ["𝌆", "é"],
  ["e\u0301", "é"],
  ["abc".repeat(80).slice(1, 113), "xbc"],
  ["a" + "b".repeat(512), "c"],
])
  eq(f.call({ left: a }, { right: b }), intrinsic.call(a, b), "wide/rope/slice");
const both = { left: "same", right: "same", f };
eq(both.f(both), 0, "alias");
String.prototype.compareAlias = intrinsic;
try {
  for (let i = 0; i < 64; i++)
    eq(alias.call({ left: "cat" }, { right: "dog" }), -1, "arbitrary method atom");
} finally {
  delete String.prototype.compareAlias;
}
let order = [];
const a = {
  get left() {
    order.push("left");
    std.gc();
    return "a";
  },
  f,
};
const b = {
  get right() {
    order.push("right");
    std.gc();
    return "b";
  },
};
eq(a.f(b), -1, "getters/GC");
eq(order.join(","), "left,right", "getter order");
const base = { left: "x", f },
  peer = { right: "y" };
let traps = 0;
const proxy = new Proxy(base, {
  get(t, k, r) {
    traps++;
    return Reflect.get(t, k, r);
  },
});
eq(proxy.f(peer), -1, "proxy receiver");
eq(traps, 2, "receiver traps");
traps = 0;
const argProxy = new Proxy(peer, {
  get(t, k, r) {
    traps++;
    return Reflect.get(t, k, r);
  },
});
eq(base.f(argProxy), -1, "proxy argument");
eq(traps, 1, "argument traps");
let methodGets = 0;
try {
  Object.defineProperty(String.prototype, "localeCompare", {
    configurable: true,
    get() {
      methodGets++;
      order.push("method");
      std.gc();
      return intrinsic;
    },
  });
  order = [];
  eq(a.f(b), -1, "method getter");
  eq(order.join(","), "left,method,right", "method before argument getter");
  eq(methodGets, 1, "one method getter");
} finally {
  Object.defineProperty(String.prototype, "localeCompare", descriptor);
}
try {
  String.prototype.localeCompare = function (v) {
    return [String(this), v].join("/");
  };
  eq(base.f(peer), "x/y", "replacement target");
  String.prototype.localeCompare = intrinsic;
  for (let i = 0; i < 64; i++) eq(base.f(peer), -1, "restored target");
} finally {
  Object.defineProperty(String.prototype, "localeCompare", descriptor);
}
const objectLC = Object.getOwnPropertyDescriptor(Object.prototype, "localeCompare");
try {
  delete String.prototype.localeCompare;
  Object.prototype.localeCompare = intrinsic;
  eq(base.f(peer), -1, "inherited method");
} finally {
  if (objectLC) Object.defineProperty(Object.prototype, "localeCompare", objectLC);
  else delete Object.prototype.localeCompare;
  Object.defineProperty(String.prototype, "localeCompare", descriptor);
}
for (const bad of [null, undefined]) {
  let expected, actual;
  try {
    intrinsic.call(bad, "a");
  } catch (e) {
    expected = e.constructor;
  }
  try {
    f.call({ left: bad }, { right: "a" });
  } catch (e) {
    actual = e.constructor;
  }
  eq(actual, expected, "null/undefined abrupt");
}
let converted = 0;
const convert = {
  toString() {
    converted++;
    std.gc();
    return "b";
  },
};
eq(base.f({ right: convert }), intrinsic.call("x", "b"), "argument coercion");
eq(converted, 1, "one conversion");
for (let i = 0; i < 96; i++) {
  const x = { left: "a", f },
    y = { right: "b" };
  eq(x.f(y), -1, "shape initial");
  Object.defineProperty(x, "left", {
    get() {
      return "z";
    },
    configurable: true,
  });
  eq(x.f(y), 1, "data to accessor");
  delete x.left;
  Object.setPrototypeOf(x, { left: "c" });
  eq(x.f(y), 1, "own to inherited");
  Object.defineProperty(x, "left", { value: "a", writable: true, configurable: true });
  eq(x.f(y), -1, "own restored");
}
for (const literal of [
  function () {
    return null;
  },
  function () {
    return true;
  },
  function () {
    return false;
  },
  function () {
    return 3;
  },
]) {
  const expected = literal();
  for (let i = 0; i < 512; i++) eq(literal(), expected, "existing leaf kind preserved");
}
print("FRAME_COMPOUND_LEAF_OK " + checks);
