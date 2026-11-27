"""Pure-C BigInt add_loc extractor."""

import hashlib
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


def generate(source):
    path = _frame_source_file(source, "quickjs-interpreter-bigint.h")
    text = path.read_text()
    start = text.index("    if (tag1==JS_TAG_SHORT_BIG_INT && tag2==JS_TAG_SHORT_BIG_INT) {")
    end = text.index("\nbigint_done:", start)
    arithmetic = text[start:end]
    assert arithmetic.count("sp[-2] = ") == 3
    arithmetic = arithmetic.replace("sp[-2] = ", "result = ")
    return """/* Retained primitive body SHA256: %s. */
extern int JS_FrameInterpSlow(JSFrameRegisterState *state);
extern const char JS_FrameAddLocalDisable[];
_Static_assert(offsetof(JSRuntime, module_loader_has_attr)==QJS_ABI_OFF_JSRuntime_module_loader_has_attr &&
               offsetof(JSRuntime, u)==QJS_ABI_OFF_JSRuntime_u, "add-local mode uses measured padding");
static no_inline int js_add_local_wide_inplace(JSBigInt *p1, const js_limb_t *p2_tab, uint32_t n1, uint32_t n2)
{
    js_limb_t tmp[32];
    uint64_t carry=0;
    uint32_t i;
    for (i=0; i<n2; i++) {
        uint64_t sum=(uint64_t)p1->tab[i]+(uint64_t)p2_tab[i]+carry;
        tmp[i]=(js_limb_t)sum;
        carry=sum>>32;
    }
    js_limb_t b_sign=(js_limb_t)(0u-(p2_tab[n2-1u]>>31));
    for (; i<n1; i++) {
        uint64_t sum=(uint64_t)p1->tab[i]+(uint64_t)b_sign+carry;
        tmp[i]=(js_limb_t)sum;
        carry=sum>>32;
    }
    js_limb_t a_sign=(js_limb_t)(0u-(p1->tab[n1-1u]>>31));
    js_limb_t top_ext=a_sign+b_sign+(js_limb_t)carry;
    if ((top_ext==0u || top_ext==(js_limb_t)-1) &&
        (top_ext&1u)==(tmp[n1-1u]>>31) &&
        !((tmp[n1-1u]==0u || tmp[n1-1u]==(js_limb_t)-1) &&
          (tmp[n1-1u]&1u)==(tmp[n1-2u]>>31))) {
        memcpy(p1->tab, tmp, (size_t)n1*sizeof(js_limb_t));
        return 1;
    }
    return 0;
}
FRAME_NULL_CODE int JS_FrameAddLocalBig(JSFrameRegisterState *state)
{
    JSFrame *frame=state->frame;
    JSStackFrame *sf=&frame->sf;
    JSContext *ctx=frame->bytecode->realm;
    JSRuntime *rt=state->rt;
    unsigned char *mode=(unsigned char *)rt+offsetof(JSRuntime,module_loader_has_attr)+3;
    const char *flag;
    JSValue *sp=state->sp, *pv=&sf->var_buf[state->pc[1]];
    JSValue op1, op2, result;
    uint32_t tag1, tag2;
    uint8_t *pc=state->pc+2;
    if (!*mode) {
        QJS_CONTROL_SLOT_ADDR(flag, JS_FrameAddLocalDisable);
        *mode=getenv(flag)==NULL ? 1 : 2;
    }
    if (*mode!=1) return JS_FrameInterpSlow(state);
    /* The ASM gate has checked both tags before reaching the C boundary. */
    assert(JS_IsBigInt(*pv) && JS_IsBigInt(sp[-1]));
    if (JS_VALUE_GET_TAG(*pv)==JS_TAG_BIG_INT) {
        JSBigInt *p1=(JSBigInt *)JS_VALUE_GET_PTR(*pv);
        uint32_t n1=(uint32_t)p1->len;
        if (JS_REF_COUNT(p1)==1 && n1>=2u && n1<=32u) {
            JSValue rhs=sp[-1];
            uint32_t rtag=JS_VALUE_GET_TAG(rhs);
            JSBigInt *p2=NULL;
            const js_limb_t *p2_tab=NULL;
            js_limb_t rhs_limb0=0;
            uint32_t n2=0;
            if (rtag==JS_TAG_SHORT_BIG_INT) {
                int32_t sv=JS_VALUE_GET_SHORT_BIG_INT(rhs);
                if (n1>=4u && sv>0) {
                    uint64_t lo=(uint64_t)p1->tab[0]|((uint64_t)p1->tab[1]<<32);
                    uint64_t nlo=lo+(uint64_t)(uint32_t)sv;
                    if (likely(nlo>=lo)) {
                        p1->tab[0]=(js_limb_t)nlo;
                        p1->tab[1]=(js_limb_t)(nlo>>32);
                        state->pc=pc;
                        state->sp=sp-1;
                        return 2;
                    }
                }
                rhs_limb0=(js_limb_t)(js_slimb_t)sv;
                p2_tab=&rhs_limb0;
                n2=1u;
            } else if (rtag==JS_TAG_BIG_INT) {
                p2=(JSBigInt *)JS_VALUE_GET_PTR(rhs);
                p2_tab=p2->tab;
                n2=(uint32_t)p2->len;
            }
            if (p2_tab && n1==2u && n2<=2u) {
                int64_t v2=(n2==1u)?(int64_t)(js_slimb_t)p2_tab[0]:(int64_t)((uint64_t)p2_tab[0]|((uint64_t)p2_tab[1]<<32));
                int64_t v1=(int64_t)((uint64_t)p1->tab[0]|((uint64_t)p1->tab[1]<<32));
                uint64_t ures=(uint64_t)v1+(uint64_t)v2;
                int64_t sres=(int64_t)ures;
                if (!((((uint64_t)v1^~(uint64_t)v2)&((uint64_t)v1^ures))>>63) &&
                    (sres<INT32_MIN || sres>INT32_MAX)) {
                    p1->tab[0]=(js_limb_t)ures;
                    p1->tab[1]=(js_limb_t)(ures>>32);
                    if (p2 && --JS_REF_COUNT(p2)<=0)
                        qjs_bigint_pool_put(rt,p2);
                    state->pc=pc;
                    state->sp=sp-1;
                    return 2;
                }
            } else if (p2_tab && n1>=n2 && js_add_local_wide_inplace(p1,p2_tab,n1,n2)) {
                if (p2 && --JS_REF_COUNT(p2)<=0)
                    qjs_bigint_pool_put(rt,p2);
                state->pc=pc;
                state->sp=sp-1;
                return 2;
            }
        }
    }
    op1=js_dup(*pv);
    op2=sp[-1];
    tag1=JS_VALUE_GET_TAG(op1);
    tag2=JS_VALUE_GET_TAG(op2);
    js_frame_begin_c(state);
    sf->cur_pc=pc;
    /* The RHS ownership is transferred to the retained arithmetic. */
    state->pc=pc;
    state->sp=sp-1;
%s
bigint_done:
    /* Publish the result before releasing the old local, as set_value does. */
    set_value(ctx,pv,result);
    js_frame_finish_c(state);
    return 2; /* success in this same frame; the native cursor can resume */
exception:
    /* Retained arithmetic consumed the RHS and the duplicate of the local.
     * The original local remains owned and no dead operand is visited. */
    sp[-1]=JS_UNDEFINED;
    state->exception_pending=true;
    js_frame_finish_c(state);
    return JS_FrameInterpSlow(state);
}
""" % (hashlib.sha256(path.read_bytes()).hexdigest(), arithmetic)
