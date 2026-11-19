#ifdef NDEBUG
#undef NDEBUG
#endif
#include "quickjs.h"
#include <assert.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <windows.h>

_Static_assert(sizeof(JSValue) == 16 && JS_TAG_OBJECT == -1 && JS_TAG_SYMBOL == -8 &&
                   JS_TAG_BOOL == 1,
               "strict identity leaf value/tag ABI");
extern int JS_FrameStrictIdentitySlow(JSContext *, JSValue *, bool);
extern void JS_FrameStrictIdentitySlow_end(void);
static JSClassID finalizer_class;
static unsigned finalizer_count, finalizer_order[16];

static void finalize(JSRuntime *rt, JSValue value)
{
    (void)rt;
    assert(finalizer_count < 16);
    finalizer_order[finalizer_count++] = (unsigned)(uintptr_t)JS_GetOpaque(value, finalizer_class);
}
static JSValue object(JSContext *ctx, unsigned id)
{
    JSValue value = JS_NewObjectClass(ctx, finalizer_class);
    assert(!JS_IsException(value));
    JS_SetOpaque(value, (void *)(uintptr_t)id);
    return value;
}
static JSValue evaluate(JSContext *ctx, const char *text)
{
    JSValue value = JS_Eval(ctx, text, strlen(text), "strict-identity.js", JS_EVAL_TYPE_GLOBAL);
    assert(!JS_IsException(value));
    return value;
}
static JSValue floating(double d)
{
    JSValue value;
    value.tag = JS_TAG_FLOAT64;
    value.u.float64 = d;
    return value;
}
/* The helper consumes both slots, replaces slot0, and leaves popping to its
 * interpreter caller. Never release the stale, already-consumed slot1. */
