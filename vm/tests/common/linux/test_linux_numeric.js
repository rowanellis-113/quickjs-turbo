function check(value, message) {
  if (!value) throw Error(message);
}
function local(left, right, count) {
  let value = left;
  for (let i = 0; i < count; ++i) value += right;
  return value;
}
function arithmetic(left, right) {
  return (left + right) * right;
}
const cases = [
  [0n, 1n, 257, 257n],
  [-1n, -3n, 257, -772n],
  [2147483647n, 1n, 4, 2147483651n],
  [-2147483648n, -1n, 4, -2147483652n],
  [18446744073709551616n, 3n, 257, 18446744073709552387n],
  [-18446744073709551616n, -3n, 257, -18446744073709552387n],
  [1329227995784915872903807060280344576n, -1n, 257, 1329227995784915872903807060280344319n],
];
for (let round = 0; round < 32; ++round) {
  for (const [a, b, n, expected] of cases) {
    check(local(a, b, n) === expected, "local owner/result");
    check(local(a, b, 0) === a, "unchanged local");
  }
  check(arithmetic(18446744073709551616n, 3n) === 55340232221128654857n, "primitive add/multiply");
  check(arithmetic(-18446744073709551616n, 3n) === -55340232221128654839n, "negative primitive");
  let observations = 0;
  const obj = {
    [Symbol.toPrimitive]() {
      ++observations;
      return 4n;
    },
  };
  check(local(3n, obj, 2) === 11n && observations === 2, "coercion fallback");
  check(local("a", "b", 3) === "abbb", "string local remains");
  check(local(3, 0.25, 4) === 4, "number local remains");
  check(local(3n, "x", 1) === "3x", "mixed string remains");
  let failed = false;
  try {
    local(3n, 1, 1);
  } catch (e) {
    failed = e instanceof TypeError;
  }
  check(failed, "mixed BigInt TypeError");
  const exact = [
    ["-0", -0],
    ["0.125", 0.125],
    ["-1234567.125", -1234567.125],
    ["999999999999999", 999999999999999],
    ["0.000000000000001", 1e-15],
    ["1e20", 1e20],
    ["0x80", 128],
    ["  12.5  ", 12.5],
  ];
  for (const [text, number] of exact) {
    check(Object.is(Number(text), number), "decimal/fallback " + text);
    check(Object.is(+text, number), "unary conversion " + text);
  }
}
check(local(0n, 1n, 25000) === 25000n, "short native loop");
print("LINUX_NUMERIC_FAMILY_OK");
