// Pure Number truthiness and unchanged reference/coercion behavior.
const values = [
  0,
  -0,
  NaN,
  Infinity,
  -Infinity,
  0.25,
  -0.25,
  Number.MIN_VALUE,
  -Number.MIN_VALUE,
  Number.MAX_VALUE,
  -Number.MAX_VALUE,
  2147483648,
  -2147483649,
  1,
  -1,
  null,
  undefined,
  false,
  true,
  "",
  "x",
  0n,
  1n,
  Symbol("x"),
  {},
  [],
  function () {},
];
const expected = [
  false,
  false,
  false,
  true,
  true,
  true,
  true,
  true,
  true,
  true,
  true,
  true,
  true,
  true,
  true,
  false,
  false,
  false,
  true,
  false,
  true,
  false,
  true,
  true,
  true,
  true,
  true,
];
function no(x) {
  return !x;
}
function iff(x) {
  if (x) return 17;
  return 23;
}
function reverse(x) {
  if (!x) return 23;
  return 17;
}
function wide(x) {
  if (x) {
    let n = 0;
    for (let i = 0; i < 300; i++) n += i;
    return n;
  }
  return -1;
}
let checks = 0,
  coercions = 0;
const tricky = {
  valueOf() {
    ++coercions;
    throw Error("coercion");
  },
  toString() {
    ++coercions;
    throw Error("coercion");
  },
};
for (let pass = 0; pass < 120; pass++)
  for (let i = 0; i < values.length; i++) {
    const x = values[i],
      t = expected[i];
    if (
      no(x) !== !t ||
      iff(x) !== (t ? 17 : 23) ||
      reverse(x) !== (t ? 17 : 23) ||
      wide(x) !== (t ? 44850 : -1)
    )
      throw Error("Number truth " + i + " " + pass);
    checks += 4;
  }
if (no(tricky) !== false || iff(tricky) !== 17 || coercions !== 0)
  throw Error("Reference coercion");
checks += 2;
print("NUMBER_TRUTH_OK", checks);
