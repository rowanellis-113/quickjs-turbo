function assertEq(actual, expected, label) {
  if (!Object.is(actual, expected)) {
    throw new Error(
      (label || "assertEq") + ": expected " + String(expected) + ", got " + String(actual),
    );
  }
}

function assertThrows(fn, ErrCtor, label) {
  let threw = false;
  try {
    fn();
  } catch (e) {
    threw = true;
    if (ErrCtor && !(e instanceof ErrCtor)) {
      throw new Error((label || "assertThrows") + ": unexpected error " + e);
    }
  }
  if (!threw) {
    throw new Error((label || "assertThrows") + ": did not throw");
  }
}

// 1. Chained property IC + IC map bias + mid-chain edge cases
(function testPropertyChains() {
  function readChain(r, n) {
    let s = 0;
    for (let i = 0; i < n; i++) {
      s += r.a.b.c;
    }
    return s;
  }
  const root = { a: { b: { c: 7 } } };
  assertEq(readChain(root, 200), 1400, "chain3 warm");

  // Mid-chain getter mutating downstream
  let getterHits = 0;
  const dynRoot = {
    get a() {
      getterHits++;
      return { b: { c: 11 } };
    },
  };
  assertEq(readChain(dynRoot, 5), 55, "chain3 getter");
  assertEq(getterHits, 5, "chain3 getter count");

  // Mid-chain null throws TypeError
  assertThrows(() => readChain({ a: { b: null } }, 1), TypeError, "chain3 null");

  // Proxy mid-chain
  const proxied = {
    a: new Proxy(
      { b: { c: 19 } },
      {
        get(t, k) {
          return t[k];
        },
      },
    ),
  };
  assertEq(readChain(proxied, 10), 190, "chain3 proxy");

  // Polymorphic + megamorphic shapes
  const shapes = [];
  for (let k = 0; k < 24; k++) {
    const leaf = { c: k + 1 };
    leaf["extra_" + k] = k;
    shapes.push({ a: { b: leaf } });
  }
  let polySum = 0;
  for (let i = 0; i < 96; i++) {
    polySum += readChain(shapes[i % shapes.length], 2);
  }
  assertEq(polySum, 2400, "chain3 megamorphic");
})();

// 2. Noncalling frame-free leaves + negative bit cache
(function testCallLeaves() {
  const fUndef = function () {};
  const fConst = function () {
    return 5;
  };
  const fMinus1 = function () {
    return -1;
  };
  const fArg1 = function (a, b) {
    return b;
  };
  const fNull = function () {
    return null;
  };
  const fBool = function () {
    return true;
  };
  const fAddConst = function (x) {
    return x + 3;
  };
  const fAddArgs = function (x, y) {
    return x + y;
  };

  for (let i = 0; i < 100; i++) {
    assertEq(fUndef(), undefined, "leaf undef");
    assertEq(fConst(), 5, "leaf const");
    assertEq(fMinus1(), -1, "leaf -1");
    assertEq(fArg1(10, 20), 20, "leaf arg1");
    assertEq(fArg1(10), undefined, "leaf missing arg");
    assertEq(fNull(), null, "leaf null");
    assertEq(fBool(), true, "leaf bool");
    assertEq(fAddConst(14), 17, "leaf add const");
    assertEq(fAddArgs(12, 30), 42, "leaf add args");
  }
  assertEq(fAddConst(0x7fffffff), 2147483650, "leaf add const overflow");
  assertEq(fAddArgs(0x7fffffff, 1), 2147483648, "leaf add args overflow");
  assertEq(fAddArgs("ab", "cd"), "abcd", "leaf add string fallback");

  // Closure read & closure inc/dec leaves
  function makeCounter(start) {
    let c = start;
    return {
      inc() {
        c++;
      },
      dec() {
        c--;
      },
      get() {
        return c;
      },
    };
  }
  const ctr = makeCounter(0);
  for (let i = 0; i < 250; i++) ctr.inc();
  for (let i = 0; i < 50; i++) ctr.dec();
  assertEq(ctr.get(), 200, "closure inc/dec");

  const ovf = makeCounter(0x7fffffff);
  ovf.inc();
  assertEq(ovf.get(), 2147483648, "closure inc overflow");

  assertThrows(
    () => {
      const k = 10;
      const bad = () => {
        k++;
      };
      bad();
    },
    TypeError,
    "closure const inc",
  );

  assertThrows(
    () => {
      const readTdz = () => tdzVal;
      readTdz();
      let tdzVal = 1;
      return tdzVal;
    },
    ReferenceError,
    "closure TDZ read",
  );

  // 9B getter & 10B setter leaves
  class Box {
    constructor(v) {
      this._v = v;
    }
    get v() {
      return this._v;
    }
    set v(x) {
      this._v = x;
    }
  }
  const box = new Box(1);
  let acc = 0;
  for (let i = 0; i < 200; i++) {
    box.v = i;
    acc += box.v;
  }
  assertEq(acc, 19900, "getter9 + setter10 int");

  // Setter overwriting last-ref objects + self reference
  for (let i = 0; i < 50; i++) {
    box.v = { payload: i };
  }
  assertEq(box.v.payload, 49, "setter10 last-ref object");
  box.v = box;
  box.v = 99;
  assertEq(box.v, 99, "setter10 self-alias");

  // Readonly data property in setter throws TypeError
  const roBox = new Box(7);
  Object.defineProperty(roBox, "_v", { writable: false });
  assertThrows(
    () => {
      roBox.v = 8;
    },
    TypeError,
    "setter10 readonly",
  );
  assertEq(roBox.v, 7, "setter10 readonly preserved");
})();

// 3. Fused int32 compare + short branch
(function testCompareBranch() {
  function runCmp(a, b, n) {
    let s = 0;
    for (let i = 0; i < n; i++) {
      if (a < b) s += 1;
      if (a <= b) s += 2;
      if (b > a) s += 4;
      if (b >= a) s += 8;
      if (a == a) s += 16;
      if (a != b) s += 32;
    }
    return s;
  }
  assertEq(runCmp(-2147483648, 2147483647, 100), 6300, "int32 extreme bounds");
  assertEq(runCmp(1.25, 2.5, 20), 1260, "float64 compare fallback");
  assertEq(runCmp("aa", "bb", 10), 630, "string compare fallback");
})();

// 4. Float32Array / Float64Array + borrowed indexed & field stores
(function testTypedAndBorrowedIndexed() {
  const f64 = new Float64Array(64);
  const f32 = new Float32Array(64);
  const i32 = new Int32Array(64);
  const dense = new Array(64).fill(0);

  function kernel(a64, a32, ai, ad) {
    let sum = 0;
    for (let i = 0; i < 64; i++) {
      a64[i] = i * 0.5;
      a32[i] = i * 0.25;
      ai[i] = i * 3;
      ad[i] = i + 1;
    }
    for (let i = 0; i < 64; i++) {
      sum += a64[i] + a32[i] + ai[i] + ad[i];
    }
    return sum;
  }
  assertEq(kernel(f64, f32, i32, dense), 9640, "borrowed indexed kernel");

  // Unborrowed expression receiver + special floats (-0, NaN)
  const getF64 = () => f64;
  getF64()[0] = -0.0;
  assertEq(Object.is(getF64()[0], -0.0), true, "f64 -0");
  getF64()[1] = NaN;
  assertEq(Number.isNaN(getF64()[1]), true, "f64 NaN");
  assertEq(f64[100], undefined, "f64 OOB read");
  assertEq(f32[100], undefined, "f32 OOB read");

  // Dense array holding objects replaced by int via borrowed store
  const objArr = [{ x: 1 }, { x: 2 }, { x: 3 }];
  function overwriteArr(arr) {
    for (let i = 0; i < 3; i++) {
      arr[i] = i + 10;
    }
  }
  overwriteArr(objArr);
  assertEq(objArr[0] + objArr[1] + objArr[2], 33, "borrowed dense overwrite object");

  // Borrowed put_field replace
  function updatePoint(pt, n) {
    for (let i = 0; i < n; i++) {
      pt.x = i;
      pt.y = 7;
    }
  }
  const pt = { x: { old: true }, y: 0 };
  updatePoint(pt, 100);
  assertEq(pt.x, 99, "borrowed put_field x");
  assertEq(pt.y, 7, "borrowed put_field y");
})();

// 5. Native OP_put_var (global var & top-level lexical)
var globalVarCounter = 0;
let globalLexCounter = 0;
const globalConstVal = 42;

(function testGlobalPutVar() {
  for (let i = 0; i < 300; i++) {
    globalVarCounter = i;
    globalLexCounter = i * 2;
  }
  assertEq(globalVarCounter, 299, "global var write");
  assertEq(globalLexCounter, 598, "global lex write");

  // Overwriting last-ref heap object in global var
  for (let i = 0; i < 40; i++) {
    globalVarCounter = { v: i };
  }
  assertEq(globalVarCounter.v, 39, "global var last-ref object");

  assertThrows(
    () => {
      globalConstVal = 99;
    },
    TypeError,
    "global const write",
  );

  assertThrows(
    () => {
      "use strict";
      undeclaredStrictGlobal999 = 1;
    },
    ReferenceError,
    "strict undeclared global write",
  );

  let setterObserved = 0;
  Object.defineProperty(globalThis, "globalAccessorProp", {
    get() {
      return setterObserved;
    },
    set(v) {
      setterObserved = v + 10;
    },
    configurable: true,
  });
  globalAccessorProp = 25;
  assertEq(globalAccessorProp, 35, "global accessor setter");
  delete globalThis.globalAccessorProp;
})();

// 6. R89v2: dup2/dup1/perm3/nip, float64 bitwise & neg, strict/loose equality extensions
(function testR89v2Extensions() {
  // Compound indexed ops exercising dup2 / perm3
  const arr = [{ n: 1 }, 10, 20, 30];
  for (let i = 1; i < 4; i++) {
    arr[i] += 5;
    arr[i] |= 256;
  }
  assertEq(arr[1], 271, "dup2 compound +/|= 1");
  assertEq(arr[2], 281, "dup2 compound +/|= 2");
  assertEq(arr[3], 291, "dup2 compound +/|= 3");

  // Float64 bitwise ops (|, &, ^, <<, >>, >>>) + unary -
  function fbw(x, y) {
    return [x | 0, x & y, x ^ y, x << 2.9, x >> 1.5, x >>> 0, -x];
  }
  const r1 = fbw(4294967295.0, 0x12345678 + 0.5);
  assertEq(r1[0], -1, "f64 | 0 on 0xffffffff");
  assertEq(r1[1], 0x12345678, "f64 &");
  assertEq(r1[2], -1 ^ 0x12345678, "f64 ^");
  assertEq(r1[3], -4, "f64 <<");
  assertEq(r1[4], -1, "f64 >>");
  assertEq(r1[5], 4294967295, "f64 >>> 0 uint32");
  assertEq(r1[6], -4294967295.0, "f64 unary -");

  assertEq(Object.is(-(0.5 - 0.5), -0.0), true, "f64 -0.0");
  assertEq(Number.isNaN(-(0 / 0)), true, "f64 -NaN");
  assertEq(NaN | 0, 0, "NaN | 0");
  assertEq(Infinity | 0, 0, "Inf | 0");
  assertEq(-Infinity | 0, 0, "-Inf | 0");
  assertEq(9007199254740994.0 | 0, 2, "2^53+2 | 0 fallback");

  // Strict & loose equality extensions (including rope vs string & BigInt)
  const objA = { k: 1 },
    objB = { k: 1 };
  const symA = Symbol("a"),
    symB = Symbol("a");
  let rope = "ab";
  for (let i = 0; i < 4; i++) rope += "cd"; // rope tag -6
  const flat = "abcdcdcdcd";

  for (let i = 0; i < 50; i++) {
    assertEq(objA !== false, true, "obj !== false");
    assertEq(objA === false, false, "obj === false");
    assertEq(true !== false, true, "bool !== bool");
    assertEq(false === false, true, "bool === bool");
    assertEq(null === null, true, "null === null");
    assertEq(undefined === undefined, true, "undef === undef");
    assertEq(null === undefined, false, "null === undef");
    assertEq(objA != objB, true, "loose obj != obj");
    assertEq(objA == objA, true, "loose obj == same obj");
    assertEq(symA != symB, true, "loose sym != sym");
    assertEq(rope === flat, true, "rope === flat string");
    assertEq(1n === 1n, true, "bigint ===");
    assertEq(1n === 1, false, "bigint === int");
  }
})();

