#ifdef NDEBUG
#undef NDEBUG
#endif
/* Standard Win64 tail-entry ABI and asynchronous stack-unwind regression. */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <windows.h>
#include "quickjs.h"

extern JSValue JS_LegacyCall(JSContext *, JSValueConst, JSValueConst, int, JSValueConst *);
extern void qjs_frame_select_entry(void);
extern int JS_FrameResolveCall(JSContext *, const JSValue *);
typedef JSValue (*CallEntry)(JSContext *, JSValueConst, JSValueConst, int, JSValueConst *);
static uintptr_t probe_stack;
static JSValue expected_this, expected_result;

static JSValue probe(JSContext *ctx, JSValueConst this_value, int argc, JSValueConst *argv)
{
    volatile unsigned char marker = 0;
    probe_stack = (uintptr_t)&marker;
    assert(argc == 3);
    assert(JS_VALUE_GET_PTR(this_value) == JS_VALUE_GET_PTR(expected_this));
    int32_t n;
    double x;
    assert(JS_ToInt32(ctx, &n, argv[0]) == 0 && n == 73);
    assert(JS_ToFloat64(ctx, &x, argv[1]) == 0 && x == 1.25);
    assert(JS_VALUE_GET_PTR(argv[2]) == JS_VALUE_GET_PTR(expected_result));
    return JS_DupValue(ctx, argv[2]);
}

#ifdef _MSC_VER
__declspec(noinline)
#else
__attribute__((noipa))
#endif
static JSValue invoke(CallEntry entry, JSContext *ctx, JSValueConst fn, JSValueConst this_value,
                      int argc, JSValueConst *argv)
{
    /* Both targets use this exact call instruction and its argument buffers. */
    return entry(ctx, fn, this_value, argc, argv);
}

static void check_target(JSContext *ctx, JSValueConst fn, JSValue *args, int require_legacy_stack)
{
    JSValue v = invoke(JS_LegacyCall, ctx, fn, expected_this, 3, args);
    assert(!JS_IsException(v));
    uintptr_t legacy_stack = probe_stack;
    assert(JS_VALUE_GET_PTR(v) == JS_VALUE_GET_PTR(expected_result));
    JS_FreeValue(ctx, v);
    for (int i = 0; i < 2; i++) {
        v = invoke(JS_Call, ctx, fn, expected_this, 3, args);
        assert(!JS_IsException(v));
        assert(JS_VALUE_GET_PTR(v) == JS_VALUE_GET_PTR(expected_result));
        if (require_legacy_stack)
            assert(probe_stack == legacy_stack);
        JS_FreeValue(ctx, v);
    }
}

static void check_unwind(void)
{
    DWORD64 base = 0;
    PRUNTIME_FUNCTION fn =
        RtlLookupFunctionEntry((DWORD64)(uintptr_t)qjs_frame_select_entry, &base, NULL);
    assert(fn);
    const unsigned char *start = (const unsigned char *)(uintptr_t)(base + fn->BeginAddress);
    size_t length = fn->EndAddress - fn->BeginAddress;
#ifdef _MSC_VER
    __declspec(align(16)) ULONG64 stack[16] = {0};
#else
    ULONG64 stack[16] __attribute__((aligned(16))) = {0};
#endif
    stack[9] = (ULONG64)(uintptr_t)check_unwind;
    /* Prolog start, allocated body, and both tails before/after stack restore. */
    size_t offsets[6] = {0, 4};
    int count = 2;
    for (size_t i = 4; i + 10 <= length; i++) {
        if (!memcmp(start + i, "\x48\x83\xc4\x48\xff\x25", 6)) {
            assert(count + 2 <= 6);
            offsets[count++] = i;
            offsets[count++] = i + 4;
        }
    }
    assert(count == 6);
    for (int i = 0; i < count; i++) {
        CONTEXT c = {0};
        c.ContextFlags = CONTEXT_FULL;
        c.Rip = (DWORD64)(uintptr_t)(start + offsets[i]);
        int restored = offsets[i] == 0 || start[offsets[i]] == 0xff;
        c.Rsp = (DWORD64)(uintptr_t)(stack + (restored ? 9 : 0));
        void *data = NULL;
        DWORD64 establisher = 0;
        RtlVirtualUnwind(UNW_FLAG_NHANDLER, base, c.Rip, fn, &c, &data, &establisher, NULL);
        assert(c.Rip == stack[9]);
        assert(c.Rsp == (DWORD64)(uintptr_t)(stack + 10));
    }
}

int main(void)
{
    check_unwind();
    JSRuntime *rt = JS_NewRuntime();
    JSContext *ctx = JS_NewContext(rt);
    expected_this = JS_NewObject(ctx);
    expected_result = JS_NewObject(ctx);
    JSValue args[3] = {JS_NewInt32(ctx, 73), JS_NewFloat64(ctx, 1.25), expected_result};
    JSValue native = JS_NewCFunction(ctx, probe, "entryProbe", 3);
    /* First-ever public call and warm calls must both match the legacy stack. */
    assert(JS_FrameResolveCall(ctx, &native) == 0);
    check_target(ctx, native, args, 1);
    JSValue global = JS_GetGlobalObject(ctx);
    JS_SetPropertyStr(ctx, global, "entryProbe", JS_DupValue(ctx, native));
    /* Empty finally can now be admitted; eval remains a genuine fallback. */
    const char *source = "(function(a,b,c){eval('');return entryProbe.call(this,a,b,c);})";
    JSValue unsupported =
        JS_Eval(ctx, source, strlen(source), "tail-entry-abi", JS_EVAL_TYPE_GLOBAL);
    assert(!JS_IsException(unsupported));
    assert(JS_FrameResolveCall(ctx, &unsupported) == 0);
    check_target(ctx, unsupported, args, 1);
    JS_FreeValue(ctx, unsupported);
    const char *expanded = "(function(a,b,c){try{return entryProbe.call(this,a,b,c);}finally{}})";
    JSValue formerly_unsupported =
        JS_Eval(ctx, expanded, strlen(expanded), "expanded-entry-abi", JS_EVAL_TYPE_GLOBAL);
    assert(!JS_IsException(formerly_unsupported));
    int admitted = JS_FrameResolveCall(ctx, &formerly_unsupported);
    check_target(ctx, formerly_unsupported, args, !admitted);
    JS_FreeValue(ctx, formerly_unsupported);
    JS_FreeValue(ctx, native);
    JS_FreeValue(ctx, global);
    JS_FreeValue(ctx, expected_result);
    JS_FreeValue(ctx, expected_this);
    JS_FreeContext(ctx);
    JS_FreeRuntime(rt);
    puts("tail entry: ABI, first/warm legacy stack, and six unwind positions passed");
    return 0;
}
