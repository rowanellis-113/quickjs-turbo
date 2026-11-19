/* Activation-local JSON callbacks, reusing the existing prepared capsule ABI.
 * Capsule types/accessors are generated from quickjs-interpreter-prepared-callback.h.
 * The traversal itself is extracted from the selected upstream quickjs.c. */
#include <stdatomic.h>
#ifdef _MSC_VER
#include <intrin.h>
#define JSONCB_CODE __declspec(code_seg(".qjs$zzjsonC")) __declspec(noinline)
#define JSONCB_INLINE static __forceinline
#else
#define JSONCB_CODE __attribute__((section(".qjsjson$C"), noipa))
#define JSONCB_INLINE static inline __attribute__((always_inline))
#endif
#define CALLBACK_INLINE JSONCB_INLINE
/* GENERATED_CALLBACK_CAPSULE */
#ifdef _MSC_VER
extern unsigned char JS_FrameJSONLoad8(const unsigned char *);
extern _Bool JS_FrameJSONCAS8(unsigned char *, unsigned char *, unsigned char);
#endif

typedef struct FrameJSONCallbackPair {
    JSFrameCallbackScope calls[2];
} FrameJSONCallbackPair;
extern JSValue JS_FramePreparedCallbackSelect(JSContext *, JSValueConst, JSValueConst, JSValueConst,
                                              int, JSValueConst *, int, void *);
extern JSValue JS_LegacyJSONStringify(JSContext *, JSValueConst, JSValueConst, JSValueConst);

