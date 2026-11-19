"""Typed routing must hold code bytes and fail closed on unknown inputs."""

# Shared source/tool/artifact addressing for this backend package.
import sys as _frame_sys
from pathlib import Path as _FramePath

_frame_sys.path.insert(0, str(_FramePath(__file__).resolve().parents[3] / "tools"))
from x86.common.paths_x86 import (
    activate_tools as _frame_activate_tools,
    tool_path as _frame_tool_path,
    source_file as _frame_source_file,
    source_text as _frame_source_text,
    generated_file as _frame_generated_file,
    project_root as _frame_project_root,
    build_file as _frame_build_file,
)

_frame_activate_tools()
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "tools"))
import call_env_adapter as E


def calls_coff(opcode=0xE8, kind=4):
    names = ["JS_FrameCallMetaMiss", "JS_FrameCallLinkMiss", "JS_FrameCallLinkPrepare"]
    code = b"".join(bytes([opcode]) + bytes(4) for _ in names) + b"\xc3"
    data = bytearray(60)
    data += code
    reloc = len(data)
    for i in range(3):
        data += struct.pack("<IIH", 5 * i + 1, i, kind)
    table = len(data)
    strings = bytearray(4)
    for name in names:
        offset = len(strings)
        strings += name.encode() + b"\0"
        data += struct.pack("<IIIhHBB", 0, offset, 0, 0, 0x20, 2, 0)
    struct.pack_into("<I", strings, 0, len(strings))
    data += strings
    struct.pack_into("<HHIIIHH", data, 0, 0x8664, 1, 0, table, 3, 0, 0)
    struct.pack_into(
        "<8sIIIIIIHHI", data, 20, b".text\0\0\0", 0, 0, len(code), 60, reloc, 0, 3, 0, 0x60300020
    )
    return bytes(data)


class CallEnvContracts(unittest.TestCase):
    def test_routes_both_vm_helpers_and_holds_explicit_api_and_code(self):
        raw = calls_coff()
        result, proof = E.rewrite(raw, False, {})
        old, new = E.U.C.Coff(raw), E.U.C.Coff(result)
        self.assertEqual(len(proof["changes"]), 2)
        self.assertEqual(new.all_symbols[2], old.all_symbols[2])
        section = new.section_records[0]
        targets = [
            new.all_symbols[struct.unpack_from("<I", result, section["reloc"] + i * 10 + 4)[0]][
                "name"
            ]
            for i in range(3)
        ]
        self.assertEqual(
            targets,
            ["JS_FrameCallEnvMetaMiss", "JS_FrameCallEnvLinkMiss", "JS_FrameCallLinkPrepare"],
        )
        self.assertEqual(raw[60:76], result[section["raw"] : section["raw"] + 16])

    def test_indirect_or_non_rel32_is_rejected(self):
        for opcode, kind in ((0x90, 4), (0xE8, 3)):
            with (
                self.subTest(opcode=opcode, kind=kind),
                self.assertRaisesRegex(RuntimeError, "typed direct"),
            ):
                E.rewrite(calls_coff(opcode, kind), False, {})

    def test_header_copies_are_private_and_tentative_constants_need_a_provider(self):
        raw = bytearray(calls_coff())
        co = E.U.C.Coff(raw)
        struct.pack_into("<h", raw, co.table + 12, 1)
        struct.pack_into("<I", raw, co.table + co.stride + 8, 16)
        with self.assertRaisesRegex(RuntimeError, "Unbound call-environment tentative constant"):
            E.rewrite(bytes(raw), True, {})
        result, proof = E.rewrite(bytes(raw), True, {"JS_FrameCallLinkMiss": [16]})
        final = E.U.C.Coff(result)
        self.assertTrue(final.all_symbols[0]["name"].startswith("call_env_emitted_"))
        self.assertEqual(final.all_symbols[1]["name"], "JS_FrameCallLinkMiss")
        self.assertEqual(final.all_symbols[1]["value"], 0)
        self.assertEqual(len(proof["changes"]), 2)

    def test_restore_checks_provenance_and_preserves_compiler_timestamp(self):
        before = calls_coff()
        after, _ = E.rewrite(before, False, {})
        with tempfile.TemporaryDirectory(prefix="call env ") as directory:
            path = Path(directory) / "member.obj"
            record, backup = E.sidecars(path)
            backup.write_bytes(before)
            path.write_bytes(after + b"corrupt")
            record.write_text(
                json.dumps(dict(before_sha256=E.sha(before), after_sha256=E.sha(after)))
            )
            with self.assertRaisesRegex(RuntimeError, "Unknown call-environment endpoint"):
                E.restore([path])
            self.assertEqual(path.read_bytes(), after + b"corrupt")
            path.write_bytes(after)
            stamp = path.stat().st_mtime_ns
            E.restore([path])
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(path.stat().st_mtime_ns, stamp)
            self.assertFalse(record.exists())
            self.assertFalse(backup.exists())
            E.restore([path])


if __name__ == "__main__":
    unittest.main()
