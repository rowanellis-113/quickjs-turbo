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
from native_build import find_objdump
from native_abi import current as current_abi, source_abi

"""Private .call forwarding: owned JS window plus logical native SF chain. MIT."""
from pathlib import Path
import hashlib, importlib.util, json, re, struct, subprocess, time

sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
TAG = 199
NATIVE_BYTES = 80


def module(source, name):
    sp = importlib.util.spec_from_file_location(
        "forward_" + name.replace("-", "_"), _frame_tool_path(name + ".py")
    )
    m = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


PARENTS = r"""
#define FRAME_FORWARD_TAG 199
#define FRAME_FORWARD_BYTES 80
_Static_assert(sizeof(JSStackFrame)==QJS_ABI_SIZE_JSStackFrame && sizeof(JSFrame)==128 &&
    offsetof(JSStackFrame,cur_sp)==64 && offsetof(JSStackFrame,var_buf)==32 &&
    offsetof(JSStackFrame,is_strict_mode)+2==62,
    "logical C SF is original80-byte header, with borrowed zero-argc undefined");
_Static_assert(FRAME_FORWARD_BYTES>=sizeof(JSStackFrame) &&
    FRAME_FORWARD_BYTES-sizeof(JSStackFrame)<=8,"fixed logical C allocation includes measured tail padding");
static FRAME_INLINE bool js_frame_forward_sf(JSStackFrame *sf)
{
    return sf && sf->var_buf == NULL && ((unsigned char *)sf)[63] == FRAME_FORWARD_TAG;
}
static FRAME_INLINE JSStackFrame *js_frame_forward_parent(JSFrame *frame)
{
    JSStackFrame *sf=frame->sf.prev_frame;
    if (FRAME_ROOT(frame)!=1)
        while (js_frame_forward_sf(sf)) sf=sf->prev_frame;
    return sf;
}
/* Called only after closing/freeing the child. Keep logical frames visible
   throughout all observable cleanup; normalize before their storage is freed. */
static FRAME_INLINE size_t js_frame_forward_take(JSFrame *frame)
{
    JSStackFrame *sf=frame->sf.prev_frame;
    size_t bytes=0;
    if (FRAME_ROOT(frame)!=1) {
        while (js_frame_forward_sf(sf)) {bytes+=FRAME_FORWARD_BYTES;sf=sf->prev_frame;}
        frame->sf.prev_frame=sf;
    }
    return bytes;
}
"""

