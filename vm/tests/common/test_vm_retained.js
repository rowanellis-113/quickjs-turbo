// Combined-source smoke gate: exercise interactions across the retained bundle.
function same(actual, expected) {
  if (!Object.is(actual, expected))
    throw new Error(`expected ${String(expected)}, got ${String(actual)}`);
}
function sum(a, b) {
  return a + b;
}
function forward() {
  return sum.apply(null, arguments);
}
function missing(a, b = 7) {
  return a + b;
}
function mapped(a) {
  arguments[0] = a + 1;
  return a;
}
function factory(x) {
  return (y) => x + y;
}
const frozen = Object.freeze([3, 4]);
for (let i = 0; i < 300; i++) {
  same(sum(3, 4), 7);
  same(forward(3, 4), 7);
  same(sum.apply(null, frozen), 7);
  same(missing(3), 10);
  // Modules are strict: writing arguments does not change the parameter.
  same(mapped(3), 3);
  same(factory(i)(2), i + 2);
  const object = { x: i, y: i + 1 };
  same(object.x + object.y, 2 * i + 1);
  same("latin-text".indexOf("text"), 6);
  same("latin-text".indexOf("missing"), -1);
  same("abc".charCodeAt(1), 98);
  same("abc".charAt(2), "c");
  same("\u4e2d\u6587".charCodeAt(0), 0x4e2d);
  const text = "abca\u4e2d\ud83d\ude00";
  const index = i % text.length;
  same(text[index], text.charAt(index));
  same(text[4].charCodeAt(0), 0x4e2d);
  same(text[5].charCodeAt(0), 0xd83d);
  same(text[-1], undefined);
  same(text[text.length], undefined);
  // Arithmetic can leave integral indices boxed as doubles (for example
  // after Math.min in substr's reference implementation). Their tag check
  // must reach the general conversion path before the cached string entry.
  const doubleIndex = Math.min(0, 2) + (i % 2);
  same("ab"[doubleIndex], "ab".charAt(i % 2));
  same("ab"[0.5], undefined);
  same("ab"[NaN], undefined);
  same("ab"[Infinity], undefined);
  same("12" == 12, true);
  same(0n == 0, true);
  same(null == undefined, true);
  same("12" === 12, false);
  same(NaN === NaN, false);
  same(-0 === 0, true);
  same(typeof null, "object");
  same(typeof sum, "function");
  same(typeof 1n, "bigint");
  same(!0, true);
  same(!!{}, true);
  const regex = /a(b+)/g;
  same(regex.test("abbb"), true);
  same(regex.lastIndex, 4);
  same(regex.test("abbb"), false);
  same(regex.lastIndex, 0);
  const tree = { x: [i, "two", true, null], text: "\u4e2d\u6587\ud800" };
  const copy = JSON.parse(JSON.stringify(tree));
  same(copy.x[0], i);
  same(copy.x[1], "two");
  same(copy.text, tree.text);
}
let converted = 0;
same(
  {
    valueOf() {
      converted++;
      return 12;
    },
  } == "12",
  true,
);
same(converted, 1);
let caught = 0;
try {
  (() => {
    throw new Error("reentry");
  })();
} catch (e) {
  caught++;
}
const cycle = {};
cycle.self = cycle;
try {
  JSON.stringify(cycle);
} catch (e) {
  if (e instanceof TypeError) caught++;
}
same(caught, 2);
// The 0.15.1 caller supplies CESU-8 for v-mode patterns. Raw astral literals,
// class atoms and constructor input must agree with escaped Unicode atoms.
const astral = "\ud842\udfb7";
for (const re of [/\u{20bb7}/v, /𠮷/v, /[𠮷]/v, new RegExp(astral, "v")]) {
  const match = re.exec(astral + "a");
  same(match[0], astral);
  same(match.index, 0);
}
same(/\ud842/v.test(astral), false);
same(/\ud842/v.test("\ud842"), true);
same(new RegExp("\ud842x", "v").test("\ud842x"), true);
same(/\ud842\udfb7/.test(astral), true);
// Empty global v matches must progress over the full surrogate pair. Bound
// iterator pulls so a regression fails without constructing an infinite array.
for (const flag of ["u", "v"]) {
  const text = astral + "a";
  const it = text.matchAll(new RegExp("(?:)", "g" + flag));
  for (const index of [0, 2, 3]) {
    const item = it.next();
    same(item.done, false);
    same(item.value.index, index);
  }
  same(it.next().done, true);
  function checkedRegex() {
    const rx = new RegExp("(?:)", "g" + flag);
    let calls = 0;
    rx.exec = function (input) {
      if (++calls > 8) throw new Error("empty regexp failed to progress");
      return RegExp.prototype.exec.call(this, input);
    };
    return rx;
  }
  same(text.match(checkedRegex()).length, 3);
  same(text.replace(checkedRegex(), "-"), "-" + astral + "-a-");
  same(
    text.replace(checkedRegex(), () => "-"),
    "-" + astral + "-a-",
  );
  const parts = text.split(new RegExp("(?:)", flag));
  same(parts.length, 2);
  same(parts[0], astral);
  same(parts[1], "a");
}
print("retained bundle smoke: OK");
