#ifndef QJS_FRAME_CONTEXT_TYPES
#define QJS_FRAME_CONTEXT_TYPES
#include "src/common/internal/interpreter-env.h"
/*
 * Explicit JavaScript frames. Compiled separately from the legacy interpreter.
 * Copyright (c) 2026. MIT license, as in quickjs.c.
 */
#if defined(_MSC_VER)
#define FRAME_CODE __declspec(code_seg(".qjsvm$z")) no_inline
#define FRAME_WINDOW_CODE __declspec(code_seg(".qjsvm$zw")) no_inline
#define FRAME_OPCODE_CODE __declspec(code_seg(".qjsvm$zo")) no_inline
#define FRAME_PROPERTY_CODE __declspec(code_seg(".qjsprop")) no_inline
#define FRAME_HOST_CODE __declspec(code_seg(".qjsvm$zh")) no_inline
#define FRAME_INLINE __forceinline
#define FRAME_VAR_REFS() var_refs
#elif defined(QJS_INTERP_FRAME_LINUX)
#define FRAME_CODE __attribute__((section(".text.qjs_frame"), noipa))
#define FRAME_WINDOW_CODE __attribute__((section(".text.qjs_frame_window"), noipa))
#define FRAME_OPCODE_CODE __attribute__((section(".text.qjs_frame_opcode"), noipa))
#define FRAME_PROPERTY_CODE __attribute__((section(".text.qjs_frame_property"), noipa))
#define FRAME_HOST_CODE __attribute__((section(".text.qjs_frame_host"), noipa))
#define FRAME_INLINE inline __attribute__((always_inline))
#define FRAME_VAR_REFS() (JS_VALUE_GET_OBJ(sf->cur_func)->u.func.var_refs)
#else
#define FRAME_CODE __attribute__((section(".qjsvm$z"), noipa))
#define FRAME_WINDOW_CODE __attribute__((section(".qjsvm$zw"), noipa))
#define FRAME_OPCODE_CODE __attribute__((section(".qjsvm$zo"), noipa))
#define FRAME_PROPERTY_CODE __attribute__((section(".qjsprop"), noipa))
#define FRAME_HOST_CODE __attribute__((section(".qjsvm$zh"), noipa))
#define FRAME_INLINE inline __attribute__((always_inline))
#define FRAME_VAR_REFS() (JS_VALUE_GET_OBJ(sf->cur_func)->u.func.var_refs)
#endif

/* Experimental metadata occupies verified, zero-initialized padding. Access
 * through unsigned char keeps the core's original type definitions identical.
 * The internal-entry adapter only redirects audited call-target operands;
 * original type definitions, instruction layout and unwind remain intact. */
#include "src/common/call/interpreter-bytecode-metadata.inc"
/* 0 unknown, 1 supported with argument writes, 2 unsupported, 3 supported
 * with read-only argument slots, 5 supported with captured argument slots.
 * Bit 8 independently records the presence of a local var-ref table.
 * Bit 16 publishes native-call preparation data: frame bytes at 18..19,
 * locals at 20, formals at 21, in verified original header padding. This
 * belongs to the live bytecode, not a weak call-site address hint. Publication
 * follows all descriptor writes. Kind revalidation clears the validity bit.
 * GNU scoped sort reserves bits32/64/128 for its per-bytecode controls. Its
 * admission runs only after existing readonly support is established. Both
 * controls leave every mask above and native metadata mask21 unchanged.
 * Bit zero is the supported-function bit; bit two requires owned arguments. */
#define FRAME_SUPPORTED(b) (FRAME_KIND(b) & 1)
/* Generic shortcuts require plain readonly slots. Captured kind7 is
 * admitted only by native builders that own a complete lifetime proof. */
#define FRAME_READONLY_ARGS(b) ((FRAME_KIND(b) & 7) == 3)
#define FRAME_CAPTURED_ARGS(b) (FRAME_KIND(b) & 4)
#define FRAME_STATE(rt) (((unsigned char *)(rt))[offsetof(JSRuntime, current_stack_frame) - 1])
#ifdef QJS_INTERP_FRAME_INTERNAL_ENTRY
#define FRAME_INTERNAL_STATE(rt)                                                                   \
    (((unsigned char *)(rt))[offsetof(JSRuntime, current_stack_frame) - 2])
_Static_assert(offsetof(JSRuntime, in_free) + sizeof(bool) <=
                   offsetof(JSRuntime, current_stack_frame) - 2,
               "internal entry padding");
#ifdef QJS_INTERP_FRAME_REGISTER_ABI
#define FRAME_REGISTER_STATE(rt)                                                                   \
    (((unsigned char *)(rt))[offsetof(JSRuntime, current_stack_frame) - 3])
#define FRAME_HOST_STATE(rt) (((unsigned char *)(rt))[offsetof(JSRuntime, current_stack_frame) - 4])
_Static_assert(offsetof(JSRuntime, in_free) + sizeof(bool) <=
                   offsetof(JSRuntime, current_stack_frame) - 4,
               "register and host mode padding");
