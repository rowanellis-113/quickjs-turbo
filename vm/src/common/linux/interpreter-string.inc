/* Linux policy and typed boundaries for the shared string algorithms. */
#define LINUX_STRING_CODE __attribute__((section(".text.qjs_strings"), noipa))
int JS_FrameStringIndexStep(JSFrameRegisterState *state);
__attribute__((visibility("hidden"),
               section(".bss.qjs_strings"))) _Atomic unsigned char qjs_linux_string_add_mode;
static _Atomic unsigned char qjs_linux_string_local_add_mode
    __attribute__((section(".bss.qjs_strings")));

static inline unsigned char linux_string_policy(_Atomic unsigned char *control, const char *name)
{
    unsigned char value = atomic_load_explicit(control, memory_order_relaxed);
    if (unlikely(!value)) {
        value = getenv(name) ? 2 : 1;
        atomic_store_explicit(control, value, memory_order_relaxed);
    }
    return value;
}

_Static_assert(ATOMIC_CHAR_LOCK_FREE == 2 && sizeof(JSValue) == 16 &&
                   offsetof(JSFrame, bytecode) == 80,
               "Linux native string lane uses the audited VM/value protocol");

LINUX_STRING_CODE JSValue JS_FrameLinuxSharedConcatSelect(JSContext *ctx, JSValue left,
                                                          JSValue right)
{
    if (JS_VALUE_GET_TAG(left) == JS_TAG_STRING && JS_VALUE_GET_TAG(right) == JS_TAG_STRING) {
        JSString *a = JS_VALUE_GET_STRING(left), *b = JS_VALUE_GET_STRING(right);
        if (a->len > JS_STRING_ROPE_SHORT_LEN && a->len <= JS_STRING_ROPE_SHORT2_LEN &&
            a->header.ref_count > 1 && b->len && b->len <= JS_STRING_ROPE_SHORT_LEN)
            return JS_FrameSharedConcatRope(ctx, left, right);
    }
    return JS_ConcatString(ctx, left, right);
}

LINUX_STRING_CODE int JS_FrameLinuxStringConcat(JSFrameRegisterState *state)
{
    JSFrame *frame = state->frame;
    JSValue *sp = state->sp;
    JSContext *ctx = frame->bytecode->realm;
    JSValue result;
    /* Operands have already passed the primitive/string guard. The original
     * consuming helper still owns conversion, Symbol exceptions and OOM. */
    frame->sf.cur_pc = state->pc + 1;
    js_frame_begin_c(state);
    result = JS_FrameLinuxSharedConcatSelect(ctx, sp[-2], sp[-1]);
    state->pc++;
    if (JS_IsException(result)) {
        sp[-2] = JS_UNDEFINED;
        sp[-1] = JS_UNDEFINED;
        state->exception_pending = true;
        js_frame_finish_c(state);
        return JS_FrameInterpSlow(state);
    }
    sp[-2] = result;
    state->sp = sp - 1;
    js_frame_finish_c(state);
    return 0;
}

LINUX_STRING_CODE int JS_FrameLinuxStringAdd(JSFrameRegisterState *state)
{
    JSValue *sp = state->sp;
    int left = JS_VALUE_GET_TAG(sp[-2]), right = JS_VALUE_GET_TAG(sp[-1]);
    if ((!tag_is_string(left) && !tag_is_string(right)) || left == JS_TAG_OBJECT ||
        right == JS_TAG_OBJECT ||
        linux_string_policy(&qjs_linux_string_add_mode, "QJS_DISABLE_NATIVE_ADD_BOUNDARY") != 1)
        return JS_FrameInterpBig_add(state);
    if (left == JS_TAG_STRING_ROPE && right == JS_TAG_STRING &&
        JS_VALUE_GET_STRING_ROPE(sp[-2])->header.ref_count == 2)
        return JS_FrameLocalRopeAppendStep(state);
    return JS_FrameLinuxStringConcat(state);
}

LINUX_STRING_CODE int JS_FrameLinuxStringSlow(JSFrameRegisterState *state)
{
    if (!state->exception_pending && state->frame) {
        unsigned opcode = *state->pc;
        if ((opcode == OP_get_array_el || opcode == OP_get_array_el2) &&
            JS_VALUE_GET_TAG(state->sp[-2]) == JS_TAG_STRING &&
            JS_VALUE_GET_TAG(state->sp[-1]) == JS_TAG_INT)
            return JS_FrameStringIndexStep(state);
    }
    return JS_FrameInterpSlow(state);
}
