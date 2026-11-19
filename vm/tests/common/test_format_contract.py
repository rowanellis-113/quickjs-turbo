"""Formatting checks only govern our own source files, never upstream inputs."""

import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]


def load(name):
    spec = importlib.util.spec_from_file_location(
        name, ROOT / "tools/common/format" / (name + ".py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


NATIVE = load("native")
PROJECT = load("project")
CONTRACTS = load("contracts")
SCRIPTS = load("scripts")


class FormattingContracts(unittest.TestCase):
    def test_shell_contract_preserves_here_document_contents_and_scope(self):
        tool = Path(SCRIPTS.sysconfig.get_path("scripts")) / (
            "shfmt.exe" if sys.platform == "win32" else "shfmt"
        )
        self.assertEqual(
            SCRIPTS.shell_ast(tool, "if true; then\n echo one\nfi\n"),
            SCRIPTS.shell_ast(tool, "if true; then\n    echo one\nfi\n"),
        )
        self.assertNotEqual(
            SCRIPTS.shell_ast(tool, "cat <<'END'\n  literal\nEND\n"),
            SCRIPTS.shell_ast(tool, "cat <<'END'\nliteral\nEND\n"),
        )
        self.assertNotEqual(
            SCRIPTS.shell_ast(tool, "if true; then\necho one\nfi\necho two\n"),
            SCRIPTS.shell_ast(tool, "if true; then\necho one\necho two\nfi\n"),
        )

    def test_linker_preserves_selector_order_and_line_contents(self):
        text = "SECTIONS\n{\n  .text : { *(.one) *(.two) }\n}\n"
        formatted = NATIVE.linker(text)
        self.assertEqual(formatted, NATIVE.linker(formatted))
        self.assertEqual(text.splitlines()[2].strip(), formatted.splitlines()[2].strip())

    def test_meson_contract_preserves_statements_and_literal_contents(self):
        self.assertEqual(SCRIPTS.meson_ast("a=[1,2]\n"), SCRIPTS.meson_ast("a = [1, 2,]\n"))
        self.assertNotEqual(SCRIPTS.meson_ast("a='one'\n"), SCRIPTS.meson_ast("a='two'\n"))
        self.assertNotEqual(
            SCRIPTS.meson_ast("if true\na=1\nendif\nb=2\n"),
            SCRIPTS.meson_ast("if true\na=1\nb=2\nendif\n"),
        )

    def test_cpp_sources_are_discovered_without_build_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            (root / "example.cc").write_text("int main() {}\n")
            (root / "src").mkdir()
            (root / "src/example.hpp").write_text("struct Example {};\n")
            (root / "tests").mkdir()
            (root / "tests/callee-saved.S").write_text("entry:\n  ret\n")
            (root / "build").mkdir()
            (root / "build/unowned.cpp").write_text("int ignored;\n")
            with patch.object(NATIVE, "ROOT", root):
                selected = {path.relative_to(root).as_posix() for path in NATIVE.candidates()}
            self.assertEqual(selected, {"example.cc", "src/example.hpp", "tests/callee-saved.S"})

    def test_c_literals_and_token_order_are_protected(self):
        self.assertEqual(NATIVE.tokens("x=call(1);"), NATIVE.tokens("x = call(\n 1);\n"))
        self.assertNotEqual(NATIVE.tokens('x="a b";'), NATIVE.tokens('x="a  b";'))
        self.assertNotEqual(NATIVE.tokens("a(); b();"), NATIVE.tokens("b(); a();"))

    def test_gas_and_masm_preserve_line_contents_and_order(self):
        for source in (
            '  .text\n  entry:\n\tmov rax, rbx\n .asciz "a  b"\n',
            "  PUBLIC entry\n entry PROC FRAME\n\tpush rbp\n entry ENDP\n END\n",
        ):
            with self.subTest(source=source):
                formatted = NATIVE.assembly(source)
                self.assertEqual(
                    [line.strip() for line in source.splitlines()],
                    [line.strip() for line in formatted.splitlines()],
                )
                self.assertEqual(NATIVE.assembly(formatted), formatted)

    def test_cmake_arguments_and_literal_whitespace_are_protected(self):
        self.assertEqual(
            PROJECT.cmake_tokens('set(A "one two") # comment\n'),
            PROJECT.cmake_tokens('set(\n    A "one two"\n)\n'),
        )
        self.assertNotEqual(
            PROJECT.cmake_tokens('set(A "one two")'),
            PROJECT.cmake_tokens('set(A "one  two")'),
        )

    def test_python_formatter_rolls_back_a_semantic_change(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            path = root / "sample.py"
            original = b'value = "original"\n'
            path.write_bytes(original)

            def mutate(*args, **kwargs):
                path.write_text('value = "changed"\n')
                return subprocess.CompletedProcess(args[0], 0)

            with (
                patch.object(PROJECT, "ROOT", root),
                patch.object(PROJECT.subprocess, "run", side_effect=mutate),
            ):
                with self.assertRaisesRegex(RuntimeError, "changed the AST"):
                    PROJECT.format_python([path], True)
            self.assertEqual(path.read_bytes(), original)

    def test_python_formatter_rolls_back_partial_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            path = root / "sample.py"
            original = b"value=1\n"
            path.write_bytes(original)

            def partial_failure(*args, **kwargs):
                path.write_text("value = 1\n")
                return subprocess.CompletedProcess(args[0], 2)

            with (
                patch.object(PROJECT, "ROOT", root),
                patch.object(PROJECT.subprocess, "run", side_effect=partial_failure),
            ):
                self.assertEqual(PROJECT.format_python([path], True), 2)
            self.assertEqual(path.read_bytes(), original)

    def test_receipt_check_does_not_treat_symbol_fingerprints_as_files(self):
        source = "tools/common/format/native.py"
        data = {"source": source, "source_sha256": "a" * 64, "compiler_symbol": "b" * 64}
        records = list(CONTRACTS.receipts(data))
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0][1:3], ("source_sha256", ROOT / source))

    def test_stale_python_factory_pin_fails_without_accepting_new_hashes(self):
        manifest = ROOT / "tools/common/format/contracts.py"
        source = ROOT / "tools/common/format/native.py"
        with (
            patch.object(CONTRACTS, "manifests", return_value=[]),
            patch.object(
                CONTRACTS, "python_source_receipts", return_value=[(manifest, source, "0" * 64)]
            ),
        ):
            self.assertEqual(CONTRACTS.main(), 1)

    def test_owned_c_worker_reflow_preserves_the_measured_constraint(self):
        spec = importlib.util.spec_from_file_location(
            "owned_c_workers", ROOT / "tools/common/elf/c_workers.py"
        )
        workers = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(workers)
        old = "offsetof(JSFrame,bytecode)==80"
        source = '_Static_assert(offsetof(JSFrame, bytecode) == 80, "ABI");'
        result = workers.replace_one(source, old, "FRAME_OFFSET", "measured offset")
        self.assertEqual(result, '_Static_assert(FRAME_OFFSET, "ABI");')
        with self.assertRaisesRegex(ValueError, "measured offset"):
            workers.replace_one(source.replace("== 80", "== 88"), old, "ignored", "measured offset")


if __name__ == "__main__":
    unittest.main()
