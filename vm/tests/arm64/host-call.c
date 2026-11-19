#ifdef NDEBUG
#undef NDEBUG
#endif
#include "quickjs.h"
#include "src/arm64/linux/interpreter-observe.h"
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <execinfo.h>

struct JSFrameRegisterState;
extern int JS_FrameInterp(struct JSFrameRegisterState *);
extern unsigned char qjs_aarch64_vm_end[];
static JSContext *foreign_ctx, *caller_ctx;
static JSValue nested;
static unsigned generic_calls, magic_calls, throws, collections, reentries, unwinds;
static int want_argc, expect_vm;

static void observe(JSContext *ctx)
{
    assert(ctx == foreign_ctx);
    uintptr_t sp;
    __asm__ volatile("mov %0, sp" : "=r"(sp));
    assert((sp & 15) == 0);
    void *frames[40];
    int n = backtrace(frames, 40), found = 0;
    uintptr_t first = (uintptr_t)JS_FrameInterp, last = (uintptr_t)qjs_aarch64_vm_end;
    for (int i = 0; i < n; i++)
        found |= (uintptr_t)frames[i] > first && (uintptr_t)frames[i] < last;
    assert(found == expect_vm);
    ++unwinds;
    JS_RunGC(JS_GetRuntime(ctx));
    ++collections;
    JSValue result = JS_Call(caller_ctx, nested, JS_UNDEFINED, 0, NULL);
    int32_t value;
    assert(!JS_IsException(result) && JS_ToInt32(caller_ctx, &value, result) == 0 && value == 41);
    JS_FreeValue(caller_ctx, result);
    ++reentries;
}
static JSValue generic(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)self;
    observe(ctx);
    ++generic_calls;
    assert(argc == want_argc && (argc == 0 || argc == 1));
    for (int i = argc; i < 3; i++)
        assert(JS_IsUndefined(argv[i]));
    return argc ? JS_DupValue(ctx, argv[0]) : JS_NewInt32(ctx, 47);
}
static JSValue magic(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv, int number)
{
    observe(ctx);
    ++magic_calls;
    assert(argc == want_argc && number == -327);
    assert(JS_VALUE_GET_PTR(self) == JS_VALUE_GET_PTR(argv[0]));
    for (int i = argc; i < 3; i++)
        assert(JS_IsUndefined(argv[i]));
    return JS_NewInt32(ctx, number + argc);
}
static JSValue throwing(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)self;
    (void)argv;
    observe(ctx);
    assert(argc == 1);
    ++throws;
    return JS_ThrowTypeError(ctx, "arm-host-marker");
}
static JSValue eval(JSContext *ctx, const char *source)
{
    JSValue value = JS_Eval(ctx, source, strlen(source), "<arm-host-call>", JS_EVAL_TYPE_GLOBAL);
    if (JS_IsException(value)) {
        JSValue error = JS_GetException(ctx);
        const char *text = JS_ToCString(ctx, error);
        fprintf(stderr, "%s\n", text ? text : "<exception>");
        abort();
    }
    return value;
}
int main(int argc, char **argv)
{
    assert(argc == 2);
    int direct = !strcmp(argv[1], "native");
    expect_vm = direct || !strcmp(argv[1], "host-off");
    JSRuntime *rt = JS_NewRuntime();
    assert(rt);
    JS_SetMaxStackSize(rt, 4 * 1024 * 1024);
    caller_ctx = JS_NewContext(rt);
    foreign_ctx = JS_NewContext(rt);
    assert(caller_ctx && foreign_ctx);
    nested = eval(caller_ctx, "(function(){return 41;})");
    JSValue global = JS_GetGlobalObject(caller_ctx);
    assert(JS_SetPropertyStr(caller_ctx, global, "generic",
                             JS_NewCFunction(foreign_ctx, generic, "generic", 3)) == 1);
    assert(JS_SetPropertyStr(caller_ctx, global, "throwing",
                             JS_NewCFunction(foreign_ctx, throwing, "throwing", 1)) == 1);
    JSValue object = JS_NewObject(caller_ctx);
    assert(JS_SetPropertyStr(caller_ctx, object, "magic",
                             JS_NewCFunctionMagic(foreign_ctx, magic, "magic", 3,
                                                  JS_CFUNC_generic_magic, -327)) == 1);
    JS_FreeValue(caller_ctx,
                 eval(caller_ctx,
                      "function g0(){return generic();}function g1(o){return generic(o);}"
                      "function m1(o){return o.magic(o);}function m4(o){return o.magic(o,1,2,3);}"
                      "function fail(o){return throwing(o);}"));
    const char *names[] = {"g0", "g1", "m1", "m4", "fail"};
    QJSArmVMCounts before, after;
    qjs_aarch64_vm_counts(&before);
    for (unsigned pass = 0; pass < 20; pass++)
        for (unsigned i = 0; i < 5; i++) {
            JSValue fn = JS_GetPropertyStr(caller_ctx, global, names[i]);
            want_argc = i == 0 ? 0 : i == 3 ? 4 : 1;
            JSValue result =
                JS_Call(caller_ctx, fn, JS_UNDEFINED, i == 0 ? 0 : 1, i == 0 ? NULL : &object);
            JS_FreeValue(caller_ctx, fn);
            if (i == 4) {
                assert(JS_IsException(result));
                JSValue error = JS_GetException(caller_ctx);
                const char *text = JS_ToCString(caller_ctx, error);
                assert(text && strstr(text, "arm-host-marker"));
                JS_FreeCString(caller_ctx, text);
                JS_FreeValue(caller_ctx, error);
            } else {
                assert(!JS_IsException(result));
                if (i == 1)
                    assert(JS_VALUE_GET_PTR(result) == JS_VALUE_GET_PTR(object));
                else {
                    int32_t n;
                    assert(JS_ToInt32(caller_ctx, &n, result) == 0 &&
                           n == (i == 0 ? 47 : -327 + want_argc));
                }
            }
            JS_FreeValue(caller_ctx, result);
        }
    qjs_aarch64_vm_counts(&after);
    if (direct)
        assert(after.direct_generic - before.direct_generic == 60 &&
               after.direct_magic - before.direct_magic == 40);
    else
        assert(after.direct_generic == 0 && after.direct_magic == 0);
    JS_FreeValue(caller_ctx, object);
    JS_FreeValue(caller_ctx, global);
    JS_FreeValue(caller_ctx, nested);
    JS_FreeContext(foreign_ctx);
    JS_FreeContext(caller_ctx);
    JS_RunGC(rt);
    JS_FreeRuntime(rt);
    assert(generic_calls == 40 && magic_calls == 40 && throws == 20 && collections == 100 &&
           reentries == 100 && unwinds == 100);
    printf(
        "AARCH64_HOST_CALL_OK mode=%s generic=%u magic=%u throws=%u collections=%u reentry=%u unwind=%u direct_generic=%llu direct_magic=%llu\n",
        argv[1], generic_calls, magic_calls, throws, collections, reentries, unwinds,
        (unsigned long long)after.direct_generic, (unsigned long long)after.direct_magic);
    return 0;
}
