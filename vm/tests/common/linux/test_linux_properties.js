/* Property supplement semantics under live mutations and callbacks. MIT. */
"use strict";
function eq(actual, expected) {
  if (!Object.is(actual, expected)) throw Error(actual + " != " + expected);
}
function read(o) {
  return o.value;
}
function method(o, n) {
  return o.method(n);
}
function write(o, v) {
  o.value = v;
  return o.value;
}
const objects = [];
for (let k = 0; k < 24; ++k) {
  const o = { value: k };
  o["key" + k] = k;
  objects.push(o);
}
for (let n = 0; n < 8; ++n)
  for (let k = 0; k < objects.length; ++k) {
    eq(read(objects[k]), n ? k + 1 : k);
    eq(write(objects[k], k + 1), k + 1);
  }
const parent = {
  value: 17,
  method(n) {
    return this.value + n;
  },
};
const child = Object.create(parent);
for (let k = 0; k < 64; ++k) eq(method(child, k), 17 + k);
parent.value = 29;
for (let k = 0; k < 64; ++k) eq(method(child, k), 29 + k);
Object.defineProperty(parent, "method", {
  configurable: true,
  get() {
    gc();
    return function (n) {
      return this.value - n;
    };
  },
});
for (let k = 0; k < 8; ++k) eq(method(child, k), 29 - k);
const replacement = {
  value: 41,
  method(n) {
    return this.value + n;
  },
};
Object.setPrototypeOf(child, replacement);
for (let k = 0; k < 64; ++k) eq(method(child, k), 41 + k);
let deep = replacement;
for (let k = 0; k < 6; ++k) deep = Object.create(deep);
for (let k = 0; k < 64; ++k) eq(method(deep, k), 41 + k);
let hooks = 0;
const proxy = new Proxy(replacement, {
  get(t, k, r) {
    ++hooks;
    gc();
    return Reflect.get(t, k, r);
  },
});
const exotic = Object.create(proxy);
for (let k = 0; k < 8; ++k) eq(method(exotic, k), 41 + k);
eq(hooks, 16);
const aliases = { value: null };
aliases.value = aliases;
eq(write(aliases, aliases), aliases);
eq(read(aliases), aliases);
Object.defineProperty(aliases, "value", {
  configurable: true,
  get() {
    gc();
    return 73;
  },
});
eq(read(aliases), 73);
let threw = false;
try {
  write(aliases, 1);
} catch (e) {
  threw = e instanceof TypeError;
}
eq(threw, true);
const descriptor = Object.getOwnPropertyDescriptor(Number.prototype, "portMethod");
const stringDescriptor = Object.getOwnPropertyDescriptor(String.prototype, "portMethod");
try {
  Object.defineProperty(Number.prototype, "portMethod", {
    configurable: true,
    writable: true,
    value: function (n) {
      "use strict";
      return this + n;
    },
  });
  Object.defineProperty(String.prototype, "portMethod", {
    configurable: true,
    writable: true,
    value: function (n) {
      "use strict";
      return this.length + n;
    },
  });
  function primitive(o, n) {
    return o.portMethod(n);
  }
  for (let k = 0; k < 64; ++k) {
    eq(primitive(3, k), 3 + k);
    eq(primitive(3.25, k), 3.25 + k);
    eq(primitive("abcd", k), 4 + k);
    eq(primitive("\u03bb\ud83d\ude00", k), 3 + k);
  }
  const callers = [];
  for (let k = 0; k < 128; ++k) callers.push(Function("v", "return v.portMethod(" + k + ")"));
  for (let pass = 0; pass < 3; ++pass)
    for (let k = 0; k < callers.length; ++k) {
      eq(callers[k]("abc"), 3 + k);
      eq(callers[k](7), 7 + k);
    }
  Number.prototype.portMethod = function (n) {
    return n - 5;
  };
  String.prototype.portMethod = function (n) {
    return n - 7;
  };
  for (let k = 0; k < 64; ++k) {
    eq(primitive(3, k), k - 5);
    eq(primitive("abc", k), k - 7);
  }
} finally {
  if (descriptor) Object.defineProperty(Number.prototype, "portMethod", descriptor);
  else delete Number.prototype.portMethod;
  if (stringDescriptor) Object.defineProperty(String.prototype, "portMethod", stringDescriptor);
  else delete String.prototype.portMethod;
}
function length(v) {
  return v.length;
}
const array = [1, 2, 3];
array.length = 0xffffffff;
for (let k = 0; k < 64; ++k) {
  eq(length(array), 0xffffffff);
  eq(length("abc"), 3);
  eq(length("\u03bb\ud83d\ude00"), 3);
  eq(length({ length: 11 }), 11);
}
function argumentLength() {
  return arguments.length;
}
eq(argumentLength(1, 2, 3), 3);
const symbol = Symbol("port");
globalThis.portSymbol = symbol;
const compare = Function("v", "if(v===portSymbol)return 1;return 0;");
for (let k = 0; k < 64; ++k) {
  eq(compare(symbol), 1);
  eq(compare(Symbol("other")), 0);
}
delete globalThis.portSymbol;
const longRead = Function("o", "let v=0;" + Array(600).fill("v+=o.value;").join("") + "return v;");
eq(longRead({ value: 2 }), 1200);
gc();
print("LINUX_PROPERTY_FAMILY_OK");
