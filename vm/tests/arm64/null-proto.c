/* Natural native NULL_PROTO admission and retained THIS_FUNC routing. MIT. */
#ifdef NDEBUG
#undef NDEBUG
#endif
#include "quickjs.h"
#include "interpreter-aarch64-values.h"
#include "src/arm64/linux/interpreter-observe.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "tests/common/native_oom_allocator.h"
extern int qjs_aarch64_vm_function_info(JSValueConst, uintptr_t *);
static JSValue checked(JSContext *ctx, JSValue value)
{
    if (JS_IsException(value)) {
        JSValue e = JS_GetException(ctx);
        const char *s = JS_ToCString(ctx, e);
        fprintf(stderr, "NULL_PATH_EXCEPTION %s\n", s ? s : "<exception>");
        abort();
    }
    return value;
}
int main(void)
{
    Allocator memory = {0};
    JSRuntime *rt = JS_NewRuntime2(&functions, &memory);
    assert(rt);
    JSContext *ctx = JS_NewContext(rt);
    assert(ctx);
    int enabled = !getenv("QJS_DISABLE_NATIVE_NULL_PROTO") &&
                  !getenv("QJS_DISABLE_LINUX_ADMISSION") &&
                  !getenv("QJS_DISABLE_REGISTER_INTERP") && !getenv("QJS_DISABLE_INTERP_FRAME");
    const char *bodies[] = {
        "(function(){return {__proto__:null}})",
        "(function(a){a={__proto__:null};return a})",
        "(function(seed){return function(){let a={__proto__:null};a.x=seed;return a}})(17)",
        "(function self(a){if(a)return self;return {__proto__:null}})",
        "(function(){return {}})",
        "(function self(){return self})"};
    unsigned native = 0;
    for (unsigned n = 0; n < sizeof(bodies) / sizeof(bodies[0]); n++) {
        JSValue f = checked(
            ctx, JS_Eval(ctx, bodies[n], strlen(bodies[n]), "null-paths", JS_EVAL_TYPE_GLOBAL));
        QJSArmVMCounts before, after;
        uint64_t ops0[256], ops1[256];
        qjs_aarch64_vm_counts(&before);
        qjs_aarch64_vm_opcode_counts(ops0);
        for (unsigned i = 0; i < 32; i++) {
            JSValue arg = JS_FALSE, value = checked(ctx, JS_Call(ctx, f, JS_UNDEFINED, 1, &arg));
            if (n < 5) {
                JSValue prototype = checked(ctx, JS_GetPrototype(ctx, value));
                assert(n == 4 ? JS_IsObject(prototype) : JS_IsNull(prototype));
                JS_FreeValue(ctx, prototype);
                if (n == 2) {
                    JSValue x = checked(ctx, JS_GetPropertyStr(ctx, value, "x"));
                    int32_t v;
                    assert(!JS_ToInt32(ctx, &v, x) && v == 17);
                    JS_FreeValue(ctx, x);
                }
            } else
                assert(JS_IsSameValue(ctx, value, f));
            JS_FreeValue(ctx, value);
            if (i % 7 == 0)
                JS_RunGC(rt);
        }
        qjs_aarch64_vm_counts(&after);
        qjs_aarch64_vm_opcode_counts(ops1);
        uintptr_t info[6];
        assert(qjs_aarch64_vm_function_info(f, info));
        printf("NULL_COHORT %u kind=%zu activations=%llu native=%llu special_C=%llu\n", n,
               (size_t)info[0], (unsigned long long)(after.activations - before.activations),
               (unsigned long long)(after.native_ops - before.native_ops),
               (unsigned long long)(ops1[ARM_OP_special_object] - ops0[ARM_OP_special_object]));
        if (n < 3 && enabled) {
            assert(info[0] & 32);
            assert(after.activations > before.activations);
            assert(after.native_ops - before.native_ops >= 64);
            assert(ops1[ARM_OP_special_object] == ops0[ARM_OP_special_object]);
            native++;
        } else
            assert(!(info[0] & 32));
        JS_FreeValue(ctx, f);
    }
    JS_FreeContext(ctx);
    JS_FreeRuntime(rt);
    assert(!memory.live && !memory.bytes);
    printf("ARM64_NULL_PATHS_OK cohorts=6 native=%u zero-ledgers\n", native);
    return 0;
}
