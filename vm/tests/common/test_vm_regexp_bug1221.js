function assert(actual, expected, message) {
  if (arguments.length === 1) expected = true;
  if (typeof actual === typeof expected) {
    if (actual === expected && (actual !== 0 || 1 / actual === 1 / expected)) return;
    if (typeof actual === "number" && isNaN(actual) && isNaN(expected)) return;
  }
  throw Error(
    "assertion failed: got |" +
      actual +
      "|, expected |" +
      expected +
      "|" +
      (message ? " (" + message + ")" : ""),
  );
}
let caught = 0;
for (let i = 1; i <= 32; i++) {
  const prefix = "(:?".repeat(i);
  const suffix = "|)+".repeat(i);
  const between = "(?:a|)+";
  const pattern = prefix + between + suffix;
  try {
    const re = new RegExp(pattern);
    assert(re.source, pattern);
  } catch (e) {
    assert(e instanceof SyntaxError);
    assert(e.message, "out of memory");
    caught++;
  }
}
// Avoiding repeated nested bytecode copies can reduce the old OOM count.
// Keep its upper bound and check every successful compilation above.
assert(caught <= 12);
