/* Public/native entry ownership, fallback, realm, GC, interrupts and OOM. MIT. */
#ifdef NDEBUG
#undef NDEBUG
#endif
#include "quickjs.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "../native_oom_allocator.h"

extern JSValue JS_FrameCallEntryDispatch(JSContext *, JSValueConst, JSValueConst, JSValueConst, int,
                                         JSValueConst *, int) __attribute__((weak));
static unsigned checks, interrupts;

static JSValue evaluate(JSContext *ctx, const char *source)
{
    JSValue value =
        JS_Eval(ctx, source, strlen(source), "native-entry-fixture", JS_EVAL_TYPE_GLOBAL);
    if (JS_IsException(value)) {
        JSValue error = JS_GetException(ctx);
        const char *message = JS_ToCString(ctx, error);
        fprintf(stderr, "ENTRY_FIXTURE_ERROR %s\n", message ? message : "unknown");
        JS_FreeCString(ctx, message);
        JS_FreeValue(ctx, error);
        abort();
    }
    return value;
}

static JSValue call(JSContext *ctx, JSValueConst fn, JSValueConst self, int argc,
                    JSValueConst *argv, unsigned route)
{
    if (route && JS_FrameCallEntryDispatch)
        return JS_FrameCallEntryDispatch(ctx, fn, self, JS_UNDEFINED, argc, argv,
                                         route == 1 ? 0 : 2);
    return JS_Call(ctx, fn, self, argc, argv);
}

static JSValue invoke(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)self;
    assert(argc >= 2);
    return JS_Call(ctx, argv[0], argv[1], argc - 2, argv + 2);
}

static void number(JSContext *ctx, JSValue value, int expected)
{
    int32_t result;
    assert(!JS_IsException(value));
    assert(JS_ToInt32(ctx, &result, value) == 0 && result == expected);
    JS_FreeValue(ctx, value);
    ++checks;
}

static int interrupt(JSContext *ctx, void *opaque)
{
    (void)ctx;
    (void)opaque;
    return ++interrupts >= 3;
}

static size_t fault_case(size_t fault)
{
    Allocator allocator = {0};
    JSRuntime *rt = JS_NewRuntime2(&functions, &allocator);
    assert(rt);
    JSContext *ctx = JS_NewContext(rt);
    assert(ctx);
    JSValue fn = evaluate(ctx, "(function(a){return {x:a}})"), seed = JS_NewObject(ctx);
    assert(!JS_IsException(seed));
    for (unsigned i = 0; i < 12; i++) {
        JSValue value = JS_Call(ctx, fn, JS_UNDEFINED, 1, &seed);
        assert(!JS_IsException(value));
        JS_FreeValue(ctx, value);
    }
    AllocatorArenaDrain drain = {0};
    oom_drain_arenas(rt, &allocator, &drain);
    allocator.sequence = 0;
    allocator.fail_at = fault;
    JSValue result = JS_Call(ctx, fn, JS_UNDEFINED, 1, &seed);
    size_t attempts = allocator.sequence;
    allocator.fail_at = 0;
    if (JS_IsException(result)) {
        JSValue error = JS_GetException(ctx);
        JS_FreeValue(ctx, error);
        JS_ResetUncatchableError(ctx);
    } else {
        JSValue field = JS_GetPropertyStr(ctx, result, "x");
        assert(JS_IsSameValue(ctx, field, seed));
        JS_FreeValue(ctx, field);
        JS_FreeValue(ctx, result);
    }
    if (fault)
        assert(allocator.rejected == 1);
    result = JS_Call(ctx, fn, JS_UNDEFINED, 1, &seed);
    assert(!JS_IsException(result));
    JSValue field = JS_GetPropertyStr(ctx, result, "x");
    assert(JS_IsSameValue(ctx, field, seed));
    JS_FreeValue(ctx, field);
    JS_FreeValue(ctx, result);
    JS_FreeValue(ctx, seed);
    JS_FreeValue(ctx, fn);
    oom_undrain_arenas(rt, &drain);
    JS_FreeContext(ctx);
    JS_FreeRuntime(rt);
    assert(!allocator.live && !allocator.bytes);
    return attempts;
}

