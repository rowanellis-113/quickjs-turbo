"""Shared pure-C declaration, gateway, and configure bodies for dense array append."""

import re
from common.paths import generated_file as _frame_generated_file

DECLARATION = r"""
#include <stdatomic.h>
typedef struct JSFrameArrayAppendData {
    _Atomic(unsigned char) mode;
    unsigned char reserved[7];
    uint64_t hits;
} JSFrameArrayAppendData;
_Static_assert(sizeof(JSFrameArrayAppendData)==16 &&
    offsetof(JSFrameArrayAppendData,hits)==8,"array append observation ABI");
_Static_assert(JS_CLASS_ARRAY==2 && sizeof(JSValue)==16 && JS_TAG_INT==0 &&
    offsetof(JSObject,shape)==QJS_ABI_OFF_JSObject_shape && offsetof(JSObject,prop)==QJS_ABI_OFF_JSObject_prop &&
    offsetof(JSObject,u.array.u.values)==QJS_ABI_OFF_JSObject_u_array_u_values &&
    offsetof(JSObject,u.array.count)==QJS_ABI_OFF_JSObject_u_array_count &&
    offsetof(JSObject,u.array.u1.size)==QJS_ABI_OFF_JSObject_u_array_u1 &&
    offsetof(JSShape,proto)==QJS_ABI_OFF_JSShape_proto &&
    offsetof(JSContext,class_proto)==QJS_ABI_OFF_JSContext_class_proto &&
    offsetof(JSShape,prop_hash_mask)==QJS_ABI_OFF_JSShape_prop_hash_mask && JS_PROP_WRITABLE==2,
    "dense append selected private ABI");
#ifdef _MSC_VER
#pragma section(".qjszzcm$zzzzzzzzzzzzarrayappend",read,write)
__declspec(allocate(".qjszzcm$zzzzzzzzzzzzarrayappend"))
#else
__attribute__((section(".qjslcm$zzzzarrayappend"),used))
#endif
JSFrameArrayAppendData JS_FrameVarargsArrayAppendData={255};
static FRAME_CODE int JS_FrameVarargsArrayAppendConfigure(JSFrameRegisterState *state);
static FRAME_CODE int JS_FrameVarargsArrayReadonlyStep(JSFrameRegisterState *state);
/* The original core has an in-capacity append shortcut which omits this
 * writable-length check. Keep the giant copied semantic body unchanged, but
 * route the violating case to the original complete property setter first.
 * Reads only: no reference, PC, quota, frame or object mutation here.
 */
static FRAME_INLINE bool JS_FrameVarargsArrayReadonlyAppend(JSFrameRegisterState *state)
{
    JSValue *sp=state->sp;
    JSContext *ctx=state->frame->bytecode->realm;
    JSObject *p;
    uint32_t index,length;
    JSShapeProperty *props;
    if(!JS_IsObject(sp[-3]) || JS_VALUE_GET_TAG(sp[-2])!=JS_TAG_INT)return false;
    p=JS_VALUE_GET_OBJ(sp[-3]);
    if(p->class_id!=JS_CLASS_ARRAY || !p->fast_array || !p->extensible ||
       !ctx->std_array_prototype ||
       p->shape->proto!=JS_VALUE_GET_OBJ(ctx->class_proto[JS_CLASS_ARRAY]) ||
       JS_VALUE_GET_TAG(p->prop[0].u.value)!=JS_TAG_INT)return false;
    index=(uint32_t)JS_VALUE_GET_INT(sp[-2]);
    length=(uint32_t)JS_VALUE_GET_INT(p->prop[0].u.value);
    if(index!=p->u.array.count || index<length ||
       index>=p->u.array.u1.size)return false;
#if QJS_ABI_HAS_PREFIX_RC
    props=(JSShapeProperty *)(p->shape->hash_table+p->shape->prop_hash_mask+1);
#else
    props=p->shape->prop;
#endif
    return !(props[0].flags & JS_PROP_WRITABLE);
}

extern int JS_FrameVarargsSlowSelect(JSFrameRegisterState *state);
static FRAME_CODE int JS_FrameVarargsArrayStep(JSFrameRegisterState *state);
"""
CONFIGURE = '\n/* First append miss arrives through the inherited real C boundary. Publish\n * roots before environment access, then re-enter the unchanged selector.\n * Subsequent disabled misses execute the inherited semantic path directly.\n * Environment policy has the same process lifetime as the existing controls.\n */\nstatic FRAME_CODE int JS_FrameVarargsArrayAppendConfigure(JSFrameRegisterState *state)\n{\n    JSFrame *frame=state->frame;\n    unsigned char mode;\n    js_frame_begin_c(state);\n    frame->saved_sp=state->sp;\n    frame->sf.cur_sp=state->sp;\n    frame->sf.cur_pc=state->pc;\n    mode=getenv("QJS_DISABLE_FRAME_ARRAY_APPEND")?2:1;\n    if(getenv("QJS_OBSERVE_FRAME_ARRAY_APPEND"))mode|=4;\n    atomic_store_explicit(&JS_FrameVarargsArrayAppendData.mode,mode,memory_order_relaxed);\n    js_frame_finish_c(state);\n    return JS_FrameVarargsArrayStep(state);\n}\n\n/* Only the inherited in-capacity readonly-extension defect with a proven\n * normal prototype chain reaches this operation. No prototype observer can\n * run before the setter consumes the rejected value. Other prototype cases\n * retain the inherited full semantic path and its live-value root protocol.\n * The complete setter preserves strict/sloppy behavior.\n * A rejected value may run a finalizer: clear its consumed slot before the\n * call, then publish the popped cursor before releasing the base object.\n * Exceptions use the retained complete checkpoint/forward unwinder.\n */\nstatic FRAME_CODE int JS_FrameVarargsArrayReadonlyStep(JSFrameRegisterState *state)\n{\n    JSFrame *frame=state->frame;\n    JSStackFrame *sf=&frame->sf;\n    JSContext *ctx=frame->bytecode->realm;\n    JSValue *sp=state->sp;\n    JSValue value=sp[-1],base;\n    int result;\n    js_frame_begin_c(state);\n    state->pc++;\n    sf->cur_pc=state->pc;\n    frame->saved_sp=sp;\n    sf->cur_sp=sp;\n    sp[-1]=JS_UNDEFINED;\n    result=JS_SetPropertyValue(ctx,sp[-3],sp[-2],value,JS_PROP_THROW_STRICT);\n    base=sp[-3];\n    sp[-3]=JS_UNDEFINED;\n    sp-=3;\n    state->sp=sp;\n    frame->saved_sp=sp;\n    sf->cur_sp=sp;\n    JS_FreeValue(ctx,base);\n    if(unlikely(result<0))state->exception_pending=true;\n    js_frame_finish_c(state);\n    return result<0?JS_FrameVarargsSlowSelect(state):0;\n}\n'
GATEWAY = "\n/* This opcode-only gateway must remain a tail dispatcher. In particular,\n * do not inline array shape checks into a shared selector/prologue. */\nFRAME_CODE int JS_FrameVarargsArraySlowSelect(JSFrameRegisterState *state)\n{\n    if (!state->exception_pending && *state->pc == OP_put_array_el)\n        return JS_FrameVarargsArrayStep(state);\n    return JS_FrameVarargsSlowSelect(state);\n}\n\nstatic FRAME_CODE int JS_FrameVarargsArrayStep(JSFrameRegisterState *state)\n{\n    if (atomic_load_explicit(&JS_FrameVarargsArrayAppendData.mode,memory_order_relaxed) == 255)\n        return JS_FrameVarargsArrayAppendConfigure(state);\n    if (JS_FrameVarargsArrayReadonlyAppend(state))\n        return JS_FrameVarargsArrayReadonlyStep(state);\n    return JS_FrameVarargsSlowSelect(state);\n}\n"


def generate_c(source, build, target):
    parent = (_frame_generated_file(build, "quickjs-interpreter-varargs.c")).read_text(
        encoding="utf-8"
    )
    include = next(line for line in parent.splitlines() if line.startswith("#include "))
    start = parent.index("#ifndef QJS_FRAME_CONTEXT_TYPES\n#define QJS_FRAME_CONTEXT_TYPES\n")
    end = parent.index(
        "/* A supported opcode is declared once, for validation and dispatch. */", start
    )
    # This prefix contains ABI definitions and inline quota helpers only;
    # neither a copied core public body nor a validator/semantic body enters.
    prefix = parent[start:end]
    assert not re.search(r"(?m)^(?:static )?FRAME_CODE ", prefix)
    target.write_text(
        include + "\n" + prefix + "\n" + DECLARATION + GATEWAY + CONFIGURE, encoding="utf-8"
    )
