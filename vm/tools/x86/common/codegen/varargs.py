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
from c_source_match import replace_one
from x86.common.build_tools import find_objdump

"""Isolated append/apply coverage; inherited interpreter code is never rebuilt.

Compile the superset validator/one-step interpreter in a private TU. Existing
slow entry and cold validation operands select it; the old opcode tables and
native frame remain intact. Compiler unwind rows live in a separate RO packet.
"""
from pathlib import Path
import argparse, hashlib, importlib.util, json, re, shutil, struct, subprocess, time

CAPACITY = 393216  # Exact combined unwind table storage, not executable padding.
MAGIC = b"QJSVA_UNWIND_v1!"
FOOTER = b"QJSVA_END_v1!!!!"
PREFIX = ".qjvfn$"
GROUP = ".qjzzvf"
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()


def module(source, name):
    spec = importlib.util.spec_from_file_location(
        "varargs_" + name.replace("-", "_"), _frame_tool_path(name + ".py")
    )
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def msvc_build(build):
    rows = json.loads((_frame_build_file(build, "compile_commands.json")).read_text())
    command = next(x["command"] for x in rows if Path(x["file"]).name == "quickjs-interpreter.c")
    return (
        Path(module(Path(__file__).resolve().parents[4], "atod").win_argv(command)[0]).name.lower()
        == "cl.exe"
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


# Research template copied verbatim into the new candidate's private generator.
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


"""Fuse a proven single-spread bytecode sequence into the existing owned child.

The successful path has no allocating/user-code operation before the copy.
Capacity/guard failures leave PC/SP/values untouched for the full B path.
"""
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


def checkpoint_text(source, build, text, msvc):
    """Compose typed JS-next continuations with varargs/forward/GC slow semantics.

    The GNU opcode helpers already create ordinary JS-next checkpoints. Every
    slow operation below such a checkpoint must retain that protocol, including
    exceptions from append/apply and logical C frames. Reuse its exact next body;
    retain this superset's existing frame/ownership/exception cleanup elsewhere.
    """
    if msvc:
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


def generate(source, build, target, msvc):
    C = module(source, "object-adapter")
    iterator = module(source, "iterator")
    directory = _frame_generated_file(build, "varargs-generation") / str(time.time_ns())
    directory.mkdir(parents=True)
    core = _frame_build_file(build, "CMakeFiles/qjs-core.dir/quickjs.c.obj")
    copy_core = directory / "CMakeFiles/qjs-core.dir/quickjs.c.obj"
    copy_core.parent.mkdir(parents=True)
    original = core.read_bytes()
    shutil.copy2(core, copy_core)
    old_bodies = iterator.bodies
    inherited_ops = iterator.OPS
    iterator.OPS = ("append", "apply") if msvc else (*inherited_ops, "append", "apply")

    def bodies(src):
        result, loop = old_bodies(src)
        result.update(core_bodies(src))
        return result, loop

    iterator.bodies = bodies
    old_module = iterator.module

    def fusion_module(src, name):
        result = old_module(src, name)
        if name == "object-adapter":
            generate_header = result.generate
            result.generate = lambda src, coff, backend: generate_header(
                src, coff, backend + DEPENDENCIES
            )
        return result

    iterator.module = fusion_module
    temporary = directory / "generated.c"
    iterator.generate(
        source, directory, temporary, native_instanceof=iterator.native_instanceof_enabled(build)
    )

    if not msvc:
        # These are the exact original core function identities, not copied
        # helpers. A typed inline RIP-relative LEA avoids GCC .refptr cells
        # whose DIR64 fixups GNU PE cannot place after its .reloc section.
        header_path = _frame_generated_file(directory, "quickjs-iterator-private.h")
        header = header_path.read_text(encoding="utf-8")
        address_loads = []
        # __builtin_frame_address forces an early RBP frame in GCC13.1. Its
        # subsequent nonvolatile XMM saves use RSP-relative native CFI offsets,
        # which the actual Windows unwinder cannot restore from that RBP base.
        # The private island reads the real RSP directly instead. This is a
        # conservative native stack-limit check and needs no interpreter-address
        # builtin. Core helpers and all inherited code/metadata stay unchanged.
        needle = "    return (uintptr_t)__builtin_frame_address(0);"
        assert header.count(needle) == 1
        header = header.replace(
            needle,
            "    uintptr_t current_sp;\n"
            '    __asm__ __volatile__("mov %%rsp, %0" : "=r"(current_sp));\n'
            "    return current_sp;",
        )

        for raw_name, suffix in (
            ("js_array_iterator_next", "ArrayNext"),
            ("js_create_array_iterator", "ArrayCreate"),
            ("js_function_call", "FunctionCall"),
        ):
            core_name = "qjs_frame_core_" + raw_name
            address_name = "JS_FrameVarargsAddress" + suffix
            needle = "#define " + raw_name + " " + core_name

            # The original alias macro precedes its extern declaration.
            # Canonicalize that declaration before replacing the alias with
            # an expression, then declare the same exact type before LEA.
            match = re.search(r"(?m)^extern [^\n]*\b" + re.escape(raw_name) + r"\([^;]*;", header)
            assert match, ("Exact exported helper prototype missing", raw_name)
            prototype = match[0].replace(raw_name + "(", core_name + "(", 1)
            header = header[: match.start()] + prototype + header[match.end() :]
            assert header.count(needle) == 1, (raw_name, header.count(needle))
            replacement = (
                prototype
                + "\n"
                + "\n".join(
                    [
                        "static __inline__ __attribute__((always_inline))",
                        "__typeof__(&" + core_name + ") " + address_name + "(void)",
                        "{",
                        "    __typeof__(&" + core_name + ") address;",
                        '    __asm__("lea %c1(%%rip), %0" : "=r"(address) : "i"(&'
                        + core_name
                        + "));",
                        "    return address;",
                        "}",
                        "#define " + raw_name + " (*" + address_name + "())",
                    ]
                )
            )
            header = header.replace(needle, replacement)
            address_loads.append(
                dict(
                    core_function=core_name,
                    helper=address_name,
                    form="typed inline RIP-relative LEA",
                )
            )
        header_path.write_text(header, encoding="utf-8")
        (directory / "function-address-loads.json").write_text(
            json.dumps(
                dict(status="passed", loads=address_loads, header_sha256=sha(header_path)), indent=2
            )
            + "\n"
        )
    adapted = copy_core.read_bytes()
    before, after = C.Coff(original), C.Coff(adapted)
    assert before.sections == after.sections, "Only new static aliases may affect the core object"
    for index, symbol in before.all_symbols.items():
        assert after.all_symbols[index] == symbol
    snapshot = directory / "core-before-varargs-aliases.obj"
    snapshot.write_bytes(original)
    core.write_bytes(adapted)
    text = temporary.read_text(encoding="utf-8")
    # This tiny public core function is normally inlined/dead in the MS
    # parent. Referencing it from the exception loop retained 28 new bytes
    # in the old .text. Copy the exact implementation into this TU instead.
    core_text = _frame_source_file(source, "quickjs.c").read_text(encoding="utf-8")
    at = core_text.index("bool JS_IsUncatchableError(")
    brace = core_text.index("{", at)
    end = brace + 1
    depth = 1
    while depth:
        depth += (core_text[end] == "{") - (core_text[end] == "}")
        end += 1
    copied = core_text[at:end].replace("JS_IsUncatchableError(", "JS_FrameVarargsIsUncatchable(")
    qualifier = '#ifdef _MSC_VER\n__declspec(code_seg(".qjzzva")) __declspec(noinline)\n#else\n__attribute__((section(".qjzzva"),noipa))\n#endif\n'
    first_line, rest = text.split("\n", 1)
    assert first_line.startswith("#include ")
    text = (
        "#define JS_IsUncatchableError JS_FrameVarargsIsUncatchable\n"
        + first_line
        + "\n"
        + qualifier
        + copied
        + "\n"
        + rest
    )
    text = text.replace("JS_FrameIterator", "JS_FrameVarargs")
    text = text.replace("JS_FrameValidateNativeNull", "JS_FrameVarargsOldValidate")

    if not msvc:
        # GNU binds OldValidate to the raw iterator validator, which publishes
        # captured kind5 without the post-classification used by NativeNull.
        # Qualify this successful edge too; the inherited validator stays exact.
        old = "    if (JS_FrameVarargsOldValidate(b)) return true;"
        assert text.count(old) == 1
        text = text.replace(
            old,
            "    if (JS_FrameVarargsOldValidate(b)) {\n"
            "        JS_FrameCapturedReadonlyClassify(b);\n"
            "        return true;\n"
            "    }",
        )

    text = text.replace(
        "extern int JS_FrameInterpSlow(JSFrameRegisterState *state);",
        "extern int JS_FrameVarargsOldSlow(JSFrameRegisterState *state);",
    )
    start = text.index("FRAME_CODE int JS_FrameVarargsSlowSelect(")
    brace = text.index("{", start)
    depth, end = 1, brace + 1
    while depth:
        depth += (text[end] == "{") - (text[end] == "}")
        end += 1
    selector = """FRAME_CODE int JS_FrameVarargsSlowSelect(JSFrameRegisterState *state)
{
    JSFrame *f;
    unsigned op = *state->pc;
    if (op == OP_append || op == OP_apply)
        return JS_FrameVarargsSlow(state);
    for (f = state->frame; f; f = js_frame_parent(f))
        if ((((unsigned char *)f->bytecode)[offsetof(JSFunctionBytecode,byte_code_buf)-2] & 2) != 0)
            return JS_FrameVarargsSlow(state);
    return JS_FrameVarargsOldSlow(state);
}"""
    if not msvc:
        # The old GNU outer selector only knows its own byte22 marker.
        # Both its base and iterator branches must reach this new selector;
        # otherwise byte108-only functions fall back to a rejecting old VM.
        selector = selector.replace(
            "    return JS_FrameVarargsOldSlow(state);",
            "    for (f = state->frame; f; f = js_frame_parent(f))\n"
            "        if (((unsigned char *)f->bytecode)[offsetof(JSFunctionBytecode,byte_code_buf)-2])\n"
            "            return JS_FrameVarargsOldSlow(state);\n"
            "    return JS_FrameVarargsOldBaseSlow(state);",
        )
        text = text.replace(
            "extern int JS_FrameVarargsOldSlow(JSFrameRegisterState *state);",
            "extern int JS_FrameVarargsOldBaseSlow(JSFrameRegisterState *state);\n"
            "extern int JS_FrameVarargsOldSlow(JSFrameRegisterState *state);",
        )
        # The insertion above precedes the selector; recompute its bounds.
        start = text.index("FRAME_CODE int JS_FrameVarargsSlowSelect(")
        brace = text.index("{", start)
        depth, end = 1, brace + 1
        while depth:
            depth += (text[end] == "{") - (text[end] == "}")
            end += 1
    text = text[:start] + selector + text[end:]
    # Superset fallback is used only after the inherited validator rejects.
    # Successful old validation keeps exactly its old metadata bytes.
    needle = "    FRAME_ITERATOR_KIND(b) = extended;"
    assert text.count(needle) == 1
    text = text.replace(
        needle,
        """    if (extended) {
        bool varargs = false;
        for (int p = 0; p < b->byte_code_len; p += js_frame_opcode_sizes[b->byte_code_buf[p]])
            if (b->byte_code_buf[p] == OP_append || b->byte_code_buf[p] == OP_apply)
                varargs = true;
        if (varargs && getenv("QJS_DISABLE_FRAME_VARARGS")) return false;
        if (varargs) ((unsigned char *)b)[FRAME_ITERATOR_OFFSET+1] = getenv("QJS_DISABLE_FRAME_VARARGS_DIRECT") ? 2 : 1;
        if (varargs) ((unsigned char *)b)[FRAME_ITERATOR_OFFSET+2] = getenv("QJS_DISABLE_FRAME_VARARGS_FUSION") ? 2 : 1;
        FRAME_ITERATOR_KIND(b) = varargs ? 3 : 1;
    } else FRAME_ITERATOR_KIND(b) = 0;""",
    )
    # Iterator generation has its own isolated build context and generated root.
    relative = _frame_generated_file(directory, "").relative_to(build).as_posix()
    text = text.replace(
        '#include "quickjs-iterator-private.h"',
        '#include "' + relative + '/quickjs-iterator-private.h"',
    )
    text = text.replace(
        '#include "quickjs-interpreter-iterator-dispatch.h"',
        '#include "' + relative + '/quickjs-interpreter-iterator-dispatch.h"',
    )
    text = text.replace(".qjsiter", ".qjzzva")

    # Byte22 is owned by the inherited leaf classifier (3 means return-arg).
    # Its reuse made a warmed recursive spread function return its first
    # argument inside an iterator callback. Use verified bytecode padding
    # after pc2line_len instead; never alter byte22 or any core field.
    marker = "#define FRAME_ITERATOR_KIND(b) (((unsigned char *)(b))[offsetof(JSFunctionBytecode,byte_code_buf)-2])"
    assert text.count(marker) == 1
    text = text.replace(
        marker,
        "#define FRAME_ITERATOR_OFFSET (offsetof(JSFunctionBytecode,pc2line_len)+sizeof(((JSFunctionBytecode *)0)->pc2line_len))\n"
        "#define FRAME_ITERATOR_KIND(b) (((unsigned char *)(b))[FRAME_ITERATOR_OFFSET])\n"
        "_Static_assert(offsetof(JSFunctionBytecode,pc2line_len)==QJS_ABI_OFF_JSFunctionBytecode_pc2line_len &&\n"
        "               offsetof(JSFunctionBytecode,pc2line_buf)==QJS_ABI_OFF_JSFunctionBytecode_pc2line_buf,\n"
        '               "varargs marker uses measured bytecode tail padding");',
    )
    text = text.replace(
        "iterator kind uses measured bytecode padding", "inherited bytecode prefix layout"
    )
    assert (
        text.count(
            "(((unsigned char *)f->bytecode)[offsetof(JSFunctionBytecode,byte_code_buf)-2] & 2)"
        )
        == 1
    )
    text = text.replace(
        "(((unsigned char *)f->bytecode)[offsetof(JSFunctionBytecode,byte_code_buf)-2] & 2)",
        "(((unsigned char *)f->bytecode)[FRAME_ITERATOR_OFFSET] & 2)",
    )

    # Keep all still-live slots visible during exception/finalizer cleanup.
    # Only this new private semantic unit changes; the core/old slow unit
    # and native register frame retain their exact original bytes/layout.
    needle = "            JSValue val = *--sp;\n            JS_FreeValue(ctx, val);"
    assert text.count(needle) == 1
    text = text.replace(
        needle,
        "            JSValue val = *--sp;\n"
        "            *sp = JS_UNDEFINED;\n"
        "            state->sp = sp; frame->saved_sp = sp; sf->cur_sp = sp;\n"
        "            JS_FreeValue(ctx, val);",
    )
    needle = "                    JS_FreeValue(ctx, sp[-1]); /* drop the next method */\n                    sp--;"
    assert text.count(needle) == 1
    text = text.replace(
        needle,
        "                    JSValue consumed = *--sp;\n"
        "                    *sp = JS_UNDEFINED;\n"
        "                    state->sp = sp; frame->saved_sp = sp; sf->cur_sp = sp;\n"
        "                    JS_FreeValue(ctx, consumed);",
    )
    needle = "                    rt->current_exception = JS_UNINITIALIZED;\n                    JS_FreeValueRT(rt, ctx->error_back_trace);"
    assert text.count(needle) == 1
    text = text.replace(
        needle,
        "                    rt->current_exception = JS_UNINITIALIZED;\n"
        "                    state->sp = sp; frame->saved_sp = sp; sf->cur_sp = sp;\n"
        "                    JS_FreeValueRT(rt, ctx->error_back_trace);",
    )
    needle = "    for (pval = local_buf; pval < sp; pval++)\n        JS_FreeValue(ctx, *pval);"
    assert text.count(needle) == 1
    text = text.replace(
        needle,
        "    for (pval = local_buf; pval < sp; pval++) {\n"
        "        JSValue consumed = *pval;\n"
        "        *pval = JS_UNDEFINED;\n"
        "        JS_FreeValue(ctx, consumed);\n"
        "    }",
    )
    text = direct_call_text(text)
    text = fusion_call_text(text)
    text = module(source, "call-forward").transform(text)
    text = checkpoint_text(source, build, text, msvc)
    text = module(source, "set-name").transform(source, text)
    text = module(source, "slow-observe").adapt_source(source, build, text)
    # Extend only the final superset. Iterator/checkpoint/literal generation
    # and every short-validator metadata transform above retain their order.
    # Derive one private long function after those transformations complete.
    signature = "FRAME_CODE bool JS_FrameVarargsValidate(JSFunctionBytecode *b)"
    if text.count(signature) != 1:
        raise ValueError("Review complete validator")
    begin = text.index(signature)
    brace = text.index("{", begin)
    end = brace + 1
    depth = 1
    while depth:
        depth += (text[end] == "{") - (text[end] == "}")
        end += 1
    large = text[begin:end]
    changes = [
        (signature, "static FRAME_LARGE_CODE bool JS_FrameLongValidate(JSFunctionBytecode *b)"),
        ("uint8_t boundaries[(4096 + 7) / 8]", "uint8_t boundaries[FRAME_LARGE_BITMAP_BYTES]"),
        ("b->byte_code_len > 4096", "b->byte_code_len > FRAME_LARGE_CODE_MAX"),
        ("int pos, size, op, index, target;", "int pos, size, op, index; int64_t target;"),
        ("target = pos + 1 +", "target = (int64_t)pos + 1 +"),
    ]
    for old, new in changes:
        if large.count(old) != (3 if old.startswith("target =") else 1):
            raise ValueError("Review large validator anchor: " + old)
        large = large.replace(old, new)
    # Compose existing regexp execution with the existing large-code cohort.
    # Keep the old short validator, C opcode executor and handler tables intact.
    regexp_anchor = "#undef FRAME_OP\n            break;\n"
    if large.count(regexp_anchor) != 1 or "case OP_regexp:" in large:
        raise ValueError("Review long regexp admission source")
    large = large.replace(
        regexp_anchor,
        regexp_anchor
        + """        case OP_regexp:
            /* The complete existing native regexp opcode needs a register
               frame. Only the existing guarded long-code cohort is extended.
               Keep OFF/unknown inputs on their original admission path. */
            if (getenv("QJS_DISABLE_FRAME_LONG_REGEXP") != NULL ||
                getenv("QJS_DISABLE_FRAME_REGEXP") != NULL ||
                !js_frame_register_enabled(b->realm->rt))
                return false;
            break;
""",
    )
    selector = "FRAME_CODE bool JS_FrameVarargsValidateSelect(JSFunctionBytecode *b)\n{"
    if text.count(selector) != 1:
        raise ValueError("Review native selector")
    # Resolved Symbol branch fusion needs the existing large-code cohort.
    # GNU enables it with the same PIC/release guard as that worker. Preserve
    # MSVC's inherited default and all explicit disable/opt-in controls.
    diagnostic = re.search(
        r"(?m)^QJS_INTERP_FRAME_DIAGNOSTICS:BOOL=(\w+)$",
        (build / "CMakeCache.txt").read_text(encoding="utf-8"),
    )
    if not diagnostic or diagnostic[1].upper() not in {
        "ON",
        "TRUE",
        "YES",
        "1",
        "OFF",
        "FALSE",
        "NO",
        "0",
    }:
        raise ValueError("Review native diagnostic policy")
    large_default = msvc or (
        module(source, "property_ic_native").enabled(build)
        and diagnostic[1].upper() in {"OFF", "FALSE", "NO", "0"}
    )
    policy = "#define FRAME_LARGE_CODE_DEFAULT " + str(int(large_default)) + "\n"
    text = text.replace(
        selector, policy + '#include "src/common/call/large-code-policy.inc"\n' + selector
    )
    old = "    if (!JS_FrameVarargsValidate(b)) return false;"
    if text.count(old) != 1:
        raise ValueError("Review native slow admission")
    text = text.replace(
        old, "    if (!JS_FrameVarargsValidate(b) && !js_frame_large_select(b)) return false;"
    )
    text += "\n" + large + "\n"
    text = module(source, "construct-continuation").transform(source, text, module)
    target.write_text(text, encoding="utf-8")
    (directory / "generation.json").write_text(
        json.dumps(
            dict(
                status="passed",
                original_core_sha256=hashlib.sha256(original).hexdigest(),
                adapted_core_sha256=sha(core),
                core_sections_and_original_symbols_identical=True,
                msvc=msvc,
                opcodes=list(iterator.OPS),
                root_safe_bodies={
                    k: hashlib.sha256(v.encode()).hexdigest()
                    for k, v in core_bodies(source).items()
                },
                source_sha256=sha(target),
            ),
            indent=2,
        )
        + "\n"
    )


def compile_extra(source, build):
    M = module(source, "atod")
    msvc = msvc_build(build)
    output = _frame_generated_file(build, "quickjs-interpreter-varargs-c.obj")
    M.compile_extra(
        source,
        build,
        output,
        generator=lambda src, p: generate(src, build, p, msvc),
        filename="quickjs-interpreter-varargs.c",
        late_name=".qjzzva",
    )
    module(source, "slow-observe").normalize_object(source, build, output)
    if not msvc:
        Ccheck = module(source, "object-adapter")
        check = Ccheck.Coff(output.read_bytes())
        for number, rec in enumerate(check.section_records, 1):
            if not rec["flags"] & 0x20000000:
                continue
            for j in range(rec["count"]):
                off, index, kind = struct.unpack_from("<IIH", check.data, rec["reloc"] + 10 * j)
                assert kind != 1, (
                    "Allocated varargs section cannot depend on absolute 64-bit pointers",
                    number,
                    off,
                    check.all_symbols[index],
                )
    # Merged MSVC string COMDATs must not reuse an existing carrier's
    # external names. Preserve section bytes and symbol indexes, as the
    # inherited metadata producer already does for its private C unit.
    C = module(source, "object-adapter")
    original_object = output.read_bytes()
    private = C.Coff(original_object)
    renamed = []
    common_dependencies = []
    for index, symbol in private.all_symbols.items():
        if symbol["section"] == 0 and symbol["storage"] == 2 and symbol["value"]:
            providers = []
            for candidate in (
                _frame_build_file(build, "CMakeFiles/qjs-core.dir/quickjs.c.obj"),
                _frame_build_file(
                    build, "CMakeFiles/qjs.dir/src/x86/win64/common/quickjs-interpreter.c.obj"
                ),
            ):
                old = C.Coff(candidate.read_bytes())
                if any(
                    v["name"] == symbol["name"]
                    and v["storage"] == 2
                    and (v["section"] > 0 or (v["section"] == 0 and v["value"] >= symbol["value"]))
                    for v in old.all_symbols.values()
                ):
                    providers.append(str(candidate))
            assert providers, ("Common storage needs an existing provider", symbol)
            struct.pack_into("<I", private.data, private.table + index * private.stride + 8, 0)
            common_dependencies.append(
                dict(name=symbol["name"], bytes=symbol["value"], providers=providers)
            )
    for index, symbol in private.all_symbols.items():
        if (
            symbol["section"] > 0
            and symbol["storage"] == 2
            and not symbol["name"].startswith("JS_FrameVarargs")
        ):
            name = "varargs_emitted_" + hashlib.sha256(symbol["name"].encode()).hexdigest()[:32]
            at = len(private.strings)
            private.strings += name.encode() + b"\0"
            struct.pack_into("<II", private.data, private.table + index * private.stride, 0, at)
            renamed.append(dict(index=index, old=symbol["name"], new=name))
    backup = output.with_name(output.name + ".unrenamed")
    assert not backup.exists()
    backup.write_bytes(original_object)
    output.write_bytes(private.finish())
    assert C.Coff(original_object).sections == C.Coff(output.read_bytes()).sections
    output.with_name(output.name + ".private-symbols.json").write_text(
        json.dumps(
            dict(
                status="passed",
                original=str(backup),
                original_sha256=sha(backup),
                output_sha256=sha(output),
                renamed=renamed,
                common_dependencies=common_dependencies,
                all_section_payloads_and_relocations_identical=True,
            ),
            indent=2,
        )
        + "\n"
    )
    compiler = Path(
        M.win_argv(
            next(
                x["command"]
                for x in json.loads((_frame_build_file(build, "compile_commands.json")).read_text())
                if Path(x["file"]).name == "quickjs-interpreter.c"
            )
        )[0]
    )
    module(source, "call-forward").compile_asm(source, build, compiler, msvc)
    diagnostics = "QJS_INTERP_FRAME_DIAGNOSTICS" in next(
        x["command"]
        for x in json.loads((_frame_build_file(build, "compile_commands.json")).read_text())
        if Path(x["file"]).name == "quickjs-interpreter.c"
    )
    module(source, "array-append").compile_extra(source, build, compiler, msvc, diagnostics)
    module(source, "slow-direct").compile_extra(source, build, msvc)
    module(source, "length").compile_extra(source, build, msvc)
    module(source, "proto-direct").compile_extra(source, build, msvc)
    module(source, "own-bytecode").compile_extra(source, build, msvc)
    module(source, "cvm_segments").compile_isolated(source, build, msvc)
    obj = _frame_generated_file(build, "quickjs-interpreter-varargs-packet.obj")
    if msvc:
        asm = _frame_generated_file(build, "quickjs-interpreter-varargs-packet.asm")
        text = [
            "OPTION CASEMAP:NONE",
            "OPTION DOTNAME",
            ".qjzzva SEGMENT ALIGN(16) READONLY 'CODE'",
            "PUBLIC JS_FrameVarargsPacket, JS_FrameVarargsPacket_end",
            "JS_FrameVarargsPacket PROC",
            "lea rax, JS_FrameVarargsHeader",
            "ret",
            "JS_FrameVarargsPacket_end LABEL BYTE",
            "JS_FrameVarargsPacket ENDP",
            "ALIGN 4",
            "JS_FrameVarargsPacketUnwind LABEL BYTE",
            "DB 1,0,0,0",
            ".qjzzva ENDS",
            ".pdata$zzzzzznullfast SEGMENT ALIGN(4) READONLY 'DATA'",
            "DD IMAGEREL JS_FrameVarargsPacket, IMAGEREL JS_FrameVarargsPacket_end, IMAGEREL JS_FrameVarargsPacketUnwind",
            ".pdata$zzzzzznullfast ENDS",
            ".qjvfn$0 SEGMENT ALIGN(4) READONLY 'CODE'",
            "JS_FrameVarargsHeader LABEL BYTE",
            'DB "' + MAGIC.decode() + '"',
            "DD 0,1",
            "DQ 0",
            ".qjvfn$0 ENDS",
            ".qjvfn$3 SEGMENT ALIGN(4) READONLY 'CODE'",
            'DB "' + FOOTER.decode() + '"',
            "DD " + str(CAPACITY) + ",1",
            "DB " + str(CAPACITY) + " DUP(0)",
            ".qjvfn$3 ENDS",
            "END",
        ]
        command = [str(compiler.with_name("ml64.exe")), "/nologo", "/c", "/Fo" + str(obj), str(asm)]
    else:
        asm = _frame_generated_file(build, "quickjs-interpreter-varargs-packet.S")
        text = [
            ".intel_syntax noprefix",
            '.section .qjzzva,"xr"',
            ".p2align 4",
            ".globl JS_FrameVarargsPacket, JS_FrameVarargsPacket_end",
            ".def JS_FrameVarargsPacket; .scl 2; .type 32; .endef",
            "JS_FrameVarargsPacket:",
            "lea rax, [rip+JS_FrameVarargsHeader]",
            "ret",
            "JS_FrameVarargsPacket_end:",
            ".p2align 2",
            "JS_FrameVarargsPacketUnwind:",
            ".byte 1,0,0,0",
            '.section .pdata$zzzzzznullfast,"dr"',
            ".rva JS_FrameVarargsPacket,JS_FrameVarargsPacket_end,JS_FrameVarargsPacketUnwind",
            '.section .qjvfn$0,"xr"',
            ".p2align 2",
            "JS_FrameVarargsHeader:",
            '.ascii "' + MAGIC.decode() + '"',
            ".long 0,1",
            ".quad 0",
            '.section .qjvfn$3,"xr"',
            '.ascii "' + FOOTER.decode() + '"',
            ".long " + str(CAPACITY) + ",1",
            ".zero " + str(CAPACITY),
        ]
        command = [str(compiler), "-c", "-g0", str(asm), "-o", str(obj)]
    asm.write_text("\n".join(text) + "\n", encoding="ascii")
    p = subprocess.run(command, capture_output=True)
    obj.with_suffix(".log").write_bytes(p.stdout + p.stderr)
    assert p.returncode == 0, (p.stdout, p.stderr)
    (_frame_generated_file(build, "quickjs-varargs-generation.json")).write_text(
        json.dumps(
            dict(
                status="passed",
                c_object=str(output),
                c_object_sha256=sha(output),
                packet_object=str(obj),
                packet_object_sha256=sha(obj),
                source_generator_sha256=sha(__file__),
                msvc=msvc,
                frame_bytes=128,
                method="Separate C semantic island, inherited slow entry ABI, no opcode table/native frame changes.",
            ),
            indent=2,
        )
        + "\n"
    )


def targets(msvc):
    if msvc:
        return {
            "JS_FrameValidateNativeNull": "JS_FrameVarargsValidateSelect",
            "JS_FrameInterpSlow": "JS_FrameVarargsArraySlowSelect",
        }
    return {
        "JS_FrameIteratorValidate": "JS_FrameVarargsValidateSelect",
        "JS_FrameIteratorSlowSelect": "JS_FrameVarargsArraySlowSelect",
        "JS_FrameIteratorSlow": "JS_FrameVarargsArraySlowSelect",
        "JS_FrameInterpSlow": "JS_FrameVarargsArraySlowSelect",
    }


def applicable(coff, msvc):
    return any(s["name"] in targets(msvc) for s in coff.all_symbols.values()) or module(
        Path(__file__).resolve().parents[4], "call-forward"
    ).applicable(coff)


def adapt(source, build, path, raw, msvc):
    C = module(source, "object-adapter")
    merge = module(source, "extension-merge")
    before_raw, _ = module(source, "call-metadata").packed(raw, C)
    coff = C.Coff(before_raw)
    aliases = []
    for old, new in targets(msvc).items():
        defined = [s for s in coff.all_symbols.values() if s["name"] == old and s["section"] > 0]
        if not defined:
            continue
        assert len(defined) == 1
        s = defined[0]
        name = (
            "JS_FrameVarargsOldValidate"
            if "Validate" in old
            else "JS_FrameVarargsOldBaseSlow"
            if old == "JS_FrameInterpSlow" and not msvc
            else "JS_FrameVarargsOldSelector"
            if old == "JS_FrameIteratorSlowSelect"
            else "JS_FrameVarargsOldSlow"
        )
        at = len(coff.strings)
        coff.strings += name.encode() + b"\0"
        entry = bytearray(coff.stride)
        struct.pack_into("<III", entry, 0, 0, at, s["value"])
        struct.pack_into("<i" if coff.stride == 20 else "<h", entry, 12, s["section"])
        struct.pack_into("<H", entry, 16 if coff.stride == 20 else 14, 32)
        entry[coff.class_offset] = 2
        coff.aliases.append(entry)
        aliases.append(name)
    folder = _frame_generated_file(build, "varargs-link") / str(time.time_ns())
    folder.mkdir(parents=True)
    temp = folder / "route.obj"
    temp.write_bytes(coff.finish())
    objdump = find_objdump(build)
    module(source, "iterator").route(
        temp, source, objdump, targets=targets(msvc), label="varargs", conditional=True
    )
    result = temp.read_bytes()
    result, forward_record = module(source, "call-forward").adapt(source, build, path, result, msvc)
    result, js_captured_record = module(source, "js-captured").adapt(
        source, build, path, result, msvc
    )
    record = folder / "adapt.json"
    record.write_text(
        json.dumps(
            dict(
                status="passed",
                input=str(path),
                input_sha256=hashlib.sha256(raw).hexdigest(),
                output_sha256=hashlib.sha256(result).hexdigest(),
                aliases=aliases,
                route_record=str(temp) + ".varargs.json",
                forward_record=forward_record,
                js_captured_record=js_captured_record,
                no_opcode_table_or_frame_changes=True,
            ),
            indent=2,
        )
        + "\n"
    )
    return result, str(record)


def append_module(source, build, path, raw, msvc):
    C = module(source, "object-adapter")
    merge = module(source, "extension-merge")
    meta = module(source, "call-metadata")
    packed, _ = meta.packed(raw, C)
    old = C.Coff(packed)
    folder = _frame_generated_file(build, "varargs-link") / str(time.time_ns())
    folder.mkdir(parents=True)
    output = folder / "carrier.obj"
    output.write_bytes(packed)
    owner = "JS_FrameNativeCScopeVM" if msvc else "JS_RunFrame"
    code_group = ".qjs$zzzzzzzzzzrvV" if msvc else ".qjzzva"
    packet_group = code_group if msvc else GROUP
    c_input = _frame_generated_file(build, "quickjs-interpreter-varargs-c.obj")
    merge.append(
        output,
        c_input,
        "JS_FrameVarargsSlow",
        "varargs-c",
        keep_all=True,
        code_input=".qjzzva",
        code_output=code_group if msvc else code_group + "$C",
        pdata_output=PREFIX + "1",
        metadata_inputs=(".voltbl",) if msvc else (),
        writable_metadata_inputs=(".qjsrmet",)
        + (
            (".qjvsom$C",)
            if json.loads(
                (
                    _frame_generated_file(build, "quickjs-interpreter-slow-observe-source.json")
                ).read_text()
            )["diagnostics"]
            else ()
        ),
        base_owner=owner,
        baseline_sections=(),
    )
    merge.append(
        output,
        _frame_generated_file(build, "quickjs-interpreter-call-forward.obj"),
        "JS_FrameCallForwardEnter",
        "call-forward-asm",
        keep_all=True,
        code_input=".qjzzva",
        code_output=code_group if msvc else code_group + "$B",
        pdata_output=PREFIX + "1",
        base_owner=owner,
        baseline_sections=(),
    )
    merge.append(
        output,
        _frame_generated_file(build, "quickjs-interpreter-varargs-packet.obj"),
        "JS_FrameVarargsPacket",
        "varargs-packet",
        keep_all=True,
        code_input=".qjzzva",
        code_output=code_group if msvc else code_group + "$A",
        pdata_output=PREFIX + "2",
        allocated_metadata_inputs=(PREFIX + "0", PREFIX + "3"),
        base_owner=owner,
        baseline_sections=(),
    )
    module(source, "call-forward-native").append_module(
        source, build, output, msvc, code_group, PREFIX, owner, merge
    )
    module(source, "call-forward-owned").append_module(
        source, build, output, msvc, code_group, PREFIX, owner, merge
    )
    module(source, "call-forward-borrow").append_module(
        source, build, output, msvc, code_group, PREFIX, owner, merge
    )
    module(source, "call-forward-owned").append_captured(
        source, build, output, msvc, code_group, PREFIX, owner, merge
    )
    module(source, "call-prepare").append_module(
        source, build, output, msvc, code_group, PREFIX, owner, merge
    )
    module(source, "array-append").append_module(
        source, build, output, msvc, code_group, PREFIX, owner, merge
    )
    module(source, "slow-direct").append_module(
        source, build, output, msvc, code_group, PREFIX, owner, merge
    )
    data = bytearray(output.read_bytes())
    co = C.Coff(data)
    for i, rec in enumerate(co.section_records, 1):
        if i <= old.count:
            continue
        if merge.section_name(co, i).startswith(".qjzzva") or (
            msvc and merge.section_name(co, i) == code_group
        ):
            struct.pack_into("<I", data, rec["pos"] + 36, (rec["flags"] & ~0xE0) | 0x60000040)
        if merge.section_name(co, i).startswith(PREFIX):
            struct.pack_into(
                "<I",
                data,
                rec["pos"] + 36,
                (rec["flags"] & ~0xE00000E0) | (0x60000040 if msvc else 0x40000040),
            )
    result, coalescing = meta.coalesce_native_packet(
        bytes(data),
        old.count,
        C,
        merge,
        prefix=PREFIX,
        group=packet_group,
        magic=MAGIC,
        footer_magic=FOOTER,
        capacity=CAPACITY,
    )
    output.write_bytes(result)
    module(source, "length").append_module(
        source, build, output, msvc, code_group, PREFIX, owner, merge
    )
    module(source, "proto-direct").append_module(
        source, build, output, msvc, code_group, PREFIX, owner, merge
    )
    module(source, "own-bytecode").append_module(
        source, build, output, msvc, code_group, PREFIX, owner, merge
    )
    module(source, "cvm_segments").append_isolated(
        source, build, output, msvc, code_group, PREFIX, owner, merge
    )
    result = output.read_bytes()
    record = folder / "append.json"
    record.write_text(
        json.dumps(
            dict(
                status="passed",
                input=str(path),
                input_sha256=hashlib.sha256(raw).hexdigest(),
                output_sha256=hashlib.sha256(result).hexdigest(),
                coalescing=coalescing,
                old_sections_unchanged=True,
                code_group=code_group,
                native_group=packet_group,
            ),
            indent=2,
        )
        + "\n"
    )
    return result, str(record)


def finalize_image(image, previous):
    raw = bytearray(image.read_bytes())
    pe = struct.unpack_from("<I", raw, 60)[0]
    opt = pe + 24
    start = opt + struct.unpack_from("<H", raw, pe + 20)[0]
    sections = []
    for i in range(struct.unpack_from("<H", raw, pe + 6)[0]):
        at = start + 40 * i
        name = raw[at : at + 8].split(b"\0")[0].decode("ascii")
        size, rva, physical_size, physical = struct.unpack_from("<IIII", raw, at + 8)
        sections.append(
            dict(
                name=name, size=size, rva=rva, physical_size=physical_size, physical=physical, at=at
            )
        )
    found = [s for s in sections if MAGIC in raw[s["physical"] : s["physical"] + s["size"]]]
    assert len(found) <= 1
    carrier = found[0] if found else None
    if not carrier:
        return previous
    data = raw[carrier["physical"] : carrier["physical"] + carrier["size"]]
    starts = [i for i in range(len(data)) if data.startswith(MAGIC, i)]
    ends = [i for i in range(len(data)) if data.startswith(FOOTER, i)]
    assert len(starts) == len(ends) == 1
    lo = starts[0] + 32
    hi = ends[0]
    assert hi > lo and (hi - lo) % 12 == 0
    native = [bytes(data[i : i + 12]) for i in range(lo, hi, 12)]
    assert all(any(r) for r in native)
    directory = opt + 112 + 3 * 8
    old_rva, old_size = struct.unpack_from("<II", raw, directory)
    s = next(
        s
        for s in sections
        if s["rva"] <= old_rva and old_rva + old_size <= s["rva"] + s["physical_size"]
    )
    old_at = s["physical"] + old_rva - s["rva"]
    inherited = bytes(raw[old_at : old_at + old_size])
    rows = sorted(
        set(inherited[i : i + 12] for i in range(0, len(inherited), 12)) | set(native),
        key=lambda r: struct.unpack_from("<I", r)[0],
    )
    previous_end = 0
    for r in rows:
        begin, end, uw = struct.unpack("<III", r)
        assert previous_end <= begin < end and uw > 0, (begin, end, previous_end)
        previous_end = end
        for address, size in ((begin, end - begin), (uw, 4)):
            assert any(
                s["rva"] <= address and address + size <= s["rva"] + s["physical_size"]
                for s in sections
            )
    table = b"".join(rows)
    cap, version = struct.unpack_from("<II", data, hi + 16)
    assert version == 1 and cap == CAPACITY and cap >= len(table)
    relative = hi + 24
    at = carrier["physical"] + relative
    assert relative + cap <= carrier["size"] and bytes(raw[at : at + cap]) in (
        bytes(cap),
        table + bytes(cap - len(table)),
    )
    raw[at : at + len(table)] = table
    struct.pack_into("<II", raw, directory, carrier["rva"] + relative, len(table))
    before = sha(image)
    if bytes(raw) != image.read_bytes():
        image.write_bytes(raw)
    return dict(
        status="passed",
        image=str(image),
        before_sha256=before,
        image_sha256=sha(image),
        inherited_finalization=previous,
        varargs_native_rows=len(native),
        combined_rows=len(rows),
        directory_rva=carrier["rva"] + relative,
        all_inherited_rows_retained=True,
        native_storage_readonly=not bool(
            struct.unpack_from("<I", raw, carrier["at"] + 36)[0] & 0x80000000
        ),
        policy="Only new RO directory storage and PE exception-directory pointer/size; all code/data/RVA/base/ASLR preserved.",
    )


_length_parent_finalize = finalize_image


def finalize_image(image, previous):
    extension = module(Path(__file__).resolve().parents[4], "length")
    extension.strip_native_before_parent(image)
    return extension.finalize_image(image, _length_parent_finalize(image, previous))


_proto_direct_parent_finalize = finalize_image


def finalize_image(image, previous):
    extension = module(Path(__file__).resolve().parents[4], "proto-direct")
    extension.strip_native_before_parent(image)
    return extension.finalize_image(image, _proto_direct_parent_finalize(image, previous))


_own_bytecode_parent_finalize = finalize_image


def finalize_image(image, previous):
    extension = module(Path(__file__).resolve().parents[4], "own-bytecode")
    extension.strip_native_before_parent(image)
    return extension.finalize_image(image, _own_bytecode_parent_finalize(image, previous))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", type=Path, required=True)
    ap.add_argument("--build", type=Path, required=True)
    ap.add_argument("--compile", action="store_true")
    a = ap.parse_args()
    assert a.compile
    compile_extra(a.source, a.build)
