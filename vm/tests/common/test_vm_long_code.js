import * as std from "qjs:std";
function check(ok, message) {
  if (!ok) throw Error(message);
}
// Distinct code PCs on both sides of the old hint capacity; no shared hint plane.
for (const count of [32, 210, 230, 300, 400, 450, 700]) {
  const read = new Function("o", "v", "let r=0;" + "r += o.x;".repeat(count) + "v=v+1;return r+v;");
  const method = new Function("o", "let r=0;" + "r += o.f();".repeat(count) + "return r;");
  const write = new Function("o", "let r=0;" + "o.x=r;r=r+1;".repeat(count) + "return o.x;");
  for (let round = 0; round < 4; round++) {
    const proto = {
      x: round + 1,
      f() {
        return this.x;
      },
    };
    const object = Object.create(proto);
    check(read(object, 3) === count * (round + 1) + 4, "long prototype read");
    check(method(object) === count * (round + 1), "long method this");
    object.x = round + 2;
    check(read(object, 3) === count * (round + 2) + 4, "long own read");
    delete object.x;
    proto.x = round + 3;
    check(method(object) === count * (round + 3), "long proto invalidation");
    check(write(object) === count - 1, "long replacement and transition");
    check(read({ x: 2 }, 3) === count * 2 + 4, "long temporary receiver");
  }
  let accesses = 0;
  const object = {
    get x() {
      accesses++;
      if (accesses % 71 === 0) std.gc();
      return 2;
    },
  };
  check(read(object, 3) === count * 2 + 4 && accesses === count, "long getter GC/reentry");
  Object.defineProperty(object, "x", {
    get() {
      throw Error("long-code-throw");
    },
  });
  try {
    read(object, 3);
    throw Error("missing throw");
  } catch (error) {
    check(error.message === "long-code-throw", "long throw propagation");
  }
  check(read({ x: 3 }, 3) === count * 3 + 4, "long recovery");
}
print("long-code semantic fixtures passed");
