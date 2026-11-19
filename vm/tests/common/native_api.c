#include "src/common/internal/upstream-compat.h"
#ifdef NDEBUG
#undef NDEBUG
#endif
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "quickjs.h"

static JSClassID resource_class;
static int finalized;
static JSValue producer;
static JSContext *finalizer_reentry_ctx;
static JSValue finalizer_reentry_func;
static int finalizer_reentry_count;
static void finalize_resource(JSRuntime *rt, JSValue value)
{
    finalized++;
    if (finalizer_reentry_ctx) {
        JSValue result =
            JS_Call(finalizer_reentry_ctx, finalizer_reentry_func, JS_UNDEFINED, 0, NULL);
        int32_t actual;
        assert(!JS_IsException(result));
        assert(!JS_ToInt32(finalizer_reentry_ctx, &actual, result) && actual == 43);
        JS_FreeValue(finalizer_reentry_ctx, result);
        finalizer_reentry_count++;
    }
}
static JSValue produce_closure(JSContext *ctx, JSValueConst this_val, int argc, JSValueConst *argv)
{
    JSValue object = JS_NewObjectClass(ctx, resource_class);
    if (JS_IsException(object))
        return object;
    JS_SetPropertyStr(ctx, object, "value", JS_NewInt32(ctx, 42));
    JSValue result = JS_Call(ctx, producer, JS_UNDEFINED, 1, &object);
    JS_FreeValue(ctx, object);
    return result;
}
static JSValue finalizer_count(JSContext *ctx, JSValueConst this_val, int argc, JSValueConst *argv)
{
    return JS_NewInt32(ctx, finalized);
}
static JSValue produce_resource(JSContext *ctx, JSValueConst this_val, int argc, JSValueConst *argv)
{
    JSValue object = JS_NewObjectClass(ctx, resource_class);
    if (JS_IsException(object))
        return object;
    assert(JS_SetPropertyStr(ctx, object, "value", JS_NewInt32(ctx, 42)) >= 0);
    if (argc && JS_ToBool(ctx, argv[0]))
        assert(JS_SetPropertyStr(ctx, object, "self", JS_DupValue(ctx, object)) >= 0);
    return object;
}
static JSValue collect_frame(JSContext *ctx, JSValueConst this_val, int argc, JSValueConst *argv)
{
    JS_RunGC(JS_GetRuntime(ctx));
    return JS_UNDEFINED;
}
static JSValue *host_arg;
static JSValue release_host_arg(JSContext *ctx, JSValueConst this_val, int argc, JSValueConst *argv)
{
    assert(host_arg);
    JS_FreeValue(ctx, *host_arg);
    *host_arg = JS_UNDEFINED;
    return JS_UNDEFINED;
}
static JSValue reenter_depth(JSContext *ctx, JSValueConst this_val, int argc, JSValueConst *argv)
{
    assert(argc == 2);
    return JS_Call(ctx, argv[0], JS_UNDEFINED, 1, argv + 1);
}
static int fresh_count;
static JSValue produce_fresh(JSContext *ctx, JSValueConst this_val, int argc, JSValueConst *argv)
{
    const char *code =
        ++fresh_count % 3 == 0 ? "(function fresh(a) { try { return 42; } finally {} })"
        : fresh_count % 3 == 1 ? "(function fresh(a,b,c) { return a===undefined ? 42 : 0; })"
                               : "(function fresh() { let a=40,b=2; return a+b; })";
    return JS_Eval(ctx, code, strlen(code), "fresh-interpreter-code", JS_EVAL_TYPE_GLOBAL);
}

