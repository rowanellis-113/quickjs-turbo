// Differential grammar/number/observable-fallback checks. Linux native child experiment.
let checked = 0;
function* yieldCall(f, args) {
  yield f(...args);
}
function invoke(f, args) {
  let iterator = yieldCall(f, args);
  return iterator.next().value;
}
function encode(v) {
  if (typeof v === "number") {
    if (Number.isNaN(v)) return "number:NaN";
    if (Object.is(v, -0)) return "number:-0";
  }
  return typeof v + ":" + String(v);
}
function outcome(f, args) {
  try {
    return encode(invoke(f, args));
  } catch (e) {
    return "throw:" + e.name;
  }
}
const inputs = [
  -2147483648,
  -2147483647,
  -65536,
  -129,
  -128,
  -100,
  -2,
  -1,
  -0,
  0,
  1,
  2,
  7,
  8,
  100,
  127,
  128,
  32767,
  65536,
  2147483647,
  1.5,
  NaN,
  Infinity,
  -Infinity,
  undefined,
  null,
  true,
  false,
  "7",
  "bad",
  Symbol("s"),
  7n,
];
const constants = [
  -2147483648, -65536, -129, -128, -1, 0, 1, 2, 7, 8, 100, 127, 128, 255, 32767, 32768, 2147483647,
];
const arithmetic = ["+", "-", "*", "%", "&", "|", "^", "<<", ">>", ">>>"];
const compares = ["<", "<=", ">", ">=", "==", "!=", "===", "!=="];
function check(expr, index = 0, vector = inputs) {
  const f = Function("x0", "x1", "x2", "x3", "return " + expr + ";");
  // Finally and its observed counter prevent the reference from matching a leaf.
  const ref = Function(
    "x0",
    "x1",
    "x2",
    "x3",
    "try { return " + expr + "; } finally { referenceCalls++; }",
  );
  for (const v of vector) {
    const args = [13, 17, 19, 23];
    args[index] = v;
    const actual = outcome(f, args),
      expected = outcome(ref, args);
    if (actual !== expected)
      throw Error(expr + " input " + encode(v) + " actual " + actual + " expected " + expected);
    checked++;
  }
}
// Function() sees the script global binding, and this counter is only a reference side effect.
globalThis.referenceCalls = 0;
for (const k of constants) {
  for (const op of arithmetic) check("(x0 " + op + " (" + k + "))");
  for (const op of compares) check("(x0 " + op + " (" + k + "))");
}
for (const op of arithmetic)
  for (const cmp of compares)
    for (const rhs of [-1, 0, 3, 100]) check("((x0 " + op + " (" + rhs + ")) " + cmp + " 0)");
for (let n = 1; n < 4; n++)
  for (const op of arithmetic)
    check("(x" + n + " " + op + " 3)", n, [0, 7, -7, 2147483647, -2147483648]);
// Slow conversion must run exactly once and may GC/reenter safely.
for (const expr of ["x0+3", "x0%100===0", "x0*0", "x0<3"]) {
  const f = Function("x0", "return " + expr + ";");
  const ref = Function("x0", "try { return " + expr + "; } finally { referenceCalls++; }");
  function argument(log) {
    return {
      [Symbol.toPrimitive](hint) {
        log.push(hint);
        gc();
        return 7;
      },
    };
  }
  let a = [],
    b = [];
  const actual = outcome(f, [argument(a)]),
    expected = outcome(ref, [argument(b)]);
  if (actual !== expected || JSON.stringify(a) !== JSON.stringify(b) || a.length !== 1)
    throw Error("observable fallback " + expr);
  checked++;
}
// Unexpected bytecode following otherwise matching expressions must fall back without committing.
for (const body of [
  "return (x0%100===0) ? 7 : 8;",
  "return (x0+3)+4;",
  "return (x0*2) / 3;",
  "return [x0%100===0];",
]) {
  const f = Function("x0", body),
    ref = Function("x0", "try {" + body + "} finally {referenceCalls++;}");
  for (const v of [0, 1, -1, -0, 2147483647]) {
    if (outcome(f, [v]) !== outcome(ref, [v])) throw Error("late miss " + body);
    checked++;
  }
}
// Read live captured cells, both operand orders, and preserve integer truth tests.
for (const k of constants)
  for (const op of arithmetic) {
    for (const expression of ["c " + op + " x0", "x0 " + op + " c", "!(c " + op + " x0)"]) {
      const f = Function("c", "return function(x0){return " + expression + ";}")(k);
      const ref = Function(
        "c",
        "return function(x0){try{return " + expression + ";}finally{referenceCalls++;}}",
      )(k);
      for (const value of inputs) {
        if (outcome(f, [value]) !== outcome(ref, [value]))
          throw Error("captured " + expression + " value " + encode(value) + " constant " + k);
        checked++;
      }
    }
  }
for (const op of arithmetic) {
  const f = Function("x0", "x1", "return x0 " + op + " x1;");
  const ref = Function("x0", "x1", "try{return x0 " + op + " x1;}finally{referenceCalls++;}");
  for (const a of [-2147483648, -1, -0, 0, 7, 2147483647])
    for (const b of [-1, 0, 3, 31, 32, 2147483647]) {
      if (outcome(f, [a, b]) !== outcome(ref, [a, b])) throw Error("two arguments " + op);
      checked++;
    }
}
function changingCell() {
  let cell = 7;
  return [
    (x) => cell % x,
    (v) => {
      cell = v;
    },
  ];
}
const [captured, change] = changingCell();
for (const value of [7, 11, -11, -0, 2147483647]) {
  change(value);
  gc();
  if (outcome(captured, [3]) !== encode(value % 3)) throw Error("live detached captured cell");
  checked++;
}
function beforeInitialization() {
  const f = (x) => uninitialized % x;
  const result = outcome(f, [3]);
  if (result !== "throw:ReferenceError") throw Error("captured TDZ " + result);
  return;
  let uninitialized = 7;
}
beforeInitialization();
checked++;
print("integer-expression semantics OK " + checked);