ENTER = r"""
_Static_assert(offsetof(JSFunctionBytecode,pc2line_len)+sizeof(int)<=FRAME_ITERATOR_OFFSET+3 &&
    FRAME_ITERATOR_OFFSET+3<offsetof(JSFunctionBytecode,pc2line_buf),"forward control owns measured padding");
static FRAME_INLINE bool js_frame_forward_is_call(JSValueConst value)
{
    if (!JS_IsObject(value)) return false;
    JSObject *p=JS_VALUE_GET_OBJ(value);
    return p->class_id==JS_CLASS_C_FUNCTION && p->u.cfunc.cproto==JS_CFUNC_generic &&
        p->u.cfunc.magic==0 && p->u.cfunc.length==1 &&
        p->u.cfunc.c_function.generic==js_function_call;
}

/* Read actual immutable bytecode, never the shared old byte22 leaf cache.
   Accepted bodies cannot allocate, call JS/C, poll, throw, observe this,
   create arguments, write an argument, capture a value, or expose a frame.
   The result remains borrowed until the final poll preflight succeeds. */
static FRAME_INLINE bool js_frame_forward_leaf(JSFunctionBytecode *b,
    JSValue *argv,unsigned argc,JSValue *out)
{
    const uint8_t *pc=b->byte_code_buf;
    unsigned n=b->byte_code_len,index;
    JSValue value;
    int64_t left,right,total;
    _Static_assert(OP_push_7-OP_push_minus1==8 && OP_get_arg3-OP_get_arg0==3,
        "small integer and short argument bytecode ranges");
    if (b->var_count || b->var_ref_count || b->closure_var_count || b->stack_size>2)
        return false;
    if (n==1 && pc[0]==OP_return_undef) {*out=JS_UNDEFINED;return true;}
    if (n==2 && pc[1]==OP_return) {
        if (pc[0]>=OP_push_minus1 && pc[0]<=OP_push_7)
            value=JS_NewInt32(b->realm,(int)pc[0]-(int)OP_push_0);
        else if (pc[0]>=OP_get_arg0 && pc[0]<=OP_get_arg3) {
            index=pc[0]-OP_get_arg0;value=index<argc?argv[index]:JS_UNDEFINED;
        } else if (pc[0]==OP_undefined) value=JS_UNDEFINED;
        else if (pc[0]==OP_null) value=JS_NULL;
        else if (pc[0]==OP_push_false) value=JS_FALSE;
        else if (pc[0]==OP_push_true) value=JS_TRUE;
        else return false;
        *out=value;return true;
    }
    if (n!=4 || pc[0]<OP_get_arg0 || pc[0]>OP_get_arg3 ||
        pc[2]!=OP_add || pc[3]!=OP_return) return false;
    index=pc[0]-OP_get_arg0;
    if (index>=argc || JS_VALUE_GET_TAG(argv[index])!=JS_TAG_INT) return false;
    left=JS_VALUE_GET_INT(argv[index]);
    if (pc[1]>=OP_push_minus1 && pc[1]<=OP_push_7)
        right=(int)pc[1]-(int)OP_push_0;
    else if (pc[1]>=OP_get_arg0 && pc[1]<=OP_get_arg3) {
        index=pc[1]-OP_get_arg0;
        if (index>=argc || JS_VALUE_GET_TAG(argv[index])!=JS_TAG_INT) return false;
        right=JS_VALUE_GET_INT(argv[index]);
    } else return false;
    total=left+right;
    if (total<INT32_MIN || total>INT32_MAX) return false;
    *out=JS_NewInt32(b->realm,(int32_t)total);return true;
}

FRAME_CODE int JS_FrameVarargsForwardTry(JSFrameRegisterState *state)
{
    JSFrame *parent=state->frame,*child;
    JSFrameSegment *segment=state->segment;
    JSRuntime *rt=state->rt;
    JSFunctionBytecode *caller=parent->bytecode,*target;
    JSContext *ctx=caller->realm,*poll_ctx,*walk_ctx;
    JSValue *sp=state->sp,*original_argv,*argv,*owned,*vars,*stack;
    JSValue callee,receiver,original_func,original_this,target_func,target_this;
    JSValue leaf_value;
    unsigned op=*state->pc,argc,size,method,tail,depth=0,count,committed=0;
    size_t regular,extra,need;
    int result=0;
#ifdef QJS_INTERP_FRAME_INTERNAL_ENTRY
    js_frame_begin_c(state);
#endif
    if (!((unsigned char *)caller)[FRAME_ITERATOR_OFFSET+3])
        ((unsigned char *)caller)[FRAME_ITERATOR_OFFSET+3]=getenv("QJS_DISABLE_FRAME_CALL_FORWARD")?2:\
            getenv("QJS_DISABLE_FRAME_CALL_FORWARD_LEAF")?5:1;
    if ((((unsigned char *)caller)[FRAME_ITERATOR_OFFSET+3]&3)!=1) goto done;
    if (op>=OP_call0 && op<=OP_call3) {argc=op-OP_call0;size=1;method=tail=0;}
    else if (op==OP_call || op==OP_call_method || op==OP_tail_call || op==OP_tail_call_method) {
        argc=get_u16(state->pc+1);size=3;
        method=op==OP_call_method || op==OP_tail_call_method;
        tail=op==OP_tail_call || op==OP_tail_call_method;
    } else goto done;
    if (argc+1+method>0x7fff) goto done;
    original_argv=sp-argc;
    original_func=original_argv[-1];
    original_this=method?original_argv[-2]:JS_UNDEFINED;
    callee=original_func;receiver=original_this;argv=original_argv;count=argc;
    while (js_frame_forward_is_call(callee)) {
        if (++depth>64) goto done;
        callee=receiver;
        receiver=count?argv[0]:JS_UNDEFINED;
        if (count) {count--;argv++;}
    }
    if (!depth || !(target=js_frame_target(callee))) goto done;
    target_func=callee;target_this=receiver;
    unsigned owned_count=max_int((int)count,target->arg_count);
    regular=FRAME_HEADER_BYTES+sizeof(JSValue)*(owned_count+target->var_count+target->stack_size)+FRAME_CAPTURE_BYTES(target);
    extra=(size_t)depth*FRAME_FORWARD_BYTES;need=regular+extra;
    /* Do not allocate before the original logical C frames/poll are visible.
       A grow or pending interrupt uses the complete inherited protocol. */
    if (need>segment->capacity-segment->used || js_check_stack_overflow(rt,need)) goto done;
    callee=original_func;receiver=original_this;argv=original_argv;unsigned native_argc=argc;
    poll_ctx=ctx;
    for (unsigned i=0;i<depth;i++) {
        if (poll_ctx->interrupt_counter<=1) goto rollback_polls;
        poll_ctx->interrupt_counter--;committed++;
        JSObject *function=JS_VALUE_GET_OBJ(callee);
        poll_ctx=function->u.cfunc.realm;
        callee=receiver;receiver=native_argc?argv[0]:JS_UNDEFINED;
        if (native_argc) {native_argc--;argv++;}
    }
    if (poll_ctx->interrupt_counter<=1) goto rollback_polls;
    if (((unsigned char *)caller)[FRAME_ITERATOR_OFFSET+3]==1 &&
        js_frame_forward_leaf(target,argv,count,&leaf_value)) {
        /* Exactly the original d native polls plus the target poll; every
           counter is >1, so no observer runs during the elided activation.
           Duplicate a returned reference before original operands can die. */
        state->result=js_dup(leaf_value);
        parent->sf.cur_pc=state->pc+size;parent->sf.cur_sp=sp;parent->saved_sp=sp;
        parent->pending=(argc+1+method)|(tail?0x8000:0);
        state->pc+=size;
        poll_ctx->interrupt_counter--;
        result=2;goto done;
    }
    /* There is now no allocation, JS, callback, failing operation or poll
       handler until the entire owned child and logical SF chain are ready. */
    child=(JSFrame *)(segment->data+segment->used);
    owned=(JSValue *)((uint8_t *)child+FRAME_HEADER_BYTES);
    for (unsigned i=0;i<count;i++) owned[i]=js_dup(argv[i]);
    for (unsigned i=count;i<owned_count;i++) owned[i]=JS_UNDEFINED;
    vars=owned+owned_count;
    for (unsigned i=0;i<target->var_count;i++) vars[i]=JS_UNDEFINED;
    stack=vars+target->var_count;
    child->segment=segment;child->frame_bytes=(uint32_t)regular;
    child->bytecode=target;child->this_value=target_this;
    child->owned_args=owned_count;child->pending=0;child->saved_sp=stack;
    JSStackFrame *sf=&child->sf,*previous=&parent->sf;
    sf->cur_func=target_func;sf->arg_buf=owned;sf->var_buf=vars;
    sf->arg_count=owned_count;
    sf->var_ref_count=target->var_ref_count;
    sf->var_refs=target->var_ref_count?(JSVarRef **)(stack+target->stack_size):NULL;
    for (unsigned i=0;i<target->var_ref_count;i++) sf->var_refs[i]=NULL;
    sf->is_strict_mode=target->is_strict_mode;FRAME_CLEAR_STACK_AUX(sf);
    sf->cur_pc=NULL;sf->cur_sp=stack;
    FRAME_ROOT(child)=2;((unsigned char *)sf)[63]=0;
    callee=original_func;receiver=original_this;argv=original_argv;native_argc=argc;
    for (unsigned i=0;i<depth;i++) {
        JSStackFrame *logical=(JSStackFrame *)((uint8_t *)child+regular+i*FRAME_FORWARD_BYTES);
        /* A successful zero-argc wrapper is the last layer; target this
           is undefined and remains borrowed/immutable through logical pop. */
        JSValue *undefined_slot=&child->this_value;
        assert(native_argc || JS_IsUndefined(*undefined_slot));
        logical->prev_frame=previous;logical->cur_func=callee;
        logical->arg_buf=native_argc?argv:undefined_slot;
        logical->arg_count=native_argc?native_argc:1;
        logical->var_buf=NULL;logical->var_refs=NULL;logical->var_ref_count=0;
        logical->is_strict_mode=false;FRAME_CLEAR_STACK_AUX(logical);
        logical->cur_pc=NULL;logical->cur_sp=NULL;
        ((unsigned char *)logical)[62]=0;((unsigned char *)logical)[63]=FRAME_FORWARD_TAG;
        previous=logical;
        callee=receiver;receiver=native_argc?argv[0]:JS_UNDEFINED;
        if (native_argc) {native_argc--;argv++;}
    }
    sf->prev_frame=previous;
    parent->sf.cur_pc=state->pc+size;parent->sf.cur_sp=sp;parent->saved_sp=sp;
    parent->pending=(argc+1+method)|(tail?0x8000:0);
    segment->used+=need;state->used_bytes+=need;
#ifdef QJS_INTERP_FRAME_INTERNAL_ENTRY
    js_frame_charge_stack(rt,need);
#endif
    poll_ctx->interrupt_counter--;
    state->frame=child;state->pc=target->byte_code_buf;state->sp=stack;
    rt->current_stack_frame=sf;
#ifdef QJS_INTERP_FRAME_DIAGNOSTICS
    state->pushes++;state->copied_values+=count;state->depth++;
    if (count<target->arg_count)state->arities++;
    if(state->depth>state->max_depth)state->max_depth=state->depth;
    if(state->used_bytes>state->peak_bytes)state->peak_bytes=state->used_bytes;
#endif
    result=1;goto done;
rollback_polls:
    /* No callback has run and no operand, frame or owner has changed. Refund
       precisely the successful native-prefix decrements before full fallback. */
    callee=original_func;receiver=original_this;argv=original_argv;native_argc=argc;
    walk_ctx=ctx;
    for (unsigned i=0;i<committed;i++) {
        walk_ctx->interrupt_counter++;
        walk_ctx=JS_VALUE_GET_OBJ(callee)->u.cfunc.realm;
        callee=receiver;receiver=native_argc?argv[0]:JS_UNDEFINED;
        if (native_argc) {native_argc--;argv++;}
    }
done:
#ifdef QJS_INTERP_FRAME_INTERNAL_ENTRY
    js_frame_finish_c(state);
#endif
    return result;
}
"""


