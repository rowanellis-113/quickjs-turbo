"use strict";
function LE_assert(v, m) {
  if (!v) throw Error(m);
}
function LE_run(n) {
  const constants = [
    () => -1,
    () => 0,
    () => 1,
    () => 2,
    () => 3,
    () => 4,
    () => 5,
    () => 6,
    () => 7,
    () => undefined,
    () => null,
    () => false,
    () => true,
    function () {},
  ];
  const expected = [-1, 0, 1, 2, 3, 4, 5, 6, 7, undefined, null, false, true, undefined];
  const identity = [
    function (a) {
      return a;
    },
    function (a, b) {
      return b;
    },
    function (a, b, c) {
      return c;
    },
    function (a, b, c, d) {
      return d;
    },
  ];
  const arithmetic = [
    function (a) {
      return a + 3;
    },
    function (a, b) {
      return b + -1;
    },
    function (a, b) {
      return a + b;
    },
    function (a, b) {
      return b + a;
    },
  ];
  const receiver = {
    f: function (a) {
      return a + 3;
    },
  };
  function tail(a) {
    return receiver.f(a);
  }
  function closureFactory(x) {
    return (y) => x + y;
  }
  const closure = closureFactory(11);
  let sum = 0;
  for (let round = 0; round < n; round++)
    for (let i = 0; i < 64; i++) {
      for (let j = 0; j < constants.length; j++)
        LE_assert(Object.is(constants[j](42), expected[j]), "constant " + j);
      for (let j = 0; j < identity.length; j++) {
        const args = [{ i }, ["v"], function () {}, "abc"];
        LE_assert(identity[j](...args) === args[j], "identity " + j);
        LE_assert(identity[j]() === undefined, "missing identity " + j);
      }
      LE_assert(arithmetic[0](5) === 8 && arithmetic[1](1, 5) === 4, "small addition");
      LE_assert(arithmetic[2](3, 5) === 8 && arithmetic[3](3, 5) === 8, "arg addition");
      LE_assert(arithmetic[0](2147483647) === 2147483650, "overflow");
      LE_assert(arithmetic[0](-0) === 3 && arithmetic[0](0.25) === 3.25, "double");
      LE_assert(arithmetic[0]("x") === "x3", "string coercion");
      let conversions = 0;
      const coercer = {
        valueOf() {
          conversions++;
          return 9;
        },
      };
      LE_assert(arithmetic[0](coercer) === 12 && conversions === 1, "coercion callback");
      try {
        arithmetic[0](Symbol());
        throw Error("missing throw");
      } catch (e) {
        LE_assert(e instanceof TypeError, "symbol throw");
      }
      LE_assert(tail(5) === 8 && receiver.f(7) === 10, "method/tail");
      LE_assert(closure(4) === 15, "closure fallback");
      LE_assert(arithmetic[0].bind(null, 2)() === 5, "bound fallback");
      let applies = 0;
      const proxied = new Proxy(arithmetic[0], {
        apply(t, th, a) {
          applies++;
          return Reflect.apply(t, th, a);
        },
      });
      LE_assert(proxied(5) === 8 && applies === 1, "proxy fallback");
      const resource = { self: null, v: 42 };
      resource.self = resource;
      const passed = identity[0](resource);
      LE_assert(passed === resource && passed.self === resource, "cycle identity");
      function capture(a) {
        return function () {
          return a;
        };
      }
      LE_assert(capture(resource)() === resource, "captured args");
      function local(a) {
        let b = a + 1;
        return b;
      }
      LE_assert(local(4) === 5, "locals fallback");
      sum = (sum + arithmetic[0](i) + arithmetic[2](i, 3) + tail(i)) | 0;
    }
  return sum;
}
globalThis.frameCases = { semantics: LE_run };
if (typeof scriptArgs !== "undefined")
  console.log(JSON.stringify({ checksum: LE_run(3), status: "passed" }));

if (typeof scriptArgs === "undefined") {
  const result = globalThis.frameCases.semantics(3);
  if (result !== 19872) throw new Error("upgrade semantic checksum " + result);
}
