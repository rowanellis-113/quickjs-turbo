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

static JSClassID token_class;
static unsigned born, finalized;
static uintptr_t host_sp;
static void finalizer(JSRuntime *rt, JSValue value)
{
    (void)rt;
    (void)value;
    ++finalized;
}
static JSValue probe(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)ctx;
    (void)self;
    (void)argc;
    (void)argv;
    host_sp = (uintptr_t)__builtin_frame_address(0);
    return JS_NewInt32(ctx, 37);
}
static JSValue checked(JSContext *ctx, JSValue value)
{
    if (JS_IsException(value)) {
        JSValue error = JS_GetException(ctx);
        const char *text = JS_ToCString(ctx, error);
        fprintf(stderr, "owned args: %s\n", text ? text : "<exception>");
        abort();
    }
    return value;
}
static JSValue eval(JSContext *ctx, const char *text)
{
    return checked(ctx, JS_Eval(ctx, text, strlen(text), "<arm-owned-args>", JS_EVAL_TYPE_GLOBAL));
}
static void number(JSContext *ctx, JSValue result, int expected)
{
    int32_t n;
    checked(ctx, result);
    assert(JS_ToInt32(ctx, &n, result) == 0 && n == expected);
    JS_FreeValue(ctx, result);
}
int main(int argc, char **argv)
{
    assert(argc == 2);
    int vm = strcmp(argv[1], "register-off") && strcmp(argv[1], "legacy");
    int owned_off = !strcmp(argv[1], "owned-off") || !strcmp(argv[1], "owned-zero");
    JSRuntime *rt = JS_NewRuntime();
    assert(rt);
    JS_SetMaxStackSize(rt, 4 * 1024 * 1024);
    JSContext *ctx = JS_NewContext(rt);
    assert(ctx);
    JS_NewClassID(rt, &token_class);
    JSClassDef definition = {0};
    definition.class_name = "AArch64OwnedArg";
    definition.finalizer = finalizer;
    assert(JS_NewClass(rt, token_class, &definition) == 0);
    JSValue scalar = eval(ctx, "(function(a,b){a=b;b=3;return a+b;})");
    JSValue heap = eval(ctx, "(function(a,b){a=b;return a;})");
    JSValue drivers[] = {eval(ctx, "(function(f,a,b,c){var value=f(a,b,c);return value;})"),
                         eval(ctx, "(function(f,a,b,c){return f(a,b,c);})")};
    JSValue initial[] = {JS_NewInt32(ctx, 4), JS_NewInt32(ctx, 6)};
    // Prepare through ordinary API execution; never modify private metadata.
    number(ctx, JS_Call(ctx, scalar, JS_UNDEFINED, 2, initial), 9);
    number(ctx, JS_Call(ctx, heap, JS_UNDEFINED, 2, initial), 6);
    uint64_t native_calls = 0;
    for (unsigned pass = 0; pass < 40; pass++)
        for (unsigned kind = 0; kind < 2; kind++) {
            JSValue a = JS_NewObjectClass(ctx, token_class),
                    b = JS_NewObjectClass(ctx, token_class),
                    extra = JS_NewObjectClass(ctx, token_class);
            assert(!JS_IsException(a) && !JS_IsException(b) && !JS_IsException(extra));
            born += 3;
            JSValue values[] = {kind ? heap : scalar, kind ? a : initial[0], kind ? b : initial[1],
                                extra};
            QJSArmVMCounts before, after;
            qjs_aarch64_vm_counts(&before);
            JSValue result = checked(ctx, JS_Call(ctx, drivers[pass % 2], JS_UNDEFINED, 4, values));
            qjs_aarch64_vm_counts(&after);
            if (kind) {
                assert(JS_VALUE_GET_PTR(result) == JS_VALUE_GET_PTR(b));
                JS_FreeValue(ctx, result);
            } else
                number(ctx, result, 9);
            if (vm && !owned_off)
                assert(after.native_calls - before.native_calls == 1);
            else
                assert(after.native_calls == before.native_calls);
            native_calls += after.native_calls - before.native_calls;
            // The child writes its copies. The caller's owning values are intact.
            if (kind)
                assert(JS_VALUE_GET_PTR(values[1]) == JS_VALUE_GET_PTR(a));
            else
                assert(JS_VALUE_GET_INT(values[1]) == 4 && JS_VALUE_GET_INT(values[2]) == 6);
            JS_FreeValue(ctx, a);
            JS_FreeValue(ctx, b);
            JS_FreeValue(ctx, extra);
            assert(finalized == born);
        }
    JSValue callback = JS_NewCFunction(ctx, probe, "probe", 0);
    JSValue recurse = eval(
        ctx, "(function recurse(n,probe){if(n===0)return probe();n=n-1;return recurse(n,probe);})");
    JSValue args[] = {JS_NewInt32(ctx, 0), callback};
    number(ctx, JS_Call(ctx, recurse, JS_UNDEFINED, 2, args), 37);
    uintptr_t shallow_sp = host_sp;
    args[0] = JS_NewInt32(ctx, 120);
    QJSArmVMCounts before, after;
    qjs_aarch64_vm_counts(&before);
    number(ctx, JS_Call(ctx, recurse, JS_UNDEFINED, 2, args), 37);
    qjs_aarch64_vm_counts(&after);
    uintptr_t delta = shallow_sp > host_sp ? shallow_sp - host_sp : host_sp - shallow_sp;
    if (vm && !owned_off)
        assert(after.native_calls - before.native_calls >= 100);
    else
        assert(after.native_calls == before.native_calls);
    if (strcmp(argv[1], "legacy"))
        assert(delta == 0);
    else
        assert(delta > 0);
    if (vm)
        assert(after.activations - before.activations == 1);
    else
        assert(after.activations == 0);
    // Missing arguments and captured formals keep their original builders.
    JSValue result = checked(ctx, JS_Call(ctx, scalar, JS_UNDEFINED, 1, initial));
    double d;
    assert(JS_ToFloat64(ctx, &d, result) == 0 && d != d);
    JS_FreeValue(ctx, result);
    JSValue captured = eval(ctx, "(function outer(a){return function(){a=a+1;return a;};})(4)");
    number(ctx, JS_Call(ctx, captured, JS_UNDEFINED, 0, NULL), 5);
    JS_FreeValue(ctx, captured);
    JS_FreeValue(ctx, recurse);
    JS_FreeValue(ctx, callback);
    for (unsigned i = 0; i < 2; i++)
        JS_FreeValue(ctx, drivers[i]);
    JS_FreeValue(ctx, scalar);
    JS_FreeValue(ctx, heap);
    JS_FreeContext(ctx);
    JS_RunGC(rt);
    JS_FreeRuntime(rt);
    assert(finalized == born);
    printf(
        "AARCH64_OWNED_ARGS_OK mode=%s born=%u finalized=%u native_calls=%llu recursive_calls=%llu host_sp_delta=%llu\n",
        argv[1], born, finalized, (unsigned long long)native_calls,
        (unsigned long long)(after.native_calls - before.native_calls), (unsigned long long)delta);
    return 0;
}
