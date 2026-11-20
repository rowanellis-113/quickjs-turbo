// Hybrid Reference Counting + Generational Partial Cycle GC + ZCT + Borrowed Array Torture Suite

function assert(cond, msg) {
  if (!cond) {
    throw new Error("Assertion failed: " + (msg || "unknown"));
  }
}

const HAS_STD_GC = typeof std !== "undefined" && std && typeof std.gc === "function";

function maybeGC() {
  if (HAS_STD_GC) {
    std.gc();
  }
}

function linkOldYoungCycle(oldObj) {
  const a = { ref: oldObj, tag: "youngA" };
  const b = { peer: a, tag: "youngB" };
  a.peer = b;
  oldObj.back = a;
}

function spawnYoungRefOld(oldCohort, i, wrList) {
  const y1 = { idx: i, oldRef: oldCohort[(i * 13) % oldCohort.length] };
  const y2 = { prev: y1, arr: [oldCohort[i % 100], y1] };
  y1.next = y2;
  if ((i & 31) === 0) {
    wrList.push(new WeakRef(y1));
  }
}

function churnYoungCyclesToTriggerMinorGC(oldCohort) {
  for (let i = 0; i < 6000; i++) {
    const a = { k: i, old: oldCohort[i & 255] };
    const b = { peer: a, arr: [i, a] };
    a.peer = b;
  }
}

// 1. Old-to-Young & Young-to-Old cross-generational cycles + REMOVE_CYCLES old-node drop
function testCrossGenCycles() {
  const oldCohort = [];
  for (let i = 0; i < 6000; i++) {
    oldCohort.push({ id: i, tag: "old" + (i & 31), sub: { v: i * 2 } });
  }
  let oldDroppedByYoung = { secret: 424242 };
  const wrOldDropped = new WeakRef(oldDroppedByYoung);
  maybeGC();
  maybeGC();

  linkOldYoungCycle(oldDroppedByYoung);
  oldDroppedByYoung = null;

  churnYoungCyclesToTriggerMinorGC(oldCohort);

  for (let round = 0; round < 5; round++) {
    const wrList = [];
    for (let i = 0; i < 400; i++) {
      spawnYoungRefOld(oldCohort, i, wrList);
    }
    maybeGC();
    if (HAS_STD_GC) {
      for (const w of wrList) {
        assert(w.deref() === undefined, "Dead young cycle should be collected after GC");
      }
    }
  }

  maybeGC();
  if (HAS_STD_GC) {
    assert(
      wrOldDropped.deref() === undefined,
      "Old object dropped by dead young cycle must be collected",
    );
  }
  for (let i = 0; i < oldCohort.length; i += 257) {
    assert(oldCohort[i].id === i && oldCohort[i].sub.v === i * 2, "Live old object corrupted");
  }
}

// 2. Property-IC transition shape survival across minor GC + dead prototype pruning
function makeDeadProtoWithIC(readVal) {
  const p = { y: 77, payload: { nested: "ic" } };
  const wr = new WeakRef(p);
  const o = Object.create(p);
  o.x = 23;
  for (let i = 0; i < 50; i++) {
    assert(readVal(o) === 100, "Property IC read mismatch");
  }
  return wr;
}

function testPropertyICAndProtoPruning() {
  function readVal(o) {
    return o.x + (o.y | 0);
  }
  function makeProtoChain(k) {
    const p = { y: k, extra: { k } };
    return Object.create(p);
  }

  const protoWr = makeDeadProtoWithIC(readVal);
  maybeGC();
  if (HAS_STD_GC) {
    assert(protoWr.deref() === undefined, "Dead IC-cached prototype must be pruned across GC");
  }

  let sum = 0;
  for (let i = 0; i < 8000; i++) {
    const obj = makeProtoChain(i & 15);
    obj.x = i;
    obj.y = 1;
    sum = (sum + readVal(obj)) | 0;
  }
  maybeGC();
  assert(sum === 32004000, "Property IC shape transition sum mismatch: " + sum);
}

// 3. ZCT boundary tests (511, 512, 513, 4096), nested structures, dynamic setPrototypeOf, WeakRef
function zctSlotReturn(n) {
  let slot = { v: 0 };
  let sum = 0;
  for (let i = 0; i < n; i++) {
    slot = { v: i, arr: [i, i + 1] };
    sum = (sum + slot.v + slot.arr[1]) | 0;
  }
  return sum;
}

function zctDropOpcode(n) {
  let acc = 0;
  for (let i = 0; i < n; i++) {
    ({ a: i, b: [i + 1] });
    [i, i + 1, { c: i }];
    acc = (acc + (i & 7)) | 0;
  }
  return acc;
}

function zctReturnRelease(flag) {
  const localObj = { a: 10, nested: { b: 20 } };
  const localArr = [localObj, { c: 30 }];
  if (flag) return localObj.a + localArr[1].c;
  return 0;
}

function makeDynProtoTarget() {
  const proto = { tag: "dynProto", p: 123 };
  const inst = { own: 7 };
  Object.setPrototypeOf(inst, proto);
  assert(inst.p === 123 && inst.own === 7, "Dynamic setPrototypeOf failed");
  return new WeakRef(proto);
}

