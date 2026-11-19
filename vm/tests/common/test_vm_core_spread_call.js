/* Dense prefix/spread semantics, observable fallback and suspended callers. */
import * as std from "qjs:std";
(function prefixSpreadSemantics() {
  "use strict";
  let checks = 0;
  const trace = [];
  function assert(ok, label) {
    ++checks;
    if (!ok) throw Error(label);
  }
  function one(f, a, tail) {
    return f(a, ...tail);
  }
  function method(o, a, tail) {
    return o.f(a, ...tail);
  }
  function two(f, a, b, tail) {
    if (a === -999) return f(0, 0, 0, 0, 0, 0);
    return f(a, b, ...tail);
  }
  function local(f, a, tail) {
    let source = tail;
    return f(a, ...source);
  }
  function sum(...args) {
    let total = 0;
    for (let i = 0; i < args.length; i++) total += args[i];
    return total;
  }
  for (let i = 0; i < 300; i++) {
    assert(one(sum, 1, [2, 3, 4]) === 10, "one");
    assert(
      method(
        {
          base: 10,
          f(a, b, c) {
            return this.base + a + b + c;
          },
        },
        1,
        [2, 3],
      ) === 16,
      "method",
    );
    assert(two(sum, 1, 2, [3, 4]) === 10, "two");
    assert(local(sum, 1, [2, 3]) === 6, "local");
    assert(one(sum, 9, []) === 9, "empty");
  }
  const object = { name: "object" },
    symbol = Symbol("prefix"),
    big = 123n;
  function identity(a, b, c, d) {
    assert(a === object && b === symbol && c === big && d === "tail", "tags");
    return a;
  }
  assert(one(identity, object, [symbol, big, "tail"]) === object, "identity");
  let captured = [2, 3];
  function closure(f, a) {
    return f(a, ...captured);
  }
  assert(closure(sum, 1) === 6, "closure");
  captured = [4, 5];
  assert(closure(sum, 1) === 10, "live closure");
  const original = [{ x: 2 }, { x: 3 }],
    prefix = { x: 1 };
  assert(
    one(
      (a, b, c) => {
        original.length = 0;
        a.x = 4;
        std.gc();
        return a.x + b.x + c.x;
      },
      prefix,
      original,
    ) === 9,
    "snapshot GC",
  );
  assert(prefix.x === 4 && original.length === 0, "alias effects");
  const sentinel = { sentinel: 1 };
  try {
    one(
      () => {
        throw sentinel;
      },
      1,
      [2, 3],
    );
    assert(false, "throw");
  } catch (e) {
    assert(e === sentinel, "same throw");
  }
  assert(one(sum, 1, [2, 3]) === 6, "after throw");
  const custom = [2, 3];
  Object.defineProperty(custom, Symbol.iterator, {
    get() {
      trace.push("iterator-get");
      return function () {
        trace.push("iterator-call");
        let i = 0;
        return {
          next() {
            trace.push("next-" + i);
            return i < 2 ? { value: custom[i++], done: false } : { done: true };
          },
        };
      };
    },
  });
  assert(one(sum, 1, custom) === 6, "custom iterator");
  const iteratorProto = Object.getPrototypeOf([][Symbol.iterator]());
  const oldNext = iteratorProto.next;
  let nextCalls = 0;
  iteratorProto.next = function () {
    ++nextCalls;
    return oldNext.call(this);
  };
  try {
    assert(one(sum, 1, [2, 3]) === 6, "custom next");
    assert(nextCalls > 0, "next used");
  } finally {
    iteratorProto.next = oldNext;
  }
  const inherited = Object.create(Array.prototype);
  Object.defineProperty(inherited, "1", {
    get() {
      trace.push("inherited-index");
      return 7;
    },
  });
  const hole = [2, , 3];
  Object.setPrototypeOf(hole, inherited);
  assert(one(sum, 1, hole) === 13, "inherited hole");
  const proxy = new Proxy([2, 3], {
    get(o, k, r) {
      trace.push("proxy-" + String(k));
      return Reflect.get(o, k, r);
    },
  });
  assert(one(sum, 1, proxy) === 6, "proxy");
  const explicitThis = { v: 20 };
  assert(
    method(
      {
        f(a, ...rest) {
          assert(this !== explicitThis, "this ownership");
          std.gc();
          return a + sum(...rest);
        },
      },
      1,
      [2, 3],
    ) === 6,
    "method GC",
  );
  for (let n of [0, 2, 8, 127]) {
    const names = Array.from({ length: n }, (_, i) => "p" + i);
    const params = ["f", "tail", ...names];
    const fixed = names.join(",");
    const call = "return f(" + (fixed ? fixed + "," : "") + "...tail);";
    const f = Function(...params, call);
    const values = Array.from({ length: n }, (_, i) => i + 1);
    assert(f(sum, [7, 8], ...values) === (n * (n + 1)) / 2 + 15, "general prefix " + n);
  }
  print("PREFIX_SPREAD_SEMANTICS_OK " + checks + " " + JSON.stringify(trace));
})();
(function coreSpreadSemantics() {
  "use strict";
  let checks = 0;
  const trace = [];
  function assert(ok, label) {
    ++checks;
    if (!ok) throw Error(label);
  }
  function core1(f, a, ...tail) {
    return f(a, ...tail);
  }
  function core0(f, ...tail) {
    return f(...tail);
  }
  function core2(f, a, b, ...tail) {
    return f(a, b, ...tail);
  }
  function coreMethod(o, a, ...tail) {
    return o.f(a, ...tail);
  }
  function shared(f, a, tail, ...unused) {
    return f(a, ...tail);
  }
  function sum(...values) {
    let n = 0;
    for (let i = 0; i < values.length; i++) n += values[i];
    return n;
  }
  for (let i = 0; i < 300; i++) {
    assert(core1(sum, 1, 2, 3, 4) === 10, "rest prefix");
    assert(core0(sum, 1, 2, 3) === 6, "rest zero");
    assert(core2(sum, 1, 2, 3, 4) === 10, "rest two");
    assert(
      coreMethod(
        {
          base: 10,
          f(a, b, c) {
            return this.base + a + b + c;
          },
        },
        1,
        2,
        3,
      ) === 16,
      "rest method",
    );
    assert(core1(sum, 9) === 9, "empty rest");
  }
  const object = { name: "object" },
    symbol = Symbol("core"),
    big = 123n;
  assert(
    core1(
      (a, b, c, d) => a === object && b === symbol && c === big && d === "tail",
      object,
      symbol,
      big,
      "tail",
    ),
    "value tags",
  );
  const source = [{ x: 2 }, { x: 3 }],
    prefix = { x: 1 };
  const result = shared(
    (a, b, c) => {
      source.length = 0;
      a.x = 4;
      std.gc();
      return a.x + b.x + c.x;
    },
    prefix,
    source,
  );
  assert(result === 9 && prefix.x === 4 && source.length === 0, "snapshot GC");
  let captured = [{ x: 5 }, { x: 7 }];
  function closure(f, a, ...unused) {
    return f(a, ...captured);
  }
  assert(
    closure(
      (a, b, c) => {
        captured = null;
        std.gc();
        return a.x + b.x + c.x;
      },
      { x: 1 },
    ) === 13,
    "released source GC",
  );
  const alias = { alias: 1 };
  assert(
    core1(
      (a, b) => {
        std.gc();
        return b;
      },
      alias,
      alias,
    ) === alias,
    "return alias",
  );
  const sentinel = { sentinel: 1 };
  let finalizers = 0;
  for (let i = 0; i < 80; i++) {
    try {
      try {
        core1(
          (a, b) => {
            std.gc();
            throw sentinel;
          },
          alias,
          alias,
        );
        assert(false, "throw absent");
      } finally {
        ++finalizers;
        assert(core1(sum, 1, 2, 3) === 6, "finally reentry");
      }
    } catch (e) {
      assert(e === sentinel, "same exception");
    }
  }
  assert(finalizers === 80, "finally count");
  try {
    core1(null, 1, 2, 3);
    assert(false, "noncallable");
  } catch (e) {
    assert(e instanceof TypeError, "noncallable type");
    trace.push(String(e));
  }
  const custom = [2, 3];
  Object.defineProperty(custom, Symbol.iterator, {
    get() {
      trace.push("iterator-get");
      return function () {
        trace.push("iterator-call");
        let i = 0;
        return {
          next() {
            trace.push("next-" + i);
            return i < 2 ? { value: custom[i++], done: false } : { done: true };
          },
        };
      };
    },
  });
  assert(shared(sum, 1, custom) === 6, "custom iterator");
  const iteratorProto = Object.getPrototypeOf([][Symbol.iterator]()),
    oldNext = iteratorProto.next;
  let nextCalls = 0;
  iteratorProto.next = function () {
    ++nextCalls;
    return oldNext.call(this);
  };
  try {
    assert(core1(sum, 1, 2, 3) === 6, "custom next");
    assert(nextCalls > 0, "next observed");
  } finally {
    iteratorProto.next = oldNext;
  }
  const inherited = Object.create(Array.prototype);
  Object.defineProperty(inherited, "1", {
    get() {
      trace.push("inherited-index");
      return 7;
    },
  });
  const hole = [2, , 3];
  Object.setPrototypeOf(hole, inherited);
  assert(shared(sum, 1, hole) === 13, "inherited hole");
  const proxy = new Proxy([2, 3], {
    get(o, k, r) {
      trace.push("proxy-" + String(k));
      return Reflect.get(o, k, r);
    },
  });
  assert(shared(sum, 1, proxy) === 6, "proxy");
  assert(shared(sum, 1, Object.freeze([2, 3])) === 6, "readonly dense");
  const seventeen = Array.from({ length: 17 }, (_, i) => i + 1);
  assert(shared(sum, 1, seventeen) === 154, "over scratch bound");
  function core8(f, a, b, c, d, e, g, h, i, ...tail) {
    return f(a, b, c, d, e, g, h, i, ...tail);
  }
  assert(core8(sum, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10) === 55, "i8 prefix");
  const throwing = [];
  Object.defineProperty(throwing, Symbol.iterator, {
    get() {
      trace.push("throwing-iterator");
      throw sentinel;
    },
  });
  try {
    shared(null, 1, throwing);
    assert(false, "iterator throw");
  } catch (e) {
    assert(e === sentinel, "iterator before callable check");
  }
  assert(core1(sum, 1, 2, 3) === 6, "after errors");
  print("CORE_SPREAD_SEMANTICS_OK " + checks + " " + JSON.stringify(trace));
})();
{
  ("use strict");
  let checks = 0;
  function assert(ok, message) {
    ++checks;
    if (!ok) throw Error(message);
  }
  function core(f, a, ...tail) {
    return f(a, ...tail);
  }
  function sum(a, b, c) {
    return a.x + b.x + c.x;
  }
  async function asyncCaller(f, a, tail) {
    const result = f(a, ...tail);
    await 0;
    std.gc();
    return result;
  }
  function* generatorCaller(f, a, tail) {
    std.gc();
    yield f(a, ...tail);
    std.gc();
    return f(a, ...tail);
  }
  async function* asyncGeneratorCaller(f, a, tail) {
    yield f(a, ...tail);
    await 0;
    std.gc();
    return f(a, ...tail);
  }
  async function asyncTarget(a, b, c) {
    await 0;
    std.gc();
    return a.x + b.x + c.x;
  }
  function* generatorTarget(a, b, c) {
    std.gc();
    yield a.x + b.x + c.x;
    return a;
  }
  async function* asyncGeneratorTarget(a, b, c) {
    await 0;
    std.gc();
    yield a.x + b.x + c.x;
    return a;
  }
  await (async () => {
    for (let i = 0; i < 30; i++) {
      const a = { x: 1 },
        tail = [{ x: 2 }, { x: 3 }];
      assert((await asyncCaller(sum, a, tail)) === 6, "async caller");
      const g = generatorCaller(sum, a, tail);
      assert(g.next().value === 6, "generator caller first");
      assert(g.next().value === 6, "generator caller return");
      const ag = asyncGeneratorCaller(sum, a, tail);
      assert((await ag.next()).value === 6, "async generator caller");
      assert((await ag.next()).value === 6, "async generator caller return");
      const promise = core(asyncTarget, a, ...tail);
      std.gc();
      assert((await promise) === 6, "async target argument lifetime");
      const target = core(generatorTarget, a, ...tail);
      std.gc();
      assert(target.next().value === 6, "generator target");
      assert(target.next().value === a, "generator target identity");
      const at = core(asyncGeneratorTarget, a, ...tail);
      std.gc();
      assert((await at.next()).value === 6, "async generator target");
      assert((await at.next()).value === a, "async generator target identity");
    }
    let active;
    function* reentrant(f, a, tail) {
      yield f(a, ...tail);
    }
    active = reentrant(
      (a, b, c) => {
        let threw = false;
        try {
          active.next();
        } catch (e) {
          threw = e instanceof TypeError;
        }
        assert(threw, "running generator");
        std.gc();
        return a + b + c;
      },
      1,
      [2, 3],
    );
    assert(active.next().value === 6, "generator reentry result");
    const sentinel = {};
    async function errorCaller(f, a, tail) {
      try {
        return f(a, ...tail);
      } finally {
        std.gc();
      }
    }
    try {
      await errorCaller(
        () => {
          throw sentinel;
        },
        1,
        [2, 3],
      );
      assert(false, "async throw absent");
    } catch (e) {
      assert(e === sentinel, "async same exception");
    }
    print("CORE_SPREAD_ASYNC_OK " + checks);
  })();
}
print("FRAME_CORE_SPREAD_OK 3498");
