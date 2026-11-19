import * as std from "qjs:std";
let checks = 0;
function eq(a, b) {
  ++checks;
  if (!Object.is(a, b))
    throw Error("STRING_PROTO " + checks + " " + String(a) + " != " + String(b));
}
function throws(f, T = TypeError) {
  let e;
  try {
    f();
  } catch (x) {
    e = x;
  }
  eq(e instanceof T, true);
}
const name = "__qjs_string_proto_r4462",
  proto = String.prototype;
const original = Object.getOwnPropertyDescriptor(proto, name);
const oldChain = Object.getPrototypeOf(proto);
function invoke(s, x) {
  return s.__qjs_string_proto_r4462(x);
}
function install(value) {
  Object.defineProperty(proto, name, { value, writable: true, configurable: true });
}
function first(x) {
  "use strict";
  eq(typeof this, "string");
  return this.length + x;
}
try {
  install(first);
  for (let i = 0; i < 300; i++) eq(invoke("hello", i), 5 + i);
  for (const s of [
    "",
    "é",
    "中é",
    "\ud800",
    "😀",
    "x".repeat(4096),
    "x".repeat(4096) + "y".repeat(4096),
  ])
    for (let i = 0; i < 20; i++) eq(invoke(s, i), s.length + i);
  install(function (x) {
    "use strict";
    return this + ":" + x;
  });
  for (let i = 0; i < 100; i++) eq(invoke("ab", i), "ab:" + i);
  for (let i = 0; i < 80; i++) {
    const marker = { i };
    install(function () {
      return marker;
    });
    eq(invoke("x", 0), marker);
    install(function () {
      return i;
    });
    eq(invoke("x", 0), i);
    std.gc();
  }
  // Data slots of every non-callable type still reach the normal call error,
  // with the receiver and duplicated property value released exactly once.
  for (const v of [
    undefined,
    null,
    false,
    19,
    -0,
    1.25,
    17n,
    2n ** 80n,
    Symbol("v"),
    "value",
    {},
    [],
  ]) {
    install(v);
    throws(() => invoke("abc", 0));
    std.gc();
  }
  install(
    function (a, b) {
      return a + b;
    }.bind(null, 7),
  );
  eq(invoke("x", 8), 15);
  let proxyCalls = 0;
  install(
    new Proxy(
      function (x) {
        return x + 11;
      },
      {
        apply(f, t, a) {
          proxyCalls++;
          std.gc();
          return Reflect.apply(f, t, a);
        },
      },
    ),
  );
  eq(invoke("ab", 3), 14);
  eq(proxyCalls, 1);
  let gets = 0;
  Object.defineProperty(proto, name, {
    configurable: true,
    get: function () {
      "use strict";
      gets++;
      eq(typeof this, "string");
      std.gc();
      return first;
    },
  });
  for (let i = 0; i < 80; i++) eq(invoke("xyz", i), 3 + i);
  eq(gets, 80);
  Object.defineProperty(proto, name, {
    configurable: true,
    get() {
      std.gc();
      throw new RangeError("getter");
    },
  });
  throws(() => invoke("abc", 0), RangeError);
  Object.defineProperty(proto, name, {
    configurable: true,
    get() {
      install(first);
      std.gc();
      return first;
    },
  });
  eq(invoke("abcd", 3), 7);
  eq(invoke("abcd", 4), 8);
  delete proto[name];
  throws(() => invoke("x", 0));
  Object.defineProperty(Object.prototype, name, {
    configurable: true,
    value: function (x) {
      "use strict";
      return this.length + x + 100;
    },
  });
  eq(invoke("abcd", 7), 111);
  delete Object.prototype[name];
  const alternate = {};
  Object.defineProperty(alternate, name, { value: first, configurable: true });
  Object.setPrototypeOf(proto, alternate);
  eq(invoke("abcd", 9), 13);
  let chainGets = 0;
  Object.defineProperty(alternate, name, {
    configurable: true,
    get() {
      chainGets++;
      std.gc();
      return first;
    },
  });
  eq(invoke("abcd", 10), 14);
  eq(chainGets, 1);
  const proxied = new Proxy(
    {},
    {
      get(o, k, r) {
        if (k === name) {
          std.gc();
          return first;
        }
        return Reflect.get(o, k, r);
      },
    },
  );
  Object.setPrototypeOf(proto, proxied);
  eq(invoke("abcd", 11), 15);
  Object.setPrototypeOf(proto, oldChain);
  install(first);
  Object.seal(proto[name]);
  eq(invoke("abc", 1), 4);
  install(function (x) {
    "use strict";
    return this.length + x;
  });
  for (const o of [
    {
      [name](x) {
        return x + 1;
      },
    },
    new String("abc"),
  ]) {
    if (typeof o === "object" && o instanceof String) eq(invoke(o, 2), 5);
    else eq(invoke(o, 2), 3);
  }
  install(first);
  // An indexed receiver character and its virtual length shadow prototypes.
  const zero = Object.getOwnPropertyDescriptor(proto, "0");
  Object.defineProperty(proto, "0", {
    configurable: true,
    value: function () {
      return 91;
    },
  });
  try {
    throws(() => "abc"["0"]());
    eq(""["0"](), 91);
    throws(() => "abc".length());
  } finally {
    if (zero) Object.defineProperty(proto, "0", zero);
    else delete proto["0"];
  }
  const symbol = Symbol("method");
  Object.defineProperty(proto, symbol, { configurable: true, value: first });
  try {
    eq("abcd"[symbol](2), 6);
  } finally {
    delete proto[symbol];
  }
  for (let i = 0; i < 100; i++) {
    const s = "ab中😀";
    eq(s.slice(1, 4), "b中\ud83d");
    eq(s.substring(1, 3), "b中");
    eq(s.charCodeAt(2), 20013);
    eq(s.indexOf("中"), 2);
  }
  eq(invoke("last", 7), 11);
} finally {
  Object.setPrototypeOf(proto, oldChain);
  if (original) Object.defineProperty(proto, name, original);
  else delete proto[name];
  delete Object.prototype[name];
}
std.gc();
print(JSON.stringify({ fixture: "msvc-string-proto-boundary-r4462b", status: "passed", checks }));
