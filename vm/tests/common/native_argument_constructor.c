#include "quickjs.h"
#include <stdint.h>
#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

extern _Atomic(uint64_t) JS_FrameArgumentsConstructStats[2];
int main(void)
{
    JSRuntime *rt = JS_NewRuntime();
    JSContext *ctx = JS_NewContext(rt);
    const char *source =
        "'use strict';function C(x){this.value=arguments[0];}"
        "function run(){let result;for(let i=0;i<128;i++)result=new C(i);return result.value;}"
        "if(run()!==127)throw Error('constructor result');";
    JSValue value =
        JS_Eval(ctx, source, strlen(source), "argument-constructor-host.js", JS_EVAL_TYPE_GLOBAL);
    if (JS_IsException(value))
        return 2;
    JS_FreeValue(ctx, value);
    uint64_t hits = atomic_load_explicit(&JS_FrameArgumentsConstructStats[0], memory_order_relaxed);
    int disabled = getenv("QJS_DISABLE_FRAME_ARGUMENTS_CONSTRUCTOR") != NULL;
    if (disabled ? (hits != 0) : (hits != 128))
        return 3;
    /* A successful foreign constructor also keeps the original path. */
    JSContext *foreign = JS_NewContext(rt);
    if (!foreign)
        return 4;
    const char *foreign_source = "function Foreign(x){this.value=arguments[0];} Foreign;";
    JSValue ctor = JS_Eval(foreign, foreign_source, strlen(foreign_source),
                           "foreign-argument-constructor.js", JS_EVAL_TYPE_GLOBAL);
    if (JS_IsException(ctor))
        return 5;
    JSValue global = JS_GetGlobalObject(ctx);
    if (JS_SetPropertyStr(ctx, global, "Foreign", ctor) < 0)
        return 6;
    JS_FreeValue(ctx, global);
    const char *cross = "function foreignRun(){return new Foreign(73);} foreignRun();";
    value =
        JS_Eval(ctx, cross, strlen(cross), "foreign-constructor-caller.js", JS_EVAL_TYPE_GLOBAL);
    if (JS_IsException(value))
        return 7;
    JSValue property = JS_GetPropertyStr(ctx, value, "value");
    int32_t n = 0;
    int failed = JS_ToInt32(ctx, &n, property);
    JS_FreeValue(ctx, property);
    JS_FreeValue(ctx, value);
    if (failed || n != 73)
        return 8;
    if (atomic_load_explicit(&JS_FrameArgumentsConstructStats[0], memory_order_relaxed) != hits)
        return 9;
    JS_FreeContext(foreign);
    JS_FreeContext(ctx);
    JS_FreeRuntime(rt);
    printf("ARGUMENT_CONSTRUCTOR_HOST_OK hits=%llu disabled=%d\n", (unsigned long long)hits,
           disabled);
    return 0;
}
