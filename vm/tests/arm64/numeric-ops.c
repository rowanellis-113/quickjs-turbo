#ifdef NDEBUG
#undef NDEBUG
#endif
#include "quickjs.h"
#ifdef QJS_AARCH64_VM_INSTRUMENT
#include "src/arm64/linux/interpreter-observe.h"
#endif
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static uint64_t digest = UINT64_C(1469598103934665603);
static uint64_t semantic = UINT64_C(1469598103934665603);
static int trace;
static void mix(uint64_t *hash, uint64_t n)
{
    for (unsigned i = 0; i < 8; i++) {
        *hash ^= (unsigned char)n;
        *hash *= UINT64_C(1099511628211);
        n >>= 8;
    }
}
static void record(JSValue v, unsigned op, unsigned a, unsigned b)
{
    int tag = JS_VALUE_GET_TAG(v);
    uint64_t bits;
    assert(tag == JS_TAG_INT || tag == JS_TAG_BOOL || tag == JS_TAG_FLOAT64);
    mix(&digest, (uint64_t)tag);
    if (tag == JS_TAG_FLOAT64) {
        double d = JS_VALUE_GET_FLOAT64(v);
        memcpy(&bits, &d, 8);
        // JS does not specify NaN payload/sign selection. Keep every other
        // bit (including negative zero), and retain the actual numeric tag.
        if ((bits & UINT64_C(0x7fffffffffffffff)) > UINT64_C(0x7ff0000000000000))
            bits = UINT64_C(0x7ff8000000000000);
    } else
        bits = (uint32_t)JS_VALUE_GET_INT(v);
    mix(&digest, bits);
    if (trace)
        printf("NUMERIC_CASE op=%u a=%u b=%u tag=%d bits=%016llx\n", op, a, b, tag,
               (unsigned long long)bits);
    // JS numbers may have either int32 or double representation. The accepted
    // mixed-number C fast path already differs from the legacy slow path here.
    // Native and C-frame modes must still match tags and bits exactly; legacy
    // must match the JS value, including boolean type and the sign of zero.
    if (tag == JS_TAG_INT) {
        double d = JS_VALUE_GET_INT(v);
        memcpy(&bits, &d, 8);
        tag = JS_TAG_FLOAT64;
    }
    mix(&semantic, (uint64_t)tag);
    mix(&semantic, bits);
}
static JSValue check(JSContext *ctx, JSValue v)
{
    if (JS_IsException(v)) {
        JSValue e = JS_GetException(ctx);
        const char *s = JS_ToCString(ctx, e);
        fprintf(stderr, "numeric: %s\n", s ? s : "<exception>");
        abort();
    }
    return v;
}
int main(int argc, char **argv)
{
    assert(argc == 2 || (argc == 3 && !strcmp(argv[2], "trace")));
    trace = argc == 3;
#ifdef QJS_AARCH64_VM_INSTRUMENT
    int vm = strcmp(argv[1], "register-off") && strcmp(argv[1], "legacy");
    int branch_off = !strcmp(argv[1], "truth-off") || !strcmp(argv[1], "truth-zero") ||
                     !strcmp(argv[1], "number-off") || !strcmp(argv[1], "number-zero");
#endif
    JSRuntime *rt = JS_NewRuntime();
    assert(rt);
    JS_SetMaxStackSize(rt, 4 * 1024 * 1024);
    JSContext *ctx = JS_NewContext(rt);
    assert(ctx);
    const char *ops[] = {"+", "-", "*", "/", "<", "<=", ">", ">=", "==", "!=", "===", "!=="};
    JSValue functions[12], values[80];
    unsigned count = 0, cases = 0;
    for (unsigned k = 0; k < 12; k++) {
        char text[100];
        snprintf(text, sizeof(text), "(function(a,b){return a%s b;})", ops[k]);
        functions[k] =
            check(ctx, JS_Eval(ctx, text, strlen(text), "<arm-number>", JS_EVAL_TYPE_GLOBAL));
    }
    const int32_t ints[] = {0,     1,      -1,    INT32_MIN, INT32_MAX,
                            46341, -46341, 65536, -65536,    1073741824};
    for (unsigned k = 0; k < sizeof(ints) / sizeof(ints[0]); k++)
        values[count++] = JS_NewInt32(ctx, ints[k]);
    const uint64_t raw[] = {0,
                            UINT64_C(0x8000000000000000),
                            UINT64_C(0x3ff0000000000000),
                            UINT64_C(0xbff0000000000000),
                            UINT64_C(0x3ff8000000000000),
                            UINT64_C(0xbff8000000000000),
                            1,
                            UINT64_C(0x8000000000000001),
                            UINT64_C(0x7fefffffffffffff),
                            UINT64_C(0xffefffffffffffff),
                            UINT64_C(0x7ff0000000000000),
                            UINT64_C(0xfff0000000000000),
                            UINT64_C(0x7ff8000000000000),
                            UINT64_C(0xfff8000000000001),
                            UINT64_C(0x7ff0000000000001),
                            UINT64_C(0x41dfffffffffffff),
                            UINT64_C(0x41e0000000000000),
                            UINT64_C(0xc1e0000000000000),
                            UINT64_C(0xc1e0000000200000)};
    for (unsigned k = 0; k < sizeof(raw) / sizeof(raw[0]); k++) {
        double d;
        memcpy(&d, &raw[k], 8);
        values[count++] = __JS_NewFloat64(d);
    }
    uint64_t seed = UINT64_C(0x62b7de41f7a12349);
    for (unsigned k = 0; k < 32; k++) {
        seed ^= seed << 13;
        seed ^= seed >> 7;
        seed ^= seed << 17;
        double d;
        memcpy(&d, &seed, 8);
        values[count++] = __JS_NewFloat64(d);
    }
    uint64_t numeric_steps = 0, branch_steps = 0;
#ifdef QJS_AARCH64_VM_INSTRUMENT
    QJSArmVMCounts before, after;
    qjs_aarch64_vm_counts(&before);
#endif
    for (unsigned k = 0; k < 12; k++)
        for (unsigned a = 0; a < count; a++)
            for (unsigned b = 0; b < count; b++) {
                JSValue args[] = {values[a], values[b]};
                JSValue result = check(ctx, JS_Call(ctx, functions[k], JS_UNDEFINED, 2, args));
                record(result, k, a, b);
                ++cases;
                JS_FreeValue(ctx, result);
            }
#ifdef QJS_AARCH64_VM_INSTRUMENT
    qjs_aarch64_vm_counts(&after);
    numeric_steps = after.c_steps - before.c_steps;
    if (vm)
        assert(numeric_steps == 0 && after.native_ops > before.native_ops);
    else
        assert(after.activations == 0);
#endif
    const char *truth = "(function(a){if(a)return 17;return -13;})";
    JSValue test =
        check(ctx, JS_Eval(ctx, truth, strlen(truth), "<arm-number-truth>", JS_EVAL_TYPE_GLOBAL));
#ifdef QJS_AARCH64_VM_INSTRUMENT
    qjs_aarch64_vm_counts(&before);
#endif
    for (unsigned k = 0; k < count; k++) {
        JSValue result = check(ctx, JS_Call(ctx, test, JS_UNDEFINED, 1, &values[k]));
        record(result, 12, k, 0);
        ++cases;
        JS_FreeValue(ctx, result);
    }
#ifdef QJS_AARCH64_VM_INSTRUMENT
    qjs_aarch64_vm_counts(&after);
    branch_steps = after.c_steps - before.c_steps;
    if (vm && branch_off)
        assert(branch_steps > 0);
    else if (vm)
        assert(branch_steps <= 1); // natural interrupt-reset boundary
#endif
    for (unsigned k = 0; k < count; k++)
        JS_FreeValue(ctx, values[k]);
    for (unsigned k = 0; k < 12; k++)
        JS_FreeValue(ctx, functions[k]);
    JS_FreeValue(ctx, test);
    JS_FreeContext(ctx);
    JS_FreeRuntime(rt);
    printf(
        "AARCH64_NUMERIC_OK mode=%s cases=%u digest=%016llx semantic=%016llx numeric_steps=%llu branch_steps=%llu observed=%d\n",
        argv[1], cases, (unsigned long long)digest, (unsigned long long)semantic,
        (unsigned long long)numeric_steps, (unsigned long long)branch_steps,
#ifdef QJS_AARCH64_VM_INSTRUMENT
        1
#else
        0
#endif
    );
    return 0;
}
