/* Array-copy ownership, public embedding, bounded mutation-phase OOM and GC
 * regressions. Numeric private ABI views below only observe path coverage and
 * the actual allocation window; engine code uses its ordinary C declarations.
 * No JavaScript executes from a finalizer or allocation callback. */
#ifdef NDEBUG
#undef NDEBUG
#endif
#include "quickjs.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
#include <windows.h>
#endif
static void suppress_error_box(void)
{
#ifdef _WIN32
    SetErrorMode(SEM_FAILCRITICALERRORS | SEM_NOGPFAULTERRORBOX);
#endif
}
static JSClassID resource_class;
static unsigned finalized[8];
static void finalize(JSRuntime *rt, JSValue v)
{
    uintptr_t id = (uintptr_t)JS_GetOpaque(v, resource_class);
    (void)rt;
    assert(id > 0 && id < 8);
    finalized[id]++;
}
static JSValue make_resource(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    int32_t id = 0;
    JSValue v;
    (void)self;
    if (argc < 1 || JS_ToInt32(ctx, &id, argv[0]) < 0)
        return JS_EXCEPTION;
    v = JS_NewObjectClass(ctx, resource_class);
    if (!JS_IsException(v))
        JS_SetOpaque(v, (void *)(uintptr_t)id);
    return v;
}
static JSValue count_resource(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    int32_t id = 0;
    (void)self;
    if (argc < 1 || JS_ToInt32(ctx, &id, argv[0]) < 0)
        return JS_EXCEPTION;
    assert(id > 0 && id < 8);
    return JS_NewInt32(ctx, finalized[id]);
}
static JSValue collect(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)self;
    (void)argc;
    (void)argv;
    JS_RunGC(JS_GetRuntime(ctx));
    return JS_UNDEFINED;
}
static JSValue evaluate(JSContext *ctx, const char *text)
{
    return JS_Eval(ctx, text, strlen(text), "splice-consumer.js", JS_EVAL_TYPE_GLOBAL);
}
static void checked_eval(JSContext *ctx, const char *text)
{
    JSValue v = evaluate(ctx, text);
    if (JS_IsException(v)) {
        JSValue e = JS_GetException(ctx);
        const char *s = JS_ToCString(ctx, e);
        fprintf(stderr, "%s\n", s ? s : "exception");
        JS_FreeCString(ctx, s);
        JS_FreeValue(ctx, e);
        assert(0);
    }
    JS_FreeValue(ctx, v);
}
static void lifetimes(void)
{
    JSRuntime *rt = JS_NewRuntime();
    assert(rt);
    JSContext *ctx = JS_NewContext(rt);
    assert(ctx);
    JSClassDef cls = {0};
    cls.class_name = "SpliceResource";
    cls.finalizer = finalize;
    JS_NewClassID(rt, &resource_class);
    assert(JS_NewClass(rt, resource_class, &cls) == 0);
    JSValue g = JS_GetGlobalObject(ctx);
    assert(JS_SetPropertyStr(ctx, g, "makeResource",
                             JS_NewCFunction(ctx, make_resource, "makeResource", 1)) > 0);
    assert(JS_SetPropertyStr(ctx, g, "resourceCount",
                             JS_NewCFunction(ctx, count_resource, "resourceCount", 1)) > 0);
    assert(JS_SetPropertyStr(ctx, g, "collect", JS_NewCFunction(ctx, collect, "collect", 0)) > 0);
    JS_FreeValue(ctx, g);
    checked_eval(
        ctx,
        "(function(){"
        " let a=[makeResource(1),makeResource(2),makeResource(3)];"
        " a.constructor={get [Symbol.species](){collect();return function(){"
        "   return new Proxy({}, {defineProperty(){return true},set(){return true}});"
        " }}};"
        " a.splice(1,1,7,8,9);"
        " if(resourceCount(2)!==1||resourceCount(1)!==0||resourceCount(3)!==0)throw Error('prompt release');"
        " if(a.length!==5||a[4]===undefined)throw Error('tail lost');"
        " a.length=0;"
        " if(resourceCount(1)!==1||resourceCount(3)!==1)throw Error('tail ownership');"
        " let x=makeResource(4);a=[x,x,x];"
        " let out=a.splice(1,1,x,x,x);x=null;collect();"
        " if(resourceCount(4)!==0)throw Error('alias freed');"
        " a.length=0;collect();if(resourceCount(4)!==0)throw Error('removed lost');"
        " out.length=0;if(resourceCount(4)!==1)throw Error('alias retained');"
        " x=makeResource(5);a=[x];a.push(a,x);x.back=a;"
        " let removed=a.splice(0,1,x,x,42,43);x=null;a=null;removed.length=0;collect();"
        " if(resourceCount(5)!==1)throw Error('cyclic transferred ownership retained');"
        "})();");
    JS_RunGC(rt);
    JS_FreeContext(ctx);
    JS_FreeRuntime(rt);
    for (unsigned i = 1; i <= 5; i++)
        assert(finalized[i] == 1);
}
typedef union Header {
    size_t size;
    long double alignment;
    unsigned char pad[16];
} Header;
typedef struct Memory {
    size_t attempts, fail_at, live, bytes;
    unsigned failed;
} Memory;
static Memory *armed_memory;
static size_t armed_offset;
static JSValue arm_failure(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)ctx;
    (void)self;
    (void)argc;
    (void)argv;
    assert(armed_memory);
    armed_memory->fail_at = armed_memory->attempts + armed_offset;
    return JS_UNDEFINED;
}
static int reject(Memory *m)
{
    m->attempts++;
    if (m->fail_at && m->attempts == m->fail_at) {
        m->failed++;
        return 1;
    }
    return 0;
}
static void *allocate(void *opaque, size_t size)
{
    Memory *m = opaque;
    Header *h;
    if (reject(m) || size > SIZE_MAX - sizeof(*h))
        return NULL;
    h = malloc(sizeof(*h) + size);
    if (!h)
        return NULL;
    h->size = size;
    m->live++;
    m->bytes += size;
    return h + 1;
}
static void release(void *opaque, void *ptr)
{
    Memory *m = opaque;
    if (!ptr)
        return;
    Header *h = (Header *)ptr - 1;
    assert(m->live && m->bytes >= h->size);
    m->live--;
    m->bytes -= h->size;
    free(h);
}
static void *allocate_zero(void *opaque, size_t n, size_t size)
{
    if (size && n > SIZE_MAX / size)
        return NULL;
    void *p = allocate(opaque, n * size);
    if (p)
        memset(p, 0, n * size);
    return p;
}
static void *resize(void *opaque, void *ptr, size_t size)
{
    Memory *m = opaque;
    Header *h;
    size_t old;
    if (!ptr)
        return allocate(opaque, size);
    if (!size) {
        release(opaque, ptr);
        return NULL;
    }
    if (reject(m) || size > SIZE_MAX - sizeof(*h))
        return NULL;
    h = (Header *)ptr - 1;
    old = h->size;
    h = realloc(h, sizeof(*h) + size);
    if (!h)
        return NULL;
    h->size = size;
    m->bytes = m->bytes - old + size;
    return h + 1;
}
static size_t usable(const void *ptr)
{
    return ptr ? ((const Header *)ptr - 1)->size : 0;
}
static void allocation_failures(void)
{
    JSMallocFunctions mf = {allocate_zero, allocate, release, resize, usable};
    unsigned failures = 0, successes = 0;
    for (size_t n = 1; n <= 100; n++) {
        Memory m = {0};
        JSRuntime *rt = JS_NewRuntime2(&mf, &m);
        assert(rt);
        JSContext *ctx = JS_NewContext(rt);
        assert(ctx);
        JSValue g = JS_GetGlobalObject(ctx);
        assert(JS_SetPropertyStr(ctx, g, "armFailure",
                                 JS_NewCFunction(ctx, arm_failure, "armFailure", 0)) > 0);
        JS_FreeValue(ctx, g);
        checked_eval(
            ctx,
            "var a=Array.from({length:128},(_,i)=>i),output=[0,0],insertion=Array.from({length:80},(_,i)=>900+i);"
            "a.constructor={[Symbol.species]:function(){armFailure();return output}};function run(){"
            "const r=a.splice(63,2,...insertion);"
            "if(a.length!==206||r.length!==2||r[0]!==63||r[1]!==64||a[62]!==62||a[63]!==900||a[142]!==979||a[143]!==65||a[205]!==127)throw Error('splice mismatch');return 206;}");
        g = JS_GetGlobalObject(ctx);
        JSValue fn = JS_GetPropertyStr(ctx, g, "run");
        JS_FreeValue(ctx, g);
        armed_memory = &m;
        armed_offset = n;
        JSValue result = JS_Call(ctx, fn, JS_UNDEFINED, 0, NULL);
        m.fail_at = 0;
        armed_memory = NULL;
        if (JS_IsException(result)) {
            JSValue e = JS_GetException(ctx);
            const char *s = JS_ToCString(ctx, e);
            assert(m.failed == 1 && (!s || !strstr(s, "splice mismatch")));
            JS_FreeCString(ctx, s);
            JS_FreeValue(ctx, e);
            failures++;
        } else {
            int32_t value = 0;
            assert(JS_ToInt32(ctx, &value, result) == 0 && value == 206);
            successes++;
        }
        JS_FreeValue(ctx, result);
        JS_FreeValue(ctx, fn);
        checked_eval(ctx, "Object.getOwnPropertyNames(a);a.length=0;");
        JS_RunGC(rt);
        JS_FreeContext(ctx);
        JS_FreeRuntime(rt);
        assert(m.live == 0 && m.bytes == 0);
    }
    assert(failures && successes);
    printf("allocation failure sites=%u success paths=%u\n", failures, successes);
}
static void inherited_consumer_main(void)
{
    suppress_error_box();
    setbuf(stdout, NULL);
    lifetimes();
    allocation_failures();
    puts(
        "splice public API, prompt resource release, alias, GC and bounded mutation-phase OOM passed");
    return;
}

