/* General forwarding-constructor semantics, independent of timing workloads. */
function assert(x, message) {
  if (!x) throw Error(message);
}
function factory() {
  return function () {
    this.work.apply(this, arguments);
  };
}
var Positive = factory();
Positive.prototype.work = function (a, b) {
  this.a = a;
  this.b = b;
};
function positiveDriver() {
  var out;
  for (var k = 0; k < 200; k++) out = new Positive(k, k + 1);
  return out;
}
assert(positiveDriver().a === 199, "qualified forwarding driver");
var Forward = factory(),
  calls = 0;
Forward.prototype.work = function (a, b) {
  this.a = a;
  this.b = b;
  this.extra = arguments[2];
  calls++;
};
for (var i = 0; i < 200; i++) {
  var a = { i: i },
    b = { i: i + 1 },
    extra = { i: i + 2 };
  var result = new Forward(a, b, extra);
  assert(result.a === a && result.b === b && result.extra === extra, "identity and extras");
}
Forward.prototype.work = function (a, b) {
  this.a = a;
  this.b = b;
  collect();
};
function gcDriver() {
  for (var i = 0; i < 200; i++) {
    var token = makeToken(i),
      extra = makeToken(i + 1000);
    var result = new Forward(token, extra, token);
    collect();
    assert(result.a === token && result.b === extra, "GC roots");
    assert(result.a.serial === i && result.b.serial === i + 1000, "live opaque payload");
  }
}
gcDriver();
result = null;
a = null;
b = null;
extra = null;
collect();
var releasePhase = 0;
watch(function reenterDuringRelease() {
  assert(releasePhase === 2, "argument finalizer ran before target completed");
  return 43;
});
Forward.prototype.work = function (a, b) {
  releasePhase = 1;
  a = null;
  b = null;
  collect();
  releasePhase = 2;
  this.a = 1;
};
function releaseDriver() {
  for (var k = 0; k < 100; k++) new Forward(makeToken(k), makeToken(k + 1), makeToken(k + 2));
}
releaseDriver();
collect();
var throwValue = { sentinel: 1 };
Forward.prototype.work = function (a) {
  collect();
  if (a < 0) throw throwValue;
  this.a = a;
};
function throwDriver() {
  for (var i = 0; i < 100; i++) new Forward(i);
  try {
    new Forward(-1);
    assert(false, "missing throw");
  } catch (e) {
    assert(e === throwValue, "throw identity");
  }
}
throwDriver();
var accesses = 0;
Object.defineProperty(Forward.prototype, "work", {
  configurable: true,
  get: function () {
    accesses++;
    collect();
    return function (a) {
      this.a = a;
    };
  },
});
assert(new Forward(4).a === 4 && accesses === 1, "descriptor getter");
Object.defineProperty(Forward.prototype, "work", {
  configurable: true,
  writable: true,
  value: function (a) {
    this.a = a;
  },
});
Forward.prototype.work.apply = function (receiver, args) {
  assert(args.length === 3 && args[2] === 9, "materialized custom apply");
  receiver.a = args[0] + 10;
};
assert(new Forward(3, 5, 9).a === 13, "custom apply");
delete Forward.prototype.work.apply;
Object.defineProperty(Forward.prototype.work, "apply", {
  configurable: true,
  get: function () {
    accesses++;
    collect();
    return Function.prototype.apply;
  },
});
assert(new Forward(7).a === 7 && accesses === 2, "apply getter");
delete Forward.prototype.work.apply;
var originalApply = Function.prototype.apply;
Function.prototype.apply = function (receiver, args) {
  assert(args.length === 1, "changed intrinsic");
  receiver.a = args[0] + 20;
};
assert(new Forward(8).a === 28, "changed intrinsic apply");
Function.prototype.apply = originalApply;
Forward.prototype.work = new Proxy(
  function (a) {
    this.a = a;
  },
  {
    apply: function (target, self, args) {
      collect();
      return Reflect.apply(target, self, args);
    },
  },
);
assert(new Forward(31).a === 31, "proxy target");
Forward.prototype.work = function (a) {
  this.a = a;
}.bind({});
assert(new Forward(32).a === undefined, "bound receiver");
Forward.prototype.work = function (a) {
  this.a = a;
  return { ignored: true };
};
for (var i = 0; i < 200; i++) assert(new Forward(i).a === i, "constructor ignores method return");
var object = {
  work: function (a) {
    this.a = a;
  },
};
Forward.call(object, 44);
assert(object.a === 44, "ordinary call");
/* Side effects during the target can mutate both descriptors and run GC. */
Forward.prototype.work = function (a) {
  this.a = a;
  this.work = function () {
    throw Error("late method");
  };
  collect();
};
for (var i = 0; i < 100; i++) assert(new Forward(i).a === i, "reentry descriptor mutation");
/* Introspection uses real callsite identities; output compared ON/OFF/base. */
var stackShapes = [];
Error.prepareStackTrace = function (error, sites) {
  return sites.map(function (s) {
    return [
      s.getFunctionName(),
      s.isNative(),
      s.getFunction() === Forward,
      s.getFunction() === Function.prototype.apply,
    ];
  });
};
Forward.prototype.work = function observed(a) {
  this.a = a;
  this.trace = new Error().stack;
};
function traceDriver() {
  var result;
  for (var i = 0; i < 20; i++) result = new Forward(i);
  return result;
}
result = traceDriver();
stackShapes.push(result.trace);
assert(Array.isArray(result.trace) && result.trace.length > 0, "callsite capture");
delete Error.prepareStackTrace;
/* Strict wrappers and inherited data methods retain the same semantics. */
var Strict = Function('return function Strict(){"use strict";this.work.apply(this,arguments);}')();
Strict.prototype = Object.create({
  work: function (a) {
    this.a = a;
    collect();
  },
});
for (var i = 0; i < 100; i++) assert(new Strict(i).a === i, "strict inherited forwarding");
var originalProto = Object.getPrototypeOf(Strict.prototype);
Object.setPrototypeOf(
  Strict.prototype,
  new Proxy(originalProto, {
    get: function (target, key, receiver) {
      return Reflect.get(target, key, receiver);
    },
  }),
);
assert(new Strict(55).a === 55, "proxy prototype");
/* Public caller with copied argv and a different realm must fall back. */
runRealm(Forward);
print("VIRTUAL_ARGUMENTS_SEMANTICS_OK " + JSON.stringify(stackShapes));
