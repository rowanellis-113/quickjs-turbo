/* Register consumer,ascending finalizers,aliasing,legal GC/reentry and quota. */
#ifdef NDEBUG
#undef NDEBUG
#endif
#include "quickjs.h"
#include "src/arm64/linux/interpreter-observe.h"
#include <assert.h>
#include <execinfo.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "tests/common/native_oom_allocator.h"
struct JSFrameRegisterState;
extern void JS_FrameInterpFree(struct JSFrameRegisterState *, JSContext *, JSValue);
extern int JS_FrameInterp(struct JSFrameRegisterState *);
extern unsigned char qjs_aarch64_vm_end[];
extern unsigned JS_FrameAArch64ScopeProbe(JSRuntime *, uintptr_t *);
extern void qjs_aarch64_vm_quota(JSRuntime *, uintptr_t *);
typedef struct {
    Allocator memory, foreign_memory;
    JSRuntime *rt, *foreign;
    JSContext *a, *b, *foreign_ctx;
    JSClassID token;
    JSValue make, host, nested, prototype;
    unsigned order[8], count, made[100], finalized[100], alias, tracking, host_returned;
    unsigned unwind_free, unwind_step, reentered;
} State;
static uintptr_t free_end, step_start, step_end;
static int native, registered;
static JSValue eval(JSContext *ctx, const char *text)
{
    JSValue value = JS_Eval(ctx, text, strlen(text), "arm-host-return", JS_EVAL_TYPE_GLOBAL);
    if (JS_IsException(value)) {
        JSValue e = JS_GetException(ctx);
        const char *s = JS_ToCString(ctx, e);
        fprintf(stderr, "HOST_RETURN_ERROR %s\n", s ? s : "unknown");
        abort();
    }
    return value;
}
static void finalize(JSRuntime *rt, JSValue value)
{
    State *s = JS_GetRuntimeOpaque(rt);
    uintptr_t raw = (uintptr_t)JS_GetOpaque(value, s->token);
    assert(raw);
    unsigned id = (unsigned)raw - 1;
    assert(id < 100);
    ++s->finalized[id];
    if (!s->tracking)
        return;
    assert(s->count < 8);
    s->order[s->count++] = id;
    if (id == 99 || !s->host_returned)
        return;
    // Passive access only to the runtime currently destroying this object.
    // The pinned embedding contract forbids executing JS from its finalizer.
    // Active GC/JS reentry below uses a separate runtime, as in the accepted
    // cross-runtime finalizer fixture; same-runtime GC runs in host().
    assert(!s->finalized[s->alias ? 2 : 99]);
    void *frames[64];
    int total = backtrace(frames, 64), helper = 0, step = 0, vm = 0;
    for (int i = 0; i < total; i++) {
        uintptr_t ip = (uintptr_t)frames[i];
        helper |= ip > (uintptr_t)JS_FrameInterpFree && ip < free_end;
        step |= ip > step_start && ip < step_end;
        vm += ip > (uintptr_t)JS_FrameInterp && ip < (uintptr_t)qjs_aarch64_vm_end;
    }
    if (native)
        assert(helper && !step && vm == 1);
    else
        assert(!helper);
    s->unwind_free += helper;
    s->unwind_step += step;
    if (registered) {
        uintptr_t scope[9];
        assert(JS_FrameAArch64ScopeProbe(rt, scope) == 4);
        assert(scope[1] == scope[2]);
    }
    JS_RunGC(s->foreign);
    JSValue nested = JS_Call(s->foreign_ctx, s->nested, JS_UNDEFINED, 0, NULL);
    int32_t n = 0;
    assert(!JS_IsException(nested) && !JS_ToInt32(s->foreign_ctx, &n, nested) && n == 77);
    JS_FreeValue(s->foreign_ctx, nested);
    ++s->reentered;
    if (id == 1)
        JS_SetMaxStackSize(rt, 0);
    if (id == 3)
        JS_SetMaxStackSize(rt, 4 * 1024 * 1024);
    assert(!s->finalized[s->alias ? 2 : 99]);
}
static JSValue token(State *s, JSContext *ctx, unsigned id)
{
    JSValue v = JS_NewObjectClass(ctx, s->token);
    if (JS_IsException(v))
        return v;
    JS_SetOpaque(v, (void *)(uintptr_t)(id + 1));
    ++s->made[id];
    return v;
}
static JSValue make(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)self;
    State *s = JS_GetRuntimeOpaque(JS_GetRuntime(ctx));
    int32_t id = 0;
    assert(ctx == s->a && argc == 1 && !JS_ToInt32(ctx, &id, argv[0]) && id >= 0 && id <= 3);
    JSValue value = token(s, ctx, id);
    if (!id && !JS_IsException(value) &&
        JS_SetPropertyStr(ctx, value, "go", JS_DupValue(ctx, s->host)) < 0) {
        JS_FreeValue(ctx, value);
        return JS_EXCEPTION;
    }
    return value;
}
static JSValue host(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    State *s = JS_GetRuntimeOpaque(JS_GetRuntime(ctx));
    assert(ctx == s->b && argc == 3);
    for (unsigned i = 0; i < 3; i++)
        assert((uintptr_t)JS_GetOpaque(argv[i], s->token) == i + 2);
    if (!JS_IsUndefined(self))
        assert((uintptr_t)JS_GetOpaque(self, s->token) == 1);
    JS_RunGC(s->rt);
    JSValue result = s->alias ? JS_DupValue(ctx, argv[1]) : token(s, ctx, 99);
    unsigned result_finalized = s->finalized[s->alias ? 2 : 99];
    if (!s->alias && !JS_IsException(result) &&
        JS_SetPropertyStr(ctx, result, "self", JS_DupValue(ctx, result)) < 0) {
        JS_FreeValue(ctx, result);
        return JS_EXCEPTION;
    }
    // This is a legal same-runtime callback boundary. The owning C result,
    // including its self-cycle or aliased argument, must survive public GC.
    if (!JS_IsException(result)) {
        JS_RunGC(s->rt);
        assert(s->finalized[s->alias ? 2 : 99] == result_finalized);
    }
    s->host_returned = !JS_IsException(result);
    return result;
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
    JS_NewClassID(s->rt, &s->token);
    JSClassDef cls = {0};
    cls.class_name = "HostReturnToken";
    cls.finalizer = finalize;
    assert(!JS_NewClass(s->rt, s->token, &cls));
    JSValue pa = JS_NewObject(s->a), pb = JS_NewObject(s->b);
    assert(!JS_IsException(pa) && !JS_IsException(pb));
    s->prototype = JS_DupValue(s->b, pb);
    JS_SetClassProto(s->a, s->token, pa);
    JS_SetClassProto(s->b, s->token, pb);
    s->make = JS_NewCFunction(s->a, make, "makeReturnToken", 1);
    s->host = JS_NewCFunction(s->b, host, "foreignReturnHost", 3);
    s->foreign = JS_NewRuntime2(&functions, &s->foreign_memory);
    assert(s->foreign);
    JS_SetMaxStackSize(s->foreign, 4 * 1024 * 1024);
    s->foreign_ctx = JS_NewContext(s->foreign);
    assert(s->foreign_ctx);
    s->nested = eval(s->foreign_ctx, "(function(){return 77})");
}
static void cleanup(State *s)
{
    s->tracking = 0;
    JS_FreeValue(s->a, s->make);
    JS_FreeValue(s->b, s->host);
    JS_FreeValue(s->foreign_ctx, s->nested);
    JS_FreeValue(s->b, s->prototype);
    JS_FreeContext(s->foreign_ctx);
    JS_FreeRuntime(s->foreign);
    JS_FreeContext(s->b);
    JS_FreeContext(s->a);
    JS_FreeRuntime(s->rt);
    assert(!s->memory.live && !s->memory.bytes);
    assert(!s->foreign_memory.live && !s->foreign_memory.bytes);
}
static void trial(State *s, JSValue actor, unsigned method, unsigned alias)
{
    memset(s->finalized, 0, sizeof(s->finalized));
    s->count = 0;
    s->alias = alias;
    s->host_returned = 0;
    s->tracking = 1;
    uintptr_t quota[2], after[2];
    qjs_aarch64_vm_quota(s->rt, quota);
    JSValue args[] = {s->make, s->host};
    uint64_t before[4], now[4];
    qjs_aarch64_vm_host_return_counts(before);
    JSValue result = JS_Call(s->a, actor, JS_UNDEFINED, 2, args);
    assert(!JS_IsException(result));
    qjs_aarch64_vm_quota(s->rt, after);
    assert(!memcmp(quota, after, sizeof(quota)));
    unsigned expected[4], length = 0;
    if (method)
        expected[length++] = 0;
    expected[length++] = 1;
    if (!alias)
        expected[length++] = 2;
    expected[length++] = 3;
    assert(s->count == length && !memcmp(s->order, expected, length * sizeof(*expected)));
    assert((uintptr_t)JS_GetOpaque(result, s->token) == (alias ? 3 : 100));
    if (!alias) {
        JSValue prototype = JS_GetPrototype(s->a, result);
        assert(JS_VALUE_GET_PTR(prototype) == JS_VALUE_GET_PTR(s->prototype));
        JS_FreeValue(s->a, prototype);
        JSValue self = JS_GetPropertyStr(s->a, result, "self");
        assert(JS_VALUE_GET_PTR(self) == JS_VALUE_GET_PTR(result));
        JS_FreeValue(s->a, self);
    }
    qjs_aarch64_vm_host_return_counts(now);
    if (native)
        assert(now[0] - before[0] == 4 + method && now[2] - before[2] == length &&
               now[3] == before[3]);
    else
        assert(now[0] == before[0] && now[2] == before[2]);
    s->tracking = 0;
    JS_FreeValue(s->a, result);
    JS_RunGC(s->rt);
    for (unsigned id = 1; id <= 3; id++)
        assert(s->finalized[id] == 1);
    assert(s->finalized[0] == method && s->finalized[99] == !alias);
}
static size_t fault(size_t fail_at)
{
    State s;
    setup(&s);
    JSValue actor =
        eval(s.a, "(function(make,host){let result=host(make(1),make(2),make(3));return result})");
    trial(&s, actor, 0, 0);
    memset(s.made, 0, sizeof(s.made));
    memset(s.finalized, 0, sizeof(s.finalized));
    s.tracking = 0;
    s.host_returned = 0;
    s.memory.sequence = 0;
    s.memory.fail_at = fail_at;
    JSValue args[] = {s.make, s.host};
    JSValue value = JS_Call(s.a, actor, JS_UNDEFINED, 2, args);
    size_t count = s.memory.sequence;
    s.memory.fail_at = 0;
    if (JS_IsException(value)) {
        JS_FreeValue(s.a, JS_GetException(s.a));
        JS_ResetUncatchableError(s.a);
    } else
        JS_FreeValue(s.a, value);
    if (fail_at)
        assert(s.memory.rejected == 1);
    JS_RunGC(s.rt);
    for (unsigned i = 0; i < 100; i++)
        assert(s.made[i] == s.finalized[i]);
    value = JS_Call(s.a, actor, JS_UNDEFINED, 2, args);
    assert(!JS_IsException(value));
    JS_FreeValue(s.a, value);
    JS_RunGC(s.rt);
    for (unsigned i = 0; i < 100; i++)
        assert(s.made[i] == s.finalized[i]);
    JS_FreeValue(s.a, actor);
    cleanup(&s);
    return count;
}
int main(int argc, char **argv)
{
    assert(argc == 4 || argc == 5);
    free_end = (uintptr_t)JS_FrameInterpFree + strtoull(argv[1], NULL, 10);
    step_start = (uintptr_t)JS_FrameInterpFree + strtoll(argv[2], NULL, 10);
    step_end = step_start + strtoull(argv[3], NULL, 10);
    registered = !getenv("QJS_DISABLE_REGISTER_INTERP") && !getenv("QJS_DISABLE_INTERP_FRAME");
    native = registered && !getenv("QJS_DISABLE_AARCH64_HOST_RETURN");
    native = native && !getenv("QJS_DISABLE_DIRECT_HOST_CALL");
    if (argc == 5) {
        assert(!strcmp(argv[4], "oom"));
        size_t count = fault(0);
        assert(count && count < 256);
        for (size_t i = 1; i <= count; i++)
            fault(i);
        printf("AARCH64_C_RETURN_OOM_OK faults=%zu exact-made-finalized zero-ledgers recovery\n",
               count);
        return 0;
    }
    State s;
    setup(&s);
    JSValue actors[] = {
        eval(s.a, "(function(make,host){let result=host(make(1),make(2),make(3));return result})"),
        eval(s.a, "(function(make,host){return host(make(1),make(2),make(3))})"),
        eval(s.a,
             "(function(make,host){let result=make(0).go(make(1),make(2),make(3));return result})"),
        eval(s.a, "(function(make,host){return make(0).go(make(1),make(2),make(3))})")};
    for (unsigned pass = 0; pass < 8; pass++)
        for (unsigned i = 0; i < 4; i++)
            for (unsigned alias = 0; alias < 2; alias++)
                trial(&s, actors[i], i >= 2, alias);
    for (unsigned i = 0; i < 4; i++)
        JS_FreeValue(s.a, actors[i]);
    uint64_t counts[4], publication[17];
    qjs_aarch64_vm_host_return_counts(counts);
    qjs_aarch64_vm_publication_extended_counts(publication);
    if (native)
        assert(s.unwind_free == 192 && !s.unwind_step && counts[2] == 192);
    else
        assert(!s.unwind_free);
    if (native && !getenv("QJS_DISABLE_DEFERRED_FRAME_PUBLISH"))
        assert(publication[16] == 192);
    printf(
        "AARCH64_C_RETURN_OK trials=64 native=%d finalizer_unwind=%u reentry=%u regular=%llu tail=%llu free=%llu fallback=%llu quota_restored=64\n",
        native, s.unwind_free, s.reentered, (unsigned long long)counts[0],
        (unsigned long long)counts[1], (unsigned long long)counts[2],
        (unsigned long long)counts[3]);
    cleanup(&s);
    return 0;
}