/* Test-only numeric ABI view; engine code uses its actual C declarations. */
#include "interpreter-private-abi-values.h"
extern int JS_FrameArrayCopySubArray(JSContext *, JSValue, int64_t, int64_t, int64_t, int);

static int dense(JSValue value)
{
    const unsigned char *p = (const unsigned char *)JS_VALUE_GET_PTR(value);
    return !!(p[QJS_ABI_BIT_JSObject_fast_array_BYTE] & QJS_ABI_BIT_JSObject_fast_array_MASK);
}
static JSContext *resource_context(JSRuntime *rt)
{
    JSContext *ctx = JS_NewContext(rt);
    assert(ctx);
    resource_class = 0;
    JSClassDef cls = {0};
    cls.class_name = "CopyResource";
    cls.finalizer = finalize;
    JS_NewClassID(rt, &resource_class);
    assert(JS_NewClass(rt, resource_class, &cls) == 0);
    JSValue g = JS_GetGlobalObject(ctx);
    assert(JS_SetPropertyStr(ctx, g, "makeResource",
                             JS_NewCFunction(ctx, make_resource, "makeResource", 1)) > 0);
    assert(JS_SetPropertyStr(ctx, g, "resourceCount",
                             JS_NewCFunction(ctx, count_resource, "resourceCount", 1)) > 0);
    assert(JS_SetPropertyStr(ctx, g, "collect", JS_NewCFunction(ctx, collect, "collect", 0)) > 0);
    JS_FreeValue(ctx, g);
    return ctx;
}
static void prefix_ownership(void)
{
    JSRuntime *rt = JS_NewRuntime();
    assert(rt);
    JSContext *ctx = resource_context(rt);
    checked_eval(
        ctx,
        "(function(){for(const n of [1,2,4,17,64])for(const gap of [1,2,8,32])for(const d of [0,1]){"
        " const start=Math.floor(n/2), deleted=Math.min(d,n-start), added=gap+deleted;"
        " const before=resourceCount(6),a=Array.from({length:n},()=>makeResource(6));"
        " const items=Array.from({length:added},(_,i)=>900+i),out=a.splice(start,d,...items);"
        " if(a.length!==n+gap||out.length!==deleted||resourceCount(6)!==before)throw Error('prefix lifetime');"
        " for(let i=0;i<added;i++)if(a[start+i]!==900+i)throw Error('insert values');"
        " for(let i=0;i<start;i++)if(typeof a[i]!=='object')throw Error('left reference');"
        " for(let i=start+added;i<a.length;i++)if(typeof a[i]!=='object')throw Error('tail reference');"
        " out.length=0;if(resourceCount(6)!==before+deleted)throw Error('removed ownership');"
        " a.length=0;if(resourceCount(6)!==before+n)throw Error('prefix retained');collect();"
        "}let a=[makeResource(7)];a.push(a);a.splice(0,0,7,8,9);"
        "if(a[4]!==a||resourceCount(7)!==0)throw Error('receiver alias');"
        "a.length=0;if(resourceCount(7)!==1)throw Error('receiver release');})();");
    JS_RunGC(rt);
    JS_FreeContext(ctx);
    JS_FreeRuntime(rt);
    assert(finalized[6] == 704 && finalized[7] == 1);
    puts("prefix overlap references, prompt release, receiver alias and GC passed");
}
static void early_prototypes(void)
{
    const char *scripts[] = {
        "var trap=-1;Object.defineProperty(Object.prototype,'5',{set(v){trap=v},configurable:true});"
        "var a=[0,1,2,3];a.splice(0,0,7,8,9);"
        "if(trap!==2||Object.hasOwn(a,'5')||a.length!==7||a[6]!==3)throw Error('Object prototype setter');",
        "var trap=-1;Object.setPrototypeOf(Array.prototype,Object.create(Object.prototype,{5:{set(v){trap=v},configurable:true}}));"
        "var a=[0,1,2,3];a.splice(0,0,7,8,9);"
        "if(trap!==2||Object.hasOwn(a,'5')||a.length!==7||a[6]!==3)throw Error('Array prototype chain');"};
    for (unsigned i = 0; i < sizeof(scripts) / sizeof(scripts[0]); i++) {
        JSRuntime *rt = JS_NewRuntime();
        assert(rt);
        JSContext *ctx = JS_NewContext(rt);
        assert(ctx);
        checked_eval(ctx, scripts[i]);
        JS_FreeContext(ctx);
        JS_FreeRuntime(rt);
    }
    puts("prototype mutation in fresh embedding contexts passed");
}
static void private_boundaries(void)
{
    JSRuntime *rt = JS_NewRuntime();
    assert(rt);
    JSContext *ctx = JS_NewContext(rt);
    assert(ctx);
    JSValue a = evaluate(ctx, "(function(){const a=[0,1,2,3];a.splice(0,0,7,8,9);return a})()");
    assert(!JS_IsException(a));
    int hit = dense(a), enabled = !getenv("QJS_DISABLE_ARRAY_COPY_GROW");
    assert(hit == enabled);
    printf("private dense coverage=%d\n", hit);
    JS_FreeValue(ctx, a);

    a = JS_NewArray(ctx);
    assert(!JS_IsException(a));
    for (unsigned i = 0; i < 3; i++)
        assert(JS_SetPropertyUint32(ctx, a, i, JS_NewInt32(ctx, i)) > 0);
    /* A direct unknown C-frame call must use the original operation. */
    assert(JS_FrameArrayCopySubArray(ctx, a, 3, 0, 3, -1) == 0);
    assert(!dense(a));
    for (unsigned i = 0; i < 6; i++) {
        JSValue v = JS_GetPropertyUint32(ctx, a, i);
        int32_t n = -1;
        assert(JS_ToInt32(ctx, &n, v) == 0 && n == (int32_t)(i % 3));
        JS_FreeValue(ctx, v);
    }
    JS_FreeValue(ctx, a);

    /* This call exceeds the native frame's 16-bit arg_count. The worker must
     * not use that truncated count as an argv range bound. */
    const int argc = 65540;
    JSValue *argv = malloc((size_t)argc * sizeof(*argv));
    assert(argv);
    for (int i = 0; i < argc; i++)
        argv[i] = JS_NewInt32(ctx, i);
    argv[0] = JS_NewInt32(ctx, 0);
    argv[1] = JS_NewInt32(ctx, 0);
    a = JS_NewArray(ctx);
    assert(!JS_IsException(a));
    for (unsigned i = 0; i < 4; i++)
        assert(JS_SetPropertyUint32(ctx, a, i, JS_NewInt32(ctx, i)) > 0);
    JSValue fn = JS_GetPropertyStr(ctx, a, "splice"), v = JS_Call(ctx, fn, a, argc, argv);
    if (JS_IsException(v)) {
        JSValue e = JS_GetException(ctx);
        const char *str = JS_ToCString(ctx, e);
        assert(str && strstr(str, "stack"));
        puts("wide call safely rejected by stack policy");
        JS_FreeCString(ctx, str);
        JS_FreeValue(ctx, e);
    } else {
        JSValue length = JS_GetPropertyStr(ctx, a, "length");
        int32_t n = 0;
        assert(JS_ToInt32(ctx, &n, length) == 0 && n == argc + 2);
        JS_FreeValue(ctx, length);
        JSValue first = JS_GetPropertyUint32(ctx, a, 0),
                last = JS_GetPropertyUint32(ctx, a, argc + 1);
        assert(JS_ToInt32(ctx, &n, first) == 0 && n == 2);
        assert(JS_ToInt32(ctx, &n, last) == 0 && n == 3);
        JS_FreeValue(ctx, first);
        JS_FreeValue(ctx, last);
        puts("wide call accepted with correct values");
    }
    JS_FreeValue(ctx, v);
    JS_FreeValue(ctx, fn);
    JS_FreeValue(ctx, a);
    for (int i = 0; i < argc; i++)
        JS_FreeValue(ctx, argv[i]);
    free(argv);
    JS_RunGC(rt);
    JS_FreeContext(ctx);
    JS_FreeRuntime(rt);
}
static int regular_copy_main(void)
{
    suppress_error_box();
    setbuf(stdout, NULL);
    prefix_ownership();
    early_prototypes();
    private_boundaries();
    inherited_consumer_main();
    puts("array-copy additional embedding coverage passed");
    return 0;
}

