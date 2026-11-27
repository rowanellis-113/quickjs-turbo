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
        (
            "set_name_computed",
            "int",
            "",
            "JS_DefineObjectNameComputed(ctx, sp[-1], sp[-2], JS_PROP_CONFIGURABLE)",
        ),
        (
            "set_proto",
            "int",
            ", JSValueConst proto",
            "JS_SetPrototypeInternal(ctx, sp[-2], proto, true)",
        ),
        (
            "copy_data_properties",
            "int",
            ", int mask",
            "JS_CopyDataProperties(ctx, sp[-1 - (mask & 3)], sp[-1 - ((mask >> 2) & 7)], sp[-1 - ((mask >> 5) & 7)], 0)",
        ),
        ("for_in_start", "int", "", "js_for_in_start(ctx, sp)"),
        ("for_in_next", "int", "", "js_for_in_next(ctx, sp)"),
        ("iter_get_val_done", "int", "", "js_iterator_get_value_done(ctx, sp)"),
        ("iter_next", "JSValue", "", "JS_Call(ctx, sp[-3], sp[-4], 1, vc(sp - 1))"),
        (
            "iter_call",
            "int",
            ", int flags, JSValue *out_ret",
            "js_linux_op_iterator_call(ctx, sp, flags, out_ret)",
        ),
        ("get_super", "JSValue", "", "JS_GetPrototype(ctx, sp[-1])"),
        ("get_super_value", "JSValue", "", "js_linux_op_get_super_value(ctx, sp)"),
        ("put_super_value", "int", "", "js_linux_op_put_super_value(ctx, sp)"),
        (
            "define_method",
            "int",
            ", JSAtom atom, int op_flags, bool is_computed",
            "js_linux_op_define_method(ctx, sp, atom, op_flags, is_computed)",
        ),
        (
            "define_class",
            "int",
            ", JSAtom atom, int class_flags, JSVarRef **cur_var_refs, JSStackFrame *cur_sf, bool is_computed",
            "js_op_define_class(ctx, sp, atom, class_flags, cur_var_refs, cur_sf, is_computed)",
        ),
    ]
    helper_defs = """static QJS_FRAME_SLOW_HOST_CODE int js_linux_op_iterator_call(
    JSContext *ctx, JSValue *sp, int flags, JSValue *out_ret)
{
    JSValue method = JS_GetProperty(ctx, sp[-4], (flags & 1) ? JS_ATOM_throw : JS_ATOM_return);
    if (JS_IsException(method))
        return -1;
    if (JS_IsUndefined(method) || JS_IsNull(method))
        return 1;
    JSValue ret = (flags & 2) ? JS_CallFree(ctx, method, sp[-4], 0, NULL)
                              : JS_CallFree(ctx, method, sp[-4], 1, vc(sp - 1));
    if (JS_IsException(ret))
        return -1;
    *out_ret = ret;
    return 0;
}

static QJS_FRAME_SLOW_HOST_CODE JSValue js_linux_op_get_super_value(JSContext *ctx, JSValue *sp)
{
    JSAtom atom = JS_ValueToAtom(ctx, sp[-1]);
    if (unlikely(atom == JS_ATOM_NULL))
        return JS_EXCEPTION;
    JSValue val = JS_GetPropertyInternal(ctx, sp[-2], atom, sp[-3], false);
    JS_FreeAtom(ctx, atom);
    return val;
}

static QJS_FRAME_SLOW_HOST_CODE int js_linux_op_put_super_value(JSContext *ctx, JSValue *sp)
{
    if (JS_VALUE_GET_TAG(sp[-3]) != JS_TAG_OBJECT) {
        JS_ThrowTypeErrorNotAnObject(ctx);
        return -1;
    }
    JSAtom atom = JS_ValueToAtom(ctx, sp[-2]);
    if (unlikely(atom == JS_ATOM_NULL))
        return -1;
    int ret = JS_SetPropertyInternal2(ctx, sp[-3], atom, js_dup(sp[-1]), sp[-4], JS_PROP_THROW_STRICT);
    JS_FreeAtom(ctx, atom);
    return ret;
}

static QJS_FRAME_SLOW_HOST_CODE int js_linux_op_define_method(
    JSContext *ctx, JSValue *sp, JSAtom atom, int op_flags, bool is_computed)
{
    int flags, ret;
    JSValue value = JS_UNDEFINED, getter = JS_UNDEFINED, setter = JS_UNDEFINED;
    if (is_computed) {
        atom = JS_ValueToAtom(ctx, sp[-2]);
        if (unlikely(atom == JS_ATOM_NULL))
            return -1;
    }
    flags = JS_PROP_HAS_CONFIGURABLE | JS_PROP_CONFIGURABLE | JS_PROP_HAS_ENUMERABLE | JS_PROP_THROW;
    if (op_flags & 4)
        flags |= JS_PROP_ENUMERABLE;
    if ((op_flags & 3) == 0) {
        value = sp[-1];
        flags |= JS_PROP_HAS_VALUE | JS_PROP_HAS_WRITABLE | JS_PROP_WRITABLE;
    } else if ((op_flags & 3) == 1) {
        getter = sp[-1];
        flags |= JS_PROP_HAS_GET;
    } else {
        setter = sp[-1];
        flags |= JS_PROP_HAS_SET;
    }
    ret = js_method_set_properties(ctx, sp[-1], atom, flags, sp[-2 - (int)is_computed]);
    if (ret >= 0)
        ret = JS_DefineProperty(ctx, sp[-2 - (int)is_computed], atom, value, getter, setter, flags);
    if (is_computed)
        JS_FreeAtom(ctx, atom);
    return ret;
}
"""
    declarations, definitions = [], [helper_defs]
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


