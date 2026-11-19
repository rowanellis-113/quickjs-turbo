/* Side effects and abrupt completion for the upstream #1780 backport. */
const traces = [];
for (const kind of ["plain", "null", "rhs-throw", "compound", "super", "destructure"]) {
  let trace = [];
  const key = {
    [Symbol.toPrimitive]() {
      trace.push("key");
      return "p";
    },
  };
  const object = {
    get p() {
      trace.push("get");
      return 1;
    },
    set p(v) {
      trace.push("set:" + v);
    },
  };
  const rhs = () => {
    trace.push("rhs");
    if (kind === "rhs-throw") throw new RangeError("rhs");
    return 7;
  };
  try {
    if (kind === "plain" || kind === "rhs-throw") object[key] = rhs();
    else if (kind === "null") null[key] = rhs();
    else if (kind === "compound") object[key] += rhs();
    else if (kind === "super") {
      class Parent {
        set p(v) {
          trace.push("set:" + v);
        }
      }
      class Child extends Parent {
        run() {
          super[key] = rhs();
        }
      }
      new Child().run();
    } else {
      const source = {
        get q() {
          trace.push("source-get");
          return 9;
        },
      };
      ({ q: object[key] } = source);
    }
  } catch (e) {
    trace.push(e.name);
  }
  traces.push([kind, trace]);
}
const actual = JSON.stringify(traces);
print("COMPUTED_ASSIGN_SIGNATURE " + actual);
const expected = [
  ["plain", ["rhs", "key", "set:7"]],
  ["null", ["rhs", "key", "TypeError"]],
  ["rhs-throw", ["rhs", "RangeError"]],
  ["compound", ["key", "get", "rhs", "set:8"]],
  ["super", ["rhs", "key", "set:7"]],
  ["destructure", ["source-get", "key", "set:9"]],
];
if (actual !== JSON.stringify(expected))
  throw Error("computed assignment evaluation order differs");
