let checks = 0,
  digest = 0;
function assert(v) {
  checks++;
  if (!v) throw Error("symbol case " + checks);
}
globalThis.SA = Symbol("a");
globalThis.SB = Symbol("b");
globalThis.SC = Symbol("c");
let LA = Symbol("la"),
  LB = Symbol("lb");
function actual(v, h) {
  let force = h.x;
  switch (v) {
    case SA:
      return 11;
    case SB:
    case SC:
      return 23;
    default:
      return 37;
  }
}
function expect(v) {
  if (v === SA) return 11;
  if (v === SB || v === SC) return 23;
  return 37;
}
function lexical(v, h) {
  let force = h.x;
  switch (v) {
    case LA:
      return 43;
    case LB:
      return 47;
    default:
      return 53;
  }
}
let values = [
  SA,
  SB,
  SC,
  Symbol("a"),
  Symbol.for("a"),
  undefined,
  null,
  true,
  false,
  0,
  1,
  NaN,
  0n,
  "a",
  {},
  Object(SA),
];
for (let pass = 0; pass < 100; pass++)
  for (let v of values) {
    assert(actual(v, { x: pass }) === expect(v));
    digest += actual(v, { x: pass });
  }
for (let pass = 0; pass < 100; pass++)
  for (let v of [LA, LB, ...values])
    assert(lexical(v, { x: pass }) === (v === LA ? 43 : v === LB ? 47 : 53));
let original = SA;
SA = SB;
for (let v of values) assert(actual(v, { x: 1 }) === expect(v));
SA = Symbol("new");
for (let v of [SA, ...values]) assert(actual(v, { x: 1 }) === expect(v));
SA = 0;
SB = "a";
SC = 0n;
for (let v of values) assert(actual(v, { x: 1 }) === expect(v));
SA = original;
SB = values[1];
SC = values[2];
LA = LB;
for (let v of [LA, LB, ...values])
  assert(lexical(v, { x: 1 }) === (v === LA ? 43 : v === LB ? 47 : 53));
let reads = 0;
Object.defineProperty(globalThis, "SA", {
  configurable: true,
  get() {
    reads++;
    if (globalThis.gc) gc();
    return original;
  },
});
for (let v of values) assert(actual(v, { x: 1 }) === expect(v));
assert(reads > 0);
Object.defineProperty(globalThis, "SA", { value: original, writable: true, configurable: true });
delete globalThis.SB;
let threw = false;
try {
  actual(values[1], { x: 1 });
} catch (e) {
  threw = e instanceof ReferenceError;
}
assert(threw);
globalThis.SB = values[1];
for (let v of values) assert(actual(v, { x: 1 }) === expect(v));
function wide0(v, h) {
  let force = h.x,
    acc = 0;
  switch (v) {
    case SA:
      acc = 61;
      break;
    case SB:
      acc = 62;
      break;
    case SC:
      acc = 63;
      break;
    case LA:
      acc = 64;
      break;
    case LB:
      acc = 65;
      break;
    default:
      acc = 79;
  }
  return acc;
}
for (let pass = 0; pass < 100; pass++)
  for (let v of [...values, LA, LB]) {
    let e = 79;
    if (v === LB) e = 65;
    if (v === LA) e = 64;
    if (v === SC) e = 63;
    if (v === SB) e = 62;
    if (v === SA) e = 61;
    assert(wide0(v, { x: pass }) === e);
  }
function wide1(v, h) {
  let force = h.x,
    acc = 0;
  switch (v) {
    case SA:
      acc = 61;
      acc += 0;
      acc += 0;
      acc += 0;
      acc += 0;
      acc += 0;
      acc += 0;
      acc += 0;
      acc += 0;
      acc += 0;
      acc += 0;
      acc += 0;
      acc += 0;
      acc += 0;
      acc += 0;
      acc += 0;
      acc += 0;
      acc += 0;
      acc += 0;
      acc += 0;
      acc += 0;
      acc += 0;
      acc += 0;
      acc += 0;
      acc += 0;
      acc += 0;
      acc += 0;
      acc += 0;
      acc += 0;
      acc += 0;
      acc += 0;
      acc += 0;
      acc += 0;
      acc += 0;
      acc += 0;
      acc += 0;
      acc += 0;
      acc += 0;
      acc += 0;
      acc += 0;
      acc += 0;
      acc += 0;
      acc += 0;
      acc += 0;
      acc += 0;
      acc += 0;
      acc += 0;
      acc += 0;
      acc += 0;
      acc += 0;
      acc += 0;
      acc += 0;
      acc += 0;
      acc += 0;
      acc += 0;
      acc += 0;
      acc += 0;
      acc += 0;
      acc += 0;
      acc += 0;
      acc += 0;
      acc += 0;
      acc += 0;
      acc += 0;
      acc += 0;
      acc += 0;
      acc += 0;
      acc += 0;
      acc += 0;
      acc += 0;
      acc += 0;
      acc += 0;
      acc += 0;
      acc += 0;
      acc += 0;
      acc += 0;
      acc += 0;
      acc += 0;
      acc += 0;
      acc += 0;
      acc += 0;
      acc += 0;
      acc += 0;
      acc += 0;
      acc += 0;
      acc += 0;
      acc += 0;
      acc += 0;
      acc += 0;
      acc += 0;
      acc += 0;
      acc += 0;
      acc += 0;
      acc += 0;
      acc += 0;
      acc += 0;
      acc += 0;
      acc += 0;
      acc += 0;
      acc += 0;
      acc += 0;
      break;
    case SB:
      acc = 62;
      break;
    case SC:
      acc = 63;
      break;
    case LA:
      acc = 64;
      break;
    case LB:
      acc = 65;
      break;
    default:
      acc = 79;
  }
  return acc;
}
for (let pass = 0; pass < 100; pass++)
  for (let v of [...values, LA, LB]) {
    let e = 79;
    if (v === LB) e = 65;
    if (v === LA) e = 64;
    if (v === SC) e = 63;
    if (v === SB) e = 62;
    if (v === SA) e = 61;
    assert(wide1(v, { x: pass }) === e);
  }
