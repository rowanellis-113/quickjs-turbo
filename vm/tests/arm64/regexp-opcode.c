/* Actual native constructor,ownership,unwind,GC/reentry,realm,quota and OOM. MIT. */
#ifdef NDEBUG
#undef NDEBUG
#endif
#include "quickjs.h"
#include "src/arm64/linux/interpreter-observe.h"
#include "interpreter-aarch64-values.h"
#include <assert.h>
#include <execinfo.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "tests/common/native_oom_allocator.h"
struct JSFrameRegisterState;
extern int JS_FrameInterp(struct JSFrameRegisterState *);
extern int JS_FrameInterpRegExp(struct JSFrameRegisterState *);
extern unsigned char qjs_aarch64_vm_end[];
extern unsigned JS_FrameAArch64ScopeProbe(JSRuntime *, uintptr_t *);
extern void qjs_aarch64_vm_quota(JSRuntime *, uintptr_t *);
extern int qjs_aarch64_vm_function_info(JSValueConst, uintptr_t *);
typedef struct {
    Allocator memory;
    JSRuntime *rt;
    JSContext *a, *b;
    JSValue nested;
    unsigned tracking, inside, exercise, fired, observations, reentries, finalized;
    JSClassID token_class;
    int expected_sum;
} State;
static uintptr_t helper_end, slow_start, slow_end;
static unsigned native_short, native_long;
static void observe(State *s)
{
    if (!s->tracking || s->inside)
        return;
    void *frames[64];
    int count = backtrace(frames, 64), helper = 0, vm = 0, slow = 0;
    for (int i = 0; i < count; ++i) {
        uintptr_t ip = (uintptr_t)frames[i];
        helper |= ip > (uintptr_t)JS_FrameInterpRegExp && ip < helper_end;
        vm |= ip > (uintptr_t)JS_FrameInterp && ip < (uintptr_t)qjs_aarch64_vm_end;
        slow |= ip > slow_start && ip < slow_end;
    }
    if (!helper)
        return;
    assert(vm && !slow);
    ++s->observations;
    if (s->exercise && !s->fired) {
        s->fired = 1;
        s->inside = 1;
        uintptr_t before[9], after[9];
        assert(JS_FrameAArch64ScopeProbe(s->rt, before) == 4);
        JS_RunGC(s->rt);
        JSValue v = JS_Call(s->b, s->nested, JS_UNDEFINED, 0, NULL);
        int32_t n = 0;
        assert(!JS_IsException(v) && !JS_ToInt32(s->b, &n, v) && n == 42);
        JS_FreeValue(s->b, v);
        ++s->reentries;
        assert(JS_FrameAArch64ScopeProbe(s->rt, after) == 4 &&
               !memcmp(before, after, sizeof(before)));
        s->inside = 0;
    }
}
static void *hook_malloc(void *p, size_t n)
{
    State *s = p;
    observe(s);
    return functions.js_malloc(&s->memory, n);
}
static void *hook_calloc(void *p, size_t n, size_t k)
{
    State *s = p;
    observe(s);
    return functions.js_calloc(&s->memory, n, k);
}
static void hook_free(void *p, void *v)
{
    State *s = p;
    functions.js_free(&s->memory, v);
}
static void *hook_realloc(void *p, void *v, size_t n)
{
    State *s = p;
    observe(s);
    return functions.js_realloc(&s->memory, v, n);
}
static const JSMallocFunctions allocator = {hook_calloc, hook_malloc, hook_free, hook_realloc,
                                            usable};
