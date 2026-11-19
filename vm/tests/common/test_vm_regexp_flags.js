import * as std from "qjs:std";
const names = [
  "hasIndices",
  "global",
  "ignoreCase",
  "multiline",
  "dotAll",
  "unicode",
  "unicodeSets",
  "sticky",
];
const letters = "dgimsuvy";
const proto = RegExp.prototype;
const desc = Object.fromEntries(names.map((n) => [n, Object.getOwnPropertyDescriptor(proto, n)]));
const flags = Object.getOwnPropertyDescriptor(proto, "flags").get;
const rows = [];
function eq(a, b) {
  if (Object.is(a, b)) return;
  if (JSON.stringify(a) !== JSON.stringify(b)) throw Error(JSON.stringify([a, b]));
}
function test(n, f) {
  rows.push([n, f()]);
}
for (let bits = 0; bits < 256; bits++) {
  if (bits & 32 && bits & 64) continue;
  const s = [...letters].filter((c, i) => bits & (1 << i)).join("");
  test("native-" + bits, () => {
    const r = new RegExp("a", s);
    eq(flags.call(r), s);
    return s;
  });
}
for (let i = 0; i < 8; i++)
  for (const value of [false, true, undefined, {}, 0, "yes"]) {
    test("own-" + i + "-" + String(value), () => {
      const r = /a/;
      Object.defineProperty(r, names[i], { value });
      const expected = value ? letters[i] : "";
      eq(flags.call(r), expected);
      return expected;
    });
  }
for (let i = 0; i < 8; i++)
  test("swapped-native-" + i, () => {
    const r = new RegExp("a", "dgimsy");
    Object.defineProperty(r, "global", { get: desc[names[i]].get });
    const expected = i === 5 || i === 6 ? "dimsy" : "dgimsy";
    eq(flags.call(r), expected);
    return expected;
  });
test("subclass", () => {
  class R extends RegExp {
    get global() {
      return true;
    }
  }
  const r = new R("a", "m");
  eq(r.flags, "gm");
  return r.flags;
});
test("proxy-order", () => {
  const log = [];
  const r = new Proxy(
    {},
    {
      get(t, k, receiver) {
        log.push(k);
        return k === "global" || k === "sticky";
      },
    },
  );
  eq(flags.call(r), "gy");
  eq(log, names);
  return log;
});
test("proxy-prototype", () => {
  const log = [];
  const r = /a/;
  Object.setPrototypeOf(
    r,
    new Proxy(
      {},
      {
        get(t, k, receiver) {
          if (receiver !== r) throw Error("receiver identity");
          log.push(k);
          return true;
        },
      },
    ),
  );
  eq(flags.call(r), letters);
  eq(log, names);
  return log;
});
test("revoked-proxy", () => {
  const r = Proxy.revocable({}, {});
  r.revoke();
  let e;
  try {
    flags.call(r.proxy);
  } catch (x) {
    e = x.name;
  }
  eq(e, "TypeError");
  return e;
});
test("native-proxy-receiver", () => {
  let e;
  try {
    flags.call(new Proxy(/a/, {}));
  } catch (x) {
    e = x.name;
  }
  eq(e, "TypeError");
  return e;
});
test("generic-order-and-bool", () => {
  const log = [],
    r = {};
  for (const name of names)
    Object.defineProperty(r, name, {
      get() {
        log.push(name);
        return {
          valueOf() {
            throw Error("no coercion");
          },
        };
      },
    });
  eq(flags.call(r), letters);
  eq(log, names);
  return log;
});
for (const name of names)
  test("abrupt-" + name, () => {
    const log = [],
      marker = {},
      r = /a/;
    for (const n of names)
      Object.defineProperty(r, n, {
        get() {
          log.push(n);
          if (n === name) throw marker;
          return true;
        },
      });
    let e;
    try {
      flags.call(r);
    } catch (x) {
      e = x;
    }
    if (e !== marker) throw Error("exception identity");
    eq(log, names.slice(0, names.indexOf(name) + 1));
    return log;
  });
test("mutate-next-property", () => {
  const r = /a/;
  Object.defineProperty(r, "hasIndices", {
    get() {
      Object.defineProperty(r, "global", { value: true });
      return false;
    },
  });
  eq(flags.call(r), "g");
  return r.flags;
});
test("mutate-prototype", () => {
  const r = /a/;
  Object.defineProperty(r, "hasIndices", {
    get() {
      Object.defineProperty(proto, "global", {
        get() {
          std.gc();
          return true;
        },
        configurable: true,
      });
      return false;
    },
  });
  try {
    eq(flags.call(r), "g");
    return r.flags;
  } finally {
    Object.defineProperty(proto, "global", desc.global);
  }
});
test("mutate-bytecode", () => {
  const r = /a/;
  if (typeof r.compile !== "function") return "not available";
  Object.defineProperty(r, "hasIndices", {
    get() {
      r.compile("b", "imy");
      return false;
    },
  });
  eq(flags.call(r), "imy");
  return r.flags;
});
test("reentry", () => {
  const r = /a/m;
  Object.defineProperty(r, "global", {
    get() {
      std.gc();
      eq(/z/dg.flags, "dg");
      return false;
    },
  });
  eq(flags.call(r), "m");
  return r.flags;
});
for (const value of [null, undefined, 0, false, "x", Symbol("x")])
  test("invalid-" + String(value), () => {
    let e;
    try {
      flags.call(value);
    } catch (x) {
      e = x.name;
    }
    eq(e, "TypeError");
    return e;
  });
for (const value of [{}, [], RegExp.prototype])
  test("generic-" + String(value), () => {
    eq(flags.call(value), "");
    return "";
  });
// Native getter identity alone does not identify its flag: magic and the
// live property name must still agree after edits to the prototype itself.
for (let i = 0; i < names.length; i++) {
  test("prototype-native-magic-" + i, () => {
    const replacement = desc[names[(i + 3) % names.length]].get;
    Object.defineProperty(proto, names[i], { ...desc[names[i]], get: replacement });
    try {
      const r = /a/dgimsy;
      const wanted = names
        .filter((n) => r[n])
        .map((n) => letters[names.indexOf(n)])
        .join("");
      std.gc();
      eq(flags.call(r), wanted);
      return wanted;
    } finally {
      Object.defineProperty(proto, names[i], desc[names[i]]);
    }
  });
  test("prototype-delete-restore-" + i, () => {
    delete proto[names[i]];
    try {
      const r = /a/dgimsy;
      const wanted = names
        .filter((n) => r[n])
        .map((n) => letters[names.indexOf(n)])
        .join("");
      eq(flags.call(r), wanted);
      return wanted;
    } finally {
      Object.defineProperty(proto, names[i], desc[names[i]]);
    }
  });
}
print(JSON.stringify({ checks: rows.length, rows }));