// 7. R89v3: constructors >1 slot, last-ref free, Array.length, for-backedge, arith+put_loc, pair_put_field, 2B indexed, to_object, string <, Array.pop
(function testR89v3Extensions() {
  // 7a. Constructor implicit return with 2..10 slots, distinct refs + aliased refs (ref_count == 2)
  function Vec3(x, y, z) {
    const tmp = { tag: "tmp" };
    const alias = this;
    this.x = x;
    this.y = y;
    this.z = z;
    let a = { k: 1 },
      b = { k: 2 },
      c = a;
    if (x < 0) return { custom: tmp, c, alias };
  }
  let vSum = 0;
  for (let i = 0; i < 120; i++) {
    const v = new Vec3(i, i + 1, i + 2);
    vSum += v.x + v.y + v.z;
  }
  assertEq(vSum, 21780, "constructor 64-bit uniqueness guard");
  const customV = new Vec3(-1, 2, 3);
  assertEq(customV.custom.tag, "tmp", "constructor explicit object return");

  // 7b. Last-ref drop, nip, property_replace (including self-alias)
  function makeAndDrop(n) {
    let out = 0;
    for (let i = 0; i < n; i++) {
      ({ a: i, b: i + 1 }); // OP_drop on last-ref object
      out += ({ p: i }, i + 1); // comma/nip idioms
    }
    return out;
  }
  assertEq(makeAndDrop(100), 5050, "last-ref drop");

  const holder = { ref: { init: 1 } };
  for (let i = 0; i < 80; i++) {
    holder.ref = { idx: i };
  }
  assertEq(holder.ref.idx, 79, "property_replace last-ref");
  holder.ref = holder;
  holder.ref = 42;
  assertEq(holder.ref, 42, "property_replace self-alias");

  // 7c. Fast Array.length truncation (ints, objects, holes, readonly length TypeError)
  const truncArr = [];
  for (let i = 0; i < 64; i++) {
    truncArr.push(i % 2 === 0 ? { n: i } : i);
  }
  for (let len = 63; len >= 0; len--) {
    truncArr.length = len;
    assertEq(truncArr.length, len, "array length decr");
  }
  assertEq(truncArr[0], undefined, "array truncated slot 0");
  assertThrows(
    () => {
      truncArr.length = -1;
    },
    RangeError,
    "negative array length",
  );

  const nonWritableArr = [1, 2, 3];
  Object.defineProperty(nonWritableArr, "length", { writable: false });
  assertThrows(
    () => {
      "use strict";
      nonWritableArr.length = 1;
    },
    TypeError,
    "readonly array length",
  );
  assertEq(nonWritableArr.length, 3, "readonly array length preserved");

  // 7d. Universal for-loop backedge (inc_loc/dec_loc + goto8 -> lt/lte/gt/gte + if_false8/if_true8)
  function loopVariants(n) {
    let a = 0;
    for (let i = 0; i < n; i++) a += 1;
    for (let i = 0; i <= n; i++) a += 1;
    for (let i = n; i > 0; i--) a += 1;
    for (let i = n; i >= 0; i--) a += 1;
    for (let i = 0; i < 0; i++) a += 1000; // zero-trip
    for (let i = 0; i < 1; i++) a += 10; // single-trip
    return a;
  }
  assertEq(loopVariants(50), 50 + 51 + 50 + 51 + 10, "for-loop backedge variants");

  // INT32_MAX overflow safety on inc_loc / dec_loc
  let ovfI = 2147483646,
    ovfSteps = 0;
  for (; ovfI < 2147483649; ovfI++) {
    ovfSteps++;
  }
  assertEq(ovfSteps, 3, "for-loop INT32_MAX transition");

  // 7e. Arithmetic + put_loc0..3 fusion (including overwriting heap object in loc0..3)
  function arithPutLoc(n) {
    let s0 = { old: 1 };
    let s1 = 1000;
    let s2 = 1;
    let s3 = 64;
    s0 = 0;
    for (let i = 1; i <= n; i++) {
      s0 = i + 2;
      s1 = s1 - i;
      s2 = i * 3;
      s3 = s3 / 2;
    }
    return [s0, s1, s2, s3];
  }
  const apl = arithPutLoc(4);
  assertEq(apl[0], 6, "add+put_loc0");
  assertEq(apl[1], 990, "sub+put_loc1");
  assertEq(apl[2], 12, "mul+put_loc2");
  assertEq(apl[3], 4, "div+put_loc3");

  function overwriteObjWithArith() {
    let x = { alive: true };
    x = 3 + 4;
    return x;
  }
  assertEq(overwriteObjWithArith(), 7, "arith+put_loc0 overwrites object");

  // 7f. get_loc0_loc1 + put_field & 2B index borrowed get_array_el / put_array_el
  function writeFieldsAnd2BIndex() {
    let obj = { a: 0, b: 0 };
    let val = 17;
    for (let i = 0; i < 40; i++) {
      obj.a = val;
      obj.b = val;
    }
    const tab = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11];
    for (let j = 0; j < 20; j++) {
      tab[8] = j;
      tab[9] = j + 1;
    }
    return obj.a + obj.b + tab[8] + tab[9];
  }
  assertEq(writeFieldsAnd2BIndex(), 34 + 19 + 20, "pair_put_field + 2B borrowed array");

  // 7g. OP_to_object (destructuring object vs null/undefined TypeError)
  function destructurePair(src) {
    let { p, q } = src;
    return p + q;
  }
  assertEq(destructurePair({ p: 12, q: 30 }), 42, "OP_to_object object");
  assertEq(destructurePair("hi") !== 999, true, "OP_to_object primitive string");
  assertThrows(() => destructurePair(null), TypeError, "OP_to_object null");
  assertThrows(() => destructurePair(undefined), TypeError, "OP_to_object undefined");

  // 7h. Native ASCII/Latin1 String <, <=, >, >= (including >= 0x80 unsigned code units & UTF-16 fallback)
  const strPairs = [
    ["apple", "banana", true],
    ["apple", "apple", false],
    ["apple", "applepie", true],
    ["applepie", "apple", false],
    ["", "a", true],
    ["a", "", false],
    ["\x7f", "\x80", true], // unsigned Latin1 0x7f < 0x80!
    ["\xff", "\x80", false],
    ["abc\u0100", "abc\u00ff", false], // wide UTF-16 fallback
    ["abc\u00ff", "abc\u0100", true],
  ];
  for (const [s1, s2, ltExpected] of strPairs) {
    assertEq(s1 < s2, ltExpected, "str lt " + s1.length + ":" + s2.length);
    assertEq(s2 > s1, ltExpected, "str gt");
    if (s1 !== s2) {
      assertEq(s1 <= s2, ltExpected, "str lte");
      assertEq(s2 >= s1, ltExpected, "str gte");
    } else {
      assertEq(s1 <= s2, true, "str eq lte");
      assertEq(s1 >= s2, true, "str eq gte");
    }
  }

  // 7i. Inline Array.prototype.pop & JS_CFUNC_f_f / f_f_f
  const popArr = [10, { v: 20 }, 30];
  assertEq(popArr.pop(), 30, "pop int");
  assertEq(popArr.pop().v, 20, "pop obj");
  assertEq(popArr.pop(), 10, "pop first");
  assertEq(popArr.pop(), undefined, "pop empty");
  assertEq(popArr.length, 0, "pop empty length");

  const holeyPop = [1, , 3];
  assertEq(holeyPop.pop(), 3, "pop before hole");
  assertEq(holeyPop.pop(), undefined, "pop hole fallback");
  assertEq(holeyPop.length, 1, "pop hole length");

  let mathAcc = 0;
  for (let i = 1; i <= 20; i++) {
    mathAcc += Math.sqrt(i * i) + Math.pow(2, 3);
  }
  assertEq(mathAcc, 210 + 160, "Math.sqrt (f_f) + Math.pow (f_f_f)");
})();

