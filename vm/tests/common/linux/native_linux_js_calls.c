/* Owned missing argv, readonly escaping cells, mutable descendants and realm
 * reentry. The private hook observes real typed frames; ASM proof is separate. */
#include "quickjs.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "../native_oom_allocator.h"

extern int JS_LinuxJSFrameProbe(JSRuntime *, uintptr_t *);
typedef struct {
    JSContext *caller;
    JSValue nested;
    unsigned calls, matched, owned, borrowed, readonly_captures, mutable_captures, reentries;
} Fixture;

static JSValue eval(JSContext *ctx, const char *text)
{
    JSValue v = JS_Eval(ctx, text, strlen(text), "native-js-calls", JS_EVAL_TYPE_GLOBAL);
    if (JS_IsException(v)) {
        JSValue e = JS_GetException(ctx);
        const char *s = JS_ToCString(ctx, e);
        fprintf(stderr, "JS CALL ERROR %s\n", s ? s : "unknown");
        JS_FreeCString(ctx, s);
        JS_FreeValue(ctx, e);
        abort();
    }
    return v;
}

static JSValue inspect(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)self;
    Fixture *f = JS_GetContextOpaque(ctx);
    int32_t scenario;
    assert(argc == 2 && JS_IsObject(argv[0]) && JS_ToInt32(ctx, &scenario, argv[1]) == 0);
    uintptr_t words[10];
    ++f->calls;
    if (JS_LinuxJSFrameProbe(JS_GetRuntime(ctx), words) &&
        words[8] == (uintptr_t)JS_VALUE_GET_PTR(argv[0])) {
        unsigned kind = (unsigned)words[5] & 7;
        ++f->matched;
        if (words[0] == words[1]) {
            ++f->owned;
            assert(words[2] <= words[3]);
        } else {
            ++f->borrowed;
            assert(words[2] == 0);
        }
        if (scenario == 2) {
            assert(kind == (getenv("QJS_DISABLE_FRAME_CAPTURED_READONLY") ? 5u : 7u));
            ++f->readonly_captures;
        }
        if (scenario == 3 || scenario == 4 || scenario == 5) {
            assert(kind == 5);
            ++f->mutable_captures;
        }
    }
    JS_RunGC(JS_GetRuntime(ctx));
    JSValue nested = JS_Call(f->caller, f->nested, JS_UNDEFINED, 0, NULL);
    int32_t n;
    assert(!JS_IsException(nested) && JS_ToInt32(f->caller, &n, nested) == 0 && n == 31);
    JS_FreeValue(f->caller, nested);
    ++f->reentries;
    JS_SetMaxStackSize(JS_GetRuntime(ctx), (f->calls & 1) ? 0 : 1024 * 1024);
    return JS_UNDEFINED;
}

static void check_result(JSContext *ctx, JSValue result, JSValueConst seed, int closure,
                         int changed)
{
    assert(!JS_IsException(result));
    if (closure) {
        JSValue next = JS_Call(ctx, result, JS_UNDEFINED, 0, NULL);
        JS_FreeValue(ctx, result);
        result = next;
        assert(!JS_IsException(result));
    }
    assert(JS_IsObject(result));
    if (changed) {
        JSValue id = JS_GetPropertyStr(ctx, result, "id");
        int32_t n;
        assert(JS_ToInt32(ctx, &n, id) == 0 && n == 99);
        JS_FreeValue(ctx, id);
    } else
        assert(JS_VALUE_GET_PTR(result) == JS_VALUE_GET_PTR(seed));
    JS_FreeValue(ctx, result);
}

