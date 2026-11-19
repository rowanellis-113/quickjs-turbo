"""Bind natural cleanup unwind observations to actual linked function extents."""

import argparse, subprocess, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from common.paths import activate_tools

activate_tools()
from elf64 import Elf64

ap = argparse.ArgumentParser()
ap.add_argument("--exe", type=Path, required=True)
ap.add_argument("--mode", choices=["semantics", "oom"], default="semantics")
ap.add_argument("--runner", nargs=argparse.REMAINDER, required=True)
a = ap.parse_args()
symbols = {
    s["name"]: s
    for s in Elf64.read(a.exe, expected_machine=183).symbols()
    if s["type"] == 2 and s["size"]
}
free = symbols["JS_FrameInterpFree"]
step = symbols["JS_AArch64Step"]
args = [free["size"], step["value"] - free["value"], step["size"]]
raise SystemExit(
    subprocess.run(
        [*a.runner, str(a.exe), *map(str, args), *(["oom"] if a.mode == "oom" else [])]
    ).returncode
)
