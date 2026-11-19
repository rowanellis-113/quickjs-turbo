/* Complete equality semantics across cold/Dirty paths,owners and coercions. */
import * as std from "qjs:std";
let checks = 0;
function check(value, message) {
  if (!value) throw Error(message);
  ++checks;
}
function operators(a, b) {
  let strict = a === b,
    strictNot = a !== b,
    loose = a == b,
    looseNot = a != b;
  check(strict === !strictNot, "strict complement");
  check(loose === !looseNot, "loose complement");
  return [strict, loose];
}
function expected(a, b, strict, loose) {
  const out = operators(a, b),
    reverse = operators(b, a);
  check(out[0] === strict && reverse[0] === strict, "strict result");
  check(out[1] === loose && reverse[1] === loose, "loose result");
}
const object = {},
  other = {},
  fn = () => 0,
  symbol = Symbol("same"),
  otherSymbol = Symbol("same");
const proxy = new Proxy(object, {
  get() {
    throw Error("identity must not trap");
  },
});
const revoked = Proxy.revocable({}, {});
revoked.revoke();
const kept = [object, other, fn, symbol, otherSymbol, proxy, revoked.proxy];
for (let repeat = 0; repeat < 24; ++repeat) {
  for (const value of kept) {
    expected(value, value, true, true);
    expected(value, null, false, false);
    expected(value, undefined, false, false);
  }
  expected(object, other, false, false);
  expected(symbol, otherSymbol, false, false);
  expected(proxy, object, false, false);
  expected(null, undefined, false, true);
  expected(null, null, true, true);
  expected(undefined, undefined, true, true);
  for (const value of [false, true, 0, -0, 1, 1.5, NaN, Infinity, 7n, 2n ** 100n, "", "abc"]) {
    expected(value, null, false, false);
    expected(value, undefined, false, false);
  }
  expected(1, 1.0, true, true);
  expected(-0, 0, true, true);
  expected(NaN, NaN, false, false);
  expected(Infinity, Infinity, true, true);
  expected(1, 1.5, false, false);
  expected(false, 0, false, true);
  expected(true, 1, false, true);
  expected(1n, 1, false, true);
  expected(2n ** 100n, 2n ** 100n, true, true);
  expected("01", 1, false, true);
  expected("12x", 12n, false, false);
  expected({}, {}, false, false);
  expected(Symbol("last"), Symbol("last"), false, false);
  if (repeat % 7 === 0) std.gc();
}
for (const length of [0, 1, 2, 3, 4, 7, 8, 9, 64, 8193]) {
  const narrow = "a".repeat(length),
    different = "b".repeat(length);
  const wide = "\u03a9".repeat(length),
    wideDifferent = "\u03c0".repeat(length);
  const narrowCopy = ["", narrow, ""].join(""),
    wideCopy = ["", wide, ""].join("");
  kept.push(narrow, narrowCopy, wide, wideCopy);
  expected(narrow, narrowCopy, true, true);
  expected(wide, wideCopy, true, true);
  expected(narrow, different, length === 0, length === 0);
  expected(wide, wideDifferent, length === 0, length === 0);
  expected(narrow, wide, length === 0, length === 0);
  const fromWide = ("\u03a9" + narrow + "\u03a9").slice(1, length + 1);
  kept.push(fromWide);
  expected(narrow, fromWide, true, true);
  expected(narrow, narrow + "x", false, false);
}
const base = "a".repeat(10000) + "\u03a9" + "b".repeat(10000);
const slices = [base.slice(100, 9000), base.slice(101, 9001), base.slice(9997, 10004)];
kept.push(...slices);
expected(slices[0], slices[1], true, true);
expected(slices[2], "aaa\u03a9bbb", true, true);
let conversions = 0;
const coercible = {
  [Symbol.toPrimitive](hint) {
    check(hint === "default", "coercion hint");
    ++conversions;
    std.gc();
    return "12";
  },
};
check(coercible == 12 && 12 == coercible, "both coercion orders");
check(conversions === 2, "exact coercions");
check(!(coercible === 12) && coercible !== 12, "strict has no coercion");
check(coercible != null && null != coercible, "object null has no coercion");
check(conversions === 2, "null has no coercion");
let calls = 0,
  marker = {};
const broken = {
  [Symbol.toPrimitive]() {
    ++calls;
    std.gc();
    throw marker;
  },
};
try {
  void (broken == "x");
  throw Error("missing exception");
} catch (e) {
  check(e === marker, "coercion exception");
}
check(calls === 1, "single throwing conversion");
check(broken != null && null != broken, "throwing object null");
check(calls === 1, "no extra conversions");
std.gc();
print("LINUX_COMPARISON_FAMILY_OK checks=" + checks);
