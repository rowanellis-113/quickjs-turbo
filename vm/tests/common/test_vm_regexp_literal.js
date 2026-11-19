/* Independent literal oracle: code-unit equality and Unicode boundaries. */
let cases = 0;
let checksum = 2166136261;
function check(ok, message) {
  if (!ok) throw Error(message);
}
function boundary(text, at) {
  if (at <= 0 || at >= text.length) return true;
  const before = text.charCodeAt(at - 1),
    current = text.charCodeAt(at);
  return !(before >= 0xd800 && before <= 0xdbff && current >= 0xdc00 && current <= 0xdfff);
}
function expected(text, needle, flags, initial) {
  const unicode = flags.includes("u") || flags.includes("v");
  const sticky = flags.includes("y"),
    indexed = sticky || flags.includes("g");
  let start = indexed ? Math.max(0, initial) : 0;
  if (start > text.length) return -1;
  if (unicode && !boundary(text, start)) start--;
  for (let at = start; at + needle.length <= text.length; at++) {
    if (
      (!unicode || (boundary(text, at) && boundary(text, at + needle.length))) &&
      text.slice(at, at + needle.length) === needle
    )
      return at;
    if (sticky) break;
  }
  return -1;
}
function pattern(needle) {
  let result = "";
  for (let i = 0; i < needle.length; i++)
    result += "\\u" + needle.charCodeAt(i).toString(16).padStart(4, "0");
  return result;
}
const needles = [
  "a",
  "ab",
  "0123456789abcdef012",
  "a.b",
  "[q]",
  "\\",
  "\0x",
  "\u0100b",
  "a\u00ff",
  "\u20ac",
  "\ud800",
  "\udc00",
  "\ud83d\ude00",
  "a\ud83d\ude00b",
  "a".repeat(64),
  "a".repeat(65),
  "a".repeat(127),
];
const flagsList = ["", "g", "d", "dg", "u", "du", "gu", "v", "dv", "gv", "m", "s", "y", "uy", "vy"];
const base = [
  "",
  "a",
  "b",
  "ab",
  "zzabzz",
  "a.a",
  "[q]x",
  "\\x",
  "\0x",
  "\u0100b0",
  "b\u0100b",
  "a\u00ff",
  "\u20acx",
  "\ud800",
  "\udc00",
  "\ud83d\ude00",
  "\ud83d\ude00a",
  "a\ud83d\ude00",
  "a\ud83d\ude00b",
  "a".repeat(128) + "x",
];
for (const needle of needles) {
  const subjects = base.concat([needle, "x" + needle + "y", needle + needle]);
  for (const flags of flagsList) {
    const rx = new RegExp(pattern(needle), flags);
    for (const text of subjects) {
      for (const initial of [-1, 0, 1, 2, text.length - 1, text.length, text.length + 1]) {
        const at = expected(text, needle, flags, initial);
        rx.lastIndex = initial;
        const value = rx.exec(text);
        const label = JSON.stringify([needle, flags, text, initial, at]);
        check((value === null) === at < 0, "presence " + label);
        if (value) {
          check(
            value.length === 1 && value[0] === needle && value.index === at && value.input === text,
            "match " + label,
          );
          check(value.groups === undefined, "groups " + label);
          if (flags.includes("d"))
            check(
              value.indices.length === 1 &&
                value.indices[0][0] === at &&
                value.indices[0][1] === at + needle.length,
              "indices " + label,
            );
        }
        const indexed = flags.includes("g") || flags.includes("y");
        check(
          rx.lastIndex === (indexed ? (at < 0 ? 0 : at + needle.length) : initial),
          "lastIndex " + label,
        );
        checksum = Math.imul(checksum ^ (at + 1), 16777619) >>> 0;
        cases++;
      }
    }
  }
}
/* Assertions, captures, flags and longer patterns must retain generic behavior. */
for (const [source, flags, text, answer] of [
  ["(ab)", "", "zab", "ab"],
  ["a+", "", "zaaa", "aaa"],
  ["^ab", "m", "x\nab", "ab"],
  ["ab$", "", "zab", "ab"],
  ["ab", "i", "zAB", "AB"],
  ["(?=ab)ab", "", "zab", "ab"],
]) {
  const value = new RegExp(source, flags).exec(text);
  check(value && value[0] === answer, "fallback " + source);
  cases++;
}
(globalThis.print || console.log)("REGEXP_LITERAL_OK", cases, checksum);
