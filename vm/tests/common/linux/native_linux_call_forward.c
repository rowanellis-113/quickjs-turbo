/* Logical native parents, owning/borrowed captures, GC/realm reentry and OOM. */
#include "quickjs.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "../native_oom_allocator.h"

extern int JS_LinuxJSFrameProbe(JSRuntime *, uintptr_t *) __attribute__((weak));
typedef struct {
    JSContext *caller;
    JSValue nested;
    unsigned expected_depth, calls, forwarded, owned, borrowed, captures, traces, reentries,
        interrupts;
} Fixture;

static JSValue eval(JSContext *ctx, const char *text)
{
    JSValue value = JS_Eval(ctx, text, strlen(text), "native-forward", JS_EVAL_TYPE_GLOBAL);
    if (JS_IsException(value)) {
        JSValue e = JS_GetException(ctx);
        const char *message = JS_ToCString(ctx, e);
        fprintf(stderr, "FORWARD ERROR %s\n", message ? message : "unknown");
        JS_FreeCString(ctx, message);
        JS_FreeValue(ctx, e);
        abort();
    }
    return value;
}

static uintptr_t word(uintptr_t pointer, size_t offset)
{
    uintptr_t out;
    memcpy(&out, (const void *)(pointer + offset), sizeof(out));
    return out;
}

static unsigned byte(uintptr_t pointer, size_t offset)
{
    unsigned char out;
    memcpy(&out, (const void *)(pointer + offset), 1);
    return out;
}

static JSValue inspect(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)self;
    assert(argc == 1 && JS_IsObject(argv[0]));
    Fixture *f = JS_GetContextOpaque(ctx);
    assert(f);
    ++f->calls;
    uintptr_t words[10];
    if (JS_LinuxJSFrameProbe && JS_LinuxJSFrameProbe(JS_GetRuntime(ctx), words) &&
        words[8] == (uintptr_t)JS_VALUE_GET_PTR(argv[0]) && words[9] == 2) {
        uintptr_t frame = words[1] - 128, previous = word(frame, 0);
        unsigned depth = 0;
        while (previous && !word(previous, 32) && byte(previous, 63) == 199) {
            assert(!word(previous, 40) && !word(previous, 64));
            ++depth;
            assert(depth <= 64);
            previous = word(previous, 0);
        }
        assert(depth == f->expected_depth && previous && word(previous, 32));
        ++f->forwarded;
        if (words[0] == words[1]) {
            ++f->owned;
            assert(words[2] == words[3]);
        } else {
            ++f->borrowed;
            assert(words[2] == 0);
        }
        if ((words[5] & 7) == 5 || (words[5] & 7) == 7)
            ++f->captures;
    }
    JS_RunGC(JS_GetRuntime(ctx));
    JSValue trace = eval(ctx, "(new Error('forward trace')).stack");
    const char *stack = JS_ToCString(ctx, trace);
    assert(stack);
    if (!strstr(stack, "call"))
        fprintf(stderr, "MISSING CALL TRACE %s\n", stack);
    assert(strstr(stack, "call"));
    ++f->traces;
    JS_FreeCString(ctx, stack);
    JS_FreeValue(ctx, trace);
    JSValue nested = JS_Call(f->caller, f->nested, JS_UNDEFINED, 0, NULL);
    int32_t n;
    assert(!JS_IsException(nested) && JS_ToInt32(f->caller, &n, nested) == 0 && n == 31);
    JS_FreeValue(f->caller, nested);
    ++f->reentries;
    JS_RunGC(JS_GetRuntime(ctx));
    JS_SetMaxStackSize(JS_GetRuntime(ctx), (f->calls & 1) ? 0 : 1024 * 1024);
    return JS_UNDEFINED;
}

