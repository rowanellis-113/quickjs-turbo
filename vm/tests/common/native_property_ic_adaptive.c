/* Public API value/GC/OOM checks; private inspection proves >4-way coverage. */
#include "quickjs.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
extern int js_property_ic_inspect(JSValueConst, uint32_t counts[7]);
static JSValue global(JSContext *ctx, const char *name)
{
    JSValue object = JS_GetGlobalObject(ctx), result = JS_GetPropertyStr(ctx, object, name);
    JS_FreeValue(ctx, object);
    return result;
}
static int evaluate(JSContext *ctx, const char *text)
{
    JSValue value = JS_Eval(ctx, text, strlen(text), "adaptive-ic", JS_EVAL_TYPE_GLOBAL);
    if (JS_IsException(value))
        return -1;
    JS_FreeValue(ctx, value);
    return 0;
}
int main(void)
{
    JSRuntime *rt = JS_NewRuntime();
    JSContext *ctx;
    JSValue function = JS_UNDEFINED, array = JS_UNDEFINED, args[2] = {JS_UNDEFINED, JS_UNDEFINED},
            result;
    JSMemoryUsage before, after;
    uint32_t counts[7];
    int32_t number;
    int code = 1;
    int disabled = getenv("QJS_DISABLE_PROPERTY_IC") != NULL;
    int legacy = getenv("QJS_DISABLE_IC_ADAPTIVE_WAYS") != NULL;
    if (!rt || !(ctx = JS_NewContext(rt)))
        return 1;
    if (evaluate(
            ctx,
            "function PolyCreate(v){this.a=v;this.b=v+1;this.c=v+2}"
            "var ctors=[],anchors=[];for(var i=0;i<12;i++){var C=Function('v','PolyCreate.call(this,v)');C.prototype={constructor:C};ctors.push(C);anchors.push(new C(i))}"
            "function validate(){for(var n=0;n<4;n++)for(var i=0;i<ctors.length;i++){var o=new ctors[i](i);if(o.a!==i||o.b!==i+1||o.c!==i+2)throw Error('polymorphic constructor')}}validate();"))
        goto end;
    JS_RunGC(rt);
    if (evaluate(ctx, "validate();"))
        goto end;
    function = global(ctx, "PolyCreate");
    if (js_property_ic_inspect(function, counts) < 0)
        goto end;
    printf("POLY transition=%u resize=%u mega=%u\n", counts[5], counts[6], counts[0]);
    if (!disabled && (legacy ? counts[0] == 0 : counts[0] != 0 || counts[5] + counts[6] < 12))
        goto end;
    JS_FreeValue(ctx, function);
    function = JS_UNDEFINED;
    if (evaluate(
            ctx,
            "var oomObjects=[];for(var i=0;i<5;i++){var o={value:0};o['unique'+i]=i;oomObjects.push(o)}"
            "function storeOnly(o,v){o.value=v;return v}for(var i=0;i<4;i++)storeOnly(oomObjects[i],i);"))
        goto end;
    function = global(ctx, "storeOnly");
    array = global(ctx, "oomObjects");
    args[0] = JS_GetPropertyUint32(ctx, array, 4);
    args[1] = JS_NewInt32(ctx, 99);
    JS_ComputeMemoryUsage(rt, &before);
    /* Existing own data slot: only optional cache growth needs new heap space. */
    JS_SetMemoryLimit(rt, (size_t)before.malloc_size + 1);
    result = JS_Call(ctx, function, JS_UNDEFINED, 2, (JSValueConst *)args);
    JS_SetMemoryLimit(rt, 0);
    if (JS_IsException(result))
        goto end;
    if (JS_ToInt32(ctx, &number, result) < 0 || number != 99) {
        JS_FreeValue(ctx, result);
        goto end;
    }
    JS_FreeValue(ctx, result);
    if (js_property_ic_inspect(function, counts) < 0 || (!disabled && counts[4] != 4))
        goto end;
    JS_ComputeMemoryUsage(rt, &before);
    /* Failed growth may still install the fifth shape by bounded replacement.
     * Revisit all five receivers, independently of which way was evicted. */
    for (unsigned i = 0; i < 5; i++) {
        JS_FreeValue(ctx, args[0]);
        args[0] = JS_GetPropertyUint32(ctx, array, i);
        result = JS_Call(ctx, function, JS_UNDEFINED, 2, (JSValueConst *)args);
        if (JS_IsException(result))
            goto end;
        if (JS_ToInt32(ctx, &number, result) < 0 || number != 99) {
            JS_FreeValue(ctx, result);
            goto end;
        }
        JS_FreeValue(ctx, result);
    }
    if (js_property_ic_inspect(function, counts) < 0 ||
        (!disabled && counts[4] != (legacy ? 4 : 5)))
        goto end;
    JS_ComputeMemoryUsage(rt, &after);
    if (!disabled && !legacy && after.memory_used_size <= before.memory_used_size)
        goto end;
    printf("OPTIONAL_GROWTH replace=%u accounted_delta=%lld\n", counts[4],
           (long long)(after.memory_used_size - before.memory_used_size));
    JS_RunGC(rt);
    code = 0;
    puts("ADAPTIVE IC PASSED");
end:
    JS_SetMemoryLimit(rt, 0);
    if (code) {
        JSValue exception = JS_GetException(ctx);
        const char *message = JS_ToCString(ctx, exception);
        fprintf(stderr, "adaptive IC failure: %s\n", message ? message : "unknown");
        JS_FreeCString(ctx, message);
        JS_FreeValue(ctx, exception);
    }
    JS_FreeValue(ctx, args[0]);
    JS_FreeValue(ctx, args[1]);
    JS_FreeValue(ctx, array);
    JS_FreeValue(ctx, function);
    JS_FreeContext(ctx);
    JS_FreeRuntime(rt);
    return code;
}
