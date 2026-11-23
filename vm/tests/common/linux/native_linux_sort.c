/* Actual prepared-sort reuse, realm/reentry, interrupts and allocator faults. */
#include "quickjs.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef NDEBUG
#error Sort ownership qualification requires assertions.
#endif
#include "../native_oom_allocator.h"
extern int JS_FrameLinuxPreparedSortProbe(JSContext *, uintptr_t *);
typedef struct Observer {
    unsigned calls, hits, reuse, gc, reentry;
    int exercise;
    uintptr_t first[4];
    JSContext *other;
    JSValue nested;
} Observer;
static JSValue probe(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    Observer *o = JS_GetRuntimeOpaque(JS_GetRuntime(ctx));
    uintptr_t words[6], after[6];
    (void)self;
    (void)argc;
    (void)argv;
    ++o->calls;
    if (JS_FrameLinuxPreparedSortProbe(ctx, words)) {
        ++o->hits;
        assert(words[0] && words[1] && words[2] && words[3] && words[4]);
        if (!o->first[0])
            memcpy(o->first, words, sizeof(o->first));
        else {
            assert(!memcmp(o->first, words, sizeof(o->first)));
            ++o->reuse;
        }
        if (o->exercise && o->hits % 17 == 0) {
            ++o->gc;
            JS_RunGC(JS_GetRuntime(ctx));
            JSValue value = JS_Call(o->other, o->nested, JS_UNDEFINED, 0, NULL);
            assert(!JS_IsException(value));
            JS_FreeValue(o->other, value);
            ++o->reentry;
            assert(JS_FrameLinuxPreparedSortProbe(ctx, after));
            assert(!memcmp(words, after, sizeof(words)));
        }
    }
    return JS_UNDEFINED;
}
static JSValue evaluate(JSContext *ctx, const char *text)
{
    JSValue value = JS_Eval(ctx, text, strlen(text), "linux-sort-owner", JS_EVAL_TYPE_GLOBAL);
    if (JS_IsException(value)) {
        JSValue error = JS_GetException(ctx);
        const char *message = JS_ToCString(ctx, error);
        fprintf(stderr, "SORT_EVAL_FAILURE %s\n", message ? message : "<conversion>");
        JS_FreeCString(ctx, message);
        JS_FreeValue(ctx, error);
        assert(0);
    }
    return value;
}
static void validate(JSContext *ctx, JSValue value)
{
    int32_t number = -1;
    if (JS_IsException(value)) {
        JSValue error = JS_GetException(ctx);
        const char *message = JS_ToCString(ctx, error);
        fprintf(stderr, "SORT_CALL_FAILURE %s\n", message ? message : "<conversion>");
        JS_FreeCString(ctx, message);
        JS_FreeValue(ctx, error);
        assert(0);
    }
    assert(JS_ToInt32(ctx, &number, value) == 0 && number == 0);
    JS_FreeValue(ctx, value);
}
static const char setup[] =
    "function cmp(a,b){probe();return a-b;}"
    "function objcmp(a,b){probe();return a.x-b.x;}"
    "function numbers(){let a=Array.from({length:64},(_,i)=>63-i);a.sort(cmp);"
    " for(let i=0;i<a.length;i++)if(a[i]!==i)throw Error('order');return a[0];}"
    "function objects(){let a=Array.from({length:64},(_,i)=>({x:63-i}));a.sort(objcmp);"
    " for(let i=0;i<a.length;i++)if(a[i].x!==i)throw Error('object order');return a[0].x;}"
    "function cross(){let a=[9,8,7,6,5,4,3,2,1,0];foreignSort.call(a,cmp);return a[0];}"
    "function throwingCmp(a,b){probe();if(a===13||b===13)throw Error('sort sentinel');return a-b;}"
    "function throwing(){return [14,13,12,11,10,9,8,7].sort(throwingCmp);}"
    "function external(){let k=0;let a=Array.from({length:32},(_,i)=>31-i).sort((a,b)=>{probe();k=k+1;return a-b;});"
    " if(k<1)throw Error('external cell mutation');return a[0];}"
    "function captureCmp(a,b){let saved=a;globalThis.captureSink=()=>saved;probe();return a-b;}"
    "function capture(){return [3,2,1,0].sort(captureCmp)[0];}"
    "function writableCmp(a,b){a=a+1;probe();return a-b-1;}"
    "function writable(){return [3,2,1,0].sort(writableCmp)[0];}"
    "function missingCmp(a,b,c){probe();return a-b+(c===undefined?0:99);}"
    "function missing(){return [3,2,1,0].sort(missingCmp)[0];}"
    "function busyCmp(a,b){for(let i=0;i<60000;i++){}probe();return a-b;}"
    "function busy(){return [9,8,7,6,5,4,3,2,1,0].sort(busyCmp)[0];}"
    "function chain(n,v){if(n)return chain(n-1,v)+1;return v;}"
    "function growthCmp(a,b){probe();return chain(64,a.x)-b.x-64;}"
    "function growthSort(){return [{x:9},{x:8},{x:7},{x:6},{x:5},{x:4},{x:3},{x:2},{x:1},{x:0}].sort(growthCmp)[0].x;}"
    "function faultSort(){return [9,8,7,6,5,4,3,2,1,0].sort(cmp)[0];}";