static JSValue make_driver(JSContext *ctx, unsigned depth, int reserve)
{
    char code[4096];
    size_t used = (size_t)snprintf(code, sizeof(code), "(function(f,r,v,c){");
    if (reserve)
        used += (size_t)snprintf(
            code + used, sizeof(code) - used,
            "let keep=7;let hold=()=>keep;forwardReserve(v,v,v,v,v,v,v,v);let out=");
    else
        used += (size_t)snprintf(code + used, sizeof(code) - used, "return ");
    if (depth == 1)
        used += (size_t)snprintf(code + used, sizeof(code) - used, "f.call(r,v)");
    else {
        used += (size_t)snprintf(code + used, sizeof(code) - used, "c.call(");
        for (unsigned i = 0; i < depth - 2; i++)
            used += (size_t)snprintf(code + used, sizeof(code) - used, "c,");
        used += (size_t)snprintf(code + used, sizeof(code) - used, "f,r,v)");
    }
    if (reserve)
        used += (size_t)snprintf(code + used, sizeof(code) - used,
                                 ";if(hold()!==7)throw Error('caller capture');return out");
    used += (size_t)snprintf(code + used, sizeof(code) - used, "})");
    assert(used < sizeof(code));
    return eval(ctx, code);
}

static JSValue make_target(JSContext *ctx, unsigned arity, unsigned scenario)
{
    char code[4096];
    size_t used = (size_t)snprintf(code, sizeof(code), "(function(");
    for (unsigned i = 0; i < arity; i++)
        used += (size_t)snprintf(code + used, sizeof(code) - used, "%sa%u", i ? "," : "", i);
    used += (size_t)snprintf(code + used, sizeof(code) - used, "){ ");
    const char *bodies[] = {
        "inspect(currentForwardTarget);return a0",
        "let saved=a0;a0=undefined;inspect(currentForwardTarget);return saved",
        "let held=()=>a0;inspect(currentForwardTarget);return held",
        "let never=()=>{a0={id:9}};let held=()=>a0;inspect(currentForwardTarget);return held"};
    used += (size_t)snprintf(code + used, sizeof(code) - used, "%s})", bodies[scenario]);
    assert(used < sizeof(code));
    return eval(ctx, code);
}

static void identity(JSContext *ctx, JSValue result, JSValueConst seed, int closure)
{
    assert(!JS_IsException(result));
    if (closure) {
        JSValue next = JS_Call(ctx, result, JS_UNDEFINED, 0, NULL);
        JS_FreeValue(ctx, result);
        result = next;
        assert(!JS_IsException(result));
    }
    assert(JS_IsObject(result) && JS_VALUE_GET_PTR(result) == JS_VALUE_GET_PTR(seed));
    JS_FreeValue(ctx, result);
}

static int interrupt(JSContext *ctx, void *opaque)
{
    (void)ctx;
    Fixture *f = opaque;
    return ++f->interrupts >= 3;
}

static void quota_case(void)
{
    Allocator a = {0};
    JSRuntime *rt = JS_NewRuntime2(&functions, &a);
    assert(rt);
    JSContext *ctx = JS_NewContext(rt);
    assert(ctx);
    JS_SetMaxStackSize(rt, 1024 * 1024);
    JSValue fn = eval(
        ctx,
        "function quotaRecurse(n){if(n)return quotaRecurse.call(undefined,n-1)+1;return 7}quotaRecurse");
    JSValue argument = JS_NewInt32(ctx, 256), result;
    int32_t n;
    result = JS_Call(ctx, fn, JS_UNDEFINED, 1, &argument);
    assert(!JS_IsException(result) && JS_ToInt32(ctx, &n, result) == 0 && n == 263);
    JS_FreeValue(ctx, result);
    JS_SetMaxStackSize(rt, 32768);
    result = JS_Call(ctx, fn, JS_UNDEFINED, 1, &argument);
    assert(JS_IsException(result));
    JSValue error = JS_GetException(ctx), message = JS_GetPropertyStr(ctx, error, "message");
    const char *text = JS_ToCString(ctx, message);
    assert(text && strstr(text, "stack"));
    JS_FreeCString(ctx, text);
    JS_FreeValue(ctx, message);
    JS_FreeValue(ctx, error);
    JS_ResetUncatchableError(ctx);
    JS_SetMaxStackSize(rt, 1024 * 1024);
    result = JS_Call(ctx, fn, JS_UNDEFINED, 1, &argument);
    assert(!JS_IsException(result) && JS_ToInt32(ctx, &n, result) == 0 && n == 263);
    JS_FreeValue(ctx, result);
    JS_FreeValue(ctx, fn);
    JS_FreeContext(ctx);
    JS_FreeRuntime(rt);
    assert(!a.live && !a.bytes);
    puts("LINUX_FORWARD_QUOTA_OK overflow-recovery-and-zero-ledgers");
}

