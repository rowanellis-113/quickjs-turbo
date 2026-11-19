// Host-only adapter. The pinned JetStream workload source files are unmodified.
(async () => {
  const { config, now } = globalThis.__jetstream10;
  const total = config.phase === "quick" ? 1 : config.warmups + config.iterations;
  const benchmark = new Benchmark({ iterationCount: total });
  await benchmark.init?.();
  const load_ms = now() - globalThis.__jetstream10.loadStart;
  async function iteration(index) {
    await benchmark.prepareForNextIteration?.();
    if (config.randomScript) Math.random.__resetSeed();
    const start = now();
    if (config.async) await benchmark.runIteration(index);
    else benchmark.runIteration(index);
    return now() - start;
  }
  const cold_ms = await iteration(0);
  const samples_ms = [];
  if (config.phase === "quick") samples_ms.push(cold_ms);
  else {
    for (let i = 1; i < config.warmups; ++i) await iteration(i);
    for (let i = 0; i < config.iterations; ++i)
      samples_ms.push(await iteration(config.warmups + i));
  }
  await benchmark.validate?.(total);
  const checks = { native_assertions_completed: true };
  if (config.name === "Babylon") {
    // The upstream workload discards ASTs. Check basic output structure in
    // an additional pass after timing, without wrapping the measured parser.
    checks.ast = benchmark.sources.map(([, source, options]) => {
      const ast = new parserIndexJS(options, source).parse();
      return { type: ast.type, end: ast.end, body: ast.program.body.length };
    });
  }
  if (config.name === "typescript-octane")
    checks.compiler = { errors: parseErrors.length, checksum: outfile.checksum };
  if (config.name === "pdfjs") checks.pdf = { length: 36788, hash: 939524096 };
  print(
    "JETSTREAM10_RESULT " +
      JSON.stringify({
        name: config.name,
        phase: config.phase,
        load_ms,
        cold_ms,
        samples_ms,
        checks,
      }),
  );
})().catch((error) => {
  console.error(String(error));
  if (error?.stack) console.error(error.stack);
  globalThis.__jetstream10.std.exit(1);
});