/* VM configuration belongs to the runtime entry contract. A callback must
 * not rescan the process environment for every interpreter activation. The
 * public/internal entry switches already have the same per-runtime lifetime. */
static FRAME_INLINE bool js_frame_register_enabled(JSRuntime *rt)
{
    if (unlikely(!FRAME_REGISTER_STATE(rt))) {
        FRAME_REGISTER_STATE(rt) = !qjs_internal_interp_register_disabled() ? 1 : 2;
#ifdef QJS_INTERP_FRAME_DIAGNOSTICS
        if (qjs_internal_interp_trace_enabled())
            fprintf(stderr, "REGMODE state=%u\n", FRAME_REGISTER_STATE(rt));
#endif
    }
    return FRAME_REGISTER_STATE(rt) == 1;
}
static FRAME_INLINE bool js_frame_direct_host_enabled(JSRuntime *rt)
{
    if (unlikely(!FRAME_HOST_STATE(rt)))
        FRAME_HOST_STATE(rt) = getenv("QJS_DISABLE_DIRECT_HOST_CALL") == NULL ? 1 : 2;
    return FRAME_HOST_STATE(rt) == 1;
}
#endif
#endif
#ifdef _WIN64
_Static_assert(offsetof(JSFunctionBytecode, byte_code_buf) ==
                   QJS_ABI_OFF_JSFunctionBytecode_byte_code_buf,
               "bytecode padding");
_Static_assert(offsetof(JSRuntime, current_stack_frame) ==
                   QJS_ABI_OFF_JSRuntime_current_stack_frame,
               "runtime padding");
#endif

#ifdef _WIN64
_Static_assert(sizeof(JSValue) == QJS_ABI_SIZE_JSValue, "native value layout");
_Static_assert(sizeof(JSStackFrame) == QJS_ABI_SIZE_JSStackFrame, "legacy frame layout");
_Static_assert(sizeof(JSFunctionBytecode) == QJS_ABI_SIZE_JSFunctionBytecode,
               "legacy bytecode layout");
_Static_assert(sizeof(JSRuntime) == QJS_ABI_SIZE_JSRuntime, "legacy runtime layout");
_Static_assert(sizeof(JSContext) == QJS_ABI_SIZE_JSContext, "legacy context layout");
_Static_assert(sizeof(JSObject) == QJS_ABI_SIZE_JSObject, "legacy object layout");
#endif

#define FRAME_INITIAL_BYTES 4096
#define FRAME_CACHE_SLOTS 16
#define FRAME_MAX_CODE 2048
#define FRAME_HEADER_BYTES ((sizeof(JSFrame) + 15) & ~(size_t)15)
#define FRAME_CAPTURE_BYTES(b)                                                                     \
    ((sizeof(JSVarRef *) * (size_t)(b)->var_ref_count + 15) & ~(size_t)15)

/* Body copied from the core's close_lexical_var. Inline only in the
 * experimental TU: retaining its otherwise dead core COMDAT moves entries.
 * close_var_ref itself is the original, already-live compiled helper. */
static FRAME_INLINE void js_frame_close_lexical_var(JSContext *ctx, JSFunctionBytecode *b,
                                                    JSStackFrame *sf, int var_idx)
{
    JSVarRef *var_ref;
    int var_ref_idx;

    var_ref_idx = b->vardefs[b->arg_count + var_idx].var_ref_idx;
    var_ref = sf->var_refs[var_ref_idx];
    if (var_ref) {
        close_var_ref(ctx->rt, var_ref);
        sf->var_refs[var_ref_idx] = NULL;
    }
}

#ifdef QJS_INTERP_FRAME_INTERNAL_ENTRY
/* Data frames must consume the SAME budget used by native helpers/reentry.
 * Raising the logical top with the limit also lets JS_SetMaxStackSize called
 * by a host callback recompute that limit without losing active frame charges.
 * Changing threads (JS_UpdateStackTop) happens outside an active JS execution.
 * An unlimited stack keeps limit zero, but still tracks the logical top. */
static FRAME_INLINE void js_frame_charge_stack(JSRuntime *rt, size_t bytes)
{
    rt->stack_top += bytes;
    if (rt->stack_limit)
        rt->stack_limit += bytes;
}

static FRAME_INLINE void js_frame_release_stack(JSRuntime *rt, size_t bytes)
{
    rt->stack_top -= bytes;
    if (rt->stack_limit)
        rt->stack_limit -= bytes;
}
#endif

typedef struct JSFrameSegment {
    struct JSFrameSegment *next;
    size_t capacity, used;
    uint8_t *data;
} JSFrameSegment;
_Static_assert(offsetof(JSFrameSegment, used) == 16 && offsetof(JSFrameSegment, data) == 24,
               "private segment cursors are independent of upstream context layout");

typedef struct JSFrame {
    JSStackFrame sf;
    FRAME_STACK_TAIL_PADDING
    JSFunctionBytecode *bytecode;
    JSValue this_value; /* borrowed until the caller consumes its call operands */
    JSValue *saved_sp;
    JSFrameSegment *segment;
    uint32_t frame_bytes;
    uint16_t owned_args; /* cleanup suffix; allocation can be larger */
    uint16_t pending;    /* low 15 bits: operand count, high bit: tail return */
} JSFrame;

