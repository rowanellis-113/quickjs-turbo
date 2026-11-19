import * as std from "qjs:std";
function check(ok, message) {
  if (!ok) throw Error(message);
}
// A qualifying slab close to1024sites;prototype mutation and callback roots.
const count = 993;
const read = new Function("o", "let r=0;" + "r+=o.x;".repeat(count) + "return r;");
for (let round = 0; round < 3; round++) {
  const proto = { x: round + 1 };
  const object = Object.create(proto);
  check(read(object) === count * (round + 1), "large prototype");
  object.x = round + 2;
  check(read(object) === count * (round + 2), "large own");
  delete object.x;
  proto.x = round + 3;
  std.gc();
  check(read(object) === count * (round + 3), "large prototype change/GC");
}
let calls = 0;
const getter = {
  get x() {
    calls++;
    if (calls % 113 === 0) {
      std.gc();
      check(std.evalScript("1+2") === 3, "getter reentry");
    }
    return 2;
  },
};
check(read(getter) === 2 * count && calls === count, "large getter count");
Object.defineProperty(getter, "x", {
  get() {
    if (++calls === count + 730) throw Error("large-getter-throw");
    return 2;
  },
});
let caught = false;
try {
  read(getter);
} catch (e) {
  caught = e.message === "large-getter-throw";
}
check(caught, "exception beyond4K");
check(read({ x: 3 }) === 3 * count, "large recovery");
// Branches cross signed16-bit range;site count exceeds PIC1024 limit.
const loopCount = 4600;
const loop = new Function(
  "o",
  "n",
  "let r=0;for(let i=0;i<n;i++){" + "r+=o.x;".repeat(loopCount) + "}return r;",
);
check(loop({ x: 3 }, 2) === loopCount * 6, "large forward/backward branch");
check(loop({ x: 9 }, 0) === 0, "large skipped branch");
let loopGets = 0;
const callback = {
  get x() {
    if (++loopGets % 257 === 0) std.gc();
    return 1;
  },
};
check(loop(callback, 1) === loopCount && loopGets === loopCount, "large disabled-PIC callback");
const writeCount = 1300;
const write = new Function(
  "o",
  "v",
  "let r=v;" + "o.x=r;r=r+1;".repeat(writeCount) + "return o.x;",
);
const target = {};
check(write(target, 7) === 7 + writeCount - 1, "large transitions/replacements");
let last = 0,
  sets = 0;
const accessor = {
  set x(v) {
    last = v;
    if (++sets % 101 === 0) std.gc();
  },
  get x() {
    return last;
  },
};
check(write(accessor, 11) === 11 + writeCount - 1 && sets === writeCount, "large setter callback");
const iter = new Function(
  "o",
  "let r=0;for(const n of [1,2]){" + "r+=o.x+n;".repeat(700) + "}return Math.max(...[r,7]);",
);
check(iter({ x: 1 }) === 3500, "large for-of/spread");
// General cap and independent NULL_PROTO eligibility must safely fall back.
const beyond = new Function("o", "let r=0;" + "r+=o.x;".repeat(9000) + "return r;");
check(beyond({ x: 2 }) === 18000, "over64K fallback");
const nullProto = new Function(
  "let o={__proto__:null,x:1};let r=0;" +
    "r+=o.x;".repeat(1000) +
    "return [r,Object.getPrototypeOf(o)];",
);
const answer = nullProto();
check(answer[0] === 1000 && answer[1] === null, "long null-prototype fallback");
// Global reads beyond the old4KiB admission limit;all cache policies must
// observe current bindings and TDZ through the inherited full resolver.
std.evalScript("let __frameLargeMutable=5;let __frameLargeObject={x:3};");
const globalRead = new Function(
  "let r=0;" + "r+=__frameLargeMutable+__frameLargeObject.x;".repeat(500) + "return r;",
);
check(globalRead() === 4000, "large lexical binding");
std.evalScript("__frameLargeMutable=8;__frameLargeObject={x:4};");
std.gc();
check(globalRead() === 6000, "large current lexical value/GC");
let tdz = false;
try {
  std.evalScript("let __frameLargeTDZ=__frameLargeTDZ;");
} catch (e) {
  tdz = e instanceof ReferenceError;
}
check(tdz, "TDZ setup");
const readTDZ = new Function(
  "let r=0;" + "r+=__frameLargeMutable;".repeat(700) + "return __frameLargeTDZ;",
);
tdz = false;
try {
  readTDZ();
} catch (e) {
  tdz = e instanceof ReferenceError;
}
check(tdz, "large lexical TDZ");

// A regexp opcode must compose with the existing large-code and iterator
// cohorts. Literal identity and live roots remain observable across callbacks.
const regexpRead = new Function(
  "o",
  "let r=0;const re=/a(?:b|c)+/gy;" + "r+=o.x;".repeat(count) + "return [r,re];",
);
const firstRegexp = regexpRead({ x: 2 });
check(firstRegexp[0] === 2 * count, "large regexp scalar body");
check(
  firstRegexp[1].exec("abcc")[0] === "abcc" && firstRegexp[1].lastIndex === 4,
  "large regexp sticky state",
);
const secondRegexp = regexpRead({ x: 3 });
check(
  secondRegexp[0] === 3 * count &&
    secondRegexp[1] !== firstRegexp[1] &&
    secondRegexp[1].lastIndex === 0,
  "large fresh literal identity",
);
let regexpGets = 0;
const regexpGetter = {
  get x() {
    if (++regexpGets % 113 === 0) {
      std.gc();
      check(std.evalScript("2+3") === 5, "large regexp getter reentry");
    }
    return 1;
  },
};
check(
  regexpRead(regexpGetter)[0] === count && regexpGets === count,
  "large regexp live local across getter/GC",
);
let regexpThrowGets = 0,
  regexpCaught = false;
try {
  regexpRead({
    get x() {
      if (++regexpThrowGets === 730) {
        std.gc();
        throw Error("large-regexp-throw");
      }
      return 1;
    },
  });
} catch (e) {
  regexpCaught = e.message === "large-regexp-throw";
}
check(
  regexpCaught && regexpRead({ x: 4 })[0] === 4 * count,
  "large regexp exception cleanup/recovery",
);
const regexpIter = new Function(
  "o",
  "let r=0;for(const n of [1,2]){" +
    "r+=o.x+n;".repeat(700) +
    "}return [Math.max(...[r,7]),/ab/g];",
);
const regexpIterResult = regexpIter({ x: 1 });
check(
  regexpIterResult[0] === 3500 && regexpIterResult[1].exec("zab").index === 1,
  "large regexp iterator/spread composition",
);
std.gc();

print("LARGE_CODE_SEMANTICS_OK");
