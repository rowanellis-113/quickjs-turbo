"""Integration contract: an unrecognized clone must not create a native route."""

import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile

parser = argparse.ArgumentParser()
parser.add_argument("--source", type=Path, required=True)
parser.add_argument("--build", type=Path, required=True)
args = parser.parse_args()
args.source = args.source.resolve()
args.build = args.build.resolve()
sys.path.insert(0, str(args.source / "tools"))
spec = importlib.util.spec_from_file_location(
    "default_sort_under_test", args.source / "tools/x86/win64/codegen/default-sort.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
C = module.module("object-adapter")
original = module.generated_file(args.build, "quickjs-core-original.obj")
normal = module.reviewed_profile(C.Coff(original.read_bytes()))
saved = module.CONTRACT
module.CONTRACT = copy.deepcopy(saved)
for profile in module.CONTRACT["functions"].values():
    profile["caller"]["normalized_code_sha256"] = "0" * 64
assert module.reviewed_profile(C.Coff(original.read_bytes())) is None
with tempfile.TemporaryDirectory(prefix="default-sort-capability-", dir=args.build) as directory:
    test_build = Path(directory)
    assert test_build.resolve().is_relative_to(args.build)
    (test_build / "generated").mkdir()
    (test_build / "CMakeFiles/qjs-core.dir").mkdir(parents=True)
    shutil.copyfile(original, test_build / "generated/quickjs-core-original.obj")
    shutil.copyfile(args.build / "CMakeCache.txt", test_build / "CMakeCache.txt")
    before_route = args.build / "CMakeFiles/qjs-core.dir/quickjs.c.obj.before-default-sort"
    if not before_route.exists():
        before_route = args.build / "CMakeFiles/qjs-core.dir/quickjs.c.obj"
    core = test_build / "CMakeFiles/qjs-core.dir/quickjs.c.obj"
    shutil.copyfile(before_route, core)
    before = hashlib.sha256(core.read_bytes()).hexdigest()
    worker = test_build / "disabled-worker.c"
    generated = module.generate(args.source, test_build, worker)
    assert not generated["enabled"] and generated["exports"] == []
    assert "JS_ArrayDefaultStringSortDispatch" not in worker.read_text()
    assert "qjs_default_string_sort_original" not in worker.read_text()
    route = module.route_core(args.source, test_build)
    assert route["status"] == "disabled-unreviewed-private-ABI-input-retained"
    assert route["before_sha256"] == route["after_sha256"] == before
    assert hashlib.sha256(core.read_bytes()).hexdigest() == before
    assert not core.with_name(core.name + ".before-default-sort").exists()
module.CONTRACT = saved
# A stable source/body name never licenses an arbitrary moved function pointer.
# Mutating a reviewed direct transfer or function LEA must reject admission.
if normal:
    for field, name in [("caller", "js_array_sort"), ("sorter", normal[1]["callee"])]:
        expected = normal[1][field]
        for key, displacement in [("local_transfers", 1), ("local_addresses", 3)]:
            if not expected[key]:
                continue
            site = expected[key][0]
            co = C.Coff(original.read_bytes())
            symbol = co.symbols[name]
            record = co.section_records[symbol["section"] - 1]
            co.data[record["raw"] + symbol["value"] + site["offset"] + displacement] ^= 1
            assert module.reviewed_profile(C.Coff(bytes(co.data))) is None, (field, key)
print("DEFAULT_SORT_CAPABILITY_PASS reviewed=" + str(bool(normal)) + " unknown=input-retained")
