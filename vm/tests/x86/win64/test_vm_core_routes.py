"""Named core routes must preserve instructions, owners and chained COFF tails."""

from pathlib import Path
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest
import importlib.util
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools"))
from x86.common.paths_x86 import activate_tools

activate_tools()
import core_routes as routes
import retained_routes as retained
import retained_modules as integration

spec = importlib.util.spec_from_file_location(
    "own_bytecode_contracts", ROOT / "tools/x86/common/codegen/own-bytecode.py"
)
own_bytecode = importlib.util.module_from_spec(spec)
spec.loader.exec_module(own_bytecode)


class AllocatedRefcountWitness(unittest.TestCase):
    def rows(self, branch="jne", store="mov DWORD PTR [rax],0x1"):
        target = 0x200 if branch == "jne" else 0x10C
        return {
            0x100: dict(offset=0x100, code="488bf8", instruction="mov rdi,rax", function_start=0),
            0x103: dict(offset=0x103, code="4885c0", instruction="test rax,rax", function_start=0),
            0x106: dict(
                offset=0x106, code="0f8500000000", instruction=branch + " 0x200", function_start=0
            ),
            target: dict(offset=target, code="c70001000000", instruction=store, function_start=0),
        }

    def test_follows_nonnull_edge_past_failure_epilogue(self):
        result = own_bytecode.decoded_allocation_refcount_path(self.rows(), 0x100, 0)
        self.assertEqual([r["offset"] for r in result], [0x200])

    def test_null_branch_uses_fallthrough(self):
        result = own_bytecode.decoded_allocation_refcount_path(self.rows("je"), 0x100, 0)
        self.assertEqual([r["offset"] for r in result], [0x10C])

    def test_rejects_unrelated_pointer_or_intervening_call(self):
        for store in ("mov DWORD PTR [rbx],0x1", "call 0x300"):
            self.assertEqual(
                own_bytecode.decoded_allocation_refcount_path(self.rows(store=store), 0x100, 0), []
            )
        rows = self.rows()
        rows[0x103]["instruction"] = "test rcx,rcx"
        self.assertEqual(own_bytecode.decoded_allocation_refcount_path(rows, 0x100, 0), [])


def fixture(relocated=True, kind=4):
    code = (
        (b"\xe8" + bytes(4) + b"\xc3") * 2 + b"\xc3"
        if relocated
        else b"\xe8\x07\0\0\0\xc3\xe8\x01\0\0\0\xc3\xc3"
    )
    data = bytearray(60) + code
    relocation = len(data) if relocated else 0
    if relocated:
        for offset in (1, 7):
            data += struct.pack("<IIH", offset, 2, kind)
    table = len(data)
    for name, value in ((b"callerA", 0), (b"callerB", 6), (b"target", 12)):
        data += struct.pack("<8sIhHBB", name.ljust(8, b"\0"), value, 1, 32, 3, 0)
    data += struct.pack("<I", 4)
    struct.pack_into("<HHIIIHH", data, 0, 0x8664, 1, 0, table, 3, 0, 0)
    struct.pack_into(
        "<8sIIIIIIHHI",
        data,
        20,
        b".text\0\0\0",
        0,
        0,
        len(code),
        60,
        relocation,
        0,
        2 if relocated else 0,
        0,
        0x60300020,
    )
    return bytes(data)


def overflow_fixture(count=65536):
    data = bytearray(60) + bytes(count * 4 + 4)
    relocation = len(data)
    data += struct.pack("<IIH", count + 1, 0, 0)
    for i in range(count):
        # A real operand may equal the extended-count sentinel's value.
        offset = count + 1 if i == 0 else i * 4
        data += struct.pack("<IIH", offset, 0, 11)
    table = len(data)
    data += struct.pack("<8sIhHBB", b"target\0\0", 0, 1, 32, 3, 0)
    data += struct.pack("<I", 4)
    struct.pack_into("<HHIIIHH", data, 0, 0x8664, 1, 0, table, 1, 0, 0)
    struct.pack_into(
        "<8sIIIIIIHHI",
        data,
        20,
        b".debug\0\0",
        0,
        0,
        count * 4 + 4,
        60,
        relocation,
        0,
        0xFFFF,
        0,
        0x43100040,
    )
    return bytes(data)


