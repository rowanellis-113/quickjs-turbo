"use strict";
function make(C, v) {
  let r = new C(v);
  return r;
}
function invoke(f, v) {
  return f(v);
}
function value(v) {
  this.v = v;
}
function primitive(v) {
  this.v = v;
  return 3;
}
function string(v) {
  this.v = v;
  return "ignored";
}
function object(v) {
  this.discard = { v };
  return { v };
}
function captured(v) {
  this.read = () => v;
  v++;
}
function inside(v) {
  this.v = v;
  return "ignored";
}
function forwarded(v) {
  return inside.call(this, v);
}
function recursive(v) {
  this.v = v ? make(recursive, v - 1) : 1;
}
function raising(v) {
  this.v = v;
  throw Error("ctor");
}
function caught(C, v) {
  try {
    return make(C, v);
  } catch (e) {
    return { v: e.message === "ctor" ? v : -1 };
  }
}
function hostRaise() {
  throw Error("host");
}
function catchHost(v) {
  try {
    hostRaise();
  } catch (e) {
    this.v = e.message === "host" ? v : -1;
  }
}
function iterating(v) {
  for (const x of [v, v + 1]) {
    this.v = x;
    break;
  }
}
let total = 0;
for (let i = 0; i < 32; i++) {
  for (const C of [value, primitive, string, object, forwarded, catchHost, iterating]) {
    const r = make(C, i);
    if (r.v !== i) throw Error("value");
    total += r.v;
  }
  if (make(captured, i).read() !== i + 1) throw Error("capture");
  if (caught(raising, i).v !== i) throw Error("catch");
}
let r = make(recursive, 24);
for (let i = 0; i < 24; i++) r = r.v;
if (r.v !== 1) throw Error("deep");
gc();
print("LINUX_CONSTRUCT_PATHS_OK checksum=" + total);
