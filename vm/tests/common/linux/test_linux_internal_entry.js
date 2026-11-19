// This path has no C-to-JS callback: it must enter via the core internal call.
function linuxEntryProbe(n) {
  return n ? linuxEntryProbe(n - 1) + 1 : 40;
}
if (linuxEntryProbe(2) !== 42) throw Error("Linux internal entry failed");
print("LINUX_INTERNAL_ENTRY_OK");
