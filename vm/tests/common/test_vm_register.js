/* Exercise assembly commits and pre-mutation C exits through the public API. */
function registerIdentity(x) {
  return x;
}
function registerAdd(x, y) {
  return x + y;
}
function registerTail(x) {
  return registerIdentity(x);
}
function registerArity(x, y, z) {
  return x + (y === undefined ? 3 : y) + (z === undefined ? 5 : z);
}
function registerObject(x) {
  let y = registerIdentity(x);
  frameGC();
  return y;
}
function registerBinding(x) {
  return x + 1;
}
let registerLexical = 7;
let registerGetterHits = 0;
const registerPropertyGetter = {
  get value() {
    return 31;
  },
};
Object.defineProperty(globalThis, "registerGetterValue", {
  configurable: true,
  get() {
    registerGetterHits++;
    return 19;
  },
});
globalThis.frameCases = {
  integers(n) {
    let s = 0;
    for (let i = 0; i < n; i++) s = registerTail((s + i * 3) ^ 17) | 0;
    return s;
  },
  edges(n) {
    if (registerAdd(2147483647, 1) !== 2147483648) throw "positive overflow";
    if (registerAdd(-2147483648, -1) !== -2147483649) throw "negative overflow";
    if (registerAdd("a", 2) !== "a2") throw "coercion";
    let x = 0,
      y = -2147483648;
    if (!Object.is(registerIdentity(-x), -0)) throw "negative zero";
    if (!Object.is(x * -1, -0)) throw "multiply negative zero";
    if (registerIdentity(y >>> 0) !== 2147483648) throw "unsigned shift";
    if (registerIdentity(1.25) + 2 !== 3.25) throw "float";
    for (let i = 0; i < n; i++) {
      x = registerAdd(x, 1);
      if (x < 1 || !(x >= 1)) throw "branch";
    }
    return x;
  },
  objects(n) {
    let o = { answer: 42 },
      sum = 0;
    o.self = o;
    for (let i = 0; i < n; i++) {
      let returned = registerObject(o);
      if (returned !== o || returned.self !== returned) throw "ownership";
      sum += returned.answer;
    }
    return sum;
  },
  arity(n) {
    let s = 0;
    for (let i = 0; i < n; i++) s += registerArity(i);
    return s;
  },
  reentry(n) {
    let s = 0;
    for (let i = 0; i < n; i++) s += frameReenter(registerTail, i);
    return s;
  },
  bindings(n) {
    let sum = 0;
    for (let i = 0; i < n; i++) {
      const object = { a: 11, f: registerBinding };
      sum += object.a + object.f(i) + registerLexical;
    }
    if (registerGetterValue !== 19 || registerGetterHits < 1) throw "global getter";
    globalThis.registerTemporary = 23;
    if (registerTemporary !== 23) throw "global data";
    delete globalThis.registerTemporary;
    if (typeof registerTemporary !== "undefined") throw "global deletion";
    if (Object.create({ inherited: 29 }).inherited !== 29) throw "prototype fallback";
    if (registerPropertyGetter.value !== 31) throw "property getter";
    return sum;
  },
};