def transform(text):
    marker = "static FRAME_INLINE JSFrame *js_frame_parent(JSFrame *frame)"
    assert text.count(marker) == 1
    text = text.replace(marker, PARENTS + "\n" + marker)
    old = "    return FRAME_ROOT(frame) ? NULL : (JSFrame *)frame->sf.prev_frame;"
    assert text.count(old) == 1
    text = text.replace(
        old, "    return FRAME_ROOT(frame)==1 ? NULL : (JSFrame *)js_frame_forward_parent(frame);"
    )
    marker = "FRAME_CODE int JS_FrameVarargsSlow(JSFrameRegisterState *state)"
    assert text.count(marker) == 1
    text = text.replace(marker, ENTER + "\n" + marker)
    start = text.index(marker)
    end = text.index("\n}\n#undef CASE", start) + 2
    body = text[start:end]
    old = "    rt->current_stack_frame = frame->sf.prev_frame;"
    assert body.count(old) == 1
    body = body.replace(
        old,
        """    size_t forward_bytes=js_frame_forward_take(frame);
    used_bytes-=forward_bytes;
#ifdef QJS_INTERP_FRAME_INTERNAL_ENTRY
    js_frame_release_stack(rt,forward_bytes);
#endif
"""
        + old,
    )
    text = text[:start] + body + text[end:]
    old = "        if ((((unsigned char *)f->bytecode)[FRAME_ITERATOR_OFFSET] & 2) != 0)"
    assert text.count(old) == 1
    text = text.replace(
        old,
        """        if ((FRAME_ROOT(f)!=1 && js_frame_forward_sf(f->sf.prev_frame)) ||
            (((unsigned char *)f->bytecode)[FRAME_ITERATOR_OFFSET] & 2) != 0)""",
    )
    return text


