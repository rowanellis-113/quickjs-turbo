/* Public numeric ownership/OOM fixture and independent actual-C oracles. */
#ifdef NDEBUG
#undef NDEBUG
#endif
#include "quickjs.h"
#include <assert.h>
#include <fenv.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "../native_oom_allocator.h"
#ifdef QJS_TEST_NUMERIC_DIRECT
#include "dtoa.h"
extern void JS_FrameBigIntRelease(JSContext *, JSValue);
extern unsigned JS_FrameBigIntReleaseState(void);
extern double JS_FrameAtod(const char *, const char **, int, int, JSATODTempMem *);
#endif

static JSValue evaluate(JSContext *ctx, const char *text)
{
    JSValue value = JS_Eval(ctx, text, strlen(text), "linux-numeric.js", JS_EVAL_TYPE_GLOBAL);
    if (JS_IsException(value)) {
        JSValue error = JS_GetException(ctx);
        const char *message = JS_ToCString(ctx, error);
        fprintf(stderr, "%s\n", message ? message : "numeric exception");
        JS_FreeCString(ctx, message);
        JS_FreeValue(ctx, error);
        abort();
    }
    return value;
}
static JSValue gc(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)self;
    (void)argc;
    (void)argv;
    JS_RunGC(JS_GetRuntime(ctx));
    return JS_UNDEFINED;
}
static JSValue setup(JSContext *ctx)
{
    JSValue global = JS_GetGlobalObject(ctx);
    assert(JS_SetPropertyStr(ctx, global, "gcNative", JS_NewCFunction(ctx, gc, "gcNative", 0)) > 0);
    JS_FreeValue(ctx, global);
    return evaluate(ctx,
                    "(function(n){let a=18446744073709551616n,b=3n;"
                    "for(let i=0;i<n;i++){a+=b;b=(b+1n)*3n;gcNative();}"
                    "if(typeof a!=='bigint'||typeof b!=='bigint')throw Error('numeric ownership');"
                    "return a+b;})");
}
static JSValue invoke(JSContext *ctx, JSValue fn)
{
    JSValue count = JS_NewInt32(ctx, 5);
    return JS_Call(ctx, fn, JS_UNDEFINED, 1, &count);
}
static void exception(JSContext *ctx, JSValue value)
{
    if (JS_IsException(value)) {
        JSValue error = JS_GetException(ctx);
        JS_FreeValue(ctx, error);
    } else {
        JS_FreeValue(ctx, value);
    }
}
static unsigned sample(unsigned fail, size_t *requests)
{
    Allocator ledger = {0};
    JSRuntime *rt = JS_NewRuntime2(&functions, &ledger);
    assert(rt);
    JS_SetMaxStackSize(rt, 2 * 1024 * 1024);
    JSContext *ctx = JS_NewContext(rt);
    assert(ctx);
    JSValue fn = setup(ctx);
    for (int warm = 0; warm < 3; ++warm) {
        JSValue result = invoke(ctx, fn);
        assert(!JS_IsException(result));
        JS_FreeValue(ctx, result);
    }
    JS_RunGC(rt);
    ledger.sequence = 0;
    ledger.fail_at = fail;
    JSValue result = invoke(ctx, fn);
    if (requests)
        *requests = ledger.sequence;
    unsigned rejected = ledger.rejected;
    ledger.fail_at = 0;
    exception(ctx, result);
    result = invoke(ctx, fn);
    assert(!JS_IsException(result));
    JS_FreeValue(ctx, result);
    JS_FreeValue(ctx, fn);
    JS_RunGC(rt);
    JS_FreeContext(ctx);
    JS_FreeRuntime(rt);
    assert(!ledger.live && !ledger.bytes);
    return rejected;
}
#ifdef QJS_TEST_NUMERIC_DIRECT
static void atod_one(const char *text, int radix, int flags)
{
    JSATODTempMem left_mem, right_mem;
    const char *left_next = NULL, *right_next = NULL;
    double left = JS_FrameAtod(text, &left_next, radix, flags, &left_mem);
    double right = js_atod(text, &right_next, radix, flags, &right_mem);
    uint64_t left_bits, right_bits;
    memcpy(&left_bits, &left, 8);
    memcpy(&right_bits, &right, 8);
    assert((isnan(left) && isnan(right)) || left_bits == right_bits);
    assert(left_next == right_next);
    left = JS_FrameAtod(text, NULL, radix, flags, &left_mem);
    memcpy(&left_bits, &left, 8);
    assert((isnan(left) && isnan(right)) || left_bits == right_bits);
}
static void direct(void)
{
    static const char *inputs[] = {"",
                                   "+",
                                   "-",
                                   ".",
                                   "0",
                                   "-0",
                                   "+0",
                                   "00",
                                   "0.",
                                   ".5",
                                   "-.5",
                                   "0.125",
                                   "-1234567.125",
                                   "999999999999999",
                                   "9999999999999999",
                                   "0.000000000000001",
                                   "1.0000000000000001",
                                   "1e20",
                                   "1e-300",
                                   "0x80",
                                   "Infinity",
                                   "-Infinity",
                                   "NaN",
                                   " 12",
                                   "12x",
                                   "12.34x"};
    int original_round = fegetround();
    static const int rounds[] = {FE_TONEAREST, FE_UPWARD, FE_DOWNWARD, FE_TOWARDZERO};
    uint32_t seed = 0x4f102431;
    for (unsigned r = 0; r < sizeof(rounds) / sizeof(rounds[0]); ++r) {
        assert(fesetround(rounds[r]) == 0);
        for (unsigned i = 0; i < sizeof(inputs) / sizeof(inputs[0]); ++i)
            for (unsigned flags = 0; flags < 2; ++flags)
                for (unsigned radix = 0; radix < 3; ++radix)
                    atod_one(inputs[i],
                             radix == 0   ? 0
                             : radix == 1 ? 10
                                          : 16,
                             flags ? JS_ATOD_INT_ONLY : 0);
        for (unsigned i = 0; i < 2048; ++i) {
            char text[80];
            seed = seed * 1664525U + 1013904223U;
            unsigned whole = seed % 1000000000U;
            seed = seed * 1664525U + 1013904223U;
            unsigned fraction = seed % 1000000U;
            snprintf(text, sizeof(text), "%s%u.%06u", i & 1 ? "-" : "", whole, fraction);
            atod_one(text, 10, 0);
        }
    }
    assert(fesetround(original_round) == 0);
    Allocator ledger = {0};
    JSRuntime *rt = JS_NewRuntime2(&functions, &ledger);
    assert(rt);
    JSContext *ctx = JS_NewContext(rt);
    assert(ctx);
    JSValue value = evaluate(ctx, "18446744073709551616000000000000000000n");
    JSValue alias = JS_DupValue(ctx, value);
    JS_FrameBigIntRelease(ctx, alias);
    assert(JS_FrameBigIntReleaseState() == (getenv("QJS_DISABLE_BIGINT_RELEASE") ? 2U : 1U));
    const char *text = JS_ToCString(ctx, value);
    assert(text && !strcmp(text, "18446744073709551616000000000000000000"));
    JS_FreeCString(ctx, text);
    JS_FrameBigIntRelease(ctx, value);
    JS_FrameBigIntRelease(ctx, JS_NewInt32(ctx, 3));
    JS_FrameBigIntRelease(ctx, JS_NewString(ctx, "general fallback"));
    JS_FrameBigIntRelease(ctx, evaluate(ctx, "42n"));
    JS_FreeContext(ctx);
    JS_FreeRuntime(rt);
    assert(!ledger.live && !ledger.bytes);
    puts("LINUX_NUMERIC_DIRECT_OK");
}
#endif
int main(int argc, char **argv)
{
    size_t requests = 0;
    assert(sample(0, &requests) == 0 && requests > 0 && requests < 256);
    if (argc == 2 && !strcmp(argv[1], "oom")) {
        unsigned failures = 0;
        for (unsigned fault = 1; fault <= requests + 2; ++fault)
            failures += sample(fault, NULL);
        assert(failures == requests);
        printf("LINUX_NUMERIC_OOM_OK failures=%u\n", failures);
        return 0;
    }
    assert(argc == 1);
#ifdef QJS_TEST_NUMERIC_DIRECT
    direct();
#endif
    puts("LINUX_NUMERIC_PUBLIC_OK");
    return 0;
}
