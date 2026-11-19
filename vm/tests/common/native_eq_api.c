#ifdef NDEBUG
#undef NDEBUG
#endif
/* Differential semantics and chained unwind for native immediate equality. */
#include "quickjs.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <windows.h>
#include "tests/common/native_vm_unwind.h"
extern int JS_FrameInterp(void *);
extern void JS_FrameInterpPrimitiveEq(void);
extern void JS_FrameInterpPrimitiveEq_end(void);
static JSValue evaluate(JSContext *ctx, const char *text)
{
    JSValue v = JS_Eval(ctx, text, strlen(text), "primitive-eq.js", JS_EVAL_TYPE_GLOBAL);
    assert(!JS_IsException(v));
    return v;
}
static JSValue double_value(double d)
{
    JSValue v;
    v.tag = JS_TAG_FLOAT64;
    v.u.float64 = d;
    return v;
}
static void unwind_all(const char *path)
{
    DWORD64 base = 0, root_base = 0;
    unsigned char *start = (unsigned char *)(uintptr_t)JS_FrameInterpPrimitiveEq;
    size_t size = (unsigned char *)(uintptr_t)JS_FrameInterpPrimitiveEq_end - start;
    PRUNTIME_FUNCTION function = RtlLookupFunctionEntry((DWORD64)(uintptr_t)start, &base, NULL);
    PRUNTIME_FUNCTION root = qjs_frame_test_raw_vm(&root_base);
    assert(function && root && base == root_base && function != root);
    assert(base + function->BeginAddress == (DWORD64)(uintptr_t)start &&
           function->EndAddress - function->BeginAddress == size);
    unsigned char *info = (unsigned char *)(uintptr_t)(base + function->UnwindData);
    assert(info[0] == 0x21 && !info[1] && !info[2] && !info[3]);
    assert(!memcmp(info + 4, root, sizeof(*root)));
    FILE *stream = fopen(path, "r");
    assert(stream);
    unsigned offset, count = 0;
    while (fscanf(stream, "%u", &offset) == 1) {
        assert(offset < size);
#ifdef _MSC_VER
        __declspec(align(16)) DWORD64 stack[80];
#else
        DWORD64 stack[80] __attribute__((aligned(16)));
#endif
        memset(stack, 0, sizeof(stack));
        const unsigned registers[8] = {15, 14, 13, 12, 7, 6, 5, 3};
        for (unsigned j = 0; j < 8; j++)
            stack[9 + j] = 0x11110000u + registers[j];
        stack[17] = 0x77778888;
        CONTEXT context;
        memset(&context, 0, sizeof(context));
        context.ContextFlags = CONTEXT_FULL;
        context.Rip = (DWORD64)(uintptr_t)(start + offset);
        context.Rsp = (DWORD64)(uintptr_t)stack;
        PVOID handler = NULL;
        DWORD64 establisher = 0;
        RtlVirtualUnwind(UNW_FLAG_NHANDLER, base, context.Rip, function, &context, &handler,
                         &establisher, NULL);
        assert(context.Rip == 0x77778888 && context.Rsp == (DWORD64)(uintptr_t)&stack[18]);
        assert(context.Rbx == 0x11110003 && context.Rbp == 0x11110005 &&
               context.Rsi == 0x11110006 && context.Rdi == 0x11110007);
        assert(context.R12 == 0x1111000c && context.R13 == 0x1111000d &&
               context.R14 == 0x1111000e && context.R15 == 0x1111000f);
        count++;
    }
    fclose(stream);
    assert(count > 20);
    printf("PRIMITIVE EQ unwind instruction boundaries=%u\n", count);
}
int main(int argc, char **argv)
{
    assert(argc == 2);
    unwind_all(argv[1]);
    JSRuntime *rt = JS_NewRuntime();
    assert(rt);
    JSContext *ctx = JS_NewContext(rt);
    assert(ctx);
    JSValue eq = evaluate(ctx, "(function(a,b){return a===b})");
    JSValue ne = evaluate(ctx, "(function(a,b){return a!==b})");
    JSValue object = JS_NewObject(ctx), symbol = evaluate(ctx, "Symbol('a')");
    JSValue values[] = {JS_UNDEFINED,
                        JS_NULL,
                        JS_TRUE,
                        JS_FALSE,
                        JS_NewInt32(ctx, -1),
                        JS_NewInt32(ctx, 0),
                        JS_NewInt32(ctx, 1),
                        double_value(0.0),
                        double_value(-0.0),
                        double_value(NAN),
                        double_value(INFINITY),
                        double_value(1.5),
                        double_value(1.0),
                        JS_NewBigInt64(ctx, 0),
                        JS_NewBigInt64(ctx, 1),
                        JS_NewBigInt64(ctx, -1),
                        evaluate(ctx, "2n**90n"),
                        JS_NewString(ctx, "same"),
                        JS_NewString(ctx, "same"),
                        JS_NewString(ctx, "different"),
                        JS_DupValue(ctx, object),
                        JS_DupValue(ctx, object),
                        JS_NewObject(ctx),
                        JS_DupValue(ctx, symbol),
                        JS_DupValue(ctx, symbol),
                        evaluate(ctx, "Symbol('a')"),
                        JS_MKVAL(JS_TAG_UNDEFINED, 123),
                        JS_MKVAL(JS_TAG_NULL, 456)};
    unsigned calls = 0;
    for (unsigned round = 0; round < 3; round++)
        for (unsigned i = 0; i < sizeof(values) / sizeof(values[0]); i++)
            for (unsigned j = 0; j < sizeof(values) / sizeof(values[0]); j++) {
                bool expected = JS_IsStrictEqual(ctx, values[i], values[j]);
                JSValueConst args[] = {values[i], values[j]};
                for (int invert = 0; invert < 2; invert++) {
                    JSValue result = JS_Call(ctx, invert ? ne : eq, JS_UNDEFINED, 2, args);
                    assert(!JS_IsException(result) && JS_IsBool(result));
                    assert(JS_ToBool(ctx, result) == (expected ^ invert));
                    JS_FreeValue(ctx, result);
                    calls++;
                }
                if ((calls & 127) == 0)
                    JS_RunGC(rt);
            }
    for (unsigned i = 0; i < sizeof(values) / sizeof(values[0]); i++)
        JS_FreeValue(ctx, values[i]);
    JS_FreeValue(ctx, object);
    JS_FreeValue(ctx, symbol);
    JS_FreeValue(ctx, eq);
    JS_FreeValue(ctx, ne);
    JS_RunGC(rt);
    JS_FreeContext(ctx);
    JS_FreeRuntime(rt);
    printf("PRIMITIVE EQ semantics PASS calls=%u\n", calls);
    return 0;
}
