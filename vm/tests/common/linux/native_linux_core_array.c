/* Public core array reads:owning data,getters/GC/realm,zero allocation and OOM. */
#ifdef NDEBUG
#undef NDEBUG
#endif
#include "quickjs.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "../native_oom_allocator.h"

typedef struct {
    JSClassID id;
    unsigned finalized, getters;
    JSContext *realm;
    JSValue nested;
} Host;
static void finalizer(JSRuntime *rt, JSValue value)
{
    Host *h = JS_GetRuntimeOpaque(rt);
    assert(JS_GetOpaque(value, h->id));
    ++h->finalized;
}
static JSValue evaluate(JSContext *ctx, const char *text)
{
    JSValue value = JS_Eval(ctx, text, strlen(text), "core-array-public", JS_EVAL_TYPE_GLOBAL);
    if (JS_IsException(value)) {
        JSValue e = JS_GetException(ctx);
        const char *s = JS_ToCString(ctx, e);
        fprintf(stderr, "%s\n", s ? s : "exception");
        assert(0);
    }
    return value;
}
static JSValue getter(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)self;
    (void)argc;
    (void)argv;
    Host *h = JS_GetRuntimeOpaque(JS_GetRuntime(ctx));
    assert(ctx == h->realm);
    ++h->getters;
    JS_RunGC(JS_GetRuntime(ctx));
    JSValue value = JS_GetPropertyInt64(ctx, h->nested, 37);
    int32_t n;
    assert(JS_ToInt32(ctx, &n, value) == 0 && n == 19);
    return value;
}
static JSValue sparse(JSContext *ctx, JSValue value)
{
    JSValue array = JS_NewArray(ctx);
    assert(!JS_IsException(array));
    /* Nonwritable configurable data forces the ordinary numeric-property
       representation through the public API;the value is transferred. */
    assert(JS_DefinePropertyValueUint32(ctx, array, 37, value,
                                        JS_PROP_CONFIGURABLE | JS_PROP_ENUMERABLE) > 0);
    return array;
}
static void semantics(void)
{
    Allocator ledger = {0};
    Host host = {0};
    JSRuntime *rt = JS_NewRuntime2(&functions, &ledger);
    assert(rt);
    JS_SetRuntimeOpaque(rt, &host);
    JS_SetMaxStackSize(rt, 2 * 1024 * 1024);
    JSContext *a = JS_NewContext(rt), *b = JS_NewContext(rt);
    assert(a && b);
    host.realm = b;
    JS_NewClassID(rt, &host.id);
    JSClassDef def = {0};
    def.class_name = "ArrayOwned";
    def.finalizer = finalizer;
    assert(JS_NewClass(rt, host.id, &def) == 0);
    JSValue object = JS_NewObjectClass(b, host.id);
    assert(!JS_IsException(object));
    JS_SetOpaque(object, (void *)(uintptr_t)1);
    JSValue array = sparse(b, object);
    JSValue owned = JS_GetPropertyInt64(a, array, 37);
    assert(!JS_IsException(owned) && JS_GetOpaque(owned, host.id) == (void *)(uintptr_t)1);
    JS_FreeValue(b, array);
    JS_RunGC(rt);
    assert(!host.finalized);
    JS_FreeValue(a, owned);
    assert(host.finalized == 1);
    JSValue values[] = {JS_NewInt32(b, -23),
                        JS_NewFloat64(b, 1.25),
                        JS_NULL,
                        JS_UNDEFINED,
                        JS_TRUE,
                        JS_NewString(b, "owned"),
                        JS_NewBigInt64(b, INT64_C(9223372036854775807)),
                        evaluate(b, "Symbol('array')")};
    for (unsigned i = 0; i < sizeof(values) / sizeof(values[0]); ++i) {
        assert(!JS_IsException(values[i]));
        array = sparse(b, JS_DupValue(b, values[i]));
        for (unsigned j = 0; j < 32; ++j) {
            JSValue result = JS_GetPropertyInt64(a, array, 37);
            assert(!JS_IsException(result) && JS_IsSameValue(a, result, values[i]));
            JS_FreeValue(a, result);
        }
        JS_FreeValue(b, array);
        JS_FreeValue(b, values[i]);
    }
    host.nested = sparse(b, JS_NewInt32(b, 19));
    array = sparse(b, JS_NewInt32(b, 1));
    JSAtom key = JS_NewAtomUInt32(b, 37);
    JSValue fn = JS_NewCFunction(b, getter, "arrayGetter", 0);
    assert(JS_DefinePropertyGetSet(b, array, key, fn, JS_UNDEFINED, JS_PROP_CONFIGURABLE) > 0);
    JS_FreeAtom(b, key);
    owned = JS_GetPropertyInt64(a, array, 37);
    int32_t n;
    assert(!JS_IsException(owned) && JS_ToInt32(a, &n, owned) == 0 && n == 19 && host.getters == 1);
    JS_FreeValue(a, owned);
    JS_FreeValue(b, array);
    JS_FreeValue(b, host.nested);
    const char *fallbacks[] = {"[11,22]", "new Uint8Array([11,22])",
                               "(function(a){return arguments;})(11,22)", "({0:11,1:22})",
                               "new Proxy([11,22],{get(t,k,r){return Reflect.get(t,k,r);}})"};
    for (unsigned i = 0; i < sizeof(fallbacks) / sizeof(fallbacks[0]); ++i) {
        array = evaluate(b, fallbacks[i]);
        owned = JS_GetPropertyInt64(a, array, 1);
        assert(!JS_IsException(owned) && JS_ToInt32(a, &n, owned) == 0 && n == 22);
        JS_FreeValue(a, owned);
        JS_FreeValue(b, array);
    }
    array = sparse(b, JS_NewString(b, "no allocation"));
    for (unsigned i = 0; i < 16; ++i) {
        owned = JS_GetPropertyInt64(a, array, 37);
        JS_FreeValue(a, owned);
    }
    size_t before = ledger.sequence;
    ledger.fail_at = before + 1;
    for (unsigned i = 0; i < 128; ++i) {
        owned = JS_GetPropertyInt64(a, array, 37);
        assert(JS_IsString(owned));
        JS_FreeValue(a, owned);
    }
    assert(ledger.sequence == before && !ledger.rejected);
    ledger.fail_at = 0;
    owned = JS_GetPropertyInt64(a, array, 38);
    assert(JS_IsUndefined(owned));
    JS_FreeValue(a, owned);
    JS_FreeValue(b, array);
    JS_FreeContext(a);
    JS_FreeContext(b);
    JS_RunGC(rt);
    JS_FreeRuntime(rt);
    assert(!ledger.live && !ledger.bytes && host.finalized == 1);
}
static size_t typed_fault(size_t fault, unsigned *rejected)
{
    Allocator ledger = {0};
    JSRuntime *rt = JS_NewRuntime2(&functions, &ledger);
    assert(rt);
    JSContext *ctx = JS_NewContext(rt);
    assert(ctx);
    JSValue array = evaluate(ctx, "new BigUint64Array([18446744073709551615n])");
    ledger.sequence = 0;
    ledger.fail_at = fault;
    JSValue value = JS_GetPropertyInt64(ctx, array, 0);
    size_t requests = ledger.sequence;
    *rejected = ledger.rejected;
    ledger.fail_at = 0;
    if (JS_IsException(value))
        value = JS_GetException(ctx);
    JS_FreeValue(ctx, value);
    value = JS_GetPropertyInt64(ctx, array, 0);
    assert(!JS_IsException(value) && JS_IsBigInt(value));
    JS_FreeValue(ctx, value);
    JS_FreeValue(ctx, array);
    JS_FreeContext(ctx);
    JS_RunGC(rt);
    JS_FreeRuntime(rt);
    assert(!ledger.live && !ledger.bytes);
    return requests;
}
int main(void)
{
    semantics();
    unsigned rejected = 0, total = 0;
    size_t requests = typed_fault(0, &rejected);
    assert(!rejected && requests > 0 && requests < 16);
    for (size_t i = 1; i <= requests + 1; ++i) {
        typed_fault(i, &rejected);
        total += rejected;
    }
    assert(total == requests);
    printf("LINUX_CORE_ARRAY_PUBLIC_OK noalloc=128 typed_faults=%u\n", total);
    return 0;
}
