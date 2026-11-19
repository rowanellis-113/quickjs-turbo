#ifdef NDEBUG
#undef NDEBUG
#endif
#include "quickjs.h"
#include "src/arm64/linux/interpreter-observe.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static JSValue checked(JSContext *ctx, JSValue value)
{
    if (JS_IsException(value)) {
        JSValue error = JS_GetException(ctx);
        const char *text = JS_ToCString(ctx, error);
        fprintf(stderr, "reference: %s\n", text ? text : "<exception>");
        abort();
    }
    return value;
}
static JSValue eval(JSContext *ctx, const char *text)
{
    return checked(ctx, JS_Eval(ctx, text, strlen(text), "<arm-reference>", JS_EVAL_TYPE_GLOBAL));
}
static unsigned tdz_errors;
static JSValue before_init(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)self;
    assert(argc == 2);
    for (unsigned i = 0; i < 2; i++) {
        JSValue argument = JS_NewInt32(ctx, 40);
        JSValue result = JS_Call(ctx, argv[i], JS_UNDEFINED, i, &argument);
        assert(JS_IsException(result));
        JSValue error = JS_GetException(ctx);
        JSValue name = checked(ctx, JS_GetPropertyStr(ctx, error, "name"));
        const char *text = JS_ToCString(ctx, name);
        assert(text && !strcmp(text, "ReferenceError"));
        JS_FreeCString(ctx, text);
        JS_FreeValue(ctx, name);
        JS_FreeValue(ctx, error);
        ++tdz_errors;
    }
    JS_RunGC(JS_GetRuntime(ctx));
    return JS_UNDEFINED;
}
int main(int argc, char **argv)
{
    assert(argc == 2);
    int vm = strcmp(argv[1], "register-off") && strcmp(argv[1], "legacy");
    int ref_off = !strcmp(argv[1], "ref-off") || !strcmp(argv[1], "ref-zero");
    JSRuntime *rt = JS_NewRuntime();
    assert(rt);
    JS_SetMaxStackSize(rt, 4 * 1024 * 1024);
    JSContext *ctx = JS_NewContext(rt);
    assert(ctx);
    const char *factory = "(function(a,b,c,d,e){return ["
                          "function(){return a+b+c+d+e;},"
                          "function(next){var sum=a+b+c+d;e=next;return sum+e;},"
                          "function(next){var sum=a+b+c+d;return (e=next)+sum;},"
                          "function(){return 1.5+2.25;},function(){return this;}];})(1,2,3,4,5)";
    JSValue array = eval(ctx, factory), functions[5];
    for (unsigned i = 0; i < 5; i++)
        functions[i] = checked(ctx, JS_GetPropertyUint32(ctx, array, i));
    JS_FreeValue(ctx, array);
    JS_RunGC(rt);
    JSValue self = JS_NewObject(ctx);
    assert(!JS_IsException(self));
    uint64_t native_ops = 0, c_steps = 0;
    for (unsigned pass = 0; pass < 20; pass++)
        for (unsigned i = 0; i < 5; i++) {
            JSValue argument = JS_NewInt32(ctx, 5);
            QJSArmVMCounts before, after;
            qjs_aarch64_vm_counts(&before);
            JSValue result =
                checked(ctx, JS_Call(ctx, functions[i], self, i == 1 || i == 2, &argument));
            qjs_aarch64_vm_counts(&after);
            if (i == 4)
                assert(JS_VALUE_GET_PTR(result) == JS_VALUE_GET_PTR(self));
            else if (i == 3) {
                double d;
                assert(JS_ToFloat64(ctx, &d, result) == 0 && d == 3.75);
            } else {
                int32_t n;
                assert(JS_ToInt32(ctx, &n, result) == 0 && n == 15);
            }
            if (vm) {
                assert(after.activations - before.activations == 1);
                if (ref_off && i < 3)
                    assert(after.c_steps > before.c_steps);
                else {
                    if (after.c_steps != before.c_steps)
                        fprintf(stderr, "REF_ROUTE function=%u c_steps=%llu\n", i,
                                (unsigned long long)(after.c_steps - before.c_steps));
                    assert(after.c_steps == before.c_steps);
                }
            } else
                assert(after.activations == 0);
            native_ops += after.native_ops - before.native_ops;
            c_steps += after.c_steps - before.c_steps;
            JS_FreeValue(ctx, result);
        }
    JSValue global = JS_GetGlobalObject(ctx);
    assert(JS_SetPropertyStr(ctx, global, "beforeInit",
                             JS_NewCFunction(ctx, before_init, "beforeInit", 2)) == 1);
    JS_FreeValue(ctx, global);
    JSValue getter =
        eval(ctx, "(function(){beforeInit(function(){return value;},function(next){value=next;});"
                  "let value=1;return function(){return value;};})()");
    assert(tdz_errors == 2);
    JSValue result = checked(ctx, JS_Call(ctx, getter, JS_UNDEFINED, 0, NULL));
    int32_t number;
    assert(JS_ToInt32(ctx, &number, result) == 0 && number == 1);
    JS_FreeValue(ctx, result);
    JS_FreeValue(ctx, getter);
    // Active capture reads and writes use the same cell before close_var_refs.
    result = eval(ctx, "(function(){let x=3;function f(){x=x+2;return x;}"
                       "if(f()!==5)throw Error('live write');return f();})()");
    assert(JS_ToInt32(ctx, &number, result) == 0 && number == 7);
    JS_FreeValue(ctx, result);
    for (unsigned i = 0; i < 5; i++)
        JS_FreeValue(ctx, functions[i]);
    JS_FreeValue(ctx, self);
    JS_FreeContext(ctx);
    JS_RunGC(rt);
    JS_FreeRuntime(rt);
    printf(
        "AARCH64_REFERENCE_OPS_OK mode=%s calls=100 tdz_errors=%u native_ops=%llu c_steps=%llu\n",
        argv[1], tdz_errors, (unsigned long long)native_ops, (unsigned long long)c_steps);
    return 0;
}
