#!/usr/bin/env python3
"""Format owned C and assembly, and verify immutable upstream/generated inputs."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
MANIFEST = ROOT / "tools/common/format/native-frozen.json"
VERSION = "22.1.8"
C_SUFFIXES = {".c", ".h", ".cc", ".cpp", ".cxx", ".hpp", ".hxx", ".inc"}
CPP_SUFFIXES = {".cc", ".cpp", ".cxx", ".hpp", ".hxx"}
ASSEMBLY_SUFFIXES = {".s", ".asm"}


def is_assembly(path):
    return path.relative_to(ROOT).parts[0] == "asm" or path.suffix.lower() in ASSEMBLY_SUFFIXES


TOKEN = re.compile(
    r"""(?P<space>\s+)|(?P<comment>/\*.*?\*/|//[^\n]*)|"""
    r"""(?P<string>(?:u8|L|u|U)?"(?:\\.|[^"\\])*")|"""
    r"""(?P<char>(?:L|u|U)?'(?:\\.|[^'\\])*')|"""
    r"""(?P<id>[A-Za-z_]\w*)|(?P<number>(?:\d|\.\d)[\w.]*|0[xX][\w.]+)|"""
    r"""(?P<punct>.)""",
    re.S,
)


def digest(data):
    return hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()


def tokens(text):
    # C translation phase 2 removes escaped newlines before tokenization.
    text = text.replace("\\\n", "")
    return [
        (m.lastgroup, m.group())
        for m in TOKEN.finditer(text)
        if m.lastgroup not in ("space", "comment")
    ]


def candidates():
    """Walk product sources without requiring a Git checkout or built tools."""
    paths = [
        p
        for p in ROOT.iterdir()
        if p.is_file() and (p.suffix in C_SUFFIXES or p.suffix.lower() in ASSEMBLY_SUFFIXES)
    ]
    for directory in ("src", "asm", "tests", "examples", "gen"):
        if not (ROOT / directory).is_dir():
            continue
        for path in (ROOT / directory).rglob("*"):
            if not path.is_file() or any(
                part in {"test262", "node_modules", "build"} for part in path.parts
            ):
                continue
            if directory == "asm":
                wanted = path.suffix.lower() in (".s", ".asm", ".inc")
            else:
                wanted = path.suffix in C_SUFFIXES or path.suffix.lower() in ASSEMBLY_SUFFIXES
            if wanted:
                paths.append(path)
    if (ROOT / "tools").is_dir():
        paths.extend((ROOT / "tools").rglob("*.ld"))
    for path in paths:
        if path.is_symlink() or not path.resolve().is_relative_to(ROOT):
            raise RuntimeError("Refusing a linked or foreign source: " + str(path))
    return sorted(paths, key=lambda p: p.relative_to(ROOT).as_posix())


def assembly(text):
    """Use four-space instruction indentation without changing assembly text."""
    result = []
    for line in text.splitlines():
        body = line.strip()
        if not body:
            result.append("")
            continue
        fields = body.split(None, 2)
        first = fields[0].upper()
        second = fields[1].upper() if len(fields) > 1 else ""
        leading = (
            body.startswith((".", "#", ";", "/*", "*", "//"))
            or body.endswith(":")
            or first in {"INCLUDE", "OPTION", "EXTERN", "PUBLIC", "END"}
            or second in {"PROC", "ENDP", "SEGMENT", "ENDS", "LABEL", "EQU", "DB", "DW", "DD", "DQ"}
        )
        result.append(("" if leading else "    ") + body)
    return "\n".join(result) + ("\n" if text.endswith("\n") else "")


def linker(text):
    """Normalize indentation to four columns, preserving all section selectors."""
    result = []
    for line in text.splitlines():
        expanded = line.expandtabs(4)
        width = len(expanded) - len(expanded.lstrip())
        result.append(" " * (((width + 3) // 4) * 4) + expanded.strip() if line.strip() else "")
    return "\n".join(result) + ("\n" if text.endswith("\n") else "")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--write", action="store_true")
    parser.add_argument("--clang-format", default=os.environ.get("CLANG_FORMAT", "clang-format"))
    args = parser.parse_args()
    tool = shutil.which(args.clang_format)
    if not tool:
        parser.error("Install clang-format==" + VERSION + " or set CLANG_FORMAT")
    version = subprocess.check_output([tool, "--version"], text=True).strip()
    if not re.search(r"\b" + re.escape(VERSION) + r"\b", version):
        parser.error("Expected clang-format " + VERSION + ", got " + version)

    frozen = json.loads(MANIFEST.read_text(encoding="utf-8"))["files"]
    candidates_list = candidates()
    actual_paths = {p.relative_to(ROOT).as_posix() for p in candidates_list}
    missing = set(frozen) - actual_paths
    failures = []
    changed = []
    counts = {"frozen": 0, "frozen_c_checked": 0, "c": 0, "assembly": 0, "linker": 0}
    still_missing = []
    for relative in sorted(missing):
        upstream_path = ROOT.parent / relative
        if not upstream_path.is_file():
            still_missing.append(relative)
            continue
        counts["frozen"] += 1
        actual_sha = hashlib.sha256(upstream_path.read_bytes()).hexdigest()
        if actual_sha != frozen[relative]["sha256"]:
            failures.append(f"Upstream frozen file modified: ../{relative}")
    if still_missing:
        raise SystemExit("Frozen source files are missing: " + ", ".join(still_missing))
    for path in candidates_list:
        relative = path.relative_to(ROOT).as_posix()
        raw = path.read_bytes()
        if relative in frozen:
            entry = frozen[relative]
            counts["frozen"] += 1
            if digest(raw) != entry["sha256"]:
                failures.append(relative + ": frozen input hash differs")
            check_format = entry.get("format_check", False)
            if type(check_format) is not bool:
                raise RuntimeError(relative + ": invalid frozen format_check value")
            if not check_format:
                continue
        old = raw.decode("utf-8").replace("\r\n", "\n")
        if is_assembly(path) or path.suffix == ".ld":
            kind = "linker" if path.suffix == ".ld" else "assembly"
            counts[kind] += 1
            new = linker(old) if kind == "linker" else assembly(old)
            if [line.strip() for line in old.splitlines()] != [
                line.strip() for line in new.splitlines()
            ]:
                raise RuntimeError(relative + ": " + kind + " contents changed")
        else:
            counts["frozen_c_checked" if relative in frozen else "c"] += 1
            command = [
                tool,
                "--style=file:" + str(ROOT / ".clang-format"),
                "--assume-filename="
                + path.with_suffix(".cpp" if path.suffix in CPP_SUFFIXES else ".c").name,
            ]
            run = subprocess.run(
                command, input=old, text=True, encoding="utf-8", capture_output=True
            )
            if run.returncode:
                raise RuntimeError(relative + ": " + run.stderr)
            new = run.stdout.replace("\r\n", "\n")
            if tokens(old) != tokens(new):
                raise RuntimeError(relative + ": formatter changed C tokens or literals")
        if old != new:
            changed.append(relative)
            if args.write:
                path.write_text(new, encoding="utf-8", newline="\n")
    if failures:
        print("\n".join(failures), file=sys.stderr)
    if args.check and changed:
        print("Formatting required:\n" + "\n".join(changed), file=sys.stderr)
    print("Native format:", counts, "changed:", len(changed), "frozen failures:", len(failures))
    return int(bool(failures or (args.check and changed)))


if __name__ == "__main__":
    sys.exit(main())
