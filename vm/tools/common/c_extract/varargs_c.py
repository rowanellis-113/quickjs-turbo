"""Pure-C varargs/apply/fusion/checkpoint transform extractor."""

from c_source_match import replace_one
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


def core_bodies(source):
    core = _frame_source_file(source, "quickjs.c").read_text(encoding="utf-8")
    # The operations call exactly the inherited core helpers. Store results and
    # clear consumed roots before any finalizer/reentrant GC can run.
    append = """        CASE(OP_append):
            {
                JSValue consumed;
                sf->cur_pc = pc;
                state->sp = sp;
                frame->saved_sp = sp;
                sf->cur_sp = sp;
                if (js_append_enumerate(ctx, sp))
                    goto exception;
                consumed = *--sp;
                *sp = JS_UNDEFINED;
                state->sp = sp;
                frame->saved_sp = sp;
                sf->cur_sp = sp;
                JS_FreeValue(ctx, consumed);
            }
            BREAK;"""
    apply = """        CASE(OP_apply):
            {
                int magic = get_u16(pc);
                JSValue result, consumed;
                pc += 2;
                sf->cur_pc = pc;
                state->sp = sp;
                frame->saved_sp = sp;
                sf->cur_sp = sp;
                result = js_function_apply(ctx, sp[-3], 2, vc(&sp[-2]), magic);
                if (unlikely(JS_IsException(result)))
                    goto exception;
                consumed = sp[-3];
                sp[-3] = result;
                state->sp = sp;
                frame->saved_sp = sp;
                sf->cur_sp = sp;
                JS_FreeValue(ctx, consumed);
                consumed = sp[-2];
                sp[-2] = JS_UNDEFINED;
                JS_FreeValue(ctx, consumed);
                consumed = sp[-1];
                sp[-1] = JS_UNDEFINED;
                JS_FreeValue(ctx, consumed);
                sp -= 2;
                state->sp = sp;
                frame->saved_sp = sp;
                sf->cur_sp = sp;
            }
            BREAK;"""
    assert "static __exception int js_append_enumerate(" in core
    assert "static JSValue js_function_apply(" in core
    return dict(append=append, apply=apply)


