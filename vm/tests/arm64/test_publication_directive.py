"""Assembly directive boundary contract tests for ARM64 publication emitters."""

import importlib.util
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from arm64.paths_arm64 import activate_arm64_tools

activate_arm64_tools()


class PublicationDirectiveTests(unittest.TestCase):
    def test_assembly_directive_boundary_accepts_indentation_and_rejects_decoys(self):
        spec = importlib.util.spec_from_file_location(
            "arm_publication", ROOT / "tools/arm64/vm/publication.py"
        )
        publication = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(publication)
        for indentation in ("", "    ", "\t"):
            source = '.asciz ".cfi_endproc"\n' + indentation + ".cfi_endproc\n"
            start = publication.assembly_line_start(source, ".cfi_endproc")
            self.assertEqual(source[start:].strip(), ".cfi_endproc")
        for source in ('.asciz ".cfi_endproc"\n', ".cfi_endproc\n.cfi_endproc\n"):
            with self.subTest(source=source), self.assertRaises(ValueError):
                publication.assembly_line_start(source, ".cfi_endproc")


if __name__ == "__main__":
    unittest.main()
