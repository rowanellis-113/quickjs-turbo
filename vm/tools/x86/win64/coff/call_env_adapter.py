"""Source-derived VM refill helpers (accepted call-environment r6422).

The explicit Prepare API keeps its live environment check. Only VM miss call
relocations use the clone, after the existing cached startup-mode admission.
Compiler code and ordinary .pdata remain intact; no PE finalizer is required.
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
import importlib.util
import json
import os
from pathlib import Path
import re
import struct

import standard_unwind as U
from c_source_match import replace_one

HERE = Path(__file__).resolve().parent
RENAMES = {
    "JS_FrameCallMetaMiss": "JS_FrameCallEnvMetaMiss",
    "JS_FrameCallLinkMiss": "JS_FrameCallEnvLinkMiss",
    "JS_FrameCallMetaState": "JS_FrameCallEnvMetaState",
    "JS_FrameCallMetaExtraBytes": "JS_FrameCallEnvMetaExtraBytes",
}
MISS_NAMES = {"JS_FrameCallMetaMiss", "JS_FrameCallLinkMiss"}
sha = lambda data: hashlib.sha256(data).hexdigest()


def module(name):
    spec = importlib.util.spec_from_file_location(
        "call_env_" + name.replace("-", "_"), _frame_tool_path(name + ".py")
    )
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def generate(source, output):
    source, output = source.resolve(), output.resolve()
    parent = output.with_name("quickjs-interpreter-call-env-parent.c")
    module("call-metadata").generate_c(source, parent)
    text = parent.read_text(encoding="utf-8")
    before = 'if(getenv("QJS_DISABLE_CALL_LINK") || rt->gc_phase!=JS_GC_PHASE_NONE ||'
    after = 'if((budget==0 && getenv("QJS_DISABLE_CALL_LINK")) || rt->gc_phase!=JS_GC_PHASE_NONE ||'
    text = replace_one(text, before, after)
    link = module("call-link")
    legacy = link._function(
        _frame_source_text(source, "quickjs-interpreter-call-link.h"),
        "CALL_LINK_CODE void JS_FrameCallLinkMiss(",
    )
    for body in (legacy, link._function(text, "CALL_LINK_CODE void JS_FrameCallMetaMiss(")):
        for token in (
            "if(call_link_vm_mode()==1 && JS_VALUE_GET_TAG(target)==JS_TAG_OBJECT)",
            "CALL_LINK_VM_BUDGET",
            "js_frame_begin_c(state);",
            "js_frame_finish_c(state);",
        ):
            if token not in body:
                replace_one(body, token, token)
    # The parent generator ends by undefining CALL_LINK_CODE. Reintroduce it
    # for the copied legacy VM miss entry, using the same compiler selection.
    text += (
        """
