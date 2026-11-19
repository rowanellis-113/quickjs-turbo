/* Private function-owned call-site metadata. MIT, as in quickjs.c.
 * No JS value is duplicated or marked. Custom weak nodes never reach the
 * core's builtin weak-record switch. Caller/target addresses are dereferenced
 * only while live, and target collection clears the linked bytecode first. */
#include "src/common/call/interpreter-bytecode-metadata.inc"
#ifdef _MSC_VER
#include <intrin.h>
#define CALL_LINK_CODE __declspec(code_seg(".qjssrc$C")) __declspec(noinline)
#define CALL_LINK_INLINE __forceinline
#else
#define CALL_LINK_CODE __attribute__((section(".qjssrc$C"), noipa))
#define CALL_LINK_INLINE inline __attribute__((always_inline))
#endif

enum {
    CALL_LINK_OWNER_KIND = 0x4c4b0101,
    CALL_LINK_TARGET_KIND = 0x4c4b0102,
    CALL_LINK_MAX_SITES = 255,
    CALL_LINK_MAX_CODE = 2048,
    CALL_LINK_VM_BUDGET = 4
};
typedef struct JSFrameCallLinkOwner JSFrameCallLinkOwner;
typedef struct JSFrameCallLinkEntry {
    JSWeakRefRecord weak;                   /* 0: union points to native owner */
    struct JSFrameCallLinkEntry *alternate; /* 24: owned secondary, NULL, or blocked sentinel1 */
    JSObject *callee;                       /* 32: cleared by target weak reset */
    JSFunctionBytecode *bytecode;           /* 40: borrowed through live callee */
    uint64_t call_flags;                    /* 48: final SF argc/strict; no JS ownership */
    uint64_t geometry;                      /* 56: bytes/pending/locals/pad/kind/history */
} JSFrameCallLinkEntry;
struct JSFrameCallLinkOwner {
    JSWeakRefRecord weak;                        /* 0: owns the complete native allocation */
    uintptr_t index_bias;                        /* 24: index_base - live caller bytecode_base */
    uint64_t hits, misses, fills, invalidations; /* 32..63 */
    JSFrameCallLinkEntry entries[];              /* 64: actual site count; byte index follows */
};
_Static_assert(OP_call3 - OP_call0 == 3 && sizeof(JSWeakRefRecord) == 24 &&
                   offsetof(JSWeakRefRecord, kind) == 0 &&
                   offsetof(JSWeakRefRecord, next_weak_ref) == 8 &&
                   offsetof(JSWeakRefRecord, u) == 16 && sizeof(JSFrameCallLinkEntry) == 64 &&
                   offsetof(JSFrameCallLinkEntry, alternate) == 24 &&
                   offsetof(JSFrameCallLinkEntry, callee) == 32 &&
                   offsetof(JSFrameCallLinkEntry, bytecode) == 40 &&
                   offsetof(JSFrameCallLinkEntry, call_flags) == 48 &&
                   offsetof(JSFrameCallLinkEntry, geometry) == 56 &&
                   offsetof(JSFrameCallLinkOwner, index_bias) == 24 &&
                   offsetof(JSFrameCallLinkOwner, entries) == 64 &&
                   sizeof(JSFrameCallLinkOwner) == 64 &&
                   offsetof(JSObject, first_weak_ref) == QJS_ABI_OFF_JSObject_first_weak_ref &&
                   offsetof(JSObject, u.func.function_bytecode) ==
                       QJS_ABI_OFF_JSObject_u_func_function_bytecode &&
                   JS_WEAK_REF_KIND_MAP == 0 && JS_WEAK_REF_KIND_WEAK_REF == 1 &&
                   JS_WEAK_REF_KIND_FINALIZATION_REGISTRY_ENTRY == 2 &&
                   sizeof(JSFunctionBytecode) == QJS_ABI_SIZE_JSFunctionBytecode &&
                   offsetof(JSFunctionBytecode, byte_code_buf) ==
                       QJS_ABI_OFF_JSFunctionBytecode_byte_code_buf,
               "call-link weak-node, metadata and unchanged engine ABI");

