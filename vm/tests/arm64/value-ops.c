#ifdef NDEBUG
#undef NDEBUG
#endif
#include "quickjs.h"
#include "src/arm64/linux/interpreter-observe.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static JSValue checked(JSContext *ctx, JSValue value)
{
    if (JS_IsException(value)) {
        JSValue error = JS_GetException(ctx);
        const char *text = JS_ToCString(ctx, error);
        fprintf(stderr, "%s\n", text ? text : "<exception>");
        abort();
    }
    return value;
}
int main(int argc, char **argv)
{
    assert(argc == 2);
    int slot_off = !strcmp(argv[1], "slot-off") || !strcmp(argv[1], "slot-zero");
    int native = !strcmp(argv[1], "native") || slot_off;
    JSRuntime *rt = JS_NewRuntime();
    assert(rt);
    JS_SetMaxStackSize(rt, 4 * 1024 * 1024);
    JSContext *ctx = JS_NewContext(rt);
    assert(ctx);
    const char *source =
        "function write(a,b){a=b;b=3;return a+b;}"
        "function loop(n){var i=0,s=0;for(;i<n;i++)s+=i;return s;}"
        "function heap(a,b){a=b;return a;}"
        "function alias(a){a=a;return a;}"
        "function wide(a,b,c,d,e){e=b;a=e;return a;}"
        "function comparisons(a,b){var s=0;if(a<b)s+=1;if(a<=b)s+=2;if(a>b)s+=4;if(a>=b)s+=8;"
        "if(a==b)s+=16;if(a!=b)s+=32;if(a===b)s+=64;if(a!==b)s+=128;return s;}"
        "function branches(a){if(a)return 7;return 9;}";
    JS_FreeValue(ctx, checked(ctx, JS_Eval(ctx, source, strlen(source), "<arm-values>",
                                           JS_EVAL_TYPE_GLOBAL)));
    JSValue global = JS_GetGlobalObject(ctx);
    const char *names[] = {"write", "loop", "heap", "alias", "wide", "comparisons", "branches"};
    uint64_t native_steps = 0, native_ops = 0;
    for (unsigned pass = 0; pass < 20; pass++)
        for (unsigned i = 0; i < 7; i++) {
            JSValue function = JS_GetPropertyStr(ctx, global, names[i]);
            JSValue a = JS_NewObject(ctx), b = JS_NewObject(ctx);
            assert(!JS_IsException(a) && !JS_IsException(b));
            JSValue args[5] = {JS_NewInt32(ctx, 4), JS_NewInt32(ctx, 6), JS_UNDEFINED, JS_UNDEFINED,
                               JS_NewInt32(ctx, 8)};
            int count = i == 4 ? 5 : i == 1 || i == 3 || i == 6 ? 1 : 2;
            if (i == 1)
                args[0] = JS_NewInt32(ctx, 100);
            if (i == 2 || i == 3) {
                args[0] = a;
                args[1] = b;
            }
            if (i == 5) {
                args[0] = JS_NewInt32(ctx, pass % 3 == 1 ? 6 : 4);
                args[1] = JS_NewInt32(ctx, pass % 3 == 0 ? 6 : 4);
            }
            if (i == 6)
                args[0] = pass % 5 == 0   ? JS_TRUE
                          : pass % 5 == 1 ? JS_FALSE
                          : pass % 5 == 2 ? JS_NULL
                          : pass % 5 == 3 ? JS_UNDEFINED
                                          : JS_NewInt32(ctx, -1);
            QJSArmVMCounts before, after;
            qjs_aarch64_vm_counts(&before);
            JSValue result = checked(ctx, JS_Call(ctx, function, JS_UNDEFINED, count, args));
            qjs_aarch64_vm_counts(&after);
            if (i == 2 || i == 3)
                assert(JS_VALUE_GET_PTR(result) == JS_VALUE_GET_PTR(i == 2 ? b : a));
            else {
                int32_t n;
                assert(JS_ToInt32(ctx, &n, result) == 0);
                assert(n == (i == 0                             ? 9
                             : i == 1                           ? 4950
                             : i == 4                           ? 6
                             : i == 5                           ? (pass % 3 == 0   ? 163
                                                                   : pass % 3 == 1 ? 172
                                                                                   : 90)
                             : (pass % 5 == 0 || pass % 5 == 4) ? 7
                                                                : 9));
            }
            if (native) {
                native_steps += after.c_steps - before.c_steps;
                native_ops += after.native_ops - before.native_ops;
                assert(after.activations - before.activations == 1);
                if (after.c_steps != before.c_steps && !slot_off)
                    fprintf(stderr, "VALUE_ROUTE name=%s pass=%u native=%llu c_steps=%llu\n",
                            names[i], pass,
                            (unsigned long long)(after.native_ops - before.native_ops),
                            (unsigned long long)(after.c_steps - before.c_steps));
                if (slot_off && (i == 2 || i == 3))
                    assert(after.c_steps > before.c_steps);
                else
                    assert(after.c_steps == before.c_steps);
            } else
                assert(after.activations == 0);
            JS_FreeValue(ctx, result);
            JS_FreeValue(ctx, function);
            JS_FreeValue(ctx, a);
            JS_FreeValue(ctx, b);
        }
    JS_FreeValue(ctx, global);
    JS_FreeContext(ctx);
    JS_RunGC(rt);
    JS_FreeRuntime(rt);
    printf("AARCH64_VALUE_OPS_OK mode=%s calls=140 native_ops=%llu c_steps=%llu\n", argv[1],
           (unsigned long long)native_ops, (unsigned long long)native_steps);
    return 0;
}
