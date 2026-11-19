/* Scoped C-to-JS admission cache. MIT.
 * One sort activation strongly owns its comparator. Bytecode and its validated
 * argument/frame geometry are immutable for that function's lifetime.
 * The paused host's native-owner slot temporarily holds an aligned stack
 * capsule tagged with bit0. Native-window admission requires owner==frame,
 * so it rejects this tag without dereferencing it. No VM executes with this
 * parent state: callbacks create their own child state. Entry/Slow invalidation
 * wins over restoration: restore only if our exact tag is still installed.
 * TLS/SF, arena cursor/capacity, quota, realm and interrupt stay per-call guards.
 * Environment ablation is read once per eligible live bytecode. Bits32/64/128
 * in private padding23 preserve all established admission/preparation bits
 * 0..4; bit128 disables prepared-state reuse. Unsupported bytecode never
 * receives these bits. Revalidation clears
 * the whole byte and its configuration; no TLS block or public type grows.
 */
typedef struct JSFrameCachedSort {
    JSContext *ctx;
    JSValue callee;
    JSFunctionBytecode *bytecode;
    size_t frame_bytes;
} JSFrameCachedSort;
typedef struct JSFrameCachedHost {
    struct JSFrameCachedHost *prev;
    unsigned char *state;
    unsigned kind;
} JSFrameCachedHost;
_Static_assert(sizeof(JSFrameCachedSort) == 40 && offsetof(JSFrameCachedSort, callee) == 8 &&
                   offsetof(JSFrameCachedSort, bytecode) == 24 &&
                   offsetof(JSFrameCachedSort, frame_bytes) == 32,
               "scoped cached-call ABI");
_Static_assert(sizeof(JSFrameCachedHost) == 24 && offsetof(JSFrameCachedHost, state) == 8 &&
                   offsetof(JSFrameCachedHost, kind) == 16,
               "retained shared-anchor ABI");
_Static_assert(
    offsetof(JSFunctionBytecode, arg_count) == QJS_ABI_OFF_JSFunctionBytecode_arg_count &&
        offsetof(JSFunctionBytecode, var_count) == QJS_ABI_OFF_JSFunctionBytecode_var_count &&
        offsetof(JSFunctionBytecode, stack_size) == QJS_ABI_OFF_JSFunctionBytecode_stack_size &&
        offsetof(JSFunctionBytecode, var_ref_count) == QJS_ABI_OFF_JSFunctionBytecode_var_ref_count,
    "cached immutable geometry");
#ifdef QJS_INTERP_FRAME_DIAGNOSTICS
#define SORT_CACHE_OWNER 2416
#define SORT_CACHE_COMMITTED 2304
#else
#define SORT_CACHE_OWNER 96
#define SORT_CACHE_COMMITTED 64
#endif
static inline __attribute__((always_inline)) void *frame_sort_tls_address(void)
{
    return NULL;
}

/* The original arena ABI is mirrored locally; no public/core type grows.
 * A distinct stack segment keeps a dormant root header away from getters and
 * unrelated C callbacks using the paused parent's cursor. Grown nonmoving
 * segments belong to this scope and are freed after sort, never its parent.
 * Per-invocation arguments/PC/SP/roots/quota/pending state are reset in ASM.
 * Normal and exceptional root pops still use the original Interp cleanup.
 */
typedef struct JSFramePreparedSegment {
    struct JSFramePreparedSegment *next;
    size_t capacity, used;
    unsigned char *data;
} JSFramePreparedSegment;
typedef struct JSFramePreparedHeader {
    JSStackFrame sf;
    FRAME_STACK_TAIL_PADDING
    JSFunctionBytecode *bytecode;
    JSValue this_value;
    JSValue *saved_sp;
    JSFramePreparedSegment *segment;
    uint32_t frame_bytes;
    uint16_t owned_args, pending;
} JSFramePreparedHeader;
#ifdef QJS_INTERP_FRAME_DIAGNOSTICS
#define SORT_PREP_STATE_BYTES 2448
#define SORT_PREP_DATA_OFFSET 2544
#define SORT_PREP_CALLER 2272
#define SORT_PREP_SITES 2280
#define SORT_PREP_NEXT 2288
#define SORT_PREP_DIRECT 2297
#else
#define SORT_PREP_STATE_BYTES 168
#define SORT_PREP_DATA_OFFSET 272
#define SORT_PREP_CALLER 136
#define SORT_PREP_SITES 144
#define SORT_PREP_NEXT 152
#define SORT_PREP_DIRECT 161
#endif
enum { SORT_PREP_ARENA_BYTES = 2048 };
typedef struct JSFramePreparedSort {
    JSFrameCachedSort cache;
    JSFrameCachedHost barrier;
    JSFramePreparedSegment segment;
    _Alignas(16) unsigned char state[SORT_PREP_STATE_BYTES];
    _Alignas(16) unsigned char data[SORT_PREP_ARENA_BYTES];
} JSFramePreparedSort;
_Static_assert(sizeof(JSFramePreparedSegment) == 32 &&
                   offsetof(JSFramePreparedSegment, used) == 16 &&
                   offsetof(JSFramePreparedSegment, data) == 24,
               "private prepared segment ABI");