class ExtendedRelocationTables(unittest.TestCase):
    def test_count_sentinel_is_not_an_operand_and_all_records_are_read(self):
        raw = overflow_fixture()
        coff = routes.C.Coff(raw)
        records = routes.relocations(coff, 1)
        self.assertEqual(len(records), 65536)
        self.assertEqual(records[65537][:2], (11, "target"))
        self.assertIn(65535 * 4, records)
        self.assertEqual(coff.section_records[0]["count"], 0xFFFF)

    def test_symbol_append_and_tail_packing_preserve_the_complete_table(self):
        raw = overflow_fixture()
        coff = routes.C.Coff(raw)
        coff.external("unused_alias")
        result = routes.pack(coff.finish() + b"kept-tail")
        routes.verify(raw, result, [])
        self.assertEqual(
            routes.relocations(routes.C.Coff(result), 1), routes.relocations(routes.C.Coff(raw), 1)
        )

    def test_change_beyond_the_old_16bit_limit_is_rejected(self):
        raw = overflow_fixture()
        coff = routes.C.Coff(raw)
        changed = bytearray(raw)
        last = list(coff.relocation_positions(1))[-1]
        struct.pack_into("<H", changed, last + 8, 10)
        with self.assertRaisesRegex(RuntimeError, "outside approved"):
            routes.verify(raw, bytes(changed), [])

    def test_malformed_extended_headers_and_truncated_tables_are_rejected(self):
        raw = overflow_fixture()
        pointer = routes.C.Coff(raw).section_records[0]["reloc"]
        for at, fmt, value in (
            (52, "<H", 12),
            (pointer + 4, "<I", 1),
            (pointer, "<I", 10),
            (pointer, "<I", 0xFFFFFFFF),
        ):
            changed = bytearray(raw)
            struct.pack_into(fmt, changed, at, value)
            with self.assertRaisesRegex(RuntimeError, "COFF relocation"):
                routes.C.Coff(bytes(changed))


class TypedCoreRoutes(unittest.TestCase):
    def test_owner_selection_changes_only_one_destination(self):
        raw = fixture()
        result, proof = routes.rewrite(
            raw,
            Path("unused.obj"),
            None,
            [{"before": "target", "after": "nativeA", "owners": ["callerA"], "count": 1}],
        )
        self.assertEqual([(row["owner"], row["offset"]) for row in proof], [("callerA", 1)])
        old, new = routes.C.Coff(raw), routes.C.Coff(result)
        self.assertEqual(old.sections[0]["sha256"], new.sections[0]["sha256"])
        self.assertEqual(routes.relocations(new, 1)[1][1], "nativeA")
        self.assertEqual(routes.relocations(new, 1)[7][1], "target")

    def test_changed_code_outside_the_operand_is_rejected(self):
        raw = fixture()
        result, proof = routes.rewrite(
            raw,
            Path("unused.obj"),
            None,
            [{"before": "target", "after": "nativeA", "owners": ["callerA"], "count": 1}],
        )
        changed = bytearray(result)
        changed[routes.C.Coff(result).section_records[0]["raw"] + 5] = 0x90
        with self.assertRaisesRegex(RuntimeError, "outside approved"):
            routes.verify(raw, bytes(changed), proof)

    def test_non_rel32_or_wrong_owner_cannot_satisfy_a_required_route(self):
        for raw, owners in ((fixture(kind=3), ["callerA"]), (fixture(), ["absent"])):
            with self.subTest(owners=owners), self.assertRaisesRegex(RuntimeError, "route count"):
                routes.rewrite(
                    raw,
                    Path("unused.obj"),
                    None,
                    [{"before": "target", "after": "nativeA", "owners": owners, "count": 1}],
                )

    def test_resolved_calls_preserve_an_existing_post_string_relocation_tail(self):
        listing = " 0: e8 07 00 00 00 call c\n 6: e8 01 00 00 00 call c\n"
        with patch.object(routes.subprocess, "check_output", return_value=listing):
            first, proof = routes.rewrite(
                fixture(False),
                Path("unused.obj"),
                Path("objdump"),
                [{"before": "target", "after": "nativeA", "owners": ["callerA"], "count": 1}],
            )
            self.assertEqual(proof[0]["kind"], "decoded-rel32")
            obj = routes.C.Coff(first)
            self.assertGreater(len(first), obj.string_offset + len(obj.strings))
            second, proof = routes.rewrite(
                first,
                Path("unused.obj"),
                Path("objdump"),
                [{"before": "target", "after": "nativeB", "owners": ["callerB"], "count": 1}],
            )
        after = routes.C.Coff(second)
        self.assertEqual(
            {off: target[1] for off, target in routes.relocations(after, 1).items()},
            {1: "nativeA", 7: "nativeB"},
        )
        self.assertEqual(proof[0]["owner"], "callerB")


