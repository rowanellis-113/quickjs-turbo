import * as std from "qjs:std";
function check(ok, message) {
  if (!ok) throw Error(message);
}
const read = std.evalScript(`
globalThis.linuxCellGlobal=17;
let linuxCellLex=23;
globalThis.linuxCellShadow=5;
function linuxCellRead(o) { return linuxCellGlobal+linuxCellLex+linuxCellShadow+o.x; }
linuxCellRead;
`);
const object = { x: 7 };
for (let i = 0; i < 20; i++) check(read(object) === 52, "initial cells");
std.evalScript("linuxCellGlobal=31;linuxCellLex=41;");
check(read(object) === 84, "live value replacement");
std.evalScript("let linuxCellShadow=9;");
check(read(object) === 88, "new lexical shadow invalidates global cell");
for (let i = 0; i < 350; i++) globalThis["linuxCellPadding" + i] = i;
std.gc();
check(read(object) === 88, "global storage growth/GC");
for (let i = 0; i < 350; i++) delete globalThis["linuxCellPadding" + i];
check(read(object) === 88, "global storage shrink");
let gets = 0;
Object.defineProperty(globalThis, "linuxCellGlobal", {
  configurable: true,
  get() {
    gets++;
    std.gc();
    return std.evalScript("linuxCellLex");
  },
});
check(read(object) === 98 && gets === 1, "accessor GC/reentry invalidates cell");
Object.defineProperty(globalThis, "linuxCellGlobal", {
  configurable: true,
  get() {
    throw Error("cell expected");
  },
});
let caught = false;
try {
  read(object);
} catch (error) {
  caught = error.message === "cell expected";
}
check(caught, "getter exception");
Object.defineProperty(globalThis, "linuxCellGlobal", {
  value: 52,
  writable: true,
  configurable: true,
});
for (let i = 0; i < 20; i++) check(read(object) === 109, "data restoration after exception");
delete globalThis.linuxCellGlobal;
Object.prototype.linuxCellGlobal = 77;
check(read(object) === 134, "prototype fallback after deletion");
delete Object.prototype.linuxCellGlobal;
Object.defineProperty(globalThis, "linuxCellGlobal", {
  value: 52,
  writable: true,
  configurable: true,
});
std.gc();
check(read(object) === 109, "cell recovery after prototype fallback");
std.evalScript("function linuxCellTdzRead(o){return linuxCellTdz+o.x;}");
let tdz = false;
try {
  std.evalScript("let linuxCellTdz=linuxCellTdzRead({x:0});");
} catch (error) {
  tdz = error instanceof ReferenceError;
}
check(tdz, "lexical TDZ remains observable");
print("LINUX_GLOBAL_CELLS_OK");