console.log("SYMBOL_CASE_SEMANTICS_OK " + checks + " " + digest);

let tdzChecks = 0,
  throws = 0;
const yes = Symbol("tdz");
function hit(v, h) {
  let force = h.x;
  switch (v) {
    case pendingSymbol:
      return 17;
    default:
      return 19;
  }
}
for (let n = 0; n < 100; n++) {
  let caught = false;
  try {
    hit(yes, { x: n });
  } catch (e) {
    caught = e instanceof ReferenceError;
    throws++;
  }
  tdzChecks++;
  if (!caught) throw Error("TDZ must throw before any comparison branch");
}
let pendingSymbol = yes;
for (let n = 0; n < 100; n++) {
  tdzChecks++;
  if (hit(yes, { x: n }) !== 17 || hit(Symbol("tdz"), { x: n }) !== 19)
    throw Error("TDZ initialization");
}
pendingSymbol = Symbol("replacement");
for (let n = 0; n < 100; n++) {
  tdzChecks++;
  if (hit(pendingSymbol, { x: n }) !== 17 || hit(yes, { x: n }) !== 19)
    throw Error("live cell replacement");
}
console.log("SYMBOL_CASE_TDZ_OK " + tdzChecks + " " + throws);

let directChecks = 0,
  checksum = 0;
globalThis.SA = Symbol("a");
globalThis.SB = Symbol("b");
function equal(v, h) {
  let force = h.x;
  if (v === SA) return 17;
  return 23;
}
function inverted(v, h) {
  let force = h.x;
  if (!(v === SA)) return 29;
  return 31;
}
function longEqual(v, h) {
  let force = h.x;
  if (v === SA) {
    let x = 1;
    x += 1;
    x += 1;
    x += 1;
    x += 1;
    x += 1;
    x += 1;
    x += 1;
    x += 1;
    x += 1;
    x += 1;
    x += 1;
    x += 1;
    x += 1;
    x += 1;
    x += 1;
    x += 1;
    x += 1;
    x += 1;
    x += 1;
    x += 1;
    x += 1;
    x += 1;
    x += 1;
    x += 1;
    x += 1;
    x += 1;
    x += 1;
    x += 1;
    x += 1;
    x += 1;
    return x;
  }
  return 41;
}
function unique(h) {
  let force = h.x;
  if (Symbol("a") === SA) return 43;
  return 47;
}
function once(make, h) {
  let force = h.x;
  if (make() === SA) return 53;
  return 59;
}
let directValues = [
  SA,
  SB,
  Symbol("a"),
  undefined,
  null,
  false,
  true,
  0,
  1,
  NaN,
  0n,
  "a",
  {},
  Object(SA),
];
for (let p = 0; p < 100; p++)
  for (let i = 0; i < directValues.length; i++) {
    let v = directValues[i],
      isSame = i === 0,
      h = { x: p };
    let a = equal(v, h),
      b = inverted(v, h),
      c = longEqual(v, h);
    if (a !== (isSame ? 17 : 23) || b !== (isSame ? 31 : 29) || c !== (isSame ? 31 : 41))
      throw Error("direct symbol branch");
    directChecks += 3;
    checksum += a + b + c;
    if (unique(h) !== 47) throw Error("last Symbol owner");
    directChecks++;
    let called = 0;
    let d = once(() => {
      called++;
      return v;
    }, h);
    if (d !== (isSame ? 53 : 59) || called !== 1) throw Error("single evaluation");
    directChecks++;
  }
SA = SB;
if (equal(SB, { x: 1 }) !== 17 || equal(directValues[0], { x: 1 }) !== 23)
  throw Error("binding replacement");
directChecks += 2;
let gets = 0;
Object.defineProperty(globalThis, "SA", {
  configurable: true,
  get() {
    gets++;
    return SB;
  },
});
if (equal(SB, { x: 1 }) !== 17 || inverted(SB, { x: 1 }) !== 31 || gets !== 2)
  throw Error("accessor fallback");
directChecks += 3;
console.log("SYMBOL_GLOBAL_DIRECT_OK " + directChecks + " " + checksum);

console.log("SYMBOL_CONDITIONS_OK");