#ifdef _MSC_VER
#define CALL_LINK_CODE __declspec(code_seg(".qjzzec")) __declspec(noinline)
#else
#define CALL_LINK_CODE __attribute__((section(".qjzzec"),noipa))
#endif
"""
        + legacy
        + "\n#undef CALL_LINK_CODE\n"
    )
    for old, new in RENAMES.items():
        text = re.sub(r"\b" + old + r"\b", new, text)
    text = text.replace(".qjssrc$C", ".qjzzec")
    output.write_text(text, encoding="utf-8", newline="\n")
    output.with_suffix(".contract.json").write_text(
        json.dumps(
            dict(
                schema=1,
                status="passed",
                retained_source_layer="r6422",
                parent_generated_sha256=sha(parent.read_bytes()),
                generated_sha256=sha(output.read_bytes()),
                renames=RENAMES,
                frame_growth=0,
                explicit_prepare_unchanged=True,
                vm_control="Existing first-use cached CALL_LINK/CALL_LINK_VM admission; budget>0 skips a repeated getenv.",
                dynamic_control="Mid-process debug-flag changes do not suppress admitted VM refills; explicit Prepare remains live.",
                native_unwind="Compiler .pdata; no custom footer or PE mutation.",
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def sidecars(path):
    return (
        path.with_name(path.name + ".call-env.json"),
        path.with_name(path.name + ".before-call-env"),
    )


def restore(paths):
    for path in paths:
        record, backup = sidecars(path)
        if not record.exists():
            if backup.exists():
                raise RuntimeError("Call-environment backup without provenance: " + str(path))
            continue
        receipt = json.loads(record.read_text(encoding="utf-8"))
        if (
            sha(path.read_bytes()) != receipt["after_sha256"]
            or sha(backup.read_bytes()) != receipt["before_sha256"]
        ):
            raise RuntimeError("Unknown call-environment endpoint: " + str(path))
        stamp = path.stat()
        path.write_bytes(backup.read_bytes())
        os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
        backup.unlink()
        record.unlink()


def rewrite(raw, own, providers):
    C = U.C
    packed, packing = module("call-metadata").packed(raw, C)
    co, old = C.Coff(packed), C.Coff(packed)
    changes = []
    if own:
        # The extracted private engine header may emit external inline COMDATs
        # or tentative constants. Give only this TU's definitions private names;
        # bind tentative constants to actual definitions in this same archive.
        for index, symbol in co.all_symbols.items():
            if symbol["storage"] != 2:
                continue
            if symbol["section"] > 0 and not symbol["name"].startswith("JS_FrameCallEnv"):
                name = "call_env_emitted_" + sha(symbol["name"].encode())[:32]
                offset = len(co.strings)
                co.strings += name.encode() + b"\0"
                struct.pack_into("<II", co.data, co.table + index * co.stride, 0, offset)
                changes.append(dict(kind="private_definition", old=symbol["name"], new=name))
            elif symbol["section"] == 0 and symbol["value"]:
                matches = providers.get(symbol["name"], [])
                if not any(size >= symbol["value"] for size in matches):
                    raise RuntimeError(
                        "Unbound call-environment tentative constant: " + symbol["name"]
                    )
                struct.pack_into("<I", co.data, co.table + index * co.stride + 8, 0)
                changes.append(
                    dict(kind="common_to_external", name=symbol["name"], size=symbol["value"])
                )
    else:
        for number, section in enumerate(co.section_records, 1):
            if not section["flags"] & 0x20000000:
                continue
            for i in range(section["count"]):
                at = section["reloc"] + 10 * i
                offset, index, kind = struct.unpack_from("<IIH", co.data, at)
                name = co.all_symbols[index]["name"]
                if name not in MISS_NAMES:
                    continue
                if (
                    kind != 4
                    or not 0 < offset <= section["size"] - 4
                    or co.data[section["raw"] + offset - 1] not in (0xE8, 0xE9)
                ):
                    raise RuntimeError("Expected a typed direct VM miss CALL/JMP: " + name)
                target = co.external(RENAMES[name])
                struct.pack_into("<I", co.data, at + 4, target)
                changes.append(
                    dict(
                        kind="vm_miss_edge",
                        section=number,
                        offset=offset,
                        old=name,
                        new=RENAMES[name],
                    )
                )
    if not changes:
        return raw, []
    result = co.finish()
    final = C.Coff(result)
    keys = ("name", "size", "flags", "sha256", "lines_sha256")
    if len(final.sections) != len(old.sections) or any(
        any(a[key] != b[key] for key in keys) for a, b in zip(old.sections, final.sections)
    ):
        raise RuntimeError("Call-environment adapter changed section identity")
    if not own and any(
        final.all_symbols[index] != symbol for index, symbol in old.all_symbols.items()
    ):
        raise RuntimeError("Call-environment routing changed an existing symbol")
    return result, dict(changes=changes, packing=packing, section_payloads_held=True)


def route(build, archive):
    paths = U.inputs(build, archive)
    own = [p for p in paths if p.name == "quickjs-interpreter-call-env.c.obj"]
    if len(own) != 1:
        raise RuntimeError("Expected one compiler-built call-environment archive member")
    providers = {}
    for path in paths:
        if path == own[0]:
            continue
        for symbol in U.C.Coff(path.read_bytes()).all_symbols.values():
            if symbol["storage"] == 2 and symbol["section"] >= 0:
                size = symbol["value"] if symbol["section"] == 0 else float("inf")
                providers.setdefault(symbol["name"], []).append(size)
    rows = []
    # Validate every input before publishing any result.
    pending = []
    for path in paths:
        record, backup = sidecars(path)
        if record.exists() or backup.exists():
            raise RuntimeError("Restore the previous call-environment adaptation before replay")
        raw = path.read_bytes()
        result, proof = rewrite(raw, path == own[0], providers)
        if proof:
            row = dict(path=str(path), before_sha256=sha(raw), after_sha256=sha(result), **proof)
            pending.append((path, raw, result, row))
            rows.append(row)
    edges = sum(change["kind"] == "vm_miss_edge" for row in rows for change in row["changes"])
    if not edges:
        raise RuntimeError("No VM miss edges found in the native archive")
    for path, raw, result, row in pending:
        record, backup = sidecars(path)
        stamp = path.stat()
        backup.write_bytes(raw)
        path.write_bytes(result)
        os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
        record.write_text(json.dumps(row, indent=2) + "\n", encoding="utf-8")
    (_frame_generated_file(build, "quickjs-interpreter-call-env-routes.json")).write_text(
        json.dumps(
            dict(
                schema=1,
                status="passed",
                vm_miss_edges=edges,
                objects=rows,
                explicit_prepare_routed=False,
                native_unwind="ordinary compiler .pdata",
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print("CALL_ENV_ROUTED", edges, "VM miss edges;", len(rows), "objects")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--build", type=Path)
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--restore", action="store_true")
    args = parser.parse_args()
    if args.output:
        if not args.source or args.build or args.archive or args.restore:
            parser.error(
                "--output requires --source and cannot be combined with archive operations"
            )
        generate(args.source, args.output)
    elif args.build and args.archive:
        if args.restore:
            restore(U.inputs(args.build, args.archive))
        else:
            route(args.build, args.archive)
    else:
        parser.error("Supply --source/--output or --build/--archive [--restore]")
