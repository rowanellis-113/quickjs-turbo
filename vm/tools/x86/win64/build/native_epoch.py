"""Invalidate only owned native build products before Ninja computes its DAG.

The research adapters mutate their inputs. A source/configuration change must
therefore start all adapters from compiler bytes. No timestamp restoration or
previous experiment objects are needed to decide which source epoch is valid.
Portable objects and unrelated user files are never selected for removal.
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
)

_frame_activate_tools()
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil

from native_build import source_digest

NATIVE_DIRECTORIES = {
    "call-forward-link",
    "call-metadata-link",
    "forward-native-control",
    "generated-adapter-history",
    "core-adapter-history",
    "js-captured-link",
    "length-link",
    "native-c-scope",
    "native-scope-entry",
    "native-scope-link",
    "own-bytecode-link",
    "proto-direct-link",
    "varargs-generation",
    "varargs-link",
    "quickjs-retained-pristine",
}


def checked_targets(source, build):
    source, build = source.resolve(), build.resolve()
    if build.parent == build or source == build or source.is_relative_to(build):
        raise RuntimeError("Native build directory cannot contain the source checkout")
    cache = _frame_build_file(build, "CMakeCache.txt")
    if cache.exists():
        home = next(
            (
                s.split("=", 1)[1]
                for s in cache.read_text(encoding="utf-8").splitlines()
                if s.startswith("CMAKE_HOME_DIRECTORY:INTERNAL=")
            ),
            None,
        )
        if home is None or Path(home).resolve() != source:
            raise RuntimeError("Refusing to invalidate a build owned by another source tree")
    elif any(p.name.startswith("quickjs-") for p in build.iterdir()):
        raise RuntimeError(
            "Native products without a matching CMake cache require a fresh build directory"
        )
    targets = [
        p
        for p in build.iterdir()
        if (p.is_file() and p.name.startswith("quickjs-"))
        or (p.is_dir() and p.name in NATIVE_DIRECTORIES)
    ]
    publication = _frame_build_file(build, "interpreter-standard-unwind.json")
    if publication.exists():
        targets.append(publication)
    # Retire known pre-migration objects as well when an existing build is reused.
    for relative, prefix in (
        ("CMakeFiles/qjs-core.dir", "quickjs.c.obj"),
        ("CMakeFiles/qjs.dir", "quickjs-interpreter.c.obj"),
        ("CMakeFiles/qjs.dir", "quickjs-interpreter-call-env.c.obj"),
    ):
        # Include the exact object's adapter sidecars and old replay history;
        # leaving those beside a freshly compiled object mixes two epochs.
        folder = _frame_build_file(build, relative)
        if folder.exists():
            targets.extend(folder.glob(prefix + "*"))
    for relative in ("generated", "CMakeFiles/qjs.dir/src", "CMakeFiles/qjs.dir/generated"):
        owned = _frame_build_file(build, relative)
        if owned.exists():
            targets.append(owned)
    # Verify every absolute target and descendant before performing any removal.
    for target in targets:
        for candidate in (target, *target.rglob("*")) if target.is_dir() else (target,):
            if (
                candidate.is_symlink()
                or getattr(candidate, "is_junction", lambda: False)()
                or not candidate.resolve().is_relative_to(build)
                or candidate.resolve() == build
            ):
                raise RuntimeError(f"Refusing unsafe native build target: {candidate}")
    return targets


def prepare(source, build, configuration):
    source, build = source.resolve(), build.resolve()
    digest = source_digest(source)
    fingerprint = hashlib.sha256((digest + "\n" + configuration).encode("utf-8")).hexdigest()
    record = _frame_build_file(build, "interpreter-native-epoch.json")
    previous = json.loads(record.read_text(encoding="utf-8")) if record.exists() else None
    if previous and previous["fingerprint"] == fingerprint:
        print("FRAME_NATIVE_EPOCH_UNCHANGED", fingerprint)
        return
    targets = checked_targets(source, build)
    removed = [p.relative_to(build).as_posix() for p in targets]
    for path in targets:
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
    result = dict(
        schema=1,
        source=str(source),
        build=str(build),
        source_tree_sha256=digest,
        fingerprint=fingerprint,
        configuration=configuration,
        removed=removed,
        previous_fingerprint=previous["fingerprint"] if previous else None,
    )
    temporary = record.with_suffix(".tmp")
    temporary.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, record)
    print("FRAME_NATIVE_EPOCH_STARTED", fingerprint, "invalidated", len(targets), "owned products")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--build", type=Path, required=True)
    parser.add_argument("--configuration", required=True)
    args = parser.parse_args()
    prepare(args.source, args.build, args.configuration)
