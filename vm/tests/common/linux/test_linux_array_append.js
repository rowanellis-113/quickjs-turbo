let checks = 0;
function check(ok) {
  ++checks;
  if (!ok) throw Error("array append check " + checks);
}
function append(n) {
  const a = [];
  for (let i = 0; i < n; ++i) a[a.length] = i;
  return a;
}
for (const n of [0, 1, 2, 3, 4, 7, 8, 16, 31, 32, 63, 64, 127]) {
  const a = append(n);
  check(a.length === n);
  for (let i = 0; i < n; ++i) check(a[i] === i);
}
const negative = append(8);
negative[-1] = 9;
check(negative.length === 8 && negative[-1] === 9 && negative[7] === 7);
let conversions = 0;
negative[
  {
    [Symbol.toPrimitive]() {
      ++conversions;
      return 8;
    },
  }
] = 44;
check(conversions === 1 && negative.length === 9 && negative[8] === 44);
const readonly = append(16);
Object.defineProperty(readonly, "length", { writable: false });
let rejected = false;
try {
  readonly[readonly.length] = 9;
} catch (e) {
  rejected = e instanceof TypeError;
}
check(rejected && readonly.length === 16 && !(16 in readonly));
for (const freeze of [Object.preventExtensions, Object.seal, Object.freeze]) {
  const a = freeze(append(4));
  rejected = false;
  try {
    a[a.length] = 7;
  } catch (e) {
    rejected = e instanceof TypeError;
  }
  check(rejected && a.length === 4 && !(4 in a));
}
const huge = [];
huge.length = 2147483647;
huge[2147483647] = 71;
check(huge.length === 2147483648 && huge[2147483647] === 71);
let setters = 0;
const prototype = Object.create(Array.prototype, {
  4: {
    set(v) {
      setters += v;
    },
    configurable: true,
  },
});
const inherited = append(4);
Object.setPrototypeOf(inherited, prototype);
inherited[inherited.length] = 5;
check(setters === 5 && inherited.length === 4 && !Object.hasOwn(inherited, 4));
let stores = 0;
const proxied = new Proxy(append(4), {
  set(target, key, value, receiver) {
    ++stores;
    return Reflect.set(target, key, value, receiver);
  },
});
proxied[proxied.length] = 17;
check(stores === 1 && proxied.length === 5 && proxied[4] === 17);
const typed = new Uint32Array(4);
typed[0] = 9;
typed[4] = 11;
check(typed.length === 4 && typed[0] === 9 && !(4 in typed));
print("LINUX_ARRAY_APPEND_OK checks=" + checks);
