/* Public null-object ownership,realm/GC reentry and fresh allocator faults. */
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
    Allocator ledger;
    JSRuntime *rt;
    JSContext *caller, *realm;
    JSValue nested;
    size_t trigger, observed;
    unsigned armed, reentries, touches;
} Host;
static void null_object(JSContext *ctx, JSValueConst object)
{
    assert(JS_IsObject(object));
    JSValue prototype = JS_GetPrototype(ctx, object);
    assert(JS_IsNull(prototype));
    JS_FreeValue(ctx, prototype);
}
static void allocation_reentry(Host *h)
{
    if (!h->armed || ++h->observed != h->trigger)
        return;
    h->armed = 0;
    ++h->reentries;
    JS_RunGC(h->rt);
    JSValue value = JS_Call(h->caller, h->nested, JS_UNDEFINED, 0, NULL);
    null_object(h->caller, value);
    JS_FreeValue(h->caller, value);
    JS_RunGC(h->rt);
}
static void *host_malloc(void *opaque, size_t size)
{
    Host *h = opaque;
    allocation_reentry(h);
    return allocate(&h->ledger, size);
}
static void *host_calloc(void *opaque, size_t count, size_t size)
{
    Host *h = opaque;
    allocation_reentry(h);
    return allocate_zero(&h->ledger, count, size);
}
static void *host_realloc(void *opaque, void *ptr, size_t size)
{
    Host *h = opaque;
    allocation_reentry(h);
    return resize(&h->ledger, ptr, size);
}
static void host_free(void *opaque, void *ptr)
{
    Host *h = opaque;
    release(&h->ledger, ptr);
}
static const JSMallocFunctions host_functions = {host_calloc, host_malloc, host_free, host_realloc,
                                                 usable};
static JSValue evaluate(JSContext *ctx, const char *text)
{
    JSValue value = JS_Eval(ctx, text, strlen(text), "null-proto-public", JS_EVAL_TYPE_GLOBAL);
    if (JS_IsException(value)) {
        JSValue error = JS_GetException(ctx);
        const char *message = JS_ToCString(ctx, error);
        fprintf(stderr, "%s\n", message ? message : "null exception");
        assert(0);
    }
    return value;
}
static void setup(Host *h)
{
    h->rt = JS_NewRuntime2(&host_functions, h);
    assert(h->rt);
    JS_SetRuntimeOpaque(h->rt, h);
    JS_SetMaxStackSize(h->rt, 2 * 1024 * 1024);
    h->caller = JS_NewContext(h->rt);
    h->realm = JS_NewContext(h->rt);
    assert(h->caller && h->realm);
    h->nested = evaluate(h->realm, "(function(){return {__proto__:null};})");
}
static void teardown(Host *h)
{
    h->armed = 0;
    h->ledger.fail_at = 0;
    JS_FreeValue(h->realm, h->nested);
    JS_FreeContext(h->caller);
    JS_FreeContext(h->realm);
    JS_RunGC(h->rt);
    JS_FreeRuntime(h->rt);
    assert(!h->ledger.live && !h->ledger.bytes);
}
static JSValue touch(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)self;
    Host *h = JS_GetRuntimeOpaque(JS_GetRuntime(ctx));
    assert(ctx == h->realm && argc == 1);
    ++h->touches;
    null_object(ctx, argv[0]);
    JS_RunGC(h->rt);
    JSValue nested = JS_Call(h->caller, h->nested, JS_UNDEFINED, 0, NULL);
    null_object(h->caller, nested);
    JS_FreeValue(h->caller, nested);
    return JS_UNDEFINED;
}
static void semantics(void)
{
    Host h = {0};
    setup(&h);
    JSValue global = JS_GetGlobalObject(h.realm);
    assert(JS_SetPropertyStr(h.realm, global, "touch",
                             JS_NewCFunction(h.realm, touch, "touch", 1)) > 0);
    JS_FreeValue(h.realm, global);
    JSValue function =
        evaluate(h.realm, "(function(v){var live={x:v};live.self=live;var out={__proto__:null};"
                          "out.live=live;touch(out);return out;})");
    for (int i = 0; i < 32; i++) {
        JSValue input = JS_NewInt32(h.caller, i);
        JSValue value = JS_Call(h.caller, function, JS_UNDEFINED, 1, &input);
        null_object(h.caller, value);
        JSValue live = JS_GetPropertyStr(h.caller, value, "live"),
                x = JS_GetPropertyStr(h.caller, live, "x");
        int32_t n;
        assert(JS_ToInt32(h.caller, &n, x) == 0 && n == i);
        JS_FreeValue(h.caller, x);
        JS_FreeValue(h.caller, live);
        JS_FreeValue(h.caller, value);
    }
    assert(h.touches == 32);
    JS_FreeValue(h.realm, function);
    teardown(&h);
}
static size_t attempt(int warm, size_t failure, size_t trigger, unsigned *rejected,
                      unsigned *reentries)
{
    Host h = {0};
    setup(&h);
    JSValue function = evaluate(h.realm, "(function(){return {__proto__:null};})");
    JSValue keeper = JS_UNDEFINED;
    if (warm) {
        keeper = JS_Call(h.caller, function, JS_UNDEFINED, 0, NULL);
        null_object(h.caller, keeper);
    }
    AllocatorArenaDrain drain = {0};
    oom_drain_arenas(h.rt, &h.ledger, &drain);
    h.ledger.sequence = 0;
    h.ledger.fail_at = failure;
    h.trigger = trigger;
    h.armed = trigger != 0;
    JSValue value = JS_Call(h.caller, function, JS_UNDEFINED, 0, NULL);
    h.armed = 0;
    h.ledger.fail_at = 0;
    size_t requests = h.ledger.sequence;
    *rejected = h.ledger.rejected;
    *reentries = h.reentries;
    if (JS_IsException(value))
        value = JS_GetException(h.caller);
    else
        null_object(h.caller, value);
    JS_FreeValue(h.caller, value);
    value = JS_Call(h.caller, function, JS_UNDEFINED, 0, NULL);
    null_object(h.caller, value);
    JS_FreeValue(h.caller, value);
    JS_FreeValue(h.caller, keeper);
    JS_FreeValue(h.realm, function);
    oom_undrain_arenas(h.rt, &drain);
    teardown(&h);
    return requests;
}
int main(void)
{
    /* The shared fixture allocator is deliberately retained as a checked
       public fallback;the custom wrapper adds bounded reentry before requests. */
    assert(functions.js_malloc && host_functions.js_malloc);
    semantics();
    unsigned rejected, reentries, total = 0;
    for (int warm = 0; warm < 2; warm++) {
        size_t requests = attempt(warm, 0, 0, &rejected, &reentries);
        assert(requests > 0 && requests < 64 && !rejected && !reentries);
        for (size_t n = 1; n <= requests + 1; n++) {
            attempt(warm, n, 0, &rejected, &reentries);
            assert(rejected == (n <= requests));
            total += rejected;
        }
        for (size_t n = 1; n <= requests; n++) {
            attempt(warm, 0, n, &rejected, &reentries);
            assert(!rejected && reentries == 1);
        }
    }
    printf("LINUX_NULL_PROTO_PUBLIC_OK faults=%u\n", total);
    return 0;
}
