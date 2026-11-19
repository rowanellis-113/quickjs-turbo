/* Public values and passive native path counters;no private-state writes. */
#ifdef NDEBUG
#undef NDEBUG
#endif
#include "quickjs.h"
#include "src/arm64/linux/interpreter-observe.h"
#include "interpreter-aarch64-values.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "tests/common/native_oom_allocator.h"
static JSContext *ctx;
static unsigned checks;
static JSValue eval(const char *source)
{
    JSValue v = JS_Eval(ctx, source, strlen(source), "arm-comparison-native", JS_EVAL_TYPE_GLOBAL);
    assert(!JS_IsException(v));
    return v;
}
static void compare(const char *op, unsigned opcode, JSValue a, JSValue b, int expected,
                    unsigned event, int enabled)
{
    char source[256];
    snprintf(source, sizeof(source),
             "(function(a,b,n){let hits=0;for(let i=0;i<n;i++){if(a%sb)hits++;}return hits})", op);
    JSValue f = eval(source), argv[] = {a, b, JS_NewInt32(ctx, 0)};
    JSValue r = JS_Call(ctx, f, JS_UNDEFINED, 3, argv);
    assert(!JS_IsException(r));
    JS_FreeValue(ctx, r);
    uint64_t before[16], after[16], old_ops[256], new_ops[256];
    qjs_aarch64_vm_comparison_counts(before);
    qjs_aarch64_vm_opcode_counts(old_ops);
    argv[2] = JS_NewInt32(ctx, 64);
    r = JS_Call(ctx, f, JS_UNDEFINED, 3, argv);
    if (JS_IsException(r)) {
        JSValue e = JS_GetException(ctx);
        const char *s = JS_ToCString(ctx, e);
        fprintf(stderr, "COMPARISON_EXCEPTION %s\n", s ? s : "unknown");
        abort();
    }
    int32_t n = -1;
    assert(!JS_ToInt32(ctx, &n, r) && n == 64 * expected);
    JS_FreeValue(ctx, r);
    qjs_aarch64_vm_comparison_counts(after);
    qjs_aarch64_vm_opcode_counts(new_ops);
    fprintf(stderr, "ARM_COMPARISON_PATH op=%s event=%u enabled=%d hits=%llu Csteps=%llu\n", op,
            event, enabled, (unsigned long long)(after[event] - before[event]),
            (unsigned long long)(new_ops[opcode] - old_ops[opcode]));
    assert(after[event] - before[event] == (enabled ? 64u : 0u));
    if (enabled)
        assert(new_ops[opcode] == old_ops[opcode]);
    JS_FreeValue(ctx, f);
    ++checks;
}
int main(void)
{
    Allocator memory = {0};
    JSRuntime *rt = JS_NewRuntime2(&functions, &memory);
    assert(rt);
    ctx = JS_NewContext(rt);
    assert(ctx);
    JS_SetMaxStackSize(rt, 4 * 1024 * 1024);
    int native = ARM_HAS_COMPARISONS && !getenv("QJS_DISABLE_REGISTER_INTERP") &&
                 !getenv("QJS_DISABLE_INTERP_FRAME");
    int group = native && !getenv("QJS_DISABLE_LINUX_COMPARISONS");
    int strict = group && !getenv("QJS_DISABLE_LINUX_STRICT_COMPARE");
    int loose = group && !getenv("QJS_DISABLE_LINUX_LOOSE_COMPARE") &&
                !getenv("QJS_DISABLE_FRAME_LOOSE_EQ");
    int reference = strict && !getenv("QJS_DISABLE_FRAME_REFERENCE_EQUALITY");
    int strings = strict && loose && !getenv("QJS_DISABLE_FRAME_LOOSE_EQ_STRINGS");
    int nulls = loose && !getenv("QJS_DISABLE_FRAME_LOOSE_EQ_NULL");
    int objects = nulls && !getenv("QJS_DISABLE_FRAME_LOOSE_EQ_OBJECT_NULL");
    JSValue object = JS_NewObject(ctx), different = JS_NewObject(ctx);
    JSValue symbol = eval("Symbol('kept')"), other = eval("Symbol('kept')");
    compare("===", ARM_OP_strict_eq, object, object, 1, 8, reference);
    compare("!==", ARM_OP_strict_neq, object, different, 1, 8, reference);
    compare("===", ARM_OP_strict_eq, symbol, symbol, 1, 8, reference);
    compare("!==", ARM_OP_strict_neq, symbol, other, 1, 8, reference);
    JSValue left = JS_NewString(ctx, "abcdefgh"), right = JS_NewString(ctx, "abcdefgh"),
            shorter = JS_NewString(ctx, "abc");
    compare("===", ARM_OP_strict_eq, left, left, 1, 0, strict);
    compare("===", ARM_OP_strict_eq, left, right, 1, 2, strict);
    compare("!==", ARM_OP_strict_neq, left, shorter, 1, 1, strict);
    compare("==", ARM_OP_eq, left, right, 1, 2, strings);
    compare("!=", ARM_OP_neq, left, shorter, 1, 1, strings);
    uint16_t wide[] = {0x3a9, 0x3a9, 0x3a9, 0x3a9, 0x3a9, 0x3a9, 0x3a9, 0x3a9};
    JSValue w1 = JS_NewStringUTF16(ctx, wide, 8), w2 = JS_NewStringUTF16(ctx, wide, 8);
    compare("===", ARM_OP_strict_eq, w1, w2, 1, 2, strict);
    compare("!==", ARM_OP_strict_neq, left, w1, 1, 3, strict);
    compare("==", ARM_OP_eq, object, JS_NULL, 0, 10, objects);
    compare("!=", ARM_OP_neq, JS_UNDEFINED, object, 1, 10, objects);
    compare("==", ARM_OP_eq, left, JS_NULL, 0, 10, nulls);
    compare("==", ARM_OP_eq, symbol, JS_UNDEFINED, 0, 10, nulls);
    compare("==", ARM_OP_eq, JS_NULL, JS_UNDEFINED, 1, 9, nulls);
    compare("!=", ARM_OP_neq, JS_TRUE, JS_NULL, 1, 9, nulls);
    compare("===", ARM_OP_strict_eq, JS_NewFloat64(ctx, 1.5), JS_TRUE, 0, 5, strict);
    JS_FreeValue(ctx, w1);
    JS_FreeValue(ctx, w2);
    JS_FreeValue(ctx, left);
    JS_FreeValue(ctx, right);
    JS_FreeValue(ctx, shorter);
    JS_FreeValue(ctx, symbol);
    JS_FreeValue(ctx, other);
    JS_FreeValue(ctx, object);
    JS_FreeValue(ctx, different);
    JS_RunGC(rt);
    JS_FreeContext(ctx);
    JS_FreeRuntime(rt);
    assert(!memory.live && !memory.bytes);
    printf("AARCH64_COMPARISON_PATHS_OK checks=%u native=%d zero_ledgers\n", checks, native);
    return 0;
}
