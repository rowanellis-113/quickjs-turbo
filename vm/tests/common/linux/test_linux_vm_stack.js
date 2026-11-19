function linuxDeepFrame(n) {
  if (!n) return 7;
  return linuxDeepFrame(n - 1) + 1;
}
function linuxTailFrame(n, total) {
  if (!n) return total;
  return linuxTailFrame(n - 1, total + 1);
}
for (let i = 0; i < 3; ++i) {
  if (linuxDeepFrame(80) !== 87 || linuxTailFrame(80, 7) !== 87)
    throw Error("Linux native frame return/continuation mismatch");
}
print("LINUX_VM_STACK_OK");
