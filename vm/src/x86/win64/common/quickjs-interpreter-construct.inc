/* Ordinary construction in the current register activation.
 * All admission is complete before object creation. FRAME_ROOT==3 is a real
 * JS child with constructor return semantics, not a public/root activation.
 * The parent's two call operands become [owned this, owned function]. */
#include <stdatomic.h>
_Static_assert(sizeof(JSFrame) == 128 && FRAME_ROOT_OFFSET == 62,
               "constructor continuation retains the native frame prefix");
_Static_assert(sizeof(_Atomic(unsigned)) == 4 && _Alignof(_Atomic(unsigned)) >= 4 &&
                   ATOMIC_INT_LOCK_FREE >= 1,
               "constructor startup policy retains its atomic ABI");
#if defined(_MSC_VER)
#pragma section(".qjsrmet", read, write)
__declspec(allocate(".qjsrmet")) static _Atomic(unsigned) js_frame_construct_policy;
#else
static _Atomic(unsigned) js_frame_construct_policy __attribute__((section(".qjsrmet")));
#endif
static FRAME_INLINE bool js_frame_construct_enabled(void)
{
    unsigned policy = atomic_load_explicit(&js_frame_construct_policy, memory_order_relaxed);
    if (!policy) {
        policy = !atomic_is_lock_free(&js_frame_construct_policy) ||
                         getenv("QJS_DISABLE_FRAME_CONSTRUCT_CONTINUATION")
                     ? 2
                     : 1;
        atomic_store_explicit(&js_frame_construct_policy, policy, memory_order_relaxed);
    }
    return policy == 1;
}

static FRAME_INLINE JSValue js_frame_construct_result(JSContext *ctx, JSFrame *parent,
                                                      JSValue result)
{
    JSValue *slot = parent->saved_sp - js_frame_pending_count(parent);
    JSValue object = *slot;
    /* A callback/finalizer must never see a consumed owner in the stack. */
    *slot = JS_UNDEFINED;
    if (JS_IsObject(result) || JS_IsException(result)) {
        JS_FreeValue(ctx, object);
        return result;
    }
    JS_FreeValue(ctx, result);
    return object;
}

FRAME_CODE int JS_FrameVarargsConstructHeapReturn(JSFrameRegisterState *state)
{
    JSFrame *frame = state->frame;
    JSContext *ctx = frame->bytecode->realm;
    JSValue *begin = frame->saved_sp - js_frame_pending_count(frame);
    JSValue *end = frame->saved_sp;
    JSValue result;
    js_frame_begin_c(state);
    frame->sf.cur_sp = end;
    result = js_frame_construct_result(ctx, frame, state->result);
    state->result = result;
    for (JSValue *slot = begin; slot < end; slot++) {
        JSValue consumed = *slot;
        *slot = JS_UNDEFINED;
        JS_FreeValue(ctx, consumed);
    }
    *begin = result;
    state->sp = begin + 1;
    frame->sf.cur_sp = begin + 1;
    frame->saved_sp = begin + 1;
    frame->pending = 0;
    js_frame_finish_c(state);
    return 0;
}
