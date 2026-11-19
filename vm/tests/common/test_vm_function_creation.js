import * as std from "qjs:std";

function check(actual, expected) {
  if (actual !== expected) throw Error(String(actual) + " != " + String(expected));
}

let moduleValue = 17;
function factory() {
  function leaf(a, b) {
    return a + (b === undefined ? 1 : b);
  }
  return leaf;
}
function forwardBinding() {
  return function forwarded() {
    return moduleValue;
  };
}
function throwingFactory(x) {
  function survivor() {
    return 42;
  }
  if (x) throw survivor;
  return survivor();
}
function generatorFactory() {
  return function* generated() {
    yield 3;
    return 5;
  };
}
// Captured arguments retain independent slots when the closure escapes.
function localCapture(x) {
  return function captured(y) {
    return x + y;
  };
}

for (let i = 0; i < 128; i++) {
  const a = factory(),
    b = factory(),
    forwarded = forwardBinding();
  check(a === b, false);
  check(a.name, "leaf");
  check(a.length, 2);
  std.gc();
  check(a(i), i + 1);
  check(b(i, 5), i + 5);
  moduleValue = i;
  check(forwarded(), i);
  const escaped = localCapture(i);
  std.gc();
  check(escaped(7), i + 7);
  let survivor;
  try {
    throwingFactory(true);
  } catch (e) {
    survivor = e;
  }
  std.gc();
  check(survivor(), 42);
  check(throwingFactory(false), 42);
}

const generated = generatorFactory()();
check(generated.next().value, 3);
check(generated.next().value, 5);
check(generated.next().done, true);

// More than 255 distinct floating constants select the wide fclosure opcode.
let body = "var sum = 0;\n";
for (let i = 0; i < 260; i++) body += "sum += " + (i + 1) + ".125;\n";
body += "return function wideLeaf() { return 73; };";
const wideFactory = Function(body);
const wideLeaf = wideFactory();
std.gc();
check(wideLeaf(), 73);
check(wideLeaf.name, "wideLeaf");
print("function-creation PASS");

// Shared open cells, detached cells, and last-owner removal during a frame.
function sharedCounter(seed) {
  let value = seed;
  function read() {
    return value;
  }
  function write(next) {
    value = next;
    return read();
  }
  return [read, write];
}
for (let i = 0; i < 64; i++) {
  const pair = sharedCounter(i);
  std.gc();
  check(pair[0](), i);
  check(pair[1](i + 9), i + 9);
  check(pair[0](), i + 9);
}
function recreateCell() {
  let value = 1;
  let first = function readFirst() {
    return value;
  };
  check(first(), 1);
  first = undefined;
  std.gc();
  value = 23;
  return function readReplacement() {
    return value;
  };
}
check(recreateCell()(), 23);
function incrementOpen(n) {
  let value = 0;
  function increment() {
    value++;
  }
  for (let i = 0; i < n; i++) increment();
  return value;
}
check(incrementOpen(128), 128);

// A per-iteration lexical cell must close before its slot is reused.
function lexicalCells() {
  let cells = [];
  for (let i = 0; i < 32; i++)
    cells[i] = function readIteration() {
      return i;
    };
  return cells;
}
const cells = lexicalCells();
std.gc();
for (let i = 0; i < cells.length; i++) check(cells[i](), i);
let escapedFromThrow;
function captureThenThrow() {
  let value = { number: 47 };
  escapedFromThrow = function readThrownCell() {
    return value.number;
  };
  throw "capture-unwind";
}
try {
  captureThenThrow();
  throw "missing exception";
} catch (error) {
  check(error, "capture-unwind");
}
std.gc();
check(escapedFromThrow(), 47);
escapedFromThrow = undefined;
function lexicalTDZ() {
  function readEarly() {
    return value;
  }
  return readEarly();
  let value = 3;
}
let tdz = false;
try {
  lexicalTDZ();
} catch (error) {
  tdz = error instanceof ReferenceError;
}
check(tdz, true);
function constantCell() {
  const value = 3;
  return function writeConstant() {
    value = 7;
  };
}
let constantError = false;
try {
  constantCell()();
} catch (error) {
  constantError = error instanceof TypeError;
}
check(constantError, true);

// Indirect writes to captured formal parameters do not affect call operands.
function capturedArgument(value, missing) {
  function replace() {
    value = 39;
    missing = 4;
  }
  replace();
  return function readArguments() {
    return value + missing;
  };
}
check(capturedArgument(3)(), 43);
function forwardingCapture(value) {
  let local = 5;
  function middle() {
    let inner = 7;
    return function forwardedAndLocal() {
      return value + local + inner;
    };
  }
  return middle();
}
const forwardedAndLocal = forwardingCapture(11);
std.gc();
check(forwardedAndLocal(), 23);

// Padding a child call must not touch the caller's table beyond its stack.
const many = Function(
  Array.from({ length: 128 }, (_, i) => "p" + i).join(","),
  'if(p127!==undefined) throw "capture-table-padding"; return 1;',
);
function captureWithPadding() {
  let value = 51;
  function readPaddingCell() {
    return value;
  }
  for (let i = 0; i < 8; i++) check(many(), 1);
  return readPaddingCell;
}
for (let i = 0; i < 8; i++) check(captureWithPadding()(), 51);

// Arena segment growth preserves every open cell's slot and stack-frame link.
function captureDeep(n) {
  let value = n;
  function readDepth() {
    return value;
  }
  if (n === 0) {
    std.gc();
    return [readDepth];
  }
  let result = captureDeep(n - 1);
  result.push(readDepth);
  return result;
}
const deepCells = captureDeep(96);
std.gc();
for (let i = 0; i < deepCells.length; i++) check(deepCells[i](), i);
let deepExceptionCell;
function captureDeepThrow(n) {
  let value = n;
  function readDepthThrown() {
    return value;
  }
  if (n === 0) {
    deepExceptionCell = readDepthThrown;
    throw "deep-capture-unwind";
  }
  return captureDeepThrow(n - 1);
}
try {
  captureDeepThrow(96);
  throw "missing deep exception";
} catch (error) {
  check(error, "deep-capture-unwind");
}
std.gc();
check(deepExceptionCell(), 0);
deepExceptionCell = undefined;
function selfCell() {
  let self = function capturedSelf() {
    return self;
  };
  return self;
}
for (let i = 0; i < 32; i++) {
  let self = selfCell();
  check(self(), self);
  self = undefined;
}
std.gc();
// Capture metadata must compose with read-only/writable argument metadata.
function capturedLocalMissing(value, missing) {
  let cell = value;
  function readCell() {
    return cell;
  }
  if (missing !== undefined) throw "captured-local-missing";
  return readCell;
}
function capturedLocalWritable(value) {
  value += 1;
  let cell = value;
  return function readWrittenCell() {
    return cell;
  };
}
for (let i = 0; i < 8; i++) {
  check(capturedLocalMissing(29)(), 29);
  check(capturedLocalWritable(31)(), 32);
}

print("local-capture PASS");
