#ifdef NDEBUG
#undef NDEBUG
#endif
#include "quickjs.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "tests/common/native_oom_allocator.h"
extern void qjs_aarch64_vm_call_leaf_counts(uint64_t[12]);
extern void qjs_aarch64_vm_host_return_counts(uint64_t[4]);
typedef struct Owner {
    JSContext *ctx;
    JSValue nested;
    JSClassID id;
    unsigned born, dead, reentered;
} Owner;
static JSValue evaluate(JSContext *c, const char *s)
{
    JSValue v = JS_Eval(c, s, strlen(s), "leaf-owners.js", JS_EVAL_TYPE_GLOBAL);
    assert(!JS_IsException(v));
    return v;
}
static void finalize(JSRuntime *rt, JSValue v)
{
    Owner *h = JS_GetRuntimeOpaque(rt);
    (void)v;
    h->dead++;
    JSValue out = JS_Call(h->ctx, h->nested, JS_UNDEFINED, 0, NULL);
    int32_t n;
    assert(!JS_IsException(out) && !JS_ToInt32(h->ctx, &n, out) && n == 42);
    JS_FreeValue(h->ctx, out);
    h->reentered++;
}
static JSValue make(JSContext *c, JSValueConst self, int argc, JSValueConst *argv)
{
    Owner *h = JS_GetRuntimeOpaque(JS_GetRuntime(c));
    (void)self;
    (void)argc;
    (void)argv;
    JSValue out = JS_NewObjectClass(c, h->id);
    if (!JS_IsException(out))
        h->born++;
    return out;
}
int main(void)
{
    Allocator a = {0};
    JSRuntime *rt = JS_NewRuntime2(&functions, &a);
    assert(rt);
    JSContext *c = JS_NewContext(rt);
    assert(c);
    Owner h = {.ctx = c};
    JS_SetRuntimeOpaque(rt, &h);
    JS_NewClassID(rt, &h.id);
    JSClassDef definition = {.class_name = "LeafLastOwner", .finalizer = finalize};
    assert(!JS_NewClass(rt, h.id, &definition));
    h.nested = evaluate(c, "(function(){return 42;})");
    JSValue global = JS_GetGlobalObject(c);
    assert(JS_SetPropertyStr(c, global, "makeLeafOwner",
                             JS_NewCFunction(c, make, "makeLeafOwner", 0)) >= 0);
    JS_FreeValue(c, global);
    JSValue f = evaluate(c, "(function(x){return 7;})"),
            driver = evaluate(c, "(function(f){return f(makeLeafOwner());})");
    uint64_t before[4], after[4], leaves[12];
    qjs_aarch64_vm_host_return_counts(before);
    for (unsigned i = 0; i < 130; i++) {
        JSValue out = JS_Call(c, driver, JS_UNDEFINED, 1, &f);
        int32_t n;
        assert(!JS_IsException(out) && !JS_ToInt32(c, &n, out) && n == 7);
        JS_FreeValue(c, out);
        JS_RunGC(rt);
    }
    qjs_aarch64_vm_host_return_counts(after);
    qjs_aarch64_vm_call_leaf_counts(leaves);
    assert(h.born == 130 && h.dead == 130 && h.reentered == 130);
#ifndef QJS_TEST_BASELINE
    if (!getenv("QJS_DISABLE_AARCH64_HOST_RETURN") && !getenv("QJS_DISABLE_INTERP_FRAME") &&
        !getenv("QJS_DISABLE_REGISTER_INTERP") && !getenv("QJS_DISABLE_FRAME_LEAF_ENTRY"))
        assert(after[2] - before[2] >= 128);
#endif
    JS_FreeValue(c, driver);
    JS_FreeValue(c, f);
    JS_FreeValue(c, h.nested);
    JS_RunGC(rt);
    JS_FreeContext(c);
    JS_FreeRuntime(rt);
    assert(!a.live && !a.bytes);
    printf(
        "AARCH64_CALL_LEAF_OWNERS_OK born=%u finalized=%u GC_JS_reentry=%u native_final=%llu leaves=%llu zero-ledgers\n",
        h.born, h.dead, h.reentered, (unsigned long long)(after[2] - before[2]),
        (unsigned long long)leaves[10]);
    return 0;
}
