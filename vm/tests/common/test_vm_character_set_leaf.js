import * as std from "qjs:std";
let checks = 0;
function check(v, m) {
  checks++;
  if (!v) throw Error(m);
}
function reference(s, a, b, c) {
  return s == a || s == b || s == c;
}
const sets = [
  [" ", "\n", "\r"],
  ["a", "b", "c"],
  ["\0", "\xff", "!"],
  ["0", "1", "2"],
  ["", "ab", "x"],
  ["\u1000", "z", "\u1001"],
];
const values = [
  undefined,
  null,
  false,
  true,
  0,
  -0,
  1,
  2,
  NaN,
  Infinity,
  0n,
  1n,
  Symbol("s"),
  "",
  "a",
  "b",
  "c",
  " ",
  "\n",
  "\r",
  "\0",
  "\xff",
  "ab",
  "\u1000",
  "\u1001",
];
for (const set of sets) {
  const body =
    "return s==" +
    JSON.stringify(set[0]) +
    "||s==" +
    JSON.stringify(set[1]) +
    "||s==" +
    JSON.stringify(set[2]) +
    ";";
  const f = Function("s", body),
    tail = Function("f", "s", "return f(s);");
  for (let round = 0; round < 32; round++) {
    for (const value of values) {
      const expected = reference(value, ...set);
      check(f(value) === expected, "value");
      check(tail(f, value) === expected, "tail");
      check(f(value, { alive: 1 }, ["extra"]) === expected, "extra");
    }
    for (let code = 0; code < 256; code++) {
      const value = String.fromCharCode(code),
        expected = reference(value, ...set);
      check(f(value) === expected, "all Latin1");
    }
  }
  check(f() === reference(undefined, ...set), "missing");
  for (const text of ["a", " ", "\n", "\u1000", "not-in-set"]) {
    let actualCalls = 0,
      expectedCalls = 0;
    const a = {
      [Symbol.toPrimitive]() {
        actualCalls++;
        return text;
      },
    };
    const b = {
      [Symbol.toPrimitive]() {
        expectedCalls++;
        return text;
      },
    };
    check(f(a) === reference(b, ...set), "coercion");
    check(actualCalls === expectedCalls, "coercion count");
  }
  const throwing = {
    [Symbol.toPrimitive]() {
      throw Error("expected coercion");
    },
  };
  let threw = false;
  try {
    f(throwing);
  } catch (e) {
    threw = e.message === "expected coercion";
  }
  check(threw, "throw");
  for (let i = 0; i < 16; i++) {
    check(f(set[0]) === true, "repeat");
    std.gc();
    check(f("not-in-set") === false, "after gc");
  }
}
print("FRAME_CHARACTER_SET_LEAF_OK " + checks);
