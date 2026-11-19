(function () {
  const print =
    typeof globalThis.print === "function" ? globalThis.print : (...args) => console.log(...args);
  function check(v, s) {
    if (!v) throw new Error(s);
  }
  function same(a, b, s) {
    check(JSON.stringify(a) === JSON.stringify(b), s + ": " + JSON.stringify(a));
  }
  async function main() {
    let calls = 0;
    async function* values() {
      yield 1;
      yield await Promise.resolve(2);
      yield {
        then(r) {
          calls++;
          r(3);
        },
      };
      return 4;
    }
    const g = values();
    const queued = [g.next(), g.next(), g.next(), g.next(), g.next()];
    same(
      await Promise.all(queued),
      [
        { value: 1, done: false },
        { value: 2, done: false },
        { value: 3, done: false },
        { value: 4, done: true },
        { done: true },
      ],
      "queued next",
    );
    check(calls === 1, "thenable value");
    const marker = { error: 42 };
    async function* failures() {
      yield 7;
      throw marker;
    }
    const bad = failures();
    same(await bad.next(), { value: 7, done: false }, "first yield");
    try {
      await bad.next();
      throw Error("not rejected");
    } catch (e) {
      check(e === marker, "throw identity");
    }
    same(await bad.next(), { done: true }, "closed next");
    let finalize = 0;
    async function* close() {
      try {
        yield 1;
      } finally {
        finalize++;
        yield 8;
      }
    }
    const c = close();
    await c.next();
    same(await c.return(9), { value: 8, done: false }, "finally yield");
    same(await c.next(), { value: 9, done: true }, "return completion");
    check(finalize === 1, "finally once");
    const closed = close();
    same(await closed.return(Promise.resolve(11)), { value: 11, done: true }, "unstarted return");
    try {
      await closed.throw(marker);
      throw Error("not thrown");
    } catch (e) {
      check(e === marker, "closed throw");
    }
    const proto = Object.getPrototypeOf(Object.getPrototypeOf(values()));
    for (const method of ["next", "return", "throw"]) {
      const p = proto[method].call({});
      check(p instanceof Promise, "invalid receiver Promise");
      try {
        await p;
        throw marker;
      } catch (e) {
        check(e instanceof TypeError, "invalid receiver rejection");
      }
    }
    // Iterator results are ordinary objects: their inherited `then` getter
    // and thrown value still participate in output Promise resolution.
    const poison = values();
    const old = Object.getOwnPropertyDescriptor(Object.prototype, "then");
    let gets = 0;
    Object.defineProperty(Object.prototype, "then", {
      configurable: true,
      get() {
        gets++;
        throw marker;
      },
    });
    let thrown;
    try {
      await poison.next();
    } catch (e) {
      thrown = e;
    }
    if (old) Object.defineProperty(Object.prototype, "then", old);
    else delete Object.prototype.then;
    check(thrown === marker && gets >= 1, "output iterator-result then getter");
    // A thenable on the iterator result must retain asynchronous adoption.
    const adopted = values();
    Object.defineProperty(Object.prototype, "then", {
      configurable: true,
      value: function (resolve) {
        if (Object.prototype.hasOwnProperty.call(this, "done")) {
          delete Object.prototype.then;
          resolve(123);
        } else {
          delete Object.prototype.then;
          resolve(this);
        }
      },
    });
    const adoptedValue = await adopted.next();
    delete Object.prototype.then;
    check(adoptedValue === 123, "output thenable adoption");
    const nested = [];
    async function* inner(n) {
      for (let i = 0; i < n; i++) yield i;
    }
    async function* outer(n) {
      for await (const x of inner(n)) yield x + 1;
    }
    for await (const x of outer(96)) nested.push(x);
    check(nested.length === 96 && nested[95] === 96, "nested generators");
    print(JSON.stringify({ passed: true, queued: 5, thenableCalls: calls, nested: 96 }));
  }
  main().catch((e) => {
    print("FAIL", (e && e.stack) || e);
    if (globalThis.std) std.exit(1);
    else process.exitCode = 1;
  });
})();
