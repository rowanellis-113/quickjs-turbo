import * as std from "qjs:std";
function assert(ok, message) {
  if (!ok) throw Error(message || "concat assertion");
}
function equal(actual, expected, message) {
  assert(actual === expected, (message || "equal") + ": " + String(actual).slice(0, 50));
}
function throwsType(action, constructor) {
  let caught = false;
  try {
    action();
  } catch (e) {
    caught = e instanceof constructor;
  }
  assert(caught, "expected " + constructor.name);
}

// Exercise add_loc while both flat leaves and rope roots have live aliases.
for (const unit of ["x", "\u0416", "\ud83d\ude03"]) {
  let text = unit.repeat(211);
  const pieces = [text];
  const keep = new Map();
  for (let i = 0; i < 700; i++) {
    if (i % 31 === 0) keep.set(text, pieces.join(""));
    text += unit;
    pieces.push(unit);
  }
  equal(text, pieces.join(""), "local rope append");
  for (const [key, value] of keep) {
    equal(key, value, "shared rope contents");
    equal(keep.get(value), value, "shared rope hash");
  }
}

// Long left/right/balanced trees, live aliases, rebalancing and flatten consumers.
for (let wide of [false, true]) {
  let pieces = [],
    snapshots = [],
    chain = "";
  for (let i = 0; i < 12000; ++i) {
    let part = String.fromCharCode((wide ? 0x400 : 97) + (i % 26));
    pieces.push(part);
    chain = chain + part;
    if (i % 997 === 0) snapshots.push([chain, i + 1]);
    if (i % 1024 === 0) std.gc();
  }
  let expected = pieces.join("");
  equal(chain.length, expected.length);
  equal(chain, expected);
  for (let i = 0; i < chain.length; i += 197) {
    equal(chain.charCodeAt(i), expected.charCodeAt(i));
    equal(chain.slice(i, i + 17), expected.slice(i, i + 17));
  }
  for (let [value, length] of snapshots) {
    equal(value, expected.slice(0, length));
    equal(value.length, length);
  }
  let reverse = "";
  for (let i = pieces.length - 1; i >= 0; --i) reverse = pieces[i] + reverse;
  equal(reverse, expected);
  let nodes = pieces.slice();
  while (nodes.length > 1) {
    let next = [];
    for (let i = 0; i < nodes.length; i += 2)
      next.push(i + 1 < nodes.length ? nodes[i] + nodes[i + 1] : nodes[i]);
    nodes = next;
  }
  equal(nodes[0], expected);
  equal(JSON.parse(JSON.stringify({ value: chain })).value, expected);
  equal(new Map([[chain, 37]]).get(expected), 37);
  let object = {};
  object[chain] = 19;
  equal(object[expected], 19);
  equal(chain.concat("", nodes[0]).length, 24000);
  std.gc();
  equal(snapshots[1][0], expected.slice(0, snapshots[1][1]));
}

// Alias/self-concat, empty strings, embedded NUL and surrogate boundaries.
let self = "x";
for (let i = 0; i < 12; ++i) self = self + self;
equal(self.length, 4096);
equal(self, "x".repeat(4096));
for (let value of ["", "abc", "\u0000x", "\u03a9", "\ud800", "\udfff"]) {
  equal(value + "", value);
  equal("" + value, value);
}
let pair = "\ud83d" + "\ude80";
equal(pair.length, 2);
equal(pair.codePointAt(0), 0x1f680);
equal(pair.charCodeAt(1), 0xde80);
equal(JSON.stringify("\ud800" + "x"), '"\\ud800x"');
equal("a" + "\u0000" + "b", "a\u0000b");

// Original conversion order, abrupt completion, Symbol, BigInt and primitive mix.
let effects = [];
let left = {
  [Symbol.toPrimitive](hint) {
    effects.push("L:" + hint);
    std.gc();
    return "left";
  },
};
let right = {
  [Symbol.toPrimitive](hint) {
    effects.push("R:" + hint);
    std.gc();
    return "right";
  },
};
equal(left + right, "leftright");
equal(effects.join(","), "L:default,R:default");
effects = [];
let broken = {
  [Symbol.toPrimitive]() {
    effects.push("bad");
    throw new RangeError("stop");
  },
};
throwsType(() => broken + right, RangeError);
equal(effects.join(","), "bad");
throwsType(() => "x" + Symbol("s"), TypeError);
throwsType(() => Symbol("s") + "x", TypeError);
equal("x" + 123n, "x123");
equal(null + "x", "nullx");
equal("x" + undefined, "xundefined");
equal("x" + NaN, "xNaN");

let text = "ab" + "cd" + ("ef" + "gh");
equal(text.indexOf("cdef"), 2);
equal(text.replace(/cd(ef)/, "$1!"), "abef!gh");
equal(text.split("de").join("|"), "abc|fgh");
equal(/cdef/.test(text), true);
std.gc();
// Explicit assignment recurrence, retained aliases and both store stack effects.
function localRecurrence(wide, retain) {
  var base = "x".repeat(600),
    s = base + "a",
    saved = [],
    parts = [base, "a"];
  for (var i = 0; i < 2400; ++i) {
    s = s + String.fromCharCode((wide ? 0x400 : 97) + (i % 26));
    parts.push(String.fromCharCode((wide ? 0x400 : 97) + (i % 26)));
    if (retain && i % 199 === 0) saved.push([s, parts.length]);
    if (i % 503 === 0) std.gc();
  }
  equal(s, parts.join(""));
  for (var [value, count] of saved) equal(value, parts.slice(0, count).join(""));
  return s;
}
localRecurrence(false, false);
localRecurrence(true, false);
localRecurrence(false, true);
localRecurrence(true, true);
function localSetResult() {
  var base = "x".repeat(600),
    s = base + "a";
  var result = (s = s + "b");
  equal(result, base + "ab");
  equal(s, result);
  s = s + "c";
  equal(result, base + "ab");
  equal(s, base + "abc");
}
localSetResult();
function localRhsReentry() {
  var base = "x".repeat(600),
    s = base + "a";
  function change() {
    s = "changed";
    std.gc();
    return "b";
  }
  s = s + change();
  equal(s, base + "ab");
}
localRhsReentry();
print("CONCAT_ROPE_SMOKE_PASSED");
