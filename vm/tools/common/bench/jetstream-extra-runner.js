// Shared shell harness. Pinned upstream workloads are loaded without rewriting.
(async () => {
  const host = globalThis.__jetExtra;
  const config = host.config;
  const now = host.now;
  const assert = (condition, message) => {
    if (!condition) throw Error(message);
  };
  const fingerprint = (text) => {
    let a = 2166136261;
    let b = 5381;
    for (let i = 0; i < text.length; ++i) {
      const c = text.charCodeAt(i);
      a = Math.imul(a ^ c, 16777619) >>> 0;
      b = (Math.imul(b, 33) ^ c) >>> 0;
    }
    return { length: text.length, fnv32: a, djb32: b };
  };
  globalThis.self = globalThis;
  globalThis.performance = { now };
  globalThis.console = {
    log: (...args) => print(...args),
    warn: (...args) => print(...args),
    error: (...args) => print(...args),
    assert: (condition, message) => assert(condition, message || "assertion"),
  };
  print("READY " + config.name);
  host.flush();
  assert(host.readline() === "GO", "Missing GO handshake");

  const strings = Object.create(null);
  for (const [name, path] of Object.entries(config.preload)) {
    if (!name.endsWith(".wasm")) strings[path] = host.read(path);
  }
  globalThis.JetStream = {
    preload: config.preload,
    getString: async (path) => {
      assert(typeof strings[path] === "string", "Missing text preload: " + path);
      return strings[path];
    },
    getBinary: async (path) => {
      assert(path in config.binaryPreloads, "Missing binary preload: " + path);
      return new Int8Array(config.binaryPreloads[path]);
    },
  };
  const loadStart = now();
  if (config.randomScript) host.load(config.randomScript);
  for (const path of config.files) host.load(path);
  const load_ms = now() - loadStart;
  const initStart = now();
  const total = config.phase === "compatibility" ? 1 : config.iterations + 2;
  const benchmark = new Benchmark({ iterationCount: total });
  await benchmark.init?.();
  const init_ms = now() - initStart;
  async function iteration(index) {
    const prepareStart = now();
    if (config.async) await benchmark.prepareForNextIteration?.();
    else benchmark.prepareForNextIteration?.();
    if (config.randomScript) Math.random.__resetSeed();
    const start = now();
    if (config.async) await benchmark.runIteration(index);
    else benchmark.runIteration(index);
    return { body_ms: now() - start, prepare_ms: start - prepareStart };
  }
  const cold = await iteration(0);
  let warmup = null;
  const samples = [];
  let warm_elapsed_ms = null;
  if (config.phase !== "compatibility") {
    warmup = await iteration(1);
    const start = now();
    for (let i = 0; i < config.iterations; ++i) samples.push(await iteration(i + 2));
    warm_elapsed_ms = now() - start;
  }
  print("MEASURED " + config.name);
  host.flush();
  assert(host.readline() === "CHECK", "Missing CHECK handshake");

  // All validation below is outside the timing and peak-memory observation.
  await benchmark.validate?.(total);
  let checks;
  if (config.name === "json-parse-inspector") {
    const actual = JSON.stringify(benchmark.result);
    assert(actual === benchmark.str, "JSON parse round trip differs");
    checks = fingerprint(actual);
  } else if (config.name === "json-stringify-inspector") {
    const actual = benchmark.result;
    assert(
      JSON.stringify(JSON.parse(actual)) === JSON.stringify(obj),
      "JSON stringify round trip differs",
    );
    checks = fingerprint(actual);
  } else if (config.name === "acorn-wtb") {
    checks = await benchmark.WTBenchmark.runTest(benchmark.files);
    assert(
      checks.length === 8 && checks.every((n) => Number.isInteger(n) && n > 0),
      "Invalid Acorn token/AST counts",
    );
  } else if (config.name === "prettier-wtb") {
    const formatted = await benchmark.WTBenchmark.runTest(benchmark.files);
    assert(formatted.length === 5, "Missing Prettier outputs");
    checks = formatted.map((text) => {
      assert(typeof text === "string" && text.length > 0, "Empty formatted file");
      return fingerprint(text);
    });
  } else if (config.name === "async-fs") {
    checks = {
      files_per_iteration: benchmark.totalFileCount / total,
      directories_per_iteration: benchmark.totalDirCount / total,
      last_file_hash: benchmark.lastFileHash,
    };
  } else if (config.name === "lazy-collections") {
    checks = { total_length: benchmark.totalLength };
  } else if (config.name === "js-tokens") {
    checks = { token_count: benchmark.tokenCount };
  } else if (config.name === "bigint-noble-ed25519") {
    // Re-evaluate the unchanged Browserify bundle only after measurement to
    // access its public module API. No instrumentation in the measured body.
    const requireModule = (0, eval)(host.read(config.files[1]));
    const ed = requireModule(1);
    const secret = "9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60";
    const publicKey = "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a";
    const signature =
      "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e06522490155" +
      "5fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b";
    const hex = (bytes) => Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
    const message = new Uint8Array(0);
    const pub = await ed.getPublicKey(secret);
    const sig = await ed.sign(message, secret);
    assert(hex(pub) === publicKey && hex(sig) === signature, "RFC 8032 vector mismatch");
    assert(await ed.verify(sig, message, pub), "Ed25519 valid signature rejected");
    assert(!(await ed.verify(sig, new Uint8Array([1]), pub)), "Ed25519 invalid message accepted");
    checks = { rfc8032_test1: true, invalid_message_rejected: true };
  } else throw Error("Unknown case: " + config.name);
  print(
    "DONE " +
      JSON.stringify({
        name: config.name,
        phase: config.phase,
        load_ms,
        init_ms,
        cold,
        warmup,
        samples,
        warm_elapsed_ms,
        checks,
        upstream_validation_present: typeof benchmark.validate === "function",
        supplemental_validation_completed: true,
      }),
  );
  host.flush();
})().catch((error) => {
  print("FAILED " + String(error) + "\n" + (error?.stack || ""));
  globalThis.__jetExtra.flush();
  globalThis.__jetExtra.exit(1);
});