static JSValue make_target(JSContext *ctx, int formals, int scenario)
{
    char text[8192];
    size_t used = (size_t)snprintf(text, sizeof(text), "(function(");
    for (int i = 0; i < formals; i++)
        used += (size_t)snprintf(text + used, sizeof(text) - used, "%sa%d", i ? "," : "", i);
    used += (size_t)snprintf(text + used, sizeof(text) - used, "){ ");
    if (scenario == 0)
        used +=
            (size_t)snprintf(text + used, sizeof(text) - used,
                             "let value=a0;a0=undefined;inspect(currentTarget,0);return value;");
    else if (scenario == 1)
        used += (size_t)snprintf(text + used, sizeof(text) - used,
                                 "inspect(currentTarget,1);return a0;");
    else if (scenario == 2)
        used += (size_t)snprintf(text + used, sizeof(text) - used,
                                 "let escaped=()=>a0;inspect(currentTarget,2);return escaped;");
    else if (scenario == 3)
        used += (size_t)snprintf(
            text + used, sizeof(text) - used,
            "let change=()=>{a0={id:99}};change();inspect(currentTarget,3);return()=>a0;");
    else if (scenario == 4)
        used += (size_t)snprintf(
            text + used, sizeof(text) - used,
            "let neverCalled=()=>{a0={id:99}};inspect(currentTarget,4);return()=>a0;");
    else if (scenario == 5) {
        for (int i = 0; i < 65; i++)
            used += (size_t)snprintf(text + used, sizeof(text) - used, "function depth%d(){", i);
        used += (size_t)snprintf(text + used, sizeof(text) - used, "return a0;");
        for (int i = 0; i < 65; i++)
            used += (size_t)snprintf(text + used, sizeof(text) - used, "}");
        used += (size_t)snprintf(text + used, sizeof(text) - used,
                                 "inspect(currentTarget,5);return()=>a0;");
    } else
        used += (size_t)snprintf(text + used, sizeof(text) - used,
                                 "inspect(currentTarget,6);return this.marker===42?a0:undefined;");
    used += (size_t)snprintf(text + used, sizeof(text) - used, "})");
    assert(used < sizeof(text));
    return eval(ctx, text);
}

static void run_target(JSContext *caller, JSContext *realm, JSValue driver, JSValueConst seed,
                       int formals, int scenario, int method)
{
    JSValue target = make_target(realm, formals, scenario);
    JSValue global = JS_GetGlobalObject(realm);
    assert(JS_SetPropertyStr(realm, global, "currentTarget", JS_DupValue(realm, target)) >= 0);
    JS_FreeValue(realm, global);
    JSValue args[2] = {target, seed};
    if (method) {
        args[0] = JS_NewObject(caller);
        assert(!JS_IsException(args[0]));
        assert(JS_SetPropertyStr(caller, args[0], "fn", JS_DupValue(caller, target)) >= 0);
        assert(JS_SetPropertyStr(caller, args[0], "marker", JS_NewInt32(caller, 42)) >= 0);
    }
    for (int i = 0; i < 9; i++) {
        JSValue result = JS_Call(caller, driver, JS_UNDEFINED, 2, args);
        check_result(caller, result, seed, scenario >= 2 && scenario <= 5, scenario == 3);
    }
    if (method)
        JS_FreeValue(caller, args[0]);
    JS_FreeValue(realm, target);
}

static size_t oom_case(size_t fail_at)
{
    Allocator allocation = {0};
    JSRuntime *rt = JS_NewRuntime2(&functions, &allocation);
    assert(rt);
    JSContext *ctx = JS_NewContext(rt);
    assert(ctx);
    JS_SetMaxStackSize(rt, 1024 * 1024);
    const char *text =
        "function target(a0,a1,a2,a3,a4,a5,a6,a7,a8,a9,a10,a11,a12,a13,a14,a15){return()=>a0}"
        "function loop(n,v){if(n)return loop(n-1,v);return target(v)}loop";
    JSValue loop = eval(ctx, text), seed = JS_NewObject(ctx);
    JSValue args[2] = {JS_NewInt32(ctx, 32), seed};
    check_result(ctx, JS_Call(ctx, loop, JS_UNDEFINED, 2, args), seed, 1, 0);
    allocation.sequence = 0;
    allocation.fail_at = fail_at;
    JSValue value = JS_Call(ctx, loop, JS_UNDEFINED, 2, args);
    size_t count = allocation.sequence;
    allocation.fail_at = 0;
    if (JS_IsException(value))
        JS_FreeValue(ctx, JS_GetException(ctx));
    else
        check_result(ctx, JS_DupValue(ctx, value), seed, 1, 0);
    JS_FreeValue(ctx, value);
    if (fail_at && fail_at <= count)
        assert(allocation.rejected == 1);
    check_result(ctx, JS_Call(ctx, loop, JS_UNDEFINED, 2, args), seed, 1, 0);
    JS_FreeValue(ctx, seed);
    JS_FreeValue(ctx, loop);
    JS_RunGC(rt);
    JS_FreeContext(ctx);
    JS_FreeRuntime(rt);
    assert(!allocation.live && !allocation.bytes);
    return count;
}