static JSValue eval(JSContext *ctx, const char *s)
{
    return JS_Eval(ctx, s, strlen(s), "explicit-interpreter-api", JS_EVAL_TYPE_GLOBAL);
}
static void expect(JSContext *ctx, JSValue v, int n)
{
    if (JS_IsException(v)) {
        JSValue e = JS_GetException(ctx);
        const char *s = JS_ToCString(ctx, e);
        fprintf(stderr, "exception: %s\n", s ? s : "");
        JS_FreeCString(ctx, s);
        JS_FreeValue(ctx, e);
        assert(0);
    }
    int32_t actual;
    assert(!JS_ToInt32(ctx, &actual, v));
    assert(actual == n);
    JS_FreeValue(ctx, v);
}
static void exception(JSContext *ctx, JSValue v, int uncatchable)
{
    assert(JS_IsException(v));
    JSValue e = JS_GetException(ctx);
    assert(JS_IsUncatchableError(e) == uncatchable);
    JS_FreeValue(ctx, e);
    JS_FreeValue(ctx, v);
}
static int interrupt(FrameInterruptSource *upgrade_interrupt_source, void *opaque)
{
    JSRuntime *rt = frame_interrupt_runtime(upgrade_interrupt_source);
    return ++*(int *)opaque == 3;
}
static JSValue fail_host(JSContext *ctx, JSValueConst this_val, int argc, JSValueConst *argv)
{
    return JS_ThrowTypeError(ctx, "native bridge failure");
}
int main(void)
{
    JSRuntime *rt = JS_NewRuntime();
    JSContext *a = JS_NewContext(rt), *b = JS_NewContext(rt);
    JS_SetDumpFlags(rt, JS_ABORT_ON_LEAKS);
    JS_SetGCThreshold(rt, 1);
    expect(a,
           eval(a, "function inc(x) { return x+1; }"
                   "function deep(x) { return x ? deep(x-1)+1 : 0; }"
                   "function arity(a,b) { a=17; return a+(b===undefined?1:b); }"
                   "function bad(x) { return inc(x); } 1;"),
           1);
    JSValue global = JS_GetGlobalObject(a);
    JS_SetPropertyStr(a, global, "reenterDepth",
                      JS_NewCFunction(a, reenter_depth, "reenterDepth", 2));
    JS_NewClassID(rt, &resource_class);
    JSClassDef resource_def = {0};
    resource_def.class_name = "interpreter-resource";
    resource_def.finalizer = finalize_resource;
    assert(JS_NewClass(rt, resource_class, &resource_def) == 0);
    producer =
        eval(a, "(function producer(o) { return function consumer() { return o.value; }; })");
    JS_SetPropertyStr(a, global, "produceClosure",
                      JS_NewCFunction(a, produce_closure, "produceClosure", 0));
    JS_SetPropertyStr(a, global, "finalizerCount",
                      JS_NewCFunction(a, finalizer_count, "finalizerCount", 0));
    JSValue probe = eval(
        a,
        "(function probe() { let f=produceClosure(); f(); f=undefined; return finalizerCount(); })");
    /* A call-site cache must not prolong the lifetime of a closure's captured
       native resources after the last program reference is released. */
    expect(a, JS_Call(a, probe, JS_UNDEFINED, 0, NULL), 1);
    JS_FreeValue(a, probe);
    JS_FreeValue(a, producer);
    JS_SetPropertyStr(a, global, "produceResource",
                      JS_NewCFunction(a, produce_resource, "produceResource", 0));
    JS_SetPropertyStr(a, global, "collectFrame",
                      JS_NewCFunction(a, collect_frame, "collectFrame", 0));
    JS_SetPropertyStr(a, global, "releaseHostArg",
                      JS_NewCFunction(a, release_host_arg, "releaseHostArg", 0));
    expect(
        a,
        eval(
            a,
            "function readonlyMissing(o,x,y) { collectFrame(); return o; }"
            "function mutableMissing(o,x,y) { o=undefined; collectFrame(); return finalizerCount(); }"
            "function mutableSetMissing(o,x,y) { let z=(o=undefined); collectFrame(); return finalizerCount(); }"
            "function mutableWideMissing(a,b,c,d,o,x) { o=undefined; collectFrame(); return finalizerCount(); }"
            "function mutableWideSetMissing(a,b,c,d,o,x) { let z=(o=undefined); collectFrame(); return finalizerCount(); }"
            "function readonlyThrow(o,x) { collectFrame(); throw 'arity-error'; } 1;"),
        1);
    probe = eval(
        a, "(function readonlyLifetime() { let before=finalizerCount();"
           "let held=readonlyMissing(produceResource());"
           "if(finalizerCount()!==before) throw 'early readonly finalizer';"
           "let value=held.value; held=undefined;"
           "if(finalizerCount()!==before+1) throw 'late readonly finalizer'; return value; })");
    expect(a, JS_Call(a, probe, JS_UNDEFINED, 0, NULL), 42);
    JS_FreeValue(a, probe);
    probe = eval(
        a,
        "(function mutableLifetime() { let before=finalizerCount();"
        "if(mutableMissing(produceResource())!==before || finalizerCount()!==before+1) throw 'put_arg lifetime';"
        "before=finalizerCount();"
        "if(mutableSetMissing(produceResource())!==before || finalizerCount()!==before+1) throw 'set_arg lifetime';"
        "before=finalizerCount();"
        "if(mutableWideMissing(0,0,0,0,produceResource())!==before || finalizerCount()!==before+1) throw 'wide put_arg lifetime';"
        "before=finalizerCount();"
        "if(mutableWideSetMissing(0,0,0,0,produceResource())!==before || finalizerCount()!==before+1) throw 'wide set_arg lifetime';"
        "return 42; })");
    expect(a, JS_Call(a, probe, JS_UNDEFINED, 0, NULL), 42);
    JS_FreeValue(a, probe);
    probe = eval(
        a,
        "(function cyclicReadonly() { let before=finalizerCount();"
        "let held=readonlyMissing(produceResource(true));"
        "if(held.self!==held || held.value!==42 || finalizerCount()!==before) throw 'lost GC root';"
        "held=undefined; collectFrame();"
        "if(finalizerCount()!==before+1) throw 'cycle leak'; return 42; })");
    expect(a, JS_Call(a, probe, JS_UNDEFINED, 0, NULL), 42);
    JS_FreeValue(a, probe);
    int before = finalized;
    probe = eval(a, "(function missingException() { return readonlyThrow(produceResource()); })");
    exception(a, JS_Call(a, probe, JS_UNDEFINED, 0, NULL), 0);
    JS_FreeValue(a, probe);
    assert(finalized == before + 1);
    /* A host may release its argv owner during a callback. Public roots must
       therefore retain their own copies even for read-only missing slots. */
    JSValue host_value = produce_resource(a, JS_UNDEFINED, 0, NULL);
    host_arg = &host_value;
    before = finalized;
    probe = eval(
        a, "(function hostReadonly(o,x) { releaseHostArg(); collectFrame(); return o.value; })");
    expect(a, JS_Call(a, probe, JS_UNDEFINED, 1, &host_value), 42);
    JS_FreeValue(a, probe);
    assert(JS_IsUndefined(host_value) && finalized == before + 1);
    host_arg = NULL;
    JS_SetPropertyStr(a, global, "produceFresh",
                      JS_NewCFunction(a, produce_fresh, "produceFresh", 0));
    probe = eval(
        a,
        "(function turnover() { let sum=0; for(let i=0;i<512;i++) { let f=produceFresh(); sum+=f(); f=undefined; } return sum; })");
    expect(a, JS_Call(a, probe, JS_UNDEFINED, 0, NULL), 512 * 42);
    JS_FreeValue(a, probe);
    JSValue fn = JS_GetPropertyStr(a, global, "arity"), arg = JS_NewInt32(a, 3);
    expect(a, JS_Call(a, fn, JS_UNDEFINED, 1, &arg), 18);
    expect(a, JS_DupValue(a, arg), 3);
    JS_FreeValue(a, fn);
    fn = JS_GetPropertyStr(a, global, "deep");
    JS_SetMaxStackSize(rt, 4 * 1024 * 1024);
    /* ASan's legacy C frames consume much more native stack. The explicit
       backend still exercises segment growth at the smaller shared depth. */
#ifdef FRAME_TEST_ASAN
    const int deep_count = 64;
#else
    const int deep_count = 512;
#endif
    arg = JS_NewInt32(a, deep_count);
    expect(a, JS_Call(a, fn, JS_UNDEFINED, 1, &arg), deep_count);
    /* Both explicit activations grow segments. The inner root's predecessor
       is a native frame; returning must resume only its own activation. */
    probe = eval(a, "(function mixed(n) { return n ? mixed(n-1)+1 : reenterDepth(deep,64); })");
    expect(a, JS_Call(a, probe, JS_UNDEFINED, 1, &arg), deep_count + 64);
    JS_FreeValue(a, probe);
    /* First return through a deep supported chain, then pad another call. */
    before = finalized;
    probe = eval(
        a,
        "(function windowAfterGrowth(n) { deep(n); let held=readonlyMissing(produceResource()); return held.value; })");
    expect(a, JS_Call(a, probe, JS_UNDEFINED, 1, &arg), 42);
    JS_FreeValue(a, probe);
    assert(finalized == before + 1);
    expect(
        a,
        eval(
            a,
            "function windowRecurse(n,o,x) { if(n) return windowRecurse(n-1,o)+1;"
            "collectFrame(); if(x!==undefined) throw 'stale recursive pad'; return o.value; }"
            "function windowRecProbe(n) { return windowRecurse(n,produceResource()); }"
            "function windowSelect(a,b,c) { return a+(b===undefined?10:b)+(c===undefined?100:c); } 1;"),
        1);
    before = finalized;
    probe = JS_GetPropertyStr(a, global, "windowRecProbe");
    expect(a, JS_Call(a, probe, JS_UNDEFINED, 1, &arg), 42 + deep_count);
    JS_FreeValue(a, probe);
    assert(finalized == before + 1);
    /* Check the zero-argument result inside JS: the same reused slots must
       first hold supplied values and then become undefined again. */
    probe =
        eval(a, "(function windowReuse() { let sum=0; for(let i=0;i<64;i++) {"
                "sum+=windowSelect(1,2,3); sum+=windowSelect(1); sum+=windowSelect(1,2);"
                "if(!Number.isNaN(windowSelect())) throw 'zero-argument pad'; } return sum; })");
    expect(a, JS_Call(a, probe, JS_UNDEFINED, 0, NULL), 64 * (6 + 111 + 103));
    JS_FreeValue(a, probe);
    /* Sweep segment boundaries with the largest supported formal window.
       Lifetime and GC checks apply to both reuse and the contiguous fallback. */
    char window_code[4096];
    size_t window_pos = (size_t)snprintf(window_code, sizeof(window_code), "function windowMany(");
    for (int parameter = 0; parameter < 128; parameter++)
        window_pos += (size_t)snprintf(window_code + window_pos, sizeof(window_code) - window_pos,
                                       "%sp%d", parameter ? "," : "", parameter);
    assert(window_pos + 256 < sizeof(window_code));
    snprintf(window_code + window_pos, sizeof(window_code) - window_pos,
             ") { collectFrame(); if(p127!==undefined) throw 'wide pad'; return p0.value; } 1;");
    expect(a, eval(a, window_code), 1);
    /* A directly grown child, rather than intervening recursive parents,
       leaves the allocator on a different segment from the caller's owner. */
    window_pos = (size_t)snprintf(window_code, sizeof(window_code), "function windowBig(");
    for (int parameter = 0; parameter < 128; parameter++)
        window_pos += (size_t)snprintf(window_code + window_pos, sizeof(window_code) - window_pos,
                                       "%sp%d", parameter ? "," : "", parameter);
    window_pos +=
        (size_t)snprintf(window_code + window_pos, sizeof(window_code) - window_pos, ") { let ");
    for (int local = 0; local < 128; local++)
        window_pos += (size_t)snprintf(window_code + window_pos, sizeof(window_code) - window_pos,
                                       "%sv%d", local ? "," : "", local);
    assert(window_pos + 128 < sizeof(window_code));
    snprintf(window_code + window_pos, sizeof(window_code) - window_pos, "; return p0; } 1;");
    expect(a, eval(a, window_code), 1);
    before = finalized;
    probe = eval(
        a,
        "(function directWindowGrowth() { windowBig(0); let held=readonlyMissing(produceResource()); return held.value; })");
    expect(a, JS_Call(a, probe, JS_UNDEFINED, 0, NULL), 42);
    JS_FreeValue(a, probe);
    assert(finalized == before + 1);
    expect(
        a,
        eval(
            a,
            "function windowBoundary(n) { return n ? windowBoundary(n-1)+1 : windowMany(produceResource()); }"
            "function windowUnwind(n,o,x) { if(n) return windowUnwind(n-1,o); collectFrame(); throw 'window-error'; }"
            "function windowUnwindProbe(n) { return windowUnwind(n,produceResource()); } 1;"),
        1);
    probe = JS_GetPropertyStr(a, global, "windowBoundary");
    const int boundary_count = deep_count < 96 ? deep_count : 96;
    for (int boundary = 0; boundary <= boundary_count; boundary++) {
        before = finalized;
        JSValue boundary_arg = JS_NewInt32(a, boundary);
        expect(a, JS_Call(a, probe, JS_UNDEFINED, 1, &boundary_arg), 42 + boundary);
        assert(finalized == before + 1);
    }
    JS_FreeValue(a, probe);
    before = finalized;
    probe = JS_GetPropertyStr(a, global, "windowUnwindProbe");
    exception(a, JS_Call(a, probe, JS_UNDEFINED, 1, &arg), 0);
    JS_FreeValue(a, probe);
    assert(finalized == before + 1);
    JS_SetMaxStackSize(rt, 32768);
    arg = JS_NewInt32(a, 100000);
    exception(a, JS_Call(a, fn, JS_UNDEFINED, 1, &arg), 0);
    JS_SetMaxStackSize(rt, 1024 * 1024);
    arg = JS_NewInt32(a, 16);
    expect(a, JS_Call(a, fn, JS_UNDEFINED, 1, &arg), 16);
    int polls = 0;
    JS_SetInterruptHandler(rt, interrupt, &polls);
    JSValue busy = eval(a, "(function busy() { for (;;) deep(16); })");
    exception(a, JS_Call(a, busy, JS_UNDEFINED, 0, NULL), 1);
    JS_FreeValue(a, busy);
    assert(polls == 3);
    JS_SetInterruptHandler(rt, NULL, NULL);
    JS_FreeValue(a, fn);
    fn = JS_GetPropertyStr(a, global, "bad");
    arg = JS_NewBigInt64(a, 1);
    exception(a, JS_Call(a, fn, JS_UNDEFINED, 1, &arg), 0);
    JS_FreeValue(a, arg);
    JS_FreeValue(a, fn);
    expect(b, eval(b, "globalThis.realm=200; function child(x) { return x+1; } 1;"), 1);
    fn = eval(b, "(function foreign(x) { child(x); return realm+child(x); })");
    arg = JS_NewInt32(a, 2);
    expect(a, JS_Call(a, fn, JS_UNDEFINED, 1, &arg), 203);
    assert(JS_SetPropertyStr(a, global, "foreign", fn) >= 0);
    expect(a, eval(a, "globalThis.realm=10; function local(x) { return foreign(x)+realm; } 1;"), 1);
    fn = JS_GetPropertyStr(a, global, "local");
    expect(a, JS_Call(a, fn, JS_UNDEFINED, 1, &arg), 213);
    JS_FreeValue(a, fn);
    /* Supported classification survives bytecode round-trip as unknown. */
    const char *code = "(function loaded(x,y) { return x+(y===undefined?3:y); })";
    fn = JS_Eval(a, code, strlen(code), "interpreter-roundtrip",
                 JS_EVAL_TYPE_GLOBAL | JS_EVAL_FLAG_COMPILE_ONLY);
    size_t size;
    uint8_t *data = JS_WriteObject(a, &size, fn, JS_WRITE_OBJ_BYTECODE);
    assert(data);
    JS_FreeValue(a, fn);
    fn = JS_ReadObject(a, data, size, JS_READ_OBJ_BYTECODE);
    js_free(a, data);
    fn = JS_EvalFunction(a, fn);
    assert(!JS_IsException(fn));
    expect(a, JS_Call(a, fn, JS_UNDEFINED, 1, &arg), 5);
    JS_FreeValue(a, fn);
    /* A last local owner is freed by the return handler. Its native finalizer
       reenters JS while that handler's fixed machine state must survive. */
    finalizer_reentry_func = eval(a, "(function reenterFinalizer() { return inc(42); })");
    finalizer_reentry_ctx = a;
    fn = eval(a, "(function freeOnReturn() { let owned=produceResource(); return 17; })");
    before = finalized;
    for (int repeat = 0; repeat < 16; repeat++)
        expect(a, JS_Call(a, fn, JS_UNDEFINED, 0, NULL), 17);
    assert(finalized == before + 16 && finalizer_reentry_count == 16);
    /* Indexed-read and read/modify/write boundaries may release the receiver's
       last owner. Reentrant finalizers must preserve the loaded result and
       the enclosing frame's exception/checkpoint state. A variable key keeps
       these operations distinct from the named-field opcode. */
    expect(
        a,
        eval(
            a,
            "function indexedTemporary(k) { return produceResource()[k]; }"
            "function indexedUpdate(k) { return produceResource()[k]++; }"
            "function indexedKeyThrow(k) { try { produceResource()[k]; }"
            "catch(e) { if(e!=='indexed-key') throw e; return 42; } throw 'missing key error'; } 1;"),
        1);
    const char *indexed_names[] = {"indexedTemporary", "indexedUpdate", "indexedKeyThrow"};
    for (int indexed_case = 0; indexed_case < 3; indexed_case++) {
        JSValue indexed_fn = JS_GetPropertyStr(a, global, indexed_names[indexed_case]);
        JSValue indexed_key =
            indexed_case < 2
                ? JS_NewString(a, "value")
                : eval(a, "({[Symbol.toPrimitive]() { collectFrame(); throw 'indexed-key'; }})");
        before = finalized;
        int indexed_reentries = finalizer_reentry_count;
        for (int repeat = 0; repeat < 16; repeat++)
            expect(a, JS_Call(a, indexed_fn, JS_UNDEFINED, 1, &indexed_key), 42);
        assert(finalized == before + 16 && finalizer_reentry_count == indexed_reentries + 16);
        JS_FreeValue(a, indexed_key);
        JS_FreeValue(a, indexed_fn);
    }
    expect(
        a,
        eval(
            a,
            "function indexedReadonly() { 'use strict'; let a=[1,2,3]; a.pop();"
            "Object.defineProperty(a,'length',{writable:false});"
            "try { a[a.length]=4; } catch(e) { if(!(e instanceof TypeError)) throw e; return a.length+40; }"
            "throw 'readonly array length accepted'; } indexedReadonly();"),
        42);
    finalizer_reentry_ctx = NULL;
    JS_FreeValue(a, finalizer_reentry_func);
    JS_FreeValue(a, fn);
    /* Captured formal slots own copies even though writes come from a child.
       The host's const argv remains intact after the parent returns/unwinds. */
    fn = eval(
        a,
        "(function capturedHostArg(x,y) { function replace() { x=39; y=4; } replace(); return function readCapturedHostArg() { return x+y; }; })");
    arg = JS_NewInt32(a, 3);
    JSValue captured_result = JS_Call(a, fn, JS_UNDEFINED, 1, &arg);
    assert(!JS_IsException(captured_result));
    expect(a, JS_DupValue(a, arg), 3);
    JS_RunGC(rt);
    expect(a, JS_Call(a, captured_result, JS_UNDEFINED, 0, NULL), 43);
    JS_FreeValue(a, captured_result);
    JS_FreeValue(a, fn);
    /* The escaped cell must detach before a local's last release reenters JS.
       Native return spill/reload also retains the returned closure itself. */
    finalizer_reentry_func =
        eval(a, "(function readClosedDuringCleanup() { return suspendedCapture()+1; })");
    finalizer_reentry_ctx = a;
    fn = eval(
        a,
        "(function captureCleanup() { let value=42, owned=produceResource(); function readClosed() { return value; } suspendedCapture=readClosed; return readClosed; })");
    before = finalized;
    int reentries_before = finalizer_reentry_count;
    for (int repeat = 0; repeat < 16; repeat++) {
        captured_result = JS_Call(a, fn, JS_UNDEFINED, 0, NULL);
        assert(!JS_IsException(captured_result));
        expect(a, JS_Call(a, captured_result, JS_UNDEFINED, 0, NULL), 42);
        JS_FreeValue(a, captured_result);
    }
    assert(finalized == before + 16 && finalizer_reentry_count == reentries_before + 16);
    finalizer_reentry_ctx = NULL;
    JS_FreeValue(a, finalizer_reentry_func);
    JS_FreeValue(a, fn);
    expect(a, eval(a, "suspendedCapture=undefined; 1;"), 1);
    JS_SetPropertyStr(a, global, "failHost", JS_NewCFunction(a, fail_host, "failHost", 0));
    expect(
        a,
        eval(
            a,
            "function hostErrorLeaf() { return failHost(); } function hostErrorCaller() { return hostErrorLeaf(); } 1;"),
        1);
    fn = JS_GetPropertyStr(a, global, "hostErrorCaller");
    /* Cold and warm targets, including a tail continuation after the bytecode,
       must enter exception unwind rather than execute the next instruction. */
    for (int repeat = 0; repeat < 4; repeat++)
        exception(a, JS_Call(a, fn, JS_UNDEFINED, 0, NULL), 0);
    JS_FreeValue(a, fn);
    JS_FreeValue(a, global);
    JS_RunGC(rt);
    JS_FreeContext(b);
    JS_FreeContext(a);
    JS_FreeRuntime(rt);
    puts("explicit frame API: passed");
    return 0;
}
