"""Shared same-activation construction and its complete semantic slow owner.

Compile original iterator/append/apply/exception bodies with real Linux types.
The native checkpoint/fast-iterator and apply-fusion optimizations are separate;
this owner supplies the complete observable cleanup required by root3.
"""

import hashlib
import json
import re
from c_workers import module, replace_one


def scoped_helpers(source):
    """Specialize the existing coherent C boundary, retaining its live checks."""
    from admission import function

    owner = (source / "src/common/call/interpreter-slow-host.inc").read_text()
    template = function(owner, "static QJS_FRAME_SLOW_HOST_CODE JSValue js_frame_slow_host_call(")
    body = template[template.index("{") :]
    original = "js_frame_legacy_call(ctx, callee, receiver, argc, argv)"
    if body.count(original) != 2:
        raise ValueError("Review scoped/original C boundary consumers")
    common = (
        "JSFrameRegisterState *state, JSFrame *frame, JSFrameSegment *segment, "
        "size_t used, uint8_t *pc, JSValue *sp, JSContext *ctx"
    )
    specs = [
        ("start", "int", ", bool async", "js_for_of_start(ctx, sp, async)"),
        ("next", "int", ", int offset", "js_for_of_next(ctx, sp, offset)"),
        (
            "close",
            "int",
            ", JSValueConst object, bool throwing",
            "JS_IteratorClose(ctx, object, throwing)",
        ),
        ("append", "int", "", "js_append_enumerate(ctx, sp)"),
        (
            "apply",
            "JSValue",
            ", int magic",
            "js_function_apply(ctx, sp[-3], 2, vc(&sp[-2]), magic)",
        ),
        (
            "create",
            "JSValue",
            ", JSValueConst ctor",
            "js_create_from_ctor(ctx, ctor, JS_CLASS_OBJECT)",
        ),
    ]
    declarations, definitions = [], []
    for name, result, extra, call in specs:
        signature = (
            "static QJS_FRAME_SLOW_HOST_CODE "
            + result
            + " js_linux_construct_host_"
            + name
            + "("
            + common
            + extra
            + ")"
        )
        code = body.replace(original, call)
        if result == "int":
            code = replace_one(
                code, "    JSValue result;", "    int result;", "actual int C boundary result"
            )
        code = replace_one(
            code,
            "    state->sp = sp;",
            "    state->sp = sp;\n    frame->saved_sp = sp;\n    frame->sf.cur_pc = pc;",
            "exact paused opcode cursor before callback",
        )
        declarations.append(signature + ";")
        definitions.append(signature + "\n" + code)
    return "\n".join(declarations) + "\n", "\n\n".join(definitions) + "\n"


def validator(source, text):
    """Extend only the existing derived short/long admission, not the base."""
    ops = (*module(source, "iterator").OPS, "append", "apply")
    text = replace_one(
        text,
        "    bool captured_args = false;",
        "    bool captured_args = false;\n    bool extended = false, varargs = false;\n"
        "    FRAME_ITERATOR_KIND(b) = 0;",
        "complete slow admission metadata",
    )
    anchor = "#undef FRAME_OP\n            break;\n"
    extra = "".join("        case OP_" + name + ":\n" for name in ops)
    extra += (
        "            extended = true;\n"
        "            if (op == OP_append || op == OP_apply) varargs = true;\n"
        "            break;\n"
    )
    text = replace_one(text, anchor, anchor + extra, "complete original slow opcode set")
    anchor = "        case OP_goto:\n        case OP_if_true:\n        case OP_if_false:"
    text = replace_one(
        text,
        anchor,
        "        case OP_catch:\n        case OP_gosub:\n" + anchor,
        "checked exception/return branch targets",
    )
    final = "    FRAME_KIND(b) = (captured_args ? 5 : readonly_args ? 3 : 1) | (b->var_ref_count ? 8 : 0);"
    policy = """    if (extended && getenv("QJS_DISABLE_FRAME_ITERATOR") != NULL)
        return false;
    if (varargs && getenv("QJS_DISABLE_FRAME_VARARGS") != NULL)
        return false;
    FRAME_ITERATOR_KIND(b) = varargs ? 3 : extended ? 1 : 0;
    if (varargs) {
        FRAME_VARARGS_DIRECT_MODE(b) = getenv("QJS_DISABLE_FRAME_VARARGS_DIRECT") ? 2 : 1;
        FRAME_VARARGS_FUSION_MODE(b) = getenv("QJS_DISABLE_FRAME_VARARGS_FUSION") ? 2 : 1;
    }
    if (extended) FRAME_ITERATOR_KIND(b) |= 8 |
        (getenv("QJS_DISABLE_FRAME_ARRAY_ITERATOR") == NULL ? 4 : 0);
"""
    return replace_one(text, final, policy + final, "publish extended metadata after validation")


