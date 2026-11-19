"use strict";
let checks = 0,
  closed = 0;
function check(ok, label) {
  checks++;
  if (!ok) throw Error(label);
}
class Numeric {
  constructor(x) {
    this.x = x + Symbol("x");
  }
}
class BadSetter {
  constructor() {
    Object.defineProperty(this, "x", {
      set() {
        gc();
        throw Error("setter");
      },
    });
    this.x = 3;
  }
}
class Coerce {
  constructor(x) {
    this.value = x + 1;
  }
}
class BadField {
  value = (() => {
    gc();
    throw Error("field");
  })();
}
class IteratorThrow {
  constructor() {
    for (const x of {
      [Symbol.iterator]() {
        return this;
      },
      next() {
        return { value: 7, done: false };
      },
      return() {
        closed++;
        gc();
        return {};
      },
    }) {
      throw Error("iter");
    }
  }
}
class ReturningThis {
  constructor(x) {
    this.x = x;
    return this;
  }
}
class ReturningCycle {
  constructor(x) {
    this.self = this;
    this.payload = { self: this };
    return { x: x };
  }
}
class SavedThis {
  constructor(x) {
    globalThis.saved = this;
    this.self = this;
    this.x = x;
    throw Error("saved");
  }
}
class Caught {
  constructor(x) {
    try {
      new Numeric(x);
    } catch (e) {
      this.numeric = e instanceof TypeError;
    }
    try {
      new BadSetter();
    } catch (e) {
      this.setter = e.message === "setter";
    }
    this.x = x;
  }
}
class InputIterator {
  constructor(input) {
    for (const x of input) {
      this.x = x;
      throw Error("input-iter");
    }
  }
}
class ClassCall {
  constructor() {
    try {
      Numeric.call(this, 1);
    } catch (e) {
      this.failed = e instanceof TypeError;
    }
  }
}
for (let i = 0; i < 64; i++) {
  for (const [C, message] of [
    [BadSetter, "setter"],
    [BadField, "field"],
    [IteratorThrow, "iter"],
  ]) {
    let caught = false;
    try {
      new C();
    } catch (e) {
      caught = e.message === message;
    }
    check(caught, message);
  }
  let caught = false;
  try {
    new Numeric(i);
  } catch (e) {
    caught = e instanceof TypeError;
  }
  check(caught, "numeric error");
  caught = false;
  try {
    new Coerce({
      [Symbol.toPrimitive]() {
        gc();
        throw Error("primitive");
      },
    });
  } catch (e) {
    caught = e.message === "primitive";
  }
  check(caught, "coercion error");
  let o = new Caught(i);
  check(o.numeric && o.setter && o.x === i, "catch in construct frame");
  caught = false;
  try {
    new InputIterator({
      [Symbol.iterator]() {
        return this;
      },
      next() {
        return { value: i, done: false };
      },
      return() {
        closed++;
        gc();
        return {};
      },
    });
  } catch (e) {
    caught = e.message === "input-iter";
  }
  check(caught, "input iterator close from construct frame");
  check(new ClassCall().failed, "class call rejection inside construct frame");
  o = new ReturningThis(i);
  check(o.x === i && o instanceof ReturningThis, "return this");
  o = new ReturningCycle(i);
  check(o.x === i, "discard cyclic this");
  gc();
  caught = false;
  try {
    new SavedThis(i);
  } catch (e) {
    caught = e.message === "saved";
  }
  check(caught && saved.x === i && saved.self === saved, "throw with escaped this");
  delete globalThis.saved;
  gc();
}
check(closed === 128, "iterator cleanup count");
gc();
print("CONSTRUCT_BOUNDARY_ERRORS_OK checks=" + checks);
