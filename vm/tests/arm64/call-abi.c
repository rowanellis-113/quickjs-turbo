/* Public-header ABI fixture; no interpreter-private state or VM admission. */
#include "quickjs.h"
#include <execinfo.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

_Static_assert(sizeof(void *) == 8 && sizeof(JSValue) == 16, "LP64 JSValue required");
_Static_assert(_Alignof(JSValue) == 8, "Measure a different aggregate ABI explicitly");
#include "src/arm64/linux/abi/call-abi.h"
extern int qjs_aarch64_test_saved(JSCFunction *, JSContext *, JSValueConst, int, JSValueConst *);
extern char qjs_aarch64_call_generic_end[], qjs_aarch64_test_saved_end[],
    qjs_aarch64_call_internal_end[];
static JSContext *expected_ctx;
static unsigned trace_count;
static int require_assembly;
extern __typeof__(qjs_aarch64_call_generic) reference_generic;
extern __typeof__(qjs_aarch64_call_magic) reference_magic;
extern __typeof__(qjs_aarch64_call_data) reference_data;
extern __typeof__(qjs_aarch64_call_double) reference_float;
extern __typeof__(qjs_aarch64_call_internal) reference_stack;
#define CHECK(x)                                                                                   \
    do {                                                                                           \
        if (!(x)) {                                                                                \
            fprintf(stderr, "ABI_CHECK_FAILED line=%d: %s\n", __LINE__, #x);                       \
            exit(1);                                                                               \
        }                                                                                          \
    } while (0)

static void check_arguments(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    int32_t integer;
    double number;
    uintptr_t physical_sp;
    __asm__ volatile("mov %0, sp" : "=r"(physical_sp));
    CHECK((physical_sp & 15) == 0);
    CHECK(ctx == expected_ctx && argc == 2);
    CHECK(!JS_ToInt32(ctx, &integer, self) && integer == 123);
    CHECK(!JS_ToInt32(ctx, &integer, argv[0]) && integer == 7);
    CHECK(!JS_ToFloat64(ctx, &number, argv[1]) && number == 0.25);
}

__attribute__((noinline)) static void trace_bridge(int need_saved)
{
    if (!require_assembly)
        return;
    void *frames[32];
    int count = backtrace(frames, 32), generic = 0, saved = 0, stack = 0;
    CHECK(count >= 3);
    for (int i = 0; i < count; i++) {
        uintptr_t pc = (uintptr_t)frames[i];
        generic |= pc > (uintptr_t)qjs_aarch64_call_generic &&
                   pc < (uintptr_t)qjs_aarch64_call_generic_end;
        saved |=
            pc > (uintptr_t)qjs_aarch64_test_saved && pc < (uintptr_t)qjs_aarch64_test_saved_end;
        stack |= pc > (uintptr_t)qjs_aarch64_call_internal &&
                 pc < (uintptr_t)qjs_aarch64_call_internal_end;
    }
    CHECK(need_saved == 2 ? stack : generic && (!need_saved || saved));
    trace_count++;
}

static JSValue generic(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    check_arguments(ctx, self, argc, argv);
    trace_bridge(0);
    JSValue nested = JS_Eval(ctx, "(()=>41+1)()", 12, "abi-reentry.js", JS_EVAL_TYPE_GLOBAL);
    int32_t number;
    CHECK(!JS_IsException(nested) && !JS_ToInt32(ctx, &number, nested) && number == 42);
    JS_FreeValue(ctx, nested);
    JSValue value = JS_NewObject(ctx);
    CHECK(!JS_IsException(value));
    CHECK(JS_SetPropertyStr(ctx, value, "sum", JS_NewFloat64(ctx, 130.25)) >= 0);
    JS_RunGC(JS_GetRuntime(ctx));
    return value;
}

static JSValue magic(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv, int code)
{
    check_arguments(ctx, self, argc, argv);
    CHECK(code == 789);
    return JS_NewInt32(ctx, code + argc + 123);
}

static JSValue data(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv, int code,
                    JSValueConst *values)
{
    int32_t integer;
    check_arguments(ctx, self, argc, argv);
    CHECK(code == 456 && !JS_ToInt32(ctx, &integer, values[0]) && integer == 9);
    const char *text = JS_ToCString(ctx, values[1]);
    CHECK(text && !strcmp(text, "capture"));
    JS_FreeCString(ctx, text);
    return JS_NewString(ctx, "data-bridge");
}

static JSValue primitive(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    check_arguments(ctx, self, argc, argv);
    trace_bridge(1);
    return JS_NewInt32(ctx, 42);
}

static double twice(double value)
{
    return value * 2;
}

static JSValue stack_callback(JSContext *ctx, JSValueConst func, JSValueConst self,
                              JSValueConst new_target, int argc, JSValueConst *argv, int flags)
{
    double number;
    check_arguments(ctx, self, argc, argv);
    CHECK(JS_IsObject(func) && !JS_ToFloat64(ctx, &number, new_target) && number == 1.5);
    CHECK(flags == -765);
    trace_bridge(2);
    return JS_NewString(ctx, "stack-bridge");
}

_Static_assert(__builtin_types_compatible_p(__typeof__(stack_callback), QJSAArch64CoreCall),
               "Core call signature changed");

static void exercise(JSContext *ctx, JSValue self, JSValue *argv, JSValue *captures, int reference)
{
    require_assembly = !reference;
    __typeof__(&qjs_aarch64_call_generic) call_generic =
        reference ? reference_generic : qjs_aarch64_call_generic;
    __typeof__(&qjs_aarch64_call_magic) call_magic =
        reference ? reference_magic : qjs_aarch64_call_magic;
    __typeof__(&qjs_aarch64_call_data) call_data =
        reference ? reference_data : qjs_aarch64_call_data;
    __typeof__(&qjs_aarch64_call_double) call_float =
        reference ? reference_float : qjs_aarch64_call_double;
    __typeof__(&qjs_aarch64_call_internal) call_stack =
        reference ? reference_stack : qjs_aarch64_call_internal;
    JSValue result = call_generic(generic, ctx, self, 2, argv);
    CHECK(JS_IsObject(result));
    JSValue sum = JS_GetPropertyStr(ctx, result, "sum");
    double number;
    CHECK(!JS_ToFloat64(ctx, &number, sum) && number == 130.25);
    JS_FreeValue(ctx, sum);
    JS_FreeValue(ctx, result);
    result = call_magic(magic, ctx, self, 2, argv, 789);
    int32_t integer;
    CHECK(!JS_ToInt32(ctx, &integer, result) && integer == 914);
    JS_FreeValue(ctx, result);
    result = call_data(data, ctx, self, 2, argv, 456, captures);
    const char *text = JS_ToCString(ctx, result);
    CHECK(text && !strcmp(text, "data-bridge"));
    JS_FreeCString(ctx, text);
    JS_FreeValue(ctx, result);
    CHECK(call_float(twice, 3.25) == 6.5);
    CHECK(signbit(call_float(twice, -0.0)));
    CHECK(isnan(call_float(twice, NAN)));
    CHECK(isinf(call_float(twice, INFINITY)));
    JSValue function = JS_NewObject(ctx);
    result =
        call_stack(stack_callback, ctx, function, self, JS_NewFloat64(ctx, 1.5), 2, argv, -765);
    text = JS_ToCString(ctx, result);
    CHECK(text && !strcmp(text, "stack-bridge"));
    JS_FreeCString(ctx, text);
    JS_FreeValue(ctx, result);
    JS_FreeValue(ctx, function);
}

int main(void)
{
    JSRuntime *rt = JS_NewRuntime();
    CHECK(rt);
    JSContext *ctx = JS_NewContext(rt);
    CHECK(ctx);
    expected_ctx = ctx;
    JSValue self = JS_NewInt32(ctx, 123), argv[] = {JS_NewInt32(ctx, 7), JS_NewFloat64(ctx, 0.25)};
    JSValue captures[] = {JS_NewInt32(ctx, 9), JS_NewString(ctx, "capture")};
    exercise(ctx, self, argv, captures, 0);
    exercise(ctx, self, argv, captures, 1);
    require_assembly = 1;
    CHECK(qjs_aarch64_test_saved(primitive, ctx, self, 2, argv) == 0);
    CHECK(trace_count == 3);
    JS_FreeValue(ctx, captures[1]);
    JS_FreeContext(ctx);
    JS_FreeRuntime(rt);
    printf(
        "AARCH64_CALL_ABI_OK JSValue=16 align=8 routes=5 reference=5 saved=10 unwind=3 reentry=2\n");
    return 0;
}
