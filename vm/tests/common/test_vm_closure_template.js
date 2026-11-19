import * as std from "qjs:std";
let checks = 0,
  collections = 0;
function check(value, why) {
  checks++;
  if (!value) throw Error("CLOSURE " + checks + ": " + why);
}
function collect() {
  collections++;
  std.gc();
}
function namedFactory(v) {
  return function retainedName(a, b) {
    return v + a + b;
  };
}
function arrowFactory(v) {
  return (a) => v + a;
}
function methods(v) {
  return {
    read(a) {
      return v + a;
    },
    get item() {
      return v;
    },
    set item(n) {
      v = n;
    },
  };
}
function asyncFactory(v) {
  return async function retainedAsync(a) {
    return v + a;
  };
}
function* generator(v) {
  yield v;
}
function generatorFactory(v) {
  return function* retainedGenerator() {
    yield v;
  };
}
for (let round = 0; round < 80; round++) {
  let f = namedFactory(round),
    g = namedFactory(round + 1000);
  check(f(2, 3) === round + 5 && g(2, 3) === round + 1005, "distinct capture cells");
  check(f.name === "retainedName" && f.length === 2, "initial name and length");
  check(Object.getOwnPropertyNames(f).join(",") === "length,name,prototype", "own property order");
  let nd = Object.getOwnPropertyDescriptor(f, "name"),
    ld = Object.getOwnPropertyDescriptor(f, "length");
  check(
    nd.configurable &&
      !nd.writable &&
      !nd.enumerable &&
      ld.configurable &&
      !ld.writable &&
      !ld.enumerable,
    "data descriptor recipe",
  );
  let fp = f.prototype,
    gp = g.prototype;
  check(fp !== gp && fp.constructor === f && gp.constructor === g, "lazy prototype per instance");
  let pd = Object.getOwnPropertyDescriptor(f, "prototype");
  check(pd.writable && !pd.configurable && !pd.enumerable, "prototype descriptor");
  check(Object.getPrototypeOf(new f(1, 2)) === fp, "constructor uses own prototype");
  Object.defineProperty(f, "name", { value: "changed" });
  Object.defineProperty(f, "length", { value: 97, writable: true });
  check(
    f.name === "changed" && f.length === 97 && g.name === "retainedName" && g.length === 2,
    "COW descriptors and values",
  );
  delete f.name;
  check(!Object.hasOwn(f, "name") && g.name === "retainedName", "delete does not mutate template");
  let h = namedFactory(round + 2000);
  check(
    h.name === "retainedName" && h.length === 2 && h(1, 2) === round + 2003,
    "fresh recipe after mutations",
  );
  h.extra = { back: h };
  h.prototype.extra = h;
  let arrow = arrowFactory(round);
  check(arrow(3) === round + 3 && !Object.hasOwn(arrow, "prototype"), "arrow shape");
  let object = methods(round);
  check(object.read(4) === round + 4 && object.item === round, "method capture");
  object.item = round + 7;
  check(object.item === round + 7, "setter closure");
  let desc = Object.getOwnPropertyDescriptor(object, "item");
  check(desc.get.name === "get item" && desc.set.name === "set item", "accessor names");
  let af = asyncFactory(round);
  check(
    af.name === "retainedAsync" && af.length === 1 && !Object.hasOwn(af, "prototype"),
    "async metadata",
  );
  let gen = generatorFactory(round),
    gg = generatorFactory(round + 1);
  check(gen.prototype !== gg.prototype && gen().next().value === round, "generator original path");
  let sym = Symbol("key"),
    o = {
      [sym](a) {
        return round + a;
      },
    };
  check(o[sym].name === "[key]" && o[sym](8) === round + 8, "computed symbol method name");
  let cl = class NamedClass {
    constructor(a) {
      this.a = a;
    }
    read() {
      return this.a + round;
    }
  };
  check(cl.name === "NamedClass" && new cl(9).read() === round + 9, "class path");
  f = g = h = arrow = object = af = gen = gg = o = cl = null;
  collect();
}
for (let n = 0; n < 32; n++) {
  let pair = (() => {
    let cell = { n };
    return [
      () => cell,
      () => {
        cell = null;
      },
    ];
  })();
  check(pair[0]().n === n, "captured owner before GC");
  collect();
  pair[1]();
  collect();
  check(pair[0]() === null, "mutable cell after GC");
  pair = null;
}
// Exercise both sides of the 256-byte object-plus-vector allocation bound.
for (const count of [0, 1, 22, 23, 40]) {
  const declarations = Array.from({ length: count }, (_, i) => `let v${i} = {n: ${i}};`).join("");
  const expression = Array.from({ length: count }, (_, i) => `v${i}.n`).join("+") || "0";
  const maker = Function(declarations + `return function held(){return ${expression};};`);
  for (let round = 0; round < 4; round++) {
    const closure = maker();
    collect();
    check(closure() === (count * (count - 1)) / 2, "capture vector boundary " + count);
  }
}
print("CLOSURE_SEMANTICS_OK checks=" + checks + " gc=" + collections);