static void consume(JSContext *ctx, JSValue left, JSValue right, bool invert, bool expected)
{
    JSValue values[] = {left, right};
    assert(JS_FrameStrictIdentitySlow(ctx, values + 2, invert) == 0);
    assert(JS_IsBool(values[0]) && JS_ToBool(ctx, values[0]) == (expected ^ invert));
    JS_FreeValue(ctx, values[0]);
}
static void unwind_leaf(void)
{
    DWORD64 base = 0;
    uintptr_t start = (uintptr_t)JS_FrameStrictIdentitySlow;
    size_t size = (uintptr_t)JS_FrameStrictIdentitySlow_end - start;
    PRUNTIME_FUNCTION function = RtlLookupFunctionEntry((DWORD64)start, &base, NULL);
    assert(function && base + function->BeginAddress == start &&
           function->EndAddress - function->BeginAddress == size);
    const unsigned char *info = (const unsigned char *)(uintptr_t)(base + function->UnwindData);
    assert(info[0] == 1 && info[1] == 0 && info[2] == 0 && info[3] == 0);
    /* This C leaf has no stack-changing prologue or saved registers. Check
     * its entry row; do not treat arbitrary mid-instruction bytes as IPs. */
    {
        DWORD64 stack[8] = {0x12345678};
        CONTEXT state;
        memset(&state, 0, sizeof(state));
        state.ContextFlags = CONTEXT_FULL;
        state.Rip = start;
        state.Rsp = (DWORD64)(uintptr_t)stack;
        state.Rbx = 0x1111;
        state.Rbp = 0x2222;
        state.Rsi = 0x5555;
        state.Rdi = 0x6666;
        state.R12 = 0x3333;
        state.R13 = 0x7777;
        state.R14 = 0x8888;
        state.R15 = 0x4444;
        PVOID handler = NULL;
        DWORD64 establisher = 0;
        RtlVirtualUnwind(UNW_FLAG_NHANDLER, base, state.Rip, function, &state, &handler,
                         &establisher, NULL);
        assert(state.Rip == stack[0] && state.Rsp == (DWORD64)(uintptr_t)(stack + 1));
        assert(state.Rbx == 0x1111 && state.Rbp == 0x2222 && state.R12 == 0x3333 &&
               state.R15 == 0x4444);
        assert(state.Rsi == 0x5555 && state.Rdi == 0x6666 && state.R13 == 0x7777 &&
               state.R14 == 0x8888);
    }
}
int main(void)
{
    unwind_leaf();
    JSRuntime *rt = JS_NewRuntime();
    assert(rt);
    JSContext *ctx = JS_NewContext(rt);
    assert(ctx);
    JSValue symbol = evaluate(ctx, "Symbol('same')"), plain = JS_NewObject(ctx);
    JSValue values[] = {JS_UNDEFINED,
                        JS_NULL,
                        JS_FALSE,
                        JS_TRUE,
                        JS_NewInt32(ctx, -1),
                        JS_NewInt32(ctx, 0),
                        JS_NewInt32(ctx, 1),
                        floating(-0.0),
                        floating(NAN),
                        floating(INFINITY),
                        floating(1.0),
                        floating(1.5),
                        JS_NewBigInt64(ctx, 0),
                        JS_NewBigInt64(ctx, 1),
                        evaluate(ctx, "2n**90n"),
                        JS_NewString(ctx, "same"),
                        JS_NewString(ctx, "same"),
                        JS_NewString(ctx, "different"),
                        evaluate(ctx, "'a'.repeat(32)+'b'.repeat(32)"),
                        JS_DupValue(ctx, symbol),
                        JS_DupValue(ctx, symbol),
                        evaluate(ctx, "Symbol('same')"),
                        JS_DupValue(ctx, plain),
                        JS_DupValue(ctx, plain),
                        JS_NewObject(ctx)};
    unsigned count = sizeof(values) / sizeof(values[0]), calls = 0;
    for (unsigned round = 0; round < 3; round++)
        for (unsigned i = 0; i < count; i++)
            for (unsigned j = 0; j < count; j++) {
                bool expected = JS_IsStrictEqual(ctx, values[i], values[j]);
                for (int invert = 0; invert < 2; invert++) {
                    consume(ctx, JS_DupValue(ctx, values[i]), JS_DupValue(ctx, values[j]),
                            invert != 0, expected);
                    calls++;
                }
                if ((calls & 127) == 0)
                    JS_RunGC(rt);
            }
    JS_NewClassID(rt, &finalizer_class);
    JSClassDef definition = {0};
    definition.class_name = "StrictIdentityFinalizer";
    definition.finalizer = finalize;
    assert(JS_NewClass(rt, finalizer_class, &definition) == 0);
    consume(ctx, object(ctx, 1), object(ctx, 2), false, false);
    assert(finalizer_count == 2 && finalizer_order[0] == 1 && finalizer_order[1] == 2);
    JSValue same = object(ctx, 3);
    consume(ctx, same, JS_DupValue(ctx, same), true, true);
    assert(finalizer_count == 3 && finalizer_order[2] == 3);
    JSValue anchored = object(ctx, 4);
    consume(ctx, JS_DupValue(ctx, anchored), JS_DupValue(ctx, anchored), false, true);
    assert(finalizer_count == 3);
    JS_FreeValue(ctx, anchored);
    assert(finalizer_count == 4);
    JSValue cycle = object(ctx, 5);
    assert(JS_SetPropertyStr(ctx, cycle, "self", JS_DupValue(ctx, cycle)) > 0);
    consume(ctx, cycle, JS_DupValue(ctx, cycle), false, true);
    assert(finalizer_count == 4);
    JS_RunGC(rt);
    assert(finalizer_count == 5 && finalizer_order[4] == 5);
    for (unsigned i = 0; i < count; i++)
        JS_FreeValue(ctx, values[i]);
    JS_FreeValue(ctx, symbol);
    JS_FreeValue(ctx, plain);
    JS_RunGC(rt);
    JS_FreeContext(ctx);
    JS_FreeRuntime(rt);
    printf("STRICT IDENTITY PASS differential=%u finalizers=%u\n", calls, finalizer_count);
    return 0;
}