EXTRA_LINUX_OPS = (
    "set_name_computed",
    "set_proto",
    "copy_data_properties",
    "for_in_start",
    "for_in_next",
    "iterator_get_value_done",
    "iterator_next",
    "iterator_call",
    "get_super",
    "get_super_value",
    "put_super_value",
    "set_home_object",
    "define_method",
    "define_method_computed",
    "define_class",
    "define_class_computed",
)


def extra_linux_bodies():
    return {
        "set_name_computed": """        CASE(OP_set_name_computed):
            {
                int ret;
                sf->cur_pc = pc;
                ret = JS_DefineObjectNameComputed(ctx, sp[-1], sp[-2], JS_PROP_CONFIGURABLE);
                if (unlikely(ret < 0))
                    goto exception;
            }
            BREAK;""",
        "set_proto": """        CASE(OP_set_proto):
            {
                JSValue proto;
                proto = sp[-1];
                if (JS_IsObject(proto) || JS_IsNull(proto)) {
                    sf->cur_pc = pc;
                    if (JS_SetPrototypeInternal(ctx, sp[-2], proto, true) < 0)
                        goto exception;
                }
                sp--;
                *sp = JS_UNDEFINED;
                state->sp = sp;
                frame->saved_sp = sp;
                sf->cur_sp = sp;
                JS_FreeValue(ctx, proto);
            }
            BREAK;""",
        "copy_data_properties": """        CASE(OP_copy_data_properties):
            {
                int mask;
                mask = *pc++;
                sf->cur_pc = pc;
                if (JS_CopyDataProperties(ctx, sp[-1 - (mask & 3)], sp[-1 - ((mask >> 2) & 7)], sp[-1 - ((mask >> 5) & 7)], 0))
                    goto exception;
            }
            BREAK;""",
        "for_in_start": """        CASE(OP_for_in_start):
            sf->cur_pc = pc;
            if (js_for_in_start(ctx, sp))
                goto exception;
            BREAK;""",
        "for_in_next": """        CASE(OP_for_in_next):
            sf->cur_pc = pc;
            if (js_for_in_next(ctx, sp))
                goto exception;
            sp += 2;
            BREAK;""",
        "iterator_get_value_done": """        CASE(OP_iterator_get_value_done):
            sf->cur_pc = pc;
            if (js_linux_construct_host_iter_get_val_done(state, frame, segment, used_bytes, pc, sp, ctx))
                goto exception;
            sp += 1;
            BREAK;""",
        "iterator_next": """        CASE(OP_iterator_next):
            {
                JSValue ret, prev;
                sf->cur_pc = pc;
                ret = js_linux_construct_host_iter_next(state, frame, segment, used_bytes, pc, sp, ctx);
                if (JS_IsException(ret))
                    goto exception;
                prev = sp[-1];
                sp[-1] = ret;
                state->sp = sp;
                frame->saved_sp = sp;
                sf->cur_sp = sp;
                JS_FreeValue(ctx, prev);
            }
            BREAK;""",
        "iterator_call": """        CASE(OP_iterator_call):
            {
                JSValue ret = JS_UNDEFINED, prev;
                int flags = *pc++;
                int rc;
                sf->cur_pc = pc;
                rc = js_linux_construct_host_iter_call(state, frame, segment, used_bytes, pc, sp, ctx, flags, &ret);
                if (rc < 0)
                    goto exception;
                if (rc == 0) {
                    prev = sp[-1];
                    sp[-1] = ret;
                    state->sp = sp;
                    frame->saved_sp = sp;
                    sf->cur_sp = sp;
                    JS_FreeValue(ctx, prev);
                }
                sp[0] = js_bool(rc != 0);
                sp += 1;
            }
            BREAK;""",
        "get_super": """        CASE(OP_get_super):
            {
                JSValue proto, prev;
                sf->cur_pc = pc;
                proto = js_linux_construct_host_get_super(state, frame, segment, used_bytes, pc, sp, ctx);
                if (JS_IsException(proto))
                    goto exception;
                prev = sp[-1];
                sp[-1] = proto;
                state->sp = sp;
                frame->saved_sp = sp;
                sf->cur_sp = sp;
                JS_FreeValue(ctx, prev);
            }
            BREAK;""",
        "get_super_value": """        CASE(OP_get_super_value):
            {
                JSValue val, v1, v2, v3;
                sf->cur_pc = pc;
                val = js_linux_construct_host_get_super_value(state, frame, segment, used_bytes, pc, sp, ctx);
                if (unlikely(JS_IsException(val)))
                    goto exception;
                v1 = sp[-1];
                v2 = sp[-2];
                v3 = sp[-3];
                sp[-3] = val;
                sp[-2] = JS_UNDEFINED;
                sp[-1] = JS_UNDEFINED;
                sp -= 2;
                state->sp = sp;
                frame->saved_sp = sp;
                sf->cur_sp = sp;
                JS_FreeValue(ctx, v1);
                JS_FreeValue(ctx, v2);
                JS_FreeValue(ctx, v3);
            }
            BREAK;""",
        "put_super_value": """        CASE(OP_put_super_value):
            {
                JSValue v1, v2, v3, v4;
                int ret;
                sf->cur_pc = pc;
                ret = js_linux_construct_host_put_super_value(state, frame, segment, used_bytes, pc, sp, ctx);
                v1 = sp[-1];
                v2 = sp[-2];
                v3 = sp[-3];
                v4 = sp[-4];
                sp[-4] = JS_UNDEFINED;
                sp[-3] = JS_UNDEFINED;
                sp[-2] = JS_UNDEFINED;
                sp[-1] = JS_UNDEFINED;
                sp -= 4;
                state->sp = sp;
                frame->saved_sp = sp;
                sf->cur_sp = sp;
                JS_FreeValue(ctx, v1);
                JS_FreeValue(ctx, v2);
                JS_FreeValue(ctx, v3);
                JS_FreeValue(ctx, v4);
                if (unlikely(ret < 0))
                    goto exception;
            }
            BREAK;""",
        "set_home_object": """        CASE(OP_set_home_object):
            js_method_set_home_object(ctx, sp[-1], sp[-2]);
            BREAK;""",
        "define_method": """        CASE(OP_define_method):
            {
                JSAtom atom = get_u32(pc);
                int op_flags = pc[4];
                JSValue fn_val;
                int ret;
                pc += 5;
                sf->cur_pc = pc;
                ret = js_linux_construct_host_define_method(state, frame, segment, used_bytes, pc, sp, ctx, atom, op_flags, false);
                fn_val = sp[-1];
                sp[-1] = JS_UNDEFINED;
                sp -= 1;
                state->sp = sp;
                frame->saved_sp = sp;
                sf->cur_sp = sp;
                JS_FreeValue(ctx, fn_val);
                if (unlikely(ret < 0))
                    goto exception;
            }
            BREAK;""",
        "define_method_computed": """        CASE(OP_define_method_computed):
            {
                int op_flags = *pc++;
                JSValue fn_val, key_val;
                int ret;
                sf->cur_pc = pc;
                ret = js_linux_construct_host_define_method(state, frame, segment, used_bytes, pc, sp, ctx, JS_ATOM_NULL, op_flags, true);
                fn_val = sp[-1];
                key_val = sp[-2];
                sp[-2] = JS_UNDEFINED;
                sp[-1] = JS_UNDEFINED;
                sp -= 2;
                state->sp = sp;
                frame->saved_sp = sp;
                sf->cur_sp = sp;
                JS_FreeValue(ctx, fn_val);
                JS_FreeValue(ctx, key_val);
                if (unlikely(ret < 0))
                    goto exception;
            }
            BREAK;""",
        "define_class": """        CASE(OP_define_class):
            {
                JSAtom atom = get_u32(pc);
                int class_flags = pc[4];
                pc += 5;
                sf->cur_pc = pc;
                if (js_linux_construct_host_define_class(state, frame, segment, used_bytes, pc, sp, ctx, atom, class_flags, JS_VALUE_GET_OBJ(sf->cur_func)->u.func.var_refs, sf, false) < 0)
                    goto exception;
            }
            BREAK;""",
        "define_class_computed": """        CASE(OP_define_class_computed):
            {
                JSAtom atom = get_u32(pc);
                int class_flags = pc[4];
                pc += 5;
                sf->cur_pc = pc;
                if (js_linux_construct_host_define_class(state, frame, segment, used_bytes, pc, sp, ctx, atom, class_flags, JS_VALUE_GET_OBJ(sf->cur_func)->u.func.var_refs, sf, true) < 0)
                    goto exception;
            }
            BREAK;""",
        "special_object": """        CASE(OP_special_object):
            {
                int arg = *pc++;
                switch (arg) {
                case OP_SPECIAL_OBJECT_THIS_FUNC:
                    *sp++ = js_dup(sf->cur_func);
                    break;
                case OP_SPECIAL_OBJECT_HOME_OBJECT: {
                    JSObject *p1 = JS_VALUE_GET_OBJ(sf->cur_func)->u.func.home_object;
                    *sp++ = p1 ? js_dup(JS_MKPTR(JS_TAG_OBJECT, p1)) : JS_UNDEFINED;
                    break;
                }
                case OP_SPECIAL_OBJECT_NULL_PROTO:
                case OP_SPECIAL_OBJECT_VAR_OBJECT:
                    sf->cur_pc = pc;
                    *sp++ = JS_NewObjectProto(ctx, JS_NULL);
                    if (unlikely(JS_IsException(sp[-1])))
                        goto exception;
                    break;
                default:
                    JS_ThrowInternalError(ctx, "unsupported special object");
                    goto exception;
                }
            }
            BREAK;""",
    }


