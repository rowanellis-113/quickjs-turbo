#!/usr/bin/env python3
"""Format Python and CMake with pinned tools and language-level safety checks."""

import argparse
import ast
from importlib.metadata import version
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
VERSIONS = {"ruff": "0.14.14", "cmakelang": "0.6.13"}


def files(language):
    """Discover owned sources in both checkouts and self-contained archives."""
    roots = ("tools", "tests") if language == "python" else ("cmake", "tests", "examples")
    selected = []
    if language == "cmake" and (ROOT / "CMakeLists.txt").is_file():
        selected.append(ROOT / "CMakeLists.txt")
    for directory in roots:
        if not (ROOT / directory).is_dir():
            continue
        for path in (ROOT / directory).rglob("*"):
            wanted = (
                path.suffix == ".py"
                if language == "python"
                else (path.suffix == ".cmake" or path.name == "CMakeLists.txt")
            )
            if path.is_file() and wanted:
                if path.is_symlink() or not path.resolve().is_relative_to(ROOT):
                    raise RuntimeError("Refusing a linked or foreign source: " + str(path))
                selected.append(path)
    return sorted(set(selected), key=lambda path: path.relative_to(ROOT).as_posix())


def python_ast(text):
    return ast.dump(ast.parse(text), include_attributes=False)


def cmake_tokens(text):
    from cmakelang import lex

    ignored = {"WHITESPACE", "NEWLINE", "COMMENT", "BRACKET_COMMENT"}
    return [
        (token.type.name, token.spelling)
        for token in lex.tokenize(text.replace("\r\n", "\n"))
        if token.type.name not in ignored
    ]


def format_python(paths, write):
    originals = {path: path.read_bytes() for path in paths} if write else {}
    command = [sys.executable, "-m", "ruff", "format", "--config", str(ROOT / "ruff.toml")]
    if not write:
        command.append("--check")
    command.extend(path.relative_to(ROOT).as_posix() for path in paths)
    result = subprocess.run(command, cwd=ROOT)
    if write:
        try:
            if result.returncode:
                for path, original in originals.items():
                    path.write_bytes(original)
                return result.returncode
            for path, original in originals.items():
                if python_ast(original.decode("utf-8")) != python_ast(
                    path.read_text(encoding="utf-8")
                ):
                    raise RuntimeError(
                        "Python formatter changed the AST: " + str(path.relative_to(ROOT))
                    )
        except Exception:
            for path, original in originals.items():
                path.write_bytes(original)
            raise
    return result.returncode


def format_cmake(paths, write):
    from cmakelang import configuration
    from cmakelang.format.__main__ import process_file

    config = configuration.Configuration(
        **json.loads((ROOT / ".cmake-format.json").read_text(encoding="utf-8"))
    )
    changes = {}
    for path in paths:
        original = path.read_text(encoding="utf-8")
        formatted, _ = process_file(config, original)
        if cmake_tokens(original) != cmake_tokens(formatted):
            raise RuntimeError(
                "CMake formatter changed command/argument tokens: " + str(path.relative_to(ROOT))
            )
        repeated, _ = process_file(config, formatted)
        if repeated != formatted:
            raise RuntimeError("CMake formatting is not idempotent: " + str(path.relative_to(ROOT)))
        if original != formatted:
            changes[path] = formatted
    if write:
        for path, formatted in changes.items():
            path.write_text(formatted, encoding="utf-8", newline="\n")
    elif changes:
        print("CMake formatting required:", file=sys.stderr)
        for path in changes:
            print(path.relative_to(ROOT).as_posix(), file=sys.stderr)
    print("CMake format:", len(paths), "files;", len(changes), "changed")
    return int(bool(changes) and not write)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--write", action="store_true")
    parser.add_argument("--language", choices=("python", "cmake"), required=True)
    args = parser.parse_args()
    package = "ruff" if args.language == "python" else "cmakelang"
    if version(package) != VERSIONS[package]:
        parser.error("Install " + package + "==" + VERSIONS[package])
    paths = files(args.language)
    if not paths:
        parser.error("No " + args.language + " sources found")
    if args.language == "python":
        return format_python(paths, args.write)
    return format_cmake(paths, args.write)


if __name__ == "__main__":
    sys.exit(main())