int main(int argc, char **argv)
{
    if (argc > 1 && !strcmp(argv[1], "oom")) {
        size_t n = oom_case(0);
        assert(n > 0 && n < 1000);
        for (size_t i = 1; i <= n + 2; i++)
            (void)oom_case(i);
        printf("LINUX_JS_CALL_OOM_OK injections=%zu recovery-and-zero-ledgers\n", n);
        return 0;
    }
    Allocator allocation = {0};
    Fixture fixture = {0};
    JSRuntime *rt = JS_NewRuntime2(&functions, &allocation);
    assert(rt);
    JSContext *ctx = JS_NewContext(rt), *realm = JS_NewContext(rt);
    assert(ctx && realm);
    fixture.caller = ctx;
    JS_SetContextOpaque(ctx, &fixture);
    JS_SetContextOpaque(realm, &fixture);
    JS_SetMaxStackSize(rt, 1024 * 1024);
    fixture.nested = eval(ctx, "(function(){return 31})");
    JSContext *contexts[2] = {ctx, realm};
    for (unsigned i = 0; i < 2; i++) {
        JSValue global = JS_GetGlobalObject(contexts[i]);
        assert(JS_SetPropertyStr(contexts[i], global, "inspect",
                                 JS_NewCFunction(contexts[i], inspect, "inspect", 2)) >= 0);
        JS_FreeValue(contexts[i], global);
    }
    JSValue drivers[4] = {
        eval(ctx, "(function(f,v){return f(v)})"),
        eval(
            ctx,
            "(function(f,v){let keep=7;let hold=()=>keep;let out=f(v);if(hold()!==7)throw Error('caller capture');return out})"),
        eval(ctx, "(function(box,v){return box.fn(v)})"),
        eval(ctx, "(function(f,v){return f(v,v,v)})")};
    JSValue seed = JS_NewObject(ctx);
    assert(!JS_IsException(seed));
    assert(JS_SetPropertyStr(ctx, seed, "id", JS_NewInt32(ctx, 17)) >= 0);
    assert(JS_SetPropertyStr(ctx, seed, "self", JS_DupValue(ctx, seed)) >= 0);
    const int arities[] = {1, 2, 4, 16, 128};
    for (int scenario = 0; scenario < 3; scenario++)
        for (unsigned a = 0; a < sizeof(arities) / sizeof(arities[0]); a++)
            for (unsigned driver = 0; driver < 3; driver++)
                run_target(ctx, ctx, drivers[driver], seed, arities[a], scenario, driver == 2);
    for (int scenario = 3; scenario <= 5; scenario++)
        run_target(ctx, ctx, drivers[0], seed, 1, scenario, 0);
    for (int scenario = 0; scenario < 3; scenario++)
        run_target(ctx, ctx, drivers[3], seed, 4, scenario, 0);
    run_target(ctx, realm, drivers[1], seed, 16, 2, 0);
    run_target(ctx, realm, drivers[2], seed, 16, 6, 1);
    int active = !getenv("QJS_DISABLE_REGISTER_INTERP") && !getenv("QJS_DISABLE_INTERP_FRAME") &&
                 !getenv("QJS_DISABLE_SHARED_ENTRY") && !getenv("QJS_DISABLE_C_INVOKE") &&
                 !getenv("QJS_DISABLE_FRAME_SET_NAME");
    if (fixture.calls < 450 || (active && fixture.matched < 400))
        fprintf(stderr, "OBS calls=%u matched=%u owned=%u borrowed=%u readonly=%u rejected=%u\n",
                fixture.calls, fixture.matched, fixture.owned, fixture.borrowed,
                fixture.readonly_captures, fixture.mutable_captures);
    assert(fixture.calls >= 450 && (!active || fixture.matched >= 400));
    assert(!active || (fixture.owned && fixture.borrowed && fixture.readonly_captures &&
                       fixture.mutable_captures));
    for (unsigned i = 0; i < 4; i++)
        JS_FreeValue(ctx, drivers[i]);
    JS_FreeValue(ctx, fixture.nested);
    JS_FreeValue(ctx, seed);
    JS_RunGC(rt);
    JS_FreeContext(realm);
    JS_FreeContext(ctx);
    JS_FreeRuntime(rt);
    assert(!allocation.live && !allocation.bytes);
    printf(
        "LINUX_JS_CALL_OK calls=%u matched=%u owned=%u borrowed=%u readonly=%u rejected=%u reentry=%u zero-ledgers\n",
        fixture.calls, fixture.matched, fixture.owned, fixture.borrowed, fixture.readonly_captures,
        fixture.mutable_captures, fixture.reentries);
    return 0;
}
