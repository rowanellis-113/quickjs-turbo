// Differential values,observable fallbacks,overflow,-0 and ownership semantics.
let checked = 0;
function require(v, label) {
  if (!v) throw Error(label);
  checked++;
}
function enc(v) {
  if (typeof v === "number" && Object.is(v, -0)) return "-0";
  if (typeof v === "number" && Number.isNaN(v)) return "NaN";
  return typeof v + ":" + String(v);
}
function outcome(fn, args) {
  try {
    return enc(fn(...args));
  } catch (e) {
    return "throw:" + e.name;
  }
}
const inputs = [
  -2147483648,
  -2147483647,
  -65536,
  -129,
  -1,
  -0,
  0,
  1,
  2,
  7,
  31,
  32,
  33,
  65536,
  2147483647,
  2147483648,
  4294967295,
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
  Symbol("x"),
  7n,
  -1n,
];
globalThis.scalarReferenceCalls = 0;
for (const op of ["|", "^", "<<", ">>", ">>>", "%"]) {
  const fn = Function("a", "b", "return a " + op + " b;"),
    ref = Function("a", "b", "try{return a " + op + " b;}finally{scalarReferenceCalls++;}");
  for (const a of inputs)
    for (const b of inputs)
      require(outcome(fn, [a, b]) === outcome(ref, [a, b]), "binary " +
        op +
        " " +
        enc(a) +
        " " +
        enc(b));
}
for (const expr of ["~a", "-a", "++a.v", "--a.v", "a.v++", "a.v--"]) {
  const field = expr.includes(".v"),
    fn = Function("a", "return " + expr + ";"),
    ref = Function("a", "try{return " + expr + ";}finally{scalarReferenceCalls++;}");
  for (const a of inputs) {
    const x = field ? { v: a } : a,
      y = field ? { v: a } : a;
    require(outcome(fn, [x]) === outcome(ref, [y]), "unary " + expr + " " + enc(a));
    if (field) require(enc(x.v) === enc(y.v), "updated field " + expr);
  }
}
for (const expr of ["a===void 0", "a===null", "(a??null)===null"]) {
  const fn = Function("a", "return " + expr + ";"),
    ref = Function("a", "try{return " + expr + ";}finally{scalarReferenceCalls++;}");
  for (const a of [...inputs, {}, [], () => 1, new Number(1)])
    require(outcome(fn, [a]) === outcome(ref, [a]), "predicate " + expr);
}
function nested(n) {
  return (n ^ 3) >>> 0;
}
for (const expr of ["a|b", "a^b", "a<<b", "a>>b", "a>>>b", "a%b"]) {
  const fn = Function("a", "b", "return " + expr + ";"),
    ref = Function("a", "b", "try{return " + expr + ";}finally{scalarReferenceCalls++;}");
  for (const side of [0, 1])
    for (const answer of [7, -0, NaN, 7n, Symbol("bad")]) {
      function args(log) {
        let a = [17, 3];
        a[side] = {
          [Symbol.toPrimitive](hint) {
            log.push(hint);
            gc();
            require(nested(7) === 4, "nested conversion");
            return answer;
          },
        };
        return a;
      }
      let x = [],
        y = [];
      require(outcome(fn, args(x)) === outcome(ref, args(y)) &&
        JSON.stringify(x) === JSON.stringify(y) &&
        x.length === 1, "conversion once " + expr);
    }
}
for (const expr of ["++a.v", "--a.v", "a.v++", "a.v--"]) {
  const fn = Function("a", "return " + expr + ";"),
    ref = Function("a", "try{return " + expr + ";}finally{scalarReferenceCalls++;}");
  function object(log) {
    let v = {
      [Symbol.toPrimitive](hint) {
        log.push(hint);
        gc();
        return 7;
      },
    };
    return {
      get v() {
        log.push("get");
        gc();
        return v;
      },
      set v(x) {
        log.push("set:" + x);
        gc();
        v = x;
      },
    };
  }
  let x = [],
    y = [];
  require(outcome(fn, [object(x)]) === outcome(ref, [object(y)]) &&
    JSON.stringify(x) === JSON.stringify(y), "get/set conversion " + expr);
}
// Null receiver is checked before a computed ++ key conversion.
for (const receiver of [null, undefined]) {
  let called = 0;
  const key = {
    [Symbol.toPrimitive]() {
      called++;
      throw Error("key must not run");
    },
  };
  try {
    receiver[key]++;
    throw Error("no receiver throw");
  } catch (e) {
    require(e instanceof TypeError && called === 0, "null receiver before key");
  }
}
// Real object-key conversion and prototype setters retain original ordering.
for (const value of [7, 7n, undefined]) {
  const fn = Function("a", "b", "c", "a[b]=c;return a[b];"),
    ref = Function("a", "b", "c", "try{a[b]=c;return a[b];}finally{scalarReferenceCalls++;}");
  function key(log) {
    return {
      [Symbol.toPrimitive](hint) {
        log.push(hint);
        gc();
        return "v";
      },
    };
  }
  let x = [],
    y = [],
    a = {},
    b = {};
  require(outcome(fn, [a, key(x), value]) === outcome(ref, [b, key(y), value]) &&
    JSON.stringify(x) === JSON.stringify(y), "property key conversion");
}
// Numeric atoms keep their allocating original path;flat atoms own references.
for (const text of ["", "scalar_value", "123", "2147483648"]) {
  const fn = Function("return " + JSON.stringify(text)),
    ref = Function("try{return " + JSON.stringify(text) + ";}finally{scalarReferenceCalls++;}");
  let prior;
  for (let i = 0; i < 128; i++) {
    let out = fn();
    require(out === text && out === ref(), "atom " + text);
    gc();
    prior = out;
  }
  require(prior === text, "atom retained");
}
function pair(a, b) {
  let x = a,
    y = b;
  return [x, y];
}
for (let i = 0; i < 128; i++) {
  let p = { i };
  let v = pair(p, p);
  require(v[0] === p && v[1] === p, "fused duplicate aliases");
  gc();
}
class C {
  v = 9;
}
for (let i = 0; i < 128; i++) {
  let c = new C();
  require(c.v === 9, "constructor initializer stack");
  gc();
}
print("AARCH64_SCALAR_SEMANTICS_OK " + checked);
