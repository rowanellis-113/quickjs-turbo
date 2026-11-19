"use strict";
let checks = 0;
function equal(actual, expected) {
  ++checks;
  if (!Object.is(actual, expected)) throw Error(`${actual} != ${expected}`);
}
function order(a, b) {
  a = Array.from(a.normalize("NFC"), (c) => c.codePointAt(0));
  b = Array.from(b.normalize("NFC"), (c) => c.codePointAt(0));
  for (let i = 0; i < Math.min(a.length, b.length); ++i)
    if (a[i] !== b[i]) return a[i] > b[i] ? 1 : -1;
  return (a.length > b.length) - (a.length < b.length);
}
function compare(a, b) {
  return a.localeCompare(b);
}
for (let i = 0; i < 256; ++i) {
  const a = String.fromCharCode(i);
  for (let j = 0; j < 256; ++j) equal(compare(a, String.fromCharCode(j)), (i > j) - (i < j));
}
const samples = [
  "",
  "\0",
  "\xff",
  "\xc5",
  "A\u030a",
  "\u212b",
  "\u0340",
  "\u00e9",
  "e\u0301",
  "\u1e9b\u0323",
  "\uac00",
  "\u1100\u1161",
  "\ud800",
  "\udc00",
  "\ud800\udc00",
  "\ue000",
  "\udbff\udfff",
  "ab\0x",
  "ab\0y",
  "z",
  "\xe9".repeat(70),
];
for (const a of samples) for (const b of samples) equal(compare(a, b), order(a, b));
for (let i = 0; i < 600; ++i) {
  const a = String.fromCharCode(i & 255, (i * 79) & 255, 0, (i * 113) & 255);
  const b = String.fromCharCode((i * 61) & 255, (i + 17) & 255, 0);
  equal(compare(a, b), order(a, b));
  const padded = "#".repeat(300) + a + "!".repeat(300);
  equal(compare(padded.slice(300, 304), b), order(a, b));
  equal(compare((a + b).repeat(40), a.repeat(80)), order((a + b).repeat(40), a.repeat(80)));
}
const log = [];
const receiver = {
  [Symbol.toPrimitive](hint) {
    log.push("this:" + hint);
    return "\xe9";
  },
};
const argument = {
  [Symbol.toPrimitive](hint) {
    log.push("arg:" + hint);
    return "e\u0301";
  },
};
equal(String.prototype.localeCompare.call(receiver, argument), 0);
equal(log.join(","), "this:string,arg:string");
for (const value of [null, undefined, Symbol("receiver")]) {
  let reached = false,
    threw = false;
  try {
    String.prototype.localeCompare.call(value, {
      toString() {
        reached = true;
        return "";
      },
    });
  } catch (e) {
    threw = e instanceof TypeError;
  }
  equal(threw, true);
  equal(reached, false);
}
let threw = false;
const marker = {};
try {
  compare("a", {
    toString() {
      throw marker;
    },
  });
} catch (e) {
  threw = e === marker;
}
equal(threw, true);
equal(String.prototype.localeCompare.call(new String("\xe9"), new String("e\u0301")), 0);
equal(compare("undefined", undefined), 0);
equal(String.prototype.localeCompare.length, 1);
print("LOCALE_COMPARE", checks, "PASS");
