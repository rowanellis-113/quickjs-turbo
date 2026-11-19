"use strict";
let checks = 0,
  digest = 2166136261 >>> 0;
function check(ok, message) {
  checks++;
  if (!ok) throw Error(message);
}
function mix(s) {
  for (let i = 0; i < s.length; i++) digest = Math.imul(digest ^ s.charCodeAt(i), 16777619) >>> 0;
}
let seed = 123456789;
function random() {
  seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0;
  return seed;
}
function cmp(a, b) {
  return a < b ? -1 : a > b ? 1 : 0;
}
function reference(values) {
  if (values.length < 2) return values.slice();
  const mid = values.length >> 1,
    a = reference(values.slice(0, mid)),
    b = reference(values.slice(mid));
  let out = [],
    i = 0,
    j = 0;
  while (i < a.length && j < b.length) out.push(cmp(a[i], b[j]) <= 0 ? a[i++] : b[j++]);
  return out.concat(a.slice(i), b.slice(j));
}
function verify(input, name) {
  const want = reference(input),
    got = input.slice();
  check(got.sort() === got, name + " identity");
  check(got.length === want.length, name + " length");
  for (let i = 0; i < want.length; i++) check(got[i] === want[i], name + " value " + i);
  mix(name + ":" + got.length + ":" + got.join("|"));
}
for (const n of [0, 1, 2, 6, 31, 32, 63, 64, 65, 127, 1024, 4096]) {
  let a = [];
  for (let i = 0; i < n; i++) {
    let s = "",
      len = random() % 17;
    for (let j = 0; j < len; j++) s += String.fromCharCode(random() % 256);
    a.push(s);
  }
  verify(a, "random8-" + n);
  verify(a.slice().reverse(), "reverse8-" + n);
  verify(
    a.map((s, i) => "common-prefix-".repeat(12) + (i % 13) + "\0" + s),
    "deep-prefix-" + n,
  );
  verify(
    a.map((s, i) => String(i % 11)),
    "duplicates-" + n,
  );
  verify(
    a.map((s, i) => (i % 2 ? "\0" + s : "")),
    "end-nul-" + n,
  );
  verify(
    a.map((s) => "\u0100" + s),
    "wide-" + n,
  );
}
verify(
  Array.from({ length: 65536 }, (_, i) => String(65535 - i).padStart(6, "0")),
  "large-reverse",
);
verify(
  Array.from({ length: 4096 }, (_, i) => "x".repeat(700) + String(i % 97)),
  "rope-fallback",
);
let a = ["d", undefined, , "b", undefined, , "a"];
check(a.sort() === a, "holes identity");
check(a.length === 7 && a[0] === "a" && a[1] === "b" && a[2] === "d", "holes values");
check(a[3] === undefined && a[4] === undefined && 3 in a && 4 in a, "undefined present");
check(!(5 in a) && !(6 in a), "holes deleted");
let calls = 0,
  objects = Array.from({ length: 128 }, (_, i) => ({
    id: i,
    toString() {
      calls++;
      return String(i % 7);
    },
  }));
let sorted = objects.slice().sort();
check(calls > 0, "objects converted");
for (let i = 1; i < sorted.length; i++)
  check(cmp(String(sorted[i - 1].id % 7), String(sorted[i].id % 7)) <= 0, "object order");
for (let key = 0; key < 7; key++) {
  const ids = sorted.filter((x) => x.id % 7 === key).map((x) => x.id);
  for (let i = 1; i < ids.length; i++) check(ids[i - 1] < ids[i], "object stable");
}
mix("object-conversions:" + calls);
let customCalls = 0;
a = Array.from({ length: 128 }, (_, i) => String(i));
a.sort((a, b) => {
  customCalls++;
  return +b - +a;
});
check(customCalls > 0 && a[0] === "127" && a[127] === "0", "custom comparator");
let threw = false;
try {
  Array.from({ length: 128 }, (_, i) => (i === 70 ? Symbol("s") : String(i))).sort();
} catch (e) {
  threw = e instanceof TypeError;
}
check(threw, "symbol conversion error");
threw = false;
try {
  Array.from({ length: 128 }, (_, i) => String(i)).sort(null);
} catch (e) {
  threw = e instanceof TypeError;
}
check(threw, "invalid comparator");
const events = [];
const target = { length: 128 };
for (let i = 0; i < 128; i++) target[i] = String(127 - i).padStart(4, "0");
const proxy = new Proxy(target, {
  get(t, k, r) {
    events.push("g" + String(k));
    return Reflect.get(t, k, r);
  },
  has(t, k) {
    events.push("h" + String(k));
    return Reflect.has(t, k);
  },
  set(t, k, v, r) {
    events.push("s" + String(k));
    return Reflect.set(t, k, v, r);
  },
  deleteProperty(t, k) {
    events.push("d" + String(k));
    return Reflect.deleteProperty(t, k);
  },
});
Array.prototype.sort.call(proxy);
for (let i = 0; i < 128; i++) check(target[i] === String(i).padStart(4, "0"), "proxy values");
mix(events.join(","));
let reentered = 0;
const access = { length: 128 };
for (let i = 0; i < 128; i++)
  Object.defineProperty(access, i, {
    configurable: true,
    get() {
      reentered++;
      const x = Array.from({ length: 96 }, (_, j) => String(95 - j));
      x.sort();
      return String(127 - i).padStart(4, "0");
    },
    set(v) {
      Object.defineProperty(this, i, { value: v, writable: true, configurable: true });
    },
  });
Array.prototype.sort.call(access);
check(reentered === 128, "getter reentry");
for (let i = 0; i < 128; i++) check(access[i] === String(i).padStart(4, "0"), "reentry values");
const readonly = Array.from({ length: 128 }, (_, i) => String(127 - i));
Object.defineProperty(readonly, 0, { writable: false });
threw = false;
try {
  readonly.sort();
} catch (e) {
  threw = e instanceof TypeError;
}
check(threw, "commit error");
if (typeof gc === "function") gc();
print("SORT_CORRECTNESS_PASS " + checks + " " + digest);
