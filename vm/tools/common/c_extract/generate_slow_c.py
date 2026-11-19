"""Generate the one-step C boundary from the experimental frame executor.

There is a single source for ownership, validation, arity growth, unwind and
all C opcode semantics. The native VM calls this step directly and keeps its
own nonvolatile register activation alive across the slow call.
"""

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

_frame_activate_tools()
import argparse
import re
from pathlib import Path

COUNTERS = """pushes arities cache_hits cache_misses bridges borrowed_values
copied_values windows window_fallbacks window_bytes shallow_values cross_windows
window_helpers peak_bytes depth max_depth""".split()

NUMERIC_OPS = (
    "add",
    "sub",
    "mul",
    "div",
    "mod",
    "lt",
    "lte",
    "gt",
    "gte",
    "eq",
    "neq",
    "strict_eq",
    "strict_neq",
)


def numeric_bodies(source):
    """Isolate the existing opcode text; do not reimplement its coercion rules."""
    text = _frame_source_text(source, "quickjs-interpreter-ops.h")
    matches = list(re.finditer(r"^        CASE\(OP_(\w+)\):\n", text, re.M))
    blocks = {
        m[1]: text[m.end() : matches[i + 1].start() if i + 1 < len(matches) else len(text)]
        for i, m in enumerate(matches)
    }
    shared = blocks["pow"]
    assert shared.lstrip().startswith("binary_arith_slow:")
    bodies = {
        name: blocks[name] + (shared if name != "add" else "")
        for name in ("add", "sub", "mul", "div", "mod")
    }
    start = text.index("#define OP_CMP(")
    end = text.index("\n\n", start)
    macro = text[start:end].splitlines()
    assert "CASE(opcode)" in macro[1] and "BREAK" in macro[-1]
    comparison = "\n".join(line.rstrip().removesuffix("\\").rstrip() for line in macro[2:]) + ";\n"
    for name in NUMERIC_OPS[5:]:
        call = re.search(r"OP_CMP\(OP_" + name + r",\s*([^,]+),\s*(.*?)\);", text)
        assert call, name
        bodies[name] = comparison.replace("binary_op", call[1]).replace("slow_call", call[2])
    assert set(bodies) == set(NUMERIC_OPS)
    return bodies


def numeric_boundaries(source):
    output = []
    for name, body in numeric_bodies(source).items():
        output.append(
            """
/* One opcode, original ownership/coercion body, no interpreter-allocation switch. */
FRAME_OPCODE_CODE int JS_FrameInterpOp_"""
            + name
            + """(JSFrameRegisterState *state)
{
    JSFrame *frame = state->frame;
    JSStackFrame *sf = &frame->sf;
    JSContext *ctx = frame->bytecode->realm;
    JSValue *sp = state->sp;
    uint8_t *pc = state->pc + 1;
"""
        )
        if name not in ("add", "eq", "neq", "strict_eq", "strict_neq"):
            output.append("    const int opcode = OP_" + name + ";\n")
        output.append("""#ifdef QJS_INTERP_FRAME_INTERNAL_ENTRY
    js_frame_begin_c(state);
#endif
    sf->cur_pc = pc;
    /* Ordinary frame values are owned references, as in the original VM.
     * Publish SP in state; cur_sp remains the suspended-frame cursor. */
""")
        output.append(body.replace("BREAK", "goto numeric_done"))
        output.append("""numeric_done:
    state->pc = pc;
    state->sp = sp;
#ifdef QJS_INTERP_FRAME_INTERNAL_ENTRY
    js_frame_finish_c(state);
#endif
    return 0;
exception:
    state->pc = pc;
    state->sp = sp;
    state->exception_pending = true;
#ifdef QJS_INTERP_FRAME_INTERNAL_ENTRY
    /* Commit before the generic unwind begins another C boundary. */
    js_frame_finish_c(state);
#endif
    return JS_FrameInterpSlow(state);
}
""")
    return "".join(output)


PROPERTY_OPS = ("get_field", "get_field2", "put_field", "drop", "call_constructor")


