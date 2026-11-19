"""Use linked current ELF extents,not guessed code ranges,in passive fixture."""

import argparse, subprocess, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from common.paths import activate_tools

activate_tools()
from elf64 import Elf64

ap = argparse.ArgumentParser()
ap.add_argument("--exe", type=Path, required=True)
ap.add_argument("--runner", nargs=argparse.REMAINDER, required=True)
a = ap.parse_args()
elf = Elf64.read(a.exe, expected_machine=183)
symbols = {s["name"]: s for s in elf.symbols() if s["type"] == 2 and s["size"]}
generic = symbols["JS_FrameAArch64GenericInvoke"]
gate = symbols["JS_FrameAArch64CInvoke"]
step = symbols["JS_AArch64Step"]
args = [
    generic["size"],
    gate["value"] - generic["value"],
    gate["size"],
    step["value"] - generic["value"],
    step["size"],
]
raise SystemExit(subprocess.run([*a.runner, str(a.exe), *map(str, args)]).returncode)
