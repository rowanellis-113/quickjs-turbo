/* Function constructors keep mapped cases non-strict under the CLI module mode. */
let checks = 0;
function check(v, m) {
  checks++;
  if (!v) throw Error(m);
}
const mapped = Function("a", "b", "a+=1;arguments[1]+=2;return [arguments[0],b,arguments.length]");
function strict(a, b) {
  "use strict";
  a += 1;
  arguments[1] += 2;
  return [arguments[0], b, arguments.length];
}
function missing(a, b, c, d, e, f, g, h, i, j) {
  "use strict";
  let out = arguments;
  gc();
  return [out.length, out[0], j];
}
function captured(f, v) {
  let keep = 7;
  let hold = () => keep;
  let out = f(v);
  check(hold() === 7, "parent capture");
  return out;
}
function complete(f, a, b) {
  let out = f(a, b);
  return out;
}
const escaped = Function("a", "b", "let out=arguments;return [out,()=>[a,b]]");
function strictEscaped(a, b) {
  "use strict";
  let out = arguments;
  a = 99;
  return out;
}
function invoke(fn) {
  return arguments[0]();
}
function receiver() {
  return this.length;
}
function forwarded(f, v) {
  let out = f.call(null, v, v + 1);
  return out;
}
function deep(n, f, v) {
  let out = n ? deep(n - 1, f, v) : captured(f, v);
  return out;
}
const ArgC = Function("a", "b", "this.n=arguments.length;a+=1;this.a=arguments[0];this.b=b");
function StrictC(a, b) {
  "use strict";
  this.n = arguments.length;
  a += 1;
  this.a = arguments[0];
  this.b = b;
}
function ObjectC(a) {
  let out = arguments;
  return { a: out[0], n: out.length };
}
function NewTargetC(a) {
  this.target = new.target;
  this.a = arguments[0];
}
function construct(C, v) {
  let out = new C(v, v + 1);
  return out;
}
function failing(a) {
  "use strict";
  let owner = arguments;
  gc();
  if (owner[0] !== a) throw Error("owner");
  throw Error("arg-error");
}
for (let i = 0; i < 64; i++) {
  let out = mapped(i, i + 1);
  check(out[0] === i + 1 && out[1] === i + 3 && out[2] === 2, "mapped alias");
  out = strict(i, i + 1);
  check(out[0] === i && out[1] === i + 1 && out[2] === 2, "strict snapshot");
  out = complete(mapped, i, i + 1);
  check(out[0] === i + 1 && out[1] === i + 3 && out[2] === 2, "native complete mapped");
  out = complete(strict, i, i + 1);
  check(out[0] === i && out[1] === i + 1 && out[2] === 2, "native complete strict");
  out = captured(missing, i);
  check(out[0] === 1 && out[1] === i && out[2] === undefined, "missing original argc");
  out = forwarded(mapped, i);
  check(out[0] === i + 1 && out[1] === i + 3 && out[2] === 2, "forwarded mapped");
  out = mapped.call.call(mapped, null, i, i + 1);
  check(out[0] === i + 1 && out[1] === i + 3, "logical wrappers");
  out = escaped(i, i + 1);
  let args = out[0],
    read = out[1];
  args[0] = i + 7;
  args[1] = i + 9;
  gc();
  let values = read();
  check(values[0] === i + 7 && values[1] === i + 9, "escaped mapped references");
  delete args[0];
  args[0] = 999;
  check(read()[0] === i + 7, "detached deleted mapping");
  args = strictEscaped(i, i + 1);
  check(args[0] === i && args[1] === i + 1, "escaped unmapped");
  Object.defineProperty(args, "0", {
    get() {
      gc();
      return 31;
    },
    configurable: true,
  });
  check(args[0] === 31, "descriptor fallback");
  args.length = 3.5;
  check(args.length === 3.5, "double length");
  Object.defineProperty(args, "length", {
    get() {
      return 47;
    },
  });
  check(args.length === 47, "length accessor fallback");
  check(invoke(receiver) === 1, "get2 receiver");
  out = construct(ArgC, i);
  check(out.a === i + 1 && out.b === i + 1 && out.n === 2, "mapped constructor");
  out = construct(StrictC, i);
  check(out.a === i && out.b === i + 1 && out.n === 2, "strict constructor");
  out = construct(ObjectC, i);
  check(out.a === i && out.n === 2, "constructor heap return");
  out = construct(NewTargetC, i);
  check(out.target === NewTargetC && out.a === i, "new.target original fallback");
  try {
    failing(i);
    throw Error("missing exception");
  } catch (e) {
    check(e.message === "arg-error" && e.stack.includes("failing"), "argument exception stack");
  }
}
let out = deep(64, missing, 17);
check(out[0] === 1 && out[1] === 17, "grown argument chain");
check(
  (function () {
    return arguments.length;
  })() === 0,
  "zero actual args",
);
check(
  (function (a) {
    return arguments.length;
  })(1, 2, 3, 4) === 4,
  "extra actual args",
);
gc();
print("LINUX_ARGUMENTS_OK checks=" + checks);
