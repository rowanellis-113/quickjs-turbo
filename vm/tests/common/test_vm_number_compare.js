/* Differential signature obtained from the pinned upstream C interpreter. */
const operators = [
  (a, b) => a < b,
  (a, b) => a <= b,
  (a, b) => a > b,
  (a, b) => a >= b,
  (a, b) => a == b,
  (a, b) => a != b,
  (a, b) => a === b,
  (a, b) => a !== b,
];
const values = [
  0,
  -0,
  1,
  -1,
  2147483647,
  -2147483648,
  2147483648,
  -2147483649,
  4294967295,
  4294967296,
  9007199254740991,
  -9007199254740991,
  0.5,
  -0.5,
  1.5,
  -1.5,
  5e-324,
  -5e-324,
  Infinity,
  -Infinity,
  NaN,
  undefined,
  null,
  false,
  true,
  "",
  "0",
  "1",
  "1.5",
  "abc",
  0n,
  1n,
  -1n,
  2147483648n,
  9007199254740993n,
  Symbol("s"),
  {},
  {
    valueOf() {
      return 1;
    },
  },
  {
    [Symbol.toPrimitive]() {
      return 1.5;
    },
  },
  {
    [Symbol.toPrimitive]() {
      return Symbol("coercion");
    },
  },
];
let signature = 2166136261;
for (let repetition = 0; repetition < 8; repetition++) {
  for (const op of operators) {
    for (const a of values)
      for (const b of values) {
        let result;
        try {
          result = op(a, b) ? 1 : 0;
        } catch (e) {
          if (!(e instanceof TypeError)) throw e;
          result = 2;
        }
        signature = Math.imul(signature ^ result, 16777619) >>> 0;
      }
  }
}
print("NUMBER_COMPARE_SIGNATURE " + signature);
if (signature !== 2605222213) throw Error("numeric comparison signature differs");
