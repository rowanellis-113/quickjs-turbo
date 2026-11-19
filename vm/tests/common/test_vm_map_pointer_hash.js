/* Identity, resizing and ordered iteration must survive bucket hash changes. */
function check(condition) {
  if (!condition) throw Error("Map pointer hash semantics");
}
const keys = [];
for (let i = 0; i < 512; i++) {
  keys.push({ i }, Object.create(null), Symbol("same"), function key() {});
}
const map = new Map();
const set = new Set();
const weak = new WeakMap();
const weakSet = new WeakSet();
for (let i = 0; i < keys.length; i++) {
  map.set(keys[i], i);
  set.add(keys[i]);
  weak.set(keys[i], i);
  weakSet.add(keys[i]);
}
check(map.size === keys.length && set.size === keys.length);
for (let i = 0; i < keys.length; i++) {
  check(map.get(keys[i]) === i && set.has(keys[i]));
  check(weak.get(keys[i]) === i && weakSet.has(keys[i]));
}
check(!map.has({ i: 0 }) && !map.has(Symbol("same")));
/* Resize/delete/reinsert must preserve identity and insertion order. */
const expected = [];
for (let i = 0; i < keys.length; i++) {
  if (i % 3 === 0) {
    check(map.delete(keys[i]) && set.delete(keys[i]));
    check(weak.delete(keys[i]) && weakSet.delete(keys[i]));
    check(!map.has(keys[i]) && !weak.has(keys[i]));
  } else expected.push(keys[i]);
}
for (let i = 0; i < keys.length; i += 3) {
  map.set(keys[i], -i);
  set.add(keys[i]);
  weak.set(keys[i], -i);
  weakSet.add(keys[i]);
  expected.push(keys[i]);
}
let index = 0;
for (const key of map.keys()) check(key === expected[index++]);
check(index === keys.length);
index = 0;
for (const key of set) check(key === expected[index++]);
check(index === keys.length);
for (let i = 0; i < keys.length; i++) {
  const value = i % 3 === 0 ? -i : i;
  check(Object.is(map.get(keys[i]), value) && Object.is(weak.get(keys[i]), value));
}
/* Preserve SameValueZero and distinct key domains alongside pointer keys. */
map.set(-0, 1);
map.set(+0, 2);
map.set(NaN, 3);
map.set(Number("x"), 4);
map.set(1, 5);
map.set(1n, 6);
map.set("1", 7);
check(map.get(-0) === 2 && map.get(NaN) === 4);
check(map.get(1) === 5 && map.get(1n) === 6 && map.get("1") === 7);
let changed = false;
const visited = [];
const live = new Map([
  [keys[0], 0],
  [keys[1], 1],
  [keys[2], 2],
]);
live.forEach((value, key) => {
  visited.push(key);
  if (!changed) {
    changed = true;
    live.delete(keys[1]);
    live.set(keys[3], 3);
  }
});
check(
  visited.length === 3 &&
    visited[0] === keys[0] &&
    visited[1] === keys[2] &&
    visited[2] === keys[3],
);
map.clear();
set.clear();
check(map.size === 0 && set.size === 0);
print("Map/Set/WeakMap/WeakSet pointer keys: passed");
