// Development foundation: public C entry into the existing owned-frame executor.
function check(value, message) {
  if (!value) throw Error(message);
}
function fib(n) {
  return n < 2 ? n : fib(n - 1) + fib(n - 2);
}
check(fib(18) === 2584, "flattened calls and returns");
function add(a, b) {
  return a + b;
}
check(add.apply(null, [20, 22]) === 42, "C helper reentry");
function counter() {
  let value = 40;
  return function () {
    return ++value;
  };
}
const next = counter();
check(next() === 41 && next() === 42, "captured cell lifetime");
let finalized = false;
function raise() {
  throw new TypeError("foundation");
}
try {
  raise();
} catch (error) {
  check(error instanceof TypeError, "exception identity");
} finally {
  finalized = true;
}
check(finalized, "exception unwind");
check([1, 2, 3].map((value) => value * 2).join(",") === "2,4,6", "native C callback");
check(JSON.parse(JSON.stringify({ value: 42 })).value === 42, "common JSON");
check(/foundation/.test("linux foundation"), "common regexp");
print("LINUX_FRAME_FOUNDATION_OK");
