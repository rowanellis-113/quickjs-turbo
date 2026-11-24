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
extern void qjs_aarch64_vm_scalar_counts(uint64_t[22]);
extern void qjs_aarch64_vm_opcode_counts(uint64_t[256]);
extern int qjs_aarch64_vm_function_info(JSValueConst, uintptr_t *);
#include "interpreter-aarch64-values.h"
typedef struct Host {
    JSContext *ctx;
    JSValue nested;
    JSClassID id;
    unsigned born, dead, reentries, depth;
} Host;
static JSValue evaluate(JSContext *c, const char *s)
{
    JSValue v = JS_Eval(c, s, strlen(s), "scalar-owners.js", JS_EVAL_TYPE_GLOBAL);
    assert(!JS_IsException(v));
    return v;
}
static void finalize(JSRuntime *r, JSValue value)
{
    Host *h = JS_GetRuntimeOpaque(r);
    (void)value;
    h->dead++;
    if (!h->depth) {
        h->depth++;
        JSValue x = JS_NewInt32(h->ctx, 5), v = JS_Call(h->ctx, h->nested, JS_UNDEFINED, 1, &x);
        int32_t n;
        assert(!JS_IsException(v) && !JS_ToInt32(h->ctx, &n, v) && n == 7);
        JS_FreeValue(h->ctx, v);
        h->reentries++;
        h->depth--;
    }
}
static JSValue fresh(JSContext *c, JSValueConst self, int argc, JSValueConst *argv)
{
    Host *h = JS_GetRuntimeOpaque(JS_GetRuntime(c));
    (void)self;
    (void)argc;
    (void)argv;
    JSValue v = JS_NewObjectClass(c, h->id);
    if (!JS_IsException(v))
        h->born++;
    return v;
}
static void last_owners(void)
{
    Allocator a = {0};
    JSRuntime *r = JS_NewRuntime2(&functions, &a);
    assert(r);
    JSContext *c = JS_NewContext(r);
    assert(c);
    Host h = {.ctx = c};
    JS_SetRuntimeOpaque(r, &h);
    JS_NewClassID(r, &h.id);
    JSClassDef d = {.class_name = "ScalarOwner", .finalizer = finalize};
    assert(!JS_NewClass(r, h.id, &d));
    h.nested = evaluate(c, "(function(x){return x|3})");
    JSValue g = JS_GetGlobalObject(c);
    assert(JS_SetPropertyStr(c, g, "freshScalar", JS_NewCFunction(c, fresh, "freshScalar", 0)) >=
           0);
    JS_FreeValue(c, g);
    const char *bodies[] = {"(function(){return freshScalar()===void 0})",
                            "(function(){return freshScalar()===null})",
                            "(function(){let a=freshScalar();return (a??null)===null})"};
    for (unsigned k = 0; k < 3; k++) {
        uint64_t before[22], after[22], cb[256], ca[256];
        JSValue f = evaluate(c, bodies[k]);
        qjs_aarch64_vm_scalar_counts(before);
        qjs_aarch64_vm_opcode_counts(cb);
        for (unsigned i = 0; i < 130; i++) {
            JSValue v = JS_Call(c, f, JS_UNDEFINED, 0, NULL);
            assert(!JS_IsException(v) && JS_ToBool(c, v) == 0);
            JS_FreeValue(c, v);
            JS_RunGC(r);
        }
        qjs_aarch64_vm_scalar_counts(after);
        qjs_aarch64_vm_opcode_counts(ca);
        if (k < 2) {
            unsigned op = k ? ARM_OP_is_null : ARM_OP_is_undefined;
            assert(after[16 + k] == before[16 + k]);
            if (!getenv("QJS_DISABLE_INTERP_FRAME") && !getenv("QJS_DISABLE_REGISTER_INTERP"))
                assert(ca[op] - cb[op] >= 130);
            printf("SCALAR_LAST_ROUTE cohort=%u native=0 C=%llu\n", k,
                   (unsigned long long)(ca[op] - cb[op]));
        }
        JS_FreeValue(c, f);
    }
    assert(h.born == 390 && h.dead == 390 && h.reentries == 390);
    JS_FreeValue(c, h.nested);
    JS_FreeContext(c);
    JS_FreeRuntime(r);
    assert(!a.live && !a.bytes);
    printf("SCALAR_LAST_OWNERS_OK made=%u finalized=%u JS_reentry=%u zero-ledgers\n", h.born,
           h.dead, h.reentries);
}
static void property_oom(void)
{
    unsigned failed = 0, passed = 0;
    for (unsigned step = 1; step <= 32; step++) {
        Allocator a = {0};
        JSRuntime *r = JS_NewRuntime2(&functions, &a);
        assert(r);
        JSContext *c = JS_NewContext(r);
        assert(c);
        JSValue f = evaluate(c, "(function(o,k){return o[k]++;})"), o = JS_NewObject(c),
                key = evaluate(c, "({[Symbol.toPrimitive](){return 123456789.25}})"),
                args[2] = {o, key};
        assert(JS_SetPropertyStr(c, o, "123456789.25", JS_NewInt32(c, 7)) >= 0);
        AllocatorArenaDrain drain = {0};
        oom_drain_arenas(r, &a, &drain);
        a.fail_at = a.sequence + step;
        JSValue v = JS_Call(c, f, JS_UNDEFINED, 2, args);
        a.fail_at = 0;
        oom_undrain_arenas(r, &drain);
        if (JS_IsException(v)) {
            failed++;
            JS_FreeValue(c, JS_GetException(c));
        } else {
            passed++;
            int32_t n;
            assert(!JS_ToInt32(c, &n, v) && n == 7);
            JS_FreeValue(c, v);
        }
        assert(JS_SetPropertyStr(c, o, "123456789.25", JS_NewInt32(c, 7)) >= 0);
        v = JS_Call(c, f, JS_UNDEFINED, 2, args);
        assert(!JS_IsException(v));
        int32_t n;
        assert(!JS_ToInt32(c, &n, v) && n == 7);
        JS_FreeValue(c, v);
        uintptr_t info[6];
        assert(qjs_aarch64_vm_function_info(f, info));
        if (!getenv("QJS_DISABLE_INTERP_FRAME") && !getenv("QJS_DISABLE_REGISTER_INTERP"))
            assert((info[0] & 7) == 3);
        JS_FreeValue(c, key);
        JS_FreeValue(c, o);
        JS_FreeValue(c, f);
        JS_RunGC(r);
        JS_FreeContext(c);
        JS_FreeRuntime(r);
        assert(!a.live && !a.bytes);
    }
    assert(failed && passed);
    printf("SCALAR_PROPERTY_KEY_OOM_OK fail=%u pass=%u fresh-runtimes=32 zero-ledgers\n", failed,
           passed);
}
int main(void)
{
    last_owners();
    property_oom();
    puts("AARCH64_SCALAR_OWNERS_OK");
    return 0;
}
