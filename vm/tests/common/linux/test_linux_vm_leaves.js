import * as std from "qjs:std";
let checks = 0;
function check(v, m) {
  if (!v) throw Error(m);
  checks++;
}
function vmLeafCall(fn, a, b, c, d) {
  let value = fn(a, b, c, d);
  return value;
}
function vmLeafTail(fn, a) {
  return fn(a);
}
function vmLeafMethod(o, arg) {
  let value = o.compare(arg);
  return value;
}
function vmLeafInt() {
  return 3;
}
function vmLeafUndefined() {
  return;
}
function vmLeafIdentity(a, b, c, d) {
  return d;
}
function vmLeafAddConst(a) {
  return a + 3;
}
function vmLeafAddArgs(a, b) {
  return a + b;
}
function vmLeafNull() {
  return null;
}
function vmLeafBool() {
  return true;
}
function vmLeafChars(s) {
  return s == "a" || s == "b" || s == "c";
}
const vmLeafCompare = function (other) {
  return this.left.localeCompare(other.right);
};
const intrinsic = String.prototype.localeCompare;
const descriptor = Object.getOwnPropertyDescriptor(String.prototype, "localeCompare");
const token = { tag: 7 },
  cycle = {};
cycle.self = cycle;
const x = { left: "a", compare: vmLeafCompare },
  y = { right: "b" };
for (let i = 0; i < 128; i++) {
  check(vmLeafCall(vmLeafInt, token, cycle, token, cycle) === 3, "small int");
  check(vmLeafCall(vmLeafUndefined, token, cycle, token, cycle) === undefined, "undefined");
  check(vmLeafCall(vmLeafIdentity, token, cycle, token, cycle) === cycle, "owned result");
  check(vmLeafCall(vmLeafAddConst, 7) === 10, "integer constant");
  check(vmLeafCall(vmLeafAddArgs, 7, 8) === 15, "integer arguments");
  check(vmLeafCall(vmLeafNull) === null, "null");
  check(vmLeafCall(vmLeafBool) === true, "boolean");
  for (const s of ["a", "b", "c", "z"])
    check(vmLeafCall(vmLeafChars, s) === (s == "a" || s == "b" || s == "c"), "character predicate");
  check(vmLeafMethod(x, y) === -1, "compound");
  if (!(i & 7)) {
    std.gc();
    x.extra = i;
    y.extra = i;
  }
}
for (const value of [token, cycle, "hello", Symbol("leaf"), 42n, null, undefined])
  check(vmLeafCall(vmLeafIdentity, 0, 1, 2, value) === value, "result kinds");
for (let i = 0; i < 32; i++) {
  check(vmLeafTail(vmLeafAddConst, 7) === 10, "tail");
  check(vmLeafTail(vmLeafChars, "b") === true, "predicate tail");
}
for (const value of [2147483647, 1.25, "s"])
  check(vmLeafCall(vmLeafAddConst, value) === value + 3, "addition fallback");
let coercions = 0;
const coercer = {
  valueOf() {
    coercions++;
    std.gc();
    return 9;
  },
};
check(vmLeafCall(vmLeafAddConst, coercer) === 12 && coercions === 1, "allocating coercion");
let threw = false;
try {
  vmLeafCall(vmLeafAddConst, Symbol());
} catch (e) {
  threw = e instanceof TypeError;
}
check(threw, "abrupt coercion");
let gets = 0;
const accessor = {
  get left() {
    gets++;
    std.gc();
    return "b";
  },
  compare: vmLeafCompare,
};
check(vmLeafMethod(accessor, y) === 0 && gets === 1, "compound own getter fallback");
try {
  String.prototype.localeCompare = function () {
    return 37;
  };
  check(vmLeafMethod(x, y) === 37, "changed builtin");
} finally {
  Object.defineProperty(String.prototype, "localeCompare", descriptor);
}
check(vmLeafMethod(x, y) === -1, "restored builtin");
const wrapped = { left: "e\u0301", compare: vmLeafCompare },
  peer = { right: "é" };
check(
  vmLeafMethod(wrapped, peer) === intrinsic.call(wrapped.left, peer.right),
  "wide normalization",
);
std.gc();
print("LINUX_VM_LEAVES_PATHS_OK " + checks);