def validator(source, text):
    """Extend only the existing derived short/long admission, not the base."""
    ops = (*module(source, "iterator").OPS, "append", "apply")
    text = replace_one(
        text,
        "b->stack_size > 512",
        "b->stack_size > 1024",
        "derived admission stack limit",
    )
    text = replace_one(
        text,
        "b->var_count > 128 || b->arg_count > 128",
        "b->var_count > 512 || b->arg_count > 256",
        "derived admission local/arg limit",
    )
    text = replace_one(
        text,
        "    bool captured_args = false;",
        "    bool captured_args = false;\n    bool extended = false, varargs = false, extra_ops = false;\n"
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
    extra += "".join("        case OP_" + name + ":\n" for name in EXTRA_LINUX_OPS)
    extra += "            extra_ops = true;\n            break;\n"
    extra += (
        "        case OP_special_object:\n"
        "            if (code[pos + 1] != OP_SPECIAL_OBJECT_NULL_PROTO &&\n"
        "                code[pos + 1] != OP_SPECIAL_OBJECT_THIS_FUNC &&\n"
        "                code[pos + 1] != OP_SPECIAL_OBJECT_HOME_OBJECT &&\n"
        "                code[pos + 1] != OP_SPECIAL_OBJECT_VAR_OBJECT)\n"
        "                return false;\n"
        "            extra_ops = true;\n"
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
    if (extra_ops && getenv("QJS_DISABLE_LINUX_EXTRA_OPS") != NULL)
        return false;
    FRAME_ITERATOR_KIND(b) = varargs ? 3 : (extended || extra_ops) ? 1 : 0;
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
    iter_bodies, exception = iterator.bodies(source)
    bodies = extra_linux_bodies()
    bodies.update(iter_bodies)
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
        (
            "JS_DefineObjectNameComputed(ctx, sp[-1], sp[-2], JS_PROP_CONFIGURABLE)",
            "js_linux_construct_host_set_name_computed(state,frame,segment,used_bytes,pc,sp,ctx)",
        ),
        (
            "JS_SetPrototypeInternal(ctx, sp[-2], proto, true)",
            "js_linux_construct_host_set_proto(state,frame,segment,used_bytes,pc,sp,ctx,proto)",
        ),
        (
            "JS_CopyDataProperties(ctx, sp[-1 - (mask & 3)], sp[-1 - ((mask >> 2) & 7)], sp[-1 - ((mask >> 5) & 7)], 0)",
            "js_linux_construct_host_copy_data_properties(state,frame,segment,used_bytes,pc,sp,ctx,mask)",
        ),
        (
            "js_for_in_start(ctx, sp)",
            "js_linux_construct_host_for_in_start(state,frame,segment,used_bytes,pc,sp,ctx)",
        ),
        (
            "js_for_in_next(ctx, sp)",
            "js_linux_construct_host_for_in_next(state,frame,segment,used_bytes,pc,sp,ctx)",
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
        "#ifndef QJS_LINUX_REGISTER_FOUNDATION\n    extern int JS_FrameVarargsConstructCall(JSFrameRegisterState *);",
        "#if !defined(QJS_LINUX_REGISTER_FOUNDATION) || defined(QJS_LINUX_CONSTRUCT_CONTINUATION)\n"
        "#ifdef QJS_LINUX_FAST_CONSTRUCT\n"
        "    extern int JS_FastConstructTry(JSFrameRegisterState *);\n"
        "    int fast_construct_event=JS_FastConstructTry(state);\n"
        "    if (fast_construct_event>=0)return fast_construct_event;\n"
        "#endif\n"
        "    extern int JS_FrameVarargsConstructCall(JSFrameRegisterState *);",
        "enable fast and ordinary same-activation constructor hook on Linux",
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
