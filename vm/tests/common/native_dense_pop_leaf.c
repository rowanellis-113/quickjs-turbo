#include "quickjs.h"
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

extern unsigned JS_FrameDensePopLeafState(void);
extern uint64_t JS_FrameDensePopLeafCount(void);
typedef struct Block {
    size_t size;
    uint64_t magic;
} Block;
typedef struct Allocator {
    JSRuntime *rt;
    JSContext *ctx;
    size_t live;
    void *target;
    unsigned armed, reentry, gc, error, finalized;
} Allocator;
static JSClassID token_class;
static void *allocate(void *opaque, size_t size)
{
    Allocator *a = opaque;
    Block *b = malloc(sizeof(*b) + size);
    if (!b)
        return NULL;
    b->size = size;
    b->magic = UINT64_C(0xdeaf4424);
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
    Allocator *a = opaque;
    Block *b = (Block *)p - 1;
    if (b->magic != UINT64_C(0xdeaf4424) || !a->live)
        abort();
    uintptr_t q = (uintptr_t)a->target, lo = (uintptr_t)p;
    if (a->armed && q >= lo && q - lo < b->size) {
        a->armed = 0;
        a->target = NULL;
        JS_RunGC(a->rt);
        a->gc++;
        const char *code = "globalThis.leafAnchor.x===91 && 9n*9n+10n===91n";
        JSValue r =
            JS_Eval(a->ctx, code, strlen(code), "allocator-reentry.js", JS_EVAL_TYPE_GLOBAL);
        if (JS_IsException(r) || JS_ToBool(a->ctx, r) != 1)
            a->error = 1;
        JS_FreeValue(a->ctx, r);
        a->reentry++;
    }
    a->live--;
    free(b);
}
static void *resize(void *opaque, void *p, size_t size)
{
    if (!p)
        return allocate(opaque, size);
    if (!size) {
        release(opaque, p);
        return NULL;
    }
    Block *b = realloc((Block *)p - 1, sizeof(*b) + size);
    if (!b)
        return NULL;
    b->size = size;
    return b + 1;
}
static size_t usable(const void *p)
{
    return p ? ((const Block *)p - 1)->size : 0;
}
static void token_finalizer(JSRuntime *rt, JSValue v)
{
    (void)v;
    Allocator *a = JS_GetRuntimeOpaque(rt);
    a->finalized++;
    /* Finalizers only count. JS execution occurs in the allocator hook above. */
}
static JSValue make_array(JSContext *ctx, JSValueConst receiver, int argc, JSValueConst *argv)
{
    (void)receiver;
    (void)argc;
    (void)argv;
    Allocator *a = JS_GetContextOpaque(ctx);
    JSValue array = JS_UNDEFINED, token = JS_NewObjectClass(ctx, token_class);
    if (JS_IsException(token))
        goto fail;
    /* Fill fresh object arenas while every temporary is live. Keep only the
       final receiver, so its later object release reaches the backing free
       hook AFTER remove_gc_object, rather than merely recycling a pool cell. */
    JSValue holding[256];
    unsigned made = 0;
    for (; made < 256; made++) {
        holding[made] = JS_NewArray(ctx);
        if (JS_IsException(holding[made]))
            break;
    }
    if (made != 256) {
        for (unsigned j = 0; j < made; j++)
            JS_FreeValue(ctx, holding[j]);
        goto fail;
    }
    array = holding[255];
    for (unsigned j = 0; j < 255; j++)
        JS_FreeValue(ctx, holding[j]);
    if (JS_SetPropertyStr(ctx, token, "x", JS_NewInt32(ctx, 91)) < 0 ||
        JS_SetPropertyStr(ctx, token, "self", JS_DupValue(ctx, token)) < 0)
        goto fail;
    if (JS_SetPropertyUint32(ctx, array, 0, token) < 0) {
        token = JS_UNDEFINED;
        goto fail;
    }
    a->target = JS_VALUE_GET_PTR(array);
    a->armed = 1;
    return array;
fail:
    JS_FreeValue(ctx, token);
    JS_FreeValue(ctx, array);
    return JS_EXCEPTION;
}
static int error(JSContext *ctx)
{
    JSValue e = JS_GetException(ctx);
    const char *s = JS_ToCString(ctx, e);
    fprintf(stderr, "EXCEPTION %s\n", s ? s : "?");
    JS_FreeCString(ctx, s);
    JS_FreeValue(ctx, e);
    return 2;
}
static int evaluate(JSContext *ctx, const char *code, int expected)
{
    JSValue r = JS_Eval(ctx, code, strlen(code), "dense-pop-leaf-native.js", JS_EVAL_TYPE_GLOBAL);
    if (JS_IsException(r))
        return error(ctx);
    int32_t n = 0;
    int rc = JS_ToInt32(ctx, &n, r);
    JS_FreeValue(ctx, r);
    return rc || n != expected ? 3 : 0;
}
int main(void)
{
    Allocator a = {0};
    JSMallocFunctions mf = {allocate_zero, allocate, release, resize, usable};
    a.rt = JS_NewRuntime2(&mf, &a);
    if (!a.rt)
        return 1;
    JS_SetRuntimeOpaque(a.rt, &a);
    a.ctx = JS_NewContext(a.rt);
    if (!a.ctx)
        return 1;
    JS_SetContextOpaque(a.ctx, &a);
    JS_NewClassID(a.rt, &token_class);
    JSClassDef def = {0};
    def.class_name = "LeafReturnToken";
    def.finalizer = token_finalizer;
    if (JS_NewClass(a.rt, token_class, &def))
        return 4;
    JSValue global = JS_GetGlobalObject(a.ctx);
    if (JS_SetPropertyStr(a.ctx, global, "makeAndArmArray",
                          JS_NewCFunction(a.ctx, make_array, "makeAndArmArray", 0)) < 0)
        return 4;
    JS_FreeValue(a.ctx, global);
    if (evaluate(
            a.ctx,
            "globalThis.leafAnchor={x:91};(()=>{let a=[1,2,3];return a.pop()+a.pop()+a.pop()+(a.pop()===undefined);})()",
            7))
        return 5;
    uint64_t warm_hits = JS_FrameDensePopLeafCount();
    const char *stress =
        "(()=>{let total=0;for(let i=0;i<200;i++){let v=makeAndArmArray().pop();if(v.x!==91||v.self!==v)throw Error('lost return root');total+=v.x;}return total;})()";
    if (evaluate(a.ctx, stress, 18200))
        return 6;
    if (a.armed || a.reentry != 200 || a.error) {
        fprintf(stderr, "REENTRY armed=%u reentry=%u error=%u gc=%u finalized=%u\n", a.armed,
                a.reentry, a.error, a.gc, a.finalized);
        return 7;
    }
    uint64_t hits = JS_FrameDensePopLeafCount();
    int expected_hits = LEAF_DIAGNOSTIC && !getenv("QJS_DISABLE_DENSE_ARRAY_POP_LEAF") &&
                        !getenv("QJS_DISABLE_DENSE_ARRAY_POP") &&
                        (!LEAF_HAS_ARGC_WINDOW || !getenv("QJS_DISABLE_NATIVE_C_ARG_WINDOW")) &&
                        !getenv("QJS_DISABLE_NATIVE_C_INVOKE") &&
                        !getenv("QJS_DISABLE_REGISTER_INTERP");
    if (expected_hits ? (warm_hits < 2 || hits < warm_hits + 200) : hits != 0) {
        fprintf(stderr, "HITS expected=%d warm=%llu hits=%llu\n", expected_hits,
                (unsigned long long)warm_hits, (unsigned long long)hits);
        return 8;
    }
    uint64_t before = hits;
    /* Native functions and ineligible arrays must never hit the leaf body. */
    const char *fallbacks =
        "(()=>{let n=0;for(let i=0;i<40;i++){let a=[9];Object.preventExtensions(a);n+=a.pop();let b=[,];n+=(b.pop()===undefined);n+=Array.prototype.pop.call({0:4,length:1});n+=Number.isNaN(NaN);Date.now();let c=[8];n+=c.pop(123);let d=[7];n+=d.shift();}return n;})()";
    if (evaluate(a.ctx, fallbacks, 1200))
        return 9;
    if (JS_FrameDensePopLeafCount() != before)
        return 10;
    JS_RunGC(a.rt);
    a.gc++;
    if (a.finalized != 200)
        return 11;
    unsigned control = JS_FrameDensePopLeafState();
    JS_FreeContext(a.ctx);
    a.ctx = NULL;
    JS_FreeRuntime(a.rt);
    if (a.live || a.error)
        return 12;
    printf(
        "DENSE_POP_LEAF_PASS diagnostic=%d state=%u warm_hits=%llu hits=%llu reentry=%u gc=%u finalized=%u live=%zu\n",
        LEAF_DIAGNOSTIC, control, (unsigned long long)warm_hits, (unsigned long long)hits,
        a.reentry, a.gc, a.finalized, a.live);
    return 0;
}
