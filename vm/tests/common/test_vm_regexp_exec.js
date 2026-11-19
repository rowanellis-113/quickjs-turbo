/* Structural exec-result oracle. Not a timing workload. */
var checks = 0,
  hash = 2166136261;
function record(value) {
  var text = JSON.stringify(value);
  for (var i = 0; i < text.length; ++i) hash = Math.imul(hash ^ text.charCodeAt(i), 16777619) >>> 0;
  ++checks;
}
function snapshot(re, result) {
  if (result === null) return [null, String(re.lastIndex)];
  var keys = Object.getOwnPropertyNames(result),
    descriptors = [];
  for (var key of keys) {
    var d = Object.getOwnPropertyDescriptor(result, key);
    descriptors.push([
      key,
      d.writable,
      d.enumerable,
      d.configurable,
      Object.prototype.hasOwnProperty.call(d, "value"),
    ]);
  }
  var slots = [];
  for (var i = 0; i < result.length; ++i)
    slots.push([
      i in result,
      Object.prototype.hasOwnProperty.call(result, i),
      typeof result[i],
      result[i],
    ]);
  return [
    String(re.lastIndex),
    result.length,
    result.index,
    result.input,
    Object.getPrototypeOf(result) === Array.prototype,
    slots,
    descriptors,
    result.groups === undefined
      ? null
      : [Object.getPrototypeOf(result.groups) === null, result.groups],
    result.indices === undefined
      ? null
      : [
          result.indices,
          result.indices.groups === undefined
            ? null
            : [Object.getPrototypeOf(result.indices.groups) === null, result.indices.groups],
        ],
  ];
}
var patterns = [
  "",
  "a",
  "(a)?(b)",
  "(a)(b)(c)",
  "(?<x>a)?(?<y>b)",
  "((a|b)+)(c?)",
  "(?<=x)(a+)",
  "(a)\\1",
  "(?<=(a))b",
  "(?<a>a)|(?<b>b)",
  "(a*)*b",
  "[\\s\\S]+",
];
var flags = ["", "g", "y", "d", "dg", "dy", "i", "du", "v"];
var strings = [
  "",
  "a",
  "ab",
  "xab",
  "aaaaab",
  "\ud83d\ude00a",
  "\ud800a",
  "\udc00b",
  "a\nb",
  "ababab",
];
for (var pattern of patterns)
  for (var flag of flags)
    for (var input of strings) {
      var re;
      try {
        re = new RegExp(pattern, flag);
      } catch (e) {
        record(["compile", e.name]);
        continue;
      }
      for (var offset of [0, 1, 3, 100, 1.5, -1, Infinity, NaN]) {
        re.lastIndex = offset;
        record(snapshot(re, re.exec(input)));
      }
    }
for (var count of [0, 1, 14, 15, 16, 17, 31, 32, 64, 128]) {
  var source = "(a)".repeat(count) + "(b)?";
  for (var flag of ["", "d", "g", "dg", "du"]) {
    var re = new RegExp(source, flag);
    var result = re.exec("a".repeat(count));
    record(snapshot(re, result));
    if (result) {
      delete result[0];
      result.push("tail");
      result.length = Math.min(3, result.length);
      record([Object.keys(result), result.length, result.slice()]);
    }
  }
}
for (var flag of ["g", "y", "dg", "dy"]) {
  var re = new RegExp("(?<x>a)?(b)", flag);
  Object.defineProperty(re, "lastIndex", { writable: false });
  try {
    record(["readonly", snapshot(re, re.exec("ab"))]);
  } catch (e) {
    record(["readonly", e.name, re.lastIndex]);
  }
}
var setterCalls = 0,
  inheritedResult,
  inheritedError;
Object.defineProperty(Array.prototype, "0", {
  configurable: true,
  set: function () {
    ++setterCalls;
  },
});
try {
  inheritedResult = /(?<a>a)?(b)/d.exec("b");
} catch (e) {
  inheritedError = e.name;
} finally {
  delete Array.prototype[0];
}
record(["prototype-index", setterCalls, inheritedError, snapshot(/x/, inheritedResult)]);
var trace = [];
var reentrantInput = {
  toString: function () {
    trace.push("string");
    record(["inner", snapshot(/(?<x>a)/d, /(?<x>a)/d.exec("a"))]);
    if (typeof std === "object" && typeof std.gc === "function") std.gc();
    return "ab";
  },
};
var outer = /(?<x>a)(b)/dg;
outer.lastIndex = {
  valueOf: function () {
    trace.push("index");
    /a/.exec("a");
    return 0;
  },
};
record(["reentry", snapshot(outer, outer.exec(reentrantInput)), trace]);
for (var receiver of [{}, "a", null, new Proxy(/a/, {})]) {
  var observed = 0;
  try {
    RegExp.prototype.exec.call(receiver, {
      toString: function () {
        ++observed;
        return "a";
      },
    });
  } catch (e) {
    record(["receiver", e.name, observed]);
  }
}
for (var value of [undefined, null, 42, Symbol("x")]) {
  var re = /a/d;
  try {
    record(["input", snapshot(re, re.exec(value))]);
  } catch (e) {
    record(["input", e.name]);
  }
}
for (var method of [
  null,
  undefined,
  {},
  function () {
    return null;
  },
  function () {
    return {};
  },
]) {
  var re = /a/;
  re.exec = method;
  try {
    record(["override", re.test("a")]);
  } catch (e) {
    record(["override", e.name]);
  }
}
print("REGEXP_EXEC_RESULT " + JSON.stringify({ checks: checks, hash: hash }));

if (checks !== 8760 || hash !== 3904843604) throw Error("RegExp exec structural result changed");
