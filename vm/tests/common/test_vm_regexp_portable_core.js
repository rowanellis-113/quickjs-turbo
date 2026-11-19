// The retained RegExp header must preserve the core language classifier ABI.
let checks = 0;
function check(value) {
  ++checks;
  if (!value) throw new Error("core Unicode classifier check " + checks);
}
const spaces = [
  9, 10, 11, 12, 13, 32, 0xa0, 0x1680, 0x2000, 0x2001, 0x2002, 0x2003, 0x2004, 0x2005, 0x2006,
  0x2007, 0x2008, 0x2009, 0x200a, 0x2028, 0x2029, 0x202f, 0x205f, 0x3000, 0xfeff,
];
for (const cp of spaces) {
  const c = String.fromCodePoint(cp);
  check(Number(c) === 0);
  check(parseInt(c + "17", 10) === 17);
  check(parseFloat(c + "1.25") === 1.25);
  check((c + "abc" + c).trim() === "abc");
  check((c + "abc").trimStart() === "abc");
  check(("abc" + c).trimEnd() === "abc");
}
for (const cp of [
  0x85, 0x180e, 0x200b, 0x200c, 0x200d, 0x2060, 0x2118, 0x309b, 0x309c, 0x5495, 0x565c, 0x1d49c,
]) {
  const c = String.fromCodePoint(cp);
  check(Number.isNaN(Number(c)));
  check(Number.isNaN(parseInt(c + "17", 10)));
  check(Number.isNaN(parseFloat(c + "1.25")));
  check(c.trim() === c);
  check((" " + c + " ").trim() === c);
  check((" " + c).trimStart() === c);
  check((c + " ").trimEnd() === c);
}
for (const cp of [0x2118, 0x309b, 0x309c, 0x5495, 0x565c, 0x1d49c]) {
  const c = String.fromCodePoint(cp);
  check(eval("var " + c + " = 9; " + c) === 9);
  const C = eval("(class { #" + c + "=7; value(){return this.#" + c + ";} })");
  check(new C().value() === 7);
}
print("PORTABLE_REGEXP_CORE_CLASSIFIERS_OK checks=" + checks);
