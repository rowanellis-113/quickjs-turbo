"""Unrelated or stale object files cannot change the executable directory reserve."""

import argparse
import importlib.util
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


parser = argparse.ArgumentParser()
parser.add_argument("--core-object", type=Path, required=True)
args = parser.parse_args()
generator = module("capacity_generator", ROOT / "tools/x86/common/codegen/json-callback.py")
coff = module("capacity_coff", ROOT / "tools/x86/win64/coff/object-adapter.py")


class UnwindCapacityIsolation(unittest.TestCase):
    def test_ambient_objects_are_ignored_and_required_input_is_enforced(self):
        with tempfile.TemporaryDirectory(prefix="qjs-unwind-capacity-") as folder:
            build = Path(folder).resolve()
            self.assertEqual(build.parent, Path(tempfile.gettempdir()).resolve())
            core = build / "generated/quickjs-core-original.obj"
            core.parent.mkdir(parents=True)
            shutil.copyfile(args.core_object, core)
            before = generator.source_unwind_capacity(build, coff)
            self.assertGreater(before["capacity_bytes"], 0)
            for relative in [
                "CMakeFiles/api-test.dir/test.obj",
                "CMakeFiles/CompilerIdC/unreadable.obj",
                "generated/old-experiment.obj",
            ]:
                other = build / relative
                other.parent.mkdir(parents=True, exist_ok=True)
                other.write_bytes(b"not even a COFF object")
            self.assertEqual(before, generator.source_unwind_capacity(build, coff))
            core.unlink()
            with self.assertRaises(FileNotFoundError):
                generator.source_unwind_capacity(build, coff)


unittest.main(argv=[__file__])