class LiveRetainedRoutes(unittest.TestCase):
    listing = b" 0: e8 07 00 00 00 call c\n 5: c3 ret\n 6: e8 01 00 00 00 call c\n b: c3 ret\n c: c3 ret\n"

    def test_runtime_common_is_limited_to_exact_ucrt_storage_shape(self):
        symbol = dict(
            storage=2,
            section=0,
            value=8,
            type=0,
            name="?_OptionsStorage@?1??__local_stdio_printf_options@@9@9",
        )
        self.assertTrue(integration.runtime_common(symbol))
        for field, value in (
            ("name", "JS_FrameUnbound"),
            ("value", 16),
            ("section", 1),
            ("storage", 3),
            ("type", 32),
        ):
            self.assertFalse(integration.runtime_common(dict(symbol, **{field: value})))

    def test_diagnostic_configuration_and_compiler_flags_must_agree(self):
        with tempfile.TemporaryDirectory(prefix="retained profile ") as directory:
            build = Path(directory)
            (build / "CMakeCache.txt").write_text("QJS_INTERP_FRAME_DIAGNOSTICS:BOOL=ON\n")
            (build / "compile_commands.json").write_text(
                '[{"file":"quickjs-interpreter.c","command":"cc -O2"}]'
            )
            with self.assertRaisesRegex(RuntimeError, "disagree"):
                retained.diagnostic_profile(build)
            (build / "compile_commands.json").write_text(
                '[{"file":"quickjs-interpreter.c","command":"cc -DQJS_INTERP_FRAME_DIAGNOSTICS -O2"}]'
            )
            self.assertTrue(retained.diagnostic_profile(build))

    def test_external_address_route_ignores_an_unrelated_resolved_local_constant(self):
        code = bytes.fromhex("48 8d 0d 08 00 00 00 48 8d 35 00 00 00 00 c3 00")
        data = bytearray(60) + code
        relocation = len(data)
        data += struct.pack("<IIH", 10, 2, 4)
        table = len(data)
        for name, value, section, kind, storage in (
            (b"caller", 0, 1, 32, 3),
            (b"constant", 15, 1, 0, 3),
            (b"outside", 0, 0, 0, 2),
        ):
            data += struct.pack("<8sIhHBB", name.ljust(8, b"\0"), value, section, kind, storage, 0)
        data += struct.pack("<I", 4)
        struct.pack_into("<HHIIIHH", data, 0, 0x8664, 1, 0, table, 3, 0, 0)
        struct.pack_into(
            "<8sIIIIIIHHI",
            data,
            20,
            b".text\0\0\0",
            0,
            0,
            len(code),
            60,
            relocation,
            0,
            1,
            0,
            0x60300020,
        )
        listing = (
            b" 0: 48 8d 0d 08 00 00 00 lea rcx,[rip+0x8]\n"
            b" 7: 48 8d 35 00 00 00 00 lea rsi,[rip+0x0]\n e: c3 ret\n"
        )
        with tempfile.TemporaryDirectory(prefix="retained external ") as directory:
            build = Path(directory)
            path = build / "input.obj"
            path.write_bytes(data)
            router = retained.Router(path, build)
            process = SimpleNamespace(returncode=0, stdout=listing, stderr=b"")
            with (
                patch.object(retained, "find_objdump", return_value=Path("objdump")),
                patch.object(retained.subprocess, "run", return_value=process),
            ):
                router.address("caller", "outside", "native")
                router.finish()
            final = routes.C.Coff(path.read_bytes())
            self.assertEqual(routes.relocations(final, 1)[10][1], "native")
            self.assertEqual(final.sections[0]["sha256"], routes.C.Coff(data).sections[0]["sha256"])

    def test_selected_table_load_requires_the_original_owner_field_and_register(self):
        code = bytes.fromhex("48 8b 35 08 00 00 00 c3")
        data = bytearray(60) + code
        relocation = len(data)
        data += struct.pack("<IIH", 3, 1, 4)
        table = len(data)
        for name, value, section, kind, storage in (
            (b"caller", 0, 1, 32, 3),
            (b"owner", 0, 0, 0, 2),
        ):
            data += struct.pack("<8sIhHBB", name.ljust(8, b"\0"), value, section, kind, storage, 0)
        data += struct.pack("<I", 4)
        struct.pack_into("<HHIIIHH", data, 0, 0x8664, 1, 0, table, 2, 0, 0)
        struct.pack_into(
            "<8sIIIIIIHHI",
            data,
            20,
            b".text\0\0\0",
            0,
            0,
            len(code),
            60,
            relocation,
            0,
            1,
            0,
            0x60300020,
        )
        listing = b" 0: 48 8b 35 08 00 00 00 mov rsi,QWORD PTR [rip+0x8]\n 7: c3 ret\n"
        with tempfile.TemporaryDirectory(prefix="retained table ") as directory:
            build = Path(directory)
            path = build / "input.obj"
            path.write_bytes(data)
            router = retained.Router(path, build)
            process = SimpleNamespace(returncode=0, stdout=listing, stderr=b"")
            with (
                patch.object(retained, "find_objdump", return_value=Path("objdump")),
                patch.object(retained.subprocess, "run", return_value=process),
            ):
                router.pointer_load("caller", "owner", 8, "rsi")
                for offset, register in ((0, "rsi"), (8, "rdi")):
                    with self.assertRaisesRegex(RuntimeError, "selected table load changed"):
                        router.pointer_load("caller", "owner", offset, register)
                proof = router.finish()
            self.assertEqual(proof["routes"], [])
            self.assertEqual(proof["profile_contracts"][0]["addend"], 8)
            self.assertEqual(
                routes.C.Coff(path.read_bytes()).sections[0]["sha256"],
                routes.C.Coff(data).sections[0]["sha256"],
            )

    def test_only_the_diagnostic_profile_accepts_an_empty_publication_producer(self):
        with tempfile.TemporaryDirectory(prefix="retained publication ") as directory:
            build = Path(directory)
            raw = bytearray(64)
            struct.pack_into("<HHIIIHH", raw, 0, 0x8664, 1, 0, 60, 0, 0, 0)
            struct.pack_into(
                "<8sIIIIIIHHI", raw, 20, b".text\0\0\0", 0, 0, 0, 0, 0, 0, 0, 0, 0x60300020
            )
            struct.pack_into("<I", raw, 60, 4)
            path = build / "publication.obj"
            path.write_bytes(raw)
            recipe = {"object_path": "generated/quickjs-interpreter-publish.obj"}
            (build / "CMakeCache.txt").write_text("QJS_INTERP_FRAME_DIAGNOSTICS:BOOL=ON\n")
            (build / "compile_commands.json").write_text(
                '[{"file":"quickjs-interpreter.c","command":"cc -DQJS_INTERP_FRAME_DIAGNOSTICS -O2"}]'
            )
            proof = retained.route(ROOT, build, path, recipe, "mingw", set())
            self.assertEqual(proof["routes"], [])
            self.assertEqual(len(proof["profile_contracts"]), 1)
            (build / "CMakeCache.txt").write_text("QJS_INTERP_FRAME_DIAGNOSTICS:BOOL=OFF\n")
            (build / "compile_commands.json").write_text(
                '[{"file":"quickjs-interpreter.c","command":"cc -O2"}]'
            )
            with self.assertRaisesRegex(RuntimeError, "Need one retained source symbol"):
                retained.route(ROOT, build, path, recipe, "mingw", set())
            path.write_bytes(fixture())
            with self.assertRaisesRegex(RuntimeError, "not the empty producer"):
                retained.publish(retained.Router(path, build), ROOT, diagnostics=True)

    def test_string_receiver_route_retains_the_float_index_guard(self):
        code = bytes.fromhex("41 83 7d f8 00 0f 85 00 00 00 00 41 83 7d e8 ff 0f 85 00 00 00 00 c3")
        data = bytearray(60) + code
        relocation = len(data)
        for offset in (7, 18):
            data += struct.pack("<IIH", offset, 1, 4)
        table = len(data)
        for name, value in ((b"dispatch", 0), (b"target", 22)):
            data += struct.pack("<8sIhHBB", name.ljust(8, b"\0"), value, 1, 32, 3, 0)
        data += struct.pack("<I", 4)
        struct.pack_into("<HHIIIHH", data, 0, 0x8664, 1, 0, table, 2, 0, 0)
        struct.pack_into(
            "<8sIIIIIIHHI",
            data,
            20,
            b".text\0\0\0",
            0,
            0,
            len(code),
            60,
            relocation,
            0,
            2,
            0,
            0x60300020,
        )
        listing = (
            b" 0: 41 83 7d f8 00 cmp DWORD PTR [r13-0x8],0x0\n"
            b" 5: 0f 85 00 00 00 00 jne b\n"
            b" b: 41 83 7d e8 ff cmp DWORD PTR [r13-0x18],0xffffffff\n"
            b" 10: 0f 85 00 00 00 00 jne 16\n 16: c3 ret\n"
        )
        with tempfile.TemporaryDirectory(prefix="retained index ") as directory:
            build = Path(directory)
            path = build / "input.obj"
            path.write_bytes(data)
            router = retained.Router(path, build)
            process = SimpleNamespace(returncode=0, stdout=listing, stderr=b"")
            with (
                patch.object(retained, "find_objdump", return_value=Path("objdump")),
                patch.object(retained.subprocess, "run", return_value=process),
            ):
                router.branches(
                    "dispatch",
                    "target",
                    "string",
                    mnemonic="jne",
                    comparison="cmp DWORD PTR [r13-0x18],0xffffffff",
                )
                router.finish()
            final = routes.C.Coff(path.read_bytes())
            self.assertEqual(
                {off: r[1] for off, r in routes.relocations(final, 1).items()},
                {7: "target", 18: "string"},
            )
            self.assertEqual(final.sections[0]["sha256"], routes.C.Coff(data).sections[0]["sha256"])

    def test_named_span_retains_the_other_resolved_call(self):
        with tempfile.TemporaryDirectory(prefix="retained source ") as directory:
            build = Path(directory)
            path = build / "input.obj"
            path.write_bytes(fixture(False))
            router = retained.Router(path, build)
            process = SimpleNamespace(returncode=0, stdout=self.listing, stderr=b"")
            with (
                patch.object(retained, "find_objdump", return_value=Path("objdump")),
                patch.object(retained.subprocess, "run", return_value=process),
            ):
                router.branches("callerA", "target", "nativeA")
                proof = router.finish()
            self.assertEqual([(r["role"], r["offset"]) for r in proof["routes"]], [("callerA", 1)])
            final = routes.C.Coff(path.read_bytes())
            self.assertEqual(routes.relocations(final, 1)[1][1], "nativeA")
            r = final.section_records[0]
            self.assertEqual(path.read_bytes()[r["raw"] + 6 : r["raw"] + 13], fixture(False)[66:73])

    def test_legacy_rename_preserves_all_existing_reference_locations(self):
        with tempfile.TemporaryDirectory(prefix="retained source ") as directory:
            build = Path(directory)
            path = build / "input.obj"
            raw = fixture()
            path.write_bytes(raw)
            router = retained.Router(path, build)
            router.rename("target", "legacy")
            router.alias("fallback", "target")
            router.finish()
            final = routes.C.Coff(path.read_bytes())
            self.assertEqual(
                {off: r[1] for off, r in routes.relocations(final, 1).items()},
                {1: "legacy", 7: "legacy"},
            )
            self.assertEqual(final.symbols["fallback"]["value"], 12)
            self.assertEqual(final.sections[0]["sha256"], routes.C.Coff(raw).sections[0]["sha256"])

    def test_unselected_instruction_corruption_fails_before_writing(self):
        with tempfile.TemporaryDirectory(prefix="retained source ") as directory:
            build = Path(directory)
            path = build / "input.obj"
            raw = fixture(False)
            path.write_bytes(raw)
            router = retained.Router(path, build)
            router.co.data[65] = 0x90
            with self.assertRaisesRegex(RuntimeError, "outside selected operands"):
                router.finish()
            self.assertEqual(path.read_bytes(), raw)

    def test_decoder_listing_must_match_the_exact_current_bytes(self):
        with tempfile.TemporaryDirectory(prefix="retained source ") as directory:
            build = Path(directory)
            path = build / "input.obj"
            path.write_bytes(fixture(False))
            router = retained.Router(path, build)
            process = SimpleNamespace(
                returncode=0, stdout=self.listing.replace(b"e8 07", b"e9 07"), stderr=b""
            )
            with (
                patch.object(retained, "find_objdump", return_value=Path("objdump")),
                patch.object(retained.subprocess, "run", return_value=process),
                self.assertRaisesRegex(RuntimeError, "not bound to its input"),
            ):
                router.branches("callerA", "target", "nativeA")


if __name__ == "__main__":
    unittest.main()
