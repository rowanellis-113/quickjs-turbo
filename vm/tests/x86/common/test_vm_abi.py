"""Fail-closed layout selection, compiler bitfields and no-op ABI generation."""

import copy
import json
import re
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools"))
from x86.common.paths_x86 import activate_tools

activate_tools()
import abi_layout
import native_abi


class PrivateABIContracts(unittest.TestCase):
    def setUp(self):
        self.layout = abi_layout.load(ROOT)

    def test_selected_core_has_exact_measured_contract(self):
        pin = (ROOT / "cmake/QuickJSUpstreamPin.cmake").read_text(encoding="utf-8")
        revision = re.search(r'set\(QJS_UPSTREAM_REVISION "([0-9a-f]+)"\)', pin)[1]
        self.assertEqual(self.layout["upstream"], revision)
        self.assertEqual(abi_layout.verify(ROOT, self.layout)["status"], "passed")

    def test_new_source_cannot_reuse_an_old_layout(self):
        build = ROOT.parent / "build"
        build.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="abi-source-", dir=build) as directory:
            source = Path(directory).resolve()
            self.assertTrue(source.is_relative_to(build.resolve()))
            (source / "quickjs.c").write_text("/* another source revision */\n", encoding="utf-8")
            target = source / "src/x86/win64/abi"
            target.mkdir(parents=True)
            (target / "quickjs-0151.json").write_text(json.dumps(self.layout), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "No unique measured private ABI"):
                abi_layout.load(source)

    def test_compiler_bitfield_drift_is_rejected(self):
        actual = copy.deepcopy(self.layout)
        actual["bits"]["JSObject.fast_array"][0][0] += 1
        result = abi_layout.verify(ROOT, actual)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(
            [row["field"] for row in result["differences"]], ["bits.JSObject.fast_array"]
        )

    def test_missing_measurement_is_rejected(self):
        actual = copy.deepcopy(self.layout)
        del actual["offsets"]["JSContext.rt"]
        result = abi_layout.verify(ROOT, actual)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["differences"][0]["field"], "offsets.JSContext.rt")

    def test_prefix_contract_has_allocator_prefix_and_coro_owner_fields(self):
        text = abi_layout.c_contract(self.layout)
        self.assertIn("offsetof(JSStackFrame, cur_gc_obj)", text)
        self.assertIn("sizeof(JSMallocBlockHeader)", text)
        self.assertNotIn("offsetof(JSString, header)", text)
        consts = abi_layout.constants(self.layout)
        self.assertEqual(consts["QJS_ABI_REF_COUNT_OFFSET"], -4)
        self.assertEqual(consts["QJS_ABI_HAS_PREFIX_RC"], 1)
        self.assertEqual(consts["QJS_ABI_HAS_CORO_OWNER"], 1)

    def test_unchanged_contracts_do_not_invalidate_ninja(self):
        build = ROOT.parent / "build"
        build.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix="ABI contracts with spaces ", dir=build
        ) as directory:
            target = Path(directory).resolve()
            self.assertTrue(target.is_relative_to(build.resolve()))
            abi_layout.write_contracts(ROOT, target)
            before = {
                path.name: (path.read_bytes(), path.stat().st_mtime_ns) for path in target.iterdir()
            }
            abi_layout.write_contracts(ROOT, target)
            after = {
                path.name: (path.read_bytes(), path.stat().st_mtime_ns) for path in target.iterdir()
            }
            self.assertEqual(before, after)

    def test_native_emission_requires_a_source_and_restores_nested_scope(self):
        with self.assertRaisesRegex(RuntimeError, "source-bound ABI"):
            native_abi.current()

        @native_abi.source_abi
        def nested(source):
            self.assertEqual(native_abi.current()["source"], source)
            raise ValueError("nested generation failed")

        @native_abi.source_abi
        def outer(source):
            self.assertEqual(native_abi.current()["source"], source)
            with self.assertRaisesRegex(ValueError, "nested generation failed"):
                nested(source="other")
            self.assertEqual(native_abi.current()["source"], source)

        with patch.object(native_abi, "load", side_effect=lambda source: {"source": source}):
            outer(source="original")
        with self.assertRaisesRegex(RuntimeError, "source-bound ABI"):
            native_abi.current()

    def test_native_emission_rejects_unknown_source_before_running_generator(self):
        executed = []

        @native_abi.source_abi
        def generate(source):
            executed.append(source)

        with patch.object(native_abi, "load", side_effect=ValueError("unmeasured source")):
            with self.assertRaisesRegex(ValueError, "unmeasured source"):
                generate(ROOT)
        self.assertEqual(executed, [])
        with self.assertRaisesRegex(RuntimeError, "source-bound ABI"):
            native_abi.current()


if __name__ == "__main__":
    unittest.main()
