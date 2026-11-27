"""BigInt add_loc boundary, borrowing the VM frame and retained arithmetic.

Only the existing two nonnumeric add_loc branches are routed here. All other
tags return to the original slow opcode before taking ownership or changing
the cursor. The copied primitive arithmetic keeps the core's allocation and
compaction semantics. No old C compilation graph changes.
"""

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
from native_abi import current as current_abi
import hashlib, re


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
#if defined(_MSC_VER)
        flag=JS_FrameAddLocalDisable;
#else
        __asm__("lea JS_FrameAddLocalDisable(%%%%rip), %%0" : "=r"(flag));
#endif
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


def append(masm, gas, diagnostics):
    abi_layout = current_abi()
    abi_fields, abi_bits = abi_layout["offsets"], abi_layout["bits"]
    assert masm.pop() == "END"
    name = "JS_FrameAddLocalBigCold"
    masm[3:3] = ["EXTERN JS_FrameAddLocalBig:PROC", "EXTERN JS_FrameAddLocalStringCold:PROC"]
    lines = [
        "mov eax, DWORD PTR [r8+8]",
        "cmp eax, -7",
        "je JS_FrameAddLocalStringCold",
        "cmp eax, -9",
        "je add_local_lhs_big",
        "cmp eax, 7",
        "jne JS_FrameAddLocalStringCold",
        "add_local_lhs_big:",
        "mov eax, DWORD PTR [r13-8]",
        "cmp eax, -9",
        "je add_local_rhs_big",
        "cmp eax, 7",
        "jne interp_slow",
        "add_local_rhs_big:",
        "mov r10, QWORD PTR [rbx+56]",
        f"cmp BYTE PTR [r10+{abi_fields['JSRuntime.module_loader_has_attr'] + 3}], 2",
        "je interp_slow",
        # ShortBigInt has the retained signed 32-bit payload and no owned
        # references. Once configured, this pure operation needs no C ABI
        # call. Overflow leaves the local, operand and PC/SP untouched.
        "cmp DWORD PTR [r8+8], 7",
        "jne add_local_call_c",
        "cmp DWORD PTR [r13-8], 7",
        "jne add_local_call_c",
        f"cmp BYTE PTR [r10+{abi_fields['JSRuntime.module_loader_has_attr'] + 3}], 0",
        "je add_local_call_c",
        "mov eax, DWORD PTR [r8]",
        "add eax, DWORD PTR [r13-16]",
        "jo add_local_call_c",
        "mov QWORD PTR [r8], rax",
        "sub r13, 16",
        "add r12, 2",
        "movzx eax, BYTE PTR [r12]",
        "jmp QWORD PTR [rdi+rax*8]",
        "add_local_call_c:",
        "mov QWORD PTR [rbx], rbp",
        "mov QWORD PTR [rbx+16], r12",
        "mov QWORD PTR [rbx+24], r13",
        "mov rcx, rbx",
        "call JS_FrameAddLocalBig",
        "cmp eax, 2",
        "je add_local_native_done",
        "test eax, eax",
        "jne interp_exit",
        "jmp interp_reload",
        "add_local_native_done:",
        "mov r12, QWORD PTR [rbx+16]",
        "mov r13, QWORD PTR [rbx+24]",
        "movzx eax, BYTE PTR [r12]",
        "jmp QWORD PTR [rdi+rax*8]",
    ]
    masm += [
        ".qjscold SEGMENT ALIGN(16) 'CODE'",
        "ALIGN 16",
        "PUBLIC " + name + ", " + name + "_end",
        name + " PROC",
    ]
    gas += [
        '.section .qjsleaf,"xr"',
        ".p2align 4",
        ".globl " + name + ", " + name + "_end",
        ".def " + name + "; .scl 2; .type 32; .endef",
        name + ":",
    ]
    for line in lines:
        # VM targets are public labels in another PROC. Spell the width for
        # conditional tails as well as JMP; MASM must not infer a label type.
        masm += [
            line[:-1] + "::"
            if line.endswith(":")
            else re.sub(r"\b(j[a-z]+) (interp_\w+)", r"\1 NEAR PTR \2", line)
        ]
        gas += [line]
    masm += [
        name + "_end LABEL BYTE",
        name + " ENDP",
        "PUBLIC JS_FrameAddLocalDisable",
        "JS_FrameAddLocalDisable LABEL BYTE",
        'DB "QJS_DISABLE_NATIVE_ADD_LOCAL", 0',
        ".qjscold ENDS",
        ".pdata$zzqjscold SEGMENT ALIGN(4) READONLY 'DATA'",
        "DD IMAGEREL "
        + name
        + ", IMAGEREL "
        + name
        + "_end, IMAGEREL JS_FrameInterpPropertyCold_unwind",
        ".pdata$zzqjscold ENDS",
        "END",
    ]
    gas += [
        name + "_end:",
        ".globl JS_FrameAddLocalDisable",
        "JS_FrameAddLocalDisable:",
        '.asciz "QJS_DISABLE_NATIVE_ADD_LOCAL"',
        '.section .pdata$zzqjscold,"dr"',
        ".p2align 2",
        ".rva " + name + ", " + name + "_end, JS_FrameInterpPropertyCold_unwind",
    ]