def property_bodies(source):
    text = _frame_source_text(source, "quickjs-interpreter-ops.h")
    matches = list(re.finditer(r"^        CASE\(OP_(\w+)\):\n", text, re.M))
    blocks = {
        m[1]: text[m.end() : matches[i + 1].start() if i + 1 < len(matches) else len(text)]
        for i, m in enumerate(matches)
    }
    return {name: blocks[name] for name in PROPERTY_OPS}


def property_boundaries(
    source,
    *,
    arg_construct_condition="#if defined(QJS_FRAME_ARGUMENTS_CONSTRUCT_GUARD)",
):
    output = []
    for name, body in property_bodies(source).items():
        output.append(
            "\n/* Original opcode body; no allocation/call switch on success. */\n"
            "FRAME_PROPERTY_CODE int JS_FrameInterpProperty_"
            + name
            + "(JSFrameRegisterState *state)\n{\n"
            "    JSFrame *frame = state->frame;\n"
            "    JSContext *ctx = frame->bytecode->realm;\n"
            "    JSValue *sp = state->sp;\n"
            "    uint8_t *pc = state->pc + 1;\n"
        )
        if name != "drop":
            output.append("    JSStackFrame *sf = &frame->sf;\n")
        if name in ("get_field", "get_field2", "put_field"):
            output.append(
                "#ifdef QJS_PROPERTY_IC\n    JSFunctionBytecode *b = frame->bytecode;\n#endif\n"
            )
        if name == "call_constructor":
            output.append(
                "    int call_argc, i;\n    JSValue *call_argv;\n"
                "    JSValue ret_val = JS_UNDEFINED;\n"
            )
        if name == "call_constructor":
            output.append(
                "#ifndef QJS_LINUX_REGISTER_FOUNDATION\n"
                "    extern int JS_FrameVarargsConstructCall(JSFrameRegisterState *);\n"
                "    int construct_event=JS_FrameVarargsConstructCall(state);\n"
                "    if (construct_event>=0)return construct_event;\n"
            )
            output.append(
                arg_construct_condition + "\n"
                "    extern int JS_FrameArgumentsConstructCall(JSFrameRegisterState *);\n"
                "    construct_event=JS_FrameArgumentsConstructCall(state);\n"
                "    if (construct_event>=0)return construct_event;\n#endif\n#endif\n"
            )
        output.append(
            "#ifdef QJS_INTERP_FRAME_INTERNAL_ENTRY\n    js_frame_begin_c(state);\n#endif\n"
        )
        output.append(body.replace("BREAK", "goto opcode_done"))
        output.append(
            "opcode_done:\n    state->pc = pc;\n    state->sp = sp;\n"
            "#ifdef QJS_INTERP_FRAME_INTERNAL_ENTRY\n    js_frame_finish_c(state);\n#endif\n    return 0;\n"
        )
        if name != "drop":
            output.append(
                "exception:\n    state->pc = pc;\n    state->sp = sp;\n"
                "    state->exception_pending = true;\n"
                "#ifdef QJS_INTERP_FRAME_INTERNAL_ENTRY\n    js_frame_finish_c(state);\n#endif\n"
                "    return JS_FrameInterpSlow(state);\n"
            )
        output.append("}\n")
    return "".join(output)


def without_register_blocks(text):
    lines, output, depth, skip = text.splitlines(), [], 0, None
    for line in lines:
        directive = line.strip()
        if directive.startswith("#if"):
            if directive == "#ifdef QJS_INTERP_FRAME_REGISTER_ABI":
                assert skip is None
                skip = depth
            depth += 1
        if skip is None:
            output.append(line)
        if directive.startswith("#endif"):
            depth -= 1
            if skip == depth:
                skip = None
    assert depth == 0 and skip is None
    return "\n".join(output) + "\n"


