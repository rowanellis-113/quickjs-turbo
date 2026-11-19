// Unmodified parent/candidate see the same generated inputs and operations.
// This is a semantic differential fixture, never a performance benchmark.
"use strict";
let hash = 2166136261,
  checks = 0;
function record(value) {
  const s = JSON.stringify(value);
  for (let i = 0; i < s.length; i++) hash = Math.imul(hash ^ s.charCodeAt(i), 16777619) >>> 0;
  checks++;
}
const patterns = [
  "a",
  "[a-z]",
  "[^a-z]",
  "[^a]",
  "[0-9]+",
  "[0-9a-z.]{3,16}\\|(START|TIMING)",
  "TAXI|RUNUP|TAKEOFF|CLIMB|PATTERN|LEFT|RIGHT",
  "(a|ab)c",
  "(?:a|)b",
  "(?:a?)*b",
  "(?:a*)*b",
  "a{0,3}b",
  "(a?)(b+)",
  "(a|b){1,3}c",
  "(?=a)a",
  "(?=[ab])(?:a|b)c",
  "(?=[^a])b",
  "(?!a)b",
  "(?<=x)a",
  "(?<!x)a",
  "(a?)\\1b",
  "(σ)\\1",
  "σ|s|k",
  "[^σsk]",
  "(𐐀|x)+",
  "[𐐀-𐐧]",
  "\\b(?:foo|bar)\\b",
  "\\B(?:a|b)",
  "^a|b",
  "^(?:a|b)$",
  "a$",
  "a.*b",
  " +",
  "(?:[a-f]|[0-9])+(x)?",
  "(?:(a)?b)*c",
  "(?:(a?)|b)+c",
  "^(?:(a)|(?:b))(c)?",
  "(a|(b)|())c",
  "(?:(?:))",
  "",
  "(?=[ab]){2}a",
  "[\u0000-\uffff]",
  "[^\ud800]",
  "[\u007f-\u0100]",
  "\\p{Letter}+",
  "\\P{Lowercase_Letter}",
  "[\\p{ASCII}&&\\p{Letter}]",
  "[[a-z]--[k]]",
  "[\\q{ab|ABC|σ}]",
  "[^\\p{Lowercase_Letter}]",
];
let inputs = [
  "",
  "a",
  "A",
  "b",
  "ab",
  "ABc",
  "abc",
  "xA",
  "a\na",
  "foo bar",
  "RUNUP",
  "not-a-leg",
  "ABC|START",
  "TAXI|1:00",
  "0kts",
  "35@150",
  "\u0000",
  "\uffff",
  "ΣsςKKſ",
  "НАЧАТЬ начать",
  "𐐀𐐨x",
  "\ud800a",
  "\udc00a",
  "x\u2028b",
  "a\r\nb",
];
let seed = 123456789;
const alphabet = "aAbBcC0129 |.σΣςkKKsSſ\u0000\u0100";
for (let n = 0; n < 60; n++) {
  let s = "";
  for (let j = 0; j < n % 9; j++) {
    seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0;
    s += alphabet[seed % alphabet.length];
  }
  inputs.push(s);
}
for (const pattern of patterns)
  for (const flags of [
    "",
    "i",
    "iu",
    "iv",
    "gi",
    "giu",
    "giv",
    "iy",
    "iuy",
    "ivy",
    "id",
    "idu",
    "idv",
  ]) {
    let re;
    try {
      re = new RegExp(pattern, flags);
    } catch (e) {
      record([pattern, flags, e.name]);
      continue;
    }
    for (const input of inputs)
      for (const start of [0, 1, 2, input.length + 1]) {
        re.lastIndex = start;
        let m = re.exec(input);
        record([
          m === null
            ? null
            : { values: [...m], index: m.index, groups: m.groups, indices: m.indices },
          re.lastIndex,
        ]);
      }
    for (const input of inputs.slice(0, 20)) {
      re.lastIndex = 0;
      record(input.replace(re, "<$&:$1>"));
      re.lastIndex = 0;
      record(input.split(re, 8));
      re.lastIndex = 0;
      record([input.search(re), re.lastIndex]);
    }
  }
print("REGEXP_DIFFERENTIAL " + checks + " " + hash.toString(16));