def direct_call_text(text):
    """Only the new full semantic step changes; boundary helpers remain L."""
    lo = text.index("FRAME_CODE int JS_FrameVarargsSlow(")
    hi = text.index("\n}\n#undef CASE", lo) + 2
    body = text[lo:hi]
    a = body.index("    CASE(OP_apply):")
    z = body.index("    CASE(OP_nop):", a)
    inherited = body[a:z]
    assert inherited.count("pc += 2;") == 1
    fallback = inherited[inherited.index("                sf->cur_pc = pc;") :]
    fallback = fallback[: fallback.rindex("            }")]
    fallback = (
        "varargs_apply_fallback:\n    {\n        int magic = get_u16(pc - 2);\n        JSValue result, consumed;\n"
        + fallback
        + "\n    }\n    goto dispatch;\n"
    )
    direct = """    CASE(OP_apply):
        {
            int magic = get_u16(pc);
            pc += 2;
            sf->cur_pc = pc;
            state->sp = sp;
            frame->saved_sp = sp;
            sf->cur_sp = sp;
            if (magic == 0 && ((unsigned char *)b)[FRAME_ITERATOR_OFFSET+1] == 1 && JS_IsObject(sp[-1])) {
                JSObject *array = JS_VALUE_GET_OBJ(sp[-1]);
                if (array->class_id == JS_CLASS_ARRAY && array->fast_array &&
                    JS_VALUE_GET_TAG(array->prop[0].u.value) == JS_TAG_INT &&
                    JS_VALUE_GET_INT(array->prop[0].u.value) >= 0 &&
                    (uint32_t)JS_VALUE_GET_INT(array->prop[0].u.value) == array->u.array.count &&
                    array->u.array.count <= JS_MAX_LOCAL_VARS) {
                    uint32_t count = array->u.array.count;
                    JSFunctionBytecode *target = js_frame_target(sp[-3]);
                    if (target) {
                        size_t need = FRAME_HEADER_BYTES + sizeof(JSValue) *
                            (max_int((int)count, target->arg_count) + target->var_count + target->stack_size) +
                            FRAME_CAPTURE_BYTES(target);
                        /* Preserve the old path when the larger owned window
                           would itself cause an earlier stack overflow. */
                        if (!js_check_stack_overflow(rt, need)) {
                            frame->pending = 3;
                            b = target;
                            func_obj = sp[-3];
                            this_obj = sp[-2];
                            incoming_argc = count;
                            incoming_argv = NULL;
                            incoming_copy = 2;
                            goto enter_frame;
                        }
                    }
                }
            }
            goto varargs_apply_fallback;
        }
"""
    body = body[:a] + direct + body[z:]
    needle = "\nfinish_call:\n"
    assert body.count(needle) == 1
    body = body.replace(needle, "\n" + fallback + needle)
    needle = "    if (unlikely(js_poll_interrupts(ctx)))\n        goto push_exception;"
    body = replace_one(
        body,
        needle,
        "    if (incoming_copy != 2 && unlikely(js_poll_interrupts(ctx)))\n        goto push_exception;",
    )
    needle = """    owned_args = (incoming_copy || incoming_argc < b->arg_count ||
                  FRAME_CAPTURED_ARGS(b)) ? b->arg_count : 0;"""
    body = replace_one(
        body,
        needle,
        """    owned_args = incoming_copy == 2 ? max_int(incoming_argc, b->arg_count) :
        (incoming_copy || incoming_argc < b->arg_count || FRAME_CAPTURED_ARGS(b)) ? b->arg_count : 0;""",
    )
    needle = "    parent = frame;\n    frame = (JSFrame *)(segment->data + segment->used);"
    replacement = """    if (incoming_copy == 2) {
        /* Segment growth may run an allocator callback. Never carry a backing
           pointer across it: reload the rooted builder and its dense span. */
        JSValue array_value = frame->saved_sp[-1];
        JSObject *array = JS_IsObject(array_value) ? JS_VALUE_GET_OBJ(array_value) : NULL;
        if (!array || array->class_id != JS_CLASS_ARRAY || !array->fast_array ||
            JS_VALUE_GET_TAG(array->prop[0].u.value) != JS_TAG_INT ||
            JS_VALUE_GET_INT(array->prop[0].u.value) != incoming_argc ||
            array->u.array.count != (uint32_t)incoming_argc) {
            b = frame->bytecode;
            ctx = b->realm;
            func_obj = sf->cur_func;
            this_obj = frame->this_value;
            frame->pending = 0;
            goto varargs_apply_fallback;
        }
        incoming_argv = vc(array->u.array.u.values);
    }
    parent = frame;
    frame = (JSFrame *)(segment->data + segment->used);"""
    body = replace_one(body, needle, replacement)
    needle = "    arg_buf = (JSValue *)incoming_argv;\n    if (owned_args) {"
    replacement = """    arg_buf = (JSValue *)incoming_argv;
    if (incoming_copy == 2) {
        /* Own all actual arguments, including the extra prefix. Existing
           native/C var_buf-owned_args cleanup releases exactly this window. */
        arg_buf = local_buf;
        for (i = 0; i < incoming_argc; i++)
            arg_buf[i] = js_dup(incoming_argv[i]);
        for (; i < owned_args; i++)
            arg_buf[i] = JS_UNDEFINED;
#ifdef QJS_INTERP_FRAME_DIAGNOSTICS
        copied_values += incoming_argc;
#endif
    } else if (owned_args) {"""
    body = replace_one(body, needle, replacement)
    needle = "    sf->arg_count = owned_args ? b->arg_count : max_int(incoming_argc, b->arg_count);"
    replacement = "    sf->arg_count = incoming_copy == 2 ? owned_args : owned_args ? b->arg_count : max_int(incoming_argc, b->arg_count);"
    body = replace_one(body, needle, replacement)
    needle = "    FRAME_ROOT(frame) = parent == NULL;\n    rt->current_stack_frame = sf;"
    replacement = """    FRAME_ROOT(frame) = parent == NULL;
    /* Snapshot before the call poll, like the original apply argument list.
       An interrupt unwinds the unpublished child without a callee backtrace. */
    if (incoming_copy == 2 && unlikely(js_poll_interrupts(ctx))) {
#ifdef QJS_INTERP_FRAME_DIAGNOSTICS
        /* return_frame removes one depth; this child was never published
           or counted as a push. Balance its internal cleanup ledger only. */
        depth++;
#endif
        ret_val = JS_EXCEPTION;
        goto return_frame;
    }
    rt->current_stack_frame = sf;"""
    body = replace_one(body, needle, replacement)
    assertion = '_Static_assert(offsetof(JSFunctionBytecode,pc2line_len)+sizeof(int)<=FRAME_ITERATOR_OFFSET+1 && FRAME_ITERATOR_OFFSET+1<offsetof(JSFunctionBytecode,pc2line_buf), "direct control uses measured bytecode padding");\n'
    return text[:lo] + assertion + body + text[hi:]


