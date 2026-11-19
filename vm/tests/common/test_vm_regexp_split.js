/* Semantic/differential corpus for the shared intrinsic @@split search. */
"use strict";
let checks = 0,
  hash = 2166136261;
function record(value) {
  const text = JSON.stringify(value, (_, x) => (x === undefined ? { undefined: true } : x));
  for (let i = 0; i < text.length; i++) hash = Math.imul(hash ^ text.charCodeAt(i), 16777619);
  checks++;
}
function equal(actual, expected, name) {
  const a = JSON.stringify(actual),
    b = JSON.stringify(expected);
  if (a !== b) throw Error(name + ": " + a + " != " + b);
  record(actual);
}
equal("a,b,c".split(/,/), ["a", "b", "c"], "simple");
equal(
  "a,,b".split(/(,)|(x)/),
  ["a", ",", undefined, "", ",", undefined, "b"],
  "undefined captures",
);
equal("ab".split(/(?:)/), ["a", "b"], "empty matches");
equal("ab".split(/$/), ["ab"], "end match");
equal("".split(/a/), [""], "empty no match");
equal("".split(/a*/), [], "empty match");
equal("\ud83d\ude00x".split(/(?:)/u), ["\ud83d\ude00", "x"], "astral u");
equal("\ud83d\ude00x".split(/(?:)/v), ["\ud83d\ude00", "x"], "astral v");
const patterns = [
  "",
  ",",
  "(,)",
  "(,)|(x)",
  "\\s?;\\s?",
  "[+, ]",
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
];
const strings = [
  "",
  "a",
  "b",
  "ab",
  "aaab",
  "a,b,c",
  ",,",
  "a ; b;; c",
  " +a,b ",
  "\nabc\r\n",
  "\ud83d\ude00a\ud83d\ude00b",
  "\ud800a\udc00",
  "A,a,aa",
];
const limits = [undefined, 0, 1, 2, 3, 4, 10, -1, NaN, Infinity, 1.9, 4294967296, 4294967297];
for (const source of patterns)
  for (const flags of ["", "g", "i", "m", "u", "v", "d", "gu", "y"]) {
    const re = new RegExp(source, flags);
    for (const input of strings)
      for (const limit of limits) {
        re.lastIndex = 7;
        const output = RegExp.prototype[Symbol.split].call(re, input, limit);
        if (re.lastIndex !== 7) throw Error("receiver lastIndex changed");
        record([source, flags, input, limit, output]);
      }
  }
// A limit conversion must happen after species construction and flags reads.
{
  const log = [],
    re = /,/;
  Object.defineProperty(re, "constructor", {
    get() {
      log.push("constructor");
      return {
        [Symbol.species]: class extends RegExp {
          constructor(...args) {
            log.push("construct");
            super(...args);
          }
        },
      };
    },
  });
  Object.defineProperty(re, "flags", {
    get() {
      log.push("flags");
      return "";
    },
  });
  const limit = {
    valueOf() {
      log.push("limit");
      return 2;
    },
  };
  equal("a,b,c".split(re, limit), ["a", "b"], "hooks output");
  equal(log, ["constructor", "flags", "construct", "limit"], "hooks order");
}
{
  const re = /,/;
  let calls = 0;
  Object.defineProperty(re, "global", {
    get() {
      calls++;
      return true;
    },
  });
  equal("a,b".split(re), ["a", "b"], "flag hook output");
  equal(calls, 1, "flag hook called");
}
{
  const re = /,/;
  let calls = 0;
  re.constructor = {
    [Symbol.species]: class extends RegExp {
      exec(input) {
        calls++;
        return super.exec(input);
      }
    },
  };
  equal("a,b".split(re), ["a", "b"], "custom exec output");
  if (!calls) throw Error("custom exec bypassed");
  record(calls);
}
{
  const saved = RegExp.prototype.exec;
  let calls = 0;
  try {
    RegExp.prototype.exec = function (input) {
      calls++;
      return saved.call(this, input);
    };
    equal("a,b,c".split(/,/), ["a", "b", "c"], "changed prototype exec");
    if (!calls) throw Error("prototype exec bypassed");
    record(calls);
  } finally {
    RegExp.prototype.exec = saved;
  }
}
{
  const re = /,/;
  let calls = 0;
  Object.defineProperty(re, "flags", {
    get() {
      calls++;
      return "y";
    },
  });
  equal("a,b,c".split(re), ["a", "b", "c"], "custom sticky flags");
  equal(calls, 1, "flags getter");
}
{
  const re = /,/;
  re.constructor = undefined;
  equal("a,b".split(re), ["a", "b"], "undefined constructor fallback");
  re.constructor = 1;
  let threw = false;
  try {
    "a,b".split(re);
  } catch (e) {
    threw = e instanceof TypeError;
  }
  equal(threw, true, "invalid constructor");
}
{
  const re = /,/;
  let calls = 0;
  Object.defineProperty(re, Symbol.match, {
    get() {
      calls++;
      return true;
    },
  });
  equal("a,b".split(re), ["a", "b"], "IsRegExp accessor output");
  equal(calls, 1, "IsRegExp accessor called");
}
{
  const re = /,/;
  Object.defineProperty(re, Symbol.match, {
    get() {
      throw new Error("match hook");
    },
  });
  let message = "";
  try {
    "a,b".split(re);
  } catch (e) {
    message = e.message;
  }
  equal(message, "match hook", "IsRegExp abrupt completion");
}
{
  const re = /,/;
  re[Symbol.match] = false;
  equal("a,b".split(re), ["a", "b"], "IsRegExp false data on real regexp");
  Object.defineProperty(re, "source", {
    get() {
      throw Error("source must not be read");
    },
  });
  equal("a,b".split(re), ["a", "b"], "real regexp internal pattern");
}
{
  const re = /,/;
  let calls = 0;
  const saved = Object.getOwnPropertyDescriptor(RegExp, Symbol.species);
  try {
    Object.defineProperty(RegExp, Symbol.species, {
      configurable: true,
      get() {
        calls++;
        return this;
      },
    });
    equal("a,b".split(re), ["a", "b"], "species accessor output");
    equal(calls, 1, "species accessor called");
  } finally {
    Object.defineProperty(RegExp, Symbol.species, saved);
  }
}
{
  let s = "";
  for (let i = 0; i < 200; i++) s += "abc,";
  record(s.split(/,/));
  const re = new RegExp("(" + "a".repeat(1) + ")".repeat(1));
  record("aaa".split(re));
  const many = new RegExp(Array(80).fill("(a?)").join(""));
  record("aaa".split(many));
}
print("REGEXP_SPLIT_OK " + checks + " " + (hash >>> 0));
