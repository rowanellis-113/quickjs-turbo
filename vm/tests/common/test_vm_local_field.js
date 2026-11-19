/* Borrowed live-slot property reads and original observable fallbacks. */
import * as std from "qjs:std";
let checks = 0;
function eq(a, b) {
  checks++;
  if (!Object.is(a, b)) throw Error(checks + ": " + a + " != " + b);
}
function local(o) {
  let a = o;
  return a.x;
}
function argument(o) {
  return o.x;
}
function closure(o) {
  return function () {
    return o.x;
  };
}
function checked(o) {
  let r;
  {
    let a = o;
    r = a.x;
  }
  return r;
}
function nested(o) {
  let a = o;
  return a.x.x;
}
function writeRead(o, v) {
  let a = o;
  a.x = v;
  return a.x;
}
let a = { x: 7 },
  b = { x: 9 },
  c = Object.create({ x: 11 }),
  empty = {};
for (let n = 0; n < 1000; n++) {
  eq(local(a), 7);
  eq(argument(b), 9);
  eq(checked(c), 11);
  eq(closure(a)(), 7);
  eq(local(empty), undefined);
}
for (let n = 0; n < 32; n++) {
  const o = {};
  for (let i = 0; i < n; i++) o["k" + i] = i;
  o.x = n;
  eq(local(o), n);
  eq(argument(o), n);
}
eq(writeRead(a, 13), 13);
eq(local(a), 13);
delete a.x;
eq(local(a), undefined);
a.x = 17;
eq(local(a), 17);
let proto = Object.getPrototypeOf(c);
proto.x = 19;
eq(local(c), 19);
delete proto.x;
eq(local(c), undefined);
Object.setPrototypeOf(c, { x: 23 });
eq(local(c), 23);
let seen = 0;
let getter = {
  get x() {
    seen++;
    eq(local(b), 9);
    std.gc();
    return 29;
  },
};
for (let n = 0; n < 16; n++) eq(local(getter), 29);
eq(seen, 16);
let proxy = new Proxy(
  { x: 31 },
  {
    get(t, k, r) {
      seen++;
      return Reflect.get(t, k, r);
    },
  },
);
for (let n = 0; n < 16; n++) eq(argument(proxy), 31);
eq(seen, 32);
let xs = [1, 2, 3];
xs.x = 37;
eq(local(xs), 37);
String.prototype.x = 41;
eq(local("a"), 41);
delete String.prototype.x;
eq(local(1), undefined);
eq(local(true), undefined);
eq(local(Symbol("a")), undefined);
for (const v of [null, undefined]) {
  let threw = false;
  try {
    local(v);
  } catch (e) {
    threw = e instanceof TypeError;
  }
  eq(threw, true);
}
let throws = {
  get x() {
    throw 43;
  },
};
for (let n = 0; n < 4; n++) {
  let v;
  try {
    local(throws);
  } catch (e) {
    v = e;
  }
  eq(v, 43);
}
let self = {};
self.x = self;
eq(local(self), self);
eq(nested(self), self);
let replace = { x: { x: 47 } };
eq(nested(replace), 47);
replace.x = { x: 53 };
eq(nested(replace), 53);
Object.defineProperty(replace, "x", {
  get() {
    return { x: 59 };
  },
});
eq(nested(replace), 59);
function tdz() {
  return a.x;
  let a = { x: 61 };
}
let tdzThrown = false;
try {
  tdz();
} catch (e) {
  tdzThrown = e instanceof ReferenceError;
}
eq(tdzThrown, true);
let capture = { x: 67 };
const get = closure(capture);
eq(get(), 67);
capture.x = 71;
eq(get(), 71);
std.gc();
eq(get(), 71);
eq(local(self), self);
print("LOCAL_FIELD_SEMANTICS_OK " + checks);
