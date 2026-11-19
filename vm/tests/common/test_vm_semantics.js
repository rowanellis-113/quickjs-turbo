/* Each case is called directly through JS_Call, not through a CLI wrapper. */
function check(actual, expected) {
  if (actual !== expected) throw "mismatch: " + actual + " != " + expected;
}
function valueLeaf(a, b) {
  a += 1;
  return a + (b === undefined ? 3 : b);
}
function valueMiddle(a) {
  return valueLeaf(valueLeaf(a));
}
function integerLeaf(a) {
  return a + 1;
}
function stringLeaf(a) {
  return a + "x";
}
function argumentLeaf(a, b) {
  return arguments.length + a + (b === undefined ? 0 : b);
}
function strictThis() {
  "use strict";
  return this;
}
function looseThis() {
  return this;
}
function deepFrame(n) {
  return n ? deepFrame(n - 1) + 1 : 0;
}
function throwingFrame(a) {
  if (a) throw a;
  return 1;
}
function outerThrow(a) {
  return throwingFrame(a);
}
function closedProducer(x) {
  return (y) => x + y;
}
const semanticClosed = closedProducer(7);
let polyTarget = integerLeaf;
const conversion = {
  valueOf() {
    frameGC();
    return 3;
  },
};
const getterObject = {
  get value() {
    frameGC();
    return integerLeaf(41);
  },
};
let getterHits = 0;
const throwingGetter = {
  get value() {
    getterHits++;
    throw "getter-error";
  },
};
const frameCases = {
  values(n) {
    check(valueMiddle(1), 9);
    check(valueLeaf("a"), "a13");
    check(1 / valueLeaf(-4, -0), -1 / 3);
    check(1 / (-0 * 3), -Infinity);
    check(12n ** 2n + 3n, 147n);
    check((1 << 31) >>> 0, 2147483648);
    check(semanticClosed(5), 12);
    check(argumentLeaf(3), 4);
    check(argumentLeaf(3, 4, 5), 10);
    check(strictThis(), undefined);
    check(looseThis(), globalThis);
    check(deepFrame(96), 96);
    return 42;
  },
  gc(n) {
    let s = 0;
    for (let i = 0; i < 1000; i++) {
      check(frameReenter(integerLeaf, i), i + 1);
      check(valueLeaf(conversion), 7);
      check(getterObject.value, 42);
      s += semanticClosed(i);
    }
    check(s, 506500);
    return 42;
  },
  polymorphic(n) {
    for (let i = 0; i < 1000; i++) {
      polyTarget = i & 1 ? integerLeaf : stringLeaf;
      let value = polyTarget(i);
      check(value, i & 1 ? i + 1 : i + "x");
    }
    return 42;
  },
  exception(n) {
    let e;
    try {
      outerThrow("test-error");
    } catch (x) {
      e = x;
    }
    check(e, "test-error");
    try {
      integerLeaf(1n);
    } catch (x) {
      e = x;
    }
    check(e instanceof TypeError, true);
    getterHits = 0;
    try {
      throwingGetter.value;
    } catch (x) {
      e = x;
    }
    check(e, "getter-error");
    check(getterHits, 1);
    check(integerLeaf(41), 42);
    return 42;
  },
};
globalThis.frameCases = frameCases;
