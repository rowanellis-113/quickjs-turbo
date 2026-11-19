"""Seal native archive inputs once per coherent source/compiler epoch."""

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
from pathlib import Path
import subprocess

from standard_unwind import inputs


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def finalize(build, archive, cmake, pipeline):
    build, archive, pipeline = build.resolve(), archive.resolve(), pipeline.resolve()
    if pipeline != _frame_generated_file(build, "quickjs-interpreter-stage.cmake").resolve():
        raise RuntimeError("Native pipeline must belong to its build directory")
    paths = inputs(build, archive)
    epoch = json.loads(
        (_frame_build_file(build, "interpreter-native-epoch.json")).read_text(encoding="utf-8")
    )["fingerprint"]
    identity = dict(
        epoch=epoch,
        pipeline_sha256=sha(pipeline),
        paths=[path.relative_to(build).as_posix() for path in paths],
    )
    current = {path.relative_to(build).as_posix(): sha(path) for path in paths}
    record = _frame_generated_file(build, "quickjs-interpreter-archive-stage.json")
    if record.exists():
        previous = json.loads(record.read_text(encoding="utf-8"))
        if (
            previous.get("status") == "passed"
            and previous.get("identity") == identity
            and previous.get("outputs") == current
        ):
            print("FRAME_ARCHIVE_STAGE_REUSED", len(paths), "verified objects", flush=True)
            return
        raise RuntimeError(
            "Native objects do not match a completed source epoch; rebuild with --clean-first"
        )
    state = dict(schema=1, status="preparing", identity=identity, inputs=current)

    def save():
        temporary = record.with_suffix(".next")
        temporary.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
        temporary.replace(record)

    save()
    try:
        subprocess.run([str(cmake), "-P", str(pipeline)], cwd=build, check=True)
        state.update(
            status="passed",
            outputs={path.relative_to(build).as_posix(): sha(path) for path in paths},
        )
        print("FRAME_ARCHIVE_STAGE_SEALED", len(paths), "objects", flush=True)
    except BaseException as error:
        state.update(status="failed", error=repr(error))
        raise
    finally:
        save()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("build", "archive", "cmake", "pipeline"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    finalize(args.build, args.archive, args.cmake, args.pipeline)