def loop_policy(loop):
    marker = '#include "quickjs-interpreter-slow.h"'
    return replace_one(
        loop,
        marker,
        "FRAME_CODE int JS_FrameInterpSlow(JSFrameRegisterState *state);\n" + marker,
        "complete selector declaration before original numeric/property boundaries",
    )


def generate(source, output, layout, *, loop_override=None):
    from forwarding import release

    iterator = module(source, "iterator")
    varargs = module(source, "varargs")
    slow = module(source, "generate-slow")
    original = (
        (source / "src/common/call/quickjs-interpreter-loop.inc").read_text()
        if loop_override is None
        else loop_override
    )
    bodies, exception = iterator.bodies(source)
    bodies.update(varargs.core_bodies(source))
    expanded = replace_one(
        original,
        "        CASE(OP_nop) :",
        "\n".join(bodies.values()) + "\n        CASE(OP_nop) :",
        "original complete opcode bodies",
    )
    anchor = "    ret_val = JS_EXCEPTION;\nreturn_frame:"
    expanded = replace_one(
        expanded,
        anchor,
        exception + "\n" + anchor,
        "original catch/iterator-close exception marker walk",
    )
    dispatch = (source / "src/common/call/quickjs-interpreter-dispatch.inc").read_text()
    for name in bodies:
        dispatch = replace_one(
            dispatch,
            "FRAME_TARGET(" + name + ", invalid)",
            "FRAME_TARGET(" + name + ", OP_" + name + ")",
            "complete semantic dispatch " + name,
        )
    (output / "quickjs-linux-construct-dispatch.h").write_text(dispatch)
    generated = output / "quickjs-linux-construct-slow.h"
    slow.generate(source, generated, interpreter_text=expanded)
    text = generated.read_text().split("\nFRAME_OPCODE_CODE", 1)[0]
    text = replace_one(
        text,
        "FRAME_CODE int JS_FrameInterpSlow(",
        "FRAME_CODE int JS_FrameVarargsSlow(",
        "independent complete slow owner",
    )
    text = replace_one(
        text,
        '#include "src/common/call/quickjs-interpreter-dispatch.inc"',
        '#include "quickjs-linux-construct-dispatch.h"',
        "complete real computed-goto table",
    )
    old = "ret_val = js_frame_legacy_call(ctx, callee, call_this, call_argc, vc(call_argv));"
    text = replace_one(
        text,
        old,
        "ret_val = js_frame_slow_host_call(state, frame, segment, used_bytes, pc, sp, "
        "ctx, callee, call_this, call_argc, vc(call_argv));",
        "coherent original legacy callback",
    )
    calls = [
        (
            "js_for_of_start(ctx, sp, false)",
            "js_linux_construct_host_start(state,frame,segment,used_bytes,pc,sp,ctx,false)",
        ),
        (
            "js_for_of_next(ctx, sp, offset)",
            "js_linux_construct_host_next(state,frame,segment,used_bytes,pc,sp,ctx,offset)",
        ),
        (
            "JS_IteratorClose(ctx, sp[-1], false)",
            "js_linux_construct_host_close(state,frame,segment,used_bytes,pc,sp,ctx,sp[-1],false)",
        ),
        (
            "JS_IteratorClose(ctx, sp[-1], true)",
            "js_linux_construct_host_close(state,frame,segment,used_bytes,pc,sp,ctx,sp[-1],true)",
        ),
        (
            "js_append_enumerate(ctx, sp)",
            "js_linux_construct_host_append(state,frame,segment,used_bytes,pc,sp,ctx)",
        ),
        (
            "js_function_apply(ctx, sp[-3], 2, vc(&sp[-2]), magic)",
            "js_linux_construct_host_apply(state,frame,segment,used_bytes,pc,sp,ctx,magic)",
        ),
    ]
    for old, new in calls:
        text = replace_one(text, old, new, "typed coherent observable C opcode " + old)
    # Same consumed-slot publication repairs as the accepted complete owner.
    repairs = [
        (
            "            JSValue val = *--sp;\n            JS_FreeValue(ctx, val);",
            "            JSValue val = *--sp;\n            *sp = JS_UNDEFINED;\n"
            "            state->sp = sp; frame->saved_sp = sp; sf->cur_sp = sp;\n"
            "            JS_FreeValue(ctx, val);",
        ),
        (
            "                    JS_FreeValue(ctx, sp[-1]); /* drop the next method */\n                    sp--;",
            "                    JSValue consumed = *--sp;\n                    *sp = JS_UNDEFINED;\n"
            "                    state->sp = sp; frame->saved_sp = sp; sf->cur_sp = sp;\n"
            "                    JS_FreeValue(ctx, consumed);",
        ),
        (
            "                    rt->current_exception = JS_UNINITIALIZED;\n                    JS_FreeValueRT(rt, ctx->error_back_trace);",
            "                    rt->current_exception = JS_UNINITIALIZED;\n"
            "                    state->sp = sp; frame->saved_sp = sp; sf->cur_sp = sp;\n"
            "                    JS_FreeValueRT(rt, ctx->error_back_trace);",
        ),
        (
            "    for (pval = local_buf; pval < sp; pval++)\n        JS_FreeValue(ctx, *pval);",
            "    for (pval = local_buf; pval < sp; pval++) {\n"
            "        JSValue consumed = *pval;\n        *pval = JS_UNDEFINED;\n"
            "        JS_FreeValue(ctx, consumed);\n    }",
        ),
    ]
    for old, new in repairs:
        text = replace_one(text, old, new, "complete slow consumed owner publication")
    text = release(text)
    # The shared transformer only needs this staging declaration as its policy
    # include anchor; admission remains the existing real Linux short/long pair.
    declaration = "FRAME_CODE bool JS_FrameVarargsValidate(JSFunctionBytecode *b);\n"
    selector = """
FRAME_CODE int JS_FrameInterpSlow(JSFrameRegisterState *state)
{
    for (JSFrame *f=state->frame; f; f=js_frame_parent(f))
        if ((FRAME_ROOT(f)!=1 && js_frame_forward_sf(f->sf.prev_frame)) ||
            FRAME_ITERATOR_KIND(f->bytecode))
            return JS_FrameVarargsSlow(state);
    return JS_FrameLinuxBaseSlow(state);
}
"""
    text = (
        declaration
        + "FRAME_CODE int JS_FrameVarargsSlow(JSFrameRegisterState *state);\n"
        + selector
        + text
    )
    text = module(source, "construct-continuation").transform(source, text, module)
    text = replace_one(
        text,
        "js_create_from_ctor(ctx,argv[-1],JS_CLASS_OBJECT)",
        "js_linux_construct_host_create(state,frame,segment,used_bytes,pc,sp,ctx,argv[-1])",
        "coherent constructor allocation boundary",
    )
    text = replace_one(text, declaration, "", "remove staging-only admission declaration")
    shared = source / "src/x86/win64/common/quickjs-interpreter-construct.inc"
    policy = shared.read_text()
    start = policy.index("#if defined(_MSC_VER)\n#pragma section")
    end = policy.index("\nstatic FRAME_INLINE bool js_frame_construct_enabled", start)
    policy = (
        policy[:start]
        + """static _Atomic(unsigned) js_frame_construct_policy
    __attribute__((section(".data.qjs_linux_construct")));
"""
        + policy[end:]
    )
    # A returned C semantic boundary resumes a running Linux frame.
    policy = replace_one(
        policy,
        "    frame->pending = 0;\n    js_frame_finish_c(state);",
        "    frame->pending = 0;\n    frame->sf.cur_sp = NULL;\n    js_frame_finish_c(state);",
        "constructor result resumes ordinary running-frame convention",
    )
    text = replace_one(
        text,
        '#include "src/x86/win64/common/quickjs-interpreter-construct.inc"',
        policy,
        "actual-type shared constructor policy/return owner",
    )
    text = replace_one(
        text,
        "    if (event) state->result=ret_val;",
        "    if (event) state->result=ret_val;\n    else if (frame) frame->sf.cur_sp=NULL;",
        "full semantic step resumes running frame",
    )
    # The constructor begins directly at the copied entry; its original label
    # has no incoming transfer in this separate function. Keep all statements.
    push_at = text.index("FRAME_CODE int JS_FrameVarargsConstructCall(")
    push = text[push_at:]
    if push.count("enter_frame:\n") != 1 or "goto enter_frame;" in push:
        raise ValueError("Review constructor copied entry label before removal")
    text = text[:push_at] + push.replace("enter_frame:\n", "", 1)
    declarations, definitions = scoped_helpers(source)
    text = declarations + text
    (output / "quickjs-linux-construct.h").write_text(text)
    (output / "quickjs-linux-construct-host.h").write_text(definitions)

    base = output / "quickjs-interpreter-slow.h"
    original_base = base.read_text()
    adapted = replace_one(
        original_base,
        "FRAME_CODE int JS_FrameInterpSlow(",
        "FRAME_CODE int JS_FrameLinuxBaseSlow(",
        "retained original base slow owner",
    )
    adapted = replace_one(
        adapted,
        "#ifndef QJS_LINUX_REGISTER_FOUNDATION",
        "#if !defined(QJS_LINUX_REGISTER_FOUNDATION) || defined(QJS_LINUX_CONSTRUCT_CONTINUATION)",
        "enable ordinary same-activation constructor hook on Linux",
    )
    adapted += '\n#include "quickjs-linux-construct.h"\n'
    base.write_text(adapted)
    owners = [
        "tools/x86/common/codegen/construct-continuation.py",
        "tools/x86/common/codegen/iterator.py",
        "tools/x86/common/codegen/varargs.py",
        "tools/x86/common/codegen/call-forward.py",
        "tools/common/c_extract/generate_slow_c.py",
        str(shared.relative_to(source)),
        "src/common/call/interpreter-slow-host.inc",
    ]
    record = dict(
        status="generated-not-qualified",
        source_files={n: hashlib.sha256((source / n).read_bytes()).hexdigest() for n in owners},
        generated_sha256=hashlib.sha256(text.encode()).hexdigest(),
        dispatch_sha256=hashlib.sha256(dispatch.encode()).hexdigest(),
        host_sha256=hashlib.sha256(definitions.encode()).hexdigest(),
        base_slow_before_sha256=hashlib.sha256(original_base.encode()).hexdigest(),
        base_slow_after_sha256=hashlib.sha256(adapted.encode()).hexdigest(),
        original_core_bodies={n: hashlib.sha256(v.encode()).hexdigest() for n, v in bodies.items()},
        constructor_root=3,
        frame_growth=0,
        state_growth=0,
        entries=[
            "JS_FrameVarargsConstructCall",
            "JS_FrameVarargsConstructHeapReturn",
            "JS_FrameVarargsSlow",
            "JS_FrameInterpSlow",
            "JS_FrameLinuxBaseSlow",
        ],
        scope="Complete ordinary construct continuation and original full semantic cleanup dependency;not native argument/checkpoint/fast iterator/apply fusion coverage",
    )
    (output / "CONSTRUCT.json").write_text(json.dumps(record, indent=2) + "\n")


