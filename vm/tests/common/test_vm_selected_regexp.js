"use strict";
/* Targeted NG migration checks; the emitted values also support differential replay. */
const rows = [];
function assert(v, message) {
  if (!v) throw new Error(message || "assertion");
}
function equal(a, b, message) {
  assert(JSON.stringify(a) === JSON.stringify(b), message || JSON.stringify([a, b]));
}
function test(name, body) {
  rows.push([name, body()]);
}
function custom(result, flags = "") {
  let used = false;
  return {
    flags,
    lastIndex: 0,
    exec() {
      if (used) return null;
      used = true;
      return result;
    },
  };
}
function replace(rx, text, callback) {
  return RegExp.prototype[Symbol.replace].call(rx, text, callback);
}

test("native-order", () => {
  const calls = [];
  const result = "ab a".replace(/(?<word>a)(b)?/g, function (...args) {
    assert(this === undefined);
    calls.push([args.length, args[0], args[1], args[2], args[3], args[4], args[5].word]);
    return "[" + args[1] + "]";
  });
  equal(result, "[a] [a]");
  equal(calls, [
    [6, "ab", "a", "b", 0, "ab a", "a"],
    [6, "a", "a", undefined, 3, "ab a", "a"],
  ]);
  return [result, calls];
});
for (let captures = 0; captures <= 18; captures++) {
  for (const groups of [false, true])
    test("argv-" + captures + "-" + groups, () => {
      const match = { length: captures, 0: "a", index: 1 };
      for (let i = 1; i < captures; i++) match[i] = i % 3 ? i : undefined;
      if (groups) match.groups = { key: "G" };
      let snapshot;
      const result = replace(custom(match), "xay", function (...args) {
        snapshot = args;
        assert(args.length === Math.max(1, captures) + 2 + (groups ? 1 : 0));
        equal(args[0], "a");
        equal(args[Math.max(1, captures)], 1);
        equal(args[Math.max(1, captures) + 1], "xay");
        for (let i = 1; i < captures; i++) equal(args[i], i % 3 ? String(i) : undefined);
        if (groups) assert(args.at(-1) === match.groups);
        return "Z";
      });
      equal(result, "xZy");
      return [result, snapshot];
    });
}
test("collect-before-callback", () => {
  const log = [];
  let i = 0;
  const rx = {
    flags: "g",
    lastIndex: 0,
    exec() {
      log.push("exec" + i);
      if (i === 2) return null;
      const id = i++;
      return {
        length: 2,
        index: id,
        groups: undefined,
        get 0() {
          log.push("match" + id);
          return "a";
        },
        get 1() {
          log.push("capture" + id);
          return {
            toString() {
              log.push("convert" + id);
              return "A";
            },
          };
        },
      };
    },
  };
  const value = replace(rx, "aa", (...args) => {
    log.push("callback" + args[2]);
    return "z";
  });
  equal(value, "zz");
  assert(log.indexOf("exec2") < log.indexOf("callback0"));
  return [value, log];
});
test("getter-and-conversion-order", () => {
  const log = [];
  const match = {
    get length() {
      log.push("length");
      return 3;
    },
    get 0() {
      log.push("0");
      return {
        toString() {
          log.push("match-string");
          return "a";
        },
      };
    },
    get index() {
      log.push("index");
      return {
        valueOf() {
          log.push("index-number");
          return 1;
        },
      };
    },
    get 1() {
      log.push("1");
      return {
        toString() {
          log.push("cap-string");
          return "b";
        },
      };
    },
    get 2() {
      log.push("2");
      return undefined;
    },
    get groups() {
      log.push("groups");
      return { x: "G" };
    },
  };
  const value = replace(custom(match), "xay", (...args) => {
    log.push("callback");
    return {
      toString() {
        log.push("return-string");
        return "Z";
      },
    };
  });
  equal(log, [
    "length",
    "0",
    "match-string",
    "index",
    "index-number",
    "1",
    "cap-string",
    "2",
    "groups",
    "callback",
    "return-string",
  ]);
  return [value, log];
});
for (const location of ["match", "index", "capture", "groups", "callback", "result"])
  test("throw-" + location, () => {
    const marker = new Error(location),
      log = [];
    const match = {
      length: 2,
      get 0() {
        log.push("match");
        if (location === "match") throw marker;
        return "a";
      },
      get index() {
        log.push("index");
        if (location === "index") throw marker;
        return 0;
      },
      get 1() {
        log.push("capture");
        if (location === "capture") throw marker;
        return "b";
      },
      get groups() {
        log.push("groups");
        if (location === "groups") throw marker;
        return {};
      },
    };
    try {
      replace(custom(match), "a", () => {
        log.push("callback");
        if (location === "callback") throw marker;
        return {
          toString() {
            log.push("result");
            if (location === "result") throw marker;
            return "x";
          },
        };
      });
      throw new Error("missing exception");
    } catch (e) {
      assert(e === marker);
    }
    return log;
  });