/* Private byte17 bit7 is outside the core's four low-bit flags, not
 * padding23 (whose high bits belong to scoped sort). OOM stops new owners
 * for this live bytecode, without retaining any address or JS value. Core
 * serialization writes named flags, so newly read code starts unblocked. */
#define CALL_LINK_NO_ALLOC_OFFSET (QJS_ABI_BIT_JSFunctionBytecode_is_strict_mode_BYTE + 1)
#define CALL_LINK_NO_ALLOC(b) (((unsigned char *)(b))[CALL_LINK_NO_ALLOC_OFFSET])
_Static_assert(CALL_LINK_NO_ALLOC_OFFSET < FRAME_CALL_META_OFFSET,
               "call-link optional allocation flag precedes native call metadata");
extern const uint8_t JS_FrameCallLinkOpcodeSizes[OP_COUNT];
static CALL_LINK_INLINE const uint8_t *call_link_opcode_sizes(void)
{
#ifdef _MSC_VER
    return JS_FrameCallLinkOpcodeSizes;
#else
    /* GNU's external C data reference creates an ADDR64 refptr cell.
     * Keep the table inside the owned code contribution and address it
     * directly through the ordinary typed RIP-relative relocation. */
    const uint8_t *p;
    __asm__("leaq JS_FrameCallLinkOpcodeSizes(%%rip),%0" : "=r"(p));
    return p;
#endif
}

_Static_assert(OP_COUNT == 252 && OP_call0 == 244 && OP_call1 == 245 && OP_call2 == 246 &&
                   OP_call3 == 247 && OP_call == 34 && OP_call_method == 36 && OP_tail_call == 35 &&
                   OP_tail_call_method == 37,
               "direct metadata scanner uses current final opcode IDs and sizes");

static CALL_LINK_INLINE unsigned call_link_count(JSFrameCallLinkOwner *owner)
{
    return (unsigned)(((uintptr_t)owner->weak.u.weak_ref_data - (uintptr_t)owner->entries) /
                      sizeof(JSFrameCallLinkEntry));
}
static CALL_LINK_INLINE int call_link_is_site(unsigned op)
{
    return (op >= OP_call0 && op <= OP_call3) || op == OP_call || op == OP_call_method ||
           op == OP_tail_call || op == OP_tail_call_method;
}

extern void qjs_frame_core_reset_weak_ref(JSRuntime *, JSWeakRefRecord **);

static CALL_LINK_INLINE JSFrameCallLinkOwner *call_link_find(JSObject *p)
{
    JSWeakRefRecord *wr;
    for (wr = p->first_weak_ref; wr; wr = wr->next_weak_ref)
        if ((int)wr->kind == CALL_LINK_OWNER_KIND)
            return (JSFrameCallLinkOwner *)(void *)wr;
    return NULL;
}

/* The hot 64-byte entries and PC map retain their original offsets. A cold
 * tail holds one predecessor pointer per primary; a secondary has one trailing
 * pointer. A 16-byte native allocation prefix stores the tail offset and
 * same-image ablation bit, preserving owner alignment and all public layouts.
 * Never point into a builtin weak node:
 * the core can remove those nodes without passing through our list helpers.
 */
