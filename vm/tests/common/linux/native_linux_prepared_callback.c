/* Real prepared-capsule reuse, roots, reentry, realm, interrupt and OOM. MIT. */
#include "quickjs.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef QJS_NATIVE_CALLBACK_UNWIND_TEST
#include <execinfo.h>
struct JSFrameRegisterState;
extern int JS_FrameInterp(struct JSFrameRegisterState *);
extern unsigned char qjs_native_vm_end[];
static unsigned vm_unwinds;
#endif
#ifdef NDEBUG
#error This fixture requires assertions.
#endif
#include "../native_oom_allocator.h"
extern int JS_FrameCallbackScopeProbe(JSContext *, uintptr_t *);

typedef struct {
    unsigned calls, hits, reentries, gc, reuse;
    int exercise;
    uintptr_t first[4];
    JSContext *other;
    JSValue nested;
} Observer;
static JSValue probe(JSContext *ctx, JSValueConst this_value, int argc, JSValueConst *argv)
{
    Observer *o = JS_GetRuntimeOpaque(JS_GetRuntime(ctx));
    uintptr_t words[6], after[6];
    ++o->calls;
    if (JS_FrameCallbackScopeProbe(ctx, words)) {
        ++o->hits;
        assert(words[0] && words[1] && words[2] && words[3] && words[4]);
        if (!o->first[0])
            memcpy(o->first, words, sizeof(o->first));
        else {
            assert(!memcmp(o->first, words, sizeof(o->first)));
            ++o->reuse;
        }
        if (o->exercise && o->hits % 7 == 0) {
#ifdef QJS_NATIVE_CALLBACK_UNWIND_TEST
            void *frames[64];
            unsigned vm_frames = 0;
            int count = backtrace(frames, 64);
            for (int i = 0; i < count; ++i)
                vm_frames += (uintptr_t)frames[i] > (uintptr_t)JS_FrameInterp &&
                             (uintptr_t)frames[i] < (uintptr_t)qjs_native_vm_end;
            /* The callback VM and the paused array caller VM both unwind
             * naturally through the typed capsule and original loop owners. */
            assert(vm_frames >= 2);
            ++vm_unwinds;
#endif
            JS_RunGC(JS_GetRuntime(ctx));
            ++o->gc;
            JSValue value = JS_Call(o->other, o->nested, JS_UNDEFINED, 0, NULL);
            assert(!JS_IsException(value));
            JS_FreeValue(o->other, value);
            ++o->reentries;
            assert(JS_FrameCallbackScopeProbe(ctx, after));
            assert(!memcmp(words, after, sizeof(words)));
        }
    }
    return JS_UNDEFINED;
}
static const char setup[] =
    "var input=Array.from({length:32},(_,i)=>i); var typed=new Uint32Array(input);"
    "var objects=input.map(v=>({v}));"
    "function ro(v,i,a){probe();return v+i+a.length;}"
    "function rw(v,i,a){v=v+1;i=i+1;probe();return v+i+a.length-2;}"
    "function pad(v,i,a,u,w){probe();if(u!==undefined||w!==undefined)throw Error('padding');return v+i+a.length;}"
    "function rwpad(v,i,a,u,w){if(u!==undefined||w!==undefined)throw Error('owned padding');u=1;v=v+1;probe();return v+i+a.length-1;}"
    "function red(acc,v,i,a){probe();return acc+v+i+a.length;}"
    "function redw(acc,v,i,a){acc=acc+v;probe();return acc+i+a.length;}"
    "function objro(v,i,a){probe();return v.v+i+a.length;}"
    "function objrw(v,i,a){v=v.v;probe();return v+i+a.length;}"
    "function yes(v,i,a){probe();return true;}"
    "function no(v,i,a){probe();return false;}"
    "function boom(v,i,a){probe();if(i===8)throw Error('sentinel');return v;}"
    "function chain(n,v){if(n)return chain(n-1,v)+1;return v;}"
    "function deep(v,i,a){probe();return chain(64,v);}"
    "function deepReduce(acc,v,i,a){probe();return chain(64,v)+acc;}"
    "function deepWriteReduce(acc,v,i,a){acc=acc+chain(64,v);probe();return acc;}"
    "function busy(v,i,a){for(let j=0;j<20000;++j){v=v+1;}probe();return v;}"
    "function mapRO(){return input.map(ro);}"
    "function mapRW(){return input.map(rw);}"
    "function mapPAD(){return input.map(pad);}"
    "function mapRWPAD(){return input.map(rwpad);}"
    "function mapTA(){return typed.map(ro);}"
    "function mapTAW(){return typed.map(rw);}"
    "function mapOBJRO(){return objects.map(objro);}"
    "function mapOBJRW(){return objects.map(objrw);}"
    "function reduceRO(){return input.reduce(red,0);}"
    "function reduceRW(){return input.reduce(redw,0);}"
    "function reduceRight(){return typed.reduceRight(red,0);}"
    "function reduceTA(){return typed.reduce(red,0);}"
    "function reduceRightArray(){return input.reduceRight(red,0);}"
    "function every(){return input.every(yes);}"
    "function everyTA(){return typed.every(yes);}"
    "function some(){return typed.some(no);}"
    "function someArray(){return input.some(no);}"
    "function filter(){return typed.filter(yes);}"
    "function filterArray(){return input.filter(yes);}"
    "function each(){return input.forEach(ro);}"
    "function eachTA(){return typed.forEach(ro);}"
    "function throwing(){return input.map(boom);}"
    "function allocation(){return input.reduce(deepReduce,0);}"
    "function allocationWrite(){return input.reduce(deepWriteReduce,0);}"
    /* map fault4 reaches an inherited 0.15.1 species-constructor defect,
       reproduced independently with the stock archive. Retain that separate
       reproducer; use reduce to sweep this new capsule's arena growth. */
    "function allocationMap(){return input.map(deep);}"
    "function interrupted(){return input.map(busy);}";

