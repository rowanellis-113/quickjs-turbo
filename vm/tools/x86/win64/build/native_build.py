"""Build-local tool discovery and hashes of actual frame source inputs.

This module performs no compilation, mutation or global environment changes.
Generated receipts must describe the current checkout, not a stale source
manifest copied from a previous experiment.
"""

# Shared source/tool/artifact addressing for the x86 backend package.
import sys as _frame_sys
from pathlib import Path as _FramePath

_frame_tools_root = str(_FramePath(__file__).resolve().parents[3])
if _frame_tools_root not in _frame_sys.path:
    _frame_sys.path.insert(0, _frame_tools_root)
from x86.common.paths_x86 import (
    activate_tools as _frame_activate_tools,
    tool_path as _frame_tool_path,
    source_file as _frame_source_file,
    source_text as _frame_source_text,
    generated_file as _frame_generated_file,
    project_root as _frame_project_root,
    build_file as _frame_build_file,
    upstream_root as _frame_upstream_root,
)

_frame_activate_tools()
import hashlib
import json
import os
from pathlib import Path
import shutil


def source_inputs(source):
    """Select owned native inputs without absorbing upstream tests/bench data.

    The inventory preserves the pre-flattening dependency scope. Paths, not
    basenames, identify each input; adding a native fixture updates the list.
    Minimal temporary source trees used by build-policy tests have no inventory.
    """
    source = Path(source).resolve()
    up = _frame_upstream_root(source)
    paths = []
    for path in source.iterdir():
        if path.is_file() and (
            path.suffix.lower() in {".c", ".h", ".s", ".asm"} or path.name == "CMakeLists.txt"
        ):
            paths.append(path)
    if up != source:
        for path in up.iterdir():
            if path.is_file() and path.suffix.lower() in {".c", ".h", ".s", ".asm"}:
                paths.append(path)
    inventory = Path(__file__).with_name("native-inputs.json")
    relative_inventory = inventory.relative_to(_frame_project_root())
    inventory = source / relative_inventory
    if not inventory.exists():
        return sorted(paths)
    data = json.loads(inventory.read_text(encoding="utf-8"))
    if data.get("schema") != 1:
        raise RuntimeError("Unknown native input inventory")
    paths.append(inventory)
    for directory in data["directories"]:
        root = _frame_source_file(source, directory)
        if root.exists():
            paths.extend(
                p
                for p in root.rglob("*")
                if p.is_file()
                and p.suffix
                in {
                    ".py",
                    ".ps1",
                    ".cmake",
                    ".ld",
                    ".c",
                    ".h",
                    ".inc",
                    ".js",
                    ".S",
                    ".asm",
                    ".json",
                }
                and "__pycache__" not in p.parts
            )
    for relative in data["files"]:
        path = _frame_source_file(source, relative)
        if not path.is_file():
            raise RuntimeError("Missing native input: " + relative)
        paths.append(path)
    return sorted(set(paths))


def source_digest(source):
    source = Path(source).resolve()
    up = _frame_upstream_root(source)
    paths = source_inputs(source)
    records = {
        (
            p.relative_to(source).as_posix()
            if p.is_relative_to(source)
            else "../" + p.relative_to(up).as_posix()
        ): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(paths)
    }
    canonical = json.dumps(records, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(canonical).hexdigest()


def find_objdump(build=None):
    configured = os.environ.get("QJS_FRAME_OBJDUMP")
    if build is not None and not configured:
        directory = Path(build).resolve()
        for parent in (directory, *directory.parents):
            binding = parent / "quickjs-interpreter-tools.json"
            if binding.is_file():
                configured = json.loads(binding.read_text(encoding="utf-8"))["objdump"]
                break
    if configured:
        result = Path(configured)
        if not result.is_file():
            raise RuntimeError(f"Configured frame objdump does not exist: {result}")
        return result
    found = shutil.which("x86_64-w64-mingw32-objdump") or shutil.which("objdump")
    if not found:
        raise RuntimeError(
            "GNU objdump is required by native adapters; configure "
            "QJS_FRAME_OBJDUMP or add its directory to PATH"
        )
    return Path(found)