// 8. R89v5: inline dense for..of + arr[i++] + while (--n >= 0)
(function testR89v5Extensions() {
  // 8a. Dense array for..of (ints, objects, mutation mid-iteration, custom iterator fallback)
  const nums = [];
  const objs = [];
  for (let i = 1; i <= 50; i++) {
    nums.push(i);
    objs.push({ v: i });
  }
  let s1 = 0,
    s2 = 0;
  for (let k = 0; k < 10; k++) {
    for (const x of nums) s1 += x;
    for (const o of objs) s2 += o.v; // exercises preserved x27 IC inside for..of!
  }
  assertEq(s1, 12750, "for..of dense ints");
  assertEq(s2, 12750, "for..of dense objs + IC");

  // Shrinking array mid-iteration stops cleanly
  const mutArr = [10, 20, 30, 40, 50];
  const seen = [];
  for (const x of mutArr) {
    seen.push(x);
    if (x === 20) mutArr.length = 3;
  }
  assertEq(seen.join(","), "10,20,30", "for..of mid-shrink");

  // Custom iterable fallback
  const customIter = {
    [Symbol.iterator]() {
      let step = 0;
      return {
        next() {
          step++;
          return step <= 3 ? { value: step * 7, done: false } : { value: undefined, done: true };
        },
      };
    },
  };
  let cSum = 0;
  for (const x of customIter) cSum += x;
  assertEq(cSum, 42, "for..of custom iterator");

  // 8b. Borrowed arr[i++] (arg & loc) + while (--n >= 0) (arg5 & loc)
  function cryptoKernel(i, x, w, j, c, n) {
    var a = this;
    var b = w;
    while (--n >= 0) {
      var l = a[i] & 0x3fff;
      var h = a[i++] >> 2;
      c = c + l + h + b[j++];
    }
    return c;
  }
  const srcA = [100, 200, 300, 400, 500];
  const srcB = [1, 2, 3, 4, 5];
  assertEq(
    cryptoKernel.call(srcA, 0, 0, srcB, 0, 10, 5),
    10 + 1500 + (25 + 50 + 75 + 100 + 125) + 15,
    "crypto am3 kernel",
  );
  assertEq(cryptoKernel.call(srcA, 0, 0, srcB, 0, 99, 0), 99, "while (--n >= 0) zero-trip");

  function localPredec(arr) {
    let i = arr.length;
    let acc = 0;
    while (--i >= 0) {
      acc += arr[i];
    }
    let p = 0;
    while (p < arr.length) {
      acc += arr[p++];
    }
    return acc;
  }
  assertEq(localPredec([3, 6, 9, 12]), 60, "local while(--i>=0) + arr[p++]");

  // 8c. JS_CFUNC_f_f / JS_CFUNC_f_f_f with valueOf objects, strings, and under-arg calls
  function BoxedNum(v) {
    this.v = v;
  }
  BoxedNum.prototype.valueOf = function () {
    return this.v;
  };
  function geomMean(items) {
    let logSum = 0;
    for (let i = 0; i < items.length; i++) {
      logSum += Math.log(items[i]);
    }
    return Math.round(Math.pow(Math.E, logSum / items.length));
  }
  assertEq(geomMean([new BoxedNum(100), new BoxedNum(400)]), 200, "Math.log on valueOf objects");
  assertEq(Math.pow(new BoxedNum(3), new BoxedNum(4)), 81, "Math.pow on valueOf objects");
  assertEq(Math.floor("42.9"), 42, "Math.floor on string");
  assertEq(Number.isNaN(Math.floor()), true, "Math.floor 0 args");
  assertEq(Number.isNaN(Math.pow(2)), true, "Math.pow 1 arg");

  // 9. R89v6 fast paths & edge cases
  // 9a. Borrowed .a.b.c + null-branch + truthiness-branch + undefined vs null
  function checkChain(o) {
    let hits = 0;
    if (o.a.b === null) hits += 1;
    if (o.a.b == null) hits += 2;
    if (o.a.b !== null) hits += 4;
    if (o.a.b != null) hits += 8;
    if (o.a.c) hits += 16;
    if (!o.a.c) hits += 32;
    return hits;
  }
  const chNull = { a: { b: null, c: 1 } };
  const chUndef = { a: { b: undefined, c: 0 } };
  const chVal = { a: { b: 7, c: { k: 1 } } };
  for (let i = 0; i < 60; i++) {
    assertEq(checkChain(chNull), 1 + 2 + 16, "borrow chain null");
    assertEq(checkChain(chUndef), 2 + 4 + 32, "borrow chain undef");
    assertEq(checkChain(chVal), 4 + 8 + 16, "borrow chain obj");
  }

  // 9b. push_this prologue fusion & get_var + get_field borrow
  function BoxC(x) {
    this.x = x;
    this.arr = [x, x + 1, x + 2];
  }
  BoxC.prototype.at = function (i) {
    return this.arr[i];
  };
  BoxC.prototype.size = function () {
    return this.arr.length;
  };
  BoxC.prototype.popHead = function () {
    return this.arr.shift();
  };
  BoxC.prototype.tailAt = function (i) {
    return this.at(i);
  };
  function boxReadThis(b) {
    return function () {
      if (this.x === null) return -1;
      return this.x + b;
    };
  }
  const bx = new BoxC(10);
  bx.fn = boxReadThis(5);
  let msum = 0;
  for (let i = 0; i < 120; i++) {
    msum += bx.at(1) + bx.size() + bx.tailAt(2) + bx.fn() + Math.floor(3.9);
  }
  assertEq(msum, 120 * (11 + 3 + 12 + 15 + 3), "methods/tail_call/leaves/get_var");
  assertEq(bx.at(99), undefined, "at11 oob decline");

  // 9c. In-VM leaves (len=4 ops + overflow, len=14 strength, sort/map callbacks)
  function cmpStronger(a, b) {
    return a.s > b.s;
  }
  function cmpWeaker(a, b) {
    return a.s < b.s;
  }
  function subFn(a, b) {
    return a - b;
  }
  function shrFn(a, b) {
    return a >>> b;
  }
  const sa = { s: 10 },
    sb = { s: 4, extra: 1 };
  let lsum = 0;
  for (let i = 0; i < 80; i++) {
    if (cmpStronger(sa, sb) && !cmpWeaker(sa, sb)) lsum++;
    lsum += subFn(20, 5) + shrFn(32, 2);
  }
  assertEq(lsum, 80 * (1 + 15 + 8), "in-VM leaves");
  assertEq(subFn(0x7fffffff, -1), 2147483648, "len4 sub overflow");
  assertEq(shrFn(-1, 0), 4294967295, "len4 shr uint32");
  const unsorted = [5, 1, 9, 2, 7, 3, 8, 4, 6];
  unsorted.sort((a, b) => a - b);
  assertEq(unsorted.join(","), "1,2,3,4,5,6,7,8,9", "sort comparator leaf");
  assertEq([1, 2, 3].map((x) => x + 10).join(","), "11,12,13", "map leaf");

  // 9d. Immediate ALU + store, ALU + store (TDZ/overflow/refcount), post_inc/dec + store, lnot + branch
  function aluSuite(a, b) {
    let c = 0;
    let x = a + b;
    let y = (x & 0x3fff) >> 1;
    c += (y | 1) ^ 3;
    let i = 0;
    while (i < 5) {
      c += [10, 20, 30, 40, 50][i++];
    }
    let flag = !(i === 5);
    if (!flag) c += 1;
    return c;
  }
  let as = 0;
  for (let i = 0; i < 80; i++) as += aluSuite(100, 200);
  assertEq(as, 80 * (((((300 & 0x3fff) >> 1) | 1) ^ 3) + 150 + 1), "alu + postinc + lnot fuse");
  function addOverflowToFloat(a, b) {
    let r = a + b;
    return r;
  }
  assertEq(addOverflowToFloat(0x7fffffff, 1), 2147483648, "add store float overflow");
  function pushShrLarge(x) {
    return x >>> 0;
  }
  for (let i = 0; i < 30; i++) {
    assertEq(pushShrLarge(-1), 4294967295, "push_int shr uint32");
  }

  // 9e. JS_CLASS_OBJECT numeric own props, sparse arrays, RESIZE transition, array_from, virtual arguments
  function am3Like(src, srcIdx, dst, dstIdx, len) {
    while (--len >= 0) {
      const w = src[srcIdx++];
      dst[dstIdx++] = (w & 0x3fff) + (w >> 14);
    }
  }
  const objSrc = { 0: 0x10001, 1: 0x20002, 2: 0x30003, 3: 0x40004 };
  const objDst = { 0: 0, 1: 0, 2: 0, 3: 0 };
  const sparseArr = [1, 2, 3, 4];
  delete sparseArr[1];
  sparseArr[1] = 20;
  for (let i = 0; i < 60; i++) {
    am3Like(objSrc, 0, objDst, 0, 4);
    assertEq(objDst[0] + objDst[3], 5 + 20, "JS_CLASS_OBJECT am3 borrow");
    assertEq(sparseArr[1], 20, "fast_array == 0 borrow/own");
  }
  function buildManyProps(k) {
    const o = {};
    o.p0 = k;
    o.p1 = k;
    o.p2 = k;
    o.p3 = k;
    o.p4 = k;
    o.p5 = k;
    o.p6 = k;
    o.p7 = k;
    o.p8 = k;
    o.p9 = k;
    o.p10 = k;
    return [o.p0, o.p9, o.p10];
  }
  for (let i = 0; i < 60; i++) {
    const pair = buildManyProps(i);
    assertEq(pair[0] + pair[2], 2 * i, "IC resize + array_from");
  }

  const Kls = function () {
    this.init.apply(this, arguments);
  };
  Kls.prototype = {
    init(a, b) {
      this.val = a * 10 + b;
    },
  };
  let ksum = 0;
  for (let i = 0; i < 80; i++) {
    if (i === 40) {
      Kls.prototype.init = function (a, b) {
        this.val = a + b;
      };
    }
    ksum += new Kls(3, 4).val;
  }
  assertEq(ksum, 40 * 34 + 40 * 7, "virtual args cache + epoch invalidation");
})();

