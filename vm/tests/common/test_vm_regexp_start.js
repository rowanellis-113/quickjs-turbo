"use strict";
let checks = 0;
function equal(a, b, why) {
  checks++;
  if (JSON.stringify(a) !== JSON.stringify(b))
    throw Error(why + ": " + JSON.stringify(a) + " != " + JSON.stringify(b));
}
for (const flags of ["i", "iu", "iv"]) {
  equal(new RegExp("a", flags).test("A"), true, "ASCII fold " + flags);
  equal(new RegExp("[^a]", flags).test("A"), false, "complement fold " + flags);
  equal(new RegExp("[^a]", flags).test("b"), true, "complement accept " + flags);
  equal(new RegExp("[0-9]", flags).test("5"), true, "digit " + flags);
  equal(new RegExp("[^0-9]", flags).test("5"), false, "digit complement " + flags);
  equal(new RegExp("σ", flags).test("ς"), true, "Greek sigma " + flags);
  equal(new RegExp("НАЧАТЬ", flags).test("начать"), true, "Cyrillic " + flags);
  equal(new RegExp("k", flags).test("\u212a"), flags !== "i", "Kelvin semantics " + flags);
  equal(new RegExp("s", flags).test("\u017f"), flags !== "i", "long s semantics " + flags);
  equal(new RegExp("[^k]", flags).test("\u212a"), flags === "i", "Kelvin complement " + flags);
  equal(
    new RegExp("(σ|s)+", flags).exec("Σsς").slice(0, 2),
    ["Σsς", "ς"],
    "ordered captures " + flags,
  );
  equal(new RegExp("(a|ab)c", flags).exec("ABc").slice(0, 2), ["ABc", "AB"], "backtrack " + flags);
  equal(new RegExp("(?<=a)b", flags).exec("AB")[0], "B", "lookbehind " + flags);
  equal(new RegExp("(?<x>a)\\k<x>", flags).test("aA"), true, "backreference " + flags);
  equal(new RegExp("a|z", flags + "y").exec("Z")[0], "Z", "sticky alternation " + flags);
}
equal(/\P{Lowercase_Letter}/iu.test("a"), true, "u complement order");
equal(/\P{Lowercase_Letter}/iv.test("a"), false, "v complement order");
equal(/[\p{ASCII}&&\p{Letter}]/iv.test("A"), true, "v intersection");
equal(/[\p{ASCII}--[K]]/iv.test("k"), false, "v subtraction");
equal(/\u{10400}/iu.test("\u{10428}"), true, "astral cased literal");
equal(/[^\u{10400}]/iu.test("\u{10428}"), false, "astral complement");
equal("\u212aſΣ".replace(/k|s|σ/giu, "x"), "xxx", "global replace");
equal("A.a".split(/a/i), ["", ".", ""], "split");
print("REGEXP_CASE_CLOSURE_OK " + checks);
