"""Isolated suspended-frame entry C core overlay and opcode eligibility catalog.

The complete slow loop is copied from this build's declared core overlays.
Its opcode bodies, exception walker and suspended-slot cleanup are unchanged.
The pinned upstream input never changes. MIT, as in quickjs.c.
"""

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from paths import source_file

SIGNATURE = "static JSValue JS_CallInternal(JSContext *caller_ctx, JSValueConst func_obj,\n"
RAW_SHA = "ffe47da76827b050f4a267b4893c3aac30f79887dff3b416156a8c43d9c56fa6"
ELIGIBLE_OPCODES = (
    "add",
    "add_loc",
    "and",
    "dec",
    "dec_loc",
    "drop",
    "dup",
    "dup1",
    "eq",
    "get_arg",
    "get_arg0",
    "get_arg1",
    "get_arg2",
    "get_arg3",
    "get_loc",
    "get_loc0",
    "get_loc0_loc1",
    "get_loc1",
    "get_loc2",
    "get_loc3",
    "get_loc8",
    "get_loc_check",
    "get_var_ref",
    "get_var_ref0",
    "get_var_ref1",
    "get_var_ref2",
    "get_var_ref3",
    "get_var_ref_check",
    "goto",
    "goto16",
    "goto8",
    "gt",
    "gte",
    "if_false",
    "if_false8",
    "if_true",
    "if_true8",
    "inc",
    "inc_loc",
    "lnot",
    "lt",
    "lte",
    "mod",
    "mul",
    "neq",
    "nip",
    "nop",
    "null",
    "or",
    "push_0",
    "push_1",
    "push_2",
    "push_3",
    "push_4",
    "push_5",
    "push_6",
    "push_7",
    "push_false",
    "push_i16",
    "push_i32",
    "push_i8",
    "push_minus1",
    "push_true",
    "put_arg",
    "put_arg0",
    "put_arg1",
    "put_arg2",
    "put_arg3",
    "put_loc",
    "put_loc0",
    "put_loc1",
    "put_loc2",
    "put_loc3",
    "put_loc8",
    "put_loc_check",
    "put_loc_check_init",
    "put_var_ref",
    "put_var_ref0",
    "put_var_ref1",
    "put_var_ref2",
    "put_var_ref3",
    "put_var_ref_check",
    "put_var_ref_check_init",
    "sar",
    "set_arg",
    "set_arg0",
    "set_arg1",
    "set_arg2",
    "set_arg3",
    "set_loc",
    "set_loc0",
    "set_loc1",
    "set_loc2",
    "set_loc3",
    "set_loc8",
    "set_var_ref",
    "set_var_ref0",
    "set_var_ref1",
    "set_var_ref2",
    "set_var_ref3",
    "shl",
    "shr",
    "strict_eq",
    "strict_neq",
    "sub",
    "swap",
    "undefined",
    "xor",
)


def opnames(root):
    text = source_file(root, "quickjs-opcode.h").read_text(encoding="utf-8")
    result = re.findall(r"^DEF\(\s*(\w+)\s*,", text, re.M)
    assert len(result) == 252
    return result


