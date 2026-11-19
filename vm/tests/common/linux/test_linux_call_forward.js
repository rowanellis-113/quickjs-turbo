/* Observable .call semantics across normalization, ownership and fallback. */
"use strict";
globalThis.forwardCall = Function.prototype.call;
let checks = 0;
function same(actual, expected, label) {
  ++checks;
  if (!Object.is(actual, expected)) throw Error(label + ": " + String(actual));
}
function throws(fn, type, label) {
  ++checks;
  try {
    fn();
  } catch (error) {
    if (error instanceof type) return;
    throw Error(label + ": wrong exception " + error);
  }
  throw Error(label + ": no exception");
}
function driver(depth, actual) {
  let args = Array(actual).fill("v");
  let expression;
  if (depth === 1) expression = "f.call(receiver";
  else expression = "forwardCall.call(" + "forwardCall,".repeat(depth - 2) + "f,receiver";
  if (args.length) expression += "," + args.join(",");
  expression += ")";
  return Function("f", "receiver", "v", "return " + expression);
}
const receiver = { marker: 73 };
const seed = { id: 19 };
seed.self = seed;
for (const depth of [1, 2, 3, 8, 16, 64, 65]) {
  for (const actual of [0, 1, 4]) {
    const invoke = driver(depth, actual);
    for (const formals of [0, 1, 2, 4, 16, 128]) {
      const names = Array.from({ length: formals }, (_, i) => "a" + i);
      const readonly = Function(...names, formals ? "return a0" : "return 19");
      const writable = Function(
        ...names,
        formals ? "let old=a0;a0=undefined;return old" : "return 19",
      );
      for (let repeat = 0; repeat < 5; ++repeat) {
        const expected = formals ? (actual ? seed : undefined) : 19;
        same(invoke(readonly, receiver, seed), expected, "readonly");
        same(invoke(writable, receiver, seed), expected, "writable");
      }
      if (formals) {
        const captured = Function(...names, "let held=()=>a0;return held");
        const mutable = Function(...names, "let change=()=>{a0=37};change();return()=>a0");
        const hiddenWrite = Function(...names, "let neverCalled=()=>{a0=37};return()=>a0");
        for (let repeat = 0; repeat < 3; ++repeat) {
          same(invoke(captured, receiver, seed)(), actual ? seed : undefined, "escaping cell");
          same(invoke(mutable, receiver, seed)(), 37, "mutable cell");
          same(
            invoke(hiddenWrite, receiver, seed)(),
            actual ? seed : undefined,
            "unexecuted writer",
          );
        }
      }
    }
    const strictThis = Function("'use strict';return this");
    const sloppyThis = Function("return this");
    same(invoke(strictThis, receiver, seed), receiver, "strict object this");
    same(invoke(strictThis, undefined, seed), undefined, "strict undefined this");
    same(invoke(strictThis, -0, seed), -0, "strict primitive this");
    same(invoke(sloppyThis, undefined, seed), globalThis, "sloppy global this");
    same(Number(invoke(sloppyThis, 12, seed)), 12, "sloppy primitive boxing");
    const argumentCount = Function("return arguments.length");
    same(invoke(argumentCount, receiver, seed), actual, "arguments fallback");
  }
}
for (const depth of [1, 2, 3, 8]) {
  const invoke = driver(depth, 1);
  const identity = Function("a", "return a");
  for (const value of [undefined, null, false, true, 0, -0, NaN, Infinity, 2147483647, "abc", seed])
    for (let repeat = 0; repeat < 5; ++repeat)
      same(invoke(identity, receiver, value), value, "leaf return");
  const increment = Function("a", "return a+1");
  for (const value of [0, -1, 2147483647, -2147483648, "a", 1.5])
    same(invoke(increment, receiver, value), value + 1, "leaf arithmetic fallback");
  let calls = 0;
  const proxy = new Proxy(identity, {
    apply(target, self, args) {
      ++calls;
      same(self, receiver, "proxy receiver");
      return args[0];
    },
  });
  same(invoke(proxy, receiver, seed), seed, "proxy fallback");
  same(calls, 1, "proxy call count");
  same(invoke(identity.bind(receiver), null, seed), seed, "bound fallback");
  throws(() => invoke(class C {}, receiver, seed), TypeError, "class fallback");
  throws(() => invoke(17, receiver, seed), TypeError, "noncallable");
  const boom = Function("throw Error('forward sentinel')");
  for (let repeat = 0; repeat < 6; ++repeat) {
    throws(() => invoke(boom, receiver, seed), Error, "throw/unwind");
    same(invoke(identity, receiver, seed), seed, "post-unwind recovery");
  }
}
const ownCall = Function("a", "return a");
ownCall.call = function () {
  return 911;
};
same(driver(1, 1)(ownCall, receiver, seed), 911, "own call override");
delete ownCall.call;
same(driver(1, 1)(ownCall, receiver, seed), seed, "override recovery");
if (checks < 2000) throw Error("incomplete forward fixture");
print("LINUX_CALL_FORWARD_OK checks=" + checks);
