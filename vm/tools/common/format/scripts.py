#!/usr/bin/env python3
"""Format build scripts with syntax guards; never execute the target scripts."""

import argparse
import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import sysconfig
import tempfile

ROOT = Path(__file__).resolve().parents[3]


def shell_ast(tool, text):
    result = subprocess.run(
        [str(tool), "-ln", "bash", "--to-json"],
        input=text,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=True,
    )

    def normalize(value):
        if isinstance(value, dict):
            return {
                key: normalize(item)
                for key, item in value.items()
                if key != "Comments"
                and not (isinstance(item, dict) and set(item) == {"Offset", "Line", "Col"})
            }
        if isinstance(value, list):
            return [normalize(item) for item in value]
        return value

    return normalize(json.loads(result.stdout))


def meson_ast(text):
    from mesonbuild import mparser

    ignored = {
        "lineno",
        "colno",
        "filename",
        "end_lineno",
        "end_colno",
        "bytespan",
        "whitespaces",
        "pre_whitespaces",
        "level",
        "ast_id",
        "condition_level",
        "commas",
        "colons",
    }

    def normalize(value):
        if isinstance(value, mparser.BaseNode):
            return (
                type(value).__name__,
                [(key, normalize(item)) for key, item in vars(value).items() if key not in ignored],
            )
        if isinstance(value, dict):
            return [(normalize(key), normalize(item)) for key, item in value.items()]
        if isinstance(value, (list, tuple)):
            return [normalize(item) for item in value]
        return value

    return normalize(mparser.Parser(text, "source").parse())


def format_sources(language, write):
    if language == "shell":
        if version("shfmt-py") != "4.2.0":
            raise RuntimeError("Install shfmt-py==4.2.0")
        tool = Path(sysconfig.get_path("scripts")) / ("shfmt.exe" if os.name == "nt" else "shfmt")
        if subprocess.check_output([str(tool), "--version"], text=True).strip() != "v3.14.1":
            raise RuntimeError("Expected upstream shfmt v3.14.1")
        paths = sorted((ROOT / "tools").rglob("*.sh"))

        def formatter(text, path):
            return subprocess.run(
                [str(tool), "-ln", "bash", "-i", "4", "-ci", "-sr"],
                input=text,
                text=True,
                encoding="utf-8",
                capture_output=True,
                check=True,
            ).stdout

        def contract(text):
            return shell_ast(tool, text)
    else:
        if version("meson") != "1.12.1":
            raise RuntimeError("Install meson==1.12.1")
        from mesonbuild import mformat

        engine = mformat.Formatter(None, True, False)
        paths = sorted(ROOT.rglob("meson.build"))
        formatter = engine.format
        contract = meson_ast
    changes = {}
    for path in paths:
        if path.is_symlink() or not path.resolve().is_relative_to(ROOT):
            raise RuntimeError("Refusing linked or foreign source: " + str(path))
        original = path.read_text(encoding="utf-8")
        formatted = formatter(original, path)
        if contract(original) != contract(formatted):
            raise RuntimeError(language + " formatter changed AST: " + str(path))
        if formatter(formatted, path) != formatted:
            raise RuntimeError(language + " formatter is not idempotent: " + str(path))
        if original != formatted:
            changes[path] = formatted
    for path, formatted in changes.items():
        if write:
            path.write_text(formatted, encoding="utf-8", newline="\n")
        else:
            print("Formatting required:", path.relative_to(ROOT).as_posix())
    print(language, "format:", len(paths), "files;", len(changes), "changed")
    return int(bool(changes) and not write)


def powershell(write):
    tools_root = (
        ROOT / "build/format-tools"
        if (ROOT / "build/format-tools").is_dir()
        else ROOT.parent / "build/format-tools"
    )
    module = tools_root / "powershell/PSScriptAnalyzer/1.24.0"
    receipt_path = module / "installed.json"
    if not receipt_path.is_file():
        raise RuntimeError("Run python tools/common/format/install_powershell.py first")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    for relative, expected in receipt["files"].items():
        path = (module / relative).resolve()
        if (
            not path.is_relative_to(module.resolve())
            or hashlib.sha256(path.read_bytes()).hexdigest() != expected
        ):
            raise RuntimeError("Modified formatter distribution: " + relative)
    executable = shutil.which("pwsh") or shutil.which("powershell.exe")
    if not executable:
        raise RuntimeError("PowerShell 7 or Windows PowerShell 5.1 is required")
    # Windows PowerShell's .NET loader rejects mapped drives. Stage only this
    # verified tool into a short-lived local directory, then remove it on exit.
    with tempfile.TemporaryDirectory(prefix="qjs-format-ps-") as directory:
        if Path(executable).name.lower() == "powershell.exe":
            target = Path(directory) / "PSScriptAnalyzer"
            target.mkdir()
            for relative in receipt["files"]:
                destination = target / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes((module / relative).read_bytes())
            module = target
        command = [
            executable,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(ROOT / "tools/common/format/powershell.ps1"),
            "-ModulePath",
            str(module / "PSScriptAnalyzer.psd1"),
        ]
        if write:
            command.append("-Write")
        return subprocess.call(command, cwd=ROOT)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    parser.add_argument("--language", choices=("shell", "meson", "powershell"), required=True)
    args = parser.parse_args()
    if args.language == "powershell":
        return powershell(args.write)
    return format_sources(args.language, args.write)


if __name__ == "__main__":
    sys.exit(main())
