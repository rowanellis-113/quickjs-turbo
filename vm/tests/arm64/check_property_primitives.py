"""Actual linked helper extents for passive natural callback unwind checks."""

import argparse, subprocess, sys
from pathlib import Path

ap = argparse.ArgumentParser(description=__doc__)
ap.add_argument("--exe", type=Path, required=True)
ap.add_argument("--mode", choices=("semantics", "oom"), default="semantics")
ap.add_argument("--runner", nargs=argparse.REMAINDER, required=True)
a = ap.parse_args()
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from common.paths import activate_tools

activate_tools()
from elf64 import Elf64

symbols = {
    s["name"]: s
    for s in Elf64.read(a.exe, expected_machine=183).symbols()
    if s["type"] == 2 and s["size"]
}
b, step = (symbols[n] for n in ("JS_FrameAArch64BuiltinInvoke", "JS_AArch64Step"))
args = [*a.runner, str(a.exe), str(b["size"]), str(step["value"] - b["value"]), str(step["size"])]
if a.mode == "oom":
    args += ["oom"]
raise SystemExit(subprocess.run(args).returncode)