DEPENDENCIES = "\njs_create_array_iterator(); js_array_iterator_next(); js_function_call(); js_create_from_ctor();\n"
HELPERS = r"""
static FRAME_INLINE bool JS_FrameVarargsIsCFunction(JSContext *ctx, JSValueConst val, JSCFunction *func,
                           int magic)
{
    JSObject *p;
    if (JS_VALUE_GET_TAG(val) != JS_TAG_OBJECT)
        return false;
    p = JS_VALUE_GET_OBJ(val);
    if (p->class_id == JS_CLASS_C_FUNCTION)
        return (p->u.cfunc.c_function.generic == func && p->u.cfunc.magic == magic);
    else
        return false;
}

/* Only ordinary own data slots can prove an unobservable property read.
 * Reject accessors, proxies, exotic prototypes and deep chains, then let
 * the original iterator protocol perform every observable operation. */
static FRAME_INLINE bool js_frame_varargs_data(JSObject *p, JSAtom atom, JSValue *value)
{
    for (unsigned depth = 0; p && depth < 32; depth++, p = p->shape->proto) {
        JSProperty *property;
        JSShapeProperty *shape;
        if (p->class_id != JS_CLASS_OBJECT && p->class_id != JS_CLASS_ARRAY)
            return false;
        if (p->is_exotic && p->class_id != JS_CLASS_ARRAY)
            return false;
        shape = find_own_property(&property, p, atom);
        if (shape) {
            if ((shape->flags & JS_PROP_TMASK) != JS_PROP_NORMAL)
                return false;
            *value = property->u.value;
            return true;
        }
    }
    return false;
}

static FRAME_INLINE bool js_frame_varargs_dense(JSContext *ctx, JSValue source)
{
    JSValue method, next;
    JSObject *array, *function;
    JSContext *iterator_realm;
    JSCFunctionType create = { .generic_magic = js_create_array_iterator };
    JSCFunctionType advance = { .iterator_next = js_array_iterator_next };
    if (!JS_IsObject(source)) return false;
    array = JS_VALUE_GET_OBJ(source);
    if (array->class_id != JS_CLASS_ARRAY || !array->fast_array ||
        JS_VALUE_GET_TAG(array->prop[0].u.value) != JS_TAG_INT ||
        JS_VALUE_GET_INT(array->prop[0].u.value) < 0 ||
        (uint32_t)JS_VALUE_GET_INT(array->prop[0].u.value) != array->u.array.count ||
        array->u.array.count > JS_MAX_LOCAL_VARS)
        return false;
    if (!js_frame_varargs_data(array, JS_ATOM_Symbol_iterator, &method) ||
        !JS_FrameVarargsIsCFunction(ctx, method, create.generic, JS_ITERATOR_KIND_VALUE))
        return false;
    function = JS_VALUE_GET_OBJ(method);
    if (function->u.cfunc.cproto != JS_CFUNC_generic_magic) return false;
    iterator_realm = function->u.cfunc.realm;
    if (!JS_IsObject(iterator_realm->class_proto[JS_CLASS_ARRAY_ITERATOR]) ||
        !js_frame_varargs_data(JS_VALUE_GET_OBJ(iterator_realm->class_proto[JS_CLASS_ARRAY_ITERATOR]), JS_ATOM_next, &next) ||
        !JS_FrameVarargsIsCFunction(ctx, next, advance.generic, 0))
        return false;
    return JS_VALUE_GET_OBJ(next)->u.cfunc.cproto == JS_CFUNC_iterator_next;
}

FRAME_CODE JSFunctionBytecode *JS_FrameVarargsTryFuse(JSFrameRegisterState *state, uint8_t **resume)
{
    JSFrame *frame = state->frame;
    JSStackFrame *sf = &frame->sf;
    JSFunctionBytecode *caller = frame->bytecode, *target;
    JSContext *ctx = caller->realm;
    const uint8_t *pc = state->pc, *end = caller->byte_code_buf + caller->byte_code_len;
    JSValue source, callee, receiver;
    JSValue *sp = state->sp;
    unsigned index, op, method;
    uint32_t count;
    size_t need;
    /* No committed state until the entire sequence, source, target, quota
       and existing segment window have all been proven. */
    if (((unsigned char *)caller)[FRAME_ITERATOR_OFFSET+1] != 1 || ((unsigned char *)caller)[FRAME_ITERATOR_OFFSET+2] != 1 ||
        end - pc < 4 || *pc != OP_array_from || get_u16(pc + 1) != 0)
        return NULL;
    pc += 3;
    if (*pc == OP_push_0) pc++;
    else if (end - pc >= 5 && *pc == OP_push_i32 && get_u32(pc + 1) == 0) pc += 5;
    else return NULL;
    if (pc == end) return NULL;
    op = *pc++;
    if (op >= OP_get_loc0 && op <= OP_get_loc3) {
        index = op - OP_get_loc0;
        if (index >= caller->var_count) return NULL;
        source = sf->var_buf[index];
    } else if (op >= OP_get_arg0 && op <= OP_get_arg3) {
        index = op - OP_get_arg0;
        if (index >= caller->arg_count) return NULL;
        source = sf->arg_buf[index];
    } else if (op >= OP_get_var_ref0 && op <= OP_get_var_ref3) {
        index = op - OP_get_var_ref0;
        if (index >= caller->closure_var_count) return NULL;
        source = *JS_VALUE_GET_OBJ(sf->cur_func)->u.func.var_refs[index]->pvalue;
    } else if (op == OP_get_loc8) {
        if (pc == end || (index = *pc++) >= caller->var_count) return NULL;
        source = sf->var_buf[index];
    } else if (op == OP_get_loc || op == OP_get_loc_check || op == OP_get_arg ||
               op == OP_get_var_ref || op == OP_get_var_ref_check) {
        if (end - pc < 2) return NULL;
        index = get_u16(pc); pc += 2;
        if (op == OP_get_arg) {
            if (index >= caller->arg_count) return NULL;
            source = sf->arg_buf[index];
        } else if (op == OP_get_loc || op == OP_get_loc_check) {
            if (index >= caller->var_count) return NULL;
            source = sf->var_buf[index];
        } else {
            if (index >= caller->closure_var_count) return NULL;
            source = *JS_VALUE_GET_OBJ(sf->cur_func)->u.func.var_refs[index]->pvalue;
        }
    } else return NULL;
    if (end - pc < 6 || pc[0] != OP_append || pc[1] != OP_drop) return NULL;
    pc += 2;
    if (*pc == OP_perm3) { method = 1; pc++; }
    else if (end - pc >= 2 && pc[0] == OP_undefined && pc[1] == OP_swap) { method = 0; pc += 2; }
    else return NULL;
    if (end - pc < 3 || *pc != OP_apply || get_u16(pc + 1) != 0) return NULL;
    pc += 3;
    if (sp - sf->var_buf < caller->var_count + (method ? 2 : 1)) return NULL;
    callee = sp[-1];
    receiver = method ? sp[-2] : JS_UNDEFINED;
    if (!js_frame_varargs_dense(ctx, source)) return NULL;
    target = js_frame_target(callee);
    if (!target) return NULL;
    count = JS_VALUE_GET_OBJ(source)->u.array.count;
    need = FRAME_HEADER_BYTES + sizeof(JSValue) *
        (max_int((int)count, target->arg_count) + target->var_count + target->stack_size) + FRAME_CAPTURE_BYTES(target);
    /* An allocating grow could run JS and invalidate a borrowed source.
       Preserve B's snapshot/order instead of carrying that pointer through it. */
    if (need > state->segment->capacity - state->segment->used ||
        js_check_stack_overflow(state->rt, need) || ctx->interrupt_counter <= 1)
        return NULL;
    /* Account for the original built-in iterator creation call's poll.
       Pending polls use the full protocol with its original operand cursor. */
    ctx->interrupt_counter--;
    source = js_dup(source);
    if (method) sp -= 2;
    else sp--;
    sp[0] = callee;
    sp[1] = receiver;
    sp[2] = source;
    sp += 3;
    state->sp = sp;
    frame->saved_sp = sp;
    sf->cur_sp = sp;
    sf->cur_pc = (uint8_t *)pc;
    *resume = (uint8_t *)pc;
    return target;
}
"""
HOOK = r"""    if (*pc == OP_array_from && ((unsigned char *)b)[FRAME_ITERATOR_OFFSET+2] == 1) {
        uint8_t *resume;
        JSFunctionBytecode *fused_target = JS_FrameVarargsTryFuse(state, &resume);
        if (fused_target) {
            sp = state->sp;
            pc = resume;
            frame->pending = 3;
            b = fused_target;
            func_obj = sp[-3];
            this_obj = sp[-2];
            incoming_argc = JS_VALUE_GET_OBJ(sp[-1])->u.array.count;
            incoming_argv = NULL;
            incoming_copy = 2;
            goto enter_frame;
        }
    }
"""