def append(source, stream, layout, forward_blocks):
    """Select the unchanged constructor-return factories under measured SysV."""
    from x86.common.abi.native_abi import source_abi

    @source_abi
    def shared(root, layout_override=None):
        return module(root, "call-forward").asm_blocks(None, False, False)

    selected = [
        (name, rows)
        for name, rows in shared(source, layout_override=layout)
        if name in ("JS_FrameConstructNativeReturn", "JS_FrameConstructNativeHeapReturn")
    ]
    if len(selected) != 2:
        raise ValueError("Review complete constructor native return factories")
    selected = [
        (
            n,
            [
                r.replace("JS_FrameCallForwardOldReleaseValues", "interp_release_values")
                for r in rows
            ],
        )
        for n, rows in selected
    ]
    for name, rows in forward_blocks:
        if name == "JS_FrameLinuxForwardReturn":
            rows[:0] = ["cmp BYTE PTR [rbp+62], 3", "je JS_FrameConstructNativeReturn"]
    # A caught slow exception resumes this activation; event1 still exits it.
    code = stream["code"]
    at = code.index("interp_host_exception:")
    end = code.index("jmp interp_exit", at)
    before = code[at + 1 : end + 1]
    expected = [
        "mov rcx, rbx",
        "call JS_FrameInterpSlow",
        "mov rbp, QWORD PTR [rbx]",
        "mov r12, QWORD PTR [rbx+16]",
        "mov r13, QWORD PTR [rbx+24]",
        "jmp interp_exit",
    ]
    if before != expected:
        raise ValueError("Review caught host exception event continuation")
    code[at + 1 : end + 1] = expected[:2] + ["test eax, eax", "jz interp_reload"] + expected[2:]
    return selected, dict(
        root=3,
        shared_return_factories=True,
        heap_return="typed state-only SysV helper",
        slow_dependency="complete original catch/iterator/append/apply semantics",
        native_iterator_apply_optimizations=False,
        frame_growth=0,
        state_growth=0,
    )
