(function () {
  const print =
    typeof globalThis.print === "function" ? globalThis.print : (...args) => console.log(...args);
  const trace = [];
  function check(v, message) {
    if (!v) throw new Error(message);
  }
  function equal(a, b, message) {
    check(JSON.stringify(a) === JSON.stringify(b), message + ": " + JSON.stringify(a));
  }
  async function identity(v) {
    return await v;
  }
  async function rejected(p) {
    try {
      await p;
      return "bad";
    } catch (e) {
      return e;
    }
  }
  async function main() {
    const values = [
      undefined,
      null,
      true,
      false,
      -0,
      NaN,
      12,
      2.5,
      "hello",
      12n,
      Symbol.for("await"),
    ];
    for (const v of values) check(Object.is(await identity(v), v), "primitive");
    for (let i = 0; i < 96; i++) {
      const plain = { i };
      check((await identity(plain)) === plain, "plain identity");
      check((await identity(Promise.resolve(i))) === i, "fulfilled");
      let resolve, reject;
      const pending = new Promise((a, b) => {
        resolve = a;
        reject = b;
      });
      const observer = identity(pending);
      pending.then((x) => trace.push("then" + x));
      resolve(i);
      check((await observer) === i, "pending fulfilled");
      const failed = new Promise((a, b) => {
        reject = b;
      });
      const observer2 = rejected(failed);
      reject(plain);
      check((await observer2) === plain, "pending rejected");
      check((await rejected(Promise.reject(plain))) === plain, "ready rejected");
      if (typeof gc === "function") gc();
    }
    let gets = 0,
      calls = 0;
    const thenable = {
      get then() {
        gets++;
        return (yes) => {
          calls++;
          yes(42);
        };
      },
    };
    check((await identity(thenable)) === 42 && gets === 1 && calls === 1, "thenable");
    const marker = { error: 1 };
    check(
      (await rejected({
        get then() {
          throw marker;
        },
      })) === marker,
      "throwing then",
    );
    const inherited = Object.create({ then: undefined });
    check((await identity(inherited)) === inherited, "inherited then undefined");
    const proxyLog = [];
    const proxy = new Proxy(
      {},
      {
        get(t, k) {
          proxyLog.push(String(k));
          return undefined;
        },
      },
    );
    check((await identity(proxy)) === proxy, "proxy identity");
    equal(proxyLog, ["then", "then"], "proxy then lookups for await and return assimilation");
    const p = Promise.resolve(9);
    let constructors = 0;
    Object.defineProperty(p, "constructor", {
      get() {
        constructors++;
        return Promise;
      },
    });
    check((await identity(p)) === 9 && constructors === 1, "promise constructor lookup");
    const order = [];
    let release;
    const shared = new Promise((r) => (release = r));
    async function wait(n) {
      const x = await shared;
      order.push(n);
      return x + n;
    }
    const a = wait(1),
      b = wait(2);
    shared.then(() => order.push(3));
    release(10);
    equal(await Promise.all([a, b]), [11, 12], "shared pending result");
    equal(order, [1, 2, 3], "FIFO");
    async function* gen() {
      yield await 1;
      yield await Promise.resolve(2);
      yield await new Promise((r) => r(3));
    }
    const generated = [];
    for await (const v of gen()) generated.push(v);
    equal(generated, [1, 2, 3], "async generator interop");

    let self;
    async function returnSelf() {
      await 0;
      return self;
    }
    self = returnSelf();
    try {
      await self;
      throw marker;
    } catch (e) {
      check(e instanceof TypeError, "output self resolution");
    }
    let returns = 0;
    const resolution = {
      then(resolve) {
        returns++;
        resolve(77);
      },
    };
    async function returnThenable() {
      return resolution;
    }
    check((await returnThenable()) === 77 && returns === 1, "return thenable");
    async function throwBeforeAwait() {
      throw marker;
    }
    check((await rejected(throwBeforeAwait())) === marker, "immediate throw");
    async function returnBadThen() {
      return {
        get then() {
          throw marker;
        },
      };
    }
    check((await rejected(returnBadThen())) === marker, "return throwing then getter");
    const OriginalPromise = Promise;
    globalThis.Promise = new Proxy(OriginalPromise, {
      construct() {
        throw marker;
      },
    });
    async function intrinsicResult() {
      return 13;
    }
    const intrinsic = intrinsicResult();
    globalThis.Promise = OriginalPromise;
    check(
      Object.getPrototypeOf(intrinsic) === OriginalPromise.prototype && (await intrinsic) === 13,
      "intrinsic Promise",
    );
    trace.push("ok");
    check(trace.length === 97, "trace size");
    print(JSON.stringify({ passed: true, iterations: 96, trace: trace.length, fifo: order }));
  }
  main().catch((e) => {
    print("FAIL", (e && e.stack) || e);
    if (globalThis.std) std.exit(1);
    else process.exitCode = 1;
  });
})();
