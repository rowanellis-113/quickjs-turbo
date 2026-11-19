let checks = 0;
function check(v) {
  if (!v) throw Error("C_INVOKE " + checks);
  ++checks;
}
function get(m, k) {
  return m.get(k);
}
function set(m, k, v) {
  return m.set(k, v);
}
function has(m, k) {
  return m.has(k);
}
function del(m, k) {
  return m.delete(k);
}
function code(s, n) {
  return s.charCodeAt(n);
}
function slice(s, a, b) {
  return s.slice(a, b);
}
function push(a, v) {
  return a.push(v);
}
function mapped(a, f) {
  return a.map(f);
}
function invoke(o, x) {
  return o.f(x);
}
function tail(m, k) {
  return m.get(k);
}
function layer(m, k) {
  return tail(m, k);
}
let m = new Map(),
  key = { key: 1 },
  value = { value: 2 };
for (let i = 0; i < 120; ++i) {
  check(set(m, key, value) === m);
  check(get(m, key) === value && layer(m, key) === value);
  check(has(m, key));
  check(del(m, key) && !has(m, key));
  check(code("ab\u4e2d", 2) === 0x4e2d);
  check(slice("abcdef", 1, 4) === "bcd");
  let a = [];
  check(push(a, value) === 1 && a[0] === value);
  check(mapped([i, i + 1], (x) => x + 3).join(",") === i + 3 + "," + (i + 4));
}
// Exceptions after a direct C call, nested C->JS calls, and subsequent recovery.
for (let i = 0; i < 30; ++i) {
  let caught = false;
  try {
    get({ get: Map.prototype.get }, key);
  } catch (e) {
    caught = e instanceof TypeError;
  }
  check(caught);
  caught = false;
  try {
    mapped([1, 2], (x) => {
      if (x === 2) throw value;
      return x;
    });
  } catch (e) {
    caught = e === value;
  }
  check(caught);
  check(set(m, i, value) === m && get(m, i) === value);
  check(
    invoke(
      {
        f: String.prototype.charCodeAt,
        toString() {
          return "abc";
        },
      },
      1,
    ) === 98,
  );
}
// A live callee is reclassified on every call; getters and proxies keep semantics.
let o = { f: Math.abs };
for (let i = 0; i < 100; ++i) {
  o.f = Math.abs;
  check(invoke(o, -i) === i);
  o.f = (x) => x + 7;
  check(invoke(o, i) === i + 7);
  o.f = new Proxy(Math.abs, {
    apply(t, that, args) {
      return Reflect.apply(t, that, args) + 1;
    },
  });
  check(invoke(o, -i) === i + 1);
}
let hits = 0;
Object.defineProperty(o, "f", {
  get() {
    ++hits;
    return Math.abs;
  },
});
check(invoke(o, -17) === 17 && hits === 1);
let oldLength = Object.getOwnPropertyDescriptor(Map.prototype.get, "length");
Object.defineProperty(Map.prototype.get, "length", { value: 100, configurable: true });
check(get(m, 29) === value);
Object.defineProperty(Map.prototype.get, "length", oldLength);
// Missing actuals and other signatures deliberately retain the inherited path.
check(Number.isNaN(code("abc")) === false && code("abc") === 97);
check(get(m) === undefined);
let wm = new WeakMap();
check(set(wm, key, value) === wm && get(wm, key) === value);
print("C_INVOKE_SEMANTICS_PASS", checks);
