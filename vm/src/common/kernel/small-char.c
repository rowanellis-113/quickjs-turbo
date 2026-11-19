#include "src/common/call/interpreter-retained-context.inc"

static FRAME_INLINE void *string_index_data(JSString *p)
{
    JSStringSlice *slice;
    void **indirect;

    switch (p->kind) {
    case JS_STRING_KIND_NORMAL:
        return (void *)&p[1];
    case JS_STRING_KIND_SLICE:
        slice = (void *)&p[1];
        return (char *)&slice->parent[1] + slice->start;
    case JS_STRING_KIND_INDIRECT:
        indirect = (void *)&p[1];
        return *indirect;
    }
    abort();
    return NULL;
}

static FRAME_INLINE uint8_t *string_index_data8(JSString *p)
{
    return string_index_data(p);
}

static FRAME_INLINE uint16_t *string_index_data16(JSString *p)
{
    return string_index_data(p);
}
static FRAME_INLINE int string_index_get(JSString *p, int idx)
{
    return p->is_wide_char ? string_index_data16(p)[idx] : string_index_data8(p)[idx];
}

#include <stdatomic.h>
extern JSValue qjs_frame_core_js_new_string_char(JSContext *, uint16_t);
extern JSAtom qjs_frame_core___JS_NewAtom(JSRuntime *, JSString *, int);
#define SMALL_RT_COUNT 16
#define SMALL_CHAR_COUNT 256
/* Sidecar avoids changing JSRuntime and the large original interpreter.
   Slots are optional: saturation uses the original allocator. Ownership is
   published atomically; each runtime retains the engine's normal single
   executor requirement. Different runtimes can occupy different slots. */
_Atomic(JSRuntime *) JS_FrameSmallCharOwners[SMALL_RT_COUNT]
    __attribute__((section(".qjzzpm"), aligned(8)));
JSString *JS_FrameSmallCharValues[SMALL_RT_COUNT][SMALL_CHAR_COUNT]
    __attribute__((section(".qjzzpm"), aligned(8)));
