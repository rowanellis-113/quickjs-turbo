#ifdef NDEBUG
#undef NDEBUG
#endif
#include "quickjs.h"
#include "src/arm64/linux/interpreter-observe.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static JSClassID token_class;
static JSContext *context;
static JSValue reader, writer;
static unsigned born, finalized, reentered, collected;

static JSValue checked(JSValue value)
{
    if (JS_IsException(value)) {
        JSValue error = JS_GetException(context);
        const char *text = JS_ToCString(context, error);
        fprintf(stderr, "slot owner: %s\n", text ? text : "<exception>");
        abort();
    }
    return value;
}
static void expect(int expected)
{
    JSValue value = checked(JS_Call(context, reader, JS_UNDEFINED, 0, NULL));
    int32_t number;
    assert(JS_ToInt32(context, &number, value) == 0 && number == expected);
    JS_FreeValue(context, value);
}
static void finalizer(JSRuntime *rt, JSValue value)
{
    (void)rt;
    (void)value;
    ++finalized;
    // The last release is an observing boundary. The replacement must already
    // be visible, and a reentrant write must survive the original instruction.
    expect(17);
    JSValue argument = JS_NewInt32(context, 99);
    JSValue result = checked(JS_Call(context, writer, JS_UNDEFINED, 1, &argument));
    JS_FreeValue(context, result);
    expect(99);
    ++reentered;
}
static JSValue make(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)self;
    (void)argc;
    (void)argv;
    JSValue value = JS_NewObjectClass(ctx, token_class);
    if (!JS_IsException(value))
        ++born;
    return value;
}
static JSValue remember(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)self;
    assert(argc == 2);
    JS_FreeValue(ctx, reader);
    JS_FreeValue(ctx, writer);
    reader = JS_DupValue(ctx, argv[0]);
    writer = JS_DupValue(ctx, argv[1]);
    return JS_UNDEFINED;
}
static JSValue collect(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)self;
    (void)argc;
    (void)argv;
    JS_RunGC(JS_GetRuntime(ctx));
    JSValue value = checked(JS_Call(ctx, reader, JS_UNDEFINED, 0, NULL));
    assert(JS_GetClassID(value) == token_class);
    JS_FreeValue(ctx, value);
    ++collected;
    return JS_UNDEFINED;
}
static JSValue checkpoint(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)ctx;
    (void)self;
    (void)argc;
    (void)argv;
    expect(99);
    return JS_UNDEFINED;
}
int main(int argc, char **argv)
{
    assert(argc == 2);
    int native = strcmp(argv[1], "register-off") && strcmp(argv[1], "legacy");
    JSRuntime *rt = JS_NewRuntime();
    assert(rt);
    JS_SetMaxStackSize(rt, 4 * 1024 * 1024);
    context = JS_NewContext(rt);
    assert(context);
    reader = writer = JS_UNDEFINED;
    JS_NewClassID(rt, &token_class);
    JSClassDef definition = {0};
    definition.class_name = "AArch64SlotOwner";
    definition.finalizer = finalizer;
    assert(JS_NewClass(rt, token_class, &definition) == 0);
    JSValue functions[] = {JS_NewCFunction(context, make, "make", 0),
                           JS_NewCFunction(context, remember, "remember", 2),
                           JS_NewCFunction(context, collect, "collect", 0),
                           JS_NewCFunction(context, checkpoint, "checkpoint", 0)};
    const char *text = "(function(make,remember,collect,checkpoint){var value=make();"
                       "remember(function(){return value;},function(next){value=next;});"
                       "value=value;collect();value=17;checkpoint();return value;})";
    JSValue function =
        checked(JS_Eval(context, text, strlen(text), "<arm-slot-owners>", JS_EVAL_TYPE_GLOBAL));
    QJSArmVMCounts before, after;
    qjs_aarch64_vm_counts(&before);
    for (unsigned i = 0; i < 40; i++) {
        JSValue result = checked(JS_Call(context, function, JS_UNDEFINED, 4, functions));
        int32_t number;
        assert(JS_ToInt32(context, &number, result) == 0);
        if (number != 99)
            fprintf(stderr,
                    "SLOT_OBSERVE pass=%u result=%d born=%u finalized=%u reentry=%u gc=%u\n", i,
                    number, born, finalized, reentered, collected);
        assert(number == 99);
        JS_FreeValue(context, result);
        expect(99);
    }
    qjs_aarch64_vm_counts(&after);
    assert(born == 40 && finalized == 40 && reentered == 40 && collected == 40);
    if (native)
        assert(after.activations > before.activations && after.native_ops > before.native_ops &&
               after.c_steps > before.c_steps);
    else
        assert(after.activations == 0);
    JS_FreeValue(context, reader);
    JS_FreeValue(context, writer);
    for (unsigned i = 0; i < 4; i++)
        JS_FreeValue(context, functions[i]);
    JS_FreeValue(context, function);
    JS_FreeContext(context);
    JS_RunGC(rt);
    JS_FreeRuntime(rt);
    printf(
        "AARCH64_SLOT_OWNERS_OK mode=%s born=%u finalized=%u reentry=%u gc=%u native_ops=%llu c_steps=%llu\n",
        argv[1], born, finalized, reentered, collected, (unsigned long long)after.native_ops,
        (unsigned long long)after.c_steps);
    return 0;
}
