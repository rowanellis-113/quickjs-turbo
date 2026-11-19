/* MIT. Cold and guarded-fallback u/v empty advancement regression. */
"use strict";
let checks = 0,
  hash = 2166136261;
function equal(actual, expected) {
  const a = JSON.stringify(actual),
    b = JSON.stringify(expected);
  if (a !== b) throw Error(a + " != " + b);
  for (let i = 0; i < a.length; i++) hash = Math.imul(hash ^ a.charCodeAt(i), 16777619);
  checks++;
}
// No prototype.exec read or warm replacement may precede this operation.
const cold = new RegExp("", "gv");
cold.lastIndex = 7;
equal(RegExp.prototype[Symbol.replace].call(cold, "\ud83d\ude00x", ""), "\ud83d\ude00x");
equal(cold.lastIndex, 0);
const replace = RegExp.prototype[Symbol.replace],
  execute = RegExp.prototype.exec;
for (const pattern of ["", "a*", "a*?", "^", "$", "^|$", "(?=a)", "\\s*", ".?", "(?:a|b)*"])
  for (const flags of ["g", "gu", "gv", "gy", "guy", "gvy", "", "u", "v", "y", "uy", "vy", "dgv"])
    for (const input of [
      "",
      "ab",
      "\ud83d\ude00",
      "\ud83d\ude00a\ud83d\ude00b",
      "a\u0100b",
      "\ud800a\udc00",
    ])
      for (const index of [0, 7]) {
        const re = new RegExp(pattern, flags),
          reference = new RegExp(pattern, flags);
        re.lastIndex = reference.lastIndex = index;
        reference.exec = function (text) {
          return execute.call(this, text);
        };
        const expected = replace.call(reference, input, "");
        equal([replace.call(re, input, ""), re.lastIndex], [expected, reference.lastIndex]);
      }
print("REGEXP_REPLACE_UNICODE_COLD", checks, hash >>> 0);
