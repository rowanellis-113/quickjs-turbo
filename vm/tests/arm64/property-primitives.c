/* Live primitive methods,length and naturally reused builtin views. MIT. */
#ifdef NDEBUG
#undef NDEBUG
#endif
#include "quickjs.h"
#include "src/arm64/linux/interpreter-observe.h"
#include "interpreter-aarch64-values.h"
#include <assert.h>
#include <execinfo.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "tests/common/native_oom_allocator.h"
struct JSFrameRegisterState;
extern JSValue JS_FrameAArch64BuiltinInvoke(struct JSFrameRegisterState *, JSValue *, int, bool);
extern int JS_FrameInterp(struct JSFrameRegisterState *);
extern unsigned char qjs_aarch64_vm_end[];
extern int JS_LinuxBuiltinProbe(JSRuntime *, uintptr_t *);
extern void qjs_aarch64_vm_quota(JSRuntime *, uintptr_t *);
typedef struct {
    Allocator memory;
    JSRuntime *rt;
    JSContext *a, *b;
    JSValue input, coercer, nested, runner;
    uintptr_t first_view;
    unsigned calls, views, unwinds, foreign, getters, tracking;
} State;
static uintptr_t builtin_end, step_start, step_end;
static int registered, primitive, string_live, views_active, hot;
static JSValue eval(JSContext *ctx, const char *text)
{
    JSValue value =
        JS_Eval(ctx, text, strlen(text), "arm-property-primitives", JS_EVAL_TYPE_GLOBAL);
    if (JS_IsException(value)) {
        JSValue error = JS_GetException(ctx);
        const char *message = JS_ToCString(ctx, error);
        fprintf(stderr, "PRIMITIVE_ERROR %s\n", message ? message : "unknown");
        abort();
    }
    return value;
}
static JSValue coerce(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)self;
    (void)argc;
    (void)argv;
    State *s = JS_GetRuntimeOpaque(JS_GetRuntime(ctx));
    uintptr_t words[9];
    int found = JS_LinuxBuiltinProbe(s->rt, words);
    assert(found == views_active);
    if (found) {
        ++s->views;
        assert(words[1] == words[2]);
        unsigned expected = getenv("QJS_DISABLE_NATIVE_FRAME_ARENA")   ? 3
                            : getenv("QJS_DISABLE_NATIVE_FRAME_REUSE") ? 4
                                                                       : 1;
        assert(words[0] == expected);
        if (!s->first_view)
            s->first_view = words[5];
        else
            assert(s->first_view == words[5]);
    }
    if (s->tracking) {
        void *frames[64];
        int total = backtrace(frames, 64), builtin = 0, step = 0, vm = 0;
        for (int i = 0; i < total; i++) {
            uintptr_t ip = (uintptr_t)frames[i];
            builtin |= ip > (uintptr_t)JS_FrameAArch64BuiltinInvoke && ip < builtin_end;
            step |= ip > step_start && ip < step_end;
            vm += ip > (uintptr_t)JS_FrameInterp && ip < (uintptr_t)qjs_aarch64_vm_end;
        }
        if (views_active)
            assert(builtin && !step && vm == 1);
        else
            assert(!builtin);
        s->unwinds += builtin;
    }
    JS_RunGC(s->rt);
    JSValue nested = JS_Call(s->a, s->nested, JS_UNDEFINED, 0, NULL);
    if (JS_IsException(nested))
        return nested;
    int32_t n;
    assert(!JS_ToInt32(s->a, &n, nested) && n == 77);
    JS_FreeValue(s->a, nested);
    // A real allocation inside the live view supplies bounded OOM points.
    char bytes[128];
    memset(bytes, 'x', sizeof(bytes));
    JSValue allocated = JS_NewStringLen(ctx, bytes, sizeof(bytes));
    if (JS_IsException(allocated))
        return allocated;
    JS_FreeValue(ctx, allocated);
    if (s->tracking) {
        if (s->calls == 15)
            JS_SetMaxStackSize(s->rt, 0);
        if (s->calls == 16)
            JS_SetMaxStackSize(s->rt, 4 * 1024 * 1024);
    }
    ++s->calls;
    return JS_NewInt32(ctx, 0);
}
static void setup(State *s)
{
    memset(s, 0, sizeof(*s));
    s->rt = JS_NewRuntime2(&functions, &s->memory);
    assert(s->rt);
    JS_SetRuntimeOpaque(s->rt, s);
    JS_SetMaxStackSize(s->rt, 4 * 1024 * 1024);
    s->a = JS_NewContext(s->rt);
    s->b = JS_NewContext(s->rt);
    assert(s->a && s->b);
    s->input = JS_NewString(s->a, "abcdef");
    s->coercer = JS_NewObject(s->a);
    assert(!JS_IsException(s->input) && !JS_IsException(s->coercer));
    assert(JS_SetPropertyStr(s->a, s->coercer, "valueOf",
                             JS_NewCFunction(s->a, coerce, "viewCoercer", 0)) >= 0);
    s->nested = eval(s->b, "(function(){return 77})");
    s->runner = eval(s->a, "(function(s,start){for(let i=0;i<32;i++)s.slice(start);return 1})");
}
static JSValue run(State *s)
{
    s->first_view = 0;
    JSValue args[] = {s->input, s->coercer};
    return JS_Call(s->a, s->runner, JS_UNDEFINED, 2, args);
}
static void cleanup(State *s)
{
    JS_FreeValue(s->a, s->input);
    JS_FreeValue(s->a, s->coercer);
    JS_FreeValue(s->a, s->runner);
    JS_FreeValue(s->b, s->nested);
    JS_FreeContext(s->b);
    JS_FreeContext(s->a);
    JS_RunGC(s->rt);
    JS_FreeRuntime(s->rt);
    assert(!s->memory.live && !s->memory.bytes);
}
static void integer(JSContext *ctx, JSValueConst function, JSValue value, int wanted)
{
    JSValue result = JS_Call(ctx, function, JS_UNDEFINED, 1, &value);
    int32_t n = 0;
    assert(!JS_IsException(result) && !JS_ToInt32(ctx, &n, result) && n == wanted);
    JS_FreeValue(ctx, result);
}
static JSValue foreign(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)argv;
    State *s = JS_GetRuntimeOpaque(JS_GetRuntime(ctx));
    assert(ctx == s->b && argc == 0);
    double number = 0;
    if (JS_IsNumber(self))
        assert(!JS_ToFloat64(ctx, &number, self));
    else
        assert(JS_IsString(self));
    ++s->foreign;
    return JS_NewInt32(ctx, number == 0 && signbit(number) ? 92 : 91);
}
static JSValue primitive_getter(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)self;
    (void)argv;
    State *s = JS_GetRuntimeOpaque(JS_GetRuntime(ctx));
    assert(ctx == s->b && !argc);
    ++s->getters;
    JS_RunGC(s->rt);
    return JS_NewCFunction(ctx, foreign, "freshGetterMethod", 0);
}
static void accessor(State *s, JSValue proto)
{
    JSAtom atom = JS_NewAtom(s->b, "mark");
    assert(atom);
    assert(JS_DefinePropertyGetSet(s->b, proto, atom,
                                   JS_NewCFunction(s->b, primitive_getter, "primitiveGetter", 0),
                                   JS_UNDEFINED, JS_PROP_CONFIGURABLE) >= 0);
    JS_FreeAtom(s->b, atom);
}
static void lengths_and_realms(State *s)
{
    JSValue length = eval(s->a, "(function(x){return x.length})");
    JSValue array = JS_NewArray(s->a);
    assert(!JS_IsException(array));
    assert(JS_SetPropertyStr(s->a, array, "length", JS_NewInt32(s->a, 1000)) >= 0);
    uint64_t before[8], after[8];
    qjs_aarch64_vm_primitive_counts(before);
    integer(s->a, length, s->input, 6);
    integer(s->a, length, array, 1000);
    qjs_aarch64_vm_primitive_counts(after);
    int native_length = primitive && !getenv("QJS_DISABLE_NATIVE_LENGTH");
    if (native_length)
        assert(after[4] - before[4] == 1 && after[5] - before[5] == 1);
    qjs_aarch64_vm_primitive_counts(before);
    assert(JS_SetPropertyStr(s->a, array, "length", JS_NewFloat64(s->a, 4294967295.0)) >= 0);
    JSValue result = JS_Call(s->a, length, JS_UNDEFINED, 1, &array);
    double number = 0;
    assert(!JS_IsException(result) && !JS_ToFloat64(s->a, &number, result) &&
           number == 4294967295.0);
    qjs_aarch64_vm_primitive_counts(after);
    if (native_length)
        assert(after[5] - before[5] == 1);
    JS_FreeValue(s->a, result);
    JS_FreeValue(s->a, array);
    JSValue wide = JS_NewString(s->a, "\xe6\xb1\x89\xf0\x9f\x98\x80");
    assert(!JS_IsException(wide));
    qjs_aarch64_vm_primitive_counts(before);
    integer(s->a, length, wide, 3);
    qjs_aarch64_vm_primitive_counts(after);
    if (native_length)
        assert(after[4] - before[4] == 1);
    JS_FreeValue(s->a, wide);
    JS_FreeValue(s->a, length);
    JSValue mark = eval(s->a, "(function(x){return x.mark()})");
    JSValue old_string = eval(s->a, "String.prototype"),
            old_number = eval(s->a, "Number.prototype");
    JSValue proto = JS_NewObject(s->b);
    assert(JS_SetPropertyStr(s->b, proto, "mark",
                             JS_NewCFunction(s->b, foreign, "foreignString", 0)) >= 0);
    JS_SetClassProto(s->a, ARM_CONST_JS_CLASS_STRING, proto);
    qjs_aarch64_vm_primitive_counts(before);
    integer(s->a, mark, s->input, 91);
    qjs_aarch64_vm_primitive_counts(after);
    if (string_live)
        assert(after[2] - before[2] == 1);
    accessor(s, proto);
    integer(s->a, mark, s->input, 91);
    JS_SetClassProto(s->a, ARM_CONST_JS_CLASS_STRING, old_string);
    proto = JS_NewObject(s->b);
    assert(JS_SetPropertyStr(s->b, proto, "mark",
                             JS_NewCFunction(s->b, foreign, "foreignNumber", 0)) >= 0);
    JS_SetClassProto(s->a, ARM_CONST_JS_CLASS_NUMBER, proto);
    qjs_aarch64_vm_primitive_counts(before);
    integer(s->a, mark, JS_NewInt32(s->a, 42), 91);
    integer(s->a, mark, JS_NewFloat64(s->a, -0.0), 92);
    qjs_aarch64_vm_primitive_counts(after);
    if (primitive && !getenv("QJS_DISABLE_NUMBER_PROPERTY_FAST"))
        assert(after[3] - before[3] == 2);
    accessor(s, proto);
    integer(s->a, mark, JS_NewInt32(s->a, 42), 91);
    JS_SetClassProto(s->a, ARM_CONST_JS_CLASS_NUMBER, old_number);
    assert(s->foreign == 5 && s->getters == 2);
    JS_FreeValue(s->a, mark);
}
static void semantics(void)
{
    State s;
    setup(&s);
    uint64_t before[8], after[8], p_before[8], p_after[8], ops_before[256], ops_after[256];
    // A fresh context retains lazy AUTOINIT for String.prototype.slice.
    // Exercise that original cold descriptor first,then the SAME caller/body.
    qjs_aarch64_vm_opcode_counts(ops_before);
    JSValue warm = run(&s);
    int32_t warmed = 0;
    assert(!JS_IsException(warm) && !JS_ToInt32(s.a, &warmed, warm) && warmed == 1);
    JS_FreeValue(s.a, warm);
    qjs_aarch64_vm_opcode_counts(ops_after);
    assert(ops_after[ARM_OP_get_field2] - ops_before[ARM_OP_get_field2] ==
           (registered ? (string_live ? 1u : 32u) : 0u));
    s.calls = s.views = s.unwinds = 0;
    s.tracking = 1;
    uintptr_t quota[2], end[2];
    qjs_aarch64_vm_quota(s.rt, quota);
    qjs_aarch64_vm_c_entry_counts(before);
    qjs_aarch64_vm_primitive_counts(p_before);
    qjs_aarch64_vm_opcode_counts(ops_before);
    for (unsigned i = 0; i < 2; i++) {
        JSValue result = run(&s);
        int32_t n = 0;
        assert(!JS_IsException(result) && !JS_ToInt32(s.a, &n, result) && n == 1);
        JS_FreeValue(s.a, result);
    }
    qjs_aarch64_vm_quota(s.rt, end);
    assert(!memcmp(quota, end, sizeof(quota)));
    qjs_aarch64_vm_c_entry_counts(after);
    qjs_aarch64_vm_primitive_counts(p_after);
    qjs_aarch64_vm_opcode_counts(ops_after);
    assert(s.calls == 64 && s.views == (views_active ? 64u : 0u) && s.unwinds == s.views);
    fprintf(stderr,
            "PRIMITIVE_HOT observed=%llu expected=%d string_methods=%llu field_steps=%llu\n",
            (unsigned long long)(after[6] - before[6]), hot,
            (unsigned long long)(p_after[2] - p_before[2]),
            (unsigned long long)(ops_after[ARM_OP_get_field2] - ops_before[ARM_OP_get_field2]));
    if (hot)
        assert(after[6] - before[6] == 62);
    else
        assert(after[6] == before[6]);
    if (string_live)
        assert(p_after[2] - p_before[2] == 64 &&
               ops_after[ARM_OP_get_field2] == ops_before[ARM_OP_get_field2]);
    s.tracking = 0;
    lengths_and_realms(&s);
    printf(
        "AARCH64_PROPERTY_PRIMITIVES_OK methods=64 views=%u hot=%llu unwind=%u gc_reentry=%u foreign=%u getters=%u logical_lengths=4 quota_restored zero_ledgers\n",
        s.views, (unsigned long long)(after[6] - before[6]), s.unwinds, s.calls, s.foreign,
        s.getters);
    cleanup(&s);
}
static size_t fault(size_t fail_at)
{
    State s;
    setup(&s);
    JSValue result = run(&s);
    assert(!JS_IsException(result));
    JS_FreeValue(s.a, result);
    s.memory.sequence = 0;
    s.memory.fail_at = fail_at;
    result = run(&s);
    size_t count = s.memory.sequence;
    s.memory.fail_at = 0;
    if (JS_IsException(result)) {
        JS_FreeValue(s.a, JS_GetException(s.a));
        JS_ResetUncatchableError(s.a);
    } else
        JS_FreeValue(s.a, result);
    if (fail_at)
        assert(s.memory.rejected == 1);
    result = run(&s);
    assert(!JS_IsException(result));
    JS_FreeValue(s.a, result);
    cleanup(&s);
    return count;
}
int main(int argc, char **argv)
{
    assert(argc == 4 || argc == 5);
    builtin_end = (uintptr_t)JS_FrameAArch64BuiltinInvoke + strtoull(argv[1], NULL, 10);
    step_start = (uintptr_t)JS_FrameAArch64BuiltinInvoke + strtoll(argv[2], NULL, 10);
    step_end = step_start + strtoull(argv[3], NULL, 10);
    registered = !getenv("QJS_DISABLE_REGISTER_INTERP") && !getenv("QJS_DISABLE_INTERP_FRAME");
    primitive = registered && !getenv("QJS_DISABLE_AARCH64_PROPERTY_PRIMITIVES");
    string_live = primitive && !getenv("QJS_DISABLE_PROTO_LOAD_CACHE");
    views_active = registered && !getenv("QJS_DISABLE_C_INVOKE") &&
                   !getenv("QJS_DISABLE_SHARED_ENTRY") && !getenv("QJS_DISABLE_DIRECT_HOST_CALL") &&
                   !getenv("QJS_RETAIN_SCOPED_HOST") && !getenv("QJS_DISABLE_NATIVE_SLICE") &&
                   !getenv("QJS_DISABLE_NATIVE_CALL_LINK") &&
                   !getenv("QJS_DISABLE_NATIVE_VM_BRIDGE");
    hot = views_active && string_live && !getenv("QJS_DISABLE_NATIVE_FRAME_ARENA") &&
          !getenv("QJS_DISABLE_NATIVE_FRAME_REUSE") && !getenv("QJS_DISABLE_NATIVE_FRAME_LIFETIME");
    if (argc == 5) {
        assert(!strcmp(argv[4], "oom"));
        size_t count = fault(0);
        assert(count && count < 512);
        for (size_t i = 1; i <= count; i++)
            fault(i);
        printf("AARCH64_PROPERTY_PRIMITIVES_OOM_OK faults=%zu recovery zero_ledgers\n", count);
        return 0;
    }
    semantics();
    return 0;
}
