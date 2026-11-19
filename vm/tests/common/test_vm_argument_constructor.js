"use strict";
(() => {
  let checks = 0;
  function ok(value) {
    ++checks;
    if (!value) throw Error("argument constructor " + checks);
  }
  function collect() {
    if (typeof std !== "undefined" && std.gc) std.gc();
    else if (typeof gc === "function") gc();
  }
  function Basic(x) {
    this.value = arguments[0];
  }
  for (let i = 0; i < 1000; i++) ok(new Basic(i).value === i);
  function Primitive(x) {
    this.value = arguments[0];
    return 27;
  }
  ok(new Primitive(11).value === 11);
  let returned = { tag: 13 };
  function ObjectResult(x) {
    this.value = arguments[0];
    return returned;
  }
  ok(new ObjectResult(12) === returned);
  function ArgsResult(x) {
    arguments[0] = x + 2;
    return arguments;
  }
  let args = new ArgsResult(20);
  ok(args.length === 1 && args[0] === 22);
  function Captured(x) {
    this.read = () => x;
    x = arguments[0] + 1;
    collect();
  }
  let captured = new Captured(31);
  collect();
  ok(captured.read() === 32);
  function NewTarget(x) {
    this.value = arguments[0];
    this.target = new.target;
  }
  let target = new NewTarget(8);
  ok(target.target === NewTarget && target.value === 8);
  function Other() {}
  let other = Reflect.construct(NewTarget, [9], Other);
  ok(
    Object.getPrototypeOf(other) === Other.prototype && other.target === Other && other.value === 9,
  );
  // Warm ordinary calls before construction. A cached body rejection must
  // preserve new.target for both direct reads and an escaping arrow capture.
  function WarmTarget(x) {
    this.value = arguments[0];
    this.target = new.target;
    this.readTarget = () => new.target;
  }
  for (let i = 0; i < 64; i++) {
    let receiver = {};
    WarmTarget.call(receiver, i);
    ok(
      receiver.value === i && receiver.target === undefined && receiver.readTarget() === undefined,
    );
  }
  for (let i = 0; i < 64; i++) {
    let instance = i & 1 ? new WarmTarget(i) : Reflect.construct(WarmTarget, [i], Other);
    let expected = i & 1 ? WarmTarget : Other;
    collect();
    ok(instance.value === i && instance.target === expected && instance.readTarget() === expected);
  }
  // Different closures share bytecode while retaining live constructor
  // prototypes. Static admission must never cache either closure's prototype.
  function constructorFactory() {
    return function Shared(x) {
      this.value = arguments[0];
    };
  }
  let first = constructorFactory(),
    second = constructorFactory();
  for (let i = 0; i < 64; i++) {
    let Constructor = i & 1 ? first : second;
    Constructor.prototype = { iteration: i };
    let instance = new Constructor(i);
    ok(instance.value === i && instance.iteration === i);
    ok(Object.getPrototypeOf(instance) === Constructor.prototype);
  }
  // Exercise the argument descriptor's existing iterator/varargs controls
  // before and after repeated constructor admission.
  function Iterating() {
    this.total = 0;
    for (let value of arguments[0]) this.total += value;
    this.values = Array(...arguments[0]);
  }
  for (let i = 0; i < 64; i++) {
    let instance = new Iterating([i, i + 1]);
    ok(instance.total === 2 * i + 1 && instance.values.join() === [i, i + 1].join());
  }
  let getterCalls = 0,
    proto = { marker: 17 };
  let alternative = new Proxy(Other, {
    get(t, key, r) {
      if (key === "prototype") {
        ++getterCalls;
        collect();
        return proto;
      }
      return Reflect.get(t, key, r);
    },
  });
  let changed = Reflect.construct(Basic, [44], alternative);
  ok(Object.getPrototypeOf(changed) === proto && changed.value === 44 && getterCalls === 1);
  let setters = 0;
  function Setter(x) {
    this.value = arguments[0];
  }
  Object.defineProperty(Setter.prototype, "value", {
    set(x) {
      collect();
      ++setters;
      this.saved = x;
    },
  });
  let set = new Setter(51);
  ok(set.saved === 51 && setters === 1);
  function Throws(x) {
    this.value = arguments[0];
    collect();
    throw returned;
  }
  try {
    new Throws(13);
    ok(false);
  } catch (e) {
    ok(e === returned);
  }
  let Sloppy = Function(
    "x",
    "this.value=arguments[0];x+=3;this.after=arguments[0];this.read=function(){return x};",
  );
  let sloppy = new Sloppy(61);
  collect();
  ok(sloppy.value === 61 && sloppy.after === 64 && sloppy.read() === 64);
  function Recursive(x) {
    this.value = arguments[0];
    if (x > 0) this.child = new Recursive(x - 1);
  }
  let recursive = new Recursive(4);
  ok(recursive.child.child.child.child.value === 0);
  class Derived extends Basic {
    constructor(x) {
      super(...arguments);
      this.target = new.target;
    }
  }
  let derived = new Derived(81);
  ok(derived.value === 81 && derived.target === Derived);
  let bound = Basic.bind(null, 82);
  ok(new bound().value === 82);
  let proxyCalls = 0;
  let proxy = new Proxy(Basic, {
    construct(t, a, n) {
      ++proxyCalls;
      collect();
      return Reflect.construct(t, a, n);
    },
  });
  ok(new proxy(83).value === 83 && proxyCalls === 1);
  globalThis.ARGUMENT_CONSTRUCTOR_CHECKS = checks;
})();
