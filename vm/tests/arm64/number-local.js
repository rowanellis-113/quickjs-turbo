/* Public semantics for the shared number-local kernel and its C exits. MIT. */
function addLocal(a, b) {
  let value = a;
  value += b;
  return value;
}
function add(a, b) {
  return a + b;
}
function subtract(a, b) {
  return a - b;
}
function multiply(a, b) {
  return a * b;
}
function divide(a, b) {
  return a / b;
}
function check(condition, description) {
  if (!condition) throw new Error(description);
}
const values = [
  0,
  -0,
  1,
  -1,
  2147483647,
  -2147483648,
  0.25,
  -0.25,
  1e100,
  -1e100,
  Number.MIN_VALUE,
  Infinity,
  -Infinity,
  NaN,
  true,
  false,
  null,
  undefined,
  "",
  "12",
  0n,
  2n,
  Symbol("value"),
];
let checked = 0;
let matrixHash = 2166136261;
function recordValue(value, error) {
  const encoded = error
    ? "E:" + error.name
    : typeof value + ":" + (Object.is(value, -0) ? "-0" : String(value));
  for (let index = 0; index < encoded.length; ++index)
    matrixHash = Math.imul(matrixHash ^ encoded.charCodeAt(index), 16777619) >>> 0;
  matrixHash = Math.imul(matrixHash ^ 255, 16777619) >>> 0;
}
for (const a of values) {
  for (const b of values) {
    let expected, actual, referenceError, actualError;
    try {
      expected = a + b;
    } catch (error) {
      referenceError = error.constructor;
    }
    try {
      actual = addLocal(a, b);
    } catch (error) {
      actualError = error.constructor;
    }
    check(referenceError === actualError, "same nonnumber exception");
    check(
      referenceError || Object.is(actual, expected),
      "same numeric/sign/NaN/BigInt/string value",
    );
    ++checked;
    recordValue(actual, actualError);
    for (let operation = 0; operation < 4; ++operation) {
      expected = actual = referenceError = actualError = undefined;
      try {
        switch (operation) {
          case 0:
            expected = a + b;
            break;
          case 1:
            expected = a - b;
            break;
          case 2:
            expected = a * b;
            break;
          case 3:
            expected = a / b;
            break;
        }
      } catch (error) {
        referenceError = error.constructor;
      }
      try {
        switch (operation) {
          case 0:
            actual = add(a, b);
            break;
          case 1:
            actual = subtract(a, b);
            break;
          case 2:
            actual = multiply(a, b);
            break;
          case 3:
            actual = divide(a, b);
            break;
        }
      } catch (error) {
        actualError = error.constructor;
      }
      check(referenceError === actualError, "operator exception family");
      check(referenceError || Object.is(actual, expected), "operator boxing/value/sign/NaN");
      ++checked;
      recordValue(actual, actualError);
    }
  }
}
for (let iteration = 0; iteration < 20; ++iteration) {
  const order = [];
  const left = {
    [Symbol.toPrimitive](hint) {
      order.push("left:" + hint);
      std.gc();
      return 1.25;
    },
  };
  const right = {
    [Symbol.toPrimitive](hint) {
      order.push("right:" + hint);
      std.gc();
      return 2.5;
    },
  };
  check(addLocal(left, right) === 3.75, "GC coercion result");
  check(order.join(",") === "left:default,right:default", "coercion order and count");
  const marker = {};
  const throwing = {
    [Symbol.toPrimitive]() {
      std.gc();
      throw marker;
    },
  };
  let caught;
  try {
    addLocal(0.5, throwing);
  } catch (error) {
    caught = error;
  }
  check(caught === marker, "original exception identity");
}
let sum = 0;
for (let i = 0; i < 10000; ++i) sum = addLocal(sum, 0.25);
check(sum === 2500, "warm number-local loop");

const fusedOperations = [
  (a, b) => a < b,
  (a, b) => a <= b,
  (a, b) => a > b,
  (a, b) => a >= b,
  (a, b) => a == b,
  (a, b) => a != b,
  (a, b) => a & b,
];
for (const a of values) {
  for (const b of values) {
    for (const operation of fusedOperations) {
      let result, error;
      try {
        result = operation(a, b);
      } catch (caught) {
        error = caught.constructor;
      }
      recordValue(result, error);
      ++checked;
    }
  }
}
function capturedPair(a, b) {
  return () => a * b + (a - b);
}
const captured = capturedPair(123, -77);
for (let iteration = 0; iteration < 100; ++iteration) {
  std.gc();
  check(captured() === -9271, "captured producer, GC and combined arithmetic");
}

check(matrixHash === 3315434651, "independent official-2026 matrix reference");
print("NUMBER_LOCAL_OK", checked, matrixHash);
