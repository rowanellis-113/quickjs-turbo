import * as std from "qjs:std";
let checks = 0;
function check(condition, why) {
  checks++;
  if (!condition) throw Error("COROUTINE " + checks + ": " + why);
}
function same(actual, expected, why) {
  check(Object.is(actual, expected), why);
}
function* arithmetic(a, b) {
  yield a + b;
  yield a - b;
  yield a * b;
  yield a % b;
  yield a < b;
  yield a <= b;
  yield a > b;
  yield a >= b;
  yield a === b;
  yield a !== b;
  yield a & b;
  yield a | b;
  yield a ^ b;
  yield a << b;
  yield a >> b;
  yield a >>> b;
}
const inputs = [0, -0, 1, -1, 17, 31, 2147483647, -2147483648, 0.5, NaN, Infinity];
for (const a of inputs) {
  for (const b of inputs) {
    const expected = [
      a + b,
      a - b,
      a * b,
      a % b,
      a < b,
      a <= b,
      a > b,
      a >= b,
      a === b,
      a !== b,
      a & b,
      a | b,
      a ^ b,
      a << b,
      a >> b,
      a >>> b,
    ];
    const actual = [...arithmetic(a, b)];
    check(actual.length === expected.length, "arithmetic length");
    for (let i = 0; i < actual.length; i++) same(actual[i], expected[i], "arithmetic boundary");
  }
}
function* scalarLoop(n) {
  let a = 1,
    b = 0,
    c = 17;
  for (let i = 0; i < n; ++i) {
    a = ((a + i) ^ c) % 997;
    b += a;
    if (i & 1) c++;
    else c--;
    if (i % 127 === 0) yield [a, b, c];
  }
  return b;
}
let last;
for (const state of scalarLoop(3000)) last = state;
same(JSON.stringify(last), "[265,1454567,17]", "integer loop state");
function* ownership(a, other) {
  let x = a,
    y = other;
  yield [x, y];
  x = y;
  y = a;
  yield [x, y];
  x = { replacement: true };
  y = undefined;
  std.gc();
  yield x;
  x = "text";
  yield x;
  x = null;
  yield x;
}
for (let i = 0; i < 32; i++) {
  const a = { id: i },
    b = { id: -i };
  const g = ownership(a, b);
  let r = g.next();
  check(r.value[0] === a && r.value[1] === b, "initial owners");
  std.gc();
  r = g.next();
  check(r.value[0] === b && r.value[1] === a, "shared replacement");
  r = g.next();
  check(r.value.replacement, "last owner slow exit");
  same(g.next().value, "text", "reference to string");
  same(g.next().value, null, "string to primitive");
  check(g.next().done, "owners complete");
}
function* captured(a) {
  let x = a;
  const read = () => [a, x];
  yield read;
  a = 17;
  x = { v: 19 };
  yield read;
  x = 23;
  return read;
}
const g = captured(7);
const read = g.next().value;
same(JSON.stringify(read()), "[7,7]", "captured initial");
check(g.next().value === read, "capture identity");
std.gc();
same(JSON.stringify(read()), '[17,{"v":19}]', "capture after suspension");
check(g.next().value === read, "closed capture identity");
std.gc();
same(JSON.stringify(read()), "[17,23]", "closed persistent capture");
function* tdz() {
  yield x;
  let x = 1;
}
let thrown;
try {
  tdz().next();
} catch (e) {
  thrown = e;
}
check(thrown instanceof ReferenceError, "TDZ exits before slot read");
const events = [];
function* completion() {
  try {
    yield 1;
    yield 2;
  } catch (e) {
    events.push("catch:" + e);
    yield 3;
  } finally {
    events.push("finally");
    yield 4;
  }
  return 5;
}
const h = completion();
same(h.next().value, 1, "initial yield");
same(h.throw("E").value, 3, "throw continuation");
same(h.return(9).value, 4, "return through finally");
let result = h.next();
check(result.done && result.value === 9, "saved abrupt completion");
same(events.join(","), "catch:E,finally", "exception ordering");
function* delegation() {
  try {
    yield* completion();
  } finally {
    events.push("outer");
  }
}
const d = delegation();
same(d.next().value, 1, "delegated initial");
d.return(11);
d.next();
same(events.slice(-2).join(","), "finally,outer", "delegated close");
function* reentry() {
  let rejected = false;
  try {
    r.next();
  } catch (e) {
    rejected = e instanceof TypeError;
  }
  yield rejected;
}
const r = reentry();
check(r.next().value, "executing generator reentry");
async function* asynchronous(n) {
  let acc = 0;
  try {
    for (let i = 0; i < n; i++) {
      acc = (acc + i) % 97;
      await Promise.resolve(i);
      yield acc;
    }
  } finally {
    events.push("async-finally");
  }
  return acc;
}
let count = 0,
  sum = 0;
for await (const value of asynchronous(128)) {
  count++;
  sum += value;
}
same(count, 128, "async iterator length");
same(sum, 5348, "async iterator state");
check(events.at(-1) === "async-finally", "async completion cleanup");
async function retained() {
  let object = { answer: 42 };
  const capture = () => object;
  await 0;
  std.gc();
  check(capture() === object, "await capture ownership");
  object = 13;
  await Promise.resolve();
  return capture();
}
same(await retained(), 13, "async captured update");
print("COROUTINE_SEGMENTS_CHECKS " + checks);
