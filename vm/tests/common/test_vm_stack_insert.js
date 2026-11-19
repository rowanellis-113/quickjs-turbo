"use strict";
// Assignment result and destination must retain independent original owners.
let checks = 0;
function check(v, m) {
  checks++;
  if (!v) throw Error(m);
}
function put(a, k, v) {
  return (a[k] = v);
}
function plus(a, k, v) {
  return (a[k] += v);
}
function logical(a, k, v) {
  return (a[k] ||= v);
}
const values = [
  0,
  -0,
  1,
  -1,
  2147483647,
  -2147483648,
  NaN,
  Infinity,
  -Infinity,
  0.25,
  undefined,
  null,
  true,
  false,
  "small",
  "wide\u4e2d",
  Symbol("key"),
  1n,
  2n ** 100n,
  {},
  [],
  function () {},
  /x/,
];
for (let turn = 0; turn < 40; turn++)
  for (const v of values) {
    const a = [];
    const result = put(a, 3, v);
    check(Object.is(result, v) && Object.is(a[3], v), "assignment value");
    a.length = 0;
    check(Object.is(result, v), "result survives receiver truncation");
    const o = {};
    check(Object.is(put(o, "x", v), v) && Object.is(o.x, v), "named receiver");
    const alias = [v];
    check(Object.is(put(alias, 0, alias[0]), v) && Object.is(alias[0], v), "alias");
  }
for (let i = 0; i < 500; i++) {
  const a = [i];
  check(plus(a, 0, 0.5) === i + 0.5 && a[0] === i + 0.5, "compound number");
  a[0] = "a";
  check(plus(a, 0, "b") === "ab" && a[0] === "ab", "compound string");
  a[0] = 0;
  const v = { i };
  check(logical(a, 0, v) === v && a[0] === v, "logical result");
}
const events = [];
const v = {};
const receiver = {
  set x(x) {
    events.push(x);
  },
};
check(put(receiver, "x", v) === v && events[0] === v, "setter result");
const key = {
  toString() {
    events.push("key");
    return "x";
  },
};
check(put(receiver, key, v) === v && events[1] === "key" && events[2] === v, "key coercion/order");
const proxy = new Proxy(
  {},
  {
    set(t, k, x) {
      events.push("proxy");
      return Reflect.set(t, k, x);
    },
  },
);
check(put(proxy, 3, v) === v && proxy[3] === v, "proxy result");
const frozen = Object.freeze([]);
let threw = false;
try {
  put(frozen, 0, v);
} catch (e) {
  threw = e instanceof TypeError;
}
check(threw, "strict throwing destination");
const custom = {
  valueOf() {
    if (typeof std !== "undefined") std.gc();
    return 7;
  },
};
check(plus([custom], 0, 3) === 10, "coercion and optional GC");
if (typeof std !== "undefined") std.gc();
print("STACK_INSERT_OK " + checks);