function makeEphemeralWeakRef() {
  const t = { num: 99 };
  return new WeakRef(t);
}

function testZCTBoundaries() {
  for (const n of [511, 512, 513, 1024, 4096]) {
    assert(typeof zctSlotReturn(n) === "number", "zctSlotReturn " + n);
    assert(typeof zctDropOpcode(n) === "number", "zctDropOpcode " + n);
  }
  for (let i = 0; i < 1200; i++) {
    assert(zctReturnRelease(true) === 40, "zctReturnRelease");
  }

  const wrTarget = makeDynProtoTarget();
  for (let i = 0; i < 700; i++) {
    let tmp = { k: i };
    void tmp.k;
  }
  maybeGC();
  if (HAS_STD_GC) {
    assert(wrTarget.deref() === undefined, "Dynamic prototype WeakRef must clear");
  }

  const targets = [];
  for (let i = 0; i < 64; i++) {
    targets.push(makeEphemeralWeakRef());
  }
  for (let i = 0; i < 700; i++) {
    let tmp = [i, { x: i }];
    void tmp[0];
  }
  maybeGC();
  if (HAS_STD_GC) {
    for (const w of targets) {
      assert(w.deref() === undefined, "Ephemeral WeakRef target must be reclaimed");
    }
  }
}

// 4. Borrowed Dense-Array DRC Safety Hazards
function helperLoc01(arr, idx) {
  return arr[idx];
}

function helperArg(ignored0, ignored1, ignored2, arr, idx) {
  return arr[idx];
}

function helperManyLocals(arr, idx) {
  let l0 = 0,
    l1 = 1,
    l2 = 2,
    l3 = 3,
    l4 = 4,
    l5 = 5,
    l6 = 6,
    l7 = 7;
  let l8 = 8,
    l9 = 9,
    l10 = 10,
    l11 = 11,
    l12 = 12,
    l13 = 13,
    l14 = 14,
    l15 = 15;
  let idxLarge = idx;
  let sum = l0 + l1 + l2 + l3 + l4 + l5 + l6 + l7 + l8 + l9 + l10 + l11 + l12 + l13 + l14 + l15;
  return arr[idxLarge] + arr[0] + arr[7] + (sum - 120);
}

function testBorrowedDenseArrayHazards() {
  const objElem = { v: 55 };
  const arr = [10, objElem, "hello_" + "world", 30, 40, 50, 60, 70];
  arr[8] = arr;
  for (let i = 0; i < 500; i++) {
    assert(helperLoc01(arr, 0) === 10, "loc01 int");
    assert(helperLoc01(arr, 1).v === 55, "loc01 object dup");
    assert(helperLoc01(arr, 2) === "hello_world", "loc01 string dup");
    assert(helperLoc01(arr, 8) === arr, "loc01 self ref");
    assert(helperArg(0, 0, 0, arr, 3) === 30, "arg3/arg read");
    assert(helperManyLocals(arr, 5) === 130, "many locals / push_0..7 read");
  }

  for (const bad of [-1, -2147483648, 9, 9999]) {
    assert(helperLoc01(arr, bad) === undefined, "OOB/negative index must be undefined: " + bad);
  }
  const origProto99 = Array.prototype[9999];
  try {
    Array.prototype[9999] = "fromProto";
    assert(helperLoc01(arr, 9999) === "fromProto", "Prototype fallback on OOB");
  } finally {
    delete Array.prototype[9999];
    if (origProto99 !== undefined) Array.prototype[9999] = origProto99;
  }

  const dynArr = new Array(100);
  for (let i = 0; i < 100; i++) dynArr[i] = i;
  let getterRan = 0;
  let total = 0;
  for (let i = 0; i < 100; i++) {
    if (i === 49) {
      Object.defineProperty(dynArr, 50, {
        configurable: true,
        get() {
          getterRan++;
          dynArr.length = 0;
          return 999;
        },
      });
    }
    const v = helperLoc01(dynArr, i);
    total += v === undefined ? 0 : v;
  }
  assert(getterRan === 1, "Mid-loop getter must run once");
  assert(total === 1225 + 999, "Mid-loop getter sum mismatch: " + total);

  const sparse = [1, 2, 3, 4];
  assert(helperLoc01(sparse, 2) === 3, "dense before delete");
  delete sparse[2];
  assert(helperLoc01(sparse, 2) === undefined, "deleted hole must return undefined");
  sparse[1000] = 77;
  assert(helperLoc01(sparse, 1000) === 77, "sparse high index");

  const ta = new Int32Array([11, -22, 33, 44]);
  for (let i = 0; i < 200; i++) {
    assert(helperLoc01(ta, 1) === -22, "TypedArray signed read");
    assert(helperLoc01(ta, 9) === undefined, "TypedArray OOB");
  }

  function closureArrayOrder() {
    let captured = [101, 202, 303];
    function mutAndIndex() {
      captured = [901, 902, 903];
      return 1;
    }
    function readCapturedIdx() {
      return mutAndIndex();
    }
    const val = captured[readCapturedIdx()];
    assert(val === 202, "Evaluation order captured array before index call: got " + val);
    assert(captured[1] === 902, "Captured array mutated in place");
  }
  for (let i = 0; i < 200; i++) {
    closureArrayOrder();
  }
}