test("symbol-capture", () => {
  let called = false;
  try {
    replace(custom({ length: 2, 0: "a", 1: Symbol(), index: 0 }), "a", () => {
      called = true;
    });
    assert(false);
  } catch (e) {
    assert(e instanceof TypeError);
  }
  assert(!called);
  return true;
});
test("rope-and-reentry", () => {
  let rope = "";
  for (let i = 0; i < 300; i++) rope += "ab";
  const match = { length: 3, 0: rope, 1: rope, 2: undefined, index: 1, groups: { k: "G" } };
  const value = replace(custom(match), "x" + rope + "y", (...args) => {
    equal(args[0], rope);
    equal(args[1], rope);
    assert(args[5] === match.groups);
    return {
      toString() {
        if (typeof forceGC === "function") forceGC();
        return "q".replace(/q/, () => "R");
      },
    };
  });
  equal(value, "xRy");
  return value;
});
for (const replacement of ["", "$&", "$1", "$`", "$'", "$<word>", "$$"])
  test("string-substitution-" + replacement, () => {
    const native = "xabcy".replace(/(?<word>a)(b)c/g, replacement);
    const fake = replace(
      custom({ length: 3, 0: "abc", 1: "a", 2: "b", index: 1, groups: { word: "a" } }, "g"),
      "xabcy",
      replacement,
    );
    equal(native, fake);
    return native;
  });
test("empty-match-unicode", () => {
  const seen = [];
  const value = "\ud83d\ude00a".replace(/(?:)/gu, (m, pos) => {
    seen.push(pos);
    return "-";
  });
  equal(seen, [0, 2, 3]);
  equal(value, "-\ud83d\ude00-a-");
  return [value, seen];
});
test("backward-results-still-call", () => {
  let i = 0;
  const calls = [];
  const results = [
    { length: 1, 0: "a", index: 1 },
    { length: 1, 0: "a", index: 0 },
  ];
  const value = replace(
    {
      flags: "g",
      lastIndex: 0,
      exec() {
        return results[i++] || null;
      },
    },
    "aa",
    (...args) => {
      calls.push(args[1]);
      return "z";
    },
  );
  equal(value, "az");
  equal(calls, [1, 0]);
  return [value, calls];
});
test("noncallable-class", () => {
  try {
    "a".replace(/a/, class C {});
    assert(false);
  } catch (e) {
    assert(e instanceof TypeError);
  }
  return true;
});
test("revoked-callback", () => {
  const p = Proxy.revocable(() => "z", {});
  p.revoke();
  try {
    "a".replace(/a/, p.proxy);
    assert(false);
  } catch (e) {
    assert(e instanceof TypeError);
  }
  return true;
});
for (const captures of [65531, 65532, 65533, 65535])
  for (const withGroups of [false, true])
    test("limit-" + captures + "-" + withGroups, () => {
      let getters = 0,
        called = false,
        length = 0;
      const match = new Proxy(
        { length: captures, index: 0, groups: withGroups ? {} : undefined },
        {
          get(t, k) {
            if (k === "0") return "a";
            if (typeof k === "string" && /^\d+$/.test(k)) {
              getters++;
              return undefined;
            }
            return t[k];
          },
        },
      );
      let error = "";
      try {
        replace(custom(match), "a", function () {
          called = true;
          length = arguments.length;
          return "z";
        });
      } catch (e) {
        error = e.name;
      }
      assert(getters === captures - 1);
      if (captures + 2 + (withGroups ? 1 : 0) > 65535) {
        assert(!called);
        assert(error === "RangeError");
      } else {
        assert(called);
        assert(length === captures + 2 + (withGroups ? 1 : 0));
      }
      return [getters, called, length, error];
    });
test("serialized-regexp-roundtrip-body", () => {
  const rx = /((a|aa)*)b/g;
  const r = rx.exec("xxaaaab");
  equal([r[0], r[1], r.index], ["aaaab", "aaaa", 2]);
  return [r[0], r[1], r.index, rx.lastIndex];
});
print(JSON.stringify({ bench: "regexp-semantics", checks: rows.length, checksum: rows }));
