import * as std from "qjs:std";
function check(ok, message) {
  if (!ok) throw Error(message);
}
function linuxShortLiteral() {
  return /a\u{1f600}/guy;
}
const first = linuxShortLiteral(),
  second = linuxShortLiteral();
check(first !== second && first.source === second.source, "fresh literal identity");
first.lastIndex = 1;
check(
  second.lastIndex === 0 && first.test("za😀") && first.lastIndex === 4,
  "literal state/Unicode",
);
const plain = new Function(
  "o",
  "return function linuxLargePlain(o){let r=0;" + "r+=o.x;".repeat(1000) + "return r;}",
)();
const literal = new Function(
  "o",
  "return function linuxLargeLiteral(o){let r=0;" + "r+=o.x;".repeat(1000) + "return [r,/ab/gu];}",
)();
const loop = new Function(
  "return function linuxLargeLoop(o,n){let r=0;for(let j=0;j<n;j++){" +
    "r+=o.x;".repeat(4600) +
    "}return r;}",
)();
check(plain({ x: 2 }) === 2000, "plain large native cohort");
const a = literal({ x: 3 }),
  b = literal({ x: 4 });
check(a[0] === 3000 && b[0] === 4000 && a[1] !== b[1], "large literal identity");
a[1].lastIndex = 1;
check(b[1].lastIndex === 0 && a[1].test("zab"), "large literal state");
check(loop({ x: 3 }, 2) === 27600 && loop({ x: 1 }, 0) === 0, "wide forward/backward branch");
let gets = 0;
const callback = {
  get x() {
    if (++gets % 113 === 0) {
      std.gc();
      check(std.evalScript("(function(){return 31})()") === 31, "GC/reentry");
    }
    return 2;
  },
};
check(literal(callback)[0] === 2000 && gets === 1000, "large getter GC roots");
Object.defineProperty(callback, "x", {
  get() {
    if (++gets === 1700) throw Error("large expected");
    return 1;
  },
});
let caught = false;
try {
  literal(callback);
} catch (error) {
  caught = error.message === "large expected";
}
check(caught && literal({ x: 1 })[0] === 1000, "exception unwind/recovery");
const beyond = new Function("o", "let r=0;" + "r+=o.x;".repeat(9000) + "return r;");
check(beyond({ x: 2 }) === 18000, "over64KiB original fallback");
print("LINUX_ADMISSION_OK");
