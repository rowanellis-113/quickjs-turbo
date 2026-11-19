"use strict";
let checks = 0;
function check(v, m) {
  checks++;
  if (!v) throw Error(m);
}
function leaf(x) {
  return x + 1;
}
function inner(x) {
  let y = leaf(x);
  return y + 1;
}
function middle(x) {
  let y = inner(x);
  return y + 1;
}
function outer(x) {
  let y = middle(x);
  return y + 1;
}
function missing(x, a, b, c, d, e, f, g, h, i, j) {
  let y = outer(x);
  return y + (j === undefined);
}
function capture(x) {
  return function (v) {
    x += v;
    return x;
  };
}
function forwarded(x) {
  return middle.call(null, x);
}
function immediate(x) {
  let y = outer(x);
  return y;
}
function heap(x) {
  let y = { x: outer(x) };
  return y;
}
function host(x) {
  let y = outer(x);
  gc();
  return y;
}
function failureLeaf() {
  return Number(Symbol("error"));
}
function failureMiddle() {
  let x = failureLeaf();
  return x;
}
function failureOuter() {
  let x = failureMiddle();
  return x;
}
function caught() {
  try {
    failureOuter();
  } catch (e) {
    check(e instanceof TypeError, "type");
    for (const name of ["failureLeaf", "failureMiddle", "failureOuter"])
      check(e.stack.includes(name), "published backtrace " + name);
    return 1;
  }
  throw Error("no exception");
}
class C {
  constructor(x) {
    this.x = outer(x);
  }
}
class HeapC {
  constructor(x) {
    this.ignore = { x };
    return { x: outer(x) };
  }
}
function construct(C, x) {
  let y = new C(x);
  return y;
}
function deep(n) {
  let x = n ? deep(n - 1) : 3;
  return x + 1;
}
function clear(v) {
  let x = v;
  gc();
  return x;
}
for (let i = 0; i < 128; i++) {
  check(outer(i) === i + 4, "call");
  check(missing(i) === i + 5, "owned arity");
  const f = capture(i);
  check(f(2) === i + 2 && f(3) === i + 5, "capture");
  check(forwarded(i) === i + 3, "logical");
  check(immediate(i) === i + 4, "return");
  check(heap(i).x === i + 4 && host(i) === i + 4, "heap and GC");
  check(construct(C, i).x === i + 4 && construct(HeapC, i).x === i + 4, "root3");
  check(caught() === 1, "caught");
  check(clear({ x: i }).x === i, "live owner");
}
check(deep(64) === 68, "deep return phases");
gc();
print("LINUX_PUBLICATION_OK checks=" + checks);
