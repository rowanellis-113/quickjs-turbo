"""Same-activation constructor continuation using the complete slow executor."""

import re


def replace(text, old, new):
    if text.count(old) != 1:
        raise ValueError("Review constructor anchor: " + old[:110])
    return text.replace(old, new)


def transform(source, text, module):
    # The complete varargs slow executor already owns catch/iterator/forward
    # cleanup. Select it whenever a constructor continuation is on the chain.
    marker = "FRAME_CODE bool JS_FrameVarargsValidate(JSFunctionBytecode *b)"
    text = replace(
        text,
        marker,
        '#include "src/common/kernel/construct.inc"\n' + marker,
    )
    text = replace(
        text,
        "        if ((FRAME_ROOT(f)!=1 && js_frame_forward_sf(f->sf.prev_frame)) ||",
        "        if (FRAME_ROOT(f)==3 || (FRAME_ROOT(f)!=1 && js_frame_forward_sf(f->sf.prev_frame)) ||",
    )
    # Freeze this child's exit kind before its storage becomes available to a
    # finalizer's nested activation. Restore the parent before selecting this.
    text = replace(
        text,
        "return_frame:\n",
        "return_frame:;\n    bool construct_return = FRAME_ROOT(frame)==3;\n",
    )
    text = replace(
        text,
        "    if (unlikely(JS_IsException(ret_val)))\n        goto exception;\n    goto finish_call;\nrestore_exception:",
        "    if (construct_return) {\n"
        "        state->frame=frame;state->segment=segment;state->used_bytes=used_bytes;\n"
        "        state->pc=pc;state->sp=sp;sf->cur_sp=sp;\n"
        "        ret_val=js_frame_construct_result(ctx,frame,ret_val);\n"
        "    }\n"
        "    if (unlikely(JS_IsException(ret_val)))\n        goto exception;\n    goto finish_call;\nrestore_exception:",
    )
    # Reuse the exact current push: arity padding, captures, segment/quota,
    # interrupt and initialization stay tied to the existing executor.
    start = text.index("FRAME_CODE int JS_FrameVarargsSlow(JSFrameRegisterState *state)")
    slow = text[start:]
    enter = slow[slow.index("enter_frame:\n") : slow.index("dispatch:\n")]
    # incoming_copy is always zero here; the apply-only copied-array branch
    # is still compiled from the original text but is unreachable.
    enter = replace(enter, "    FRAME_ROOT(frame) = parent == NULL;", "    FRAME_ROOT(frame) = 3;")
    enter = replace(enter, "    FRAME_CLEAR_STACK_AUX(sf);", "    FRAME_INIT_STACK_AUX(sf, true);")
    stats = module(source, "generate-slow-c").COUNTERS
    statvars = (
        "\n#ifdef QJS_INTERP_FRAME_DIAGNOSTICS\n"
        + "".join(
            "    "
            + (
                "unsigned"
                if n in ("depth", "max_depth")
                else "size_t"
                if n == "peak_bytes"
                else "uint64_t"
            )
            + " "
            + n
            + "=state->"
            + n
            + ";\n"
            for n in stats
        )
        + "#endif\n"
    )
    statsave = (
        "\n#ifdef QJS_INTERP_FRAME_DIAGNOSTICS\n"
        + "".join("    state->" + n + "=" + n + ";\n" for n in stats)
        + "#endif\n"
    )
    push = (
        r"""
FRAME_CODE int JS_FrameVarargsConstructCall(JSFrameRegisterState *state)
{
    JSFrame *frame=state->frame,*parent;
    JSFrameSegment *segment=state->segment;
    JSRuntime *rt=state->rt;
    JSContext *ctx=frame->bytecode->realm;
    JSStackFrame *sf=&frame->sf;
    JSValue *sp=state->sp,*arg_buf,*var_buf,*stack_buf,*local_buf;
    int i,owned_args,incoming_argc=get_u16(state->pc+1),incoming_copy=0;
    JSValue *argv=sp-incoming_argc;
    JSValue func_obj=argv[-2],this_obj,ret_val=JS_UNDEFINED;
    JSValueConst *incoming_argv=vc(argv);
    JSFunctionBytecode *b;
    uint8_t *pc=state->pc+3;
    size_t frame_size,used_bytes=state->used_bytes;
#if defined(_MSC_VER)
    JSObject *p;
    JSVarRef **var_refs;
#endif
STATS
    if (!js_frame_construct_enabled() || incoming_argc>32765 ||
        !JS_IsObject(func_obj) || !JS_IsObject(argv[-1]) ||
        JS_VALUE_GET_OBJ(func_obj)!=JS_VALUE_GET_OBJ(argv[-1])) return -1;
    JSObject *callee=JS_VALUE_GET_OBJ(func_obj);
    if(callee->class_id!=JS_CLASS_BYTECODE_FUNCTION || !callee->is_constructor ||
       callee->u.func.function_bytecode->is_derived_class_constructor) return -1;
    js_frame_begin_c(state);
    /* Admission can enter the long validator. Its soft C-stack check must see
       the exact live native-frame quota; finish before the original fallback
       begins another C boundary, so a rejected target is never charged twice. */
    if(!(b=js_frame_target(func_obj))) {
        js_frame_finish_c(state);
        return -1;
    }
    sf->cur_pc=pc;sf->cur_sp=sp;frame->saved_sp=sp;
    frame->pending=(uint16_t)(incoming_argc+2);
    if(unlikely(js_poll_interrupts(ctx)))goto original_push_exception;
    /* Exact original creation helper: prototype, realm, allocation and GC. */
    this_obj=js_create_from_ctor(ctx,argv[-1],JS_CLASS_OBJECT);
    if(JS_IsException(this_obj))goto original_push_exception;
    /* Both original operands own the same live function. Drop one provably
       nonlast reference and transfer that operand slot to the new object. */
    assert(JS_REF_COUNT(callee)>=2);
    JS_REF_COUNT(callee)--;
    argv[-2]=this_obj;
ENTER
    goto construct_step_done;
push_exception:
    state->frame=frame;state->segment=segment;state->used_bytes=used_bytes;
    state->pc=pc;state->sp=frame->saved_sp;
    ret_val=js_frame_construct_result(ctx,frame,JS_EXCEPTION);
original_push_exception:
    state->frame=frame;state->segment=segment;state->used_bytes=used_bytes;
    state->pc=pc;state->sp=frame->saved_sp;
    state->exception_pending=true;
SAVE
    js_frame_finish_c(state);
    return JS_FrameVarargsSlow(state);
construct_step_done:
    state->frame=frame;state->segment=segment;state->used_bytes=used_bytes;
    state->pc=pc;state->sp=sp;
SAVE
    js_frame_finish_c(state);
    return 0;
}
""".replace("STATS", statvars)
        .replace("ENTER", enter)
        .replace("SAVE", statsave)
    )
    # The copied dead apply branch contains labels to the full executor.
    # Avoid an unused undeclared label while preserving the live push text.
    push = push.replace("goto varargs_apply_fallback;", "goto push_exception;")
    push = push.replace("goto return_frame;", "goto push_exception;")
    text += "\n" + push
    return text