// 5. Synchronous O(1)-C-stack iterative destruction + mixed class/accessor/array fallback
function testDeepIterativeTreeAndReentrantFree() {
  function makeAndDropDeepList() {
    let head = { i: 0, payload: [0, "s_0"], next: null };
    const wrTail = new WeakRef(head);
    for (let i = 1; i < 50000; i++) {
      const a = [i, "s_" + i];
      a.length = 0; // keep backing values allocation with count == 0
      head = { i, arr: a, tag: (i & 3) === 0 ? "leaf" : "node", next: head };
    }
    const wrHead = new WeakRef(head);
    head = null;
    return [wrHead, wrTail];
  }
  const [wrHead, wrTail] = makeAndDropDeepList();
  // Synchronous RC must destroy acyclic WeakRef chain without requiring std.gc()
  assert(wrHead.deref() === undefined, "Deep acyclic head WeakRef must clear synchronously");
  assert(wrTail.deref() === undefined, "Deep acyclic tail WeakRef must clear synchronously");

  function makeAndDropMixedTree(depth) {
    let closedVar = depth * 7;
    function build(d) {
      if (d <= 0) {
        return { v: closedVar, fn: () => closedVar + 1 };
      }
      const node = {
        left: build(d - 1),
        right: build(d - 1),
        arr: [d, { nested: "n_" + d }, [1, 2, 3]],
        deleted: { dead: true },
        m: new Map([["k", d]]),
      };
      delete node.deleted;
      Object.defineProperty(node, "comp", {
        enumerable: true,
        configurable: true,
        get() {
          return closedVar;
        },
      });
      return node;
    }
    const root = build(depth);
    return new WeakRef(root);
  }
  const wrTree = makeAndDropMixedTree(13); // 2^14 - 1 = 16,383 nodes + closures + Map + getter
  assert(wrTree.deref() === undefined, "Mixed tree WeakRef must clear synchronously");
}

// 6. Promoted Old-Gen cycles bounded without threshold snowball under tight memory limit
function testPromotedOldGenCycleBound() {
  const resident = [];
  for (let i = 0; i < 4000; i++) {
    resident.push({ id: i, tag: "res" + (i & 15) });
  }
  const weakRefs = [];
  for (let round = 0; round < 32; round++) {
    let batch = new Array(900);
    for (let i = 0; i < 900; i++) {
      const a = { r: round, i, payload: [i, round, "buf_" + (i & 31)] };
      const b = { peer: a, next: null };
      const c = { peer: b };
      a.back = c;
      b.next = c;
      batch[i] = a;
      if ((i & 255) === 0) {
        weakRefs.push(new WeakRef(a));
      }
    }
    // Allocate young cycles while batch stays live so batch is promoted behind Minor boundary
    churnYoungCyclesToTriggerMinorGC(resident);
    // Now drop batch so it becomes dead cycles in the promoted generation
    batch = null;
    // Allocate enough young pressure for adaptive collection cap to reclaim dead promoted cycles
    churnYoungCyclesToTriggerMinorGC(resident);
  }
  maybeGC();
  if (HAS_STD_GC) {
    let alive = 0;
    for (let i = 0; i < weakRefs.length; i++) {
      if (weakRefs[i].deref() !== undefined) {
        alive++;
      }
    }
    assert(alive === 0, "Promoted cycles must be reclaimed cleanly, remaining=" + alive);
  }
  assert(resident.length === 4000 && resident[3999].id === 3999, "resident intact");
}

// 7. Fast non-reloading OP_drop on ref_count == 1 / > 1 strings, slices, and ropes
function testFastDropStringAndRope() {
  const baseStr = "abcdefghijklmnopqrstuvwxyz0123456789_ABCDEFGHIJKLMNOPQRSTUVWXYZ";
  for (let i = 0; i < 4000; i++) {
    // ref_count == 1 normal string from concat, immediately dropped
    "hdr_".concat("v", i);
    // ref_count == 1 integer string conversion, immediately dropped
    (i + 100000).toString();
    // ref_count == 1 slice string retaining parent baseStr
    baseStr.slice(1, 32);
    // ref_count == 1 rope string > 512 chars, immediately dropped
    const left = baseStr.repeat(9);
    const right = "_" + i;
    left + right;
    // ref_count > 1 empty concat fast-inc/dec path
    baseStr.concat();
  }
  assert(
    baseStr.length === 63 && baseStr.startsWith("abc") && baseStr.endsWith("XYZ"),
    "parent string must stay intact after slice drops",
  );
}

testCrossGenCycles();
testPropertyICAndProtoPruning();
testZCTBoundaries();
testBorrowedDenseArrayHazards();
testDeepIterativeTreeAndReentrantFree();
testPromotedOldGenCycleBound();
testFastDropStringAndRope();
print("HYBRID_GC_AB_TORTURE_OK");
