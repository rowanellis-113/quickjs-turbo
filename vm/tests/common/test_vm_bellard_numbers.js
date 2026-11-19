/* Run with both the native VM and the original C interpreter selected. */
function check(a, b) {
  if (!Object.is(a, b)) throw Error("numeric backport: " + a + " != " + b);
}
function add(a, b) {
  return a + b;
}
function sub(a, b) {
  return a - b;
}
function mul(a, b) {
  return a * b;
}
const values = [
  -2147483648,
  -3,
  -1,
  -0,
  0,
  1,
  3,
  2147483647,
  -0.5,
  0.5,
  1.25,
  2147483648,
  Infinity,
  -Infinity,
  NaN,
];
for (let a of values) {
  for (let b of values) {
    /* Function and eval forms exercise distinct opcode/argument paths. */
    globalThis.a = a;
    globalThis.b = b;
    check(add(a, b), eval("a+b"));
    check(sub(a, b), eval("a-b"));
    check(mul(a, b), eval("a*b"));
  }
}
check(add(1, 0.5), 1.5);
check(add(0.5, 1), 1.5);
check(sub(-2147483648, 0.5), -2147483648.5);
check(mul(-1, 0.0), -0);
check(mul(-0, -1), 0);
check(add("x", 0.5), "x0.5");
check(add(0.5, "x"), "0.5x");
check(sub(null, 0.5), -0.5);
check(mul(true, 0.5), 0.5);
check(add(undefined, 0.5), NaN);
let calls = 0;
let o = {
  valueOf() {
    calls++;
    return 2;
  },
};
check(add(o, 0.5), 2.5);
check(calls, 1);
check(sub(0.5, o), -1.5);
check(calls, 2);
check(mul(o, 0.5), 1);
check(calls, 3);
check(add(1n, 2n), 3n);
for (let f of [add, sub, mul]) {
  let threw = false;
  try {
    f(1n, 0.5);
  } catch (e) {
    threw = e instanceof TypeError;
  }
  check(threw, true);
  threw = false;
  try {
    f(Symbol(), 0.5);
  } catch (e) {
    threw = e instanceof TypeError;
  }
  check(threw, true);
}
delete globalThis.a;
delete globalThis.b;
print("BELLARD_NUMERIC_BACKPORT_PASS");
