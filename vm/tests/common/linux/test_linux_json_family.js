/* JSON family semantics; the external host compares the original engine too. */
(function () {
  let checks = 0,
    digest = 2166136261,
    journal = [];
  function ok(value) {
    checks++;
    if (!value) throw Error("JSON_FAMILY_CHECK_" + checks);
  }
  function record(value) {
    const text = String(value);
    for (let i = 0; i < text.length; i++)
      digest = Math.imul(digest ^ text.charCodeAt(i), 16777619) >>> 0;
  }
  function probe() {
    if (typeof jsonProbe === "function") jsonProbe();
  }
  const raw =
    '{"n":1.2300e+2,"z":-0,"s":"a\\nb","u":"é𠀀",' +
    Array.from({ length: 24 }, (_, i) => '"k' + i + '":' + i).join(",") +
    "}";
  const data = JSON.parse(raw);
  ok(data.n === 123 && Object.is(data.z, -0) && data.u === "é𠀀");
  record(JSON.stringify(data));
  function valueReviver(k, v) {
    probe();
    if (typeof v === "number") v = v + 1;
    return v;
  }
  function readonlyValueReviver(k, v) {
    probe();
    return v;
  }
  function sourceReviver(k, v, c) {
    probe();
    if (c && Object.prototype.hasOwnProperty.call(c, "source")) journal.push(k + ":" + c.source);
    return v;
  }
  function readonlyReplacer(k, v) {
    probe();
    return typeof v === "number" ? v + 2 : v;
  }
  function writableReplacer(k, v, missing) {
    probe();
    ok(missing === undefined);
    v = typeof v === "number" ? v + 2 : v;
    return v;
  }
  function parseValue() {
    return JSON.parse(raw, valueReviver);
  }
  function parseValueRO() {
    return JSON.parse(raw, readonlyValueReviver);
  }
  function parseSource() {
    return JSON.parse(raw, sourceReviver);
  }
  const ascii = raw.replace("é𠀀", "ascii");
  function parseSourceASCII() {
    return JSON.parse(ascii, sourceReviver);
  }
  function stringifyRO() {
    return JSON.stringify(data, readonlyReplacer);
  }
  function stringifyRW() {
    return JSON.stringify(data, writableReplacer);
  }
  // Warm the actual callable metadata before an admitted native activation.
  valueReviver("", 0);
  readonlyValueReviver("", 0);
  sourceReviver("", 0, {});
  readonlyReplacer("", 0);
  writableReplacer("", 0);
  for (let i = 0; i < 3; i++) {
    const value = parseValue();
    ok(value.n === 124 && value.z === 1);
    record(JSON.stringify(value));
    const readonly = parseValueRO();
    ok(readonly.n === 123 && Object.is(readonly.z, -0));
    record(JSON.stringify(readonly));
    journal = [];
    const source = parseSource();
    ok(source.n === 123 && Object.is(source.z, -0));
    ok(journal.includes("n:1.2300e+2") && journal.includes("z:-0") && journal.includes('u:"é𠀀"'));
    record(journal.join("|"));
    record(stringifyRO());
    record(stringifyRW());
    journal = [];
    const asciiSource = parseSourceASCII();
    ok(asciiSource.u === "ascii" && journal.includes('u:"ascii"'));
    record(journal.join("|"));
  }
  for (const text of [
    '[1e+2,-0,"\\ud800","é"]',
    '{"x":1,"x":2}',
    '{"2":2,"1":1,"__proto__":{"safe":true}}',
    '[true,false,null,"a\\u0000b"]',
  ]) {
    journal = [];
    const value = JSON.parse(text, sourceReviver);
    record(JSON.stringify(value));
    record(journal.join("|"));
  }
  const moved = JSON.parse('{"a":1,"b":2}', function (k, v, c) {
    if (k === "a") this.b = 99;
    if (k === "b") ok(v === 99 && !Object.prototype.hasOwnProperty.call(c, "source"));
    return v;
  });
  ok(moved.b === 99);
  const allArgs = JSON.parse("[1,2]", function () {
    ok(arguments.length === 3);
    return arguments[1];
  });
  ok(allArgs[1] === 2);
  const restArgs = JSON.parse("[1]", (...args) => {
    ok(args.length === 3);
    return args[1];
  });
  ok(restArgs[0] === 1);
  let sourceObserved = "";
  const bound = sourceReviver.bind(null);
  JSON.parse("[1.00]", bound);
  JSON.parse("[2.00]", function (k, v, c) {
    if (k === "0") sourceObserved = c.source;
    return v;
  });
  ok(sourceObserved === "2.00");
  const strings = ["plain", '\u0000\n\t\\"', "é", "𠀀", "\ud800", "\udfff"];
  for (const value of strings) ok(JSON.parse(JSON.stringify(value)) === value);
  const quoted = Array.from({ length: 32 }, (_, i) => ({
    ["key" + i]: strings[i % strings.length],
  }));
  for (let i = 0; i < 3; i++) record(JSON.stringify(quoted, readonlyReplacer));
  let calls = 0;
  const object = {
    a: 1,
    toJSON: function (k) {
      calls++;
      probe();
      return { key: k, n: this.a };
    },
  };
  const values = Array.from({ length: 24 }, () => object);
  for (let i = 0; i < 3; i++) record(JSON.stringify(values));
  ok(calls === 72);
  object.toJSON = function (k) {
    probe();
    return { changed: true };
  };
  record(JSON.stringify(values));
  delete object.toJSON;
  record(JSON.stringify(values));
  Object.defineProperty(object, "toJSON", {
    get() {
      calls++;
      return function () {
        return "getter";
      };
    },
    configurable: true,
  });
  record(JSON.stringify(values));
  ok(calls === 96);
  delete object.toJSON;
  const cycle = {};
  cycle.self = cycle;
  for (const fn of [
    () => JSON.stringify(cycle),
    () => JSON.stringify(1n),
    () => JSON.parse("01"),
    () => JSON.parse("[1,]"),
    () => JSON.parse('"\\uZZZZ"'),
  ]) {
    let threw = false;
    try {
      fn();
    } catch (e) {
      threw = e instanceof Error;
    }
    ok(threw);
  }
  let sentinel = {};
  try {
    JSON.parse(raw, function (k, v, c) {
      probe();
      throw sentinel;
    });
    ok(false);
  } catch (e) {
    ok(e === sentinel);
  }
  try {
    JSON.stringify(data, function (k, v) {
      probe();
      throw sentinel;
    });
    ok(false);
  } catch (e) {
    ok(e === sentinel);
  }
  let conversions = 0;
  const convertible = {
    toString() {
      conversions++;
      return raw;
    },
  };
  JSON.parse(convertible, sourceReviver);
  ok(conversions === 1);
  const proxy = new Proxy(sourceReviver, {
    apply(target, holder, args) {
      return Reflect.apply(target, holder, args);
    },
  });
  record(JSON.stringify(JSON.parse(raw, proxy)));
  record(JSON.stringify(data, ["n", "u", "z"], 2));
  record(JSON.stringify(data, readonlyReplacer, "é"));
  return { passed: true, checks, digest };
})();
