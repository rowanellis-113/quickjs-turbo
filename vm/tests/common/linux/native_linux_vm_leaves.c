/* Elided-frame result ownership and original last-owner cleanup. MIT. */
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
static JSClassID resource_class;
static unsigned made, finalized, interrupts;
static JSValue evaluate(JSContext *ctx, const char *text)
{
    JSValue v = JS_Eval(ctx, text, strlen(text), "native-vm-leaves", JS_EVAL_TYPE_GLOBAL);
    if (JS_IsException(v)) {
        JSValue e = JS_GetException(ctx);
        const char *s = JS_ToCString(ctx, e);
        fprintf(stderr, "VM_LEAVES_ERROR %s\n", s ? s : "unknown");
        JS_FreeCString(ctx, s);
        JS_FreeValue(ctx, e);
        abort();
    }
    return v;
}
static void finalize(JSRuntime *rt, JSValue value)
{
    (void)rt;
    (void)value;
    ++finalized;
}
static JSValue fresh(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)self;
    (void)argc;
    (void)argv;
    JSValue v = JS_NewObjectClass(ctx, resource_class);
    if (JS_IsObject(v))
        ++made;
    return v;
}
static JSContext *create(JSRuntime *rt)
{
    JSClassDef definition = {0};
    definition.class_name = "VMLeafResource";
    definition.finalizer = finalize;
    JS_NewClassID(rt, &resource_class);
    assert(JS_NewClass(rt, resource_class, &definition) == 0);
    JSContext *ctx = JS_NewContext(rt);
    assert(ctx);
    JSValue global = JS_GetGlobalObject(ctx);
    assert(JS_SetPropertyStr(ctx, global, "vmLeafFresh",
                             JS_NewCFunction(ctx, fresh, "vmLeafFresh", 0)) > 0);
    JS_FreeValue(ctx, global);
    return ctx;
}
static void numeric(JSContext *ctx, JSValue value, int expected)
{
    int32_t n;
    assert(!JS_IsException(value) && JS_ToInt32(ctx, &n, value) == 0 && n == expected);
    JS_FreeValue(ctx, value);
}
static int interrupt(JSContext *ctx, void *opaque)
{
    (void)ctx;
    (void)opaque;
    return ++interrupts >= 3;
}
static size_t fault_case(size_t fault)
{
    made = finalized = 0;
    Allocator allocator = {0};
    JSRuntime *rt = JS_NewRuntime2(&functions, &allocator);
    assert(rt);
    JSContext *ctx = create(rt);
    JSValue fn = evaluate(ctx, "(function(a){return a})"),
            driver = evaluate(ctx, "(function(f){let x=f(vmLeafFresh());return {x}})");
    for (unsigned i = 0; i < 12; i++) {
        JSValue v = JS_Call(ctx, driver, JS_UNDEFINED, 1, &fn);
        assert(!JS_IsException(v));
        JS_FreeValue(ctx, v);
    }
    assert(made == finalized);
    AllocatorArenaDrain drain = {0};
    oom_drain_arenas(rt, &allocator, &drain);
    allocator.sequence = 0;
    allocator.fail_at = fault;
    JSValue v = JS_Call(ctx, driver, JS_UNDEFINED, 1, &fn);
    size_t attempts = allocator.sequence;
    allocator.fail_at = 0;
    if (JS_IsException(v)) {
        JSValue error = JS_GetException(ctx);
        JS_FreeValue(ctx, error);
        JS_ResetUncatchableError(ctx);
    } else
        JS_FreeValue(ctx, v);
    if (fault)
        assert(allocator.rejected == 1);
    assert(made == finalized);
    v = JS_Call(ctx, driver, JS_UNDEFINED, 1, &fn);
    assert(!JS_IsException(v));
    JS_FreeValue(ctx, v);
    JS_FreeValue(ctx, driver);
    JS_FreeValue(ctx, fn);
    oom_undrain_arenas(rt, &drain);
    JS_RunGC(rt);
    JS_FreeContext(ctx);
    JS_FreeRuntime(rt);
    assert(made == finalized && !allocator.live && !allocator.bytes);
    return attempts;
}
int main(int argc, char **argv)
{
    if (argc == 2 && !strcmp(argv[1], "oom")) {
        size_t attempts = fault_case(0);
        assert(attempts && attempts < 64);
        for (size_t f = 1; f <= attempts; f++)
            fault_case(f);
        printf("LINUX_VM_LEAVES_OOM_OK faults=%zu zero-ledgers\n", attempts);
        return 0;
    }
    Allocator allocator = {0};
    JSRuntime *rt = JS_NewRuntime2(&functions, &allocator);
    assert(rt);
    JSContext *ctx = create(rt);
    JS_SetMaxStackSize(rt, 1024 * 1024);
    JSValue constant = evaluate(ctx, "(function(a){return 3})"),
            identity = evaluate(ctx, "(function(a){return a})"),
            driver = evaluate(ctx, "(function(f){let x=f(vmLeafFresh());return x})");
    for (unsigned i = 0; i < 128; i++) {
        unsigned before = finalized;
        numeric(ctx, JS_Call(ctx, driver, JS_UNDEFINED, 1, &constant), 3);
        assert(finalized == before + 1 && made == finalized);
        before = finalized;
        JSValue value = JS_Call(ctx, driver, JS_UNDEFINED, 1, &identity);
        assert(JS_IsObject(value) && finalized == before && made == finalized + 1);
        JS_RunGC(rt);
        assert(finalized == before);
        JS_FreeValue(ctx, value);
        assert(finalized == before + 1 && made == finalized);
    }
    JSValue step = evaluate(ctx, "(function(a){return a+1})"),
            loop = evaluate(ctx, "(function(f,n){let x=0;while(n-->0)x=f(x);return x})");
    JSValue av[2] = {step, JS_NewInt32(ctx, 200000)};
    JS_SetInterruptHandler(rt, interrupt, NULL);
    JSValue value = JS_Call(ctx, loop, JS_UNDEFINED, 2, av);
    assert(JS_IsException(value) && interrupts >= 3);
    JSValue error = JS_GetException(ctx);
    JS_FreeValue(ctx, error);
    JS_ResetUncatchableError(ctx);
    JS_SetInterruptHandler(rt, NULL, NULL);
    av[1] = JS_NewInt32(ctx, 42);
    numeric(ctx, JS_Call(ctx, loop, JS_UNDEFINED, 2, av), 42);
    JS_FreeValue(ctx, loop);
    JS_FreeValue(ctx, step);
    JS_FreeValue(ctx, driver);
    JS_FreeValue(ctx, identity);
    JS_FreeValue(ctx, constant);
    JS_RunGC(rt);
    JS_FreeContext(ctx);
    JS_FreeRuntime(rt);
    assert(made == finalized && !allocator.live && !allocator.bytes);
    printf("LINUX_VM_LEAVES_API_OK resources=%u interrupts=%u zero-ledgers\n", made, interrupts);
    return 0;
}
