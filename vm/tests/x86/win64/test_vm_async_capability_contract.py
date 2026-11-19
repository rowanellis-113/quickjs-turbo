"""The optional async-generator worker must retain unknown input bytes exactly."""

import argparse, hashlib, importlib.util, json, shutil, struct, sys, tempfile
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--source", type=Path, required=True)
ap.add_argument("--build", type=Path, required=True)
a = ap.parse_args()
S = a.source.resolve()
B = a.build.resolve()
sys.path.insert(0, str(S / "tools"))
sp = importlib.util.spec_from_file_location(
    "capability_under_test", S / "tools/x86/common/codegen/generator-capability.py"
)
M = importlib.util.module_from_spec(sp)
sp.loader.exec_module(M)
C = M.module("object-adapter")
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
receipt = json.loads((B / "generated/quickjs-generator-capability-route.json").read_text())
compiled = json.loads((B / "generated/quickjs-generator-capability.compile.json").read_text())
assert not any(n.startswith("js_async_generator_") for n in compiled["generated"]["exports"])
original = B / "generated/quickjs-core-original.obj"
before = B / "CMakeFiles/qjs-core.dir/quickjs.c.obj.before-generator-capability"
if not before.exists():
    before = B / "CMakeFiles/qjs-core.dir/quickjs.c.obj"
with tempfile.TemporaryDirectory(prefix="async-capability-contract-", dir=B) as directory:
    T = Path(directory).resolve()
    assert T.is_relative_to(B) and T != B
    (T / "generated").mkdir()
    (T / "CMakeFiles/qjs-core.dir").mkdir(parents=True)
    shutil.copyfile(original, T / "generated/quickjs-core-original.obj")
    core = T / "CMakeFiles/qjs-core.dir/quickjs.c.obj"
    shutil.copyfile(before, core)
    target = T / "worker.c"
    generated = M.generate(S, T, target)
    assert generated["enabled"] == compiled["generated"]["enabled"]
    if generated["enabled"]:
        assert (
            generated["exports"] == compiled["generated"]["exports"]
            and generated["copies"] == compiled["generated"]["copies"]
        )
        assert (
            sha(T / "generated/quickjs-generator-capability-private.h")
            == compiled["generated"]["private_sha256"]
        )
        proof = M.route_core(S, T)
        assert proof["status"] == "passed-generic-abi-and-exact-site-restoration"
        assert (
            proof["before_sha256"] == receipt["before_sha256"]
            and proof["after_sha256"] == receipt["after_sha256"]
        )
        assert (
            len(proof["hits"]) == 5
            and proof["all_old_symbols_held"]
            and proof["sections_equal_after_restoration"]
        )
    base = before.read_bytes()
    cases = 0
    for name in (
        "js_async_generator_resume_next",
        "js_async_generator_next",
        "js_async_generator_resolve_function",
        "js_create_resolving_functions",
    ):
        co = C.Coff(base)
        if name not in co.symbols:
            continue
        symbol = co.symbols[name]
        section = co.section_records[symbol["section"] - 1]
        co.data[section["raw"] + symbol["value"]] ^= 1
        core.write_bytes(bytes(co.data))
        saved = core.read_bytes()
        generated = M.generate(S, T, target)
        assert not generated["enabled"] and generated["exports"] == [] and generated["copies"] == []
        assert (
            "extern " not in target.read_text()
            and "JS_GeneratorCapability" not in target.read_text()
        )
        proof = M.route_core(S, T)
        assert (
            proof["status"] == "disabled-unknown-profile-input-retained"
            and proof["before_sha256"] == proof["after_sha256"]
        )
        assert core.read_bytes() == saved
        cases += 1
    assert cases
    # Method-table identity is part of admission, independently of function bytes.
    # Corrupt metadata, a method name pointer, a target pointer, or the owner
    # section role. Every unknown case must retain all input bytes and export
    # no private helper. A real shifted-section build supplies the positive case.
    for label, relative in [
        ("metadata", 8),
        ("name-pointer", 0),
        ("target-pointer", 24),
        ("section-role", None),
    ]:
        co = C.Coff(base)
        owners = [
            s
            for s in co.all_symbols.values()
            if s["name"] == "js_async_generator_proto_funcs" and s["section"] > 0
        ]
        assert len(owners) == 1
        owner = owners[0]
        record = co.section_records[owner["section"] - 1]
        if relative is None:
            struct.pack_into("<I", co.data, record["pos"] + 36, record["flags"] | 0x20000000)
        else:
            co.data[record["raw"] + owner["value"] + relative] ^= 1
        core.write_bytes(bytes(co.data))
        saved = core.read_bytes()
        generated = M.generate(S, T, target)
        assert not generated["enabled"] and not generated["exports"] and not generated["copies"], (
            label
        )
        proof = M.route_core(S, T)
        assert (
            proof["status"] == "disabled-unknown-profile-input-retained"
            and core.read_bytes() == saved
        ), label
        cases += 1
    core.write_bytes(base)
    selected = M.reviewed(S, T)
    if selected:
        for name, profile in selected[1]["adapted"].items():
            for transfer in profile["local_transfers"]:
                co = C.Coff(base)
                symbol = co.symbols[name]
                record = co.section_records[symbol["section"] - 1]
                co.data[record["raw"] + symbol["value"] + transfer["offset"] + 1] ^= 1
                core.write_bytes(bytes(co.data))
                saved = core.read_bytes()
                generated = M.generate(S, T, target)
                assert (
                    not generated["enabled"]
                    and not generated["exports"]
                    and not generated["copies"]
                )
                proof = M.route_core(S, T)
                assert (
                    proof["status"] == "disabled-unknown-profile-input-retained"
                    and core.read_bytes() == saved
                )
                cases += 1
                break
            else:
                continue
            break
print(
    "ASYNC_CAPABILITY_CONTRACT_PASS reviewed="
    + str(compiled["generated"]["enabled"])
    + " unknown=input-retained cases="
    + str(cases)
)
