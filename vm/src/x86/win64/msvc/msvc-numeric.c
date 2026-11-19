#pragma code_seg(".qjscold$zzzzzzzzzzzzzzzzzzzzzzstringnumeric")
#include "src/common/call/interpreter-retained-context.inc"

#define NUMERIC_INITIAL_MODE 1

#pragma section(".qjzzpm", read, write)
__declspec(allocate(".qjzzpm")) __declspec(align(4)) volatile unsigned JS_FrameStringNumericMode =
    NUMERIC_INITIAL_MODE;
extern int JS_FrameInterpGenericFast(JSFrameRegisterState *, JSValue *, int, bool);
extern JSValue qjs_frame_core_js_string_charCodeAt(JSContext *, JSValueConst, int, JSValueConst *);
extern JSValue qjs_frame_core_js_string_codePointAt(JSContext *, JSValueConst, int, JSValueConst *);
static __forceinline const uint8_t *numeric_data(JSString *s)
{
    if (s->kind == JS_STRING_KIND_NORMAL)
        return (const uint8_t *)&s[1];
    if (s->kind == JS_STRING_KIND_SLICE) {
        JSStringSlice *slice = (void *)&s[1];
        return (const uint8_t *)&slice->parent[1] + slice->start;
    }
    return *(const uint8_t **)&s[1];
}
static __forceinline uint32_t numeric_unit(const uint8_t *data, uint32_t index, bool wide)
{
    return wide ? ((const uint16_t *)data)[index] : data[index];
}
__declspec(noinline) int JS_FrameStringNumericHost(JSFrameRegisterState *state, JSValue *argv,
                                                   int argc, bool method)
{
    /* All guards precede the interrupt/result stores. No call/GC/host observer
    occurs on a successful path;caller retains all receiver/argument owners. */
    if (!method || argc < 1 || JS_VALUE_GET_TAG(argv[-2]) != JS_TAG_STRING ||
        JS_VALUE_GET_TAG(argv[0]) != JS_TAG_INT)
        goto slow;
    JSRuntime *rt = state->rt;
    if (((const unsigned char *)rt)[offsetof(JSRuntime, module_normalize_has_attr) + 1] != 1 ||
        (((const unsigned char *)rt)[offsetof(JSRuntime, current_stack_frame) - 5] & 11) != 1 ||
        state->exception_pending)
        goto slow;
    JSObject *callee = JS_VALUE_GET_OBJ(argv[-1]);
    if (callee->class_id != JS_CLASS_C_FUNCTION || callee->u.cfunc.cproto != JS_CFUNC_generic ||
        callee->u.cfunc.length != 1)
        goto slow;
    bool point = callee->u.cfunc.c_function.generic == qjs_frame_core_js_string_codePointAt;
    if (!point && callee->u.cfunc.c_function.generic != qjs_frame_core_js_string_charCodeAt)
        goto slow;
    JSContext *ctx = state->frame->bytecode->realm;
    if (ctx->interrupt_counter <= 1)
        goto slow;
    /* Leave the full checked host path in charge of polling and stack-boundary
    behavior. This conservative reserve covers the old host's fixed frame
    plus one formal slot and its scalar builtin;it is not a tuning knob. */
    volatile unsigned char stack_marker;
    size_t used = state->used_bytes, committed = state->committed_bytes;
    uintptr_t effective_limit = rt->stack_limit;
    if (effective_limit) {
        if (used >= committed) {
            size_t delta = used - committed;
            if (delta > UINTPTR_MAX - effective_limit)
                goto slow;
            effective_limit += delta;
        } else {
            size_t delta = committed - used;
            if (delta > effective_limit)
                goto slow;
            effective_limit -= delta;
        }
    }
    if (effective_limit && ((uintptr_t)&stack_marker <= effective_limit ||
                            (uintptr_t)&stack_marker - effective_limit < 1024))
        goto slow;
    JSString *s = JS_VALUE_GET_STRING(argv[-2]);
    if (s->kind > JS_STRING_KIND_INDIRECT)
        goto slow;
    uint32_t index = (uint32_t)JS_VALUE_GET_INT(argv[0]);
    JSValue result;
    if (index >= s->len)
        result = point ? JS_UNDEFINED : JS_NAN;
    else {
        const uint8_t *data = numeric_data(s);
        bool wide = s->is_wide_char;
        uint32_t c = numeric_unit(data, index, wide);
        if (point && c >= 0xd800 && c <= 0xdbff && index + 1 < s->len) {
            uint32_t next = numeric_unit(data, index + 1, wide);
            if (next >= 0xdc00 && next <= 0xdfff)
                c = 0x10000 + ((c - 0xd800) << 10) + (next - 0xdc00);
        }
        result = JS_MKVAL(JS_TAG_INT, (int)c);
    }
    /* Original begin_c uses defined unsigned wrap for either quota direction.
    No observer ran above. Commit before caller-side operand release,which
    may invoke an allocator/finalizer and must see the full live frame charge. */
    if (used != committed) {
        rt->stack_top += used - committed;
        rt->stack_limit = effective_limit;
    }
    if (used != committed || state->shared_stack_limit != effective_limit) {
        state->committed_bytes = used;
        state->shared_stack_limit = effective_limit;
        state->native_stack_limit = effective_limit ? effective_limit - used : 0;
    }
    ctx->interrupt_counter--;
    state->result = result;
    state->exception_pending = false;
    return 0;
slow:
    return JS_FrameInterpGenericFast(state, argv, argc, method);
}