_Static_assert(sizeof(JSFramePreparedHeader) == 128 &&
                   offsetof(JSFramePreparedHeader, bytecode) == 80 &&
                   offsetof(JSFramePreparedHeader, this_value) == 88 &&
                   offsetof(JSFramePreparedHeader, saved_sp) == 104 &&
                   offsetof(JSFramePreparedHeader, segment) == 112 &&
                   offsetof(JSFramePreparedHeader, frame_bytes) == 120 &&
                   offsetof(JSFramePreparedHeader, pending) == 126,
               "original frame header ABI");
_Static_assert(offsetof(JSFramePreparedSort, barrier) == 40 &&
                   offsetof(JSFramePreparedSort, segment) == 64 &&
                   offsetof(JSFramePreparedSort, state) == 96 &&
                   offsetof(JSFramePreparedSort, data) == SORT_PREP_DATA_OFFSET,
               "scope capsule keeps the established first40 bytes");
_Static_assert(offsetof(JSRuntime, current_stack_frame) ==
                       QJS_ABI_OFF_JSRuntime_current_stack_frame &&
                   offsetof(JSRuntime, stack_limit) == QJS_ABI_OFF_JSRuntime_stack_limit &&
                   offsetof(JSStackFrame, cur_pc) == QJS_ABI_OFF_JSStackFrame_cur_pc &&
                   offsetof(JSStackFrame, cur_sp) == QJS_ABI_OFF_JSStackFrame_cur_sp &&
                   FRAME_STACK_CORO_OFFSET_VALID,
               "prepared roots and quota ABI");
extern JSValue JS_FramePreparedArraySort(JSContext *, JSValueConst, int, JSValueConst *,
                                         JSFrameCachedHost *, JSFunctionBytecode *, size_t);
/* Retain the established specialized ChildLeaf path. These exact recognized
 * immutable bytecode shapes are tested once per scope, not interpreted here.
 * Nonmatching comparators (including the ordinary a-b shape) remain eligible.
 */
static inline __attribute__((always_inline)) int frame_sort_has_leaf(JSFunctionBytecode *b)
{
    uint64_t word;
    if (b->var_count)
        return 0;
    if (b->byte_code_len == 4) {
        uint32_t small;
        memcpy(&small, b->byte_code_buf, 4);
        return (small & UINT32_C(4294902015)) == UINT32_C(681312471);
    }
    if (b->byte_code_len == 8) {
        memcpy(&word, b->byte_code_buf, 8);
        return (word & UINT64_C(0xffffffff00ffffff)) == UINT64_C(0x28a3ba9c009cd8d7);
    }
    return 0;
}

#ifndef QJS_PREPARED_SCOPE_ONLY
NATIVE_SORT_CODE JSValue JS_FrameCachedArraySort(JSContext *ctx, JSValueConst this_val, int argc,
                                                 JSValueConst *argv)
{
    unsigned char *kind;
    JSFrameCachedHost *host;
    JSFunctionBytecode *b;
    JSObject *p;
    _Alignas(16) JSFrameCachedSort call;
    unsigned char *owner;
    uintptr_t previous, tagged, current;
    size_t used, committed;
    JSRuntime *host_rt;
    JSValue result;
    if (argc < 1 || JS_VALUE_GET_TAG(argv[0]) != JS_TAG_OBJECT)
        goto original;
    p = JS_VALUE_GET_OBJ(argv[0]);
    if (p->class_id != JS_CLASS_BYTECODE_FUNCTION)
        goto original;
    b = p->u.func.function_bytecode;
    /* Unvalidated/capturing/writing/under-applied targets retain old admission.
       First cold comparison performs the original validator, without reordering
       sort's callable check, getters or exception observations. */
    if ((FRAME_KIND(b) & 7) != 3 || b->var_ref_count || b->arg_count > 2)
        goto original;
    kind = &FRAME_KIND(b);
    if (!(*kind & 96)) {
        *kind |= getenv("QJS_DISABLE_CACHED_SORT_CALL") ? 64 : 32;
        if (getenv("QJS_DISABLE_PREPARED_SORT_CALL"))
            *kind |= 128;
    }
    if (*kind & 64)
        goto original;
    host = *(JSFrameCachedHost **)frame_sort_tls_address();
    if (!host || host->kind)
        goto original;
    memcpy(&host_rt, host->state + 56, sizeof(host_rt));
    memcpy(&used, host->state + 32, sizeof(used));
    memcpy(&committed, host->state + SORT_CACHE_COMMITTED, sizeof(committed));
    if (host_rt != ctx->rt || used != committed)
        goto original;
    /* Do not reserve the larger C capsule before checking the physical limit.
     * If the optional workspace cannot fit, preserve old quota/error behavior.
     * The existing ChildFast check remains before every prepared invocation. */
    if (!(*kind & 128) && !frame_sort_has_leaf(b)) {
        size_t bytes = 128 + sizeof(JSValue) * (b->var_count + b->stack_size);
        uintptr_t sp;
        QJS_STACK_POINTER(sp);
        if (bytes <= SORT_PREP_ARENA_BYTES &&
            sp - (sizeof(JSFramePreparedSort) + 4096) >= ctx->rt->stack_limit)
            return JS_FramePreparedArraySort(ctx, this_val, argc, argv, host, b, bytes);
    }
    call.ctx = ctx;
    call.callee = js_dup(argv[0]);
    call.bytecode = b;
    call.frame_bytes = 128 + sizeof(JSValue) * (b->var_count + b->stack_size);
    owner = host->state + SORT_CACHE_OWNER;
    memcpy(&previous, owner, sizeof(previous));
    tagged = (uintptr_t)&call | 1;
    memcpy(owner, &tagged, sizeof(tagged));
    result = js_array_sort(ctx, this_val, argc, argv);
    memcpy(&current, owner, sizeof(current));
    if (current == tagged)
        memcpy(owner, &previous, sizeof(previous));
    JS_FreeValue(ctx, call.callee);
    return result;
original:
    return js_array_sort(ctx, this_val, argc, argv);
}

