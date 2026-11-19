import * as std from "qjs:std";
// Differential fixture: complete observable results, descriptors and callback order.
const records = [];
function snapshot(a) {
  return {
    length: a.length,
    own: Object.getOwnPropertyNames(a)
      .map((k) => [k, Object.getOwnPropertyDescriptor(a, k)])
      .map(([k, d]) => [k, d.get ? "get" : d.value, d.writable, d.enumerable, d.configurable]),
  };
}
let seed = 987654321;
function random(n) {
  seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0;
  return seed % n;
}
let checksum = 0;
for (let round = 0; round < 1500; round++) {
  const a = Array.from({ length: random(90) }, (_, i) => i);
  const model = a.slice();
  for (let iter = 0; iter < 8; iter++) {
    const start = random(model.length + 13) - 6,
      del = random(10),
      n = random(13);
    const items = Array.from({ length: n }, (_, i) => round * 100 + i);
    const s = start < 0 ? Math.max(model.length + start, 0) : Math.min(start, model.length);
    const d = Math.min(del, model.length - s),
      old = model.slice(s, s + d);
    const next = model.slice(0, s).concat(items, model.slice(s + d));
    const removed = a.splice(start, del, ...items);
    if (
      JSON.stringify(a) !== JSON.stringify(next) ||
      JSON.stringify(removed) !== JSON.stringify(old)
    )
      throw Error("model " + round + ":" + iter);
    model.length = 0;
    for (const x of next) model.push(x);
    checksum = (checksum + a.length + removed.length) | 0;
  }
}
records.push(["fuzz", checksum]);
for (const mode of [
  "dense",
  "hole",
  "readonly",
  "sealed",
  "frozen",
  "accessor",
  "customProto",
  "proxy",
]) {
  let a = [0, 1, 2, 3, 4],
    events = [];
  if (mode === "hole") delete a[2];
  if (mode === "readonly") Object.defineProperty(a, "length", { writable: false });
  if (mode === "sealed") Object.seal(a);
  if (mode === "frozen") Object.freeze(a);
  if (mode === "accessor")
    Object.defineProperty(a, "3", {
      get() {
        events.push("get3");
        return 30;
      },
      set(v) {
        events.push("set3:" + v);
      },
      enumerable: true,
      configurable: true,
    });
  if (mode === "customProto")
    Object.setPrototypeOf(
      a,
      Object.create(Array.prototype, {
        6: {
          set(v) {
            events.push("proto6:" + v);
          },
          configurable: true,
        },
      }),
    );
  if (mode === "proxy")
    a = new Proxy(a, {
      get(t, k, r) {
        events.push("get:" + String(k));
        return Reflect.get(t, k, r);
      },
      set(t, k, v, r) {
        events.push("set:" + String(k));
        return Reflect.set(t, k, v, r);
      },
      has(t, k) {
        events.push("has:" + String(k));
        return Reflect.has(t, k);
      },
      deleteProperty(t, k) {
        events.push("delete:" + String(k));
        return Reflect.deleteProperty(t, k);
      },
    });
  let result, error;
  try {
    result = Array.prototype.splice.call(a, 1, 1, 10, 11, 12, 13);
  } catch (e) {
    error = e.name;
  }
  records.push([mode, result, error, snapshot(a), events]);
}
for (const mode of ["shrink", "reverse", "descriptor", "throw", "returnReceiver", "outputProxy"]) {
  const a = [0, 1, 2, 3, 4],
    events = [];
  a.constructor = {
    get [Symbol.species]() {
      events.push("species");
      if (mode === "throw") throw Error("species");
      return function (n) {
        events.push("construct:" + n);
        if (mode === "shrink") a.length = 2;
        if (mode === "reverse") a.reverse();
        if (mode === "descriptor")
          Object.defineProperty(a, "2", {
            get() {
              events.push("get2");
              return 20;
            },
            set(v) {
              events.push("set2:" + v);
            },
            configurable: true,
          });
        if (mode === "returnReceiver") return a;
        if (mode === "outputProxy")
          return new Proxy(
            {},
            {
              defineProperty(t, k, d) {
                events.push("define:" + k);
                return Reflect.defineProperty(t, k, d);
              },
              set(t, k, v, r) {
                events.push("outputSet:" + k);
                return Reflect.set(t, k, v, r);
              },
            },
          );
        std.gc();
        return new Array(n);
      };
    },
  };
  let removed, error;
  try {
    removed = a.splice(1, 1, 10, 11, 12);
  } catch (e) {
    error = e.name;
  }
  delete a.constructor;
  records.push([
    "species-" + mode,
    removed === a ? "receiver" : removed,
    error,
    snapshot(a),
    events,
  ]);
}
{
  const a = [0, 1, 2, 3],
    events = [];
  const start = {
    valueOf() {
      events.push("start");
      a.reverse();
      std.gc();
      return 1;
    },
  };
  const del = {
    valueOf() {
      events.push("delete");
      a.push(4);
      return 1;
    },
  };
  const r = a.splice(start, del, 7, 8, 9);
  records.push(["conversion", a, r, events]);
}
{
  const a = [{ id: 0 }, { id: 1 }, { id: 2 }];
  a.push(a);
  const x = a[1];
  const r = a.splice(1, 1, x, x, x);
  if (a[1] !== x || a[2] !== x || a[3] !== x || r[0] !== x || a[a.length - 1] !== a)
    throw Error("reference transfer");
  std.gc();
  records.push(["alias", a.length, r.length, a.map((x) => (x === a ? "self" : x.id))]);
}
{
  const a = [1, 2, 3];
  records.push(["zero", a.splice(), a.splice(1), a]);
  const b = new Uint8Array([1, 2, 3]);
  let e;
  try {
    Array.prototype.splice.call(b, 1, 0, 4, 5);
  } catch (x) {
    e = x.name;
  }
  records.push(["typed", Array.from(b), e]);
  const c = { 0: "a", 1: "b", length: 2 };
  records.push(["generic", Array.prototype.splice.call(c, 1, 0, "x", "y"), c]);
}
// Inherited indexed setters are observable; no fast growth may bypass them.
{
  const values = [undefined, null, true, false, 1, 1.5, NaN, "abc", Symbol("s"), 123n, {}, () => 7];
  for (let k = 0; k < 1000; k++) {
    const a = values.slice(),
      r = a.splice(2, 2, ...values);
    for (let i = 0; i < values.length; i++)
      if (!Object.is(a[i + 2], values[i])) throw Error("value kind " + i);
    if (r[0] !== true || r[1] !== false || a.length !== values.length * 2 - 2)
      throw Error("deleted ownership");
  }
  std.gc();
  records.push(["value kinds", values.length]);
  const a = [];
  a.length = 2147483648;
  a.splice(a.length, 0, 7, 8);
  records.push(["large length", a.length, a[2147483648], a[2147483649]]);
}
{
  const events = [],
    a = [0, 1, 2];
  Object.defineProperty(Array.prototype, "5", {
    set(v) {
      events.push("5=" + v);
    },
    configurable: true,
  });
  let removed, error;
  try {
    removed = a.splice(0, 0, 7, 8, 9);
  } catch (e) {
    error = e.name;
  }
  delete Array.prototype[5];
  records.push(["prototype", a, removed, error, events]);
}
const expected = [
  ["fuzz", 707144],
  [
    "dense",
    [1],
    null,
    {
      length: 8,
      own: [
        ["0", 0, true, true, true],
        ["1", 10, true, true, true],
        ["2", 11, true, true, true],
        ["3", 12, true, true, true],
        ["4", 13, true, true, true],
        ["5", 2, true, true, true],
        ["6", 3, true, true, true],
        ["7", 4, true, true, true],
        ["length", 8, true, false, false],
      ],
    },
    [],
  ],
  [
    "hole",
    [1],
    null,
    {
      length: 8,
      own: [
        ["0", 0, true, true, true],
        ["1", 10, true, true, true],
        ["2", 11, true, true, true],
        ["3", 12, true, true, true],
        ["4", 13, true, true, true],
        ["6", 3, true, true, true],
        ["7", 4, true, true, true],
        ["length", 8, true, false, false],
      ],
    },
    [],
  ],
  [
    "readonly",
    null,
    "TypeError",
    {
      length: 5,
      own: [
        ["0", 0, true, true, true],
        ["1", 1, true, true, true],
        ["2", 2, true, true, true],
        ["3", 3, true, true, true],
        ["4", 4, true, true, true],
        ["length", 5, false, false, false],
      ],
    },
    [],
  ],
  [
    "sealed",
    null,
    "TypeError",
    {
      length: 5,
      own: [
        ["0", 0, true, true, false],
        ["1", 1, true, true, false],
        ["2", 2, true, true, false],
        ["3", 3, true, true, false],
        ["4", 4, true, true, false],
        ["length", 5, true, false, false],
      ],
    },
    [],
  ],
  [
    "frozen",
    null,
    "TypeError",
    {
      length: 5,
      own: [
        ["0", 0, false, true, false],
        ["1", 1, false, true, false],
        ["2", 2, false, true, false],
        ["3", 3, false, true, false],
        ["4", 4, false, true, false],
        ["length", 5, false, false, false],
      ],
    },
    [],
  ],
  [
    "accessor",
    [1],
    null,
    {
      length: 8,
      own: [
        ["0", 0, true, true, true],
        ["1", 10, true, true, true],
        ["2", 11, true, true, true],
        ["3", "get", null, true, true],
        ["4", 13, true, true, true],
        ["5", 2, true, true, true],
        ["6", 30, true, true, true],
        ["7", 4, true, true, true],
        ["length", 8, true, false, false],
      ],
    },
    ["get3", "set3:12"],
  ],
  [
    "customProto",
    [1],
    null,
    {
      length: 8,
      own: [
        ["0", 0, true, true, true],
        ["1", 10, true, true, true],
        ["2", 11, true, true, true],
        ["3", 12, true, true, true],
        ["4", 13, true, true, true],
        ["5", 2, true, true, true],
        ["7", 4, true, true, true],
        ["length", 8, true, false, false],
      ],
    },
    ["proto6:3"],
  ],
  [
    "proxy",
    [1],
    null,
    {
      length: 8,
      own: [
        ["0", 0, true, true, true],
        ["1", 10, true, true, true],
        ["2", 11, true, true, true],
        ["3", 12, true, true, true],
        ["4", 13, true, true, true],
        ["5", 2, true, true, true],
        ["6", 3, true, true, true],
        ["7", 4, true, true, true],
        ["length", 8, true, false, false],
      ],
    },
    [
      "get:length",
      "get:constructor",
      "has:1",
      "get:1",
      "has:4",
      "get:4",
      "set:7",
      "has:3",
      "get:3",
      "set:6",
      "has:2",
      "get:2",
      "set:5",
      "set:1",
      "set:2",
      "set:3",
      "set:4",
      "set:length",
      "get:length",
    ],
  ],
  [
    "species-shrink",
    [1],
    null,
    {
      length: 7,
      own: [
        ["0", 0, true, true, true],
        ["1", 10, true, true, true],
        ["2", 11, true, true, true],
        ["3", 12, true, true, true],
        ["length", 7, true, false, false],
      ],
    },
    ["species", "construct:1"],
  ],
  [
    "species-reverse",
    [3],
    null,
    {
      length: 7,
      own: [
        ["0", 4, true, true, true],
        ["1", 10, true, true, true],
        ["2", 11, true, true, true],
        ["3", 12, true, true, true],
        ["4", 2, true, true, true],
        ["5", 1, true, true, true],
        ["6", 0, true, true, true],
        ["length", 7, true, false, false],
      ],
    },
    ["species", "construct:1"],
  ],
  [
    "species-descriptor",
    [1],
    null,
    {
      length: 7,
      own: [
        ["0", 0, true, true, true],
        ["1", 10, true, true, true],
        ["2", "get", null, true, true],
        ["3", 12, true, true, true],
        ["4", 20, true, true, true],
        ["5", 3, true, true, true],
        ["6", 4, true, true, true],
        ["length", 7, true, false, false],
      ],
    },
    ["species", "construct:1", "get2", "set2:11"],
  ],
  [
    "species-throw",
    null,
    "Error",
    {
      length: 5,
      own: [
        ["0", 0, true, true, true],
        ["1", 1, true, true, true],
        ["2", 2, true, true, true],
        ["3", 3, true, true, true],
        ["4", 4, true, true, true],
        ["length", 5, true, false, false],
      ],
    },
    ["species"],
  ],
  [
    "species-returnReceiver",
    "receiver",
    null,
    {
      length: 7,
      own: [
        ["0", 1, true, true, true],
        ["1", 10, true, true, true],
        ["2", 11, true, true, true],
        ["3", 12, true, true, true],
        ["length", 7, true, false, false],
      ],
    },
    ["species", "construct:1"],
  ],
  [
    "species-outputProxy",
    { 0: 1, length: 1 },
    null,
    {
      length: 7,
      own: [
        ["0", 0, true, true, true],
        ["1", 10, true, true, true],
        ["2", 11, true, true, true],
        ["3", 12, true, true, true],
        ["4", 2, true, true, true],
        ["5", 3, true, true, true],
        ["6", 4, true, true, true],
        ["length", 7, true, false, false],
      ],
    },
    ["species", "construct:1", "define:0", "outputSet:length", "define:length"],
  ],
  ["conversion", [3, 7, 8, 9, 1, 0], [2], ["start", "delete"]],
  ["alias", 6, 1, [0, 1, 1, 1, 2, "self"]],
  ["zero", [], [2, 3], [1]],
  ["typed", [1, 4, 5], "TypeError"],
  ["generic", [], { 0: "a", 1: "x", 2: "y", 3: "b", length: 4 }],
  ["value kinds", 12],
  ["large length", 2147483650, 7, 8],
  ["prototype", [7, 8, 9, 0, 1, null], [], null, ["5=2"]],
];
if (JSON.stringify(records) !== JSON.stringify(expected))
  throw Error("splice observable behavior changed");
print("array splice model and observable cases passed");
