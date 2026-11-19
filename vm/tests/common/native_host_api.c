#include "src/common/internal/upstream-compat.h"
#ifdef NDEBUG
#undef NDEBUG
#endif
/* Native bridge protocol, compared with the retained bridge and original VM. */
#include "quickjs.h"
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <windows.h>
#define CHECK(x)                                                                                   \
    do {                                                                                           \
        if (!(x)) {                                                                                \
            fprintf(stderr, "HOST check %s:%d: %s\n", __FILE__, __LINE__, #x);                     \
            exit(1);                                                                               \
        }                                                                                          \
    } while (0)
typedef struct HostFrameSnapshot {
    void *prev;
    JSValue func;
    JSValue *args, *vars;
    void *refs;
    const uint8_t *pc;
    uint16_t ref_count, arg_count;
    bool strict, constructor;
    void *sp, *gc;
} HostFrameSnapshot;
_Static_assert(sizeof(HostFrameSnapshot) == 80, "unchanged original C frame");
static JSContext *realm;
static JSValue expected_func, expected_this, expected_arg, reentry_func;
static int wanted_argc, wanted_formal, wanted_magic, want_throw, want_reentry;
static unsigned calls, interrupt_calls, backtraces;
static uintptr_t word(JSRuntime *rt, size_t off)
{
    uintptr_t x;
    memcpy(&x, (char *)rt + off, sizeof(x));
    return x;
}
static int counter(JSContext *ctx)
{
    int x;
    memcpy(&x, (char *)ctx + 556, sizeof(x));
    return x;
}
static void set_counter(JSContext *ctx, int x)
{
    memcpy((char *)ctx + 556, &x, sizeof(x));
}
static JSValue evaluate(JSContext *ctx, const char *code)
{
    JSValue v = JS_Eval(ctx, code, strlen(code), "host-protocol.js", JS_EVAL_TYPE_GLOBAL);
    CHECK(!JS_IsException(v));
    return v;
}
static JSValue probe(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    CHECK(ctx == realm && argc == wanted_argc);
    CHECK(JS_VALUE_GET_TAG(self) == JS_VALUE_GET_TAG(expected_this));
    if (JS_IsObject(self))
        CHECK(JS_VALUE_GET_PTR(self) == JS_VALUE_GET_PTR(expected_this));
    HostFrameSnapshot sf;
    void *live = (void *)word(JS_GetRuntime(ctx), 1264);
    CHECK(live);
    memcpy(&sf, live, sizeof(sf));
    CHECK(sf.prev && !sf.strict && !sf.constructor);
    CHECK(JS_VALUE_GET_PTR(sf.func) == JS_VALUE_GET_PTR(expected_func));
    CHECK(sf.args == (JSValue *)argv &&
          sf.arg_count == (argc < wanted_formal ? wanted_formal : argc));
    for (int i = 0; i < argc; i++)
        CHECK(JS_VALUE_GET_PTR(argv[i]) == JS_VALUE_GET_PTR(expected_arg));
    for (int i = argc; i < wanted_formal; i++)
        CHECK(JS_IsUndefined(argv[i]));
    void *trace[64];
    USHORT frames = RtlCaptureStackBackTrace(0, 64, trace, NULL);
    CHECK(frames >= 4);
    backtraces++;
    JS_RunGC(JS_GetRuntime(ctx));
    if (want_reentry) {
        uintptr_t top = word(JS_GetRuntime(ctx), 1224), limit = word(JS_GetRuntime(ctx), 1232);
        JSValue n = JS_NewInt32(ctx, 8), v = JS_Call(ctx, reentry_func, JS_UNDEFINED, 1, &n);
        int32_t x;
        CHECK(!JS_IsException(v) && !JS_ToInt32(ctx, &x, v) && x == 42);
        JS_FreeValue(ctx, v);
        CHECK(word(JS_GetRuntime(ctx), 1264) == (uintptr_t)live);
        CHECK(word(JS_GetRuntime(ctx), 1224) == top && word(JS_GetRuntime(ctx), 1232) == limit);
    }
    calls++;
    if (want_throw)
        return JS_ThrowTypeError(ctx, "host sentinel");
    return argc ? JS_DupValue(ctx, argv[0]) : JS_UNDEFINED;
}
static JSValue magic_probe(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv,
                           int magic)
{
    CHECK(magic == wanted_magic);
    return probe(ctx, self, argc, argv);
}
static int interrupt(FrameInterruptSource *upgrade_interrupt_source, void *opaque)
{
    JSRuntime *rt = frame_interrupt_runtime(upgrade_interrupt_source);
    (void)rt;
    (void)opaque;
    interrupt_calls++;
    return 1;
}
static JSValue poison(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)self;
    (void)argc;
    (void)argv;
    set_counter(ctx, 1);
    return JS_UNDEFINED;
}
static JSValue shrink_stack(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)self;
    (void)argc;
    (void)argv;
    volatile unsigned char marker = 0;
    JSRuntime *rt = JS_GetRuntime(ctx);
    uintptr_t top = word(rt, 1224);
    CHECK(top > (uintptr_t)&marker);
    JS_SetMaxStackSize(rt, top - (uintptr_t)&marker + 1024);
    return JS_UNDEFINED;
}
static JSValue control(JSContext *ctx, JSValueConst self, int magic)
{
    (void)self;
    return JS_NewInt32(ctx, magic);
}
static JSValue wrapper(JSContext *ctx, int argc, int method)
{
    char code[8192];
    size_t at =
        (size_t)snprintf(code, sizeof(code), "(function hostCaller(a){'use strict';return %s(",
                         method ? "holder.h" : "hostProbe");
    for (int i = 0; i < argc; i++)
        at += (size_t)snprintf(code + at, sizeof(code) - at, "%sa", i ? "," : "");
    CHECK(at + 4 < sizeof(code));
    strcpy(code + at, ")})");
    return evaluate(ctx, code);
}
#ifdef FRAME_HOST_DISPATCH
extern void JS_FrameInterpHostDispatch(void), JS_FrameInterpHostDispatch_end(void);
static void unwind_dispatcher(void)
{
    unsigned char *start = (unsigned char *)(uintptr_t)JS_FrameInterpHostDispatch;
    size_t size = (unsigned char *)(uintptr_t)JS_FrameInterpHostDispatch_end - start;
    DWORD64 base = 0;
    PRUNTIME_FUNCTION fn = RtlLookupFunctionEntry((DWORD64)(uintptr_t)start, &base, NULL);
    CHECK(fn && base + fn->BeginAddress == (DWORD64)(uintptr_t)start &&
          fn->EndAddress - fn->BeginAddress == size);
    CHECK(!memcmp((void *)(uintptr_t)(base + fn->UnwindData), "\1\0\0\0", 4));
    for (size_t i = 0; i < size; i++) {
#ifdef _MSC_VER
        __declspec(align(16)) DWORD64 stack[8];
#else
        DWORD64 stack[8] __attribute__((aligned(16)));
#endif
        memset(stack, 0, sizeof(stack));
        stack[1] = 0x777788889999aaaaULL;
        CONTEXT c;
        memset(&c, 0, sizeof(c));
        c.ContextFlags = CONTEXT_FULL;
        c.Rip = (DWORD64)(uintptr_t)(start + i);
        c.Rsp = (DWORD64)(uintptr_t)&stack[1];
        c.Rbx = 1;
        c.Rbp = 2;
        c.Rsi = 3;
        c.Rdi = 4;
        c.R12 = 5;
        c.R13 = 6;
        c.R14 = 7;
        c.R15 = 8;
        PVOID handler = NULL;
        DWORD64 establisher = 0;
        RtlVirtualUnwind(UNW_FLAG_NHANDLER, base, c.Rip, fn, &c, &handler, &establisher, NULL);
        CHECK(c.Rip == stack[1] && c.Rsp == (DWORD64)(uintptr_t)&stack[2]);
        CHECK(c.Rbx == 1 && c.Rbp == 2 && c.Rsi == 3 && c.Rdi == 4 && c.R12 == 5 && c.R13 == 6 &&
              c.R14 == 7 && c.R15 == 8);
    }
    printf("HOST DISPATCH UNWIND PASS byte positions=%zu\n", size);
}
#endif
int main(void)
{
#ifdef FRAME_HOST_DISPATCH
    unwind_dispatcher();
#endif
    JSRuntime *rt = JS_NewRuntime();
    CHECK(rt);
    JS_SetMaxStackSize(rt, 4 * 1024 * 1024);
    JSContext *caller = JS_NewContext(rt);
    realm = JS_NewContext(rt);
    CHECK(caller && realm);
    JSValue global = JS_GetGlobalObject(caller);
    expected_arg = evaluate(caller, "(()=>{let a={value:42};a.self=a;return a})()");
    reentry_func = evaluate(realm, "(function inner(x){return x+34})");
    int lengths[] = {0, 1, 128, 255};
    int magics[] = {-32768, -123, 0, 32767};
    unsigned scenarios = 0;
    for (int signature = 0; signature < 2; signature++)
        for (unsigned l = 0; l < 4; l++)
            for (int arity = 0; arity < 4; arity++)
                for (int method = 0; method < 2; method++)
                    for (int reentry = 0; reentry < 2; reentry++) {
                        wanted_formal = lengths[l];
                        wanted_argc = arity == 0   ? 0
                                      : arity == 1 ? 1
                                      : arity == 2 ? wanted_formal
                                                   : wanted_formal + 1;
                        wanted_magic = magics[l];
                        want_reentry = reentry;
                        want_throw = 0;
                        expected_func = JS_NewCFunction2(
                            realm, (JSCFunction *)(signature ? (void *)magic_probe : (void *)probe),
                            "hostProbe", wanted_formal,
                            signature ? JS_CFUNC_generic_magic : JS_CFUNC_generic, wanted_magic);
                        CHECK(!JS_IsException(expected_func));
                        CHECK(JS_SetPropertyStr(caller, global, "hostProbe",
                                                JS_DupValue(caller, expected_func)) >= 0);
                        JSValue holder = JS_NewObject(caller);
                        CHECK(JS_SetPropertyStr(caller, holder, "h",
                                                JS_DupValue(caller, expected_func)) >= 0);
                        CHECK(JS_SetPropertyStr(caller, global, "holder",
                                                JS_DupValue(caller, holder)) >= 0);
                        expected_this = method ? holder : JS_UNDEFINED;
                        JSValue fn = wrapper(caller, wanted_argc, method);
                        uintptr_t before = word(rt, 1264), top = word(rt, 1224),
                                  limit = word(rt, 1232);
                        set_counter(caller, 1000000);
                        set_counter(realm, 1000000);
                        JSValue v = JS_Call(caller, fn, JS_UNDEFINED, 1, &expected_arg);
                        CHECK(!JS_IsException(v));
                        if (wanted_argc)
                            CHECK(JS_VALUE_GET_PTR(v) == JS_VALUE_GET_PTR(expected_arg));
                        else
                            CHECK(JS_IsUndefined(v));
                        CHECK(counter(caller) == 999998 &&
                              counter(realm) == (reentry ? 999999 : 1000000));
                        JS_FreeValue(caller, v);
                        CHECK(word(rt, 1264) == before && word(rt, 1224) == top &&
                              word(rt, 1232) == limit);
                        want_throw = 1;
                        v = JS_Call(caller, fn, JS_UNDEFINED, 1, &expected_arg);
                        CHECK(JS_IsException(v));
                        JSValue error = JS_GetException(caller),
                                stack = JS_GetPropertyStr(caller, error, "stack");
                        const char *text = JS_ToCString(caller, stack);
                        CHECK(text && strstr(text, "hostProbe") && strstr(text, "hostCaller"));
                        JS_FreeCString(caller, text);
                        JS_FreeValue(caller, stack);
                        JS_FreeValue(caller, error);
                        CHECK(word(rt, 1264) == before && word(rt, 1224) == top &&
                              word(rt, 1232) == limit);
                        JS_FreeValue(caller, fn);
                        JS_FreeValue(caller, holder);
                        JS_FreeValue(caller, expected_func);
                        scenarios++;
                    }
    want_reentry = want_throw = 0;
    wanted_argc = wanted_formal = 0;
    expected_this = JS_UNDEFINED;
    expected_func = JS_NewCFunction(realm, probe, "hostProbe", 0);
    CHECK(JS_SetPropertyStr(caller, global, "hostProbe", JS_DupValue(caller, expected_func)) >= 0);
    CHECK(JS_SetPropertyStr(caller, global, "poison",
                            JS_NewCFunction(caller, poison, "poison", 0)) >= 0);
    JSValue fn = evaluate(caller, "(function abortCaller(){poison();return hostProbe()})");
    unsigned before_calls = calls;
    JS_SetInterruptHandler(rt, interrupt, NULL);
    JSValue v = JS_Call(caller, fn, JS_UNDEFINED, 0, NULL);
    CHECK(JS_IsException(v) && calls == before_calls && interrupt_calls == 1);
    JSValue error = JS_GetException(caller);
    JS_FreeValue(caller, error);
    JS_SetInterruptHandler(rt, NULL, NULL);
    set_counter(caller, 1000000);
    JS_FreeValue(caller, fn);
    JS_FreeValue(caller, expected_func);
    /* Shrink from a host callback, then reject 255 readable native arguments
     * before invoking the target or touching its missing-argument window. */
    wanted_formal = 255;
    expected_func = JS_NewCFunction(realm, probe, "hostProbe", 255);
    CHECK(JS_SetPropertyStr(caller, global, "hostProbe", JS_DupValue(caller, expected_func)) >= 0);
    CHECK(JS_SetPropertyStr(caller, global, "shrinkStack",
                            JS_NewCFunction(caller, shrink_stack, "shrinkStack", 0)) >= 0);
    fn = evaluate(caller, "(function stackCaller(){shrinkStack();return hostProbe()})");
    before_calls = calls;
    uintptr_t saved_frame = word(rt, 1264), saved_top = word(rt, 1224);
    v = JS_Call(caller, fn, JS_UNDEFINED, 0, NULL);
    CHECK(JS_IsException(v) && calls == before_calls);
    CHECK(word(rt, 1264) == saved_frame && word(rt, 1224) == saved_top);
    JS_SetMaxStackSize(rt, 4 * 1024 * 1024);
    error = JS_GetException(caller);
    const char *message = JS_ToCString(caller, error);
    CHECK(message && strstr(message, "Maximum call stack size exceeded"));
    JS_FreeCString(caller, message);
    JS_FreeValue(caller, error);
    JS_FreeValue(caller, fn);
    JS_FreeValue(caller, expected_func);
    /* A non-generic getter signature keeps its existing dispatch semantics. */
    JSValue getter = JS_NewCFunction2(caller, (JSCFunction *)control, "sigControl", 0,
                                      JS_CFUNC_getter_magic, -19);
    CHECK(JS_SetPropertyStr(caller, global, "sigControl", getter) >= 0);
    fn = evaluate(caller, "(function(){return sigControl()})");
    v = JS_Call(caller, fn, JS_UNDEFINED, 0, NULL);
    int32_t n;
    CHECK(!JS_IsException(v) && !JS_ToInt32(caller, &n, v) && n == -19);
    JS_FreeValue(caller, v);
    JS_FreeValue(caller, fn);
    JS_FreeValue(caller, global);
    JS_FreeValue(caller, expected_arg);
    JS_FreeValue(realm, reentry_func);
    JS_RunGC(rt);
    JS_FreeContext(caller);
    JS_FreeContext(realm);
    JS_FreeRuntime(rt);
    printf("HOST PROTOCOL PASS scenarios=%u callbacks=%u backtraces=%u interrupts=%u\n", scenarios,
           calls, backtraces, interrupt_calls);
    return 0;
}