ALIASES = {
    "JS_FrameCInvokeGuard": "JS_FrameCallForwardOldCGuard",
    "interp_root_return": "JS_FrameCallForwardOldRootReturn",
    "interp_release_values": "JS_FrameCallForwardOldReleaseValues",
}
BRANCHES = {
    "JS_FrameCInvokeEntry": "JS_FrameCallForwardCleanEntry",
    "JS_FrameCallLinkOldM_JS_FrameCInvokeEntry": "JS_FrameCallForwardCleanEntry",
    "JS_FrameCInvokeDirtyEntry": "JS_FrameCallForwardDirtyEntry",
    "interp_root_return": "JS_FrameCallForwardRootReturn",
    "JS_FrameCallForwardOldRootReturn": "JS_FrameCallForwardRootReturn",
}


def asm_blocks(build, diagnostics, msvc):
    fields = current_abi()["offsets"]
    forward = fields["JSFunctionBytecode.pc2line_len"] + 7
    blocks = [
        (
            "JS_FrameCallForwardCleanEntry",
            [
                "lea r11, [rip+"
                + ("JS_FrameNativeCScopeFallback" if msvc else "interp_host_call")
                + "]",
                "jmp JS_FrameCallForwardGuard",
            ],
        )
    ]
    if not msvc and not diagnostics:
        blocks.append(
            (
                "JS_FrameCallForwardDirtyEntry",
                ["lea r11, [rip+dirty_interp_host_call]", "jmp JS_FrameCallForwardGuard"],
            )
        )
    else:
        name, body = blocks[0]
        blocks[0] = (
            name,
            [".export JS_FrameCallForwardDirtyEntry", "JS_FrameCallForwardDirtyEntry:", *body],
        )
    blocks += [
        (
            "JS_FrameCallForwardGuard",
            [
                f"cmp WORD PTR [rdx+{fields['JSObject.class_id']}], 12",
                "jne JS_FrameCallForwardOldCGuard",
                "lea r10, [rip+qjs_frame_core_js_function_call]",
                f"cmp QWORD PTR [rdx+{fields['JSObject.u.cfunc.c_function']}], r10",
                "jne JS_FrameCallForwardOldCGuard",
                f"cmp BYTE PTR [rdx+{fields['JSObject.u.cfunc.cproto']}], 0",
                "jne JS_FrameCallForwardOldCGuard",
                f"cmp WORD PTR [rdx+{fields['JSObject.u.cfunc.magic']}], 0",
                "jne JS_FrameCallForwardOldCGuard",
                f"cmp BYTE PTR [rdx+{fields['JSObject.u.cfunc.length']}], 1",
                "jne JS_FrameCallForwardOldCGuard",
                "mov rax, QWORD PTR [rbp+80]",
                f"cmp BYTE PTR [rax+{forward}], 2",
                "je JS_FrameCallForwardOldCGuard",
                "jmp JS_FrameCallForwardEnter",
            ],
        ),
        (
            "JS_FrameCallForwardEnter",
            [
                "mov QWORD PTR [rsp+32], r11",
                "mov DWORD PTR [rsp+40], ecx",
                "mov QWORD PTR [rbx], rbp",
                "mov QWORD PTR [rbx+16], r12",
                "mov QWORD PTR [rbx+24], r13",
                "mov r10, QWORD PTR [rbx+56]",
                f"mov QWORD PTR [r10+{fields['JSRuntime.current_stack_frame']}], rbp",
                "mov rcx, rbx",
                "call JS_FrameCallForwardNativeProbe",
                "test eax, eax",
                "jz forward_enter_fallback",
                *([] if diagnostics else ["mov QWORD PTR [rbx+96], 0"]),
                "cmp eax, 2",
                "je JS_FrameCallForwardLeafReturn",
                "jmp interp_reload",
                "forward_enter_fallback:",
                "mov r11, QWORD PTR [rsp+32]",
                "mov ecx, DWORD PTR [rsp+40]",
                "mov r8, rcx",
                "shl r8, 4",
                "neg r8",
                "add r8, r13",
                "mov rdx, QWORD PTR [r8-16]",
                "jmp JS_FrameCallForwardOldCGuard",
            ],
        ),
        (
            "JS_FrameCallForwardLeafReturn",
            [
                "movdqu xmm0, XMMWORD PTR [rbx+40]",
                "mov r12, QWORD PTR [rbx+16]",
                "mov r13, QWORD PTR [rbx+24]",
                "mov r11, r13",
                "movzx r10d, WORD PTR [rbp+126]",
                "and r10d, 32767",
                "shl r10, 4",
                "neg r10",
                "add r10, r11",
                "mov r13, r10",
                "mov DWORD PTR [rsp+60], 1",
                "jmp JS_FrameCallForwardOldReleaseValues",
            ],
        ),
        (
            "JS_FrameCallForwardRootReturn",
            [
                # Root1 is the original activation exit. Root2 is a physical JS
                # child with logical C parents: the old pop has already released
                # its ordinary byte count and reset segment.used, without a call.
                "cmp BYTE PTR [rbp+62], 3",
                "je JS_FrameConstructNativeReturn",
                "cmp BYTE PTR [rbp+62], 2",
                "jne JS_FrameCallForwardTrueRootExit",
                "mov r10, QWORD PTR [rbp]",
                "forward_native_pop:",
                "sub QWORD PTR [rbx+32], 80",
                "mov r10, QWORD PTR [r10]",
                "cmp QWORD PTR [r10+32], 0",
                "jne forward_native_done",
                "cmp BYTE PTR [r10+63], 199",
                "je forward_native_pop",
                "forward_native_done:",
                "mov rax, QWORD PTR [rbx+56]",
                f"mov QWORD PTR [rax+{fields['JSRuntime.current_stack_frame']}], r10",
                "mov rbp, r10",
                "mov rax, QWORD PTR [rbp+80]",
                f"mov rsi, QWORD PTR [rax+{fields['JSFunctionBytecode.realm']}]",
                "mov r14, QWORD PTR [rbp+32]",
                "mov r15, QWORD PTR [rbp+24]",
                "mov r12, QWORD PTR [rbp+48]",
                "mov r11, QWORD PTR [rbp+104]",
                "movzx r10d, WORD PTR [rbp+126]",
                "and r10d, 32767",
                "shl r10, 4",
                "neg r10",
                "add r10, r11",
                "mov r13, r10",
                "mov DWORD PTR [rsp+60], 1",
                "jmp JS_FrameCallForwardOldReleaseValues",
            ],
        ),
    ]
    blocks.append(
        (
            "JS_FrameConstructNativeReturn",
            [
                "mov rbp, QWORD PTR [rbp]",
                "mov rax, QWORD PTR [rbp+80]",
                f"mov rsi, QWORD PTR [rax+{fields['JSFunctionBytecode.realm']}]",
                "mov r14, QWORD PTR [rbp+32]",
                "mov r15, QWORD PTR [rbp+24]",
                "mov r12, QWORD PTR [rbp+48]",
                "mov r11, QWORD PTR [rbp+104]",
                "movzx r10d, WORD PTR [rbp+126]",
                "and r10d, 32767",
                "shl r10, 4",
                "neg r10",
                "add r10, r11",
                "mov r13, r10",
                # The common undefined/immediate return transfers the parent's owner
                # directly. Heap primitives/object returns need original finalization.
                "movhlps xmm1, xmm0",
                "movq rax, xmm1",
                "test eax, eax",
                "js JS_FrameConstructNativeHeapReturn",
                "movdqu xmm0, XMMWORD PTR [r13]",
                "movdqu xmm1, XMMWORD PTR [rdi+2048]",
                "movdqu XMMWORD PTR [r13], xmm1",
                "mov DWORD PTR [rsp+60], 1",
                "jmp JS_FrameCallForwardOldReleaseValues",
            ],
        )
    )
    blocks.append(
        (
            "JS_FrameConstructNativeHeapReturn",
            [
                "movdqu XMMWORD PTR [rbx+40], xmm0",
                "mov QWORD PTR [rbx], rbp",
                "mov QWORD PTR [rbx+16], r12",
                "mov QWORD PTR [rbx+24], r11",
                "mov rcx, rbx",
                "call JS_FrameVarargsConstructHeapReturn",
                "jmp interp_reload",
            ],
        )
    )
    if not msvc and not diagnostics:
        # Only a real C callee rejected by the old .call pointer comparison
        # reaches this gate. Original .call admission/probes remain unchanged.
        name, body = next(b for b in blocks if b[0] == "JS_FrameCallForwardGuard")
        old = f"cmp QWORD PTR [rdx+{fields['JSObject.u.cfunc.c_function']}], r10"
        position = body.index(old) + 1
        assert body[position] == "jne JS_FrameCallForwardOldCGuard"
        body[position] = "jne JS_FrameApplyForwardGuard"
        blocks.extend(
            [
                (
                    "JS_FrameApplyForwardGuard",
                    [
                        "lea r10, [rip+qjs_frame_core_js_function_apply]",
                        f"cmp QWORD PTR [rdx+{fields['JSObject.u.cfunc.c_function']}], r10",
                        "jne JS_FrameCallForwardOldCGuard",
                        f"cmp BYTE PTR [rdx+{fields['JSObject.u.cfunc.cproto']}], 1",
                        "jne JS_FrameCallForwardOldCGuard",
                        f"cmp WORD PTR [rdx+{fields['JSObject.u.cfunc.magic']}], 0",
                        "jne JS_FrameCallForwardOldCGuard",
                        f"cmp BYTE PTR [rdx+{fields['JSObject.u.cfunc.length']}], 2",
                        "jne JS_FrameCallForwardOldCGuard",
                        "jmp JS_FrameApplyForwardEnter",
                    ],
                ),
                (
                    "JS_FrameApplyForwardEnter",
                    [
                        "mov QWORD PTR [rsp+32], r11",
                        "mov DWORD PTR [rsp+40], ecx",
                        "mov QWORD PTR [rbx], rbp",
                        "mov QWORD PTR [rbx+16], r12",
                        "mov QWORD PTR [rbx+24], r13",
                        "mov r10, QWORD PTR [rbx+56]",
                        f"mov QWORD PTR [r10+{fields['JSRuntime.current_stack_frame']}], rbp",
                        "mov rcx, rbx",
                        "call JS_FrameApplyForwardCall",
                        "test eax, eax",
                        "jz apply_forward_fallback",
                        "cmp eax, 2",
                        "je apply_forward_exit",
                        "jmp interp_reload",
                        "apply_forward_exit:",
                        "mov rbp, QWORD PTR [rbx]",
                        "mov r12, QWORD PTR [rbx+16]",
                        "mov r13, QWORD PTR [rbx+24]",
                        "mov eax, 1",
                        "jmp interp_exit",
                        "apply_forward_fallback:",
                        "mov r11, QWORD PTR [rsp+32]",
                        "mov ecx, DWORD PTR [rsp+40]",
                        "mov r8, rcx",
                        "shl r8, 4",
                        "neg r8",
                        "add r8, r13",
                        "mov rdx, QWORD PTR [r8-16]",
                        "jmp JS_FrameCallForwardOldCGuard",
                    ],
                ),
            ]
        )
    return blocks


