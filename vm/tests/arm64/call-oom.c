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
#include "../common/native_oom_allocator.h"
#ifdef QJS_AARCH64_VM_INSTRUMENT
#include "src/arm64/linux/interpreter-observe.h"
#endif

static uintptr_t word(JSRuntime *rt, size_t offset)
{
    uintptr_t value;
    memcpy(&value, (const unsigned char *)rt + offset, sizeof(value));
    return value;
}
int main(int argc, char **argv)
{
    assert(argc == 2);
    unsigned failures = 0, successes = 0;
    for (unsigned point = 1; point <= 24; point++) {
        Allocator ledger = {0};
        JSRuntime *rt = JS_NewRuntime2(&functions, &ledger);
        assert(rt);
        JS_SetMaxStackSize(rt, 4 * 1024 * 1024);
        JSContext *ctx = JS_NewContext(rt);
        assert(ctx);
        const char *source = "(function deep(n,a){let v=a+1;if(n)return deep(n-1,v)+1;return v;})";
        JSValue driver =
            JS_Eval(ctx, source, strlen(source), "<arm-call-oom>", JS_EVAL_TYPE_GLOBAL);
        assert(!JS_IsException(driver));
        JSValue args[2] = {JS_NewInt32(ctx, 0), JS_NewInt32(ctx, 0)};
        JSValue value = JS_Call(ctx, driver, JS_UNDEFINED, 2, args);
        assert(!JS_IsException(value));
        JS_FreeValue(ctx, value);
        uintptr_t top = word(rt, ARM_OFF_JSRuntime_stack_top),
                  limit = word(rt, ARM_OFF_JSRuntime_stack_limit);
        args[0] = JS_NewInt32(ctx, 250);
        ledger.fail_at = ledger.sequence + point;
        size_t start_sequence = ledger.sequence;
        value = JS_Call(ctx, driver, JS_UNDEFINED, 2, args);
        ledger.fail_at = 0;
        if (JS_IsException(value)) {
            ++failures;
            JS_FreeValue(ctx, JS_GetException(ctx));
        } else {
            int32_t number;
            assert(JS_ToInt32(ctx, &number, value) == 0 && number == 501);
            ++successes;
        }
        JS_FreeValue(ctx, value);
        if (point == 1) {
            fprintf(stderr, "CALL_OOM_PROBE mode=%s allocation_requests=%zu rejected=%u\n", argv[1],
                    ledger.sequence - start_sequence, ledger.rejected);
#ifdef QJS_AARCH64_VM_INSTRUMENT
            QJSArmVMCounts counts;
            qjs_aarch64_vm_counts(&counts);
            fprintf(stderr, "CALL_OOM_PROBE activations=%llu native_calls=%llu\n",
                    (unsigned long long)counts.activations,
                    (unsigned long long)counts.native_calls);
#endif
        }
        assert(word(rt, ARM_OFF_JSRuntime_stack_top) == top &&
               word(rt, ARM_OFF_JSRuntime_stack_limit) == limit);
        JS_RunGC(rt);
        value = JS_Call(ctx, driver, JS_UNDEFINED, 2, args);
        int32_t number;
        assert(!JS_IsException(value) && JS_ToInt32(ctx, &number, value) == 0 && number == 501);
        JS_FreeValue(ctx, value);
        assert(word(rt, ARM_OFF_JSRuntime_stack_top) == top &&
               word(rt, ARM_OFF_JSRuntime_stack_limit) == limit);
        JS_FreeValue(ctx, driver);
        JS_FreeContext(ctx);
        JS_RunGC(rt);
        JS_FreeRuntime(rt);
        assert(ledger.live == 0 && ledger.bytes == 0);
    }
    if (strcmp(argv[1], "legacy"))
        assert(failures > 0);
    assert(failures + successes == 24);
    printf("AARCH64_CALL_OOM_OK mode=%s faults=%u success=%u trials=24 live=0 quota_restored=24\n",
           argv[1], failures, successes);
    return 0;
}
