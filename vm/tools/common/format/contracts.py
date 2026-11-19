#!/usr/bin/env python3
"""Verify source receipts without accepting new hashes or compiler fingerprints."""

import ast
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[3]
SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def source_path(value):
    if not isinstance(value, str) or Path(value).is_absolute() or ".." in Path(value).parts:
        return None
    for base in (ROOT, ROOT.parent):
        path = base / value
        if path.is_file() and path.resolve().is_relative_to(base.resolve()):
            return path
    return None


def receipts(value, normalized=False):
    """Yield only file-input hashes; compiled symbol fingerprints stay opaque."""
    if isinstance(value, dict):
        path = source_path(value.get("source"))
        expected = value.get("source_sha256")
        if path and isinstance(expected, str) and SHA256.fullmatch(expected):
            yield value, "source_sha256", path, normalized
        for key, entry in value.items():
            path = source_path(key)
            if path and isinstance(entry, str) and SHA256.fullmatch(entry):
                yield value, key, path, normalized
            elif (
                path and isinstance(entry, dict) and SHA256.fullmatch(str(entry.get("sha256", "")))
            ):
                yield entry, "sha256", path, normalized
            yield from receipts(entry, normalized)
    elif isinstance(value, list):
        for entry in value:
            yield from receipts(entry, normalized)


def manifests():
    paths = list((ROOT / "src").rglob("*.json"))
    paths.extend(
        ROOT / "tools/common/format" / name for name in ("native-frozen.json", "js-frozen.json")
    )
    return sorted(paths)


def digest(path, normalized):
    data = path.read_bytes()
    if normalized:
        data = data.replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def python_source_receipts():
    """Read explicit factory-file pins (OWNER + OWNER_SHA) without importing executable code."""
    for manifest in sorted((ROOT / "tools").rglob("*.py")):
        values = {}
        for node in ast.parse(manifest.read_text(encoding="utf-8")).body:
            if isinstance(node, ast.Assign) and len(node.targets) == 1:
                target = node.targets[0]
                if isinstance(target, ast.Name) and target.id in {"OWNER", "OWNER_SHA"}:
                    if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                        values[target.id] = node.value.value
        if "OWNER" in values or "OWNER_SHA" in values:
            path = source_path(values.get("OWNER"))
            expected = values.get("OWNER_SHA", "")
            if path is None or not SHA256.fullmatch(expected):
                raise RuntimeError("Invalid factory source pin in " + str(manifest))
            yield manifest, path, expected


def main():
    failures = []
    count = 0
    for manifest in manifests():
        data = json.loads(manifest.read_text(encoding="utf-8"))
        normalized = manifest.parent == ROOT / "tools/common/format"
        for container, key, path, normalize in receipts(data, normalized):
            count += 1
            if container[key] != digest(path, normalize):
                rel_input = (
                    path.relative_to(ROOT).as_posix()
                    if path.is_relative_to(ROOT)
                    else "../" + path.relative_to(ROOT.parent).as_posix()
                )
                failures.append(
                    manifest.relative_to(ROOT).as_posix() + ": stale input hash for " + rel_input
                )
    for manifest, path, expected in python_source_receipts():
        count += 1
        if expected != digest(path, False):
            failures.append(manifest.relative_to(ROOT).as_posix() + ": stale factory source hash")
    if failures:
        print("\n".join(failures), file=sys.stderr)
    print("Source receipts:", count, "checked;", len(failures), "stale")
    return int(bool(failures))


if __name__ == "__main__":
    sys.exit(main())