enum { CALL_LINK_PREFIX_BYTES = 16 };
extern unsigned char JS_FrameCallLinkBacklinkControl;
#ifdef _MSC_VER
extern unsigned char JS_FrameCallMetaLoadByte(unsigned char *);
extern unsigned char JS_FrameCallMetaInitByte(unsigned char *, unsigned char);
#endif
static CALL_LINK_INLINE unsigned char call_link_backlink_mode(void)
{
    unsigned char mode;
#ifdef _MSC_VER
    mode = JS_FrameCallMetaLoadByte(&JS_FrameCallLinkBacklinkControl);
#else
    __asm__ volatile("movb JS_FrameCallLinkBacklinkControl(%%rip),%0" : "=q"(mode)::"memory");
#endif
    if (!mode) {
        unsigned char desired = getenv("QJS_DISABLE_CALL_LINK_BACKLINK") ? 2 : 1;
#ifdef _MSC_VER
        mode = JS_FrameCallMetaInitByte(&JS_FrameCallLinkBacklinkControl, desired);
        if (!mode)
            mode = desired;
#else
        unsigned char expected = 0;
        __asm__ volatile("lock cmpxchgb %2,JS_FrameCallLinkBacklinkControl(%%rip)"
                         : "+a"(expected)
                         : "0"(expected), "q"(desired)
                         : "memory", "cc");
        mode = expected ? expected : desired;
#endif
    }
    return mode;
}
static CALL_LINK_INLINE uint32_t call_link_tail_tag(JSFrameCallLinkOwner *owner)
{
    uint32_t tag;
    memcpy(&tag, (unsigned char *)owner - CALL_LINK_PREFIX_BYTES, sizeof(tag));
    return tag;
}
static CALL_LINK_INLINE JSWeakRefRecord **call_link_previous_slot(JSFrameCallLinkEntry *entry)
{
    JSFrameCallLinkOwner *owner = (JSFrameCallLinkOwner *)(void *)entry->weak.u.weak_ref_data;
    uintptr_t offset = (uintptr_t)entry - (uintptr_t)owner->entries;
    if (offset < (size_t)call_link_count(owner) * sizeof(*entry))
        return (JSWeakRefRecord **)(void *)((unsigned char *)owner +
                                            (call_link_tail_tag(owner) & UINT32_C(0x7fffffff))) +
               offset / sizeof(*entry);
    return (JSWeakRefRecord **)(void *)(entry + 1);
}
static CALL_LINK_INLINE int call_link_private(JSWeakRefRecord *wr)
{
    return wr && ((int)wr->kind == CALL_LINK_OWNER_KIND || (int)wr->kind == CALL_LINK_TARGET_KIND);
}
static CALL_LINK_INLINE void call_link_set_previous(JSWeakRefRecord *wr, JSWeakRefRecord *previous)
{
    if (wr && (int)wr->kind == CALL_LINK_TARGET_KIND)
        *call_link_previous_slot((JSFrameCallLinkEntry *)(void *)wr) = previous;
}
static CALL_LINK_INLINE JSWeakRefRecord *call_link_predecessor(JSObject *p, JSWeakRefRecord **at)
{
    JSWeakRefRecord *previous;
    if (at == &p->first_weak_ref)
        return NULL;
    previous =
        (JSWeakRefRecord *)(void *)((unsigned char *)at - offsetof(JSWeakRefRecord, next_weak_ref));
    return call_link_private(previous) ? previous : NULL;
}
static CALL_LINK_INLINE void call_link_unlink(JSFrameCallLinkEntry *entry)
{
    JSWeakRefRecord **at, *wr = &entry->weak;
    JSObject *p = entry->callee;
    if (p) {
        JSFrameCallLinkOwner *owner = (JSFrameCallLinkOwner *)(void *)wr->u.weak_ref_data;
        JSWeakRefRecord *previous = *call_link_previous_slot(entry);
        if (previous && !(call_link_tail_tag(owner) & UINT32_C(0x80000000)))
            at = &previous->next_weak_ref;
        else {
            at = &p->first_weak_ref;
            while (*at && *at != wr)
                at = &(*at)->next_weak_ref;
        }
        /* A live link must still own its node in that target's weak list. */
        assert(*at == wr);
        *at = wr->next_weak_ref;
        call_link_set_previous(wr->next_weak_ref, call_link_predecessor(p, at));
        *call_link_previous_slot(entry) = NULL;
    }
    /* The alternate belongs to the caller, independently of this target. */
    entry->callee = NULL;
    entry->bytecode = NULL;
    entry->call_flags = 0;
    entry->geometry = 0;
    wr->next_weak_ref = NULL;
}

