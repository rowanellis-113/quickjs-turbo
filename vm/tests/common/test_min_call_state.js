/* Interpreter continuation, capture lifetime and fallback regression tests. */
function check(value, expected) {
  if (!Object.is(value, expected)) throw new Error("got " + value + ", expected " + expected);
}
function leaf(x) {
  return x + 1;
}
function nested(x) {
  return leaf(leaf(x));
}
check(nested(20), 22);
function argc(a, b, ...rest) {
  return [a, b, rest.length, arguments.length].join();
}
check(argc(3), "3,,0,1");
check(argc(3, 4, 5, 6), "3,4,2,4");
function argumentState(a) {
  nested(1);
  arguments[0] = 9;
  return arguments[0] + a;
}
check(argumentState(1), 10);
const receiver = {
  x: 17,
  run(n) {
    nested(n);
    return this.x + leaf(n);
  },
};
check(receiver.run(4), 22);
function make(x) {
  nested(1);
  return () => ++x;
}
const captures = [];
for (let i = 0; i < 20000; i++) captures.push(make(i));
check(captures[0](), 1);
check(captures[19999](), 20000);
check(captures[0](), 2);
function throws(x) {
  if (x) throw new Error("leaf failure");
  return leaf(x);
}
function catches(x) {
  try {
    return throws(x);
  } catch (e) {
    return e.message;
  }
}
check(catches(1), "leaf failure");
check(catches(0), 1);
let finalized = 0;
function finallyCall() {
  try {
    return throws(1);
  } finally {
    finalized += leaf(1);
  }
}
try {
  finallyCall();
} catch (e) {
  check(e.message, "leaf failure");
}
check(finalized, 2);
function recur(n) {
  return n ? recur(n - 1) + 1 : 0;
}
check(recur(8), 8);
function tail(n) {
  return leaf(n);
}
for (let i = 0; i < 100000; i++) check(tail(i), i + 1);
check([4, 1, 3, 2].sort((a, b) => nested(a) - nested(b)).join(), "1,2,3,4");
check(leaf.bind(null, 4)(), 5);
check(
  new Proxy(leaf, {
    apply(f, t, a) {
      return nested(f.apply(t, a));
    },
  })(4),
  7,
);
class Base {
  constructor(x) {
    this.x = nested(x);
  }
}
class Derived extends Base {
  constructor(x) {
    super(x);
    this.y = new.target;
  }
}
let instance = new Derived(5);
check(instance.x, 7);
check(instance.y, Derived);
function* gen(x) {
  yield nested(x);
  yield make(x);
  return nested(x + 1);
}
const iterator = gen(3);
check(iterator.next().value, 5);
check(iterator.next().value(), 4);
check(iterator.next().value, 6);
async function asyncCall(x) {
  const y = nested(x);
  return nested(await Promise.resolve(y));
}
asyncCall(3).then((x) => check(x, 7));
try {
  (function stackLeaf() {
    throw new Error("stack");
  })();
} catch (e) {
  if (!e.stack.includes("stackLeaf")) throw new Error("missing logical frame");
}

/* Function() deliberately exercises non-strict mapped arguments and this. */
const sloppy = Function(
  "a",
  "b",
  "callback",
  "callback(a); arguments[0] = 9; callback(a);" + "return { args: arguments, get: () => a };",
);
const mapped = sloppy(1, 2, nested);
check(mapped.get(), 9);
mapped.args[0] = 21;
check(mapped.get(), 21);
const boxedThis = Function("callback", "callback(1); return this.valueOf();");
check(boxedThis.call(7, nested), 7);
function target() {
  nested(1);
  return new.target;
}
check(target(), undefined);
function constructedTarget() {
  nested(1);
  this.target = new.target;
  this.child = target();
}
const constructed = new constructedTarget();
check(constructed.target, constructedTarget);
check(constructed.child, undefined);
function illegalClassCall() {
  nested(1);
  Derived(2);
}
let classRejected = false;
try {
  new illegalClassCall();
} catch (e) {
  classRejected = e instanceof TypeError;
}
check(classRejected, true);
function* generatorArguments(a, ...rest) {
  nested(a);
  yield [this.x, arguments.length, a, rest.length].join();
  nested(a);
  return [this.x, arguments.length, a, rest.length].join();
}
const argumentIterator = generatorArguments.call({ x: 17 }, 3, 4, 5);
check(argumentIterator.next().value, "17,3,3,2");
check(argumentIterator.next().value, "17,3,3,2");

/* Small callees must preserve arithmetic, conversion and exception semantics. */
function plusThree(x) {
  return x + 3;
}
function subtract(x, y) {
  return x - y;
}
function multiply(x, y) {
  return x * y;
}
function identity(x) {
  return x;
}
function nothing() {
  return;
}
check(plusThree(4), 7);
check(plusThree(1.25), 4.25);
check(plusThree("4"), "43");
check(plusThree(2147483647), 2147483650);
check(subtract(-2147483648, 1), -2147483649);
check(multiply(2147483647, 2147483647), 4611686014132420600);
check(multiply(-1, 0), -0);
check(multiply(0, -1), -0);
check(subtract(7n, 2n), 5n);
check(multiply(7n, 2n), 14n);
check(nothing(), undefined);
const retained = { marker: 37 };
check(identity(retained), retained);
let conversions = 0;
const convertible = {
  [Symbol.toPrimitive]() {
    conversions++;
    return nested(4);
  },
};
check(plusThree(convertible), 9);
check(conversions, 1);
let conversionRejected = false;
try {
  plusThree(1n);
} catch (e) {
  conversionRejected = e instanceof TypeError && e.stack.includes("plusThree");
}
check(conversionRejected, true);
let customRejected = false;
try {
  plusThree({
    [Symbol.toPrimitive]() {
      throw new Error("conversion failed");
    },
  });
} catch (e) {
  customRejected = e.message === "conversion failed" && e.stack.includes("plusThree");
}
check(customRejected, true);
let tdzRejected = false;
try {
  (function () {
    const read = () => value;
    read();
    let value = 1;
  })();
} catch (e) {
  tdzRejected = e instanceof ReferenceError;
}
check(tdzRejected, true);
