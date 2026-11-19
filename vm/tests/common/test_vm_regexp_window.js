/* Differential semantic corpus for bounded necessary-character windows. */
"use strict";
let checks = 0,
  hash = 2166136261;
function record(value) {
  const text = JSON.stringify(value, (_, value) =>
    value === undefined ? { undefined: true } : value,
  );
  for (let i = 0; i < text.length; i++) hash = Math.imul(hash ^ text.charCodeAt(i), 16777619);
  checks++;
}
function assert(value, name) {
  if (!value) throw Error(name);
}
const patterns = [
  '(^|[^\\\\])\\"\\\\\\/Qngr\\((-?[0-9]+)\\)\\\\\\/\\"',
  "\\s?;\\s?",
  "(((\\w+):\\/\\/)([^\\/:]*)(:(\\d+))?)?([^#?]*)(\\?([^#]*))?(#(.*))?",
  "^\\s*|\\s*$",
  "(?:^|;)\\s*sevraqfgre_ynat=([^;]*)",
  "\\s+",
  "^\\s*(\\S*(\\s+\\S+)*)\\s*$",
  "^\\s+|\\s+$",
  "NQ_VQ",
  "\\b\\w+\\b",
  "qqqq|qqq|qq|q|ZZZZ|ZZZ|ZZ|Z|llll|ll|l|uu|u|UU|U|zz|z|ff|f|gg|g|sss|ss|s|mmm|mm|m",
  "\\s?;\\s?",
  "abcdefgh",
  "(?:abcdefgh|ijklmnop)",
  "(?:^|[^x])abcdefgh",
  "(?:^|[^x])abcdefgh(ij)?",
  "(?:a|bc)defghijk",
  "a(?:bc|de)fghijkl",
  "a?bcdefghi",
  "a{2,4}bcdefgh",
  "a*bcdefghij",
  "(?:^|;)\\s*abcdefgh=([^;]*)",
  "\\babcdefgh\\b",
  "\\Babcdefgh\\B",
  "[a-z]abcdefgh",
  "[^a]abcdefgh",
  "[\\x00-\\xff]abcdefgh",
  "[\\u0100-\\uffff]abcdefgh",
  "(?:\u4e2d|abcdefgh)",
  "(?:\u4e2d|abcdefgh)?",
  "(?:\u4e2d|abcdefgh)*",
  "(?:\u4e2d|abcdefgh)+",
  "a\u4e2dbcdefgh",
  "(?:a\u4e2d|abcdefgh)",
  "(?=abcdefgh)abcdefgh",
  "(?!x)abcdefgh",
  "(?<=x)abcdefgh",
  "(?<!x)abcdefgh",
  "(a)\\1bcdefghij",
  "(?<x>a)\\k<x>bcdefghij",
  "^abcdefgh",
  "abcdefgh$",
  "^|abcdefgh",
  "abcdefgh|$",
  "abcdefgh|",
  "(?:a?)*bcdefghij",
  "(?:)*",
  "(?:a|)*",
  "a{0,20}bcdefghij",
  "[A-Z]bcdefghi",
  "[a-zA-Z]bcdefghi",
  "[\\s\\S]abcdefgh",
  ".abcdefgh",
  "\\sabcdefgh",
  "\\Sabcdefgh",
  "\\u017fbcdefghi",
  "\\u212abcdefghij",
  "\\ud800abcdefgh",
  "\\udc00abcdefgh",
  "\ud83d\ude00abcdefgh",
  "(ab|abcd)efghijkl",
  "(abcdefgh)|(abcdefghi)",
  "a(b(c(d(e(f(g(h)))))))",
  "(?:ab){4}cdefgh",
];
patterns.push(
  ...[
    "\\s?;\\s?",
    "\\s{0,2};",
    "\\s{0,7};",
    "\\s{0,8};",
    "\\s*;",
    "\\s+;",
    ".?;",
    ".{0,2};",
    ".{0,7};",
    ".{0,8};",
    ".*;",
    "[^x]?;",
    "[^x]{0,2};",
    "(?:\\s?|[^x]{0,2});",
    "(?:\\s?;|\\s?:)",
    "(?:\\s?;|$)",
    "(?:\\s?;|)",
    "(?:\\s?;|\\s?;a)",
    "(?:\\s?;a|\\s?;)",
    "(\\s?)(;)(\\s?)",
    "(?<p>\\s?)(?<a>;)",
    "(?=\\s?;)\\s?;",
    "(?!\\s?:)\\s?;",
    "(?<=x)\\s?;",
    "(a)\\s?;\\1",
    "\\s?\\b;",
    "\\s?;\\B",
    "\\s?\u4e2d",
    "\\s?\ud83d\ude00",
    "\\s?\\ud800",
    "\\s?\\udc00",
    "\\s?[;:]",
    "[a-z]?;",
    "\\s?\\u00bb",
    "(?:\\s?;){1,2}",
    "(?:\\s?;)?",
  ],
);
let random = 0x78193;
function next(n) {
  random ^= random << 13;
  random ^= random >>> 17;
  random ^= random << 5;
  return (random >>> 0) % n;
}
const pieces = [
  "a",
  "b",
  "[a-c]",
  "[^x]",
  ".",
  "\\s",
  "\\S",
  "(?:ab|cd)",
  "(?:^|x)",
  "(?:a|中)",
  "a?",
  "a*",
  "(a)",
  "(?=a)",
];
for (let i = 0; i < 48; i++) {
  let p = "";
  for (let j = 0, n = 2 + next(5); j < n; j++) p += pieces[next(pieces.length)];
  patterns.push(p + "abcdefgh");
}
const flags = [
  "",
  "g",
  "y",
  "i",
  "gi",
  "m",
  "s",
  "u",
  "gu",
  "uy",
  "v",
  "gv",
  "d",
  "gd",
  "du",
  "dv",
];
const inputs = [
  "",
  "a",
  "ab",
  "abcdefgh",
  "xabcdefgh",
  "zabcdefghijk",
  "abcdefghabcdefgh",
  "xabcdefghxabcdefgh",
  "bcdefghi",
  "abcabcdefgh",
  "aabcdefghij",
  "abcdefghijklmnop",
  "ijklmnop",
  "aaabcdefgh",
  " abcdefgh ",
  "\nabcdefgh\r\n",
  ";  abcdefgh=xyz;",
  "\u0000abcdefgh\u00ff",
  "\u0081\u00c1abcdefgh",
  "中abcdefgh",
  "abcdefgh中",
  "😀abcdefgh",
  "x😀abcdefgh",
  "\ud800abcdefgh",
  "\udc00abcdefgh",
  "abababababcdefgh",
  "z".repeat(137) + "abcdefgh",
  "a".repeat(17) + "bcdefghij",
  'x"\\\\/Qngr(123)\\\\/"x',
  'x"\\\\/Qngr(-123)\\\\/"x',
];
inputs.push(
  ...[
    ";",
    " ;",
    "  ;",
    "       ;",
    "        ;",
    ":",
    " :",
    "a;b;",
    ";a;",
    "a ; a",
    "x ;",
    "x: ;",
    "\u00bb",
    " \u00bb",
    "\u4e2d;",
    ";\u4e2d",
    " \u4e2d",
    "\ud83d\ude00;",
    " \ud83d\ude00",
    "\ud800;",
    " \ud800",
    "\udc00;",
    " \udc00",
    "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa;",
    "\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d\u4e2d ;",
    "\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb\u00bb;",
    "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  ],
);
for (const pattern of patterns)
  for (const flag of flags) {
    let re;
    try {
      re = new RegExp(pattern, flag);
    } catch (error) {
      record([pattern, flag, error.name]);
      continue;
    }
    for (const input of inputs)
      for (const index of [-1, 0, 1, 2, input.length, input.length + 1]) {
        re.lastIndex = index;
        const result = re.exec(input);
        record(
          result === null
            ? [null, re.lastIndex]
            : [
                Array.from(result),
                result.index,
                result.input,
                result.groups,
                result.indices,
                re.lastIndex,
              ],
        );
      }
  }
for (const [pattern, input, expected] of [
  ["(?:^|[^x])abcdefgh", "xabcdefgh zabcdefgh", 10],
  ["abcdefgh", "zabcdefgh", 1],
  ["abcdefgh", "中abcdefgh", 1],
  ["abcdefgh", "😀abcdefgh", 2],
  ["(?:中|abcdefgh)?", "", 0],
]) {
  const result = new RegExp(pattern).exec(input);
  assert(result && result.index === expected, "leftmost " + pattern);
  record(result.index);
}
print("REGEXP_WINDOW_OK", checks, hash >>> 0);