static CALL_LINK_INLINE void call_link_front(JSObject *p, JSFrameCallLinkOwner *owner)
{
    JSWeakRefRecord **at = &p->first_weak_ref, *wr = &owner->weak;
    if (*at == wr)
        return;
    while (*at && *at != wr)
        at = &(*at)->next_weak_ref;
    assert(*at == wr);
    *at = wr->next_weak_ref;
    call_link_set_previous(wr->next_weak_ref, call_link_predecessor(p, at));
    wr->next_weak_ref = p->first_weak_ref;
    call_link_set_previous(wr->next_weak_ref, wr);
    p->first_weak_ref = wr;
}

static CALL_LINK_INLINE JSFrameCallLinkEntry *call_link_alternate(JSFrameCallLinkEntry *primary)
{
    return (uintptr_t)primary->alternate > 1 ? primary->alternate : NULL;
}
static CALL_LINK_INLINE void call_link_block_alternate(JSFrameCallLinkEntry *primary)
{
    /* Exhaust VM cold budget as well as recording the non-pointer sentinel.
       Primary hits still work, and later misses stay in the pure old Ready. */
    primary->alternate = (JSFrameCallLinkEntry *)(uintptr_t)1;
    if ((uint8_t)(primary->geometry >> 56) < CALL_LINK_VM_BUDGET)
        primary->geometry = (primary->geometry & UINT64_C(0x00ffffffffffffff)) |
                            ((uint64_t)CALL_LINK_VM_BUDGET << 56);
}

