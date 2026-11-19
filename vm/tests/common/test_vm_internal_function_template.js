import * as std from "qjs:std";
let checks = 0;
function check(value, message) {
  checks++;
  if (!value) throw Error("INTERNAL_FUNCTION " + checks + ": " + message);
}
function descriptor(fn, length) {
  check(typeof fn === "function", "callable");
  check(fn.length === length && fn.name === "", "initial length/name");
  check(Object.getOwnPropertyNames(fn).join(",") === "length,name", "own key order");
  for (const key of ["length", "name"]) {
    const d = Object.getOwnPropertyDescriptor(fn, key);
    check(d.configurable && !d.enumerable && !d.writable, "data descriptor " + key);
  }
  check(Object.getPrototypeOf(fn) === Function.prototype, "function prototype");
  check(!Object.hasOwn(fn, "prototype"), "no constructor prototype");
  check(!Object.hasOwn(fn, "caller") && !Object.hasOwn(fn, "arguments"), "no legacy properties");
}
for (let round = 0; round < 100; round++) {
  let resolve, reject;
  const p = new Promise((a, b) => {
    resolve = a;
    reject = b;
  });
  descriptor(resolve, 1);
  descriptor(reject, 1);
  check(resolve !== reject, "distinct resolving functions");
  Object.defineProperty(resolve, "name", { value: "changed", configurable: true });
  delete resolve.length;
  Object.defineProperty(reject, "length", {
    get() {
      return 77;
    },
    configurable: true,
  });
  Object.freeze(reject);
  std.gc();
  let r2, j2;
  const p2 = new Promise((a, b) => {
    r2 = a;
    j2 = b;
  });
  descriptor(r2, 1);
  descriptor(j2, 1);
  check(resolve.name === "changed" && reject.length === 77, "mutated values remain distinct");
  const value = { round };
  value.self = value;
  resolve(value);
  reject("ignored");
  r2(round);
  j2("ignored");
  check((await p) === value && value.self === value, "resolution preserves payload root");
  check((await p2) === round, "second resolution remains independent");
}
{
  const order = [];
  let resolve;
  const p = new Promise((r) => {
    resolve = r;
  });
  p.then((v) => order.push("first:" + v));
  p.then((v) => order.push("second:" + v));
  resolve(42);
  order.push("sync");
  check(order.join(",") === "sync", "reactions stay queued");
  await p;
  check(order.join(",") === "sync,first:42,second:42", "reaction order");
}
{
  let gets = 0,
    calls = 0;
  const thenable = {
    get then() {
      gets++;
      return (resolve, reject) => {
        calls++;
        descriptor(resolve, 1);
        descriptor(reject, 1);
        resolve(73);
        reject(74);
        throw Error("ignored after resolve");
      };
    },
  };
  check((await Promise.resolve(thenable)) === 73, "thenable resolution");
  check(gets === 1 && calls === 1, "thenable getter and invocation count");
  const marker = {};
  try {
    await Promise.resolve({
      get then() {
        throw marker;
      },
    });
    check(false, "then getter throws");
  } catch (e) {
    check(e === marker, "then getter error identity");
  }
  let resolve;
  const cyclic = new Promise((r) => {
    resolve = r;
  });
  resolve(cyclic);
  try {
    await cyclic;
    check(false, "self resolution rejects");
  } catch (e) {
    check(e instanceof TypeError, "self resolution TypeError");
  }
}
async function* nested(level) {
  if (level) yield* nested(level - 1);
  yield { level };
  return 99;
}
for (let round = 0; round < 12; round++) {
  const levels = [];
  for await (const value of nested(4)) {
    std.gc();
    levels.push(value.level);
  }
  check(levels.join(",") === "0,1,2,3,4", "nested async generator values");
  const g = nested(2);
  check((await g.next()).value.level === 0, "generator initial next");
  const returned = await g.return(17);
  check(returned.value === 17 && returned.done, "generator return closes delegation");
  check((await g.next()).done, "closed generator stays closed");
}
std.gc();
print("INTERNAL_FUNCTION_OK checks=" + checks);
