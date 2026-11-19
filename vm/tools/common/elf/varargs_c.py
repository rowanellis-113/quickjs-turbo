"""Source-owned C varargs/apply/fusion workers."""

import hashlib
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from common.paths import source_file
from c_workers import module, replace_one


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def contract(source, *, contract_rel=None):
    if contract_rel is None:
        return {"owners": {}}
    data = json.loads((source / contract_rel).read_text())
    owners = data.get("owners") or data.get("source_owners") or {}
    for name, digest in owners.items():
        if sha(source_file(source, name)) != digest:
            raise ValueError("Review accepted varargs/apply owner: " + name)
    return data


def generate(
    source,
    output,
    core,
    layout,
    *,
    contract_rel=None,
    platform_binding="src/common/linux/interpreter-varargs.inc",
):
    contract(source, contract_rel=contract_rel)
    raw = (source / "src/common/kernel/apply-forward.c").read_text()
    text = raw[raw.index("#include <stdatomic.h>") :]
    start = text.index("extern bool JS_FrameArgumentsPushForConstruct(")
    end = text.index("typedef struct {", start)
    text = text[:start] + text[end:]
    text = text.replace("#define JS_CALL_FLAG_COPY_ARGV (1 << 1)\n", "")
    text = text.replace("JS_FrameArgumentsPushForConstruct", "js_frame_arguments_push")
    text = text.replace("JS_FrameSlowDirectSelect", "JS_FrameInterpSlow")
    text = text.replace('".qjzzpm"', '".data.qjs_linux_apply"')
    text = text.replace(
        "static _Atomic(unsigned) apply_control;",
        'static _Atomic(unsigned) apply_control __attribute__((section(".data.qjs_linux_apply")));',
    )
    text = re.sub(r"\bcount\(", "js_linux_apply_count(", text)
    text = replace_one(
        text,
        "FRAME_CODE int JS_FrameApplyForwardCall(JSFrameRegisterState *state)",
        "static FRAME_CODE int js_linux_apply_forward_body(JSFrameRegisterState *state)",
        "typed coherent intrinsic apply body",
    )
    from iterators_c import scoped

    text += "\n" + scoped(source, "js_linux_apply_forward_body", "JS_FrameApplyForwardCall")
    text = '#include "src/common/linux/interpreter-varargs.inc"\n' + text
    text += "\n#undef FRAME_CODE\n#undef FRAME_INLINE\n"
    target = output / "quickjs-linux-varargs.h"
    target.write_text(text)
    core += '\n#include "quickjs-linux-varargs.h"\n'
    record = dict(
        status="generated-not-qualified",
        owners={},
        source_files={
            n: sha(source / n)
            for n in (
                "tools/common/elf/varargs_c.py",
                "src/common/linux/interpreter-varargs.inc",
                "src/common/call/interpreter-slow-host.inc",
            )
        },
        generated_sha256=sha(target),
        entries=["JS_FrameApplyForwardCall"],
        frame_growth=0,
        state_growth=0,
        scope="Accepted intrinsic apply algorithm;actual native state-only result0/1/2 and complete owned-prefix/root2 return protocol",
    )
    (output / "VARARGS.json").write_text(json.dumps(record, indent=2) + "\n")
    return core


def finish_slow(source, output, layout, *, contract_rel=None):
    """Apply the original two builders only to the complete semantic owner."""
    contract(source, contract_rel=contract_rel)
    path = output / "quickjs-linux-construct.h"
    text = path.read_text()
    signature = "FRAME_CODE int JS_FrameVarargsSlow(JSFrameRegisterState *state)\n{"
    if text.count(signature) != 1:
        raise ValueError("Review complete C-step definition before varargs transformation")
    start = text.index(signature)
    # Both compiler branches are present in this unpreprocessed owner; braces
    # cannot be counted across mutually exclusive #if/#else declarations.
    end = text.index("\n}\n#undef CASE", start) + 2
    original = text[start:end]
    # The factory predates the shared formatter. Canonicalize only these two
    # whitespace anchors; the exact accepted transformations still enforce
    # every owner, poll, reload, quota and snapshot operation below.
    body = original.replace("CASE(OP_nop) :", "CASE(OP_nop):")
    old = """    owned_args = (incoming_copy || incoming_argc < b->arg_count || FRAME_CAPTURED_ARGS(b))
                     ? b->arg_count
                     : 0;"""
    canonical = """    owned_args = (incoming_copy || incoming_argc < b->arg_count ||
                  FRAME_CAPTURED_ARGS(b)) ? b->arg_count : 0;"""
    body = replace_one(body, old, canonical, "source factory owned-arity formatting")
    sentinel = "\n#undef CASE\n"
    shared = module(source, "varargs-c")
    adapted = shared.direct_call_text(body + sentinel)
    adapted = shared.fusion_call_text(adapted)
    if not adapted.endswith(sentinel):
        raise ValueError("Review full C owner transformation boundary")
    adapted = adapted[: -len(sentinel)]
    text = replace_one(text, original, adapted, "complete direct/fusion semantic owner")
    path.write_text(text)
    for name in ("CONSTRUCT.json", "ITERATORS.json"):
        p = output / name
        data = json.loads(p.read_text())
        data["before_varargs_sha256"] = data["generated_sha256"]
        data["generated_sha256"] = sha(path)
        data["post_varargs_transform"] = (
            "Accepted owned dense apply and full single-spread fusion factories;paused checkpoints preserved"
        )
        p.write_text(json.dumps(data, indent=2) + "\n")
    p = output / "VARARGS.json"
    data = json.loads(p.read_text())
    data.update(
        slow_sha256=sha(path),
        original_slow_sha256=hashlib.sha256(original.encode()).hexdigest(),
        adapted_slow_sha256=hashlib.sha256(adapted.encode()).hexdigest(),
        direct_control_offset=layout["offsets"]["JSFunctionBytecode.pc2line_len"] + 5,
        fusion_control_offset=layout["offsets"]["JSFunctionBytecode.pc2line_len"] + 6,
        entries=data["entries"] + ["JS_FrameVarargsTryFuse"],
        spread="Owned all-actual copy2 frame;guarded no-allocate single-spread fusion;original protocol on every miss",
    )
    p.write_text(json.dumps(data, indent=2) + "\n")