static CALL_LINK_INLINE JSFrameCallLinkEntry *call_link_prepare(JSRuntime *rt, JSObject *caller,
                                                                const uint8_t *pc, JSObject *callee,
                                                                unsigned budget)
{
    JSFrameCallLinkOwner *owner, *allocated;
    JSFrameCallLinkEntry *entry, *primary, *secondary, *allocated_entry;
    JSFunctionBytecode *b, *cb;
    uintptr_t offset;
    unsigned index, op, kind, argc, formals, padding, pending, sites, pos, size;
    uint8_t *map;
    const uint8_t *opcode_sizes;
    size_t allocation_bytes;
    uint16_t frame_bytes;
    uint8_t history;
#ifdef QJS_INTERP_FRAME_DIAGNOSTICS
    unsigned noted_miss = 0;
#endif
    /* Optional metadata allocation uses the nonthrowing runtime allocator.
       The VM/native caller must already publish/hold caller and callee roots. */
    if (getenv("QJS_DISABLE_CALL_LINK") || rt->gc_phase != JS_GC_PHASE_NONE || caller->free_mark ||
        callee->free_mark || caller->class_id != JS_CLASS_BYTECODE_FUNCTION ||
        callee->class_id != JS_CLASS_BYTECODE_FUNCTION)
        return NULL;
    cb = caller->u.func.function_bytecode;
    if (cb->realm->rt != rt || !(FRAME_KIND(cb) & 1))
        return NULL;
    offset = (uintptr_t)pc - (uintptr_t)cb->byte_code_buf;
    if (cb->byte_code_len <= 0 || offset >= (uintptr_t)cb->byte_code_len)
        return NULL;
    op = *pc;
    if (op != OP_call0 && op != OP_call1 && op != OP_call2 && op != OP_call3 && op != OP_call &&
        op != OP_call_method && op != OP_tail_call && op != OP_tail_call_method)
        return NULL;
    if (op >= OP_call0 && op <= OP_call3)
        argc = op - OP_call0;
    else {
        uint16_t encoded;
        if (offset + 3 > (uintptr_t)cb->byte_code_len)
            return NULL;
        memcpy(&encoded, pc + 1, sizeof(encoded));
        argc = encoded;
    }
    pending = argc + 1 + (op == OP_call_method || op == OP_tail_call_method);
    if (pending > 0x7fff)
        return NULL; /* optional cache; preserve generic fallback */
    if (op == OP_tail_call || op == OP_tail_call_method)
        pending |= 0x8000;
    b = callee->u.func.function_bytecode;
    if (b->realm->rt != rt)
        return NULL;
    kind = FRAME_KIND(b);
    if ((kind & 21) != 17)
        return NULL;
    owner = call_link_find(caller);
    if (!owner) {
        if (CALL_LINK_NO_ALLOC(cb) & 128)
            return NULL;
        sites = 0;
        opcode_sizes = call_link_opcode_sizes();
        if (cb->byte_code_len > CALL_LINK_MAX_CODE)
            goto no_owner;
        for (pos = 0; pos < (unsigned)cb->byte_code_len; pos += size) {
            unsigned scan_op = cb->byte_code_buf[pos];
            if (scan_op >= OP_COUNT)
                goto no_owner;
            size = opcode_sizes[scan_op];
            if (!size || size > (unsigned)cb->byte_code_len - pos)
                goto no_owner;
            if (call_link_is_site(scan_op) && sites < CALL_LINK_MAX_SITES)
                sites++;
        }
        if (!sites)
            goto no_owner;
        allocation_bytes =
            sizeof(*owner) + (size_t)sites * sizeof(*entry) + (unsigned)cb->byte_code_len;
        allocation_bytes = ((allocation_bytes + 7u) & ~(size_t)7u) +
                           (size_t)sites * sizeof(JSWeakRefRecord *) + CALL_LINK_PREFIX_BYTES;
        allocated = js_calloc_rt(rt, 1, allocation_bytes);
        /* The caller roots cb across allocator reentry. Even allocation
         * failure may have installed an owner in a nested JS activation. */
        owner = call_link_find(caller);
        if (owner) {
            if (allocated)
                js_free_rt(rt, allocated);
        } else {
            if (!allocated)
                goto no_owner;
            owner = (JSFrameCallLinkOwner *)(void *)((unsigned char *)allocated +
                                                     CALL_LINK_PREFIX_BYTES);
            map = (uint8_t *)(void *)(owner->entries + sites);
            {
                uint32_t tag = (uint32_t)(((size_t)(map - (uint8_t *)(void *)owner) +
                                           (unsigned)cb->byte_code_len + 7u) &
                                          ~(size_t)7u);
                if (call_link_backlink_mode() == 2)
                    tag |= UINT32_C(0x80000000);
                memcpy((unsigned char *)owner - CALL_LINK_PREFIX_BYTES, &tag, sizeof(tag));
            }
            memset(map, 255, (unsigned)cb->byte_code_len);
            index = 0;
            for (pos = 0; pos < (unsigned)cb->byte_code_len; pos += size) {
                unsigned scan_op = cb->byte_code_buf[pos];
                size = opcode_sizes[scan_op];
                if (call_link_is_site(scan_op) && index < sites)
                    map[pos] = (uint8_t)index++;
            }
            owner->weak.kind = (JSWeakRefKindEnum)CALL_LINK_OWNER_KIND;
            /* Only private OWNER-kind readers interpret this as index_base. */
            owner->weak.u.weak_ref_data = (struct JSWeakRefData *)(void *)map;
            owner->index_bias = (uintptr_t)map - (uintptr_t)cb->byte_code_buf;
            owner->weak.next_weak_ref = caller->first_weak_ref;
            call_link_set_previous(owner->weak.next_weak_ref, &owner->weak);
            caller->first_weak_ref = &owner->weak;
        }
    }
    map = (uint8_t *)(void *)owner->weak.u.weak_ref_data;
    index = map[offset];
    if (index == 255)
        return NULL; /* excess sites or operand bytes never refill */
    primary = &owner->entries[index];
pick_link:
    secondary = call_link_alternate(primary);
    /* The validated direct byte-PC index already identifies exactly this site.
       Native matches do not increment actual ASM VM hit counters. */
    if (primary->callee == callee) {
        call_link_front(caller, owner);
        return primary;
    }
    if (secondary && secondary->callee == callee) {
        call_link_front(caller, owner);
        return secondary;
    }
#ifdef QJS_INTERP_FRAME_DIAGNOSTICS
    if (!noted_miss) {
        owner->misses++;
        noted_miss = 1;
    }
#endif
    history = (uint8_t)(primary->geometry >> 56);
    if (budget && history >= budget)
        return NULL;
    if (!primary->callee)
        entry = primary;
    else if (secondary)
        entry = secondary;
    else {
        if (primary->alternate)
            return NULL; /* Previous secondary OOM: no retry. */
        if (CALL_LINK_NO_ALLOC(cb) & 128) {
            call_link_block_alternate(primary);
            return NULL;
        }
        allocated_entry = js_calloc_rt(rt, 1, sizeof(*allocated_entry) + sizeof(JSWeakRefRecord *));
        /* Even a failed allocator call may have linked a secondary, changed
           the current target or exhausted the budget through GC/JS reentry. */
        owner = call_link_find(caller);
        if (!owner) {
            if (allocated_entry)
                js_free_rt(rt, allocated_entry);
            return NULL;
        }
        primary = &owner->entries[index];
        secondary = call_link_alternate(primary);
        if (primary->callee == callee || !primary->callee || secondary || primary->alternate ||
            (budget && (uint8_t)(primary->geometry >> 56) >= budget)) {
            if (allocated_entry)
                js_free_rt(rt, allocated_entry);
            goto pick_link;
        }
        if (!allocated_entry) {
            call_link_block_alternate(primary);
            call_link_front(caller, owner);
            return NULL;
        }
        primary->alternate = allocated_entry;
        entry = allocated_entry;
        history = (uint8_t)(primary->geometry >> 56);
    }
    call_link_unlink(entry);
    entry->weak.kind = (JSWeakRefKindEnum)CALL_LINK_TARGET_KIND;
    entry->weak.u.weak_ref_data = (struct JSWeakRefData *)(void *)owner;
    entry->callee = callee;
    entry->bytecode = b;
    formals = ((const unsigned char *)b)[FRAME_CALL_FORMALS_OFFSET];
    padding = formals > argc ? formals - argc : 0;
    entry->call_flags =
        ((uint64_t)(argc > formals ? argc : formals) << 16) | ((uint64_t)b->is_strict_mode << 32);
    memcpy(&frame_bytes, (const unsigned char *)b + FRAME_CALL_META_OFFSET, sizeof(frame_bytes));
    entry->geometry = (uint16_t)(frame_bytes - 32) | ((uint64_t)pending << 16) |
                      ((uint64_t)((const unsigned char *)b)[FRAME_CALL_LOCALS_OFFSET] << 32) |
                      ((uint64_t)padding << 40) | ((uint64_t)kind << 48) |
                      ((uint64_t)(history < UINT8_MAX ? history + 1 : UINT8_MAX) << 56);
    if (entry != primary)
        primary->geometry = (primary->geometry & UINT64_C(0x00ffffffffffffff)) |
                            ((uint64_t)(history < UINT8_MAX ? history + 1 : UINT8_MAX) << 56);
    entry->weak.next_weak_ref = callee->first_weak_ref;
    call_link_set_previous(entry->weak.next_weak_ref, &entry->weak);
    *call_link_previous_slot(entry) = NULL;
    callee->first_weak_ref = &entry->weak;
    /* Also handles self recursion: the owner remains the first weak node. */
    call_link_front(caller, owner);
#ifdef QJS_INTERP_FRAME_DIAGNOSTICS
    owner->fills++;
#endif
    return entry;
no_owner:
    CALL_LINK_NO_ALLOC(cb) |= 128;
    return NULL;
}

