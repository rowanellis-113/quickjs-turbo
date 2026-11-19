/* Metadata lifecycle qualification, including controlled host-address reuse. */
#include "quickjs-interpreter-private.h"
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include "tests/common/native_call_link_pressure.h"
extern void *JS_FrameCallLinkPrepare(JSRuntime *, JSObject *, const uint8_t *, JSObject *);
extern void JS_FrameCallLinkStats(const JSValue *, uint64_t[8]);
typedef struct Block {
    size_t size;
    uint64_t magic;
    struct Block *next;
    uint64_t padding;
} Block;
typedef struct Fixture {
    JSRuntime *rt;
    JSContext *ctx;
    JSClassID token_class;
    size_t live;
    unsigned fail, armed, inside, reentries, finalized, errors;
    Block *recycled;
    unsigned recycle;
    JSValue owner, target;
    const uint8_t *pc;
    void *inner_entry;
} Fixture;
static int fail_line;
#define CHECK(x)                                                                                   \
    do {                                                                                           \
        if (!(x)) {                                                                                \
            fprintf(stderr, "CALL_LINK_CHECK line=%d: %s\n", __LINE__, #x);                        \
            fail_line = __LINE__;                                                                  \
            return 1;                                                                              \
        }                                                                                          \
    } while (0)
static int value_int(JSContext *ctx, JSValue v, int expected)
{
    if (JS_IsException(v)) {
        JSValue e = JS_GetException(ctx);
        const char *s = JS_ToCString(ctx, e);
        fprintf(stderr, "CALL_LINK_EXCEPTION %s\n", s ? s : "?");
        JS_FreeCString(ctx, s);
        JS_FreeValue(ctx, e);
        return 1;
    }
    int32_t n = 0;
    int rc = JS_ToInt32(ctx, &n, v);
    JS_FreeValue(ctx, v);
    return rc || n != expected;
}
static JSValue eval(JSContext *ctx, const char *s)
{
    return JS_Eval(ctx, s, strlen(s), "call-link-lifecycle.js", 0);
}
static void *allocate(void *opaque, size_t n)
{
    Fixture *a = opaque;
    if (a->fail)
        return NULL;
    if (a->armed && !a->inside) {
        a->armed = 0;
        a->inside = 1;
        JS_RunGC(a->rt);
        JSValue args[2] = {a->target, JS_NewInt32(a->ctx, 7)};
        if (value_int(a->ctx, JS_Call(a->ctx, a->owner, JS_UNDEFINED, 2, args), 9))
            a->errors++;
        a->inner_entry = JS_FrameCallLinkPrepare(a->rt, JS_VALUE_GET_OBJ(a->owner), a->pc,
                                                 JS_VALUE_GET_OBJ(a->target));
        a->reentries++;
        a->inside = 0;
    }
    Block **slot = &a->recycled;
    while (*slot && (*slot)->size != n)
        slot = &(*slot)->next;
    Block *b = *slot;
    if (b) {
        *slot = b->next;
        if (b->magic)
            abort();
    } else
        b = malloc(sizeof(*b) + n);
    if (!b)
        return NULL;
    b->size = n;
    b->magic = UINT64_C(0xcaff4527);
    b->next = NULL;
    a->live++;
    return b + 1;
}
static void *allocate_zero(void *opaque, size_t n, size_t size)
{
    if (n && size > SIZE_MAX / n)
        return NULL;
    void *p = allocate(opaque, n * size);
    if (p)
        memset(p, 0, n * size);
    return p;
}
static void release(void *opaque, void *p)
{
    if (!p)
        return;
    Fixture *a = opaque;
    Block *b = (Block *)p - 1;
    if (b->magic != UINT64_C(0xcaff4527) || !a->live)
        abort();
    a->live--;
    b->magic = 0;
    if (a->recycle) {
        b->next = a->recycled;
        a->recycled = b;
    } else
        free(b);
}
static void *resize(void *opaque, void *p, size_t n)
{
    Fixture *a = opaque;
    if (a->fail)
        return NULL;
    if (!p)
        return allocate(opaque, n);
    if (!n) {
        release(opaque, p);
        return NULL;
    }
    Block *b = realloc((Block *)p - 1, sizeof(*b) + n);
    if (!b)
        return NULL;
    b->size = n;
    return b + 1;
}
static size_t usable(const void *p)
{
    return p ? ((const Block *)p - 1)->size : 0;
}
static void finalizer(JSRuntime *rt, JSValue value)
{
    (void)value;
    ((Fixture *)JS_GetRuntimeOpaque(rt))->finalized++;
}
static int setup(Fixture *a)
{
    JSMallocFunctions mf = {allocate_zero, allocate, release, resize, usable};
    a->rt = JS_NewRuntime2(&mf, a);
    CHECK(a->rt);
    JS_SetRuntimeOpaque(a->rt, a);
    a->ctx = JS_NewContext(a->rt);
    CHECK(a->ctx);
    JS_NewClassID(a->rt, &a->token_class);
    JSClassDef def = {0};
    def.class_name = "CallLinkToken";
    def.finalizer = finalizer;
    CHECK(JS_NewClass(a->rt, a->token_class, &def) == 0);
    return 0;
}
static int attach(Fixture *a, JSValue fn, int cycle)
{
    JSValue token = JS_NewObjectClass(a->ctx, a->token_class);
    CHECK(!JS_IsException(token));
    if (cycle)
        CHECK(JS_SetPropertyStr(a->ctx, token, "fn", JS_DupValue(a->ctx, fn)) >= 0);
    CHECK(JS_SetPropertyStr(a->ctx, fn, "token", token) >= 0);
    return 0;
}
static const uint8_t opcode_sizes[OP_COUNT] = {
#define FMT(f)
#define DEF(name, size, pop, push, fmt) size,
#define def(name, size, pop, push, fmt)
#include "quickjs-opcode.h"
#undef FMT
};
static const uint8_t *site(JSValue owner)
{
    JSFunctionBytecode *b = JS_VALUE_GET_OBJ(owner)->u.func.function_bytecode;
    for (unsigned i = 0; i < (unsigned)b->byte_code_len;) {
        unsigned op = b->byte_code_buf[i];
        if (op >= OP_COUNT || !opcode_sizes[op])
            return NULL;
        if (op == OP_call0 || op == OP_call1 || op == OP_call2 || op == OP_call3 || op == OP_call ||
            op == OP_call_method || op == OP_tail_call || op == OP_tail_call_method)
            return b->byte_code_buf + i;
        i += opcode_sizes[op];
    }
    return NULL;
}
static JSValue new_owner(JSContext *ctx)
{
    return eval(ctx, "(function owner(f,x){let y=f(x);return y;})");
}
static JSValue new_target(JSContext *ctx)
{
    return eval(ctx, "(function target(x){for(let i=0;i<2;i++)x++;return x;})");
}
static int warm(Fixture *a, JSValue owner, JSValue target, int x, int expected)
{
    JSValue args[2] = {target, JS_NewInt32(a->ctx, x)};
    for (unsigned i = 0; i < 3; i++)
        CHECK(value_int(a->ctx, JS_Call(a->ctx, owner, JS_UNDEFINED, 2, args), expected) == 0);
    return 0;
}
static void *prepare(Fixture *a, JSValue owner, JSValue target)
{
    return JS_FrameCallLinkPrepare(a->rt, JS_VALUE_GET_OBJ(owner), site(owner),
                                   JS_VALUE_GET_OBJ(target));
}
static unsigned private_nodes(JSValue value)
{
    unsigned n = 0;
    for (JSWeakRefRecord *wr = JS_VALUE_GET_OBJ(value)->first_weak_ref; wr; wr = wr->next_weak_ref)
        if ((int)wr->kind == 0x4c4b0101 || (int)wr->kind == 0x4c4b0102)
            n++;
    return n;
}
/* Builtin weak nodes are owned by the core and may disappear independently.
   A private backlink may therefore name only a direct private predecessor. */
static int backlinks_valid(JSValue value)
{
    JSWeakRefRecord *previous = NULL;
    for (JSWeakRefRecord *wr = JS_VALUE_GET_OBJ(value)->first_weak_ref; wr;
         wr = wr->next_weak_ref) {
        if ((int)wr->kind == 0x4c4b0102) {
            JSWeakRefRecord *owner = (JSWeakRefRecord *)(void *)wr->u.weak_ref_data, *actual;
            uint32_t tag;
            memcpy(&tag, (unsigned char *)owner - 16, 4);
            uintptr_t entries = (uintptr_t)owner + 64, map = (uintptr_t)owner->u.weak_ref_data;
            size_t count = (map - entries) / 64, offset = (uintptr_t)wr - entries;
            void *slot = offset < count * 64
                             ? (unsigned char *)owner + (tag & UINT32_C(0x7fffffff)) +
                                   (offset / 64) * sizeof(void *)
                             : (unsigned char *)wr + 64;
            memcpy(&actual, slot, sizeof(actual));
            JSWeakRefRecord *expected =
                previous && ((int)previous->kind == 0x4c4b0101 || (int)previous->kind == 0x4c4b0102)
                    ? previous
                    : NULL;
            /* Core deletion may create a new private adjacency without updating us;
      a NULL predecessor deliberately keeps the original search fallback. */
            if (actual && actual != expected)
                return 0;
        }
        previous = wr;
    }
    return 1;
}
_Static_assert(sizeof(JSWeakRefRecord) == 24 && offsetof(JSWeakRefRecord, u) == 16,
               "Current weak owner is at offset16; offset24 owns an optional PIC alternate");
static int cleared(void *entry)
{
    JSWeakRefRecord *weak = entry, *owner = (JSWeakRefRecord *)(void *)weak->u.weak_ref_data;
    uintptr_t fields[4];
    memcpy(fields, (unsigned char *)entry + 24, sizeof(fields));
    uint64_t geometry;
    memcpy(&geometry, (unsigned char *)entry + 56, 8);
    if ((int)weak->kind != 0x4c4b0102 || weak->next_weak_ref || !owner ||
        (int)owner->kind != 0x4c4b0101)
        return 0;
    if (fields[0] > 1) {
        JSWeakRefRecord *alternate = (JSWeakRefRecord *)fields[0];
        if ((int)alternate->kind != 0x4c4b0102 ||
            alternate->u.weak_ref_data != weak->u.weak_ref_data)
            return 0;
    }
    return fields[1] == 0 && fields[2] == 0 && fields[3] == 0 &&
           (geometry & UINT64_C(0x00ffffffffffffff)) == 0;
}
static int teardown(Fixture *a)
{
    JS_FreeContext(a->ctx);
    JS_FreeRuntime(a->rt);
    CHECK(a->live == 0 && a->errors == 0 && !a->recycled);
    return 0;
}
static int run(unsigned *reused_out, unsigned *finalized_out, unsigned *reentries_out)
{
    Fixture a = {0};
    ArenaPressure pressure = {0};
    CHECK(setup(&a) == 0);
    JSContext *ctx = a.ctx;
    uint64_t st[8];
    JSValue owner = new_owner(ctx), target = new_target(ctx);
    CHECK(JS_IsObject(owner) && JS_IsObject(target));
    CHECK(site(owner));
    CHECK(warm(&a, owner, target, 7, 9) == 0);
    if (getenv("QJS_DISABLE_CALL_LINK")) {
        CHECK(prepare(&a, owner, target) == NULL);
        JS_FrameCallLinkStats(&owner, st);
        CHECK(st[0] == 0);
        JS_FreeValue(ctx, target);
        JS_FreeValue(ctx, owner);
        CHECK(teardown(&a) == 0);
        return 0;
    }
    void *entry = prepare(&a, owner, target);
    CHECK(entry);
    CHECK(prepare(&a, owner, target) == entry);
    JS_FrameCallLinkStats(&owner, st);
    CHECK(st[0] == 1 && st[5] == 1 &&
          st[6] ==
              (((128 + (unsigned)JS_VALUE_GET_OBJ(owner)->u.func.function_bytecode->byte_code_len +
                 7u) &
                ~UINT64_C(7)) +
               sizeof(void *) + 16));
#ifdef QJS_INTERP_FRAME_DIAGNOSTICS
    CHECK(st[1] == 0 && st[3] == 1);
#endif
    CHECK(attach(&a, target, 0) == 0);
    unsigned f = a.finalized;
    JS_FreeValue(ctx, target);
    CHECK(a.finalized == f + 1);
    CHECK(cleared(entry));
    JS_FrameCallLinkStats(&owner, st);
    CHECK(st[5] == 0);
#ifdef QJS_INTERP_FRAME_DIAGNOSTICS
    CHECK(st[4] == 1);
#endif
    /* The prefix allocator has engine arenas. The inline-header allocator uses
    the host heap, whose reuse policy is unspecified and varies by thread.
    Recycle exact-size host blocks locally during this phase so reuse is an
    explicit precondition; leave OOM/reentry phases on the ordinary allocator. */
    a.recycle = !QJS_ABI_HAS_PREFIX_RC;
    uintptr_t seen[200];
    unsigned reused = 0;
    for (unsigned i = 0; i < 200; i++) {
        target = new_target(ctx);
        CHECK(JS_IsObject(target));
        uintptr_t p = (uintptr_t)JS_VALUE_GET_OBJ(target);
        for (unsigned j = 0; j < i; j++)
            if (p == seen[j]) {
                reused++;
                break;
            }
        seen[i] = p;
        CHECK(warm(&a, owner, target, 7, 9) == 0);
        CHECK(attach(&a, target, i & 1) == 0);
        entry = prepare(&a, owner, target);
        CHECK(entry);
        f = a.finalized;
        JS_FreeValue(ctx, target);
        JS_RunGC(a.rt);
        CHECK(a.finalized == f + 1);
        CHECK(cleared(entry));
    }
    a.recycle = 0;
    while (a.recycled) {
        Block *b = a.recycled;
        a.recycled = b->next;
        free(b);
    }
    CHECK(reused > 0);
    JS_FreeValue(ctx, owner);
    /* Owner dies first: every borrowed target weak node must be unlinked. */
    owner = new_owner(ctx);
    target = new_target(ctx);
    CHECK(warm(&a, owner, target, 7, 9) == 0);
    CHECK(prepare(&a, owner, target));
    CHECK(private_nodes(target) == 1);
    JS_FreeValue(ctx, owner);
    CHECK(private_nodes(target) == 0);
    JS_FreeValue(ctx, target);
    /* High fan-in, builtin prepend/removal, oldest/newest/interior unlink and
    alternating live targets. Check the complete list after every mutation. */
    {
        enum { FAN_IN = 192 };
        JSValue callers[FAN_IN], other = new_target(ctx);
        target = new_target(ctx);
        CHECK(JS_IsObject(target) && JS_IsObject(other));
        JSValue global = JS_GetGlobalObject(ctx);
        CHECK(JS_SetPropertyStr(ctx, global, "callLinkTarget", JS_DupValue(ctx, target)) >= 0);
        CHECK(value_int(ctx, eval(ctx, "globalThis.callLinkWeakRefs=[];0"), 0) == 0);
        for (unsigned i = 0; i < FAN_IN; i++) {
            callers[i] = new_owner(ctx);
            CHECK(JS_IsObject(callers[i]));
            CHECK(warm(&a, callers[i], target, 7, 9) == 0);
            CHECK(prepare(&a, callers[i], target));
            if (i % 31 == 0)
                CHECK(value_int(ctx,
                                eval(ctx, "callLinkWeakRefs.push(new WeakRef(callLinkTarget));0"),
                                0) == 0);
            CHECK(backlinks_valid(target));
        }
        CHECK(private_nodes(target) == FAN_IN);
        CHECK(value_int(ctx, eval(ctx, "callLinkWeakRefs.splice(1,3);0"), 0) == 0);
        JS_RunGC(a.rt);
        CHECK(backlinks_valid(target));
        for (unsigned i = 0; i < FAN_IN; i++) {
            unsigned index = (i & 1) ? FAN_IN - 1 - i / 2 : i / 2;
            if (i % 3 == 0) {
                CHECK(warm(&a, callers[index], other, 7, 9) == 0);
                CHECK(prepare(&a, callers[index], other));
                CHECK(backlinks_valid(target) && backlinks_valid(other));
            }
            JS_FreeValue(ctx, callers[index]);
            CHECK(backlinks_valid(target) && backlinks_valid(other));
        }
        CHECK(private_nodes(target) == 0 && private_nodes(other) == 0);
        CHECK(
            value_int(
                ctx,
                eval(ctx, "delete globalThis.callLinkWeakRefs;delete globalThis.callLinkTarget;0"),
                0) == 0);
        JS_FreeValue(ctx, global);
        JS_FreeValue(ctx, other);
        JS_FreeValue(ctx, target);
    }
    owner = new_owner(ctx);
    target = new_target(ctx);
    CHECK(warm(&a, owner, target, 7, 9) == 0);
    CHECK(prepare(&a, owner, target));
    CHECK(attach(&a, owner, 1) == 0);
    JS_FreeValue(ctx, owner);
    JS_RunGC(a.rt);
    CHECK(private_nodes(target) == 0);
    JS_FreeValue(ctx, target);
    /* Cache ownership is per actual caller, and a target may belong to another realm. */
    JSContext *other = JS_NewContext(a.rt);
    CHECK(other);
    owner = new_owner(ctx);
    target = new_target(other);
    CHECK(warm(&a, owner, target, 7, 9) == 0);
    entry = prepare(&a, owner, target);
    CHECK(entry);
    JSFunctionBytecode *linked_b = NULL;
    memcpy(&linked_b, (unsigned char *)entry + 40, sizeof(linked_b));
    CHECK(linked_b->realm == other);
    CHECK(JS_FrameCallLinkPrepare(a.rt, JS_VALUE_GET_OBJ(owner), NULL, JS_VALUE_GET_OBJ(target)) ==
          NULL);
    JS_FreeValue(ctx, owner);
    CHECK(private_nodes(target) == 0);
    JS_FreeValue(other, target);
    JS_FreeContext(other);
    /* Same code, distinct closures must link by actual callee identity. */
    JSValue pair = eval(
        ctx,
        "(()=>{function make(k){return function(x){for(let i=0;i<2;i++)x++;return x+k;};}return [make(1),make(2)];})()");
    JSValue ta = JS_GetPropertyUint32(ctx, pair, 0), tb = JS_GetPropertyUint32(ctx, pair, 1);
    JS_FreeValue(ctx, pair);
    owner = new_owner(ctx);
    CHECK(JS_VALUE_GET_OBJ(ta)->u.func.function_bytecode ==
          JS_VALUE_GET_OBJ(tb)->u.func.function_bytecode);
    CHECK(warm(&a, owner, ta, 7, 10) == 0);
    void *primary = prepare(&a, owner, ta);
    CHECK(primary);
    CHECK(warm(&a, owner, tb, 7, 11) == 0);
    entry = prepare(&a, owner, tb);
    CHECK(entry && entry != primary);
    JSObject *linked = NULL;
    memcpy(&linked, (unsigned char *)entry + 32, sizeof(linked));
    CHECK(linked == JS_VALUE_GET_OBJ(tb));
    CHECK(private_nodes(ta) == 1 && private_nodes(tb) == 1);
    JS_FreeValue(ctx, ta);
    CHECK(cleared(primary));
    JS_FreeValue(ctx, tb);
    CHECK(cleared(entry));
    JS_FreeValue(ctx, owner);
    /* Self recursion has owner and target nodes on the SAME weak list. */
    JSValue self = eval(
        ctx,
        "globalThis.callLinkSelf=function(n){let r=n;for(let i=0;i<2;i++)r+=i;if(n>0)r=callLinkSelf(n-1);return r;}");
    JSValue n = JS_NewInt32(ctx, 3);
    CHECK(value_int(ctx, JS_Call(ctx, self, JS_UNDEFINED, 1, &n), 1) == 0);
    CHECK(site(self));
    entry = prepare(&a, self, self);
    if (!entry)
        fprintf(stderr, "SELF_KIND=%u OP=%u\n",
                ((unsigned char *)JS_VALUE_GET_OBJ(self)->u.func.function_bytecode)[23],
                *site(self));
    CHECK(entry);
    CHECK(private_nodes(self) == 2);
    CHECK(attach(&a, self, 1) == 0);
    CHECK(value_int(ctx, eval(ctx, "delete globalThis.callLinkSelf;0"), 0) == 0);
    JS_FreeValue(ctx, self);
    JS_RunGC(a.rt);
    /* Mixed native/builtin weak kinds, including recursive weak-value cleanup. */
    owner = new_owner(ctx);
    target = new_target(ctx);
    CHECK(warm(&a, owner, target, 7, 9) == 0);
    entry = prepare(&a, owner, target);
    CHECK(entry);
    JSValue global = JS_GetGlobalObject(ctx);
    CHECK(JS_SetPropertyStr(ctx, global, "testCaller", JS_DupValue(ctx, owner)) >= 0);
    CHECK(JS_SetPropertyStr(ctx, global, "testTarget", JS_DupValue(ctx, target)) >= 0);
    JS_FreeValue(ctx, global);
    CHECK(
        value_int(
            ctx,
            eval(
                ctx,
                "globalThis.finalizedJobs=0;globalThis.registry=new FinalizationRegistry(v=>{finalizedJobs+=v;});registry.register(testTarget,1);globalThis.map=new WeakMap([[testTarget,{owner:testCaller}]]);globalThis.weak=new WeakRef(testTarget);0"),
            0) == 0);
    CHECK(prepare(&a, owner, target) == entry);
    CHECK(value_int(ctx, eval(ctx, "delete globalThis.testTarget;0"), 0) == 0);
    JS_FreeValue(ctx, target);
    JS_RunGC(a.rt);
    CHECK(cleared(entry));
    CHECK(value_int(ctx, eval(ctx, "weak.deref()===undefined?1:0"), 1) == 0);
    JSContext *jobctx;
    int jobs;
    unsigned jobcount = 0;
    while ((jobs = JS_ExecutePendingJob(a.rt, &jobctx)) > 0)
        CHECK(++jobcount < 100);
    CHECK(jobs == 0);
    CHECK(value_int(ctx, eval(ctx, "finalizedJobs"), 1) == 0);
    CHECK(
        value_int(
            ctx,
            eval(
                ctx,
                "delete globalThis.testCaller;globalThis.map=null;globalThis.weak=null;globalThis.registry=null;0"),
            0) == 0);
    JS_FreeValue(ctx, owner);
    /* Optional-cache OOM must preserve a pre-existing exception. */
    owner = new_owner(ctx);
    target = new_target(ctx);
    CHECK(warm(&a, owner, target, 7, 9) == 0);
    JS_ThrowTypeError(ctx, "preserved-call-link-exception");
    CHECK(arena_pressure_begin(
              a.rt,
              128 + (unsigned)JS_VALUE_GET_OBJ(owner)->u.func.function_bytecode->byte_code_len,
              &pressure) == 0);
    a.fail = 1;
    CHECK(prepare(&a, owner, target) == NULL);
    a.fail = 0;
    arena_pressure_end(a.rt, &pressure);
    JSValue e = JS_GetException(ctx);
    const char *message = JS_ToCString(ctx, e);
    CHECK(message && strstr(message, "preserved-call-link-exception"));
    JS_FreeCString(ctx, message);
    JS_FreeValue(ctx, e);
    CHECK(prepare(&a, owner, target) == NULL);
    JS_FreeValue(ctx, owner);
    JS_FreeValue(ctx, target);
    /* Allocator reentry installs an owner before the outer allocation returns. */
    a.owner = new_owner(ctx);
    a.target = new_target(ctx);
    CHECK(warm(&a, a.owner, a.target, 7, 9) == 0);
    a.pc = site(a.owner);
    CHECK(arena_pressure_begin(
              a.rt,
              128 + (unsigned)JS_VALUE_GET_OBJ(a.owner)->u.func.function_bytecode->byte_code_len,
              &pressure) == 0);
    a.armed = 1;
    entry = prepare(&a, a.owner, a.target);
    arena_pressure_end(a.rt, &pressure);
    CHECK(entry && entry == a.inner_entry && a.reentries == 1);
    JS_FrameCallLinkStats(&a.owner, st);
    CHECK(st[0] == 1 && st[5] == 1);
    JS_FreeValue(ctx, a.owner);
    JS_FreeValue(ctx, a.target);
    a.owner = a.target = JS_UNDEFINED;
    *reused_out = reused;
    *finalized_out = a.finalized;
    *reentries_out = a.reentries;
    CHECK(teardown(&a) == 0);
    return 0;
}
static DWORD WINAPI worker(void *opaque)
{
    unsigned *error = opaque, reused = 0, f = 0, r = 0;
    *error = run(&reused, &f, &r);
    return 0;
}
int main(void)
{
    unsigned reused = 0, finalized = 0, reentries = 0;
    CHECK(run(&reused, &finalized, &reentries) == 0);
    HANDLE threads[4];
    unsigned errors[4] = {0};
    for (unsigned i = 0; i < 4; i++) {
        threads[i] = CreateThread(NULL, 0, worker, &errors[i], 0, NULL);
        CHECK(threads[i]);
    }
    CHECK(WaitForMultipleObjects(4, threads, TRUE, 60000) == WAIT_OBJECT_0);
    for (unsigned i = 0; i < 4; i++) {
        CloseHandle(threads[i]);
        CHECK(errors[i] == 0);
    }
    printf(
        "CALL_LINK_LIFECYCLE_PASS diagnostic=%d off=%d threads=4 reuse=%u finalized=%u allocator_reentries=%u live=0\n",
#ifdef QJS_INTERP_FRAME_DIAGNOSTICS
        1,
#else
        0,
#endif
        getenv("QJS_DISABLE_CALL_LINK") != NULL, reused, finalized, reentries);
    return 0;
}