// 10. R89v7 fastpaths: O(1) indexed direct/reverse, FAST_CALL_READY, len6/8/30 leaves,
//     get_field2 + 2-arg method fusion, JS_FastConstructCall Tier1/Tier2, Math.*, .call() leaves
(function testR89v7FastPaths() {
  // 10a. O(1) own-indexed direct (0..n-1) and reverse (n-1..0) slot order + delete fallback
  const dirObj = { 0: 10, 1: 20, 2: 30, 3: 40 };
  const revObj = {};
  revObj[3] = 400;
  revObj[2] = 300;
  revObj[1] = 200;
  revObj[0] = 100;
  for (let i = 0; i < 60; i++) {
    let s1 = 0,
      s2 = 0;
    for (let k = 0; k < 4; k++) {
      s1 += dirObj[k];
      s2 += revObj[k];
      dirObj[k] = dirObj[k] + 1;
      revObj[k] = revObj[k] + 1;
    }
    assertEq(s1, 100 + 4 * i, "O(1) direct indexed own");
    assertEq(s2, 1000 + 4 * i, "O(1) reverse indexed own");
  }
  delete revObj[1];
  assertEq(revObj[1], undefined, "deleted reverse indexed property");
  assertEq(revObj[0], 160, "remaining direct/reverse indexed property");

  // 10b. FAST_CALL_READY: var_count=0,1,2,4, exact/over/under arity, recursion
  function v0(a, b) {
    return a + b + 1;
  }
  function v1(a) {
    const x = a + 2;
    return x;
  }
  function v2(a, b) {
    const x = a + 1;
    const y = b + 2;
    return x + y;
  }
  function v4(a, b) {
    const p = a + 1,
      q = b + 2,
      r = p + q,
      s = r * 2;
    return s;
  }
  function underArity(a, b) {
    const x = a || 10;
    const y = b || 20;
    return x + y;
  }
  function fib(n) {
    return n <= 1 ? n : fib(n - 1) + fib(n - 2);
  }
  for (let i = 0; i < 40; i++) {
    assertEq(v0(i, 3), i + 4, "FAST_CALL_READY var_count=0");
    assertEq(v1(i), i + 2, "FAST_CALL_READY var_count=1");
    assertEq(v2(i, 5), i + 8, "FAST_CALL_READY var_count=2");
    assertEq(v4(i, 3), 2 * (i + 6), "FAST_CALL_READY var_count=4");
    assertEq(underArity(7), 27, "FAST_CALL_READY under-arity fallback");
  }
  assertEq(fib(12), 144, "FAST_CALL_READY recursive fib");

  // 10c. In-VM leaves: len=6 (a op b)|0, len=8 (a+b+c)|0, len=30 3-char ASCII predicate
  function add32(a, b) {
    return (a + b) | 0;
  }
  function sub32(a, b) {
    return (a - b) | 0;
  }
  function mul32(a, b) {
    return (a * b) | 0;
  }
  function shl32(a, b) {
    return (a << b) | 0;
  }
  function shr32(a, b) {
    return (a >>> b) | 0;
  }
  function sar32(a, b) {
    return (a >> b) | 0;
  }
  function and32(a, b) {
    return (a & b) | 0;
  }
  function xor32(a, b) {
    return (a ^ b) | 0;
  }
  function or32(a, b) {
    return a | b | 0;
  }
  function add3_i32(a, b) {
    return (a + b + 3) | 0;
  }
  function isSpace3(c) {
    return c == " " || c == "\t" || c == "\n";
  }
  for (let i = 0; i < 60; i++) {
    assertEq(add32(0x7fffffff, 1), -2147483648, "len6 add32");
    assertEq(sub32(10, 25), -15, "len6 sub32");
    assertEq(mul32(300, 400), 120000, "len6 mul32");
    assertEq(shl32(3, 4), 48, "len6 shl32");
    assertEq(shr32(-1, 1), 2147483647, "len6 shr32");
    assertEq(sar32(-8, 2), -2, "len6 sar32");
    assertEq(and32(0xf3, 0x35), 0x31, "len6 and32");
    assertEq(xor32(0xaa, 0xff), 0x55, "len6 xor32");
    assertEq(or32(0x10, 0x05), 0x15, "len6 or32");
    assertEq(add3_i32(i, 10), i + 13, "len8 (a+b+3)|0");
    assertEq(isSpace3(" "), true, "len30 space");
    assertEq(isSpace3("\t"), true, "len30 tab");
    assertEq(isSpace3("\n"), true, "len30 nl");
    assertEq(isSpace3("a"), false, "len30 nonspace");
  }

  // 10d. OP_get_field2 local/arg borrow + 2-arg method fusion
  const svc = {
    scale: 3,
    combine(a, b) {
      return this.scale * a + b;
    },
    fwdCombine(a, b) {
      return this.combine(a + 1, b + 2);
    },
  };
  const box = {
    v: {
      m(x, y) {
        return x * 100 + y;
      },
    },
  };
  function gf2Arg(o, x, y) {
    return o.m(x, y);
  }
  for (let i = 0; i < 60; i++) {
    const ref = svc;
    assertEq(ref.combine(i, 7), 3 * i + 7, "gf2 local borrow 2-arg");
    assertEq(ref.fwdCombine(i, 5), 3 * (i + 1) + 7, "gf2 tail_call_method 2-arg");
    assertEq(gf2Arg(box.v, 4, i), 400 + i, "gf2 arg borrow 2-arg");
  }

  // 10e. JS_FastConstructCall Tier 1 / Tier 2 + ES6 class + invalidation
  function CtorEmpty() {}
  function CtorP2(x, y) {
    this.x = x;
    this.y = y;
  }
  function CtorNode(k, v) {
    this.k = k;
    this.v = v;
    this.left = null;
    this.tag = "nd";
  }
  class ClassP2 {
    constructor(a, b) {
      this.a = a;
      this.b = b;
    }
  }
  function CtorTier2(n) {
    this.sum = 0;
    for (let j = 0; j < 3; j++) this.sum += n + j;
  }
  let setterCalls = 0;
  for (let i = 0; i < 100; i++) {
    const e = new CtorEmpty();
    assertEq(Object.getPrototypeOf(e), CtorEmpty.prototype, "ctor empty proto");
    if (i === 50) {
      Object.defineProperty(CtorP2.prototype, "y", {
        set(val) {
          setterCalls += val;
        },
        configurable: true,
      });
    }
    const p = new CtorP2(i, 3);
    if (i < 50) {
      assertEq(p.x + p.y, i + 3, "ctor Tier 1 P2 before setter");
    } else {
      assertEq(Object.hasOwn(p, "y"), false, "ctor P2 prototype setter invalidation");
    }
    if (i === 50) {
      CtorNode.prototype = { protoTag: 99 };
    }
    const nd = new CtorNode(i, "x");
    assertEq(nd.k, i, "ctor Node.k");
    assertEq(nd.left, null, "ctor Node.left");
    assertEq(nd.tag, "nd", "ctor Node.tag const");
    assertEq(nd.protoTag, i >= 50 ? 99 : undefined, "ctor Tier 1 proto swap invalidation");
    const c = new ClassP2(i, 9);
    assertEq(c.a + c.b, i + 9, "ctor Tier 1 ES6 class");
    if (i === 50) {
      CtorTier2.prototype = { tag2: 77 };
    }
    const t2 = new CtorTier2(i);
    assertEq(t2.sum, 3 * i + 3, "ctor Tier 2 loop sum");
    assertEq(t2.tag2, i >= 50 ? 77 : undefined, "ctor Tier 2 proto swap");
  }
  assertEq(setterCalls, 50 * 3, "ctor setter call count after epoch invalidation");

  // 10f. Inline Math.* (f_f & f_f_f): int32, -0.0, NaN, INT32_MIN, pow, atan2, string coercion, tail
  function tailAbs(x) {
    return Math.abs(x);
  }
  for (let i = 0; i < 60; i++) {
    assertEq(Math.sqrt(9), 3, "Math.sqrt exact int32");
    assertEq(Math.sqrt(2) > 1.41 && Math.sqrt(2) < 1.42, true, "Math.sqrt float64");
    assertEq(Math.sqrt(-1), NaN, "Math.sqrt NaN");
    assertEq(Math.abs(-0), 0, "Math.abs(-0) === +0");
    assertEq(Math.floor(-0), -0, "Math.floor(-0) preserves -0");
    assertEq(Math.ceil(-0.5), -0, "Math.ceil(-0.5) preserves -0");
    assertEq(Math.trunc(-2147483648.9), -2147483648, "Math.trunc INT32_MIN int32");
    assertEq(Math.pow(2, 10), 1024, "Math.pow(2, 10)");
    assertEq(Math.atan2(0, -1), Math.PI, "Math.atan2");
    assertEq(Math.abs("-4.5"), 4.5, "Math.abs string coercion fallback");
    assertEq(tailAbs(-42), 42, "tail Math.abs");
  }

  // 10g. Function.prototype.call leaves (len=1,2,4,9,10, tail) + non-leaf Error().stack
  function cfUndef() {
    return;
  }
  function cfConst() {
    return 7;
  }
  function cfArg(a, b) {
    return b;
  }
  function cfAdd(a, b) {
    return a + b;
  }
  function cfSub(a, b) {
    return a - 2;
  }
  function cfField() {
    return this.val;
  }
  function cfArrLen() {
    return this.items.length;
  }
  function cfTail(a, b) {
    return cfAdd.call(null, a, b);
  }
  function cfStackNonLeaf() {
    let s = "";
    for (let k = 0; k < 2; k++) s = new Error("stk").stack;
    return s;
  }
  const callRecv = { val: 55, items: [1, 2, 3, 4] };
  for (let i = 0; i < 60; i++) {
    assertEq(cfUndef.call(callRecv), undefined, ".call len1 undef");
    assertEq(cfConst.call(null), 7, ".call len2 const");
    assertEq(cfArg.call(null, 10, i), i, ".call len2 arg1");
    assertEq(cfAdd.call(null, i, 4), i + 4, ".call len4 add");
    assertEq(cfSub.call(null, i + 10, 99), i + 8, ".call len4 sub imm");
    assertEq(cfField.call(callRecv), 55, ".call len9 this.field");
    assertEq(cfArrLen.call(callRecv), 4, ".call len10 this.arr.length");
    assertEq(cfTail.call(null, i, 6), i + 6, ".call tail leaf");
    const st = cfStackNonLeaf.call(callRecv);
    assertEq(st.indexOf("cfStackNonLeaf") >= 0, true, ".call non-leaf preserves stack");
  }

  // 11. R89v8 comprehensive fastpath & edge-case tests
  // 11a. Object.create(null) property read/write
  const nullObj = Object.create(null);
  nullObj.x = 1;
  nullObj.y = "a";
  for (let i = 0; i < 60; i++) {
    nullObj.x = (nullObj.x + i) | 0;
    assertEq(nullObj.x > 0, true, "Object.create(null) replace");
    assertEq(nullObj.missing, undefined, "Object.create(null) missing");
  }

  // 11b. Array.prototype.sort comparators (a - b, a.x - b.x, compound22 compareTo)
  const numArr = [5, 1, 9, 2, 8, 3, 7, 4, 6, 0];
  for (let i = 0; i < 40; i++) {
    const s = numArr.slice().sort((a, b) => a - b);
    assertEq(s.join(","), "0,1,2,3,4,5,6,7,8,9", "sort a-b");
    const objs = [{ x: 4 }, { x: 1 }, { x: 3 }, { x: 2 }];
    objs.sort((a, b) => a.x - b.x);
    assertEq(objs.map((o) => o.x).join(","), "1,2,3,4", "sort a.x-b.x");
  }

  function WrapStr(s) {
    this._v = s;
  }
  WrapStr.prototype.compareTo = function (o) {
    return this._v.localeCompare(o._v);
  };
  const cmpCall = (a, b) => a.compareTo(b);
  const wrapArr = [
    new WrapStr("delta"),
    new WrapStr("alpha"),
    new WrapStr("charlie"),
    new WrapStr("bravo"),
  ];
  for (let i = 0; i < 60; i++) {
    assertEq(cmpCall(wrapArr[0], wrapArr[1]) > 0, true, "compound22 gt");
    assertEq(cmpCall(wrapArr[1], wrapArr[1]), 0, "compound22 eq");
    assertEq(wrapArr[1].compareTo(wrapArr[2]) < 0, true, "compound22 direct lt");
    const ws = wrapArr.slice().sort((a, b) => a.compareTo(b));
    assertEq(ws.map((w) => w._v).join(","), "alpha,bravo,charlie,delta", "sort compound22");
  }

  // 11c. Array.prototype.push (1-arg, resize boundary, prototype setter, non-writable length, self-push)
  const pa = [];
  for (let i = 0; i < 64; i++) assertEq(pa.push(i), i + 1, "push return length");
  assertEq(pa.length, 64, "push resized length");
  assertEq(pa[63], 63, "push last element");
  const selfPush = [1];
  assertEq(selfPush.push(selfPush), 2, "self-push");
  assertEq(selfPush[1], selfPush, "self-push value");
  selfPush.length = 0;

  let protoPushSetterHits = 0;
  const protoSetArr = [];
  Object.defineProperty(Array.prototype, "9", {
    set(v) {
      protoPushSetterHits += v;
    },
    configurable: true,
  });
  try {
    for (let i = 0; i < 12; i++) protoSetArr.push(i);
    assertEq(protoPushSetterHits, 9, "push respects prototype index setter");
  } finally {
    delete Array.prototype[9];
  }

  const nonWrLen = [1, 2];
  Object.defineProperty(nonWrLen, "length", { writable: false });
  let threwNonWr = false;
  try {
    nonWrLen.push(3);
  } catch (e) {
    threwNonWr = e instanceof TypeError;
  }
  assertEq(threwNonWr, true, "push non-writable length throws TypeError");

  // 11d. String charCodeAt, codePointAt, localeCompare
  const sLatin = "Hello";
  const sWide = "A\u03b1\ud83d\ude00B";
  for (let i = 0; i < 60; i++) {
    assertEq(sLatin.charCodeAt(1), 101, "charCodeAt Latin1");
    assertEq(sLatin.charCodeAt(99), NaN, "charCodeAt OOB NaN");
    assertEq(sLatin.codePointAt(99), undefined, "codePointAt OOB undef");
    assertEq(sWide.charCodeAt(1), 0x03b1, "charCodeAt UTF-16 BMP");
    assertEq(sWide.codePointAt(2), 0x1f600, "codePointAt surrogate pair");
    assertEq("abc".localeCompare("abc"), 0, "localeCompare eq");
    assertEq("abc".localeCompare("abcd") < 0, true, "localeCompare prefix lt");
    assertEq("abd".localeCompare("abc") > 0, true, "localeCompare gt");
    assertEq("\u00e9".localeCompare("e") !== 0, true, "localeCompare wide fallback");
  }

  // 11e. OrderedCollection add/removeFirst + empty removeFirst
  function OrdCol() {
    this.el = [];
  }
  OrdCol.prototype.add = function (x) {
    this.el.push(x);
  };
  OrdCol.prototype.removeFirst = function () {
    return this.el.pop();
  };
  const oc = new OrdCol();
  for (let i = 0; i < 60; i++) {
    oc.add(i);
    oc.add(i + 100);
    assertEq(oc.removeFirst(), i + 100, "OrdCol removeFirst non-empty");
    assertEq(oc.removeFirst(), i, "OrdCol removeFirst second");
    assertEq(oc.removeFirst(), undefined, "OrdCol removeFirst empty");
  }

  // 11f. TypedArray.length, DataView.byteLength, ArrayBuffer.byteLength
  const ab = new ArrayBuffer(32);
  const dv = new DataView(ab, 4, 16);
  const tas = [
    new Int8Array(ab),
    new Uint8Array(ab),
    new Uint8ClampedArray(ab),
    new Int16Array(ab),
    new Uint16Array(ab),
    new Int32Array(ab),
    new Uint32Array(ab),
    new Float32Array(ab),
    new Float64Array(ab),
  ];
  for (let iter = 0; iter < 50; iter++) {
    assertEq(ab.byteLength, 32, "ArrayBuffer byteLength");
    assertEq(dv.byteLength, 16, "DataView byteLength");
    for (let j = 0; j < tas.length; j++) {
      const expectedLen = 32 / tas[j].BYTES_PER_ELEMENT;
      assertEq(tas[j].length, expectedLen, "TypedArray length");
      assertEq(tas[j].byteLength, 32, "TypedArray byteLength");
    }
  }
  const u8ov = new Uint8Array(10);
  const origTaLenDesc = Object.getOwnPropertyDescriptor(
    Object.getPrototypeOf(Uint8Array.prototype),
    "length",
  );
  Object.defineProperty(Object.getPrototypeOf(Uint8Array.prototype), "length", {
    get() {
      return 777;
    },
    configurable: true,
  });
  try {
    for (let i = 0; i < 10; i++) assertEq(u8ov.length, 777, "TypedArray.length override");
  } finally {
    Object.defineProperty(Object.getPrototypeOf(Uint8Array.prototype), "length", origTaLenDesc);
  }

  const abDet = new ArrayBuffer(16);
  const dvDet = new DataView(abDet);
  for (let i = 0; i < 40; i++) assertEq(dvDet.byteLength, 16, "DataView warm before detach");
  abDet.transfer(0);
  let dvOobThrew = false;
  try {
    void dvDet.byteLength;
  } catch (e) {
    dvOobThrew = e instanceof TypeError;
  }
  assertEq(dvOobThrew, true, "detached DataView.byteLength throws TypeError");

  // 11g. ES6 prototype getters (Kinds 1..4) + invalidation
  class GetterBox {
    constructor(v) {
      this._v = v;
      this._arr = [1, 2, 3];
      this._nested = { k: v + 10 };
    }
    get val() {
      return this._v;
    }
    get len() {
      return this._arr.length;
    }
    get nestedK() {
      return this._nested.k;
    }
    get tag() {
      return 42;
    }
  }
  const gb = new GetterBox(5);
  for (let i = 0; i < 50; i++) {
    assertEq(gb.val, 5, "ES6 getter this.field");
    assertEq(gb.len, 3, "ES6 getter this.arr.length");
    assertEq(gb.nestedK, 15, "ES6 getter this.a.b");
    assertEq(gb.tag, 42, "ES6 getter const");
  }
  Object.defineProperty(GetterBox.prototype, "val", {
    get() {
      return this._v + 100;
    },
    configurable: true,
  });
  assertEq(gb.val, 105, "ES6 getter invalidated after defineProperty");

  // 11h. Float64 bitwise ToInt32 >= 2^52, negative, NaN, +-Infinity
  const bigCases = [
    [4503599627370497, 1],
    [-4503599627370497, -1],
    [9007199254740998, 6],
    [1e30, 0],
    [NaN, 0],
    [Infinity, 0],
    [-Infinity, 0],
  ];
  for (let i = 0; i < 50; i++) {
    for (const [val, exp] of bigCases) {
      assertEq(val | 0, exp, "Float64 | 0");
      assertEq(0 | val, exp, "0 | Float64");
      assertEq(val ^ 0, exp, "Float64 ^ 0");
      assertEq(val & -1, exp, "Float64 & -1");
      assertEq(val << 0, exp, "Float64 << 0");
      assertEq(val >> 0, exp, "Float64 >> 0");
      assertEq(val >>> 0, exp >>> 0, "Float64 >>> 0");
    }
  }

  // 11i. typeof + rot3r + get_loc0..3 + 1B val + put_field
  function testTypesAndStores(flag) {
    assertEq(typeof undefined, "undefined", "typeof undefined");
    assertEq(typeof null, "object", "typeof null");
    assertEq(typeof true, "boolean", "typeof boolean");
    assertEq(typeof 42, "number", "typeof int");
    assertEq(typeof 3.5, "number", "typeof float64");
    assertEq(typeof 10n, "bigint", "typeof short bigint");
    assertEq(typeof (1n << 100n), "bigint", "typeof heap bigint");
    assertEq(typeof "hi", "string", "typeof string");
    assertEq(typeof ("a" + "b".repeat(20) + "c"), "string", "typeof rope");
    assertEq(typeof Symbol("s"), "symbol", "typeof symbol");
    assertEq(typeof {}, "object", "typeof object");
    assertEq(typeof [], "object", "typeof array");
    assertEq(typeof /a/, "object", "typeof regexp");
    assertEq(typeof testTypesAndStores, "function", "typeof bytecode function");
    assertEq(typeof Math.abs, "function", "typeof c function");
    assertEq(typeof testTypesAndStores.bind(null), "function", "typeof bound function");

    const p = { a: 0, b: null, self: null };
    p.a = 7;
    p.b = flag ? undefined : true;
    p.self = p;
    p.self = p;
    assertEq(p.a, 7, "1B put_field int");
    assertEq(p.b, flag ? undefined : true, "1B put_field bool/undef");
    assertEq(p.self, p, "1B put_field self-assign");

    const arrRot = [10, 20, 30];
    let idxRot = 1;
    arrRot[idxRot] += 5;
    assertEq(arrRot[1], 25, "rot3r compound assign");
  }
  for (let i = 0; i < 60; i++) testTypesAndStores((i & 1) === 0);

  // ---- 12. R89v9: null-proto calls, inline props, non-fast array, push_int+ALU, am3 loop, compound leaves, this.a=this.b.c, isNull, generator for-of ----
  (function testR89v9() {
    // 12a. Multi-call { __proto__: null } with locals & args
    const npObj = {
      __proto__: null,
      calc(a, b, c) {
        let s = this.base + a;
        let t = b * 2 - c;
        return s + t;
      },
      base: 10,
    };
    let npSum = 0;
    for (let i = 0; i < 240; i++) {
      npSum += npObj.calc(i & 7, (i & 3) + 1, i & 1);
      npSum += npObj.calc.call({ __proto__: null, base: 5 }, i & 3); // NaN? No, handle defined args:
      npSum += npObj.calc.call(npObj, 1, 2, 3);
    }
    assertEq(Number.isNaN(npSum), true, "null-proto call missing args NaN exact");
    let npClean = 0;
    for (let i = 0; i < 240; i++) {
      npClean += npObj.calc(i & 7, (i & 3) + 1, i & 1);
    }
    assertEq(npClean > 0, true, "null-proto multi-call hot loop");

    // 12b. Inline properties: birth, transition, resize >256B, delete, JSON, closure+props, GC
    function makePoly(n) {
      const o = {};
      for (let k = 0; k < n; k++) o["p" + k] = k * 3 + 1;
      return o;
    }
    for (let iter = 0; iter < 200; iter++) {
      const small = {};
      small.a = iter;
      small.b = iter + 1;
      small.c = small;
      delete small.b;
      small.d = small.a + 5;
      assertEq(small.c.d, iter + 5, "inline prop delete/readd");

      const big = makePoly(18);
      assertEq(big.p0 + big.p17, 1 + (17 * 3 + 1), "inline prop escape >256B");

      const parsed = JSON.parse('{"x":10,"y":{"z":"ok"},"arr":[1,2]}');
      parsed.extra = iter;
      assertEq(parsed.x + parsed.extra, 10 + iter, "inline JSON parsed grow");

      let cap = iter & 15;
      const fn = function (d) {
        return cap + d;
      };
      fn.tag = "k" + cap;
      fn.m0 = cap;
      fn.m1 = cap + 1;
      fn.m2 = cap + 2;
      assertEq(fn(3) + fn.m2, cap * 2 + 5, "inline closure tail + props");
    }
    const retain = [];
    for (let i = 0; i < 2000; i++) {
      const x = { a: i, b: i + 1, c: { d: i + 2 } };
      if ((i & 31) === 0) retain.push(x);
    }
    if (typeof gc === "function") gc();
    assertEq(retain[retain.length - 1].c.d > 0, true, "inline prop GC retained");

    // 12c. Own-indexed non-fast JS_CLASS_ARRAY + push_int+ALU + while(--n >= 0) arg loop
    const sparseArr = [10, 20, 30, 40];
    Object.defineProperty(sparseArr, "0", {
      value: 11,
      writable: true,
      enumerable: true,
      configurable: true,
    });
    function walkOwnIndexed(b, n, w, j) {
      let i = 0;
      let acc = 0;
      while (--n >= 0) {
        const lo = b[i++] & 0x3fff;
        const hi = (b[i - 1] >> 14) + ((lo >>> 1) & 0xfffffff);
        w[j++] = (lo + hi) & 0x3fff;
        acc = (acc + w[j - 1]) & 0x3fff;
      }
      return acc;
    }
    const outW = [0, 0, 0, 0];
    let ownSum = 0;
    for (let k = 0; k < 100; k++) {
      sparseArr[1] = 20000 + k;
      sparseArr[2] = 30000 + k;
      sparseArr[3] = 40000 + k;
      ownSum = walkOwnIndexed(sparseArr, 4, outW, 0);
    }
    assertEq(
      ownSum,
      (outW[0] + outW[1] + outW[2] + outW[3]) & 0x3fff,
      "own-indexed non-fast array + ALU + while(--n>=0)",
    );

    function edgeShift(a, b) {
      const u0 = a >>> 0;
      const u1 = b >>> 1;
      const ovf = -2147483648 - 1;
      return [u0, u1, ovf];
    }
    const es0 = edgeShift(-1, -1);
    const es1 = edgeShift(0x80000000 | 0, 7);
    assertEq(es0[0], 4294967295, "push_int shr uint32 bit31 fallback (-1>>>0)");
    assertEq(es0[1], 2147483647, "push_int shr (-1>>>1)");
    assertEq(es0[2], -2147483649, "push_int sub overflow");
    assertEq(es1[0], 2147483648, "push_int shr (int32min>>>0)");
    assertEq(es1[1], 3, "push_int shr (7>>>1)");

    function decEdge(a, b, c, d, n) {
      let hits = 0;
      while (--n >= 0) hits++;
      return [hits, n];
    }
    assertEq(decEdge(0, 0, 0, 0, 5)[0], 5, "am3 loop n=5");
    assertEq(decEdge(0, 0, 0, 0, 0)[1], -1, "am3 loop n=0");
    assertEq(decEdge(0, 0, 0, 0, -3)[0], 0, "am3 loop n=-3");

    // 12d. Compound leaves: sc_isPair, markAs*, isHeldOrSuspended, isSatisfied, input/output
    globalThis.__r89v9_Pair = function Pair(a, b) {
      this.car = a;
      this.cdr = b;
    };
    function sc_isPair_test(p) {
      return p instanceof __r89v9_Pair;
    }
    const pairObj = new __r89v9_Pair(1, 2);
    for (let i = 0; i < 100; i++) {
      assertEq(sc_isPair_test(pairObj), true, "sc_isPair true");
      assertEq(sc_isPair_test(null), false, "sc_isPair null");
      assertEq(sc_isPair_test(42), false, "sc_isPair int");
      assertEq(sc_isPair_test({}), false, "sc_isPair plain obj");
    }
    const savedProto = __r89v9_Pair.prototype;
    __r89v9_Pair.prototype = {};
    assertEq(sc_isPair_test(pairObj), false, "sc_isPair prototype swap invalidates");
    __r89v9_Pair.prototype = savedProto;
    Object.defineProperty(__r89v9_Pair, Symbol.hasInstance, {
      configurable: true,
      value: () => true,
    });
    assertEq(sc_isPair_test(123), true, "sc_isPair Symbol.hasInstance override");
    delete __r89v9_Pair[Symbol.hasInstance];

    globalThis.__r89v9_HELD = 4;
    globalThis.__r89v9_NOT_HELD = ~4;
    globalThis.__r89v9_SUSP = 2;
    globalThis.__r89v9_DIR = { NONE: 0, FWD: 1, BWD: -1 };
    function Tcb(st) {
      this.state = st;
    }
    Tcb.prototype.markAsHeld2 = function () {
      this.state = this.state | __r89v9_HELD;
    };
    Tcb.prototype.markAsNotHeld = function () {
      this.state = this.state & __r89v9_NOT_HELD;
    };
    Tcb.prototype.isHeldOrSuspended = function () {
      return (this.state & __r89v9_HELD) != 0 || this.state == __r89v9_SUSP;
    };
    function BC(d, v1, v2) {
      this.direction = d;
      this.v1 = v1;
      this.v2 = v2;
    }
    BC.prototype.isSatisfied = function () {
      return this.direction != __r89v9_DIR.NONE;
    };
    BC.prototype.input = function () {
      return this.direction == __r89v9_DIR.FWD ? this.v1 : this.v2;
    };
    BC.prototype.output = function () {
      return this.direction == __r89v9_DIR.FWD ? this.v2 : this.v1;
    };

    const tcb = new Tcb(0);
    const bcF = new BC(1, "V1", "V2");
    const bcB = new BC(-1, "V1", "V2");
    const bcN = new BC(0, "V1", "V2");
    for (let i = 0; i < 100; i++) {
      tcb.state = 1;
      assertEq(tcb.isHeldOrSuspended(), false, "tcb not held/susp");
      tcb.markAsHeld2();
      assertEq(tcb.isHeldOrSuspended(), true, "tcb held");
      tcb.markAsNotHeld();
      assertEq(tcb.state, 1, "tcb unheld");
      tcb.state = 2;
      assertEq(tcb.isHeldOrSuspended(), true, "tcb susp");
      assertEq(bcF.isSatisfied(), true, "bc satisfied fwd");
      assertEq(bcN.isSatisfied(), false, "bc unsatisfied");
      assertEq(bcF.input(), "V1", "bc fwd input");
      assertEq(bcF.output(), "V2", "bc fwd output");
      assertEq(bcB.input(), "V2", "bc bwd input");
      assertEq(bcB.output(), "V1", "bc bwd output");
    }
    delete globalThis.__r89v9_Pair;
    delete globalThis.__r89v9_HELD;
    delete globalThis.__r89v9_NOT_HELD;
    delete globalThis.__r89v9_SUSP;
    delete globalThis.__r89v9_DIR;

    // 12e. this.a = this.b.c (normal + self-alias rc==1) & is_null/is_undefined borrow+branch
    function ChainHolder(head) {
      this.head = head;
      this.cur = head;
      this.res = null;
    }
    ChainHolder.prototype.step = function () {
      this.cur = this.cur.next;
    };
    for (let i = 0; i < 100; i++) {
      const tail = { next: null, v: i };
      const node = { next: tail, v: i - 1 };
      const ch = new ChainHolder(node);
      ch.step(); // self-alias ch.cur = ch.cur.next while node rc==1
      assertEq(ch.cur.v, i, "this.cur = this.cur.next self-alias");
    }
    function checkNullBorrow(x, y) {
      let r = 0;
      if (x === null) r += 1;
      if (x === undefined) r += 2;
      if (y == null) r += 4;
      return r;
    }
    for (let i = 0; i < 100; i++) {
      const freshObj = { k: i };
      assertEq(checkNullBorrow(freshObj, { m: 1 }), 0, "borrow is_null obj/obj");
      assertEq(checkNullBorrow(null, undefined), 5, "borrow is_null null/undef");
      assertEq(checkNullBorrow(undefined, null), 6, "borrow is_null undef/null");
    }

    // 12f. Generator for-of (yield, yield*, break/finally, throw/catch)
    let finCount = 0;
    function* innerGen(n) {
      for (let i = 1; i <= n; i++) yield i;
    }
    function* outerGen(n, throwAt) {
      try {
        yield* innerGen(n);
        if (throwAt) throw new Error("boom");
        yield 99;
      } finally {
        finCount++;
      }
    }
    let genTotal = 0;
    for (let r = 0; r < 100; r++) {
      for (const x of outerGen(4, false)) genTotal += x;
    }
    assertEq(genTotal, 100 * (1 + 2 + 3 + 4 + 99), "generator for-of hot loop");
    assertEq(finCount, 100, "generator finally normal");

    for (const x of outerGen(10, false)) {
      if (x === 2) break;
    }
    assertEq(finCount, 101, "generator for-of break triggers finally");

    let caught = "";
    try {
      for (const x of outerGen(2, true)) {
        genTotal += x;
      }
    } catch (e) {
      caught = e.message;
    }
    assertEq(caught, "boom", "generator for-of throw caught");
    assertEq(finCount, 102, "generator for-of throw triggers finally");

    // 13. R89v10 regressions & fast paths
    // 13a. declareName OP_insert2 + OP_put_field regression + 1B/2B loc/arg.field = val
    function declareNameRepro(arg0) {
      let loc0 = { f: 1, g: 2, h: "init", j: 0 };
      return (loc0.f = arg0);
    }
    for (let i = 0; i < 200; i++) {
      const box = { id: i };
      assertEq(declareNameRepro(box), box, "declareName insert2+put_field return value");
    }

    function propStore1B2B(arg0, arg1, arg2, arg3) {
      let l0 = { a: 0, b: 0, c: 0, d: 0, e: null, u: undefined, t: false };
      let l1 = "s_" + arg2;
      let l2 = 12;
      let l3 = 34;
      let l4 = 56;
      let l5 = 78;
      let l6 = 90;
      // Keep >= 8 locals so l6 uses get_loc8
      let l7 = { nested: arg2 };
      for (let i = 0; i < 4; i++) {
        // 1B get_loc0..3 / push_minus1..7 / undefined / null / bool
        l0.a = l2;
        l0.b = 5;
        l0.c = -1;
        l0.d = l1;
        l0.e = null;
        l0.u = undefined;
        l0.t = true;
        l0.t = false;
        // 1B arg receiver + arg/const value
        arg0.a = arg1;
        arg0.b = 7;
        arg0.d = l7;
        // 2B push_i8 (including 66 == OP_put_field and 70 == OP_get_array_el!) + get_loc8
        l0.a = 66;
        assertEq(l0.a, 66, "put_field push_i8 66 (OP_put_field opcode byte)");
        l0.b = 70;
        assertEq(l0.b, 70, "put_field push_i8 70 (OP_get_array_el opcode byte)");
        l0.c = l6;
        assertEq(l0.c, 90, "put_field get_loc8");
        arg0.c = l5;
        arg0.d = arg3;
      }
      // Overwrite refcounted property with rc == 1 and rc > 1
      l0.d = "fresh_" + arg2;
      let keep = l0.d;
      l0.d = "next_" + arg2;
      return l0.a + l0.b + l0.c + arg0.a + arg0.b + arg0.c + l0.d.length + keep.length + arg3.x;
    }
    const psArg0 = { a: 0, b: 0, c: 0, d: null };
    for (let i = 0; i < 150; i++) {
      const res = propStore1B2B(psArg0, 11, i, { x: 3 });
      assertEq(psArg0.a, 11, "propStore arg0.a");
      assertEq(psArg0.b, 7, "propStore arg0.b");
      assertEq(psArg0.c, 78, "propStore arg0.c");
      assertEq(res > 0, true, "propStore sum");
    }
    let tdzErr = "";
    function putFieldTdz() {
      let box = { v: 1 };
      box.v = tdzVar;
      let tdzVar = 2;
    }
    try {
      putFieldTdz();
    } catch (e) {
      tdzErr = e.name;
    }
    assertEq(tdzErr, "ReferenceError", "put_field get_loc TDZ bailout");

    // 13b. len == 7 arg.field leaf & var_count==0 non-leaf 0x43->0xd3 upgrade
    const car7 = (p) => p.car;
    const cdr7 = (p) => p.cdr;
    const protoBase = { car: 999 };
    const protoChild = Object.create(protoBase);
    protoChild.cdr = 888;
    for (let i = 0; i < 200; i++) {
      const pair = { car: "L" + i, cdr: i * 2 };
      assertEq(car7(pair), "L" + i, "len7 own str field");
      assertEq(cdr7(pair), i * 2, "len7 own int field");
      if (i > 150) {
        assertEq(car7(protoChild), 999, "len7 proto field fallback");
        assertEq(cdr7(protoChild), 888, "len7 protoChild own cdr");
        assertEq(car7({}), undefined, "len7 missing field fallback");
      }
    }
    function var0Inner(x) {
      return x + 1;
    }
    function var0NonLeafLen12(x) {
      return var0Inner(x) + 2;
    }
    let v0sum = 0;
    for (let i = 0; i < 500; i++) {
      v0sum += var0NonLeafLen12(i & 15);
    }
    assertEq(v0sum > 0, true, "var0 non-leaf 0x43->0xd3");

    // 13c. 0xc1 owned_args fast call admission (mutating primitive + refcounted args)
    function mutOwnedArgs(a, b, s) {
      a = a + 10;
      b = { v: a + b.v };
      s = s + "!";
      return b.v + s.length;
    }
    for (let i = 0; i < 200; i++) {
      const origObj = { v: 5 };
      const origStr = "hi" + (i & 3);
      const r = mutOwnedArgs(i, origObj, origStr);
      assertEq(r, i + 15 + origStr.length + 1, "owned_args mutated result");
      assertEq(origObj.v, 5, "owned_args caller obj intact");
      assertEq(origStr.length, 3, "owned_args caller str intact");
    }

    // 13d. BigInt inline SHORT_BIG_INT + 1/2/3-limb add_loc + alias protection + overflow
    function bigAcc64(n) {
      let sum = 0n;
      for (let i = 1; i <= n; i++) {
        let a = BigInt(i) * 134217728n; // 2^27 * i -> a*a crosses int32, int64, and 2^64
        sum += a * a;
      }
      return sum;
    }
    // Check exact formula: 2^54 * n*(n+1)*(2n+1)/6
    assertEq(
      bigAcc64(1000),
      ((1n << 54n) * 1000n * 1001n * 2001n) / 6n,
      "bigAcc64 1/2/3-limb sum+=a*a",
    );
    assertEq(bigAcc64(500), ((1n << 54n) * 500n * 501n * 1001n) / 6n, "bigAcc64 2-limb boundary");

    // Shrink from 2-limb back to SHORT_BIG_INT
    function bigShrink() {
      let s = 3000000000n;
      for (let i = 0; i < 100; i++) {
        s += -30000000n;
      }
      return s;
    }
    assertEq(bigShrink(), 0n, "bigShrink 2-limb back to SHORT_BIG_INT");

    // Shared alias ref_count > 1 must NOT mutate in-place
    function bigSharedAlias() {
      let sum = 1n << 40n;
      let alias = sum;
      for (let i = 0; i < 50; i++) {
        let a = 10000000n;
        sum += a * a;
      }
      return [sum, alias];
    }
    const [bsum, balias] = bigSharedAlias();
    assertEq(balias, 1n << 40n, "bigSharedAlias kept original");
    assertEq(bsum, (1n << 40n) + 50n * 100000000000000n, "bigSharedAlias updated independently");
    assertEq(-2147483648n + -1n, -2147483649n, "SHORT_BIG_INT INT32_MIN + -1n overflow");

    // 13e. .Lpush_int constant-RHS ALU + local store + compare-branch
    function pushIntAll(x, extra) {
      let l0 = x,
        l1 = 0,
        l2 = 0,
        l3 = 0,
        l4 = 0,
        l5 = 0,
        l6 = 0,
        l7 = "strval";
      l0 = l0 + 1;
      l1 = l0 - 3 + 500;
      l2 = (l1 << 3) >> 1;
      l3 = l2 >>> 2;
      l4 = (l3 & 0x5555) ^ 127;
      l5 = l4 | 1024;
      l6 = l0 + 100000 - 200; // push_i32
      // Test chained set_loc
      let chained = (l0 = x + 7);
      assertEq(chained, x + 7, "push_int add + set_loc0");
      // Overwrite refcounted local (must bail out to slow path safely without leaking)
      l7 = x + 9;
      assertEq(l7, x + 9, "push_int overwrite string in l7 (get/put_loc8)");
      l7 = "restore_" + x;
      // shr producing > INT32_MAX float64 must bail to unsigned->float64
      let u = -1 >>> 0;
      assertEq(u, 4294967295, "(-1) >>> 0 float64 bailout");
      // pow / instanceof / in must bail safely
      let pw = (x & 3) ** 2;
      let inst = extra instanceof Array;
      let hasIn = 0 in extra ? 1 : 0;
      // Compare + if_false8 / if_true8
      let branchAcc = 0;
      if (x < 50) branchAcc += 1;
      if (x <= 50) branchAcc += 2;
      if (x > 50) branchAcc += 4;
      if (x >= 50) branchAcc += 8;
      if (x == 50) branchAcc += 16;
      if (x != 50) branchAcc += 32;
      if (x === 50) branchAcc += 64;
      if (x !== 50) branchAcc += 128;
      return (
        l0 + l1 + l2 + l3 + l4 + l5 + l6 + l7.length + pw + (inst ? 10 : 0) + hasIn + branchAcc
      );
    }
    const piArr = [42];
    for (let i = 0; i < 120; i++) {
      const v = pushIntAll(i, piArr);
      const expectedAcc =
        (i < 50 ? 1 : 0) +
        (i <= 50 ? 2 : 0) +
        (i > 50 ? 4 : 0) +
        (i >= 50 ? 8 : 0) +
        (i === 50 ? 16 : 0) +
        (i !== 50 ? 32 : 0) +
        (i === 50 ? 64 : 0) +
        (i !== 50 ? 128 : 0);
      const l1 = i + 1 - 3 + 500;
      const l2 = (l1 << 3) >> 1;
      const l3 = l2 >>> 2;
      const l4 = (l3 & 0x5555) ^ 127;
      const l5 = l4 | 1024;
      const l6 = i + 1 + 100000 - 200;
      const l7len = ("restore_" + i).length;
      const exp = i + 7 + l1 + l2 + l3 + l4 + l5 + l6 + l7len + (i & 3) ** 2 + 10 + 1 + expectedAcc;
      assertEq(v, exp, "pushIntAll iteration " + i);
    }

    // 13f. R89v10b: BigInt put_loc8, compound-leaf 30k iterations & mutation, JS_FastInstanceOf
    function bigAccPutLoc8(n) {
      let l0 = 1,
        l1 = 2,
        l2 = 3,
        l3 = 4; // force sum into >= put_loc8 slot
      let sum = 0n;
      for (let i = 1; i <= n; i++) {
        let a = BigInt(i) * 134217728n;
        sum += a * a;
      }
      return sum + BigInt(l0 + l1 + l2 + l3);
    }
    assertEq(
      bigAccPutLoc8(600),
      ((1n << 54n) * 600n * 601n * 1201n) / 6n + 10n,
      "bigAccPutLoc8 sum+=a*a put_loc8",
    );

    function bigAccAlias8() {
      let l0 = 1,
        l1 = 2,
        l2 = 3,
        l3 = 4;
      let sum = 1n << 40n;
      let saved = sum;
      for (let i = 0; i < 40; i++) {
        let a = 10000000n;
        sum += a * a;
      }
      return [sum, saved, l0 + l1 + l2 + l3];
    }
    const [bs8, bsave8, bsum8] = bigAccAlias8();
    assertEq(bsave8, 1n << 40n, "bigAccAlias8 preserved saved when ref_count > 2");
    assertEq(bs8, (1n << 40n) + 40n * 100000000000000n, "bigAccAlias8 sum updated");
    assertEq(bsum8, 10, "bigAccAlias8 extra locals intact");

    // Compound leaves: sc_isNumber (len=9 typeof ===), sc_isPair (len=8), markUnsatisfied (len=19)
    function leafIsNum(x) {
      return typeof x === "number";
    }
    function leafNotBigInt(x) {
      return typeof x !== "bigint";
    }
    function leafIsFoo(p) {
      return p instanceof LeafFoo;
    }
    function LeafFoo(v) {
      this.v = v;
      this.dir = 0;
    }
    LeafFoo.prototype.markUnsat = function () {
      this.dir = LEAF_CONST.NONE;
    };
    var LEAF_CONST = { NONE: 0, INIT: 7 };
    const fooObj = new LeafFoo(123);
    const fooArr = [fooObj, 42, "sym", null, undefined, true, 123n, 10n ** 30n, {}, leafIsNum];
    let numHits = 0,
      pairHits = 0,
      nbHits = 0;
    for (let i = 0; i < 30000; i++) {
      const x = fooArr[i % fooArr.length];
      if (leafIsNum(x)) numHits++;
      if (leafNotBigInt(x)) nbHits++;
      if (leafIsFoo(x)) pairHits++;
      fooObj.markUnsat();
    }
    assertEq(numHits, 3000, "leafIsNum 30k iterations");
    assertEq(nbHits, 24000, "leafNotBigInt 30k iterations");
    assertEq(pairHits, 3000, "leafIsFoo 30k iterations");
    assertEq(fooObj.dir, 0, "LeafFoo.markUnsat initial LEAF_CONST.NONE");
    LEAF_CONST.NONE = 99;
    fooObj.markUnsat();
    assertEq(fooObj.dir, 99, "LeafFoo.markUnsat after LEAF_CONST.NONE mutation");
    LEAF_CONST.NONE = "strval"; // switch from non-ref to refcounted!
    fooObj.markUnsat();
    assertEq(fooObj.dir, "strval", "LeafFoo.markUnsat after refcounted mutation");

    // JS_FastInstanceOf: primitives, 1-hop & multi-hop protos, aliased f instanceof f, Symbol.hasInstance override
    function InstBase() {}
    function InstMid() {}
    InstMid.prototype = Object.create(InstBase.prototype);
    function InstSub() {}
    InstSub.prototype = Object.create(InstMid.prototype);
    const subInst = new InstSub();
    const midInst = new InstMid();
    function checkInst(v, C) {
      return v instanceof C;
    }
    const primVals = ["str", 42, null, undefined, true, 123n, 10n ** 30n, Symbol("s")];
    for (let r = 0; r < 200; r++) {
      for (const pv of primVals) {
        assertEq(checkInst(pv, InstBase), false, "primitive instanceof false");
      }
      assertEq(checkInst(subInst, InstSub), true, "1-hop instanceof true");
      assertEq(checkInst(subInst, InstMid), true, "2-hop instanceof true");
      assertEq(checkInst(subInst, InstBase), true, "3-hop instanceof true");
      assertEq(checkInst(midInst, InstSub), false, "sibling instanceof false");
      assertEq(checkInst(InstBase, InstBase), false, "aliased ctor instanceof ctor");
    }
    // Detach prototype.constructor cycle to hit ref_count==2 alias path:
    function AliasCtor() {}
    AliasCtor.prototype.constructor = undefined;
    function testAliasOnce() {
      const f = AliasCtor;
      assertEq(f instanceof f, false, "AliasCtor instanceof AliasCtor");
    }
    testAliasOnce();
    // Custom [Symbol.hasInstance] invalidation:
    Object.defineProperty(InstBase, Symbol.hasInstance, {
      value(v) {
        return v === "magic";
      },
      configurable: true,
    });
    assertEq(checkInst("magic", InstBase), true, "custom Symbol.hasInstance primitive magic");
    assertEq(checkInst(subInst, InstBase), false, "custom Symbol.hasInstance rejects subInst");
    delete InstBase[Symbol.hasInstance];
    assertEq(checkInst(subInst, InstBase), true, "restored Symbol.hasInstance after delete");

    // Deferred publication invariants on non-root returns interleaved with mapped arguments + backtrace
    function argAssert(actual, expected, message) {
      if (arguments.length === 1) expected = true;
      assertEq(actual, expected, message || "argAssert");
    }
    function makeArgArrow(a, b = () => arguments) {
      return b;
    }
    for (let r = 0; r < 20; r++) {
      const g1 = (function (a, b = arguments[0]) {
        return b;
      })(12 + r);
      argAssert(g1, 12 + r, "default arguments[0] before deferred return");
      const arrFn = makeArgArrow(12 + r);
      const vals = arrFn();
      const got = vals[0];
      argAssert(got, 12 + r, "arrow captured arguments return under deferred publish");
    }
    try {
      throw new Error("bt");
    } catch (e) {
      assertEq(
        typeof e.stack,
        "string",
        "backtrace string after mapped arguments + deferred publish",
      );
    }

    // Polymorphic JS_FastCompoundLeaf 2-way shape cache + 3rd shape eviction
    globalThis.__r89v10c_Dir = { NONE: 0, FORWARD: 1, BACKWARD: -1 };
    globalThis.__r89v10c_Mask = 1;
    globalThis.__r89v10c_Held = 2;
    globalThis.__r89v10c_Susp = 4;
    function PolyA(dir, v1, v2, st) {
      this.aPad = 11;
      this.direction = dir;
      this.v1 = v1;
      this.v2 = v2;
      this.state = st;
    }
    function PolyB(dir, v1, v2, st) {
      this.v2 = v2;
      this.bPad1 = 22;
      this.v1 = v1;
      this.bPad2 = 33;
      this.direction = dir;
      this.bPad3 = 44;
      this.state = st;
    }
    function PolyC(dir, v1, v2, st) {
      this.cPad1 = 55;
      this.v1 = v1;
      this.state = st;
      this.cPad2 = 66;
      this.v2 = v2;
      this.direction = dir;
    }
    function polySelect() {
      return this.direction === __r89v10c_Dir.FORWARD ? this.v2 : this.v1;
    }
    function polySat() {
      return this.direction !== __r89v10c_Dir.NONE;
    }
    function polyMark() {
      this.state |= __r89v10c_Mask;
    }
    function polyHeldOrSusp() {
      return (this.state & __r89v10c_Held) !== 0 || this.state === __r89v10c_Susp;
    }
    function polySetDir() {
      this.direction = __r89v10c_Dir.BACKWARD;
    }
    PolyA.prototype.sel = PolyB.prototype.sel = PolyC.prototype.sel = polySelect;
    PolyA.prototype.sat = PolyB.prototype.sat = PolyC.prototype.sat = polySat;
    PolyA.prototype.mark = PolyB.prototype.mark = PolyC.prototype.mark = polyMark;
    PolyA.prototype.hos = PolyB.prototype.hos = PolyC.prototype.hos = polyHeldOrSusp;
    PolyA.prototype.setDir = PolyB.prototype.setDir = PolyC.prototype.setDir = polySetDir;

    const oa = new PolyA(1, "a1", "a2", 2);
    const ob = new PolyB(-1, "b1", "b2", 4);
    const oc = new PolyC(0, "c1", "c2", 0);
    for (let i = 0; i < 64; i++) {
      const x = i & 1 ? ob : oa;
      assertEq(x.sel(), i & 1 ? "b1" : "a2", "2-way CL_SELECT_DIR initial");
      assertEq(x.sat(), true, "2-way CL_IS_SATISFIED");
      assertEq(x.hos(), true, "2-way CL_IS_HELD_OR_SUSP");
    }
    // Flip direction on PolyA and PolyB dynamically and verify cache slot switching
    oa.direction = -1;
    ob.direction = 1;
    for (let i = 0; i < 32; i++) {
      assertEq(oa.sel(), "a1", "2-way CL_SELECT_DIR oa flipped");
      assertEq(ob.sel(), "b2", "2-way CL_SELECT_DIR ob flipped");
    }
    // Exercise 3rd shape eviction & CL_MARK_AS / CL_SET_GLOBAL_PROP
    assertEq(oc.sat(), false, "3rd shape sat");
    assertEq(oc.hos(), false, "3rd shape hos");
    oc.mark();
    oa.mark();
    ob.mark();
    assertEq(oc.state, 1, "3rd shape CL_MARK_AS");
    assertEq(oa.state, 3, "PolyA CL_MARK_AS");
    assertEq(ob.state, 5, "PolyB CL_MARK_AS");
    assertEq(oa.hos(), true, "PolyA hos after mark");
    assertEq(ob.hos(), false, "PolyB hos after mark (state=5 != Susp=4)");
    ob.setDir();
    assertEq(ob.sel(), "b1", "PolyB sel after CL_SET_GLOBAL_PROP");

    // Multi-limb BigInt +, -, *, /, % including pseudo-Mersenne reduction correctness
    const primes = [
      (1n << 255n) - 19n,
      (1n << 256n) - 189n,
      (1n << 130n) - 5n,
      (1n << 192n) - (1n << 64n) - 1n, // non-pseudo-Mersenne control
      1000000000000000000000000000000000000033n,
    ];
    for (const p of primes) {
      const vals = [
        0n,
        1n,
        -1n,
        2n,
        -2n,
        18n,
        -18n,
        19n,
        -19n,
        p - 1n,
        p,
        p + 1n,
        -p + 1n,
        -p,
        -p - 1n,
        (1n << 255n) - 1n,
        -(1n << 255n) + 1n,
        (1n << 256n) + 12345678901234567890n,
        -((1n << 256n) + 12345678901234567890n),
        (p - 3n) * (p - 5n),
        -((p - 3n) * (p - 5n)),
        (1n << 520n) - 777n,
        -((1n << 520n) - 777n),
      ];
      for (const a of vals) {
        const q = a / p;
        const r = a % p;
        const negR = a % -p;
        assertEq(q * p + r, a, "BigInt div/rem identity");
        assertEq(r, a - q * p, "BigInt mod matches a - (a/p)*p");
        assertEq(negR, r, "BigInt mod sign ignores divisor sign");
        if (a >= 0n) {
          assertEq(r >= 0n && r < p, true, "BigInt non-neg mod range");
        } else {
          assertEq(r <= 0n && r > -p, true, "BigInt neg mod range");
        }
      }
    }
    // Chained BigInt arithmetic (ed25519-style mul+add+mod) + div-by-zero
    const edP = (1n << 255n) - 19n;
    let accA = (1n << 254n) + 0x123456789abcdef0123456789abcdef0n;
    let accB = (1n << 253n) + 0xfedcba9876543210fedcba9876543210n;
    for (let i = 0; i < 40; i++) {
      const prod = accA * accB + BigInt(i) - accA;
      const rem = prod % edP;
      const quo = prod / edP;
      assertEq(quo * edP + rem, prod, "ed25519 chain identity");
      accA = accB;
      accB = rem < 0n ? rem + edP : rem;
    }
    assertThrows(
      () => {
        return edP % 0n;
      },
      RangeError,
      "BigInt mod by zero",
    );

    // 4-limb & 8-limb OP_add_loc (+= short bigint) including low-64b carry boundary & negative locals
    let bi4 = (1n << 123n) + 0xfffffffffffffffen;
    for (let k = 0; k < 8; k++) {
      bi4 += 1n;
    }
    assertEq(bi4, (1n << 123n) + 0x10000000000000006n, "4-limb OP_add_loc carry boundary");
    let bi8 = (1n << 250n) + 42n;
    for (let k = 0; k < 10; k++) {
      bi8 += 3n;
    }
    assertEq(bi8, (1n << 250n) + 72n, "8-limb OP_add_loc no-carry");
    let biNeg = -(1n << 123n);
    for (let k = 0; k < 8; k++) {
      biNeg += 1n;
    }
    assertEq(biNeg, -(1n << 123n) + 8n, "4-limb negative OP_add_loc fallback");

    // Interleaved 2-way compound leaves + inline_only closure leaf across interrupt rollovers
    let capVal = 7;
    function inlineCapLeaf(x) {
      return x + capVal;
    }
    const pa2 = new PolyA(1, 10, 20, 2);
    const pb2 = new PolyB(-1, 30, 40, 4);
    let loopSum = 0;
    for (let iter = 0; iter < 25000; iter++) {
      const o = iter & 1 ? pb2 : pa2;
      loopSum += o.sel() + inlineCapLeaf(iter & 3);
    }
    // Expected: (20+30)*12500 + (7 + 8 + 9 + 10)*6250 = 625000 + 212500 = 837500
    assertEq(loopSum, 837500, "leaf + inline_only closure survival across interrupt rollovers");
    delete globalThis.__r89v10c_Dir;
    delete globalThis.__r89v10c_Mask;
    delete globalThis.__r89v10c_Held;
    delete globalThis.__r89v10c_Susp;

    // R89v10e: Class.create() forwarding constructors (Tier 3), prototype setter invalidation, apply override,
    // non-pure initialize negative cache, under-applied Tier 2 ctor, and 2->4 slot inline ctor growth.
    function makeClassCreate() {
      return function () {
        this.initialize.apply(this, arguments);
      };
    }
    const ColorC = makeClassCreate();
    ColorC.prototype = {
      red: 0.0,
      green: 0.0,
      blue: 0.0,
      initialize: function (r, g, b) {
        if (!r) r = 0.0;
        if (!g) g = 0.0;
        if (!b) b = 0.0;
        this.red = r;
        this.green = g;
        this.blue = b;
      },
    };
    const VecC = makeClassCreate();
    VecC.prototype = {
      x: 0.0,
      y: 0.0,
      z: 0.0,
      initialize: function (x, y, z) {
        this.x = x ? x : 0;
        this.y = y ? y : 0;
        this.z = z ? z : 0;
      },
    };
    let lastC = null,
      lastV = null;
    for (let i = 0; i < 64; i++) {
      const cc = new ColorC(0, i * 0.5, "");
      assertEq(cc.red, 0.0, "ColorC falsy 0 -> 0.0");
      assertEq(cc.green, i * 0.5, "ColorC green");
      assertEq(cc.blue, 0.0, "ColorC falsy empty str -> 0.0");
      lastC = cc;
      const argObj = { tag: i };
      const vv = i & 1 ? new VecC(argObj, 2, 3, 99) : new VecC(argObj);
      assertEq(vv.x.tag, i, "VecC object arg refcount survival");
      assertEq(vv.y, i & 1 ? 2 : 0, "VecC y missing vs present");
      assertEq(vv.z, i & 1 ? 3 : 0, "VecC z missing vs present");
      vv.w = i + 1;
      assertEq(vv.w, i + 1, "VecC post-ctor transition w");
      lastV = vv;
    }
    assertEq(lastC.blue, 0.0, "lastC");
    assertEq(lastV.w, 64, "lastV.w");

    // Prototype setter installation after warm-up must invalidate Tier 3 and run setter
    let setterSaw = 0;
    const VecSetter = makeClassCreate();
    VecSetter.prototype = {
      x: 0,
      z: 0,
      initialize: function (x, z) {
        this.x = x;
        this.z = z;
      },
    };
    for (let i = 0; i < 16; i++) {
      const v0 = new VecSetter(1, i);
      assertEq(v0.z, i, "VecSetter warm-up");
    }
    Object.defineProperty(VecSetter.prototype, "z", {
      set(v) {
        setterSaw += v;
        this._z = v * 10;
      },
      get() {
        return this._z;
      },
    });
    for (let i = 1; i <= 8; i++) {
      const v1 = new VecSetter(5, i);
      assertEq(v1.z, i * 10, "VecSetter setter invoked after defineProperty");
      assertEq(v1.x, 5, "VecSetter x intact");
    }
    assertEq(setterSaw, 36, "setterSaw sum 1..8");

    // init.apply override after warm-up must invalidate Tier 3 and run overridden apply
    let applyCalls = 0;
    const VecApply = makeClassCreate();
    function initApply(a, b) {
      this.a = a;
      this.b = b;
    }
    VecApply.prototype = { initialize: initApply };
    for (let i = 0; i < 16; i++) {
      const va = new VecApply(i, i + 1);
      assertEq(va.b, i + 1, "VecApply warm-up");
    }
    initApply.apply = function (recv, args) {
      applyCalls++;
      recv.a = args[0] + 100;
      recv.b = args[1] + 200;
    };
    for (let i = 0; i < 8; i++) {
      const va2 = new VecApply(i, i + 1);
      assertEq(va2.a, i + 100, "VecApply custom init.apply a");
      assertEq(va2.b, i + 201, "VecApply custom init.apply b");
    }
    assertEq(applyCalls, 8, "init.apply override count");

    // Non-pure initialize (constructing nested object) must negative-cache safely
    const InnerC = makeClassCreate();
    InnerC.prototype = {
      initialize: function (v) {
        this.v = v;
      },
    };
    const OuterC = makeClassCreate();
    OuterC.prototype = {
      initialize: function (v) {
        this.inner = new InnerC(v);
        this.doubleV = v * 2;
      },
    };
    for (let i = 0; i < 16; i++) {
      const oc = new OuterC(i);
      assertEq(oc.inner.v, i, "OuterC nested inner.v");
      assertEq(oc.doubleV, i * 2, "OuterC doubleV");
    }

    // Under-applied Tier 2 constructor (incoming_argc < b->arg_count) calling another ctor
    function Box2(val) {
      this.val = val;
    }
    function Variable2(name, initialValue) {
      this.name = name;
      this.box = new Box2(initialValue || 0);
    }
    for (let i = 0; i < 32; i++) {
      const vUnder = i & 1 ? new Variable2("v" + i, i + 10) : new Variable2("v" + i);
      assertEq(vUnder.name, "v" + i, "Variable2 name");
      assertEq(vUnder.box.val, i & 1 ? i + 10 : 0, "Variable2 under-applied initialValue");
    }

    // SplayTree.Node-style 2-field Tier 1 ctor followed by .left / .right growth across 1000 nodes
    function SplayNode(key, value) {
      this.key = key;
      this.value = value;
    }
    SplayNode.prototype.left = null;
    SplayNode.prototype.right = null;
    let rootNode = null;
    for (let i = 0; i < 1000; i++) {
      const node = new SplayNode(i, "val" + (i & 7));
      node.left = rootNode;
      node.right = null;
      rootNode = node;
    }
    assertEq(rootNode.key, 999, "SplayNode root key");
    assertEq(rootNode.left.key, 998, "SplayNode child key");
    assertEq(rootNode.right, null, "SplayNode right null");
  })();
})();
