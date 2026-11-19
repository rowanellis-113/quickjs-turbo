#!/usr/bin/env python3
"""Verify JavaScript fixtures intentionally excluded from Prettier."""

import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
manifest = json.loads((ROOT / "tools/common/format/js-frozen.json").read_text(encoding="utf-8"))
failures = []
for name, expected in manifest["files"].items():
    path = ROOT / name
    if not path.is_file() and (ROOT.parent / name).is_file():
        path = ROOT.parent / name
    if not path.is_file():
        failures.append(name + ": missing")
        continue
    actual = hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    if actual != expected["sha256"]:
        failures.append(name + ": frozen input hash differs")
base_dm = ROOT if (ROOT / "tests/detect_module").is_dir() else ROOT.parent
directory = base_dm / "tests/detect_module"
listed = {name for name in manifest["files"] if name.startswith("tests/detect_module/")}
actual = {p.relative_to(base_dm).as_posix() for p in directory.glob("*.js")}
if actual != listed:
    failures.append("tests/detect_module: add or remove fixtures in the manifest explicitly")
if failures:
    print("\n".join(failures), file=sys.stderr)
    sys.exit(1)
print("Verified", len(manifest["files"]), "immutable JavaScript source fixtures.")
