let checks = 0;
function eq(a, b) {
  checks++;
  if (!Object.is(a, b)) throw Error(checks + ": " + String(a) + " != " + String(b));
}
function read(o) {
  return o.value;
}
function write(o, v) {
  o.value = v;
}
function absent(o) {
  return o.missing;
}
function invoke(o) {
  return o.method();
}
function build(x) {
  this.a = x;
  this.b = x + 1;
  this.c = "c" + x;
  this.d = { x };
  this.e = x + 4;
  this.f = x + 5;
}
let objects = [];
for (let i = 0; i < 6; ++i) {
  let o = {};
  for (let j = 0; j < i; ++j) o["pad" + j] = j;
  o.value = i;
  objects.push(o);
}
for (let i = 0; i < 5000; ++i) {
  let o = objects[i % 4];
  write(o, i & 1 ? { i } : "s" + i);
  eq(read(o), o.value);
  let b = new build(i);
  eq(b.a, i);
  eq(b.b, i + 1);
  eq(b.c, "c" + i);
  eq(b.d.x, i);
  eq(b.e, i + 4);
  eq(b.f, i + 5);
}
for (let i = 0; i < 1000; ++i) eq(read(objects[i % 6]), objects[i % 6].value);
let grand = {
    value: 21,
    method() {
      return this.own;
    },
  },
  proto = Object.create(grand),
  obj = Object.create(proto);
obj.own = 44;
for (let i = 0; i < 1000; ++i) {
  eq(read(obj), 21);
  eq(absent(obj), undefined);
  eq(invoke(obj), 44);
}
grand.value = "changed";
eq(read(obj), "changed");
proto.value = 31;
eq(read(obj), 31);
delete proto.value;
eq(read(obj), "changed");
Object.defineProperty(proto, "value", {
  get() {
    gc();
    return this.own + 1;
  },
  configurable: true,
});
eq(read(obj), 45);
delete proto.value;
eq(read(obj), "changed");
grand.missing = 7;
eq(absent(obj), 7);
delete grand.missing;
eq(absent(obj), undefined);
Object.setPrototypeOf(proto, { value: 99 });
eq(read(obj), 99);
Object.defineProperty(proto, "value", { value: 100, writable: false, configurable: true });
let threw = false;
try {
  write(obj, 1);
} catch (e) {
  threw = e instanceof TypeError;
}
eq(threw, true);
eq(read(obj), 100);
delete proto.value;
let setters = 0;
Object.defineProperty(proto, "value", {
  set(v) {
    setters += v;
    gc();
  },
  get() {
    return 8;
  },
  configurable: true,
});
write(obj, 2);
write(obj, 3);
eq(setters, 5);
eq(read(obj), 8);
let seen = [];
let proxy = new Proxy(Object.create(null), {
  get(t, k, r) {
    seen.push("g" + String(k));
    return 123;
  },
  set(t, k, v, r) {
    seen.push("s" + String(k));
    return true;
  },
});
for (let i = 0; i < 100; ++i) {
  eq(read(proxy), 123);
  write(proxy, i);
  eq(absent(proxy), 123);
}
eq(seen.length, 300);
let nullProto = Object.create(null);
nullProto.value = 7;
for (let i = 0; i < 100; ++i) {
  eq(read(nullProto), 7);
  eq(absent(nullProto), undefined);
  eq(absent(proxy), 123);
}
let frozen = Object.freeze({ value: 8 });
threw = false;
try {
  write(frozen, 9);
} catch (e) {
  threw = e instanceof TypeError;
}
eq(threw, true);
eq(read(frozen), 8);
let sealed = Object.preventExtensions({});
threw = false;
try {
  write(sealed, 9);
} catch (e) {
  threw = e instanceof TypeError;
}
eq(threw, true);
eq(read(sealed), undefined);
function transition(o, x) {
  o.value = x;
}
for (let i = 0; i < 1000; ++i) {
  let o = Object.create(grand);
  transition(o, i);
  eq(o.value, i);
}
Object.defineProperty(grand, "value", {
  set(x) {
    setters += x;
  },
  get() {
    return 81;
  },
  configurable: true,
});
let changed = Object.create(grand);
transition(changed, 4);
eq(setters, 9);
eq(changed.value, 81);
eq(Object.hasOwn(changed, "value"), false);
delete grand.value;
Object.defineProperty(grand, "value", { value: 4, writable: false, configurable: true });
threw = false;
try {
  transition(Object.create(grand), 5);
} catch (e) {
  threw = e instanceof TypeError;
}
eq(threw, true);
delete grand.value;
for (let i = 0; i < 1000; ++i) {
  let p = {},
    a = Object.create(p);
  eq(absent(a), undefined);
  p.missing = i;
  eq(absent(a), i);
  delete p.missing;
}
let a = [];
for (let i = 0; i < 1000; ++i) {
  a.value = i;
  eq(read(a), i);
}
Object.defineProperty(a, "length", { writable: false });
function length(o) {
  return o.length;
}
for (let i = 0; i < 100; ++i) eq(length(a), 0);
let ta = new Uint8Array(4);
ta.value = 6;
for (let i = 0; i < 100; ++i) {
  eq(read(ta), 6);
  eq(length(ta), 4);
}
function ownGone(o) {
  return o.value;
}
for (let i = 0; i < 1000; ++i) {
  let o = { value: i };
  eq(ownGone(o), i);
  delete o.value;
  eq(ownGone(o), undefined);
  o.value = i + 2;
  eq(ownGone(o), i + 2);
  for (let j = 0; j < 35; ++j) o["x" + j] = j;
  for (let j = 0; j < 25; ++j) delete o["x" + j];
  eq(ownGone(o), i + 2);
  if (!(i % 50)) gc();
}
let before = Object.prototype.value;
try {
  for (let i = 0; i < 200; ++i) {
    let o = {};
    transition(o, i);
    eq(o.value, i);
  }
  Object.defineProperty(Object.prototype, "value", {
    set(x) {
      setters += x;
    },
    configurable: true,
  });
  let o = {};
  transition(o, 8);
  eq(Object.hasOwn(o, "value"), false);
  eq(setters, 17);
} finally {
  delete Object.prototype.value;
  if (before !== undefined) Object.prototype.value = before;
}
for (let i = 0; i < 1000; ++i) {
  // Bytecode -> cached shape -> prototype -> function/bytecode cycle.
  let p = {},
    o = Object.create(p),
    f = Function("o", "return o.value");
  p.f = f;
  p.value = i;
  eq(f(o), i);
  if (!(i % 20)) gc();
}
gc();
print("PROPERTY_IC_SMOKE", checks, "PASS");
