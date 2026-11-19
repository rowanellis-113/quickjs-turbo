// A cached view can be overwritten by an intervening borrowed argv window.
// Reinitialize per-invocation release ownership on hot and geometry paths.
let checks = 0;
for (let count = 1; count <= 128; count++) {
  const parameters = Array.from({ length: count }, (_, i) => "a" + i).join(",");
  const pad = Function(parameters, "return 1");
  const root = Function(
    "pad",
    "return function(){'abcdef'.slice(1,4);pad();return 'abcdef'.slice(1,4)}",
  )(pad);
  pad();
  for (let i = 0; i < 8; i++) {
    if (root() !== "bcd") throw Error("view/argv alias at arity " + count);
    checks++;
  }
}
print("LINUX_VIEW_ARGUMENT_ALIAS_OK " + checks);
