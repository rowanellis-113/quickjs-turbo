"use strict";
let checks = 0;
function check(value, message) {
  checks++;
  if (!value) throw Error(message);
}
class Point {
  constructor(x, y) {
    this.x = x;
    this.y = y;
  }
}
class Missing {
  constructor(x, y, z) {
    this.x = x;
    this.y = y;
    this.z = z;
  }
}
class Mutable {
  constructor(x) {
    x++;
    this.x = x;
  }
}
class StringResult {
  constructor(x) {
    this.x = x;
    return "ignored-" + x;
  }
}
class SymbolResult {
  constructor(x) {
    this.x = x;
    return Symbol(x);
  }
}
class BigResult {
  constructor(x) {
    this.x = x;
    return 123456789012345678901234567890n;
  }
}
class ObjectResult {
  constructor(x) {
    this.x = -1;
    return { x: x };
  }
}
class FunctionResult {
  constructor(x) {
    return function () {
      return x;
    };
  }
}
class Captured {
  constructor(x) {
    this.read = () => x;
    x++;
  }
}
class Inner {
  constructor(x) {
    this.x = x;
  }
}
class Nested {
  constructor(x) {
    this.inner = new Inner(x);
    this.x = x + 1;
  }
}
class Field {
  value = 11;
  other = this.value + 1;
  constructor(x) {
    this.x = x;
  }
}
class Throwing {
  constructor(x) {
    this.x = x;
    throw Error("ctor-" + x);
  }
}
class Catching {
  constructor(x) {
    try {
      new Throwing(x);
    } catch (e) {
      this.message = e.message;
    }
    this.x = x;
  }
}
class Collect {
  constructor(x) {
    this.x = x;
    gc();
    this.y = this.x + 1;
  }
}
class Iterating {
  constructor(x) {
    this.sum = 0;
    for (const value of [x, x + 1]) this.sum += value;
  }
}
class Target {
  constructor() {
    this.target = new.target;
  }
}
class Derived extends Point {
  constructor(x, y) {
    super(x, y);
    this.z = 3;
  }
}
class Private {
  #x = 9;
  constructor(x) {
    this.x = x;
  }
  read() {
    return this.#x;
  }
}
function Plain(x) {
  this.x = x;
}
function ChildFactory(x) {
  return new Nested(x);
}
function PlainResult(x) {
  this.x = x;
  return 3;
}
function Other() {}
Other.prototype = { other: 17 };
const Bound = Point.bind(null, 23);
const ProxyPoint = new Proxy(Point, {
  construct(t, args, nt) {
    return Reflect.construct(t, args, nt);
  },
});
for (let i = 0; i < 100; i++) {
  let o = new Point(i, i + 1);
  check(o.x === i && o.y === i + 1, "point");
  o = new Missing(i);
  check(o.x === i && o.y === undefined && o.z === undefined, "arity");
  check(new Mutable(i).x === i + 1, "writable argument");
  check(new StringResult(i).x === i, "string return");
  check(new SymbolResult(i).x === i, "symbol return");
  check(new BigResult(i).x === i, "big return");
  check(new ObjectResult(i).x === i, "object return");
  check(new FunctionResult(i)() === i, "function return");
  check(new Captured(i).read() === i + 1, "captured writable argument");
  o = ChildFactory(i);
  check(o.inner.x === i && o.x === i + 1, "nested");
  o = new Field(i);
  check(o.value === 11 && o.other === 12 && o.x === i, "class fields");
  o = new Catching(i);
  check(o.message === "ctor-" + i && o.x === i, "caught nested constructor");
  let thrown = false;
  try {
    new Throwing(i);
  } catch (e) {
    thrown = e.message === "ctor-" + i;
  }
  check(thrown, "throw to parent");
  o = new Collect(i);
  check(o.x === i && o.y === i + 1, "GC");
  check(new Iterating(i).sum === 2 * i + 1, "iterator slow path");
  check(new Target().target === Target, "new.target fallback");
  o = new Derived(i, i + 1);
  check(o.x === i && o.y === i + 1 && o.z === 3, "derived fallback");
  check(new Private(i).read() === 9, "private fields fallback");
  check(new Plain(i).x === i && new PlainResult(i).x === i, "plain");
  o = Reflect.construct(Point, [i, i + 1], Other);
  check(o.x === i && Object.getPrototypeOf(o) === Other.prototype, "newTarget fallback");
  o = new Bound(i);
  check(o.x === 23 && o.y === i, "bound");
  check(new ProxyPoint(i, i + 1).x === i, "proxy");
  for (const invoke of [
    () => Point(i),
    () => Point.call({}, i),
    () => Reflect.apply(Point, {}, [i]),
  ]) {
    let failed = false;
    try {
      invoke();
    } catch (e) {
      failed = e instanceof TypeError;
    }
    check(failed, "class call rejection");
  }
}
function deep(n) {
  return n ? new Recursive(n - 1) : 1;
}
class Recursive {
  constructor(n) {
    this.value = deep(n);
  }
}
let tree = new Recursive(24);
for (let i = 0; i < 24; i++) tree = tree.value;
check(tree.value === 1, "deep segment chain");
let overflow = false;
try {
  new Recursive(10000);
} catch (e) {
  overflow = e instanceof RangeError;
}
check(overflow, "constructor stack overflow");
check(new Point(7, 8).x === 7, "post-overflow recovery");
gc();
print("CONSTRUCT_CONTINUATION_OK checks=" + checks);
