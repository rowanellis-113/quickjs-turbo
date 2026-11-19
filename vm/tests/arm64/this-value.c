#ifdef NDEBUG
#undef NDEBUG
#endif
#include "quickjs.h"
#ifdef QJS_AARCH64_VM_INSTRUMENT
#include "src/arm64/linux/interpreter-observe.h"
#endif
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static JSValue checked(JSContext *ctx, JSValue value)
{
    if (JS_IsException(value)) {
        JSValue error = JS_GetException(ctx);
        const char *text = JS_ToCString(ctx, error);
        fprintf(stderr, "this value: %s\n", text ? text : "<exception>");
        abort();
    }
    return value;
}
static JSValue eval(JSContext *ctx, const char *text)
{
    return checked(ctx, JS_Eval(ctx, text, strlen(text), "<arm-this>", JS_EVAL_TYPE_GLOBAL));
}
int main(int argc, char **argv)
{
    assert(argc == 2);
    int native = !strcmp(argv[1], "native");
    JSRuntime *rt = JS_NewRuntime();
    assert(rt);
    JS_SetMaxStackSize(rt, 4 * 1024 * 1024);
    JSContext *caller = JS_NewContext(rt), *foreign = JS_NewContext(rt);
    assert(caller && foreign);
    JSContext *realms[] = {caller, foreign};
    JSValue functions[2][2], globals[2];
    for (unsigned r = 0; r < 2; r++) {
        functions[r][0] = eval(realms[r], "(function(){return this;})");
        functions[r][1] = eval(realms[r], "(function(){'use strict';return this;})");
        globals[r] = JS_GetGlobalObject(realms[r]);
    }
    JSValue values[] = {JS_UNDEFINED,
                        JS_NULL,
                        JS_TRUE,
                        JS_FALSE,
                        JS_NewInt32(caller, -3),
                        eval(caller, "1.5"),
                        eval(caller, "-0"),
                        JS_NewString(caller, "this"),
                        JS_NewString(caller, ""),
                        eval(caller, "3n"),
                        eval(caller, "Symbol('this')"),
                        JS_NewObject(caller),
                        JS_DupValue(caller, globals[0])};
    unsigned cases = 0;
    for (unsigned r = 0; r < 2; r++)
        for (unsigned strict = 0; strict < 2; strict++)
            for (unsigned i = 0; i < sizeof(values) / sizeof(values[0]); i++) {
                JSValue value = values[i];
                int nullish = JS_IsNull(value) || JS_IsUndefined(value);
                int box = !strict && !nullish && !JS_IsObject(value);
#ifdef QJS_AARCH64_VM_INSTRUMENT
                QJSArmVMCounts before, after;
                qjs_aarch64_vm_counts(&before);
#endif
                JSValue result =
                    checked(caller, JS_Call(caller, functions[r][strict], value, 0, NULL));
#ifdef QJS_AARCH64_VM_INSTRUMENT
                qjs_aarch64_vm_counts(&after);
                if (native) {
                    assert(after.activations - before.activations == 1);
                    if (box)
                        assert(after.c_steps > before.c_steps);
                    else
                        assert(after.c_steps == before.c_steps);
                } else
                    assert(after.activations == 0);
#else
                (void)native;
#endif
                JS_RunGC(rt);
                if (!strict && nullish) {
                    if (!JS_IsStrictEqual(caller, result, globals[r]))
                        fprintf(stderr, "THIS_GLOBAL_MISMATCH realm=%u input=%u\n", r, i);
                    assert(JS_IsStrictEqual(caller, result, globals[r]));
                } else if (box) {
                    assert(JS_IsObject(result));
                    JSValue method = checked(caller, JS_GetPropertyStr(caller, result, "valueOf"));
                    JSValue primitive = checked(caller, JS_Call(caller, method, result, 0, NULL));
                    assert(JS_IsStrictEqual(caller, primitive, value));
                    // Boxing must use the callee's realm, including a foreign caller.
                    JSValue global = JS_GetGlobalObject(realms[r]);
                    const char *name = JS_IsBool(value)     ? "Boolean"
                                       : JS_IsNumber(value) ? "Number"
                                       : JS_IsString(value) ? "String"
                                       : JS_IsBigInt(value) ? "BigInt"
                                                            : "Symbol";
                    JSValue constructor =
                        checked(realms[r], JS_GetPropertyStr(realms[r], global, name));
                    JSValue expected =
                        checked(realms[r], JS_GetPropertyStr(realms[r], constructor, "prototype"));
                    JSValue actual = checked(caller, JS_GetPrototype(caller, result));
                    assert(JS_IsStrictEqual(caller, actual, expected));
                    JS_FreeValue(caller, actual);
                    JS_FreeValue(realms[r], expected);
                    JS_FreeValue(realms[r], constructor);
                    JS_FreeValue(realms[r], global);
                    JS_FreeValue(caller, primitive);
                    JS_FreeValue(caller, method);
                } else
                    assert(JS_IsStrictEqual(caller, result, value));
                JS_FreeValue(caller, result);
                ++cases;
            }
    for (unsigned i = 0; i < sizeof(values) / sizeof(values[0]); i++)
        JS_FreeValue(caller, values[i]);
    for (unsigned r = 0; r < 2; r++) {
        JS_FreeValue(realms[r], functions[r][0]);
        JS_FreeValue(realms[r], functions[r][1]);
        JS_FreeValue(realms[r], globals[r]);
    }
    JS_FreeContext(foreign);
    JS_FreeContext(caller);
    JS_RunGC(rt);
    JS_FreeRuntime(rt);
    printf("AARCH64_THIS_VALUE_OK mode=%s cases=%u strict_sloppy_realms_boxing_gc=passed\n",
           argv[1], cases);
    return 0;
}
