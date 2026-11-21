/* Cross-platform Map/Set string-key hashing, async output, and inline-object coverage. */
function check(ok, label) {
  if (!ok) throw new Error(label);
}

function stringKeys() {
  const left = "abcdefgh".repeat(60);
  const right = "\u6c34".repeat(60);
  const rope = left + right;
  const flat = (rope + "!").slice(0, 540);
  const map = new Map([[rope, 11]]);
  const set = new Set([flat]);
  for (let i = 0; i < 160; ++i) map.set("entry-" + i, i);
  check(map.get(flat) === 11 && set.has(rope), "flat/rope keys after resize");
  map.set(flat, 12);
  check(map.size === 161 && map.get(rope) === 12, "same key across representations");
  check([...map.keys()][0] === rope && map.delete(flat) && !map.has(rope), "iterator and delete");

  const longLeft = "\u0100".repeat(3500),
    longRight = "y".repeat(1000);
  const long = longLeft + longRight;
  check(new Set([long]).has((long + "!").slice(0, 4500)), "large rope is not required to flatten");

  let key = ["dynamic", "key"].join("-");
  const intern = new Map([[key, 23]]);
  check(Symbol(key).description === key && Symbol.for(key).description === key, "atomization");
  check(intern.get(["dynamic-", "key"].join("")) === 23, "symbol atom hash is not string hash");

  let scratch = ["before", "-"].join("");
  map.has(scratch);
  for (let i = 0; i < 300; i++) scratch += "x";
  const expected = "before-" + "x".repeat(300);
  check(new Map([[scratch, 5]]).get(expected) === 5, "hash after in-place concatenation");

  let tail = ["tail", "_"].join("");
  map.has(tail);
  let r = "head_" + tail;
  tail = null;
  for (let i = 0; i < 40; i++) r += "z";
  check(new Map([[r, 9]]).get("head_tail_" + "z".repeat(40)) === 9, "rope leaf append hash");

  map.set(NaN, 17).set(-0, 18).set(Symbol.for("sym"), 19);
  check(
    map.get(NaN) === 17 && map.get(+0) === 18 && map.get(Symbol.for("sym")) === 19,
    "SameValueZero for non-string keys",
  );
}

function objectPaths() {
  function literal(x) {
    return { a: x, b: 2, c: 3, d: 4, e: 5, f: 6, g: 7, h: 8 };
  }
  let keep = [];
  for (let i = 0; i < 160; ++i) {
    const o = literal(i);
    o.self = o;
    for (let j = 0; j < 10; ++j) o["e" + j] = { i, j };
    for (const name of ["b", "d", "e", "f", "g", "self"]) delete o[name];
    if ((i & 7) === 0) keep.push(o);
    check(o.a === i && o.e9.j === 9 && !("self" in o), "growth and compact");
    const packed = JSON.parse('{"a":0,"b":1,"c":2,"d":3,"e":4,"f":5}');
    check(packed.f === 5, "JSON transition");
  }
  const nullObject = { __proto__: null, a: 1 };
  nullObject.cycle = nullObject;
  keep = [];
  if (typeof std !== "undefined" && std.gc) std.gc();
  check(nullObject.cycle === nullObject && nullObject.a === 1, "null-object GC");
}

async function promisePaths() {
  let get = 0,
    call = 0;
  const thenable = {
    get then() {
      get++;
      return (resolve) => {
        call++;
        resolve(31);
      };
    },
  };
  async function run(x) {
    return x;
  }
  async function fail(x) {
    throw x;
  }
  async function awaited(x) {
    return (await x) + 1;
  }
  check((await run(7)) === 7, "primitive async return");
  check((await run(thenable)) === 31 && get === 1 && call === 1, "thenable async return");
  let caught = null;
  try {
    await fail("boom");
  } catch (e) {
    caught = e;
  }
  check(caught === "boom", "async throw");
  check((await awaited(41)) === 42, "awaited primitive");

  check((await Promise.resolve(99)) === 99, "Promise.resolve primitive");
  const p = Promise.resolve(5);
  check(Promise.resolve(p) === p, "Promise.resolve identity");

  class SubPromise extends Promise {}
  const sub = SubPromise.resolve(12);
  check(sub instanceof SubPromise && (await sub) === 12, "Promise subclass resolve");

  let order = [];
  const p1 = Promise.resolve(1).then((v) => order.push("a" + v));
  const p2 = run(2).then((v) => order.push("b" + v));
  await Promise.all([p1, p2]);
  check(order.join(",") === "a1,b2", "microtask ordering");
}

stringKeys();
objectPaths();
promisePaths().then(
  () => print("KEYED_ASYNC_FASTPATHS_OK"),
  (err) => {
    print("KEYED_ASYNC_FASTPATHS_FAIL: " + err);
    throw err;
  },
);
