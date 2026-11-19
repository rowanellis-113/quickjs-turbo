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
static JSValue retained;
static unsigned finalized;
static const char *phase = "setup";
static void finalizer(JSRuntime *rt, JSValue value)
{
    (void)rt;
    (void)value;
    ++finalized;
}
static JSValue checked(JSContext *ctx, JSValue value)
{
    if (JS_IsException(value)) {
        JSValue error = JS_GetException(ctx);
        const char *text = JS_ToCString(ctx, error);
        fprintf(stderr, "missing window phase=%s: %s\n", phase, text ? text : "<exception>");
        abort();
    }
    return value;
}
static JSValue eval(JSContext *ctx, const char *text)
{
    return checked(ctx,
                   JS_Eval(ctx, text, strlen(text), "<arm-missing-window>", JS_EVAL_TYPE_GLOBAL));
}
static JSValue remember(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)self;
    assert(argc == 1);
    JS_FreeValue(ctx, retained);
    retained = JS_DupValue(ctx, argv[0]);
    JS_RunGC(JS_GetRuntime(ctx));
    return JS_UNDEFINED;
}
static JSValue sink(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)self;
    assert(argc == 400 || argc == 511);
    JS_RunGC(JS_GetRuntime(ctx));
    return JS_DupValue(ctx, argv[argc - 1]);
}
static void same(JSContext *ctx, JSValue result, JSValue expected)
{
    checked(ctx, result);
    assert(JS_IsObject(result) && JS_VALUE_GET_PTR(result) == JS_VALUE_GET_PTR(expected));
    JS_FreeValue(ctx, result);
}
int main(int argc, char **argv)
{
    assert(argc == 2);
    int vm = strcmp(argv[1], "register-off") && strcmp(argv[1], "legacy");
    int native = vm && strcmp(argv[1], "window-off") && strcmp(argv[1], "window-zero");
    JSRuntime *rt = JS_NewRuntime();
    assert(rt);
    JS_SetMaxStackSize(rt, 4 * 1024 * 1024);
    JSContext *ctx = JS_NewContext(rt);
    assert(ctx);
    retained = JS_UNDEFINED;
    JS_NewClassID(rt, &token_class);
    JSClassDef definition = {0};
    definition.class_name = "ArmMissingOwner";
    definition.finalizer = finalizer;
    assert(JS_NewClass(rt, token_class, &definition) == 0);
    JSValue object = checked(ctx, JS_NewObjectClass(ctx, token_class));
    char text[4096];
    size_t used = 0;
    used += snprintf(text + used, sizeof(text) - used, "(function(");
    for (unsigned i = 0; i < 128; i++)
        used += snprintf(text + used, sizeof(text) - used, "%sp%u", i ? "," : "", i);
    used +=
        snprintf(text + used, sizeof(text) - used,
                 "){if(p1!==undefined||p127!==undefined)throw Error('wide padding');return p0;})");
    assert(used < sizeof(text));
    JSValue callees[] = {
        eval(ctx,
             "(function(a,b,c){if(b!==undefined||c!==undefined)throw Error('padding');return a;})"),
        eval(ctx, text)};
    JSValue driver = eval(ctx, "(function(f,a){return f(a);})");
    for (unsigned i = 0; i < 2; i++)
        same(ctx, JS_Call(ctx, callees[i], JS_UNDEFINED, 1, &object), object);
    JS_SetMaxStackSize(rt, 64 * 1024);
    uint64_t calls = 0;
    for (unsigned pass = 0; pass < 40; pass++)
        for (unsigned i = 0; i < 2; i++) {
            JSValue args[] = {callees[i], object};
            QJSArmVMCounts before, after;
            qjs_aarch64_vm_counts(&before);
            same(ctx, JS_Call(ctx, driver, JS_UNDEFINED, 2, args), object);
            qjs_aarch64_vm_counts(&after);
            assert(after.native_calls - before.native_calls == (unsigned)native);
            assert(after.last_window_flags == (unsigned)(native ? 3 : 0));
            calls += after.native_calls - before.native_calls;
            JS_RunGC(rt);
            assert(finalized == 0);
        }
    // The current allocator segment may be a returned descendant's segment,
    // while the missing-argument window belongs to the original root segment.
    // This is a segment-reuse test; give legacy's real C recursion room too.
    JS_SetMaxStackSize(rt, 4 * 1024 * 1024);
    char big_text[12288], cross_text[4096];
    used = 0;
    used += snprintf(big_text + used, sizeof(big_text) - used, "(function(sink){var ");
    for (unsigned i = 0; i < 128; i++)
        used += snprintf(big_text + used, sizeof(big_text) - used, "%sv%u=sink", i ? "," : "", i);
    used += snprintf(big_text + used, sizeof(big_text) - used, ";sink(");
    for (unsigned i = 0; i < 511; i++)
        used += snprintf(big_text + used, sizeof(big_text) - used, "%s0", i ? "," : "");
    used += snprintf(big_text + used, sizeof(big_text) - used, ");if(");
    for (unsigned i = 0; i < 128; i++)
        used +=
            snprintf(big_text + used, sizeof(big_text) - used, "%sv%u!==sink", i ? "||" : "", i);
    used += snprintf(big_text + used, sizeof(big_text) - used,
                     ")throw Error('live locals');return 0;})");
    assert(used < sizeof(big_text));
    JSValue big = eval(ctx, big_text), sink_function = JS_NewCFunction(ctx, sink, "sink", 0);
    QJSArmVMCounts big_before, big_after;
    qjs_aarch64_vm_counts(&big_before);
    JS_FreeValue(ctx, checked(ctx, JS_Call(ctx, big, JS_UNDEFINED, 1, &sink_function)));
    qjs_aarch64_vm_counts(&big_after);
    assert(big_after.activations - big_before.activations == (unsigned)vm);
    used = 0;
    used += snprintf(cross_text + used, sizeof(cross_text) - used,
                     "(function(f,a,big,sink){return sink(");
    for (unsigned i = 0; i < 398; i++)
        used += snprintf(cross_text + used, sizeof(cross_text) - used, "0,");
    used += snprintf(cross_text + used, sizeof(cross_text) - used, "big(sink),f(a));})");
    assert(used < sizeof(cross_text));
    JSValue cross = eval(ctx, cross_text);
    JSValue cross_args[] = {callees[1], object, big, sink_function};
    phase = "cross-segment";
    QJSArmVMCounts cross_before, cross_after;
    qjs_aarch64_vm_counts(&cross_before);
    same(ctx, JS_Call(ctx, cross, JS_UNDEFINED, 4, cross_args), object);
    qjs_aarch64_vm_counts(&cross_after);
    assert(cross_after.native_calls - cross_before.native_calls == (unsigned)native);
    assert(cross_after.last_window_flags == (unsigned)(native ? 7 : 0));
    JS_SetMaxStackSize(rt, 64 * 1024);
    phase = "captured-parent";
    JSValue remember_function = JS_NewCFunction(ctx, remember, "remember", 1);
    JSValue captured = eval(
        ctx,
        "(function(f,a,remember){var live=a;remember(function(){return live;});return f(a);})");
    JSValue capture_args[] = {callees[1], object, remember_function};
    for (unsigned i = 0; i < 20; i++) {
        QJSArmVMCounts before, after;
        qjs_aarch64_vm_counts(&before);
        same(ctx, JS_Call(ctx, captured, JS_UNDEFINED, 3, capture_args), object);
        qjs_aarch64_vm_counts(&after);
        // A local capture table must force the C missing-argument builder.
        assert(after.native_calls == before.native_calls);
        assert(after.last_window_flags == 0);
        same(ctx, JS_Call(ctx, retained, JS_UNDEFINED, 0, NULL), object);
    }
    JSValue recurse =
        eval(ctx, "(function recurse(n,f,a){if(n===0)return f(a);return recurse(n-1,f,a);})");
    JSValue recurse_args[] = {JS_NewInt32(ctx, 1000000), callees[1], object};
    JS_SetMaxStackSize(rt, 48 * 1024);
    JSValue result = JS_Call(ctx, recurse, JS_UNDEFINED, 3, recurse_args);
    assert(JS_IsException(result));
    JS_FreeValue(ctx, JS_GetException(ctx));
    JS_SetMaxStackSize(rt, 64 * 1024);
    for (unsigned i = 0; i < 10; i++) {
        JSValue args[] = {callees[1], object};
        same(ctx, JS_Call(ctx, driver, JS_UNDEFINED, 2, args), object);
    }
    JS_FreeValue(ctx, recurse);
    JS_FreeValue(ctx, captured);
    JS_FreeValue(ctx, remember_function);
    JS_FreeValue(ctx, retained);
    JS_FreeValue(ctx, cross);
    JS_FreeValue(ctx, big);
    JS_FreeValue(ctx, sink_function);
    JS_FreeValue(ctx, driver);
    for (unsigned i = 0; i < 2; i++)
        JS_FreeValue(ctx, callees[i]);
    JS_FreeValue(ctx, object);
    assert(finalized == 1);
    JS_FreeContext(ctx);
    JS_RunGC(rt);
    JS_FreeRuntime(rt);
    printf(
        "AARCH64_MISSING_WINDOW_OK mode=%s calls=80 native_children=%llu captured_parent_fallbacks=20 finalized=%u quota_recovery=10 cross_segment_flags=%llu\n",
        argv[1], (unsigned long long)calls, finalized,
        (unsigned long long)cross_after.last_window_flags);
    return 0;
}
