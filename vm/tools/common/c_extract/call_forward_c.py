"""Shared pure-C call forwarding parents, entry, and captured-readonly proof."""

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

CAPTURED_PROOF = r"""
/* MIT. Cold proof only; no allocation, GC or recursive C calls.
 * Parameters remain owned by the paused caller/logical native view. Borrowing
 * is valid only while no descendant can replace a binding before detach.
 * Reject unrelated writes too: this deliberately favors a small sound proof.
 * `sizes` is the complete upstream table, passed explicitly so extracted
 * validators can share their existing original-table adapter.
 */
static FRAME_CODE bool js_frame_captured_readonly(
    const JSFunctionBytecode *root, const uint8_t *sizes)
{
    const JSFunctionBytecode *work[64];
    unsigned count = 1, cursor, i, j, code_budget = 65536, pool_budget = 4096;
    work[0] = root;
    for (cursor = 0; cursor < count; cursor++) {
        const JSFunctionBytecode *b = work[cursor];
        const uint8_t *code = b->byte_code_buf;
        int pos, size, op;
        if (b->func_kind != JS_FUNC_NORMAL || b->is_derived_class_constructor ||
            !code || b->byte_code_len <= 0 ||
            (unsigned)b->byte_code_len > code_budget ||
            b->cpool_count < 0 || (unsigned)b->cpool_count > pool_budget ||
            (b->cpool_count && !b->cpool))
            return false;
        code_budget -= b->byte_code_len;
        pool_budget -= b->cpool_count;
        for (pos = 0; pos < b->byte_code_len; pos += size) {
            op = code[pos];
            if (op >= OP_COUNT || !(size = sizes[op]) ||
                size > b->byte_code_len - pos)
                return false;
            if (op == OP_put_arg || op == OP_set_arg ||
                (op >= OP_put_arg0 && op <= OP_put_arg3) ||
                (op >= OP_set_arg0 && op <= OP_set_arg3) ||
                op == OP_put_var_ref || op == OP_set_var_ref ||
                op == OP_put_var_ref_check || op == OP_put_var_ref_check_init ||
                (op >= OP_put_var_ref0 && op <= OP_put_var_ref3) ||
                (op >= OP_set_var_ref0 && op <= OP_set_var_ref3))
                return false;
            /* Positive whitelist: eval/apply_eval, arguments/rest exposure,
             * with and all make/put reference forms are absent. New unknown
             * upstream opcodes cannot silently widen this proof.
             */
            switch (op) {
#define FRAME_OP(id) case OP_##id:
#include "src/common/call/quickjs-interpreter-opcodes.h"
#undef FRAME_OP
            case OP_for_of_start: case OP_for_of_next: case OP_iterator_close:
            case OP_catch: case OP_gosub: case OP_ret: case OP_nip_catch:
            case OP_check_object: case OP_set_name:
                break;
            default:
                return false;
            }
        }
        /* All bytecode constants, including constructors and descendants
         * never executed on the current path, participate in the proof.
         */
        for (i = 0; i < (unsigned)b->cpool_count; i++) {
            const JSFunctionBytecode *child;
            if (JS_VALUE_GET_TAG(b->cpool[i]) != JS_TAG_FUNCTION_BYTECODE)
                continue;
            child = (JSFunctionBytecode *)JS_VALUE_GET_PTR(b->cpool[i]);
            if (!child) return false;
            for (j = 0; j < count && work[j] != child; j++) {}
            if (j != count) continue;
            if (count == countof(work)) return false;
            work[count++] = child;
        }
    }
    return true;
}
"""