static JSValue evaluate(JSContext *ctx, const char *source)
{
    JSValue value =
        JS_Eval(ctx, source, strlen(source), "linux-prepared-callback", JS_EVAL_TYPE_GLOBAL);
    if (JS_IsException(value)) {
        JSValue error = JS_GetException(ctx);
        const char *text = JS_ToCString(ctx, error);
        fprintf(stderr, "EVAL_FAILED %s\n", text ? text : "<OOM>");
        abort();
    }
    return value;
}
static JSValue function(JSContext *ctx, const char *name)
{
    JSValue global = JS_GetGlobalObject(ctx), value = JS_GetPropertyStr(ctx, global, name);
    JS_FreeValue(ctx, global);
    assert(JS_IsFunction(ctx, value));
    return value;
}
static void install(JSContext *ctx, Observer *o)
{
    JS_SetRuntimeOpaque(JS_GetRuntime(ctx), o);
    JSValue global = JS_GetGlobalObject(ctx);
    assert(JS_SetPropertyStr(ctx, global, "probe", JS_NewCFunction(ctx, probe, "probe", 0)) >= 0);
    JS_FreeValue(ctx, global);
    JSValue value = evaluate(ctx, setup);
    JS_FreeValue(ctx, value);
}
static void reset(Observer *o)
{
    o->calls = o->hits = o->reuse = 0;
    memset(o->first, 0, sizeof(o->first));
}
static void validate(JSContext *ctx, const char *name, JSValueConst value)
{
    if (!strncmp(name, "map", 3)) {
        for (int i = 0; i < 32; ++i) {
            JSValue item = JS_GetPropertyUint32(ctx, value, i);
            int32_t n;
            assert(JS_ToInt32(ctx, &n, item) == 0 && n == 32 + 2 * i);
            JS_FreeValue(ctx, item);
        }
    } else if (!strncmp(name, "reduce", 6)) {
        int32_t n;
        assert(JS_ToInt32(ctx, &n, value) == 0 && n == 2016);
    } else if (!strncmp(name, "every", 5))
        assert(JS_ToBool(ctx, value) == 1);
    else if (!strncmp(name, "some", 4))
        assert(JS_ToBool(ctx, value) == 0);
    else if (!strncmp(name, "each", 4))
        assert(JS_IsUndefined(value));
    else if (!strncmp(name, "filter", 6)) {
        JSValue length = JS_GetPropertyStr(ctx, value, "length");
        int32_t n;
        assert(JS_ToInt32(ctx, &n, length) == 0 && n == 32);
        JS_FreeValue(ctx, length);
    }
}
static unsigned interrupts;
static int interrupt(JSContext *ctx, void *opaque)
{
    (void)ctx;
    return ++interrupts >= 2;
}
static int disabled(void)
{
    return getenv("QJS_DISABLE_PREPARED_CALLBACK") || getenv("QJS_DISABLE_SHARED_CALL_BYPASS") ||
           getenv("QJS_DISABLE_SHARED_ENTRY") || getenv("QJS_DISABLE_REGISTER_INTERP") ||
           getenv("QJS_DISABLE_INTERP_FRAME") || getenv("QJS_DISABLE_INTERNAL_INTERP");
}
static void semantics(void)
{
    Observer o = {0};
    JSRuntime *rt = JS_NewRuntime();
    assert(rt);
    JSContext *ctx = JS_NewContext(rt);
    assert(ctx);
    o.other = JS_NewContext(rt);
    assert(o.other);
    o.nested = evaluate(o.other, "(function otherRealm(){return {answer:42};})");
    install(ctx, &o);
    const char *names[] = {
        "mapRO",       "mapRW",     "mapPAD",           "mapRWPAD",    "mapTA",
        "mapTAW",      "mapOBJRO",  "mapOBJRW",         "reduceRO",    "reduceRW",
        "reduceRight", "reduceTA",  "reduceRightArray", "every",       "everyTA",
        "some",        "someArray", "filter",           "filterArray", "each",
        "eachTA"};
    unsigned total_hits = 0, total_reuse = 0;
    for (unsigned k = 0; k < sizeof(names) / sizeof(names[0]); ++k) {
        const char *name = names[k];
        JSValue fn = function(ctx, name);
        for (int pass = 0; pass < 3; ++pass) {
            reset(&o);
            o.exercise = pass == 2;
            JSValue value = JS_Call(ctx, fn, JS_UNDEFINED, 0, NULL);
            assert(!JS_IsException(value));
            validate(ctx, name, value);
            JS_FreeValue(ctx, value);
            assert(o.calls == 32 && !JS_FrameCallbackScopeProbe(ctx, NULL));
            if (pass == 2) {
                int misses = disabled() ||
                             (strstr(name, "RW") && getenv("QJS_DISABLE_CALLBACK_WRITE")) ||
                             (!strcmp(name, "mapTAW") && getenv("QJS_DISABLE_CALLBACK_WRITE")) ||
                             (strstr(name, "PAD") && getenv("QJS_DISABLE_CALLBACK_ARITY"));
                if (misses ? o.hits != 0 : o.hits != 32)
                    fprintf(stderr, "PREPARED_CASE %s hits=%u reuse=%u expected=%u\n", name, o.hits,
                            o.reuse, misses ? 0u : 32u);
                assert(misses ? o.hits == 0 : o.hits == 32);
                assert(misses ? o.reuse == 0 : o.reuse == 31);
                total_hits += o.hits;
                total_reuse += o.reuse;
            }
        }
        JS_FreeValue(ctx, fn);
    }
    reset(&o);
    o.exercise = 0;
    JSValue fn = function(ctx, "throwing");
    for (int pass = 0; pass < 3; ++pass) {
        reset(&o);
        JSValue value = JS_Call(ctx, fn, JS_UNDEFINED, 0, NULL);
        assert(JS_IsException(value));
        JS_FreeValue(ctx, JS_GetException(ctx));
        assert(o.calls == 9 && !JS_FrameCallbackScopeProbe(ctx, NULL));
    }
    JS_FreeValue(ctx, fn);
    fn = function(ctx, "interrupted");
    JS_SetInterruptHandler(rt, interrupt, NULL);
    JSValue value = JS_Call(ctx, fn, JS_UNDEFINED, 0, NULL);
    assert(JS_IsException(value) && interrupts >= 2);
    JS_FreeValue(ctx, JS_GetException(ctx));
    JS_SetInterruptHandler(rt, NULL, NULL);
    JS_FreeValue(ctx, fn);
    reset(&o);
    fn = function(ctx, "mapRO");
    value = JS_Call(ctx, fn, JS_UNDEFINED, 0, NULL);
    assert(!JS_IsException(value));
    validate(ctx, "mapRO", value);
    JS_FreeValue(ctx, value);
    JS_FreeValue(ctx, fn);
    assert(!JS_FrameCallbackScopeProbe(ctx, NULL));
    JS_RunGC(rt);
    JS_FreeValue(o.other, o.nested);
    JS_FreeContext(o.other);
    JS_FreeContext(ctx);
    JS_FreeRuntime(rt);
    printf("LINUX_PREPARED_SEMANTICS_OK hits=%u reuse=%u gc=%u reentry=%u interrupts=%u\n",
           total_hits, total_reuse, o.gc, o.reentries, interrupts);
#ifdef QJS_NATIVE_CALLBACK_UNWIND_TEST
    assert(vm_unwinds == o.gc);
    printf("AARCH64_PREPARED_UNWIND_OK observations=%u\n", vm_unwinds);
#endif
}
static unsigned failures, injected;
static int map_fault_reproducer;
static int write_fault_reproducer;
static size_t trial(size_t fault)
{
    Allocator memory = {0};
    Observer o = {0};
    JSRuntime *rt = JS_NewRuntime2(&functions, &memory);
    assert(rt);
    JSContext *ctx = JS_NewContext(rt);
    assert(ctx);
    install(ctx, &o);
    JSValue fn = function(ctx, map_fault_reproducer     ? "allocationMap"
                               : write_fault_reproducer ? "allocationWrite"
                                                        : "allocation");
    for (int i = 0; i < 2; ++i) {
        reset(&o);
        JSValue value = JS_Call(ctx, fn, JS_UNDEFINED, 0, NULL);
        assert(!JS_IsException(value));
        JS_FreeValue(ctx, value);
    }
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
        JS_FreeValue(ctx, value);
    assert(!JS_FrameCallbackScopeProbe(ctx, NULL));
    reset(&o);
    value = JS_Call(ctx, fn, JS_UNDEFINED, 0, NULL);
    assert(!JS_IsException(value));
    JS_FreeValue(ctx, value);
    JS_FreeValue(ctx, fn);
    JS_RunGC(rt);
    JS_FreeContext(ctx);
    JS_FreeRuntime(rt);
    assert(memory.live == 0 && memory.bytes == 0);
    return count;
}
int main(int argc, char **argv)
{
    if (argc > 1) {
        map_fault_reproducer = !strcmp(argv[1], "map-oom");
        write_fault_reproducer = !strcmp(argv[1], "write-oom");
        size_t count = trial(0);
        if (!strcmp(argv[1], "legacy-noarena")) {
            assert(getenv("QJS_DISABLE_REGISTER_INTERP") && getenv("QJS_DISABLE_INTERP_FRAME") &&
                   getenv("QJS_DISABLE_INTERNAL_INTERP") && count == 0);
            puts("LINUX_PREPARED_LEGACY_NO_ARENA_OK allocations=0 live=0 bytes=0");
            return 0;
        }
        for (size_t fault = 1; fault <= count + 1; ++fault)
            trial(fault);
        assert(count && injected && failures);
        printf("LINUX_PREPARED_OOM_OK allocations=%zu injected=%u failures=%u\n", count, injected,
               failures);
    } else
        semantics();
    return 0;
}
