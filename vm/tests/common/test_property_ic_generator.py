"""The opcode generator must preserve qualified backports and IC composition."""

from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from common.paths import source_file


class PropertyGeneratorContract(unittest.TestCase):
    def test_qualified_opcode_roundtrip(self):
        with tempfile.TemporaryDirectory(prefix="qjs-property-ops-") as folder:
            target = Path(folder)
            (target / "src/common/call").mkdir(parents=True)
            for name in ("quickjs.c", "quickjs-opcode.h", "src/sources.json"):
                shutil.copyfile(source_file(ROOT, name), target / name)
            run = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(ROOT / "tools/common/backports/generate-ops.py"),
                    "--source",
                    str(target),
                    "--lazy-var-refs",
                    "--local-captures",
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(run.returncode, 0, run.stderr)
            for name in (
                "quickjs-interpreter-ops.inc",
                "quickjs-interpreter-opcodes.h",
                "quickjs-interpreter-dispatch.inc",
            ):
                relative = "src/common/call/" + name
                self.assertEqual(
                    (target / relative).read_text(encoding="utf-8"),
                    (ROOT / relative).read_text(encoding="utf-8"),
                    name,
                )


if __name__ == "__main__":
    unittest.main()
