import * as std from "qjs:std";
import * as os from "qjs:os";

const config = JSON.parse(std.loadFile(scriptArgs[1]));
const now = () => os.now() / 1000;
globalThis.performance = { now };
globalThis.console = {
  log: (...args) => print(...args),
  warn: (...args) => std.err.puts(args.join(" ") + "\n"),
  error: (...args) => std.err.puts(args.join(" ") + "\n"),
  assert: (condition, message) => {
    if (!condition) throw Error(message || "assertion");
  },
};
const preloaded = Object.create(null);
for (const path of Object.values(config.preload)) {
  const text = std.loadFile(path);
  if (typeof text !== "string") throw Error("Missing preload: " + path);
  preloaded[path] = text;
}
globalThis.JetStream = {
  preload: config.preload,
  getString: async (path) => {
    if (!(path in preloaded)) throw Error("Unknown preload: " + path);
    return preloaded[path];
  },
};
globalThis.__jetstream10 = { config, now, std, loadStart: now() };
if (config.randomScript) std.loadScript(config.randomScript);
for (const path of config.files) std.loadScript(path);
std.loadScript(config.runner);