static size_t oom_case(size_t fault)
{
    Allocator a = {0};
    JSRuntime *rt = JS_NewRuntime2(&functions, &a);
    assert(rt);
    JSContext *ctx = JS_NewContext(rt);
    assert(ctx);
    JS_SetMaxStackSize(rt, 1024 * 1024);
    JSValue run =
        eval(ctx, "function recurse(n,v){if(n)return recurse.call(undefined,n-1,v);return()=>v}"
                  "(function(n,v){return recurse.call(undefined,n,v)})");
    JSValue seed = JS_NewObject(ctx);
    assert(!JS_IsException(seed));
    assert(JS_SetPropertyStr(ctx, seed, "self", JS_DupValue(ctx, seed)) >= 0);
    JSValue args[2] = {JS_NewInt32(ctx, 64), seed};
    identity(ctx, JS_Call(ctx, run, JS_UNDEFINED, 2, args), seed, 1);
    AllocatorArenaDrain drain = {0};
    oom_drain_arenas(rt, &a, &drain);
    a.sequence = 0;
    a.fail_at = fault;
    JSValue result = JS_Call(ctx, run, JS_UNDEFINED, 2, args);
    size_t count = a.sequence;
    a.fail_at = 0;
    oom_undrain_arenas(rt, &drain);
    if (JS_IsException(result))
        JS_FreeValue(ctx, JS_GetException(ctx));
    else
        identity(ctx, JS_DupValue(ctx, result), seed, 1);
    JS_FreeValue(ctx, result);
    if (fault && fault <= count)
        assert(a.rejected == 1);
    identity(ctx, JS_Call(ctx, run, JS_UNDEFINED, 2, args), seed, 1);
    JS_FreeValue(ctx, seed);
    JS_FreeValue(ctx, run);
    JS_RunGC(rt);
    JS_FreeContext(ctx);
    JS_FreeRuntime(rt);
    assert(!a.live && !a.bytes);
    return count;
}

