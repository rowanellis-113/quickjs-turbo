"""An Interp-style single C operation; retain the old large semantic step exactly."""

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
import hashlib


def replace(text, old, new):
    assert text.count(old) == 1, (old, text.count(old))
    return text.replace(old, new)


def span(text, signature):
    lo = text.index(signature)
    at = text.index("{", lo) + 1
    depth = 1
    while depth:
        depth += (text[at] == "{") - (text[at] == "}")
        at += 1
    return lo, at


def slow_body(text):
    lo = text.index("FRAME_CODE int JS_FrameVarargsSlow(")
    return text[lo : text.index("\n}\n#undef CASE", lo) + 2]


def helpers(source):
    core = _frame_source_file(source, "quickjs.c").read_text(encoding="utf-8")
    lo, hi = span(core, "static bool js_object_has_name(")
    has = core[lo:hi]
    lo, hi = span(core, "static int JS_DefineObjectName(")
    define = core[lo:hi]
    has = replace(
        has,
        "static bool js_object_has_name(",
        "static FRAME_CODE bool JS_FrameVarargsHasFunctionName(",
    )
    define = replace(
        define,
        "static int JS_DefineObjectName(",
        "static FRAME_CODE int JS_FrameVarargsDefineObjectName(",
    )
    define = replace(define, "js_object_has_name(", "JS_FrameVarargsHasFunctionName(")
    return has + "\n" + define + "\n"


STEP = r"""
/* Original opcode semantics, original name/descriptor/error helpers.
 * The generic native slow entry has already published its register state.
 * Publish all live roots before any allocation or host-allocator reentry.
 * No argument ownership, native frame, logical C frame or interrupt changes.
 */
static FRAME_CODE int JS_FrameVarargsNameStep(JSFrameRegisterState *state)
{
    JSFrame *frame=state->frame;
    JSStackFrame *sf=&frame->sf;
    JSContext *ctx=frame->bytecode->realm;
    JSAtom atom=get_u32(state->pc+1);
    uint8_t *pc=state->pc+5;
    int result;
    js_frame_begin_c(state);
    state->pc=pc;
    sf->cur_pc=pc;
    frame->saved_sp=state->sp;
    sf->cur_sp=state->sp;
    result=JS_FrameVarargsDefineObjectName(ctx,state->sp[-1],atom,JS_PROP_CONFIGURABLE);
    if (unlikely(result<0)) state->exception_pending=true;
    js_frame_finish_c(state);
    /* Preserve the complete old checkpoint/forward/iterator unwinder.
       Pending exceptions must bypass the operation dispatch, even when
       the following opcode is another set_name. */
    return result<0 ? JS_FrameVarargsSlowSelect(state) : 0;
}
"""


def transform(source, text):
    original = slow_body(text)
    assert "CASE(OP_set_name):" not in original
    lo, hi = span(text, "FRAME_CODE bool JS_FrameVarargsValidate(")
    validator = text[lo:hi]
    validator = replace(
        validator,
        "    bool extended = false;",
        "    bool extended = false;\n    bool name_needs_full = false;",
    )
    validator = replace(
        validator,
        "        case OP_apply:\n            extended = true;",
        "        case OP_apply:\n            name_needs_full = true;\n            extended = true;\n            break;\n        case OP_set_name:\n            extended = true;",
    )
    validator = replace(
        validator, "        bool varargs = false;", "        bool varargs = false, names = false;"
    )
    validator = replace(
        validator,
        "                varargs = true;",
        "                varargs = true;\n            else if (b->byte_code_buf[p] == OP_set_name)\n                names = true;",
    )
    validator = replace(
        validator,
        '        if (varargs && getenv("QJS_DISABLE_FRAME_VARARGS")) return false;',
        '        if (names && getenv("QJS_DISABLE_FRAME_SET_NAME")) return false;\n        if (varargs && getenv("QJS_DISABLE_FRAME_VARARGS")) return false;',
    )
    validator = replace(
        validator,
        "        FRAME_ITERATOR_KIND(b) = varargs ? 3 : 1;",
        "        FRAME_ITERATOR_KIND(b) = (varargs ? 3 : 1) | (names ? 4 : 0) | ((names && name_needs_full) ? 8 : 0);",
    )
    text = text[:lo] + validator + text[hi:]
    marker = "FRAME_CODE int JS_FrameVarargsSlowSelect(JSFrameRegisterState *state)"
    lo, hi = span(text, marker)
    selector = text[lo:hi]
    selector = replace(
        selector,
        "    unsigned op = *state->pc;",
        "    unsigned op = *state->pc;\n"
        "    if (!state->exception_pending && op == OP_set_name)\n"
        "        return JS_FrameVarargsNameStep(state);",
    )
    # This guard precedes the existing checkpoint override on GNU. A name
    # operation inside next() is still one operation; its error takes the
    # retained complete checkpoint unwinder instead of executing the next op.
    if "state->iterator_checkpoint_depth" in selector:
        assert selector.index("return JS_FrameVarargsNameStep") < selector.index(
            "state->iterator_checkpoint_depth"
        )
    assert "(((unsigned char *)f->bytecode)[FRAME_ITERATOR_OFFSET] & 2)" in selector
    assert "(((unsigned char *)f->bytecode)[FRAME_ITERATOR_OFFSET] & 6)" not in selector
    # Names alone use the old base step. A name-containing function admitted
    # by an inherited catch/iterator/other extended opcode needs the complete
    # old extended cleanup. Existing non-name markers stay unchanged.
    selector = replace(
        selector,
        "(((unsigned char *)f->bytecode)[FRAME_ITERATOR_OFFSET] & 2)",
        "(((unsigned char *)f->bytecode)[FRAME_ITERATOR_OFFSET] & 10)",
    )
    prototype = "static FRAME_CODE int JS_FrameVarargsNameStep(JSFrameRegisterState *state);\n"
    text = text[:lo] + prototype + selector + text[hi:]
    text += "\n" + helpers(source) + STEP
    assert slow_body(text) == original, "The old big semantic function must remain literal."
    assert text.count("static FRAME_CODE int JS_FrameVarargsNameStep(") == 2
    return text