static void finalize(JSRuntime *rt, JSValue value)
{
    (void)value;
    State *s = JS_GetRuntimeOpaque(rt);
    ++s->finalized;
}
static JSValue evaluate(JSContext *ctx, const char *text)
{
    JSValue v = JS_Eval(ctx, text, strlen(text), "arm-regexp-opcode", JS_EVAL_TYPE_GLOBAL);
    if (JS_IsException(v)) {
        JSValue error = JS_GetException(ctx);
        const char *message = JS_ToCString(ctx, error);
        fprintf(stderr, "regexp opcode eval:%s\n", message ? message : "<oom>");
        abort();
    }
    return v;
}
static JSValue tap(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)self;
    State *s = JS_GetRuntimeOpaque(JS_GetRuntime(ctx));
    int32_t n = 0;
    assert(argc == 2 && !JS_ToInt32(ctx, &n, argv[0]) && n == s->expected_sum &&
           JS_IsObject(argv[1]));
    return JS_DupValue(ctx, argv[1]);
}
static void setup(State *s)
{
    memset(s, 0, sizeof(*s));
    s->rt = JS_NewRuntime2(&allocator, s);
    assert(s->rt);
    JS_SetRuntimeOpaque(s->rt, s);
    JS_SetMaxStackSize(s->rt, 4 * 1024 * 1024);
    JSClassDef def = {.class_name = "RegexpOpcodeToken", .finalizer = finalize};
    JS_NewClassID(s->rt, &s->token_class);
    assert(!JS_NewClass(s->rt, s->token_class, &def));
    s->a = JS_NewContext(s->rt);
    s->b = JS_NewContext(s->rt);
    assert(s->a && s->b);
    s->nested = evaluate(s->b, "(function(){return 42;})");
    JSValue g = JS_GetGlobalObject(s->a);
    assert(JS_SetPropertyStr(s->a, g, "tap", JS_NewCFunction(s->a, tap, "tap", 2)) >= 0);
    JS_FreeValue(s->a, g);
}
static void teardown(State *s)
{
    assert(!JS_FrameAArch64ScopeProbe(s->rt, NULL));
    JS_FreeValue(s->b, s->nested);
    JS_FreeContext(s->b);
    JS_FreeContext(s->a);
    JS_RunGC(s->rt);
    JS_FreeRuntime(s->rt);
    assert(!s->memory.live && !s->memory.bytes);
}
static JSValue call(State *s, JSValueConst fn, int argc, JSValueConst *argv, unsigned native)
{
    uintptr_t before[2], after[2];
    qjs_aarch64_vm_quota(s->rt, before);
    uint64_t count = qjs_aarch64_vm_regexp_count();
    s->fired = 0;
    s->tracking = 1;
    JSValue v = JS_Call(s->a, fn, JS_UNDEFINED, argc, argv);
    s->tracking = 0;
    assert(qjs_aarch64_vm_regexp_count() - count == native);
    qjs_aarch64_vm_quota(s->rt, after);
    assert(!memcmp(before, after, sizeof(before)));
    return v;
}
static void check_regexp(JSContext *ctx, JSValueConst r)
{
    assert(JS_IsObject(r));
    JSValue v = JS_GetPropertyStr(ctx, r, "source");
    const char *text = JS_ToCString(ctx, v);
    assert(text && !strcmp(text, "a+"));
    JS_FreeCString(ctx, text);
    JS_FreeValue(ctx, v);
    v = JS_GetPropertyStr(ctx, r, "flags");
    text = JS_ToCString(ctx, v);
    assert(text && !strcmp(text, "gi"));
    JS_FreeCString(ctx, text);
    JS_FreeValue(ctx, v);
}
static JSValue generated(State *s, unsigned count, int branch)
{
    size_t capacity = (size_t)count * 8 + 256;
    char *source = malloc(capacity);
    assert(source);
    size_t at = (size_t)sprintf(source, "(function(x,n){var sum=0;%s", branch ? "while(n--){" : "");
    for (unsigned i = 0; i < count; ++i)
        at += (size_t)sprintf(source + at, "sum+=x;");
    at += (size_t)sprintf(source + at, "%sreturn tap(sum,/a+/gi);})", branch ? "}" : "");
    assert(at < capacity);
    JSValue fn = evaluate(s->a, source);
    free(source);
    return fn;
}
static void boundaries(State *s)
{
    uintptr_t info[6];
    JSValue args[2] = {JS_NewInt32(s->a, 3), JS_NewInt32(s->a, 0)};
    JSValue branch = generated(s, 11000, 1);
    s->expected_sum = 0;
    JSValue v = call(s, branch, 2, args, native_long);
    assert(!JS_IsException(v));
    check_regexp(s->a, v);
    JS_FreeValue(s->a, v);
    args[1] = JS_NewInt32(s->a, 2);
    s->expected_sum = 66000;
    v = call(s, branch, 2, args, native_long);
    assert(!JS_IsException(v));
    check_regexp(s->a, v);
    JS_FreeValue(s->a, v);
    assert(qjs_aarch64_vm_function_info(branch, info) && info[4] > 32767 && info[4] <= 65536);
    size_t branch_bytes = info[4];
    if (native_long)
        assert((info[0] & 7) == 1);
    JS_FreeValue(s->a, branch);
    JSValue near = generated(s, 20000, 0);
    s->expected_sum = 60000;
    v = call(s, near, 2, args, native_long);
    assert(!JS_IsException(v));
    check_regexp(s->a, v);
    JS_FreeValue(s->a, v);
    assert(qjs_aarch64_vm_function_info(near, info) && info[4] >= 60000 && info[4] <= 65536);
    size_t near_bytes = info[4];
    if (native_long)
        assert((info[0] & 7) == 3);
    JS_FreeValue(s->a, near);
    JSValue over = generated(s, 24000, 0);
    s->expected_sum = 72000;
    v = call(s, over, 2, args, 0);
    assert(!JS_IsException(v));
    check_regexp(s->a, v);
    JS_FreeValue(s->a, v);
    assert(qjs_aarch64_vm_function_info(over, info) && info[4] > 65536 && !(info[0] & 1));
    size_t over_bytes = info[4];
    JS_FreeValue(s->a, over);
    JSValue limited = generated(s, 2000, 0);
    s->expected_sum = 6000;
    assert(qjs_aarch64_vm_function_info(limited, info) && !(info[0] & 1));
    JS_SetMaxStackSize(s->rt, 8192);
    v = call(s, limited, 2, args, 0);
    if (JS_IsException(v))
        JS_FreeValue(s->a, JS_GetException(s->a));
    else {
        check_regexp(s->a, v);
        JS_FreeValue(s->a, v);
    }
    assert(qjs_aarch64_vm_function_info(limited, info) && !(info[0] & 1));
    JS_SetMaxStackSize(s->rt, 4 * 1024 * 1024);
    JS_FreeValue(s->a, limited);
    JSValue recovery = generated(s, 2000, 0);
    v = call(s, recovery, 2, args, native_long);
    assert(!JS_IsException(v));
    check_regexp(s->a, v);
    JS_FreeValue(s->a, v);
    JS_FreeValue(s->a, recovery);
    printf(
        "AARCH64_REGEXP_BOUNDS_OK branch_bytes=%zu near_bytes=%zu over_bytes=%zu stack_guard_recovery=1 quota_restored=6\n",
        branch_bytes, near_bytes, over_bytes);
}
static void semantics(void)
{
    State s;
    setup(&s);
    JSValue fn = evaluate(s.a, "(function(){return /a+/gi;})"), previous = JS_UNDEFINED;
    QJSArmVMCounts before, after;
    qjs_aarch64_vm_counts(&before);
    for (unsigned i = 0; i < 100; ++i) {
        JSValue v = call(&s, fn, 0, NULL, native_short);
        assert(!JS_IsException(v));
        check_regexp(s.a, v);
        if (JS_IsObject(previous))
            assert(JS_VALUE_GET_PTR(previous) != JS_VALUE_GET_PTR(v));
        JS_FreeValue(s.a, previous);
        previous = v;
    }
    qjs_aarch64_vm_counts(&after);
    if (native_short)
        assert(after.slow_entries == before.slow_entries);
    uintptr_t info[6];
    assert(qjs_aarch64_vm_function_info(fn, info));
    if (native_short)
        assert((info[0] & 7) == 3);
    else
        assert(!(info[0] & 1));
    JS_FreeValue(s.a, previous);
    JS_FreeValue(s.a, fn);
    fn = evaluate(s.b, "(function(){return /a+/gi;})");
    JSValue v = call(&s, fn, 0, NULL, native_short);
    assert(!JS_IsException(v));
    JSValue actual = JS_GetPrototype(s.a, v), wanted = evaluate(s.b, "RegExp.prototype");
    assert(JS_VALUE_GET_PTR(actual) == JS_VALUE_GET_PTR(wanted));
    JS_FreeValue(s.a, actual);
    JS_FreeValue(s.b, wanted);
    JS_FreeValue(s.a, v);
    JS_FreeValue(s.b, fn);
    fn = evaluate(s.a, "(function(p){var keep=p;var r=/a+/gi;return keep;})");
    JSValue token = JS_NewObjectClass(s.a, s.token_class);
    assert(!JS_IsException(token));
    s.exercise = 1;
    v = call(&s, fn, 1, &token, native_short);
    s.exercise = 0;
    assert(!JS_IsException(v) && JS_VALUE_GET_PTR(v) == JS_VALUE_GET_PTR(token));
    assert(s.reentries == (native_short ? 1u : 0u));
    JS_FreeValue(s.a, v);
    JS_FreeValue(s.a, token);
    JS_RunGC(s.rt);
    assert(s.finalized == 1);
    JS_FreeValue(s.a, fn);
    char *source = malloc(64000);
    assert(source);
    size_t at = 0;
    at += (size_t)sprintf(source + at, "(function(x){var sum=0;");
    for (unsigned i = 0; i < 2000; ++i)
        at += (size_t)sprintf(source + at, "sum+=x;");
    at += (size_t)sprintf(source + at, "return tap(sum,/a+/gi);})");
    fn = evaluate(s.a, source);
    free(source);
    JSValue arg = JS_NewInt32(s.a, 3);
    s.expected_sum = 6000;
    for (unsigned i = 0; i < 4; ++i) {
        v = call(&s, fn, 1, &arg, native_long);
        assert(!JS_IsException(v));
        check_regexp(s.a, v);
        JS_FreeValue(s.a, v);
    }
    assert(qjs_aarch64_vm_function_info(fn, info) && info[4] > 4096 && info[4] <= 65536);
    if (native_long)
        assert((info[0] & 7) == 3);
    printf(
        "AARCH64_REGEXP_OPCODE_OK short=%u long=%u long_bytes=%lu unwind=%u reentry=%u finalized=%u quota_restored=106\n",
        native_short, native_long, (unsigned long)info[4], s.observations, s.reentries,
        s.finalized);
    JS_FreeValue(s.a, fn);
    boundaries(&s);
    teardown(&s);
}
static unsigned faults, successes;
static size_t trial(size_t fault)
{
    State s;
    setup(&s);
    JSValue fn = evaluate(s.a, "(function(){return /a+/gi;})");
    for (unsigned i = 0; i < 2; ++i) {
        JSValue v = call(&s, fn, 0, NULL, native_short);
        assert(!JS_IsException(v));
        JS_FreeValue(s.a, v);
    }
    size_t start = s.memory.sequence;
    s.memory.fail_at = fault ? start + fault : 0;
    JSValue v = call(&s, fn, 0, NULL, native_short);
    s.memory.fail_at = 0;
    size_t count = s.memory.sequence - start;
    if (JS_IsException(v)) {
        ++faults;
        JS_FreeValue(s.a, JS_GetException(s.a));
    } else {
        ++successes;
        check_regexp(s.a, v);
        JS_FreeValue(s.a, v);
    }
    v = call(&s, fn, 0, NULL, native_short);
    assert(!JS_IsException(v));
    check_regexp(s.a, v);
    JS_FreeValue(s.a, v);
    JS_FreeValue(s.a, fn);
    teardown(&s);
    return count;
}
int main(int argc, char **argv)
{
    assert(argc == 5);
    helper_end = (uintptr_t)JS_FrameInterpRegExp + (uintptr_t)strtoull(argv[2], NULL, 10);
    slow_start = (uintptr_t)((intptr_t)JS_FrameInterp + (intptr_t)strtoll(argv[3], NULL, 10));
    slow_end = slow_start + (uintptr_t)strtoull(argv[4], NULL, 10);
    native_short = !getenv("QJS_DISABLE_FRAME_REGEXP") && !getenv("QJS_DISABLE_REGISTER_INTERP") &&
                   !getenv("QJS_DISABLE_INTERP_FRAME") && !getenv("QJS_DISABLE_LINUX_ADMISSION");
    native_long = native_short && !getenv("QJS_DISABLE_FRAME_LONG_REGEXP") &&
                  !getenv("QJS_DISABLE_FRAME_LARGE_CODE") &&
                  !getenv("QJS_DISABLE_FRAME_LONG_CODE") &&
                  (ARM_HAS_PROPERTY_IC || getenv("QJS_ENABLE_FRAME_LARGE_CODE"));
    if (!strcmp(argv[1], "oom")) {
        size_t count = trial(0);
        for (size_t i = 1; i <= count + 1; ++i)
            trial(i);
        assert(faults && successes);
        printf("AARCH64_REGEXP_OPCODE_OOM_OK allocations=%zu faults=%u successes=%u live=0\n",
               count, faults, successes);
    } else
        semantics();
    return 0;
}
