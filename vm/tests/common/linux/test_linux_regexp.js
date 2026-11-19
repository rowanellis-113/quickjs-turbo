/* Complete callback argv,observable getter/coercion order and search fallbacks. */
"use strict";
let checks = 0;
function equal(a, b) {
  if (!Object.is(a, b)) throw Error(String(a) + " != " + String(b));
  ++checks;
}
function same(a, b) {
  equal(JSON.stringify(a), JSON.stringify(b));
}
let kept = [];
const small = "a ab".replace(/(?<first>a)(b)?/g, function (m, a, b, offset, input, groups) {
  equal(this, undefined);
  equal(arguments.length, 6);
  equal(a, "a");
  equal(groups.first, "a");
  equal(Object.getPrototypeOf(groups), null);
  equal(input, "a ab");
  gc();
  kept.push(arguments);
  equal("zb".replace(/b/, "B"), "zB");
  return {
    toString() {
      gc();
      return "[" + offset + "]";
    },
  };
});
equal(small, "[0] [2]");
equal(kept[0][0], "a");
equal(kept[0][2], undefined);
equal(kept[1][0], "ab");
equal(kept[1][2], "b");
let wideKept = [];
const wide = "abcdefghij;abcdefghij".replace(
  /(?<first>a)(b)(c)(d)(e)(f)(g)(h)(i)(j)/g,
  function (m, a, b, c, d, e, f, g, h, i, j, offset, input, groups) {
    equal(arguments.length, 14);
    equal(groups.first, "a");
    equal(input, "abcdefghij;abcdefghij");
    equal(a, "a");
    equal(j, "j");
    gc();
    wideKept.push(arguments);
    return m.toUpperCase();
  },
);
equal(wide, "ABCDEFGHIJ;ABCDEFGHIJ");
equal(wideKept[0][11], 0);
equal(wideKept[1][11], 11);
gc();
equal(wideKept[0][9], "i");
equal(wideKept[1][13].first, "a");
let events = [];
const result = {
  get length() {
    events.push("length");
    return 3;
  },
  get 0() {
    events.push("match");
    return "a";
  },
  get index() {
    events.push("index");
    return 0;
  },
  get 1() {
    events.push("cap1");
    gc();
    return {
      toString() {
        events.push("string1");
        return "A";
      },
    };
  },
  get 2() {
    events.push("cap2");
    return undefined;
  },
  get groups() {
    events.push("groups");
    return { named: "yes" };
  },
};
const custom = {
  get flags() {
    events.push("flags");
    return "";
  },
  exec(s) {
    events.push("exec:" + s);
    return result;
  },
  get unicode() {
    throw Error("nonglobal unicode");
  },
};
const value = RegExp.prototype[Symbol.replace].call(
  custom,
  {
    toString() {
      events.push("input");
      gc();
      return "abc";
    },
  },
  function (m, a, b, offset, input, groups) {
    events.push("callback");
    gc();
    equal(m, "a");
    equal(a, "A");
    equal(b, undefined);
    equal(offset, 0);
    equal(input, "abc");
    equal(groups.named, "yes");
    return {
      toString() {
        events.push("return");
        gc();
        return "Z";
      },
    };
  },
);
equal(value, "Zbc");
same(events, [
  "input",
  "flags",
  "exec:abc",
  "length",
  "match",
  "index",
  "cap1",
  "string1",
  "cap2",
  "groups",
  "callback",
  "return",
]);
const zero = {
  flags: "",
  exec() {
    return { length: 0, 0: "a", index: 0, groups: undefined };
  },
};
equal(
  RegExp.prototype[Symbol.replace].call(zero, "a", function () {
    equal(arguments.length, 3);
    equal(arguments[0], "a");
    return "R";
  }),
  "R",
);
let applied = 0;
const proxy = new Proxy(function () {}, {
  apply(target, self, args) {
    equal(self, undefined);
    equal(args[0], "a");
    ++applied;
    gc();
    return "P";
  },
});
equal("aa".replace(/a/g, proxy), "PP");
equal(applied, 2);
const marker = {};
let caught = false;
try {
  "a".replace(/(a)/g, () => {
    gc();
    throw marker;
  });
} catch (e) {
  caught = e === marker;
}
equal(caught, true);
equal(
  "a".replace(/(a)/g, (m, a) => a.toUpperCase()),
  "A",
);
let callbackRan = false;
const broken = {
  flags: "",
  exec() {
    return {
      length: 2,
      0: "a",
      index: 0,
      get 1() {
        gc();
        throw marker;
      },
    };
  },
};
caught = false;
try {
  RegExp.prototype[Symbol.replace].call(broken, "a", () => {
    callbackRan = true;
  });
} catch (e) {
  caught = e === marker;
}
equal(caught, true);
equal(callbackRan, false);
const r = /(?<part>a)(b)?/dg;
const captures = r.exec("ab");
same(captures.slice(), ["ab", "a", "b"]);
same(captures.indices, [
  [0, 2],
  [0, 1],
  [1, 2],
]);
equal(captures.groups.part, "a");
const split = /(,)/g;
split.lastIndex = 7;
/* The cold call materializes lazy builtin descriptors. Repeat normally to
   exercise the unchanged-intrinsic guard after initialization as well. */
for (let warm = 0; warm < 2; ++warm) {
  same("a,b,c".split(split), ["a", ",", "b", ",", "c"]);
  equal(split.lastIndex, 7);
}
let constructors = 0;
const hooked = /,/;
Object.defineProperty(hooked, "constructor", {
  get() {
    ++constructors;
    gc();
    return RegExp;
  },
});
same("a,b".split(hooked), ["a", "b"]);
equal(constructors > 0, true);
equal("baab".replace(/a/g, ""), "bb");
equal("\u0100aba".replace(/a/g, ""), "\u0100b");
same("\ud83d\ude00a".match(/(?:)/gv), ["", "", ""]);
equal(
  "\ud83d\ude00a".replace(/(?:)/gv, (m, p) => "[" + p + "]"),
  "[0]\ud83d\ude00[2]a[3]",
);
same(
  [..."ab".matchAll(/(?<x>.)/dg)].map((v) => [v[0], v.index, v.groups.x]),
  [
    ["a", 0, "a"],
    ["b", 1, "b"],
  ],
);
equal(/a/dgimsuy.flags, "dgimsuy");
let reads = [];
const flagsGetter = Object.getOwnPropertyDescriptor(RegExp.prototype, "flags").get;
const flagsProxy = new Proxy(
  {},
  {
    get(o, k) {
      reads.push(k);
      gc();
      return k === "global" || k === "unicodeSets";
    },
  },
);
equal(flagsGetter.call(flagsProxy), "gv");
same(reads, [
  "hasIndices",
  "global",
  "ignoreCase",
  "multiline",
  "dotAll",
  "unicode",
  "unicodeSets",
  "sticky",
]);
kept = [];
wideKept = [];
gc();
print("LINUX_REGEXP_FAMILY_OK checks=" + checks);