CALL_LINK_CODE JSFrameCallLinkEntry *JS_FrameCallLinkPrepare(JSRuntime *rt, JSObject *caller,
                                                             const uint8_t *pc, JSObject *callee)
{
    /* Preserve management/testing callers' unbounded explicit refill API.
       The real VM cold wrapper below supplies its bounded four-fill policy. */
    return call_link_prepare(rt, caller, pc, callee, 0);
}

CALL_LINK_CODE void JS_FrameCallLinkStats(const JSValue *caller, uint64_t out[8])
{
    JSFrameCallLinkOwner *owner;
    unsigned i;
    memset(out, 0, 8 * sizeof(*out));
    if (JS_VALUE_GET_TAG(*caller) != JS_TAG_OBJECT)
        return;
    owner = call_link_find(JS_VALUE_GET_OBJ(*caller));
    if (!owner)
        return;
    out[0] = 1;
    out[1] = owner->hits;
    out[2] = owner->misses;
    out[3] = owner->fills;
    out[4] = owner->invalidations;
    out[6] = sizeof(*owner) + (size_t)call_link_count(owner) * sizeof(JSFrameCallLinkEntry) +
             (unsigned)JS_VALUE_GET_OBJ(*caller)->u.func.function_bytecode->byte_code_len;
    out[6] = ((out[6] + 7u) & ~UINT64_C(7)) +
             (size_t)call_link_count(owner) * sizeof(JSWeakRefRecord *) + CALL_LINK_PREFIX_BYTES;
    for (i = 0; i < call_link_count(owner); i++) {
        JSFrameCallLinkEntry *primary = &owner->entries[i];
        JSFrameCallLinkEntry *secondary = call_link_alternate(primary);
        if (primary->callee)
            out[5]++;
        if (secondary) {
            out[6] += sizeof(*secondary) + sizeof(JSWeakRefRecord *);
            if (secondary->callee)
                out[5]++;
        }
    }
    out[7] = (uintptr_t)owner;
}