def core_overlay(text, raw, root, build):
    start = raw.index(SIGNATURE)
    end = raw.index("\n}\n", start) + 3
    assert hashlib.sha256(raw[start:end].encode()).hexdigest() == RAW_SHA
    line_count = text.count("\n")
    start = text.index(SIGNATURE)
    end = text.index("\n}\n", start) + 3
    body = text[start:end]
    loops = body[body.index(" restart:\n") :]
    macros = body[
        body.index("#ifdef ENABLE_DUMPS") : body.index("    if (js_poll_interrupts(caller_ctx))")
    ]
    assert macros.count("goto *dispatch_table[opcode = *pc++]") == 1
    marker = "#define SWITCH(pc)      DUMP_BYTECODE_OR_DONT(pc) __extension__ ({ goto *dispatch_table[opcode = *pc++]; });"
    assert macros.count(marker) == 1
    switch = "#define SWITCH(pc)      DUMP_BYTECODE_OR_DONT(pc) switch (opcode = *pc++)"
    assert macros.count(switch) == 1
    macros = macros.replace(
        switch,
        "#define SWITCH(pc) DUMP_BYTECODE_OR_DONT(pc) CVM_SEGMENT_TRY() switch (opcode = *pc++)",
    )
    declaration = """static JSValue JS_CVMResumeInternal(JSContext *caller_ctx, JSValueConst func_obj,
                                    JSValueConst this_obj, JSValueConst new_target,
                                    int argc, JSValueConst *argv, int flags)
{
    JSRuntime *rt = caller_ctx->rt;
    JSAsyncFunctionState *s;
    JSContext *ctx;
    JSObject *p;
    JSFunctionBytecode *b;
    JSStackFrame *sf;
    uint8_t *pc;
    int opcode, i;
    JSValue *local_buf, *stack_buf, *var_buf, *arg_buf, *sp, ret_val, *pval;
    JSVarRef **var_refs;
#ifdef QJS_CVM_NATIVE_OPS
    bool use_native;
    JSCVMSegmentState native_state;
#endif
"""
    entry = """    /* Preserve caller-realm poll before reading/publishing the persistent SF. */
    if (js_poll_interrupts(caller_ctx))
        return JS_EXCEPTION;
    s = JS_VALUE_GET_PTR(func_obj);
    sf = &s->frame;
    p = JS_VALUE_GET_OBJ(sf->cur_func);
    b = p->u.func.function_bytecode;
    ctx = b->realm;
    var_refs = p->u.func.var_refs;
    local_buf = arg_buf = sf->arg_buf;
    var_buf = sf->var_buf;
    stack_buf = var_buf + b->var_count;
    sp = sf->cur_sp;
    sf->cur_sp = NULL;
    pc = sf->cur_pc;
    sf->prev_frame = rt->current_stack_frame;
    rt->current_stack_frame = sf;
#ifdef QJS_CVM_NATIVE_OPS
    use_native = js_cvm_segment_mode() == 1;
    if (use_native) {
        native_state.locals = var_buf;
        native_state.args = arg_buf;
        native_state.refs = var_refs;
        native_state.ctx = ctx;
    }
#endif
    if (s->throw_flag)
        goto exception;
    goto restart;
"""
    prefix = [
        "/* Generated from this build's fully declared JS_CallInternal loop. MIT. */",
        "#if defined(QJS_CVM_NATIVE_SEGMENTS) && !DIRECT_DISPATCH",
        '#include "src/common/call/cvm-native-segments.inc"',
        "#undef SWITCH",
        "#undef CASE",
        "#undef DEFAULT",
        "#undef BREAK",
        "#undef DUMP_BYTECODE_OR_DONT",
    ]
    suffix = "\n#undef SWITCH\n#undef CASE\n#undef DEFAULT\n#undef BREAK\n#undef DUMP_BYTECODE_OR_DONT\n#else\n#define JS_CVMResumeEntry JS_CallInternal\n#endif\n"
    content = "\n".join(prefix) + "\n" + declaration + macros + entry + loops + suffix
    target = build.resolve() / "generated/backports/quickjs-coroutine-resume.inc"
    target.parent.mkdir(parents=True, exist_ok=True)
    generated = content.encode("utf-8")
    if not target.exists() or target.read_bytes() != generated:
        target.write_bytes(generated)
    receipt = dict(
        raw_function_sha256=RAW_SHA,
        patched_parent_function_sha256=hashlib.sha256(body.encode()).hexdigest(),
        inherited_loop_sha256=hashlib.sha256(loops.encode()).hexdigest(),
        opcode_bodies_unchanged=True,
        generated=str(target),
        generated_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
        native_opcode_count=len(ELIGIBLE_OPCODES),
        native_opcodes=list(ELIGIBLE_OPCODES),
    )
    target.with_suffix(".json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    anchor = (
        "\n\nstatic JSValue async_func_resume(JSContext *ctx, JSAsyncFunctionState *s)\n"
        "{\n"
        "    JSValue func_obj;\n"
        "\n"
        "    if (js_check_stack_overflow(ctx->rt, 0))\n"
        "        return JS_ThrowStackOverflow(ctx);\n"
        "\n"
        "    /* the tag does not matter provided it is not an object */\n"
        "    func_obj = JS_MKPTR(JS_TAG_INT, s);\n"
        "    return JS_CallInternal(ctx, func_obj, s->this_val, JS_UNDEFINED,\n"
        "                           s->argc, vc(s->frame.arg_buf),\n"
        "                           JS_CALL_FLAG_GENERATOR);"
    )
    repl = (
        "\n#define QJS_CVM_NATIVE_SEGMENTS 1\n"
        '#include "quickjs-coroutine-resume.inc"\n'
        "static JSValue async_func_resume(JSContext *ctx, JSAsyncFunctionState *s)\n"
        "{\n"
        "    JSValue func_obj;\n"
        "    if (js_check_stack_overflow(ctx->rt, 0))\n"
        "        return JS_ThrowStackOverflow(ctx);\n"
        "\n"
        "    /* the tag does not matter provided it is not an object */\n"
        "    func_obj = JS_MKPTR(JS_TAG_INT, s);\n"
        "    return JS_CVMResumeEntry(ctx, func_obj, s->this_val, JS_UNDEFINED,\n"
        "                             s->argc, vc(s->frame.arg_buf),\n"
        "                             JS_CALL_FLAG_GENERATOR);"
    )
    assert anchor.count("\n") == repl.count("\n") and text.count(anchor) == 1
    text = text.replace(anchor, repl, 1)
    assert text.count("\n") == line_count
    return text


def eligibility_header(root):
    names = opnames(root)
    eligible = set(ELIGIBLE_OPCODES)
    text = "/* Generated by tools/common/backports/cvm_segments_c.py. MIT. */\n"
    text += "static const uint8_t js_cvm_segment_eligible[256] = {\n"
    text += ",\n".join(
        "    " + ", ".join("1" if name in eligible else "0" for name in names[i : i + 16])
        for i in range(0, len(names), 16)
    )
    text += ",\n    0, 0, 0, 0\n};\n"
    return text


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source-root", type=Path, required=True)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    result = eligibility_header(args.source_root)
    target = args.source_root / "src/common/call/cvm-native-segment-opcodes.inc"
    if args.check:
        assert target.read_text(encoding="utf-8") == result
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(result, encoding="utf-8", newline="\n")
    print("CVM native segment catalog:", len(ELIGIBLE_OPCODES), "opcodes", flush=True)
