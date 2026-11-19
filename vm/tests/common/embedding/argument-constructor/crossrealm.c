#include "quickjs.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define CHECK(c)                                                                                   \
    do {                                                                                           \
        if (!(c)) {                                                                                \
            fprintf(stderr, "realm probe:%d:%s\n", __LINE__, #c);                                  \
            exit(1);                                                                               \
        }                                                                                          \
    } while (0)
static int stack_limit;
static JSValue arm(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)self;
    (void)argc;
    (void)argv;
    if (stack_limit)
        JS_SetMaxStackSize(JS_GetRuntime(ctx), (size_t)stack_limit);
    return JS_UNDEFINED;
}
static JSValue prototype(JSContext *ctx, const char *name)
{
    JSValue g = JS_GetGlobalObject(ctx), c = JS_GetPropertyStr(ctx, g, name);
    JSValue p = JS_GetPropertyStr(ctx, c, "prototype");
    JS_FreeValue(ctx, c);
    JS_FreeValue(ctx, g);
    return p;
}
int main(void)
{
    const int limits[] = {64, 256, 512, 1024, 2048, 4096, 8192, 16384};
    const char *names[] = {"Error", "RangeError", "InternalError", "TypeError"};
    for (unsigned item = 0; item < sizeof(limits) / sizeof(limits[0]); item++) {
        JSRuntime *rt = JS_NewRuntime();
        CHECK(rt);
        JS_SetMaxStackSize(rt, 2 * 1024 * 1024);
        JSContext *caller = JS_NewContext(rt), *target = JS_NewContext(rt);
        CHECK(caller && target);
        JSValue global = JS_GetGlobalObject(caller);
        CHECK(JS_SetPropertyStr(caller, global, "armStack",
                                JS_NewCFunction(caller, arm, "armStack", 0)) >= 0);
        JS_FreeValue(caller, global);
        const char *ctor_source = "'use strict';function C(v){this.value=arguments[0];} C;";
        const char *run_source = "'use strict';function run(C,v){armStack();return new C(v);} run;";
        JSValue ctor = JS_Eval(target, ctor_source, strlen(ctor_source), "foreign-constructor.js",
                               JS_EVAL_TYPE_GLOBAL);
        JSValue run = JS_Eval(caller, run_source, strlen(run_source), "native-caller.js",
                              JS_EVAL_TYPE_GLOBAL);
        CHECK(!JS_IsException(ctor) && !JS_IsException(run));
        JSValue args[] = {ctor, JS_NewInt32(caller, 17)};
        stack_limit = 0;
        JSValue result = JS_Call(caller, run, JS_UNDEFINED, 2, args);
        CHECK(!JS_IsException(result));
        JS_FreeValue(caller, result);
        stack_limit = limits[item];
        result = JS_Call(caller, run, JS_UNDEFINED, 2, args);
        JS_SetMaxStackSize(rt, 2 * 1024 * 1024);
        char origin[64] = "success";
        if (JS_IsException(result)) {
            JSValue error = JS_GetException(caller), proto = JS_GetPrototype(caller, error);
            strcpy(origin, "other");
            for (int which = 0; which < 2; which++)
                for (int n = 0; n < 4; n++) {
                    JSContext *ctx = which ? target : caller;
                    JSValue expected = prototype(ctx, names[n]);
                    if (JS_IsObject(proto) && JS_IsObject(expected) &&
                        JS_VALUE_GET_PTR(proto) == JS_VALUE_GET_PTR(expected))
                        snprintf(origin, sizeof(origin), "%s.%s", which ? "target" : "caller",
                                 names[n]);
                    JS_FreeValue(ctx, expected);
                }
            CHECK(strcmp(origin, "caller.RangeError") == 0 ||
                  strcmp(origin, "caller.InternalError") == 0);
            JS_FreeValue(caller, proto);
            JS_FreeValue(caller, error);
        }
        printf("CROSS_REALM_STACK limit=%d origin=%s\n", limits[item], origin);
        JS_FreeValue(caller, result);
        JS_FreeValue(caller, run);
        JS_FreeValue(target, ctor);
        JS_FreeContext(target);
        JS_FreeContext(caller);
        JS_FreeRuntime(rt);
    }
    puts("ARGUMENT_CONSTRUCTOR_CROSS_REALM_OK");
    return 0;
}
