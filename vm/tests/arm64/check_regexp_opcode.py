"""Pass actual linked function extents to the natural-unwind API fixture."""

import argparse, subprocess, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from common.paths import activate_tools

activate_tools()
from elf64 import Elf64

ap = argparse.ArgumentParser()
ap.add_argument("--exe", type=Path, required=True)
ap.add_argument("--mode", required=True)
ap.add_argument("--runner", nargs=argparse.REMAINDER, required=True)
a = ap.parse_args()
elf = Elf64.read(a.exe, expected_machine=183)
symbols = {s["name"]: s for s in elf.symbols() if s["type"] == 2 and s["size"]}
helper = symbols["JS_FrameInterpRegExp"]
vm = symbols["JS_FrameInterp"]
slow = symbols["JS_AArch64Step"]
assert 0 < helper["size"] < 1024 * 1024 and 0 < slow["size"] < 1024 * 1024
cmd = [
    *a.runner,
    str(a.exe),
    a.mode,
    str(helper["size"]),
    str(slow["value"] - vm["value"]),
    str(slow["size"]),
]
raise SystemExit(subprocess.run(cmd).returncode)