static JSRuntime *stress_runtime;
static void *expected_vector;
static unsigned armed_gc, gc_runs;
static void before_allocation(void *pointer, int resizing)
{
    if (!armed_gc)
        return;
    if (!getenv("QJS_DISABLE_ARRAY_COPY_GROW") && (!resizing || pointer != expected_vector))
        return;
    armed_gc = 0;
    if (!getenv("QJS_DISABLE_ARRAY_COPY_GROW"))
        assert(resizing && pointer == expected_vector);
    gc_runs++;
    /* One controlled collector invocation at the same pre-allocation window
     * as the engine's GC trigger, after all observable species operations.
     * No JavaScript runs in allocator/finalizer callbacks. */
    JS_RunGC(stress_runtime);
}
static void *stress_allocate(void *opaque, size_t size)
{
    before_allocation(NULL, 0);
    return allocate(opaque, size);
}
static void *stress_zero(void *opaque, size_t n, size_t size)
{
    before_allocation(NULL, 0);
    return allocate_zero(opaque, n, size);
}
static void *stress_resize(void *opaque, void *pointer, size_t size)
{
    before_allocation(pointer, 1);
    return resize(opaque, pointer, size);
}
static JSValue arm_copy_gc(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)ctx;
    (void)self;
    assert(argc == 1 && JS_IsObject(argv[0]));
    const unsigned char *p = (const unsigned char *)JS_VALUE_GET_PTR(argv[0]);
    memcpy(&expected_vector, p + QJS_ABI_OFF_JSObject_u_array_u_values, sizeof(expected_vector));
    uint32_t capacity = 0;
    memcpy(&capacity, p + QJS_ABI_OFF_JSObject_u_array_u1, sizeof(capacity));
    assert(expected_vector && capacity < 638);
    armed_gc = 1;
    return JS_UNDEFINED;
}
static int gc_copy_main(void)
{
    suppress_error_box();
    setbuf(stdout, NULL);
    JSMallocFunctions mf = {stress_zero, stress_allocate, release, stress_resize, usable};
    Memory memory = {0};
    JSRuntime *rt = JS_NewRuntime2(&mf, &memory);
    assert(rt);
    stress_runtime = rt;
    JSContext *ctx = resource_context(rt);
    JSValue global = JS_GetGlobalObject(ctx);
    assert(JS_SetPropertyStr(ctx, global, "armCopyGC",
                             JS_NewCFunction(ctx, arm_copy_gc, "armCopyGC", 1)) > 0);
    JS_FreeValue(ctx, global);
    checked_eval(
        ctx,
        "(function(){let garbage=makeResource(5);garbage.self=garbage;garbage=null;"
        " const a=Array.from({length:128},()=>makeResource(6));"
        " const insertion=Array.from({length:512},()=>makeResource(7));"
        " const output={set length(v){armCopyGC(a)}};"
        " a.constructor={[Symbol.species]:function(){return output}};"
        " const result=a.splice(63,2,...insertion);"
        " if(result!==output||a.length!==638||resourceCount(5)!==1)throw Error('collector window');"
        " if(resourceCount(6)!==0||resourceCount(7)!==0)throw Error('live root lost');"
        " for(let i=0;i<512;i++)if(a[i+63]!==insertion[i])throw Error('argument root');"
        " a.length=0;if(resourceCount(6)!==126||resourceCount(7)!==0)throw Error('receiver root');"
        " delete output[0];delete output[1];"
        " insertion.length=0;if(resourceCount(6)!==128||resourceCount(7)!==512)throw Error('root retained');"
        "})();");
    assert(gc_runs == 1 && !armed_gc);
    JS_RunGC(rt);
    JS_FreeContext(ctx);
    JS_FreeRuntime(rt);
    stress_runtime = NULL;
    assert(memory.live == 0 && memory.bytes == 0);
    puts(
        "GC at actual copy-phase vector reallocation: arguments, receiver, species output and cyclic garbage passed");
    return 0;
}

int main(void)
{
    (void)regular_copy_main;
    (void)gc_copy_main;
#ifdef FRAME_ARRAY_COPY_GC_ONLY
    return gc_copy_main();
#else
    return regular_copy_main();
#endif
}
