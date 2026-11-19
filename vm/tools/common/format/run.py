#!/usr/bin/env python3
"""Run the same pinned formatting policy locally and in CI."""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import sysconfig

ROOT = Path(__file__).resolve().parents[3]
LANGUAGES = ("native", "python", "cmake", "shell", "meson", "powershell", "js", "contracts")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--write", action="store_true")
    parser.add_argument("--language", choices=("all", *LANGUAGES), default="all")
    args = parser.parse_args()

    # Prefer the project-local development environment without requiring shell
    # activation, global package installation or a persistent PATH change.
    environment = ROOT / "build/format-tools"
    if not environment.is_dir() and (ROOT.parent / "build/format-tools").is_dir():
        environment = ROOT.parent / "build/format-tools"
    local_python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if local_python.is_file() and Path(sys.prefix).resolve() != environment.resolve():
        return subprocess.call([str(local_python), str(Path(__file__)), *sys.argv[1:]], cwd=ROOT)

    env = os.environ.copy()
    clang_format = Path(sysconfig.get_path("scripts")) / (
        "clang-format.exe" if os.name == "nt" else "clang-format"
    )
    if clang_format.is_file():
        env.setdefault("CLANG_FORMAT", str(clang_format))
    action = "--write" if args.write else "--check"
    selected = LANGUAGES if args.language == "all" else (args.language,)
    commands = []
    for language in selected:
        if language == "native":
            commands.append([sys.executable, "tools/common/format/native.py", action])
        elif language in {"python", "cmake"}:
            commands.append(
                [sys.executable, "tools/common/format/project.py", action, "--language", language]
            )
        elif language in {"shell", "meson", "powershell"}:
            commands.append(
                [sys.executable, "tools/common/format/scripts.py", action, "--language", language]
            )
        elif language == "js":
            package = ROOT / "node_modules/prettier/package.json"
            if not package.is_file():
                parser.error("Run npm ci --ignore-scripts --no-audit --no-fund first")
            data = json.loads(package.read_text(encoding="utf-8"))
            expected = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))[
                "devDependencies"
            ]["prettier"]
            if data["version"] != expected:
                parser.error("Expected Prettier " + expected + "; run npm ci")
            node = shutil.which("node")
            if not node:
                parser.error("Node.js must be on PATH")
            binary = data["bin"]
            if isinstance(binary, dict):
                binary = binary["prettier"]
            commands.append([sys.executable, "tools/common/format/frozen_js.py"])
            commands.append([node, str(package.parent / binary), action, "**/*.{js,mjs}"])
        else:
            commands.append([sys.executable, "tools/common/format/contracts.py"])
    for command in commands:
        result = subprocess.run(command, cwd=ROOT, env=env)
        if result.returncode:
            return result.returncode
    return 0


if __name__ == "__main__":
    sys.exit(main())
