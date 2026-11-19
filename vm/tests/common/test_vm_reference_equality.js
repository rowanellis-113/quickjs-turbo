import * as std from "qjs:std";
function check(ok, message) {
  if (!ok) throw Error(message);
}
function eq(a, b) {
  return a === b;
}
function ne(a, b) {
  return a !== b;
}
function lastObjects() {
  return {} === {};
}
function lastSymbols() {
  return Symbol("last") === Symbol("last");
}
const one = Symbol("same"),
  other = Symbol("same");
const object = {},
  different = {},
  fn = () => 0;
const proxy = new Proxy(object, {
  get() {
    throw Error("identity must not trap");
  },
});
for (let i = 0; i < 300; i++) {
  for (const value of [one, object, fn, proxy]) {
    check(eq(value, value) && !ne(value, value), "same reference");
    check(!eq(value, undefined) && ne(value, undefined), "mixed reference");
  }
  check(!eq(one, other) && ne(one, other), "distinct symbols");
  check(!eq(object, different) && ne(object, different), "distinct objects");
  check(!eq(proxy, object) && ne(proxy, object), "proxy identity");
  check(eq(12345678901234567890n, 12345678901234567890n), "BigInt equality");
  check(!eq(NaN, NaN) && eq(0, -0), "numeric semantics");
  check(eq("abcdefghijk", "abc" + "defghijk"), "long string semantics");
  check(!eq(Symbol("last"), Symbol("last")), "last symbol releases");
  check(!eq({}, {}), "last object releases");
  check(!lastObjects() && !lastSymbols(), "VM operands with final references");
  if (i % 31 === 0) std.gc();
}
const revoked = Proxy.revocable({}, {});
revoked.revoke();
check(eq(revoked.proxy, revoked.proxy), "revoked proxy identity");
const cycle = {};
cycle.self = cycle;
check(eq(cycle, cycle), "cyclic identity");
std.gc();
print("REFERENCE_EQUALITY_SEMANTICS_OK");