_Atomic(unsigned) JS_FrameSmallCharMode __attribute__((section(".qjzzpm"), aligned(4)));
unsigned JS_FrameSmallCharInterning[SMALL_RT_COUNT] __attribute__((section(".qjzzpm"), aligned(4)));
_Atomic(uint64_t) JS_FrameSmallCharStats[7] __attribute__((section(".qjzzpm"), aligned(8)));
static FRAME_INLINE void small_count(unsigned mode, unsigned n)
{
    if (mode & 4)
        atomic_fetch_add_explicit(&JS_FrameSmallCharStats[n], 1, memory_order_relaxed);
}
static FRAME_INLINE unsigned small_mode(void)
{
    unsigned m = atomic_load_explicit(&JS_FrameSmallCharMode, memory_order_relaxed);
    if (!m) {
        unsigned expected = 0;
        m = getenv("QJS_DISABLE_SMALL_CHAR_CACHE") ? 2 : 1;
        if (getenv("QJS_OBSERVE_SMALL_CHAR_CACHE"))
            m |= 4;
        if (!atomic_compare_exchange_strong_explicit(&JS_FrameSmallCharMode, &expected, m,
                                                     memory_order_relaxed, memory_order_relaxed))
            m = expected;
    }
    return m;
}
static FRAME_INLINE int small_slot(JSRuntime *rt, unsigned mode)
{
    for (unsigned attempt = 0; attempt < 2; attempt++) {
        int empty = -1;
        for (unsigned i = 0; i < SMALL_RT_COUNT; i++) {
            JSRuntime *owner =
                atomic_load_explicit(&JS_FrameSmallCharOwners[i], memory_order_acquire);
            if (owner == rt)
                return (int)i;
            if (!owner && empty < 0)
                empty = (int)i;
        }
        if (empty < 0)
            return -1;
        JSRuntime *expected = NULL;
        if (atomic_compare_exchange_strong_explicit(&JS_FrameSmallCharOwners[empty], &expected, rt,
                                                    memory_order_acq_rel, memory_order_acquire)) {
            small_count(mode, 4);
            return empty;
        }
    }
    return -1;
}
FRAME_CODE JSValue JS_FrameSmallCharNew(JSContext *ctx, uint16_t c)
{
    unsigned mode = small_mode();
    JSRuntime *rt = ctx->rt;
    small_count(mode, 0);
    if ((mode & 3) != 1 || c >= SMALL_CHAR_COUNT || rt->in_free) {
        small_count(mode, 3);
        return qjs_frame_core_js_new_string_char(ctx, c);
    }
    int slot = small_slot(rt, mode);
    if (slot < 0) {
        small_count(mode, 3);
        return qjs_frame_core_js_new_string_char(ctx, c);
    }
    JSString *p = JS_FrameSmallCharValues[slot][c];
    if (p) {
        small_count(mode, 1);
        return JS_DupValue(ctx, JS_MKPTR(JS_TAG_STRING, p));
    }
    small_count(mode, 2);
    /* Miss allocates only the original result. Native allocator reentry may
    have populated this cell, so re-read it before installing one extra owner. */
    JSValue value = qjs_frame_core_js_new_string_char(ctx, c);
    if (!JS_IsException(value) && !JS_FrameSmallCharValues[slot][c] &&
        !JS_FrameSmallCharInterning[slot]) {
        /* Plain JSString storage can be converted in place to a user Symbol.
     Only cache STRING atoms: Symbol construction must clone their storage.
     The internal constructor also keeps digits as real string atoms here.
     It consumes value on success and failure; do not free value again. */
        /* Allocator reentry may request any character while the core atom table
     is reallocating. Such a nested miss returns its ordinary string without
     recursively interning it; populated cache hits remain safe and cheap. */
        JS_FrameSmallCharInterning[slot] = 1;
        JSAtom atom =
            qjs_frame_core___JS_NewAtom(rt, JS_VALUE_GET_STRING(value), JS_ATOM_TYPE_STRING);
        JS_FrameSmallCharInterning[slot] = 0;
        if (atom == JS_ATOM_NULL)
            return JS_ThrowOutOfMemory(ctx);
        value = JS_AtomToString(ctx, atom);
        JS_FreeAtom(ctx, atom);
        /* Atom-table allocation may itself reenter. Never replace another owner. */
        if (!JS_FrameSmallCharValues[slot][c])
            JS_FrameSmallCharValues[slot][c] = JS_VALUE_GET_STRING(JS_DupValue(ctx, value));
    }
    return value;
}
FRAME_CODE void JS_FrameSmallCharCleanupGC(JSRuntime *rt)
{
    /* Only the original JS_FreeRuntime -> JS_RunGC operand targets this entry.
    JS_FreeRuntime has already set rt->in_free, so allocator reentry cannot
    repopulate a cache while it is being detached. */
    assert(rt->in_free);
    unsigned mode = atomic_load_explicit(&JS_FrameSmallCharMode, memory_order_relaxed);
    for (unsigned i = 0; i < SMALL_RT_COUNT; i++) {
        if (atomic_load_explicit(&JS_FrameSmallCharOwners[i], memory_order_acquire) != rt)
            continue;
        for (unsigned c = 0; c < SMALL_CHAR_COUNT; c++) {
            JSString *p = JS_FrameSmallCharValues[i][c];
            JS_FrameSmallCharValues[i][c] = NULL;
            if (p) {
                JS_FreeValueRT(rt, JS_MKPTR(JS_TAG_STRING, p));
                small_count(mode, 6);
            }
        }
        JS_FrameSmallCharInterning[i] = 0;
        atomic_store_explicit(&JS_FrameSmallCharOwners[i], NULL, memory_order_release);
        small_count(mode, 5);
        break;
    }
    JS_RunGC(rt);
}
_Static_assert(sizeof(JSValue) == QJS_ABI_SIZE_JSValue && JS_TAG_STRING == -7 &&
                   SMALL_RT_COUNT == 16 && SMALL_CHAR_COUNT == 256 &&
                   sizeof(JS_FrameSmallCharValues) == 32768,
               "bounded single-character ownership ABI");
