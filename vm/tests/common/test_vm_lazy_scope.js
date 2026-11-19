/* A live closure must survive supported child calls, native reentry and GC.
 * Seven cells cover compact and indexed closure-read/write opcodes. */
function lazyScopeLeaf(x) {
  return x + 7;
}
const lazyScopeCells = (function () {
  let a = 1,
    b = 2,
    c = 3,
    d = 4,
    e = 5,
    f = 6;
  const box = { value: 8 };
  box.self = box;
  return function cells(x, reset) {
    if (reset) {
      a = 1;
      b = 2;
      c = 3;
      d = 4;
      e = 5;
      f = 6;
      return 0;
    }
    const before = a + b + c + d + e + f + box.value;
    const nativeResult = frameReenter(lazyScopeLeaf, x);
    const directResult = lazyScopeLeaf(x);
    frameGC();
    a += x;
    b += 2 * x;
    c += 3 * x;
    d += 4 * x;
    e += 5 * x;
    f += 6 * x;
    return before + a + b + c + d + e + f + box.value + nativeResult + directResult;
  };
})();
globalThis.frameCases = {
  cells(n) {
    lazyScopeCells(0, true);
    let sum = 0;
    for (let i = 0; i < n; i++) sum += lazyScopeCells(i, false);
    return sum;
  },
};