/* Ordinary native frames already publish the same parent in sf.prev_frame.
 * A root may have an outer C/coroutine frame, which is NOT a JSFrame. Byte 62
 * is verified padding after is_strict_mode in the selected C header. Initialize it after
 * all named SF fields; no core type or GC/captured-slot address is changed. */
#define FRAME_ROOT_OFFSET (offsetof(JSStackFrame, is_strict_mode) + 2)
_Static_assert(FRAME_ROOT_OFFSET < offsetof(JSStackFrame, cur_sp),
               "native activation root marker requires C frame padding");
#define FRAME_ROOT(frame) (((unsigned char *)&(frame)->sf)[FRAME_ROOT_OFFSET])
/* Disjoint JS-frame flags; cur_sp remains the real GC-visible cursor.
 * Bit0 belongs to native C-window reuse. Bit1 tags a paused JS next call.
 * Logical native frames are a separate type: var_buf NULL and tag199. */
#define FRAME_FLAGS_OFFSET (FRAME_ROOT_OFFSET + 1)
#define FRAME_FLAG_C_WINDOW 1u
#define FRAME_FLAG_NEXT_CHECKPOINT 2u
_Static_assert(FRAME_FLAGS_OFFSET == 63 && FRAME_FLAGS_OFFSET < offsetof(JSStackFrame, cur_sp) &&
                   !(FRAME_FLAG_C_WINDOW & FRAME_FLAG_NEXT_CHECKPOINT),
               "disjoint native C-window/next flags in original SF padding63");
#define FRAME_FLAGS(frame) (((unsigned char *)&(frame)->sf)[FRAME_FLAGS_OFFSET])
#define FRAME_CHECKPOINT(frame) (FRAME_FLAGS(frame) & FRAME_FLAG_NEXT_CHECKPOINT)
#define FRAME_SET_CHECKPOINT(frame) (FRAME_FLAGS(frame) |= FRAME_FLAG_NEXT_CHECKPOINT)
#define FRAME_CLEAR_CHECKPOINT(frame)                                                              \
    (FRAME_FLAGS(frame) &= (unsigned char)~FRAME_FLAG_NEXT_CHECKPOINT)
static FRAME_INLINE JSFrame *js_frame_parent(JSFrame *frame)
{
    return FRAME_ROOT(frame) ? NULL : (JSFrame *)frame->sf.prev_frame;
}
static FRAME_INLINE size_t js_frame_segment_mark(JSFrame *frame)
{
    return (uint8_t *)frame - frame->segment->data;
}
static FRAME_INLINE unsigned js_frame_pending_count(JSFrame *frame)
{
    return frame->pending & 0x7fff;
}
static FRAME_INLINE bool js_frame_pending_tail(JSFrame *frame)
{
    return (frame->pending & 0x8000) != 0;
}

typedef struct JSFrameCallSite {
    uintptr_t continuation;
    uintptr_t identity;
    uintptr_t code_identity; /* address hints only; all reads use the live callee */
    int argc;
} JSFrameCallSite;

_Static_assert(FRAME_CACHE_SLOTS == 16 && sizeof(JSFrameCallSite) == 32 &&
                   offsetof(JSFrameCallSite, continuation) == 0 &&
                   offsetof(JSFrameCallSite, identity) == 8 &&
                   offsetof(JSFrameCallSite, code_identity) == 16 &&
                   offsetof(JSFrameCallSite, argc) == 24,
               "global/lexical hints share the 16 existing 32-byte weak cells");

#ifdef QJS_INTERP_FRAME_REGISTER_ABI
#include "src/common/call/quickjs-interpreter-register.h"
#ifdef QJS_INTERP_FRAME_INTERNAL_ENTRY
/* Retain the last committed quota during pure JS execution. C must see the
 * exact live count; a negative delta uses defined unsigned pointer-sized
 * wraparound to remove a previously committed, now-returned frame charge. */
static FRAME_INLINE void js_frame_begin_c(JSFrameRegisterState *state)
{
    if (state->used_bytes != state->committed_bytes) {
        js_frame_charge_stack(state->rt, state->used_bytes - state->committed_bytes);
#ifdef QJS_INTERP_FRAME_DIAGNOSTICS
        state->budget_syncs++;
#endif
    }
}

/* Shared C pushes/pops keep the runtime quota exact. Cache the effective
 * native limit after any interpreter-count or host stack-size change. Outer C
 * activation charges stay included; zero remains the unlimited sentinel. */
static FRAME_INLINE void js_frame_finish_c(JSFrameRegisterState *state)
{
    uintptr_t limit = state->rt->stack_limit;
    if (state->committed_bytes != state->used_bytes || state->shared_stack_limit != limit) {
        state->committed_bytes = state->used_bytes;
        state->shared_stack_limit = limit;
        state->native_stack_limit = limit ? limit - state->used_bytes : 0;
#ifdef QJS_INTERP_FRAME_DIAGNOSTICS
        state->budget_refreshes++;
#endif
    }
}
#endif
#endif

#endif
