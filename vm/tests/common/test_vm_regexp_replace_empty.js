/* MIT. Observable semantics and differential corpus for intrinsic empty replacement. */
"use strict";
let checks = 0,
  hash = 2166136261;
function record(value) {
  const text = JSON.stringify(value, (_, x) => (x === undefined ? { undefined: true } : x));
  for (let i = 0; i < text.length; i++) hash = Math.imul(hash ^ text.charCodeAt(i), 16777619);
  checks++;
}
function equal(actual, expected, label) {
  if (JSON.stringify(actual) !== JSON.stringify(expected))
    throw Error(label + ": " + JSON.stringify(actual) + " != " + JSON.stringify(expected));
  record(actual);
}
function throwsTypeError(fn, label) {
  try {
    fn();
  } catch (error) {
    if (!(error instanceof TypeError)) throw error;
    record([label, error.name]);
    return;
  }
  throw Error(label + ": missing TypeError");
}
const replace = RegExp.prototype[Symbol.replace],
  exec = RegExp.prototype.exec;
equal("a,b,c".replace(/,/g, ""), "abc", "global deletion");
equal("a,b,c".replace(/,/, ""), "ab,c", "first deletion");
equal("ab".replace(/(?:)/g, ""), "ab", "global empty matches");
equal("\ud83d\ude00x".replace(/(?:)/gu, ""), "\ud83d\ude00x", "astral empty u");
equal("\ud83d\ude00x".replace(/./gv, ""), "", "astral consuming v");
const patterns = [
  "",
  ",",
  "(,)|(x)",
  "\\s?;\\s?",
  "a*",
  "a*?",
  "a+",
  "a|ab",
  "(a|ab)",
  "^",
  "$",
  "^|$",
  "(?=b)",
  "(?<=a)",
  "(a)?b",
  "(?<x>a)?b",
  "(a)\\1",
  "[a-z]+",
  "[^a]*",
  ".",
  "\\s+",
  "\\b",
  "(?:a?)*",
  "(?:(a)|(b))+",
  "(a?)".repeat(40),
];
const inputs = [
  "",
  "a",
  "b",
  "ab",
  "aaab",
  "a,b,c",
  ",,",
  "a ; b;; c",
  "\nabc\r\n",
  "\u0100a\u0100b",
  "\ud83d\ude00a\ud83d\ude00b",
  "\ud800a\udc00",
  "A,a,aa",
];
for (const pattern of patterns)
  for (const flags of ["", "g", "i", "m", "u", "v", "d", "gu", "gi", "y", "gy", "uy", "dy"])
    for (const input of inputs)
      for (const index of [-1, 0, 1, 7, 2147483647]) {
        const re = new RegExp(pattern, flags),
          reference = new RegExp(pattern, flags);
        re.lastIndex = reference.lastIndex = index;
        // Custom exec forces generic replacement but preserves matching semantics.
        reference.exec = function (text) {
          return exec.call(this, text);
        };
        const expected = replace.call(reference, input, "");
        equal(
          [replace.call(re, input, ""), re.lastIndex],
          [expected, reference.lastIndex],
          "generic exec reference",
        );
      }

// Changing lastIndex conversion, input or replacement conversion can mutate exec.
for (const global of [false, true]) {
  const re = new RegExp("a", global ? "g" : ""),
    log = [];
  re.lastIndex = {
    valueOf() {
      log.push("index");
      return 0;
    },
  };
  equal(replace.call(re, "aba", ""), global ? "b" : "ba", "object index");
  equal(log, global ? [] : ["index"], "index conversion");
}
{
  const re = /a/,
    log = [];
  const input = {
    toString() {
      log.push("input");
      re.exec = function (text) {
        log.push("exec");
        return exec.call(this, text);
      };
      return "aba";
    },
  };
  const replacement = {
    toString() {
      log.push("replacement");
      return "";
    },
  };
  equal(replace.call(re, input, replacement), "ba", "conversion hooks");
  equal(log, ["input", "replacement", "exec"], "conversion order");
}
{
  const re = /a/g,
    log = [];
  Object.defineProperty(re, "constructor", {
    get() {
      log.push("constructor");
      return RegExp;
    },
  });
  equal(replace.call(re, "aba", ""), "b", "constructor hook");
  equal(log, ["constructor"], "inherited constructor observation");
}
for (const name of [
  "flags",
  "hasIndices",
  "global",
  "ignoreCase",
  "multiline",
  "dotAll",
  "unicode",
  "unicodeSets",
  "sticky",
]) {
  const re = /a/g,
    log = [],
    getter = Object.getOwnPropertyDescriptor(RegExp.prototype, name).get;
  Object.defineProperty(re, name, {
    get() {
      log.push(name);
      return getter.call(this);
    },
  });
  equal(replace.call(re, "aba", ""), "b", "flag getter " + name);
  if (!log.length) throw Error("skipped getter " + name);
  record(log);
}
{
  const re = /a/g;
  Object.defineProperty(re, "flags", {
    get() {
      throw 123;
    },
  });
  try {
    replace.call(re, "aba", "");
    throw Error("missing abrupt flag get");
  } catch (error) {
    equal(error, 123, "flag abrupt completion");
  }
}
{
  const re = /a/;
  Object.defineProperty(re, "lastIndex", { value: 7, writable: false });
  equal(replace.call(re, "aba", ""), "ba", "readonly nonglobal index");
  equal(re.lastIndex, 7, "readonly index preserved");
}
{
  const re = /a/g;
  Object.defineProperty(re, "lastIndex", { writable: false });
  throwsTypeError(() => replace.call(re, "aba", ""), "readonly global index");
}
throwsTypeError(() => replace.call(new Proxy(/a/, {}), "aba", ""), "proxy receiver");
throwsTypeError(
  () =>
    replace.call(/a/, "aba", {
      toString() {
        throw new TypeError("replacement");
      },
    }),
  "replacement throws",
);
for (const replacement of ["x", "$&", "$$", "$`", "$'", "$1", "$<x>"])
  for (const flags of ["", "g", "d", "u", "gu"]) {
    const re = new RegExp("(?<x>a)(b)?", flags);
    record([replacement, flags, replace.call(re, "aba", replacement), re.lastIndex]);
  }
{
  const log = [],
    re = /(a)(b)?/g;
  equal(
    replace.call(re, "aba", (...args) => {
      log.push(args);
      return "X";
    }),
    "XX",
    "callback fallback",
  );
  record(log);
}
print("REGEXP_REPLACE_EMPTY", checks, hash >>> 0);
