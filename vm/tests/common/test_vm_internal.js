/* Ordinary CLI entry and C built-in callbacks, without a special API driver. */
function entryCheck(actual, expected) {
  if (actual !== expected) throw new Error("entry mismatch " + actual + " != " + expected);
}
function entryLeaf(a) {
  return a + 3;
}
function entryMiddle(a) {
  return entryLeaf(entryLeaf(a));
}
function entryTop(a) {
  return entryMiddle(entryMiddle(a));
}
function entryMissing(a, b, c) {
  return a + (b === undefined ? 20 : b) + (c === undefined ? 20 : c);
}
function entryWritable(a, b) {
  b = 2;
  return a + b;
}
function entryThrow(a) {
  throw a;
}
function entryLegacy(a) {
  try {
    return entryTop(a);
  } finally {
  }
}
function entryCompare(a, b) {
  return entryMiddle(a) - entryMiddle(b);
}
function entryMap(a) {
  return entryMiddle(a);
}
function entryReduce(a, b) {
  return a + b;
}
function entryNested() {
  let s = 0;
  for (let i = 0; i < 100; i++) s += entryTop(i);
  return s;
}
function entryCapture(a) {
  return function (b) {
    return entryTop(a + b);
  };
}
function* entryGenerator(a) {
  yield entryTop(a);
}
function EntryConstructor(a) {
  this.value = entryTop(a);
}
entryCheck(entryNested(), 6150);
entryCheck(entryLegacy(30), 42);
entryCheck(entryMissing(2), 42);
entryCheck(entryWritable(40), 42);
entryCheck([7, 2, 9, 1, 5, 3, 8, 4, 6].sort(entryCompare)[4], 5);
entryCheck([1, 2, 3].map(entryMap).reduce(entryReduce, 0), 24);
entryCheck(new Int32Array([3, 1, 2]).sort(entryCompare)[1], 2);
entryCheck(entryCapture(20)(10), 42);
entryCheck(entryGenerator(30).next().value, 42);
entryCheck(new EntryConstructor(30).value, 42);

// Small callbacks from a synchronous generator must retain the complete
// legacy call contract, including borrowed operands and abrupt completion.
function* entryGeneratorCallbacks(callback, values) {
  for (const value of values) yield callback(value);
}
const entryCycle = {};
entryCycle.self = entryCycle;
const entryIdentity = (value) => value;
const entryGeneratorValues = [undefined, null, -0, 0.25, 2147483647, 123n, "x", entryCycle];
const entryGeneratorIdentity = Array.from(
  entryGeneratorCallbacks(entryIdentity, entryGeneratorValues),
);
for (let i = 0; i < entryGeneratorValues.length; i++)
  entryCheck(Object.is(entryGeneratorIdentity[i], entryGeneratorValues[i]), true);
entryCheck(entryGeneratorIdentity[7].self, entryCycle);
entryCheck(Array.from(entryGeneratorCallbacks((value, missing) => missing, [1]))[0], undefined);
entryCheck(
  Array.from(
    entryGeneratorCallbacks(
      (value) => {
        value = 42;
        return value;
      },
      [entryCycle],
    ),
  )[0],
  42,
);
const entryClosedOver = entryCycle;
entryCheck(Array.from(entryGeneratorCallbacks(() => entryClosedOver, [0]))[0], entryCycle);
let entryGeneratorCoercions = 0;
const entryGeneratorCoercer = {
  valueOf() {
    entryGeneratorCoercions++;
    return 39;
  },
};
entryCheck(Array.from(entryGeneratorCallbacks(entryLeaf, [entryGeneratorCoercer]))[0], 42);
entryCheck(entryGeneratorCoercions, 1);
let entryGeneratorFinally = 0;
function* entryGeneratorThrow(callback, value) {
  try {
    yield callback(value);
  } finally {
    entryGeneratorFinally++;
  }
}
try {
  entryGeneratorThrow(entryThrow, entryCycle).next();
  throw new Error("missing generator callback throw");
} catch (error) {
  entryCheck(error, entryCycle);
}
entryCheck(entryGeneratorFinally, 1);
entryCheck(Array.from(entryGeneratorCallbacks((value) => value % 3n, [10n]))[0], 1n);
entryCheck(Array.from(entryGeneratorCallbacks(entryLeaf, [2147483647]))[0], 2147483650);
entryCheck(Array.from(entryGeneratorCallbacks(Math.abs, [-7]))[0], 7);
const entryGeneratorProxy = new Proxy(entryIdentity, {
  apply(target, receiver, args) {
    return Reflect.apply(target, receiver, args);
  },
});
entryCheck(Array.from(entryGeneratorCallbacks(entryGeneratorProxy, [entryCycle]))[0], entryCycle);
try {
  entryThrow("internal-throw");
  throw new Error("missing throw");
} catch (e) {
  entryCheck(e, "internal-throw");
}
let entryTraceCalls = 0;
const entryOldPrepare = Error.prepareStackTrace;
Error.prepareStackTrace = function () {
  entryTraceCalls++;
};
function entryOverflow() {
  entryOverflow();
}
try {
  entryOverflow();
  throw new Error("missing overflow");
} catch (e) {
  entryCheck(e instanceof RangeError, true);
}
entryCheck(entryTraceCalls, 0);
// Budget release must allow an ordinary stack hook to execute after overflow.
Error.prepareStackTrace = function () {
  entryTraceCalls++;
  return "entry-stack";
};
function entryOrdinaryError() {
  throw new Error("after overflow");
}
try {
  entryOrdinaryError();
} catch (e) {
  entryCheck(e.stack, "entry-stack");
}
entryCheck(entryTraceCalls > 0, true);
Error.prepareStackTrace = entryOldPrepare;
print(
  "internal CLI: nested, legacy-to-native, writable/missing args, Array/TypedArray callbacks, captures, generator, constructor, catch and overflow/backtrace recovery passed",
);