int main(int argc, char **argv)
{
    if (argc > 1 && !strcmp(argv[1], "quota")) {
        quota_case();
        return 0;
    }
    if (argc > 1 && !strcmp(argv[1], "oom")) {
        size_t count = oom_case(0);
        assert(count > 0 && count < 1000);
        for (size_t i = 1; i <= count + 2; i++)
            (void)oom_case(i);
        printf("LINUX_FORWARD_OOM_OK injections=%zu recovery-and-zero-ledgers\n", count);
        return 0;
    }
    int reference = argc > 1 && !strcmp(argv[1], "reference");
    Allocator allocation = {0};
    Fixture f = {0};
    JSRuntime *rt = JS_NewRuntime2(&functions, &allocation);
    assert(rt);
    JSContext *ctx = JS_NewContext(rt), *realm = JS_NewContext(rt);
    assert(ctx && realm);
    f.caller = ctx;
    f.nested = eval(ctx, "(function(){return 31})");
    JS_SetContextOpaque(ctx, &f);
    JS_SetContextOpaque(realm, &f);
    JS_SetMaxStackSize(rt, 1024 * 1024);
    JSContext *contexts[2] = {ctx, realm};
    for (unsigned i = 0; i < 2; i++) {
        JSValue global = JS_GetGlobalObject(contexts[i]);
        assert(JS_SetPropertyStr(contexts[i], global, "inspect",
                                 JS_NewCFunction(contexts[i], inspect, "inspect", 1)) >= 0);
        JS_FreeValue(contexts[i], global);
        JSValue reserve =
            eval(contexts[i], "globalThis.forwardReserve=function(a,b,c,d,e,f,g,h){return 0}");
        JS_FreeValue(contexts[i], reserve);
    }
    JSValue wrappers[2] = {eval(ctx, "Function.prototype.call"),
                           eval(realm, "Function.prototype.call")};
    JSValue receiver = JS_NewObject(ctx), seed = JS_NewObject(ctx);
    assert(!JS_IsException(receiver) && !JS_IsException(seed));
    assert(JS_SetPropertyStr(ctx, seed, "self", JS_DupValue(ctx, seed)) >= 0);
    const unsigned depths[] = {1, 2, 3, 8}, arities[] = {1, 4, 16, 128};
    for (unsigned d = 0; d < 4; d++)
        for (unsigned a = 0; a < 4; a++)
            for (unsigned scenario = 0; scenario < 4; scenario++) {
                JSContext *owner = ((d + a + scenario) & 1) ? realm : ctx;
                JSValue target = make_target(owner, arities[a], scenario);
                JSValue global = JS_GetGlobalObject(owner);
                assert(JS_SetPropertyStr(owner, global, "currentForwardTarget",
                                         JS_DupValue(owner, target)) >= 0);
                JS_FreeValue(owner, global);
                JSValue drive = make_driver(ctx, depths[d], d == 0);
                f.expected_depth = depths[d];
                JSValue args[4] = {target, receiver, seed, wrappers[(a + scenario) & 1]};
                for (int repeat = 0; repeat < 5; repeat++)
                    identity(ctx, JS_Call(ctx, drive, JS_UNDEFINED, 4, args), seed, scenario >= 2);
                JS_FreeValue(ctx, drive);
                JS_FreeValue(owner, target);
            }
    JSValue pump =
        eval(ctx, "(function(f,r,v){let out;for(let i=0;i<100000;i++)out=f.call(r,v);return out})");
    JSValue simple = eval(ctx, "(function(v){return v})");
    JSValue args[3] = {simple, receiver, seed};
    identity(ctx, JS_Call(ctx, pump, JS_UNDEFINED, 3, args), seed, 0);
    JS_SetInterruptHandler(rt, interrupt, &f);
    JSValue stopped = JS_Call(ctx, pump, JS_UNDEFINED, 3, args);
    JS_SetInterruptHandler(rt, NULL, NULL);
    assert(JS_IsException(stopped) && f.interrupts == 3);
    JS_FreeValue(ctx, JS_GetException(ctx));
    JS_ResetUncatchableError(ctx);
    identity(ctx, JS_Call(ctx, pump, JS_UNDEFINED, 3, args), seed, 0);
    int active = !reference && JS_LinuxJSFrameProbe && !getenv("QJS_DISABLE_REGISTER_INTERP") &&
                 !getenv("QJS_DISABLE_INTERP_FRAME") && !getenv("QJS_DISABLE_SHARED_ENTRY") &&
                 !getenv("QJS_DISABLE_C_INVOKE") && !getenv("QJS_DISABLE_FRAME_CALL_FORWARD");
    int borrow_active = active && !getenv("QJS_DISABLE_FRAME_CALL_FORWARD_NATIVE") &&
                        !getenv("QJS_DISABLE_FRAME_CALL_FORWARD_OWNED") &&
                        !getenv("QJS_DISABLE_FRAME_CALL_FORWARD_BORROW");
    if (active && !(f.forwarded >= 200 && f.owned && f.captures))
        fprintf(stderr, "FORWARD OBS calls=%u forwarded=%u owned=%u borrowed=%u captures=%u\n",
                f.calls, f.forwarded, f.owned, f.borrowed, f.captures);
    assert(f.calls == 320 && f.traces == f.calls && f.reentries == f.calls);
    assert(!active || (f.forwarded >= 200 && f.owned && f.captures));
    assert(!borrow_active || f.borrowed);
    JS_FreeValue(ctx, pump);
    JS_FreeValue(ctx, simple);
    for (unsigned i = 0; i < 2; i++)
        JS_FreeValue(ctx, wrappers[i]);
    JS_FreeValue(ctx, seed);
    JS_FreeValue(ctx, receiver);
    JS_FreeValue(ctx, f.nested);
    JS_RunGC(rt);
    JS_FreeContext(realm);
    JS_FreeContext(ctx);
    JS_FreeRuntime(rt);
    assert(!allocation.live && !allocation.bytes);
    printf(
        "LINUX_FORWARD_HOST_OK calls=%u forwarded=%u owned=%u borrowed=%u captures=%u traces=%u reentry=%u interrupts=%u zero-ledgers\n",
        f.calls, f.forwarded, f.owned, f.borrowed, f.captures, f.traces, f.reentries, f.interrupts);
    return 0;
}
