import { gc } from "qjs:std";
let checks = 0;
function equal(a, b) {
  checks++;
  if (!Object.is(a, b)) throw Error("hint boundary " + checks + ": " + a + " != " + b);
}
function invoke(o, x) {
  return o.go(x);
}
function miss(o) {
  try {
    invoke(o, 1);
  } catch (e) {
    equal(e instanceof TypeError, true);
    return;
  }
  throw Error("expected non-callable");
}
const holders = [],
  receivers = [];
const add = function (x) {
  return this.marker + x;
};
const subtract = function (x) {
  return this.marker - x;
};
for (let n = 0; n < 40; n++) {
  let p = {};
  for (let i = 0; i < n; i++) p["padding" + i] = i;
  p.go = add;
  holders.push(p);
  let o = Object.create(p);
  o.marker = 100 + n;
  receivers.push(o);
}
// Alternate one property name across different real slots, including a stale
// large index followed by a shape with just one property.
for (let round = 0; round < 64; round++) {
  for (let i = 39; i >= 0; i--) equal(invoke(receivers[i], round), 100 + i + round);
}
let getters = 0;
for (let i = 0; i < 40; i++) {
  let p = holders[i],
    o = receivers[i];
  for (let j = 0; j < 20; j++) equal(invoke(o, j), 100 + i + j);
  Object.defineProperty(p, "go", {
    configurable: true,
    get() {
      getters++;
      gc();
      return subtract;
    },
  });
  equal(invoke(o, 3), 97 + i);
  Object.defineProperty(p, "go", { configurable: true, writable: true, value: 4 });
  miss(o);
  Object.defineProperty(p, "go", { configurable: true, writable: true, value: add });
  equal(invoke(o, 4), 104 + i);
  o.go = subtract;
  equal(invoke(o, 5), 95 + i);
  delete o.go;
  equal(invoke(o, 5), 105 + i);
  delete p.go;
  p.other = subtract;
  miss(o);
  p.go = add;
  equal(invoke(o, 6), 106 + i);
  // Trigger deleted-descriptor compaction and grow/reallocate both the
  // hash/descriptor array and property-value storage after a warmed hint.
  for (let j = 0; j < 80; j++) p["grow" + j] = j;
  for (let j = 0; j < 80; j++) delete p["grow" + j];
  for (let j = 0; j < i; j++) delete p["padding" + j];
  equal(invoke(o, 7), 107 + i);
  Object.setPrototypeOf(o, holders[(i + 1) % 40]);
  equal(invoke(o, 8), 108 + i);
  Object.setPrototypeOf(o, p);
  equal(invoke(o, 9), 109 + i);
  if (!(i & 3)) gc();
}
equal(getters, 40);
const small = { go: add };
Object.setPrototypeOf(receivers[39], small);
for (let i = 0; i < 128; i++) equal(invoke(receivers[39], i), 139 + i);
const token = { value: 91 };
small.go = function () {
  return token;
};
for (let i = 0; i < 128; i++) {
  equal(invoke(receivers[39], i), token);
  gc();
}
print("OBJECT_PROTO_HINT_BOUNDARY_PASS checks=" + checks);
