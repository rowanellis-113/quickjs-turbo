"""Pure-C prepared callback loop extractor."""

import hashlib
import importlib.util
from pathlib import Path
import re
import sys as _frame_sys
from pathlib import Path as _FramePath

_frame_tools_root = str(_FramePath(__file__).resolve().parents[2])
if _frame_tools_root not in _frame_sys.path:
    _frame_sys.path.insert(0, _frame_tools_root)
from common.paths import (
    activate_tools as _frame_activate_tools,
    tool_path as _frame_tool_path,
    source_file as _frame_source_file,
    source_text as _frame_source_text,
    generated_file as _frame_generated_file,
    project_root as _frame_project_root,
    build_file as _frame_build_file,
)


def module(name, file):
    sp = importlib.util.spec_from_file_location(name, _frame_tool_path(file))
    m = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()


def prepare_source(source):
    """Extract complete array loops before any platform object routing."""
    M = module("callback_adapter", "object-adapter-c")
    source_text = _frame_source_file(source, "quickjs.c").read_text(encoding="utf-8")
    functions = {m[2]: m for m in M.FUNCTION.finditer(source_text)}
    virtual = source_text
    loop_proofs = []
    loops = [
        ("js_array_every", "frame_callback_array_every"),
        ("js_array_reduce", "frame_callback_array_reduce"),
    ]
    loops += [
        ("js_array_every", "frame_callback_write_array_every"),
        ("js_array_reduce", "frame_callback_write_array_reduce"),
    ]
    for original, local in loops:
        body = functions[original][0]
        assert len(re.findall(r"\bJS_Call\s*\(", body)) == 1, original
        prepared = re.sub(
            r"\b(" + original + r"|JS_Call)\b",
            lambda m: local if m[0] == original else "frame_callback_prepared_call",
            body,
        )
        signature = next(m for m in M.FUNCTION.finditer(prepared) if m[2] == local)
        prepared = prepared[: signature.end(3)] + ",void *scope" + prepared[signature.end(3) :]
        if "_write_" in local:
            prepared = prepared.replace(
                "frame_callback_prepared_call", "frame_callback_write_prepared_call"
            )
        call_name = (
            "frame_callback_write_prepared_call"
            if "_write_" in local
            else "frame_callback_prepared_call"
        )
        prepared, count = re.subn(
            r"\b" + call_name + r"\s*\(([^;]*?)\)",
            lambda m: call_name + "(" + m[1] + ",scope)",
            prepared,
        )
        assert count == 1, original
        virtual += "\n" + prepared + "\n"
        loop_proofs.append(
            dict(
                original=original,
                prepared=local,
                original_body_sha256=hashlib.sha256(body.encode()).hexdigest(),
                prepared_body_sha256=hashlib.sha256(prepared.encode()).hexdigest(),
                policy="Exact parser-extracted body, function/private scope parameter and one JS_Call target/scope argument substituted; no maintained source fork.",
            )
        )
    return virtual, loop_proofs