def fusion_call_text(text):
    lo = text.index("FRAME_CODE int JS_FrameVarargsSlow(")
    hi = text.index("\n}\n#undef CASE", lo) + 2
    body = text[lo:hi]
    needle = "    goto execute_opcode;\nenter_frame:"
    body = replace_one(body, needle, HOOK + needle)
    assertion = '_Static_assert(offsetof(JSFunctionBytecode,pc2line_len)+sizeof(int)<=FRAME_ITERATOR_OFFSET+2 && FRAME_ITERATOR_OFFSET+2<offsetof(JSFunctionBytecode,pc2line_buf), "fusion control uses measured bytecode padding");\n'
    return text[:lo] + assertion + HELPERS + body + text[hi:]


def checkpoint_text(source, build, text, skip=False):
    """Compose typed JS-next continuations with varargs/forward/GC slow semantics.

    The native opcode helpers already create ordinary JS-next checkpoints. Every
    slow operation below such a checkpoint must retain that protocol, including
    exceptions from append/apply and logical C frames. Reuse its exact next body;
    retain this superset's existing frame/ownership/exception cleanup elsewhere.
    """
    if skip:
        return text
    checkpoint = (
        _frame_generated_file(build, "quickjs-interpreter-iterator-checkpoint.c")
    ).read_text(encoding="utf-8")
    start = checkpoint.index("FRAME_CODE int JS_FrameIteratorCheckpointSlow(")
    begin = checkpoint.index("    CASE(OP_for_of_next):", start)
    end = checkpoint.index("    CASE(OP_iterator_close):", begin)
    body = checkpoint[begin:end]
    assert "FRAME_CHECKPOINT(frame)" in body
    body = body.replace("js_frame_iterator_checkpoint_admit(", "JS_FrameIteratorCheckpointAdmit(")
    # A completed value/done pair is an ordinary live operand window.
    needle = "                sp+=2;\n                goto dispatch;"
    assert body.count(needle) == 1
    body = body.replace(
        needle,
        "                sp+=2;\n                sf->cur_sp=sp;\n                goto dispatch;",
    )
    begin = text.index("    CASE(OP_for_of_next):")
    end = text.index("    CASE(OP_iterator_close):", begin)
    text = text[:begin] + body + text[end:]
    declaration = """
extern bool JS_FrameIteratorCheckpointAdmit(JSFrame *,JSValue *,int);
extern int JS_FrameIteratorCheckpointPush(JSFrameRegisterState *);
extern JSValue JS_FrameIteratorCheckpointValue(JSContext *,JSValue,int *);
extern int JS_FrameIteratorSlowNext(JSContext *,JSValue *,int);
"""
    signature = "FRAME_CODE int JS_FrameVarargsSlow(JSFrameRegisterState *state)"
    assert text.count(signature) == 1
    text = text.replace(signature, declaration + signature)
    # The flag is independent of cur_sp: ordinary GC-visible roots are never
    # interpreted as a next() continuation. The pending next operand owns its
    # cached iterator until this hook clears it, matching js_for_of_next.
    hook = """
    if (FRAME_CHECKPOINT(frame)) {
        JSValue *iterator_sp=sf->cur_sp;
        int iterator_offset=-3-sf->cur_pc[1];
        JSValue consumed=iterator_sp[iterator_offset];
        pc=sf->cur_pc+2;
        FRAME_CLEAR_CHECKPOINT(frame);
        assert(state->iterator_checkpoint_depth);
        state->iterator_checkpoint_depth--;
        iterator_sp[iterator_offset]=JS_UNDEFINED;
        state->frame=frame;state->sp=sp;state->pc=pc;
        frame->saved_sp=sp;sf->cur_sp=sp;
        JS_FreeValue(ctx,consumed);
    }
"""
    needle = "exception:\n    sf->cur_pc = pc;"
    assert text.count(needle) == 1
    text = text.replace(needle, "exception:\n" + hook + "    sf->cur_pc = pc;")
    needle = """    if (needs_backtrace(rt->current_exception) || JS_IsUndefined(ctx->error_back_trace))
        build_backtrace(ctx, rt->current_exception, JS_UNDEFINED, NULL, 0, 0, 0);"""
    assert text.count(needle) == 1
    text = text.replace(
        needle,
        """    if (needs_backtrace(rt->current_exception) || JS_IsUndefined(ctx->error_back_trace)) {
        JSFrame *trace_frame;
        for(trace_frame=frame;trace_frame;trace_frame=js_frame_parent(trace_frame))
            if(FRAME_CHECKPOINT(trace_frame))trace_frame->sf.cur_pc+=2;
        build_backtrace(ctx, rt->current_exception, JS_UNDEFINED, NULL, 0, 0, 0);
        for(trace_frame=frame;trace_frame;trace_frame=js_frame_parent(trace_frame))
            if(FRAME_CHECKPOINT(trace_frame))trace_frame->sf.cur_pc-=2;
    }""",
    )
    needle = "    unsigned op = *state->pc;"
    assert text.count(needle) == 1
    text = text.replace(
        needle,
        needle
        + """
    /* Keep all supported opcodes and this superset's complete ownership/GC
       cleanup while a next() call is paused, even in a non-varargs child. */
    if (state->iterator_checkpoint_depth)
        return JS_FrameVarargsSlow(state);""",
    )
    return text
