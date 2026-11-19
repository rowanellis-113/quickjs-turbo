/* Fault/recovery of captured missing-arity children. MIT. */
#ifdef NDEBUG
#undef NDEBUG
#endif
#include "quickjs.h"
#include "interpreter-aarch64-values.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "tests/common/native_oom_allocator.h"
static uintptr_t word(JSRuntime *rt, size_t offset)
{
    uintptr_t v;
    memcpy(&v, (const unsigned char *)rt + offset, sizeof(v));
    return v;
}
int main(int argc, char **argv)
{
    assert(argc == 2);
    unsigned failures = 0, successes = 0, rejections = 0;
    for (unsigned variant = 0; variant < 2; variant++)
        for (unsigned point = 1; point <= 24; point++) {
            Allocator ledger = {0};
            JSRuntime *rt = JS_NewRuntime2(&functions, &ledger);
            assert(rt);
            JS_SetMaxStackSize(rt, 4 * 1024 * 1024);
            JSContext *ctx = JS_NewContext(rt);
            assert(ctx);
            const char *source =
                "(function(x,a,b){var y=x,z=x;return function(which){return which===0?x:which===1?y:z;};})";
            if (variant)
                source =
                    "(function(x,a,b){var y=x,z=x;var keep=function(which){return which===0?x:which===1?y:z;};return keep;})";
            JSValue f = JS_Eval(ctx, source, strlen(source), "<capture-oom>", JS_EVAL_TYPE_GLOBAL);
            assert(!JS_IsException(f));
            source = "(function(f,x){var r=f(x);return r;})";
            JSValue driver =
                JS_Eval(ctx, source, strlen(source), "<capture-oom-driver>", JS_EVAL_TYPE_GLOBAL);
            assert(!JS_IsException(driver));
            JSValue object = JS_NewObject(ctx);
            assert(!JS_IsException(object));
            JSValue warm[] = {object, JS_UNDEFINED, JS_UNDEFINED};
            JSValue result = JS_Call(ctx, f, JS_UNDEFINED, 3, warm);
            assert(!JS_IsException(result));
            JS_FreeValue(ctx, result);
            JSValue args[] = {f, object};
            uintptr_t top = word(rt, ARM_OFF_JSRuntime_stack_top),
                      limit = word(rt, ARM_OFF_JSRuntime_stack_limit);
            ledger.fail_at = ledger.sequence + point;
            result = JS_Call(ctx, driver, JS_UNDEFINED, 2, args);
            ledger.fail_at = 0;
            rejections += ledger.rejected;
            if (JS_IsException(result)) {
                ++failures;
                JS_FreeValue(ctx, JS_GetException(ctx));
            } else {
                ++successes;
                JS_RunGC(rt);
                for (unsigned k = 0; k < 3; k++) {
                    JSValue which = JS_NewInt32(ctx, k),
                            v = JS_Call(ctx, result, JS_UNDEFINED, 1, &which);
                    assert(!JS_IsException(v) && JS_VALUE_GET_PTR(v) == JS_VALUE_GET_PTR(object));
                    JS_FreeValue(ctx, v);
                }
            }
            JS_FreeValue(ctx, result);
            JS_RunGC(rt);
            assert(word(rt, ARM_OFF_JSRuntime_stack_top) == top &&
                   word(rt, ARM_OFF_JSRuntime_stack_limit) == limit);
            /* Recovery must allocate/close all three references after every fault. */
            result = JS_Call(ctx, driver, JS_UNDEFINED, 2, args);
            assert(!JS_IsException(result));
            JS_RunGC(rt);
            for (unsigned k = 0; k < 3; k++) {
                JSValue which = JS_NewInt32(ctx, k),
                        v = JS_Call(ctx, result, JS_UNDEFINED, 1, &which);
                assert(!JS_IsException(v) && JS_VALUE_GET_PTR(v) == JS_VALUE_GET_PTR(object));
                JS_FreeValue(ctx, v);
            }
            JS_FreeValue(ctx, result);
            assert(word(rt, ARM_OFF_JSRuntime_stack_top) == top &&
                   word(rt, ARM_OFF_JSRuntime_stack_limit) == limit);
            JS_FreeValue(ctx, object);
            JS_FreeValue(ctx, driver);
            JS_FreeValue(ctx, f);
            JS_FreeContext(ctx);
            JS_RunGC(rt);
            JS_FreeRuntime(rt);
            assert(ledger.live == 0 && ledger.bytes == 0);
        }
    assert(failures > 0 && successes > 0 && failures + successes == 48 && rejections > 0);
    printf(
        "AARCH64_CAPTURED_OOM_OK mode=%s failures=%u success=%u rejected=%u trials=48 live=0 quota_restored=48\n",
        argv[1], failures, successes, rejections);
    return 0;
}
