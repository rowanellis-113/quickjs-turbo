"""Complete owned spread/apply builders and intrinsic apply logical forwarding.

Keep the accepted source algorithms, normal frame ownership and original
miss/exception paths. Linux supplies actual core types, typed C scopes and
the measured private-GPR/SysV bridge; no COFF/clone rewriting is used.
"""

import sys as _x86_sys
from pathlib import Path as _X86Path

if str(_X86Path(__file__).resolve().parents[2]) not in _x86_sys.path:
    _x86_sys.path.insert(0, str(_X86Path(__file__).resolve().parents[2]))
from x86.common.paths_x86 import source_file
import hashlib
import json
import re
from c_workers import module, replace_one

OWNERS = (
    "tools/x86/common/codegen/varargs.py",
    "tools/x86/common/codegen/call-forward.py",
    "src/x86/win64/mingw64/mingw-apply-forward.c",
    "src/x86/win64/mingw64/mingw-arguments.c",
)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def contract(source):
    data = json.loads((source / "src/x86/linux/abi/varargs.json").read_text())
    for name, digest in data["owners"].items():
        if sha(source_file(source, name)) != digest:
            raise ValueError("Review accepted varargs/apply owner: " + name)
    return data


def append(source, output, stream, handlers, layout):
    contract(source)
    from x86.common.abi.native_abi import source_abi

    @source_abi
    def shared(root, layout_override=None):
        return module(root, "call-forward").asm_blocks(None, False, False)

    selected = [
        (name, rows)
        for name, rows in shared(source, layout_override=layout)
        if name in ("JS_FrameApplyForwardGuard", "JS_FrameApplyForwardEnter")
    ]
    if len(selected) != 2:
        raise ValueError("Review complete intrinsic apply guard/entry factories")
    # The existing Linux .call guard has already checked object/C-function
    # identity and has not advanced PC/pending/owners. Its exact pointer miss
    # is the original GNU apply entry edge. All .call paths stay intact.
    fields = layout["offsets"]
    code = stream["code"]
    old = (
        "lea r10, [rip+qjs_linux_core_js_function_call]\n"
        f"cmp QWORD PTR [rax+{fields['JSObject.u.cfunc.c_function']}], r10\n"
        "jne linux_forward_original_host"
    )
    new = old.rsplit("\n", 1)[0] + "\n"
    new += (
        "je linux_varargs_original_call\nmov rdx, rax\n"
        "jmp JS_FrameApplyForwardGuard\nlinux_varargs_original_call:"
    )
    code[:] = replace_one(
        "\n".join(code), old, new, "actual intrinsic apply pointer miss"
    ).splitlines()
    selected = [
        (
            name,
            [
                r.replace(
                    "qjs_frame_core_js_function_apply", "qjs_linux_core_js_function_apply"
                ).replace("JS_FrameCallForwardOldCGuard", "linux_forward_original_host")
                for r in rows
            ],
        )
        for name, rows in selected
    ]
    if handlers.get("array_from", "interp_slow") != "interp_slow":
        raise ValueError("Review array_from dispatch before the source-owned fusion hook")
    record = dict(
        status="generated-not-qualified",
        owners={n: sha(source_file(source, n)) for n in OWNERS},
        functions=[n for n, _ in selected],
        c_helper="JS_FrameApplyForwardCall",
        prefix_bytes=16,
        logical_frame_bytes=80,
        frame_growth=0,
        state_growth=0,
        scope="Complete intrinsic apply guard/owned snapshot/logical root2;spread direct/fusion use the existing complete C step",
    )
    (output / "VARARGS-VM.json").write_text(json.dumps(record, indent=2) + "\n")
    return selected, record


def generate(source, output, core, layout):
    contract(source)
    raw = (source / OWNERS[2]).read_text()
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
    from iterators import scoped

    text += "\n" + scoped(source, "js_linux_apply_forward_body", "JS_FrameApplyForwardCall")
    text = '#include "src/common/linux/interpreter-varargs.inc"\n' + text
    text += "\n#undef FRAME_CODE\n#undef FRAME_INLINE\n"
    target = output / "quickjs-linux-varargs.h"
    target.write_text(text)
    core += '\n#include "quickjs-linux-varargs.h"\n'
    record = dict(
        status="generated-not-qualified",
        owners={n: sha(source_file(source, n)) for n in OWNERS},
        source_files={
            n: sha(source_file(source, n))
            for n in (
                "tools/x86/linux/varargs_native.py",
                "src/common/linux/interpreter-varargs.inc",
                "src/common/call/interpreter-slow-host.inc",
            )
        },
        generated_sha256=sha(target),
        entries=["JS_FrameApplyForwardCall"],
        frame_growth=0,
        state_growth=0,
        scope="Accepted intrinsic apply algorithm;actual SysV state-only result0/1/2 and complete owned-prefix/root2 return protocol",
    )
    (output / "VARARGS.json").write_text(json.dumps(record, indent=2) + "\n")
    return core


def finish_slow(source, output, layout):
    """Apply the original two builders only to the complete semantic owner."""
    contract(source)
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
    shared = module(source, "varargs")
    adapted = shared.direct_call_text(body + sentinel)
    adapted = shared.fusion_call_text(adapted)
    if not adapted.endswith(sentinel):
        raise ValueError("Review full C owner transformation boundary")
    adapted = adapted[: -len(sentinel)]
    adapted = replace_one(
        adapted,
        "FRAME_CODE int JS_FrameVarargsSlow(JSFrameRegisterState *state)\n{",
        '#include "src/common/kernel/fast-array-from.inc"\n'
        "FRAME_CODE int JS_FrameVarargsSlow(JSFrameRegisterState *state)\n{",
        "fast-array-from helper include",
    )
    adapted = replace_one(
        adapted,
        "    goto execute_opcode;\nenter_frame:",
        "    if (*pc == OP_array_from) {\n"
        "        int fast_arr_err = JS_FastArrayFrom(state);\n"
        "        pc = state->pc;\n"
        "        sp = state->sp;\n"
        "        if (unlikely(fast_arr_err)) {\n"
        "            state->exception_pending = false;\n"
        "            goto exception;\n"
        "        }\n"
        "        goto slow_step_done;\n"
        "    }\n"
        "    goto execute_opcode;\n"
        "enter_frame:",
        "fast OP_array_from hook in JS_FrameVarargsSlow",
    )
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
