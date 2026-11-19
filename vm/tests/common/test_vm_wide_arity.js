"use strict";
function WA_assert(v, m) {
  if (!v) throw Error(m);
}
function WA_function(formal, body) {
  const names = [];
  for (let i = 0; i < formal; i++) names.push("a" + i);
  return Function(...names, body);
}
const WA_forms = [5, 6, 16, 64, 128, 129];
const WA_read = WA_forms.map((n) => WA_function(n, "return a0;"));
const WA_write = WA_forms.map((n) => WA_function(n, "a0=a1;return a0;"));
const WA_missing = WA_forms.map((n) => WA_function(n, "return a" + (n - 1) + "===undefined;"));
const WA_numbers = WA_forms.map((n) =>
  WA_function(n, "a0=a0+1;return a0+(a" + (n - 1) + "===undefined?3:a" + (n - 1) + ");"),
);
const WA_wide16 = WA_numbers[2],
  WA_wide128 = WA_numbers[4];
const WA_read16 = WA_function(16, "return a0+(a15===undefined?3:a15);");
const WA_receiver = { f: WA_wide16 };
function WA_tail(x) {
  return WA_wide16(x);
}
function WA_semantics(n) {
  let sum = 0;
  for (let round = 0; round < n; round++)
    for (let i = 0; i < 48; i++) {
      const cycle = { v: i };
      cycle.self = cycle;
      const values = [cycle, "abc", function () {}, 13, undefined, null, Symbol("s")];
      for (let j = 0; j < WA_forms.length; j++) {
        for (const v of values) {
          WA_assert(WA_read[j](v) === v, "read " + WA_forms[j]);
          WA_assert(WA_write[j](0, v) === v, "write " + WA_forms[j]);
          WA_assert(WA_write[j](v, v) === v, "aliased owners " + WA_forms[j]);
        }
        WA_assert(WA_read[j]() === undefined, "zero actual " + WA_forms[j]);
        WA_assert(WA_missing[j](i), "missing tail " + WA_forms[j]);
        WA_assert(WA_numbers[j](i) === i + 4, "numeric " + WA_forms[j]);
        const all = Array(WA_forms[j]).fill(0);
        all[0] = i;
        all[all.length - 1] = 7;
        WA_assert(WA_numbers[j](...all) === i + 8, "full actual " + WA_forms[j]);
        // Callers with captured locals cannot pad across their capture table.
        function captured() {
          let held = cycle;
          function observe() {
            return held;
          }
          WA_assert(WA_read[j](observe()) === held, "captured caller");
          return held.v;
        }
        WA_assert(captured() === i, "capture survives");
        const capturedArg = WA_function(WA_forms[j], "return function(){return a0;};");
        WA_assert(capturedArg(cycle)() === cycle, "captured argument fallback");
      }
      WA_assert(WA_receiver.f(i) === i + 4 && WA_tail(i) === i + 4, "method/tail");
      WA_assert(WA_read16(2147483647) === 2147483650, "integer overflow");
      WA_assert(WA_read16(0.25) === 3.25, "double");
      const coercer = {
        valueOf() {
          const t = WA_wide16(3);
          WA_assert(t === 7, "coercion reentry");
          return 9;
        },
      };
      WA_assert(WA_numbers[2](coercer) === 13, "reentering coercion");
      try {
        WA_numbers[2](Symbol());
        throw Error("missing throw");
      } catch (e) {
        WA_assert(e instanceof TypeError, "throw");
      }
      const bound = WA_read[2].bind(null, cycle);
      WA_assert(bound() === cycle, "bound");
      const proxy = new Proxy(WA_read[2], {
        apply(t, th, a) {
          return Reflect.apply(t, th, a);
        },
      });
      WA_assert(proxy(cycle) === cycle, "proxy");
      sum = (sum + WA_wide16(i) + WA_tail(i)) | 0;
    }
  return sum;
}
const WA_bench = {
  wide_write16(n) {
    let s = 0;
    for (let i = 0; i < n; i++) s = (s + WA_wide16(i & 1023)) | 0;
    return s;
  },
  wide_read16(n) {
    let s = 0;
    for (let i = 0; i < n; i++) s = (s + WA_read16(i & 1023)) | 0;
    return s;
  },
  wide_write128(n) {
    let s = 0;
    for (let i = 0; i < n; i++) s = (s + WA_wide128(i & 1023)) | 0;
    return s;
  },
  wide_method16(n) {
    let s = 0;
    for (let i = 0; i < n; i++) s = (s + WA_receiver.f(i & 1023)) | 0;
    return s;
  },
  wide_tail16(n) {
    let s = 0;
    for (let i = 0; i < n; i++) s = (s + WA_tail(i & 1023)) | 0;
    return s;
  },
  semantics: WA_semantics,
};
globalThis.frameCases = WA_bench;
if (typeof scriptArgs !== "undefined")
  console.log(JSON.stringify({ checksum: WA_semantics(3), status: "passed" }));

if (typeof scriptArgs === "undefined") {
  const result = globalThis.frameCases.semantics(3);
  if (result !== 7920) throw new Error("upgrade semantic checksum " + result);
}