@source_abi
def compile_asm(source, build, compiler, msvc):
    rows = json.loads((_frame_build_file(build, "compile_commands.json")).read_text())
    diagnostics = "QJS_INTERP_FRAME_DIAGNOSTICS" in next(
        x["command"] for x in rows if Path(x["file"]).name == "quickjs-interpreter.c"
    )
    blocks = asm_blocks(build, diagnostics, msvc)
    defined = {n for n, _ in blocks}
    for _, body in blocks:
        defined.update(x.split(" ", 1)[1] for x in body if x.startswith(".export "))
    externals = {
        "qjs_frame_core_js_function_call",
        "JS_FrameVarargsForwardTry",
        "JS_FrameCallForwardNativeProbe",
        "interp_reload",
        "JS_FrameInterpPropertyCold_unwind",
        "JS_FrameCallForwardOldCGuard",
        "JS_FrameCallForwardTrueRootExit",
        "JS_FrameCallForwardOldReleaseValues",
        "JS_FrameVarargsConstructHeapReturn",
        "JS_FrameNativeCScopeFallback" if msvc else "interp_host_call",
    }
    if not msvc and not diagnostics:
        externals.add("dirty_interp_host_call")
    if not msvc and not diagnostics:
        externals.update(
            ("qjs_frame_core_js_function_apply", "JS_FrameApplyForwardCall", "interp_exit")
        )
    if msvc:
        text = ["OPTION CASEMAP:NONE", "OPTION DOTNAME"]
        text += [
            "EXTERN " + n + (":BYTE" if n == "JS_FrameInterpPropertyCold_unwind" else ":PROC")
            for n in sorted(externals)
        ]
        text += [".qjzzva SEGMENT ALIGN(16) READONLY 'CODE'"]
        for name, body in blocks:
            text += ["ALIGN 16", "PUBLIC " + name + ", " + name + "_end", name + " PROC"]
            for line in body:
                if line.startswith(".export "):
                    text += ["PUBLIC " + line.split(" ", 1)[1]]
                    continue
                line = re.sub(r"\[rip\+([^\]]+)\]", r"\1", line)
                if line.endswith(":") and line[:-1] in defined:
                    line += ":"
                if re.fullmatch(r"(j\w+|call) \w+", line):
                    kind, target = line.split(" ", 1)
                    if kind != "call":
                        line = kind + " NEAR PTR " + target
                text.append(line)
            text += [name + "_end LABEL BYTE", name + " ENDP"]
        text += [".qjzzva ENDS", ".pdata$zzzzzznullfast SEGMENT ALIGN(4) READONLY 'DATA'"]
        text += [
            "DD IMAGEREL "
            + n
            + ", IMAGEREL "
            + n
            + "_end, IMAGEREL JS_FrameInterpPropertyCold_unwind"
            for n, _ in blocks
        ]
        text += [".pdata$zzzzzznullfast ENDS", "END"]
        asm = _frame_generated_file(build, "quickjs-interpreter-call-forward.asm")
        obj = _frame_generated_file(build, "quickjs-interpreter-call-forward.obj")
        command = [str(compiler.with_name("ml64.exe")), "/nologo", "/c", "/Fo" + str(obj), str(asm)]
    else:
        text = [".intel_syntax noprefix", '.section .qjzzva,"xr"']
        for name, body in blocks:
            text += [
                ".p2align 4",
                ".globl " + name + ", " + name + "_end",
                ".def " + name + "; .scl 2; .type 32; .endef",
                name + ":",
            ]
            for line in body:
                text.append(
                    ".globl " + line.split(" ", 1)[1] if line.startswith(".export ") else line
                )
            text.append(name + "_end:")
        text += ['.section .pdata$zzzzzznullfast,"dr"', ".p2align 2"]
        text += [
            ".rva " + n + "," + n + "_end,JS_FrameInterpPropertyCold_unwind" for n, _ in blocks
        ]
        asm = _frame_generated_file(build, "quickjs-interpreter-call-forward.S")
        obj = _frame_generated_file(build, "quickjs-interpreter-call-forward.obj")
        command = [str(compiler), "-c", "-g0", str(asm), "-o", str(obj)]
    asm.write_text("\n".join(text) + "\n", encoding="ascii")
    p = subprocess.run(command, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
    obj.with_suffix(".log").write_bytes(p.stdout + p.stderr)
    assert p.returncode == 0, (command, (p.stdout + p.stderr).decode(errors="replace")[-3000:])
    obj.with_suffix(".compile.json").write_text(
        json.dumps(
            dict(
                status="passed",
                command=command,
                source_sha256=sha(asm),
                object_sha256=sha(obj),
                diagnostics=diagnostics,
                functions=[n for n, _ in blocks],
                protocol="Same physical VM RSP/register ABI; logical native SF tail is80 bytes; zero-argc argv borrows child.this_value; no C activation per forwarded native wrapper.",
            ),
            indent=2,
        )
        + "\n"
    )
    module(source, "call-forward-native").compile_extra(source, build, compiler, msvc, diagnostics)


def applicable(coff):
    return any(s["name"] in {*ALIASES, *BRANCHES} for s in coff.all_symbols.values())


def route_bounded_m_probe(source, path, folder):
    """Decode the named M probe without unrelated merged COFF symbol boundaries.

    objdump can split an instruction at another contribution's symbol value.
    A raw, independently bounded probe avoids silently missing this existing
    conditional transfer. Retain all instruction bytes and relocation slots.
    """
    C = module(source, "object-adapter")
    I = module(source, "iterator")
    raw = path.read_bytes()
    co = C.Coff(raw)
    starts = [
        s
        for s in co.all_symbols.values()
        if s["name"] == "JS_FrameCallLinkMProbe" and s["section"] > 0
    ]
    if not starts:
        return []
    ends = [
        s
        for s in co.all_symbols.values()
        if s["name"] == "JS_FrameCallLinkMProbe_end" and s["section"] > 0
    ]
    assert len(starts) == len(ends) == 1
    start, end = starts[0], ends[0]
    assert start["section"] == end["section"] and start["value"] < end["value"]
    section = co.section_records[start["section"] - 1]
    body = raw[section["raw"] + start["value"] : section["raw"] + end["value"]]
    binary = folder / "bounded-M-probe.bin"
    binary.write_bytes(body)
    command = [
        str(find_objdump(folder)),
        "-D",
        "-w",
        "-z",
        "-b",
        "binary",
        "-m",
        "i386:x86-64",
        "-Mintel",
        "--insn-width=15",
        "--adjust-vma=" + str(start["value"]),
        str(binary),
    ]
    listing = subprocess.check_output(command, text=True, encoding="utf-8")
    (folder / "bounded-M-probe.asm.txt").write_text(listing, encoding="utf-8")
    decoded = []
    for line in listing.splitlines():
        m = re.match(r"^\s*([0-9a-f]+):\s+((?:[0-9a-f]{2}[ \t]+)+)(\S.*)$", line)
        if m:
            decoded.append((int(m[1], 16), bytes.fromhex(m[2]), m[3]))
    cursor = start["value"]
    branches = {}
    for pc, data, instruction in decoded:
        assert pc == cursor
        cursor += len(data)
        if len(data) == 6 and data[:2] == b"\x0f\x85":
            assert instruction.startswith("jne ")
            branches[pc + 2] = data
    assert decoded and cursor == end["value"]
    expected = ("JS_FrameCallLinkOldM_JS_FrameCInvokeEntry", "JS_FrameCallForwardCleanEntry")
    hits = []
    for i in range(section["count"]):
        at = section["reloc"] + i * 10
        offset, index, kind = struct.unpack_from("<IIH", raw, at)
        name = co.all_symbols[index]["name"]
        if start["value"] <= offset < end["value"] and name in expected:
            assert kind == 4 and offset in branches and branches[offset][2:] == bytes(4)
            hits.append((at, offset, index, name))
    assert len(hits) == 1, hits
    at, offset, index, old = hits[0]
    if old != expected[1]:
        target = co.external(expected[1])
        struct.pack_into("<I", co.data, at + 4, target)
        I.finish_preserving_tail(co, raw, path)
    result = path.read_bytes()
    check = C.Coff(result)
    for i, symbol in co.all_symbols.items():
        assert check.all_symbols[i] == symbol
    for sn, (a, b) in enumerate(zip(co.section_records, check.section_records), 1):
        assert (raw[a["raw"] : a["raw"] + a["size"]] if a["raw"] else bytes(a["size"])) == (
            result[b["raw"] : b["raw"] + b["size"]] if b["raw"] else bytes(b["size"])
        )
        for i in range(a["count"]):
            before = list(struct.unpack_from("<IIH", raw, a["reloc"] + i * 10))
            after = list(struct.unpack_from("<IIH", result, b["reloc"] + i * 10))
            if sn == start["section"] and before[0] == offset:
                assert after[0] == offset and after[2] == 4
                assert check.all_symbols[after[1]]["name"] == expected[1]
                after[1] = before[1]
            assert before == after
    return [
        dict(
            section=start["section"],
            offset=offset,
            old=old,
            target=expected[1],
            recovered=old != expected[1],
            probe_sha256=hashlib.sha256(body).hexdigest(),
            instruction_boundaries=len(decoded),
            command=command,
            listing_sha256=sha(folder / "bounded-M-probe.asm.txt"),
            every_instruction_byte_and_original_relocation_slot_preserved=True,
        )
    ]


def adapt(source, build, path, raw, msvc):
    C = module(source, "object-adapter")
    I = module(source, "iterator")
    co = C.Coff(raw)
    exports = []
    for old, new in [*ALIASES.items(), ("interp_root_return", "JS_FrameCallForwardTrueRootExit")]:
        found = [s for s in co.all_symbols.values() if s["name"] == old and s["section"] > 0]
        if not found:
            continue
        assert len(found) == 1, (old, found)
        s = found[0]
        at = len(co.strings)
        co.strings += new.encode() + b"\0"
        entry = bytearray(co.stride)
        struct.pack_into("<III", entry, 0, 0, at, s["value"])
        struct.pack_into("<i" if co.stride == 20 else "<h", entry, 12, s["section"])
        struct.pack_into("<H", entry, 16 if co.stride == 20 else 14, 32)
        entry[co.class_offset] = 2
        co.aliases.append(entry)
        exports.append(dict(old=old, new=new, section=s["section"], offset=s["value"]))
    folder = _frame_generated_file(build, "call-forward-link") / str(time.time_ns())
    folder.mkdir(parents=True)
    temp = folder / "route.obj"
    I.finish_preserving_tail(co, raw, temp)
    I.route(
        temp, source, find_objdump(build), targets=BRANCHES, label="call-forward", conditional=True
    )
    jump_record = Path(str(temp) + ".call-forward.json")
    bounded = route_bounded_m_probe(source, temp, folder) if msvc else []
    result = temp.read_bytes()
    record = folder / "adapt.json"
    record.write_text(
        json.dumps(
            dict(
                status="passed",
                input=str(path),
                input_sha256=hashlib.sha256(raw).hexdigest(),
                output_sha256=sha(temp),
                aliases=exports,
                bounded_M_probe_routes=bounded,
                branch_routes=str(jump_record) if jump_record.exists() else None,
                old_instructions_not_shifted=True,
                allowed_operand_changes="Only separately decoded existing near branch rel32 fields. Normal JS return kernels and tables are unchanged.",
            ),
            indent=2,
        )
        + "\n"
    )
    return result, str(record)