static void install(JSContext *ctx, Observer *o)
{
    JS_SetRuntimeOpaque(JS_GetRuntime(ctx), o);
    JSValue global = JS_GetGlobalObject(ctx);
    assert(JS_SetPropertyStr(ctx, global, "probe", JS_NewCFunction(ctx, probe, "probe", 0)) > 0);
    JS_FreeValue(ctx, global);
    JS_FreeValue(ctx, evaluate(ctx, setup));
}
static JSValue function(JSContext *ctx, const char *name)
{
    JSValue global = JS_GetGlobalObject(ctx);
    JSValue value = JS_GetPropertyStr(ctx, global, name);
    JS_FreeValue(ctx, global);
    assert(JS_IsFunction(ctx, value));
    return value;
}
static void reset(Observer *o)
{
    o->calls = o->hits = o->reuse = 0;
    memset(o->first, 0, sizeof(o->first));
}
static unsigned interrupts;
static int interrupt(JSContext *ctx, void *opaque)
{
    (void)ctx;
    (void)opaque;
    return ++interrupts >= 2;
}
static void semantics(void)
{
    JSRuntime *rt = JS_NewRuntime();
    assert(rt);
    Observer o = {0};
    JSContext *ctx = JS_NewContext(rt);
    assert(ctx);
    install(ctx, &o);
    o.other = JS_NewContext(rt);
    assert(o.other);
    o.nested = evaluate(o.other, "(function(){return [7,3,6,1,0].sort((a,b)=>a-b)[0];})");
    JSValue global = JS_GetGlobalObject(ctx);
    JSValue foreign = evaluate(o.other, "Array.prototype.sort");
    assert(JS_SetPropertyStr(ctx, global, "foreignSort", foreign) > 0);
    JS_FreeValue(ctx, global);
    int disabled = getenv("QJS_DISABLE_CACHED_SORT_CALL") ||
                   getenv("QJS_DISABLE_PREPARED_SORT_CALL") ||
                   getenv("QJS_DISABLE_REGISTER_INTERP") || getenv("QJS_DISABLE_INTERP_FRAME") ||
                   getenv("QJS_DISABLE_SHARED_ENTRY") || getenv("QJS_DISABLE_INTERNAL_INTERP") ||
                   getenv("QJS_DISABLE_SHARED_CALL_BYPASS");
    unsigned total = 0, reused = 0;
    const char *names[] = {"numbers", "objects", "cross", "external"};
    for (unsigned n = 0; n < sizeof(names) / sizeof(names[0]); ++n) {
        JSValue fn = function(ctx, names[n]);
        for (unsigned pass = 0; pass < 4; ++pass) {
            reset(&o);
            o.exercise = pass == 3;
            validate(ctx, JS_Call(ctx, fn, JS_UNDEFINED, 0, NULL));
            if (pass >= 1) {
                if (disabled ? o.hits != 0 : o.hits != o.calls)
                    fprintf(stderr, "SORT_CASE %s pass=%u calls=%u hits=%u reuse=%u disabled=%d\n",
                            names[n], pass, o.calls, o.hits, o.reuse, disabled);
                assert(o.calls && (disabled ? o.hits == 0 : o.hits == o.calls));
                assert(disabled ? o.reuse == 0 : o.reuse + 1 == o.hits);
                total += o.hits;
                reused += o.reuse;
            }
            assert(!JS_FrameLinuxPreparedSortProbe(ctx, NULL));
        }
        JS_FreeValue(ctx, fn);
    }
    o.exercise = 0;
    const char *fallbacks[] = {"capture", "writable", "missing"};
    for (unsigned n = 0; n < sizeof(fallbacks) / sizeof(fallbacks[0]); ++n) {
        JSValue fn = function(ctx, fallbacks[n]);
        for (unsigned i = 0; i < 3; ++i) {
            reset(&o);
            validate(ctx, JS_Call(ctx, fn, JS_UNDEFINED, 0, NULL));
            if (o.hits)
                fprintf(stderr, "SORT_FALLBACK_CASE %s pass=%u calls=%u hits=%u\n", fallbacks[n], i,
                        o.calls, o.hits);
            assert(!o.hits);
        }
        JS_FreeValue(ctx, fn);
    }
    JSValue fn = function(ctx, "throwing");
    for (unsigned i = 0; i < 3; ++i) {
        reset(&o);
        JSValue value = JS_Call(ctx, fn, JS_UNDEFINED, 0, NULL);
        assert(JS_IsException(value));
        JS_FreeValue(ctx, JS_GetException(ctx));
        assert(!JS_FrameLinuxPreparedSortProbe(ctx, NULL));
    }
    JS_FreeValue(ctx, fn);
    fn = function(ctx, "busy");
    JS_SetInterruptHandler(rt, interrupt, NULL);
    JSValue value = JS_Call(ctx, fn, JS_UNDEFINED, 0, NULL);
    assert(JS_IsException(value) && interrupts >= 2);
    JS_FreeValue(ctx, JS_GetException(ctx));
    JS_SetInterruptHandler(rt, NULL, NULL);
    JS_FreeValue(ctx, fn);
    fn = function(ctx, "growthSort");
    for (unsigned pass = 0; pass < 3; ++pass) {
        reset(&o);
        validate(ctx, JS_Call(ctx, fn, JS_UNDEFINED, 0, NULL));
        if (pass && !disabled) {
            assert(o.hits && o.hits < o.calls);
            assert(o.reuse + 1 == o.hits);
        }
        assert(!JS_FrameLinuxPreparedSortProbe(ctx, NULL));
    }
    JS_FreeValue(ctx, fn);
    fn = function(ctx, "numbers");
    reset(&o);
    validate(ctx, JS_Call(ctx, fn, JS_UNDEFINED, 0, NULL));
    JS_FreeValue(ctx, fn);
    JS_RunGC(rt);
    JS_FreeValue(o.other, o.nested);
    JS_FreeContext(o.other);
    JS_FreeContext(ctx);
    JS_FreeRuntime(rt);
    printf("LINUX_SORT_SEMANTICS_OK hits=%u reuse=%u gc=%u reentry=%u interrupts=%u\n", total,
           reused, o.gc, o.reentry, interrupts);
}
static unsigned failures, injected;
static int growth_fault;
static size_t trial(size_t fault)
{
    Allocator memory = {0};
    Observer o = {0};
    JSRuntime *rt = JS_NewRuntime2(&functions, &memory);
    assert(rt);
    JSContext *ctx = JS_NewContext(rt);
    assert(ctx);
    install(ctx, &o);
    JSValue fn = function(ctx, growth_fault ? "growthSort" : "faultSort");
    for (unsigned i = 0; i < 2; ++i)
        validate(ctx, JS_Call(ctx, fn, JS_UNDEFINED, 0, NULL));
    reset(&o);
    size_t before = memory.sequence;
    memory.fail_at = fault ? before + fault : 0;
    JSValue value = JS_Call(ctx, fn, JS_UNDEFINED, 0, NULL);
    memory.fail_at = 0;
    size_t count = memory.sequence - before;
    injected += memory.rejected;
    if (JS_IsException(value)) {
        ++failures;
        JS_FreeValue(ctx, JS_GetException(ctx));
    } else
        validate(ctx, value);
    assert(!JS_FrameLinuxPreparedSortProbe(ctx, NULL));
    reset(&o);
    validate(ctx, JS_Call(ctx, fn, JS_UNDEFINED, 0, NULL));
    JS_FreeValue(ctx, fn);
    JS_RunGC(rt);
    JS_FreeContext(ctx);
    JS_FreeRuntime(rt);
    assert(!memory.live && !memory.bytes);
    return count;
}
int main(int argc, char **argv)
{
    if (argc > 1) {
        growth_fault = !strcmp(argv[1], "growth-oom");
        size_t count = trial(0);
        for (size_t fault = 1; fault <= count + 1; ++fault)
            trial(fault);
        assert(count && injected && failures);
        printf("LINUX_SORT_OOM_OK allocations=%zu injected=%u failures=%u growth=%d\n", count,
               injected, failures, growth_fault);
    } else
        semantics();
    return 0;
}