def generate(
    source,
    output,
    *,
    interpreter_text=None,
    arg_construct_condition="#if defined(QJS_FRAME_ARGUMENTS_CONSTRUCT_GUARD)",
):
    text = (
        _frame_source_text(source, "quickjs-interpreter-loop.h")
        if interpreter_text is None
        else interpreter_text
    )
    start = text.index("enter_frame:\n")
    end = text.index("exit_activation:\n", start)
    body = without_register_blocks(text[start:end])
    assert body.count("dispatch:\n") == 1
    body = body.replace("dispatch:\n", "dispatch:\n    goto slow_step_done;\nexecute_opcode:\n")
    declarations = """/* Generated by tools/generate-slow.py; do not edit. */
FRAME_CODE int JS_FrameInterpSlow(JSFrameRegisterState *state)
{
    JSFrame *frame=state->frame, *parent;
    JSFrameSegment *segment=state->segment;
    JSRuntime *rt=state->rt;
    JSContext *caller_ctx=state->caller_ctx;
    JSStackFrame *sf=&frame->sf;
    JSFunctionBytecode *b=frame->bytecode;
    JSContext *ctx=b->realm;
#if defined(_MSC_VER)
    JSObject *p=JS_VALUE_GET_OBJ(sf->cur_func);
    JSVarRef **var_refs=p->u.func.var_refs;
#endif
    JSValue this_obj=frame->this_value, func_obj=sf->cur_func;
    JSValue *sp=state->sp, *arg_buf=sf->arg_buf, *var_buf=sf->var_buf;
    JSValue *stack_buf=var_buf+b->var_count, *local_buf, *pval, *call_argv;
    JSValue ret_val=JS_UNDEFINED;
    JSValueConst *incoming_argv;
    uint8_t *pc=state->pc;
    int incoming_argc, incoming_copy, opcode, i, call_argc, owned_args;
    int event=0;
    size_t frame_size, used_bytes=state->used_bytes;
    JSFrameCallSite *sites=state->sites;
    uint8_t *cache_next=state->cache_next;
#undef CASE
#undef BREAK
#undef FRAME_NEXT
#if DIRECT_DISPATCH
    __extension__ static const void *const frame_dispatch_table[256] = {
#define FRAME_TARGET(id, label) &&frame_##label,
#include "src/common/call/quickjs-interpreter-dispatch.inc"
#undef FRAME_TARGET
        [OP_COUNT ... 255] = &&frame_invalid
    };
#define FRAME_NEXT() __extension__ ({ goto *frame_dispatch_table[opcode = *pc++]; });
#define CASE(op) frame_##op
#else
#define FRAME_NEXT() switch (opcode = *pc++)
#define CASE(op) case op
#endif
#define BREAK goto dispatch
"""
    declarations += "#ifdef QJS_INTERP_FRAME_DIAGNOSTICS\n"
    for name in COUNTERS:
        ctype = (
            "unsigned"
            if name in ("depth", "max_depth")
            else ("size_t" if name == "peak_bytes" else "uint64_t")
        )
        declarations += f"    {ctype} {name}=state->{name};\n"
    declarations += """#endif
#ifdef QJS_INTERP_FRAME_INTERNAL_ENTRY
    js_frame_begin_c(state);
#endif
    if (state->exception_pending) {
        state->exception_pending=false;
        goto exception;
    }
    goto execute_opcode;
"""
    footer = """exit_activation:
    event=1;
slow_step_done:
    state->frame=frame;
    state->segment=segment;
    state->pc=pc;
    state->sp=sp;
    state->used_bytes=used_bytes;
    if (event) state->result=ret_val;
#ifdef QJS_INTERP_FRAME_DIAGNOSTICS
"""
    footer += "".join(f"    state->{name}={name};\n" for name in COUNTERS)
    footer += """#endif
#ifdef QJS_INTERP_FRAME_INTERNAL_ENTRY
    /* C kept the full quota exact, even when it pushed/unwound frames. Keep
     * that updated snapshot until native execution next crosses into C. */
    js_frame_finish_c(state);
#endif
    return event;
}
#undef CASE
#undef BREAK
#undef FRAME_NEXT
"""
    output.write_text(
        declarations
        + body
        + footer
        + numeric_boundaries(source)
        + property_boundaries(source, arg_construct_condition=arg_construct_condition)
    )
    print("Register Interp: generated C slow step from the single frame/semantic source")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    generate(args.source, args.output)