CALL_LINK_CODE void JS_FrameCallLinkResetWeak(JSRuntime *rt, JSWeakRefRecord **first)
{
    JSWeakRefRecord **at = first, *wr, *owners = NULL;
    JSFrameCallLinkOwner *owner;
    unsigned i;
    /* Detach and invalidate EVERY private target before freeing any owner.
       This handles a function that is both owner and target in the same list. */
    while ((wr = *at) != NULL) {
        if ((int)wr->kind == CALL_LINK_TARGET_KIND) {
            JSFrameCallLinkEntry *entry = (JSFrameCallLinkEntry *)(void *)wr;
            owner = (JSFrameCallLinkOwner *)(void *)wr->u.weak_ref_data;
            *at = wr->next_weak_ref;
            call_link_set_previous(wr->next_weak_ref, NULL);
            *call_link_previous_slot(entry) = NULL;
            entry->callee = NULL;
            entry->bytecode = NULL;
            entry->call_flags = 0;
            entry->geometry &= UINT64_C(0xff00000000000000);
            wr->next_weak_ref = NULL;
            /* Caller-owned alternate and the site cold budget survive target reset. */
#ifdef QJS_INTERP_FRAME_DIAGNOSTICS
            owner->invalidations++;
#else
            (void)owner;
#endif
        } else if ((int)wr->kind == CALL_LINK_OWNER_KIND) {
            *at = wr->next_weak_ref;
            call_link_set_previous(wr->next_weak_ref, NULL);
            owner = (JSFrameCallLinkOwner *)(void *)wr;
            owner->index_bias = 0;
            wr->next_weak_ref = owners;
            owners = wr;
        } else
            at = &wr->next_weak_ref;
    }
    /* Preserve the core's builtin two-pass behavior and finalizer scheduling.
       Detached owners stay allocated across recursive builtin value releases. */
    if (*first)
        qjs_frame_core_reset_weak_ref(rt, first);
    while (owners) {
        wr = owners;
        owners = wr->next_weak_ref;
        owner = (JSFrameCallLinkOwner *)(void *)wr;
        for (i = 0; i < call_link_count(owner); i++) {
            JSFrameCallLinkEntry *primary = &owner->entries[i];
            JSFrameCallLinkEntry *secondary = call_link_alternate(primary);
            if (secondary) {
                call_link_unlink(secondary);
                js_free_rt(rt, secondary);
            }
            call_link_unlink(primary);
            primary->alternate = NULL;
        }
        js_free_rt(rt, (unsigned char *)owner - CALL_LINK_PREFIX_BYTES);
    }
}