int main(int argc, char **argv)
{
    if (argc == 2 && !strcmp(argv[1], "oom")) {
        size_t attempts = fault_case(0);
        assert(attempts && attempts < 64);
        for (size_t fault = 1; fault <= attempts; fault++)
            fault_case(fault);
        printf("LINUX_NATIVE_ENTRY_OOM_OK faults=%zu zero-ledgers\n", attempts);
        return 0;
    }
    Allocator allocator = {0};
    JSRuntime *rt = JS_NewRuntime2(&functions, &allocator);
    assert(rt);
    JSContext *ctx = JS_NewContext(rt), *other = JS_NewContext(rt);
    assert(ctx && other);
    JSValue init = evaluate(
        ctx,
        "globalThis.entrySeed=7;globalThis.entryFunctions=["
        "function(){return 3+(globalThis.entrySeed|0)},function(a){return a.k+1},"
        "function(a,b){return a+b+1},function(a,b,c){return a+b+c+1},function(){return this.k}];");
    JS_FreeValue(ctx, init);
    JSValue global = JS_GetGlobalObject(ctx),
            list = JS_GetPropertyStr(ctx, global, "entryFunctions");
    JSValue seed = evaluate(ctx, "({k:11})");
    JSValue constant = evaluate(ctx, "(function(){return 3})");
    for (unsigned route = 0; route < 3; route++)
        for (unsigned i = 0; i < 8; i++)
            number(ctx, call(ctx, constant, seed, 0, NULL, route), 3);
    JS_FreeValue(ctx, constant);
    for (unsigned route = 0; route < 3; route++)
        for (unsigned n = 0; n < 5; n++) {
            JSValue fn = JS_GetPropertyUint32(ctx, list, n);
            for (unsigned round = 0; round < 32; round++) {
                JSContext *caller = (round & 1) ? ctx : other;
                JSValue av[3] = {n == 1 ? seed : JS_NewInt32(caller, 2), JS_NewInt32(caller, 2),
                                 JS_NewInt32(caller, 3)};
                const int expected[] = {10, 12, 5, 8, 11};
                number(caller, call(caller, fn, seed, n < 4 ? (int)n : 0, av, route), expected[n]);
                if (!(round & 7))
                    JS_RunGC(rt);
            }
            JS_FreeValue(ctx, fn);
        }
    assert(JS_SetPropertyStr(ctx, global, "nativeEntryInvoke",
                             JS_NewCFunction(ctx, invoke, "nativeEntryInvoke", 2)) > 0);
    JSValue run = evaluate(
        ctx, "(function(){let acc=0;const left={k:Symbol.for('entry-symbol')};"
             "const add=function(a){return a+1},reduce=function(a,b){return(a+b+1)|0};"
             "const update=function(a){acc=(acc+a+1)|0};const get=function(){return this.k};"
             "const equal=function(){return this.k===left.k};const obj={k:left.k};"
             "for(let i=0;i<64;i++){"
             "if(nativeEntryInvoke(add,null,41)!==42)throw Error('map');"
             "if(nativeEntryInvoke(reduce,null,20,21)!==42)throw Error('reduce');"
             "nativeEntryInvoke(update,null,1);"
             "if(nativeEntryInvoke(get,obj)!==left.k)throw Error('getter');"
             "if(nativeEntryInvoke(equal,obj)!==true)throw Error('symbol getter');"
             "if(nativeEntryInvoke(add,null,2147483647)!==2147483648)throw Error('overflow');"
             "if(nativeEntryInvoke(add,null,'x')!=='x1')throw Error('coercion');"
             "}return acc})");
    for (unsigned i = 0; i < 8; i++) {
        number(ctx, JS_Call(ctx, run, JS_UNDEFINED, 0, NULL), 128);
        JS_RunGC(rt);
    }
    JS_FreeValue(ctx, run);
    JSValue getter = JS_GetPropertyUint32(ctx, list, 4);
    const char *receivers[] = {"Object.create({k:11})", "({get k(){return 11}})",
                               "new Proxy({k:11},{get(t,k,r){return Reflect.get(t,k,r)}})",
                               "({get k(){throw new TypeError('entry getter')}})"};
    for (unsigned i = 0; i < 4; i++) {
        JSValue receiver = evaluate(ctx, receivers[i]);
        for (unsigned route = 0; route < 3; route++) {
            JSValue value = call(ctx, getter, receiver, 0, NULL, route);
            if (i < 3)
                number(ctx, value, 11);
            else {
                assert(JS_IsException(value));
                JSValue error = JS_GetException(ctx);
                JS_FreeValue(ctx, error);
                ++checks;
            }
        }
        JS_FreeValue(ctx, receiver);
    }
    JSValue cycle = JS_NewObject(ctx);
    assert(JS_SetPropertyStr(ctx, cycle, "k", JS_DupValue(ctx, cycle)) > 0);
    for (unsigned route = 0; route < 3; route++) {
        JSValue result = call(ctx, getter, cycle, 0, NULL, route);
        assert(JS_IsSameValue(ctx, result, cycle));
        JS_FreeValue(ctx, result);
        ++checks;
    }
    JS_FreeValue(ctx, cycle);
    JS_RunGC(rt);
    JSValue pump = evaluate(ctx, "(function(a){while(a>0)a--;return 7})"),
            arg = JS_NewInt32(ctx, 1000000);
    JS_SetInterruptHandler(rt, interrupt, NULL);
    JSValue result = JS_Call(ctx, pump, JS_UNDEFINED, 1, &arg);
    assert(JS_IsException(result) && interrupts >= 3);
    JSValue error = JS_GetException(ctx);
    JS_FreeValue(ctx, error);
    JS_ResetUncatchableError(ctx);
    JS_SetInterruptHandler(rt, NULL, NULL);
    arg = JS_NewInt32(ctx, 8);
    number(ctx, JS_Call(ctx, pump, JS_UNDEFINED, 1, &arg), 7);
    JS_FreeValue(ctx, pump);
    JS_FreeValue(ctx, getter);
    JS_FreeValue(ctx, seed);
    JS_FreeValue(ctx, list);
    JS_FreeValue(ctx, global);
    JS_FreeContext(other);
    JS_FreeContext(ctx);
    JS_FreeRuntime(rt);
    assert(!allocator.live && !allocator.bytes);
    printf("LINUX_NATIVE_ENTRY_OK checks=%u interrupts=%u zero-ledgers\n", checks, interrupts);
    return 0;
}