#endif
#ifdef QJS_PREPARED_SCOPE_ONLY
#include <stdatomic.h>
/* A process-wide research option, read once before the first eligible sort.
 * Independent runtimes may initialize concurrently. Both modes use the same
 * cached load; changing the environment later does not reconfigure it. */
static _Atomic unsigned char frame_entry_control
    __attribute__((section(".data$zzzzzzzzzsortentrycontrol")));
extern JSValue JS_FramePreparedEntryArraySort(JSContext *, JSValueConst, int, JSValueConst *,
                                              JSFramePreparedSort *, JSFrameCachedHost *);
/* A complete reusable state and root header are prepared once per sort.
 * Only eligible scopes enter this larger frame; cache-off and low quota
 * execute the established small wrapper and admission path.
 */
NATIVE_SORT_CODE JSValue JS_FramePreparedArraySort(JSContext *ctx, JSValueConst this_val, int argc,
                                                   JSValueConst *argv, JSFrameCachedHost *host,
                                                   JSFunctionBytecode *b, size_t bytes)
{
    _Alignas(16) JSFramePreparedSort call;
    JSFramePreparedHeader *frame = (JSFramePreparedHeader *)call.data;
    JSFramePreparedSegment *next, *following;
    unsigned char *owner = host->state + SORT_CACHE_OWNER;
    uintptr_t previous, tagged, current;
    JSValue result;
    call.cache.ctx = ctx;
    call.cache.callee = js_dup(argv[0]);
    call.cache.bytecode = b;
    call.cache.frame_bytes = bytes;
    call.segment.next = NULL;
    call.segment.capacity = sizeof(call.data);
    call.segment.used = 0;
    call.segment.data = call.data;
    memset(call.state, 0, sizeof(call.state));
    memcpy(call.state + 56, &ctx->rt, sizeof(ctx->rt));
    memcpy(call.state + SORT_PREP_CALLER, &ctx, sizeof(ctx));
    memcpy(call.state + SORT_PREP_SITES, host->state + SORT_PREP_SITES, 8);
    memcpy(call.state + SORT_PREP_NEXT, host->state + SORT_PREP_NEXT, 8);
    call.state[SORT_PREP_DIRECT] = host->state[SORT_PREP_DIRECT];
    call.barrier.state = call.state;
    call.barrier.kind = 2;
    memset(frame, 0, sizeof(*frame));
    frame->sf.cur_func = call.cache.callee;
    frame->sf.var_buf = (JSValue *)(call.data + 128);
    frame->sf.arg_count = 2;
    frame->sf.is_strict_mode = b->is_strict_mode;
    ((unsigned char *)&frame->sf)[62] = 1;
    frame->bytecode = b;
    frame->segment = &call.segment;
    frame->frame_bytes = bytes;
    memcpy(&previous, owner, 8);
    tagged = (uintptr_t)&call | 3;
    memcpy(owner, &tagged, 8);
    unsigned char control = atomic_load_explicit(&frame_entry_control, memory_order_relaxed);
    if (!control) {
        unsigned char expected = 0;
        control = getenv("QJS_DISABLE_PREPARED_SORT_ENTRY") ? 2 : 1;
        if (!atomic_compare_exchange_strong_explicit(&frame_entry_control, &expected, control,
                                                     memory_order_relaxed, memory_order_relaxed))
            control = expected;
    }
    if (control == 1)
        result = JS_FramePreparedEntryArraySort(ctx, this_val, argc, argv, &call, host);
    else
        result = js_array_sort(ctx, this_val, argc, argv);
    memcpy(&current, owner, 8);
    if (current == tagged)
        memcpy(owner, &previous, 8);
    for (next = call.segment.next; next; next = following) {
        following = next->next;
        js_free(ctx, next);
    }
    JS_FreeValue(ctx, call.cache.callee);
    return result;
}
#endif
#undef SORT_CACHE_OWNER
#undef SORT_CACHE_COMMITTED