/* One process startup switch, atomically initialized across independent RTs.
   Only the VM entry reads this byte; no JS value or metadata pointer is shared. */
extern unsigned char JS_FrameCallLinkControl;
static CALL_LINK_INLINE unsigned char call_link_vm_mode(void)
{
    unsigned char mode;
#ifdef _MSC_VER
    mode = *(volatile unsigned char *)&JS_FrameCallLinkControl;
#else
    __asm__ volatile("movb JS_FrameCallLinkControl(%%rip),%0" : "=q"(mode)::"memory");
#endif
    if (!mode) {
        /* VM weak-link allocation is opt-in on both Windows compilers.
           Scalar frame preparation and uncached native calls remain enabled;
           explicit management Prepare retains its independent contract. */
        unsigned char desired = getenv("QJS_ENABLE_CALL_LINK_VM") &&
                                        !getenv("QJS_DISABLE_CALL_LINK") &&
                                        !getenv("QJS_DISABLE_CALL_LINK_VM")
                                    ? 1
                                    : 2;
#ifdef _MSC_VER
        _InterlockedCompareExchange8((volatile char *)&JS_FrameCallLinkControl, (char)desired, 0);
        mode = *(volatile unsigned char *)&JS_FrameCallLinkControl;
#else
        unsigned char expected = 0;
        __asm__ volatile("lock cmpxchgb %2,JS_FrameCallLinkControl(%%rip)"
                         : "+a"(expected)
                         : "0"(expected), "q"(desired)
                         : "memory", "cc");
        __asm__ volatile("movb JS_FrameCallLinkControl(%%rip),%0" : "=q"(mode)::"memory");
#endif
    }
    return mode;
}
CALL_LINK_CODE unsigned JS_FrameCallLinkVMState(void)
{
#ifdef _MSC_VER
    return *(volatile unsigned char *)&JS_FrameCallLinkControl;
#else
    unsigned char mode;
    __asm__ volatile("movb JS_FrameCallLinkControl(%%rip),%0" : "=q"(mode)::"memory");
    return mode;
#endif
}
CALL_LINK_CODE void JS_FrameCallLinkMiss(JSFrameRegisterState *state, unsigned argc)
{
    JSFrame *frame = state->frame;
    JSValue *argv = state->sp - argc;
    JSValue target = argv[-1];
    /* The ASM entry has published caller SF/PC/SP and exact cur_sp, and has
       retained the original physical 8KB native-entry margin before this C call. */
    js_frame_begin_c(state);
    if (call_link_vm_mode() == 1 && JS_VALUE_GET_TAG(target) == JS_TAG_OBJECT)
        call_link_prepare(state->rt, JS_VALUE_GET_OBJ(frame->sf.cur_func), state->pc,
                          JS_VALUE_GET_OBJ(target), CALL_LINK_VM_BUDGET);
    /* Match the original running-frame contract, rather than leaving a stale
       suspended cursor while subsequent pure JS drops/replaces operands. */
    frame->sf.cur_sp = NULL;
    js_frame_finish_c(state);
}

#undef CALL_LINK_NO_ALLOC
#undef CALL_LINK_CODE
#undef CALL_LINK_INLINE