JSONCB_INLINE void frame_json_callback_init(FrameJSONCallbackPair *pair)
{
    unsigned i;
    for (i = 0; i < 2; i++) {
        pair->calls[i].callee = JS_UNDEFINED;
        pair->calls[i].segment.next = NULL;
    }
}
JSONCB_INLINE void frame_json_callback_clear(JSContext *ctx, FrameJSONCallbackPair *pair)
{
    unsigned i;
    for (i = 0; i < 2; i++) {
        JSFrameCallbackScope *call = &pair->calls[i];
        JSFrameCallbackSegment *next, *following;
        for (next = call->segment.next; next; next = following) {
            following = next->next;
            js_free(ctx, next);
        }
        JS_FreeValue(ctx, call->callee);
    }
}
JSONCB_INLINE int frame_json_callback_available(JSContext *ctx)
{
    JSFrameCallbackHost *host = frame_callback_host();
    JSRuntime *rt;
    size_t used, committed;
    unsigned char control;
    uintptr_t sp = frame_callback_sp();
    if (!host || host->kind)
        return 0;
    memcpy(&rt, host->state + 56, 8);
    memcpy(&used, host->state + 32, 8);
    memcpy(&committed, host->state + CALLBACK_COMMITTED, 8);
    if (rt != ctx->rt || used != committed || sp < sizeof(FrameJSONCallbackPair) + 4096 ||
        sp - (sizeof(FrameJSONCallbackPair) + 4096) < ctx->rt->stack_limit)
        return 0;
#ifdef _MSC_VER
    control = JS_FrameJSONLoad8((const unsigned char *)&frame_callback_control);
#else
    control = atomic_load_explicit(&frame_callback_control, memory_order_relaxed);
#endif
    if (!control) {
        unsigned char expected = 0;
        control = getenv("QJS_DISABLE_PREPARED_CALLBACK") ? 2 : 1;
#ifdef _MSC_VER
        if (!JS_FrameJSONCAS8((unsigned char *)&frame_callback_control, &expected, control))
            control = expected;
#else
        if (!atomic_compare_exchange_strong_explicit(&frame_callback_control, &expected, control,
                                                     memory_order_relaxed, memory_order_relaxed))
            control = expected;
#endif
    }
    return control == 1;
}
JSONCB_INLINE int frame_json_callback_bind(JSContext *ctx, JSValueConst callee, int argc,
                                           JSFrameCallbackScope *call)
{
    JSObject *object;
    JSFunctionBytecode *b;
    JSFrameCallbackHost *host;
    JSFrameCallbackHeader *frame;
    size_t bytes;
    if (JS_VALUE_GET_TAG(callee) != JS_TAG_OBJECT)
        return 0;
    object = JS_VALUE_GET_OBJ(callee);
    if (object->class_id != JS_CLASS_BYTECODE_FUNCTION)
        return 0;
    b = object->u.func.function_bytecode;
    if ((FRAME_KIND(b) & 7) != 3 || b->var_ref_count || b->arg_count > argc ||
        frame_callback_may_have_leaf(b))
        return 0;
    bytes = 128 + sizeof(JSValue) * (b->var_count + b->stack_size);
    if (bytes > sizeof(call->data))
        return 0;
    host = frame_callback_host();
    if (!host || host->kind)
        return 0;
    call->ctx = ctx;
    call->callee = js_dup(callee);
    call->bytecode = b;
    call->frame_bytes = bytes;
    call->host = host;
    call->callback_argc = argc;
    call->reserved = 0;
    call->segment.next = NULL;
    call->segment.capacity = sizeof(call->data);
    call->segment.used = 0;
    call->segment.data = call->data;
    memset(call->state, 0, sizeof(call->state));
    memcpy(call->state + 56, &ctx->rt, 8);
    memcpy(call->state + CALLBACK_CALLER, &ctx, 8);
    memcpy(call->state + CALLBACK_SITES, host->state + CALLBACK_SITES, 8);
    memcpy(call->state + CALLBACK_NEXT, host->state + CALLBACK_NEXT, 8);
    call->state[CALLBACK_DIRECT] = host->state[CALLBACK_DIRECT];
    call->barrier.state = call->state;
    call->barrier.kind = 4;
    frame = (JSFrameCallbackHeader *)call->data;
    memset(frame, 0, sizeof(*frame));
    frame->sf.cur_func = call->callee;
    frame->sf.var_buf = (JSValue *)(call->data + 128);
    frame->sf.arg_count = argc;
    frame->sf.is_strict_mode = b->is_strict_mode;
    ((unsigned char *)&frame->sf)[62] = 1;
    frame->bytecode = b;
    frame->segment = &call->segment;
    frame->frame_bytes = (uint32_t)bytes;
    return 1;
}
JSONCB_INLINE JSValue frame_json_callback_call(JSContext *ctx, JSValueConst func,
                                               JSValueConst this_val, int argc, JSValueConst *argv,
                                               void *opaque, unsigned kind)
{
    FrameJSONCallbackPair *pair = opaque;
    JSFrameCallbackScope *call = &pair->calls[kind];
    if (JS_IsUndefined(call->callee) && !frame_json_callback_bind(ctx, func, argc, call))
        return JS_FramePreparedCallbackSelect(ctx, func, this_val, JS_UNDEFINED, argc, argv, 2,
                                              NULL);
    return JS_FramePreparedCallbackSelect(ctx, func, this_val, JS_UNDEFINED, argc, argv, 2, call);
}
JSONCB_INLINE JSValue frame_json_callback_free(JSContext *ctx, JSValue func, JSValueConst this_val,
                                               int argc, JSValueConst *argv, void *opaque,
                                               unsigned kind)
{
    JSValue result = frame_json_callback_call(ctx, func, this_val, argc, argv, opaque, kind);
    JS_FreeValue(ctx, func);
    return result;
}
JSONCB_INLINE int frame_json_callback_stack_overflow(JSRuntime *rt)
{
#if defined(__GNUC__) && defined(_WIN32) && defined(__x86_64__) && !defined(_MSC_VER)
    uintptr_t sp;
    __asm__ volatile("movq %%rsp,%0" : "=r"(sp));
    return unlikely(sp < rt->stack_limit);
#else
    return js_check_stack_overflow(rt, 0);
#endif
}
JSONCB_CODE static JSValue frame_json_reviver_run(JSContext *ctx, JSValueConst this_val, int argc,
                                                  JSValueConst *argv)
{
    _Alignas(16) FrameJSONCallbackPair pair;
    JSValue result;
    frame_json_callback_init(&pair);
    result = frame_json_reviver_parse(ctx, this_val, argc, argv, &pair);
    frame_json_callback_clear(ctx, &pair);
    return result;
}
JSONCB_CODE JSValue JS_FrameJSONReviver(JSContext *ctx, JSValueConst this_val, int argc,
                                        JSValueConst *argv)
{
    return js_json_parse(ctx, this_val, argc, argv);
}
JSONCB_CODE static JSValue frame_json_replacer_run(JSContext *ctx, JSValueConst obj,
                                                   JSValueConst replacer, JSValueConst space)
{
    _Alignas(16) FrameJSONCallbackPair pair;
    JSValue result;
    frame_json_callback_init(&pair);
    result = frame_json_replacer_stringify(ctx, obj, replacer, space, &pair);
    frame_json_callback_clear(ctx, &pair);
    return result;
}
/* Batch replacers alone amortize this capsule on the qualified GNU compiler. */
JSONCB_CODE JSValue JS_FrameJSONCallbackStringify(JSContext *ctx, JSValueConst obj,
                                                  JSValueConst replacer, JSValueConst space)
{
#ifdef _MSC_VER
    return JS_LegacyJSONStringify(ctx, obj, replacer, space);
#else
    JSObject *o;
    if (!JS_IsFunction(ctx, replacer) || !JS_IsObject(obj))
        return JS_LegacyJSONStringify(ctx, obj, replacer, space);
    o = JS_VALUE_GET_OBJ(obj);
    if (!((o->class_id == JS_CLASS_ARRAY && o->fast_array && o->u.array.count >= 16) ||
          (o->class_id == JS_CLASS_OBJECT && !o->is_exotic && o->shape->prop_count >= 16)))
        return JS_LegacyJSONStringify(ctx, obj, replacer, space);
    if (!frame_json_callback_available(ctx))
        return JS_LegacyJSONStringify(ctx, obj, replacer, space);
    return frame_json_replacer_run(ctx, obj, replacer, space);
#endif
}
