#ifdef NDEBUG
#undef NDEBUG
#endif
#include "quickjs.h"
#include "interpreter-aarch64-values.h"
#ifdef QJS_AARCH64_VM_INSTRUMENT
#include "src/arm64/linux/interpreter-observe.h"
#endif
#include <assert.h>
#include <execinfo.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

struct JSFrameRegisterState;
extern int JS_FrameInterp(struct JSFrameRegisterState *);
extern unsigned char qjs_aarch64_vm_end[];
static JSContext *caller, *foreign, *expected_context;
static JSValue nested, caller_error, foreign_error;
static int expect_vm, direct, pre_steps, method_case;
#ifdef QJS_AARCH64_VM_INSTRUMENT
static QJSArmVMCounts before;
static uint64_t before_opcodes[256];
#endif
static unsigned observations, coercions, cases;

static JSValue checked(JSContext *ctx, JSValue value)
{
    if (JS_IsException(value)) {
        JSValue error = JS_GetException(ctx);
        const char *text = JS_ToCString(ctx, error);
        fprintf(stderr, "class host: %s\n", text ? text : "<exception>");
        abort();
    }
    return value;
}
static JSValue eval(JSContext *ctx, const char *text)
{
    return checked(ctx, JS_Eval(ctx, text, strlen(text), "<arm-class-host>", JS_EVAL_TYPE_GLOBAL));
}
static void observe(JSContext *ctx)
{
    assert(ctx == expected_context);
#ifdef QJS_AARCH64_VM_INSTRUMENT
    QJSArmVMCounts now;
    qjs_aarch64_vm_counts(&now);
    if (method_case) {
        uint64_t opcodes[256];
        qjs_aarch64_vm_opcode_counts(opcodes);
        fprintf(
            stderr,
            "CLASS_METHOD_ROUTE core_ic=%d steps=%llu property=%llu expected_property=%d direct=%d\n",
            ARM_HAS_PROPERTY_IC, (unsigned long long)(now.slow_entries - before.slow_entries),
            (unsigned long long)(opcodes[ARM_OP_get_field2] - before_opcodes[ARM_OP_get_field2]),
            pre_steps, direct);
        assert(opcodes[ARM_OP_get_field2] - before_opcodes[ARM_OP_get_field2] ==
               (unsigned)pre_steps);
        if (expect_vm)
            assert(now.slow_entries - before.slow_entries == (unsigned)(pre_steps + !direct));
    }
    if (direct) {
        assert(now.class_host - before.class_host == 1);
        // Observe before return cleanup. completed.c_steps also counts typed
        // C boundaries, so only this explicit opcode-entry counter proves it.
        assert(now.slow_entries - before.slow_entries == (unsigned)pre_steps);
    } else {
        assert(now.class_host == before.class_host);
        if (expect_vm)
            assert(now.slow_entries - before.slow_entries > (unsigned)pre_steps);
    }
#endif
    uintptr_t sp;
    __asm__ volatile("mov %0,sp" : "=r"(sp));
    assert((sp & 15) == 0);
    void *frames[48];
    int count = backtrace(frames, 48), found = 0;
    for (int i = 0; i < count; i++)
        found |= (uintptr_t)frames[i] > (uintptr_t)JS_FrameInterp &&
                 (uintptr_t)frames[i] < (uintptr_t)qjs_aarch64_vm_end;
    assert(found == expect_vm);
    JS_RunGC(JS_GetRuntime(ctx));
    JSValue result = checked(caller, JS_Call(caller, nested, JS_UNDEFINED, 0, NULL));
    int32_t n;
    assert(JS_ToInt32(caller, &n, result) == 0 && n == 41);
    JS_FreeValue(caller, result);
    ++observations;
}
static double unary(double a)
{
    observe(foreign);
    return a + 3;
}
static double binary(double a, double b)
{
    observe(foreign);
    return a * 10 + b;
}
static JSValue getter(JSContext *ctx, JSValueConst self)
{
    (void)self;
    observe(ctx);
    return JS_NewInt32(ctx, 101);
}
static JSValue setter(JSContext *ctx, JSValueConst self, JSValueConst value)
{
    (void)self;
    observe(ctx);
    return JS_DupValue(ctx, value);
}
static JSValue getter_magic(JSContext *ctx, JSValueConst self, int magic)
{
    (void)self;
    observe(ctx);
    assert(magic == 17);
    return JS_NewInt32(ctx, magic);
}
static JSValue setter_magic(JSContext *ctx, JSValueConst self, JSValueConst value, int magic)
{
    (void)self;
    observe(ctx);
    assert(magic == 19);
    int32_t n;
    assert(JS_ToInt32(ctx, &n, value) == 0);
    return JS_NewInt32(ctx, n + magic);
}
static JSValue iterator(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv, int *done,
                        int magic)
{
    (void)self;
    observe(ctx);
    assert(argc == 2 && magic == 23);
    *done = 0;
    return JS_DupValue(ctx, argv[0]);
}
static JSValue data(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv, int magic,
                    JSValueConst *slots)
{
    (void)self;
    observe(ctx);
    assert(argc == 2 && magic == 73 && JS_IsUndefined(argv[2]));
    JSValue base = checked(ctx, JS_GetPropertyStr(ctx, slots[0], "base"));
    int32_t a, b;
    assert(JS_ToInt32(ctx, &a, argv[0]) == 0 && JS_ToInt32(ctx, &b, base) == 0);
    JS_FreeValue(ctx, base);
    return JS_NewInt32(ctx, a + b);
}
static JSValue constructor(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)argv;
    observe(ctx);
    assert(argc == 2 && JS_IsUndefined(self));
    return JS_NewInt32(ctx, 29);
}
static JSValue constructor_magic(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv,
                                 int magic)
{
    (void)argv;
    observe(ctx);
    assert(argc == 2 && magic == 43 && JS_IsUndefined(self));
    return JS_NewInt32(ctx, magic);
}
static JSValue class_call(JSContext *ctx, JSValueConst function, JSValueConst self, int argc,
                          JSValueConst *argv, int flags)
{
    (void)function;
    (void)self;
    (void)argv;
    observe(ctx);
    assert(argc == 2 && flags == 0);
    return JS_NewInt32(ctx, 31);
}
static JSValue coerce(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)self;
    (void)argv;
    observe(ctx);
    assert(argc == 0);
    ++coercions;
    return JS_NewInt32(ctx, 2);
}
static void check_case(JSValue driver, JSValue function, JSValue x, JSValue y, int expected,
                       int iterator_result, int throws)
{
    JSValue args[] = {function, x, y};
#ifdef QJS_AARCH64_VM_INSTRUMENT
    qjs_aarch64_vm_counts(&before);
    if (method_case)
        qjs_aarch64_vm_opcode_counts(before_opcodes);
#endif
    JSValue result = JS_Call(caller, driver, JS_UNDEFINED, 3, args);
#ifdef QJS_AARCH64_VM_INSTRUMENT
    QJSArmVMCounts after;
    qjs_aarch64_vm_counts(&after);
    assert(after.class_host - before.class_host == (unsigned)direct);
#endif
    if (throws) {
        assert(JS_IsException(result));
        JSValue error = JS_GetException(caller);
        JSValue name = checked(caller, JS_GetPropertyStr(caller, error, "name"));
        const char *text = JS_ToCString(caller, name);
        assert(text && !strcmp(text, "TypeError"));
        assert(JS_IsInstanceOf(caller, error,
                               expected_context == foreign ? foreign_error : caller_error) == 1);
        JS_FreeCString(caller, text);
        JS_FreeValue(caller, name);
        JS_FreeValue(caller, error);
    } else {
        checked(caller, result);
        if (iterator_result) {
            JSValue done = checked(caller, JS_GetPropertyStr(caller, result, "done"));
            assert(JS_ToBool(caller, done) == 0);
            JS_FreeValue(caller, done);
            JSValue value = checked(caller, JS_GetPropertyStr(caller, result, "value"));
            int32_t n;
            assert(JS_ToInt32(caller, &n, value) == 0 && n == expected);
            JS_FreeValue(caller, value);
        } else {
            double d;
            assert(JS_ToFloat64(caller, &d, result) == 0);
            if (expected == -999)
                assert(isnan(d));
            else
                assert(d == expected);
        }
    }
    JS_FreeValue(caller, result);
    ++cases;
}
int main(int argc, char **argv)
{
    assert(argc == 2);
    direct = !strcmp(argv[1], "native");
    expect_vm = strcmp(argv[1], "register-off") && strcmp(argv[1], "legacy");
    JSRuntime *rt = JS_NewRuntime();
    assert(rt);
    JS_SetMaxStackSize(rt, 4 * 1024 * 1024);
    caller = JS_NewContext(rt);
    foreign = JS_NewContext(rt);
    assert(caller && foreign);
    nested = eval(caller, "(function(){return 41;})");
    caller_error = eval(caller, "TypeError");
    foreign_error = eval(foreign, "TypeError");
    JSValue driver = eval(caller, "(function(f,x,y){return f(x,y);})");
    JSCFunctionType types[8] = {0};
    types[0].f_f = unary;
    types[1].f_f_f = binary;
    types[2].getter = getter;
    types[3].setter = setter;
    types[4].getter_magic = getter_magic;
    types[5].setter_magic = setter_magic;
    types[6].iterator_next = iterator;
    types[7].constructor_or_func = constructor;
    const JSCFunctionEnum protos[] = {JS_CFUNC_f_f,           JS_CFUNC_f_f_f,
                                      JS_CFUNC_getter,        JS_CFUNC_setter,
                                      JS_CFUNC_getter_magic,  JS_CFUNC_setter_magic,
                                      JS_CFUNC_iterator_next, JS_CFUNC_constructor_or_func};
    const int magic[] = {0, 0, 0, 0, 17, 19, 23, 0}, expected[] = {5, 27, 101, 2, 17, 21, 2, 29};
    JSValue functions[13];
    for (unsigned i = 0; i < 8; i++)
        functions[i] = checked(
            foreign, JS_NewCFunction2(foreign, types[i].generic, "typed", 3, protos[i], magic[i]));
    JSValue slot = JS_NewObject(caller);
    assert(!JS_IsException(slot));
    assert(JS_SetPropertyStr(caller, slot, "base", JS_NewInt32(caller, 11)) == 1);
    functions[8] = checked(foreign, JS_NewCFunctionData(foreign, data, 3, 73, 1, &slot));
    JS_FreeValue(caller, slot);
    JSClassID id;
    JS_NewClassID(rt, &id);
    JSClassDef definition = {0};
    definition.class_name = "ArmCallable";
    definition.call = class_call;
    assert(JS_NewClass(rt, id, &definition) == 0);
    functions[9] = checked(caller, JS_NewObjectClass(caller, id));
    functions[10] = checked(
        foreign, JS_NewCFunction2(foreign, constructor, "onlyNew", 3, JS_CFUNC_constructor, 0));
    functions[11] =
        checked(foreign, JS_NewCFunctionMagic(foreign, constructor_magic, "eitherMagic", 3,
                                              JS_CFUNC_constructor_or_func_magic, 43));
    functions[12] =
        checked(foreign, JS_NewCFunctionMagic(foreign, constructor_magic, "onlyNewMagic", 3,
                                              JS_CFUNC_constructor_magic, 47));
    JSValue coercion = JS_NewObject(caller);
    assert(JS_SetPropertyStr(caller, coercion, "valueOf",
                             JS_NewCFunction(foreign, coerce, "valueOf", 0)) == 1);
    for (unsigned pass = 0; pass < 10; pass++) {
        for (unsigned i = 0; i < 13; i++) {
            // Original CData/class owners receive the caller context. Do not
            // silently repair the pinned CData realm TODO as part of this port.
            expected_context = i == 8 || i == 9 ? caller : foreign;
            check_case(driver, functions[i], JS_NewInt32(caller, 2), JS_NewInt32(caller, 7),
                       i < 8     ? expected[i]
                       : i == 8  ? 13
                       : i == 11 ? 43
                                 : 31,
                       i == 6, i == 10 || i == 12);
        }
        expected_context = foreign;
        check_case(driver, functions[0], coercion, JS_UNDEFINED, 5, 0, 0);
        check_case(driver, functions[0], JS_UNDEFINED, JS_UNDEFINED, -999, 0, 0);
        JSValue symbol = checked(caller, eval(caller, "Symbol('coercion')"));
        check_case(driver, functions[0], symbol, JS_UNDEFINED, 0, 0, 1);
        JS_FreeValue(caller, symbol);
    }
    // An active first PIC site learns through C. Without PICs the original
    // independent own-slot/hash path resolves this ordinary data method.
    // Primitive-method OFF does not disable that generic own-data owner.
    JSValue object = JS_NewObject(caller);
    assert(JS_SetPropertyStr(caller, object, "fn", JS_DupValue(caller, functions[0])) == 1);
    JSValue method = eval(caller, "(function(o,x,y){return o.fn(x,y);})");
    int live_method = !ARM_HAS_PROPERTY_IC || getenv("QJS_DISABLE_AARCH64_PROPERTY_IC") ||
                      getenv("QJS_DISABLE_PROPERTY_IC");
    pre_steps = expect_vm && !live_method;
    method_case = 1;
    expected_context = foreign;
    check_case(method, object, JS_NewInt32(caller, 2), JS_NewInt32(caller, 7), 5, 0, 0);
    pre_steps = 0;
    method_case = 0;
    JS_FreeValue(caller, method);
    JS_FreeValue(caller, object);
    JSValue factory = eval(caller, "(function(f){return new Proxy(f,{});})");
    JSValue proxy = checked(caller, JS_Call(caller, factory, JS_UNDEFINED, 1, &functions[0]));
    JS_FreeValue(caller, factory);
    check_case(driver, proxy, JS_NewInt32(caller, 2), JS_NewInt32(caller, 7), 5, 0, 0);
    JS_FreeValue(caller, proxy);
    JSValue bind = checked(caller, JS_GetPropertyStr(caller, functions[0], "bind")),
            self = JS_UNDEFINED;
    JSValue bound = checked(caller, JS_Call(caller, bind, functions[0], 1, &self));
    JS_FreeValue(caller, bind);
    check_case(driver, bound, JS_NewInt32(caller, 2), JS_NewInt32(caller, 7), 5, 0, 0);
    JS_FreeValue(caller, bound);
    JSValue noncallable = JS_NewObject(caller);
    expected_context = caller;
    check_case(driver, noncallable, JS_UNDEFINED, JS_UNDEFINED, 0, 0, 1);
    JS_FreeValue(caller, noncallable);
    factory = eval(caller, "(function(f){return Proxy.revocable(f,{});})");
    JSValue revocable = checked(caller, JS_Call(caller, factory, JS_UNDEFINED, 1, &functions[0]));
    JS_FreeValue(caller, factory);
    proxy = checked(caller, JS_GetPropertyStr(caller, revocable, "proxy"));
    JSValue revoke = checked(caller, JS_GetPropertyStr(caller, revocable, "revoke"));
    JS_FreeValue(caller, checked(caller, JS_Call(caller, revoke, JS_UNDEFINED, 0, NULL)));
    JS_FreeValue(caller, revoke);
    JS_FreeValue(caller, revocable);
    check_case(driver, proxy, JS_UNDEFINED, JS_UNDEFINED, 0, 0, 1);
    JS_FreeValue(caller, proxy);
    JS_FreeValue(caller, coercion);
    for (unsigned i = 0; i < 13; i++)
        JS_FreeValue(caller, functions[i]);
    JS_FreeValue(caller, driver);
    JS_FreeValue(caller, nested);
    JS_FreeValue(caller, caller_error);
    JS_FreeValue(caller, foreign_error);
    JS_FreeContext(foreign);
    JS_FreeContext(caller);
    JS_RunGC(rt);
    JS_FreeRuntime(rt);
    assert(cases == 165 && observations == 143 && coercions == 10);
    printf(
        "AARCH64_CLASS_HOST_OK mode=%s cases=%u observe_gc_reentry_unwind=%u coercions=%u route_observed=%d\n",
        argv[1], cases, observations, coercions,
#ifdef QJS_AARCH64_VM_INSTRUMENT
        1
#else
        0
#endif
    );
    return 0;
}
