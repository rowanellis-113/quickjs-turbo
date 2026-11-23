#ifdef NDEBUG
#undef NDEBUG
#endif
#include "quickjs.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <stdatomic.h>
#include "../native_oom_allocator.h"
extern _Atomic uint64_t JS_LinuxVirtualArgumentsStats[2] __attribute__((weak));
static JSClassID token_class;
static unsigned born, dead;
static JSContext *active;
static JSValue reader;
static unsigned reentries;
static void finish(JSRuntime *rt, JSValue value)
{
    (void)rt;
    (void)value;
    dead++;
    if (!JS_IsUndefined(reader)) {
        JSValue v = JS_Call(active, reader, JS_UNDEFINED, 0, NULL);
        int32_t n;
        assert(!JS_IsException(v) && !JS_ToInt32(active, &n, v) && n == 43);
        JS_FreeValue(active, v);
        reentries++;
    }
}
static JSValue watch(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)self;
    assert(argc == 1 && JS_IsFunction(ctx, argv[0]));
    JSValue next = JS_DupValue(ctx, argv[0]);
    JS_FreeValue(ctx, reader);
    reader = next;
    return JS_UNDEFINED;
}
static JSValue make_token(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)self;
    (void)argc;
    (void)argv;
    JSValue v = JS_NewObjectClass(ctx, token_class);
    if (!JS_IsException(v)) {
        born++;
        if (argc > 0 && JS_SetPropertyStr(ctx, v, "serial", JS_DupValue(ctx, argv[0])) < 0) {
            JS_FreeValue(ctx, v);
            return JS_EXCEPTION;
        }
    }
    return v;
}
static JSValue collect(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)self;
    (void)argc;
    (void)argv;
    JS_RunGC(JS_GetRuntime(ctx));
    return JS_UNDEFINED;
}
static JSValue print_line(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)self;
    for (int i = 0; i < argc; i++) {
        const char *p = JS_ToCString(ctx, argv[i]);
        if (!p)
            return JS_EXCEPTION;
        puts(p);
        JS_FreeCString(ctx, p);
    }
    return JS_UNDEFINED;
}
static void check(JSContext *ctx, JSValue v)
{
    if (JS_IsException(v)) {
        JSValue e = JS_GetException(ctx);
        const char *s = JS_ToCString(ctx, e);
        fprintf(stderr, "ERROR %s\n", s ? s : "unprintable");
        JS_FreeCString(ctx, s);
        JSValue stack = JS_GetPropertyStr(ctx, e, "stack");
        s = JS_ToCString(ctx, stack);
        fprintf(stderr, "%s\n", s ? s : "");
        JS_FreeCString(ctx, s);
        JS_FreeValue(ctx, stack);
        JS_FreeValue(ctx, e);
        abort();
    }
}
static JSValue realm(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)self;
    assert(argc == 1);
    JSContext *other = JS_NewContext(JS_GetRuntime(ctx));
    if (!other)
        return JS_EXCEPTION;
    const char *src = "(function(a){this.a=a;})";
    JSValue method = JS_Eval(other, src, strlen(src), "other-realm.js", 0);
    check(other, method);
    JSValue proto = JS_GetPropertyStr(ctx, argv[0], "prototype");
    check(ctx, proto);
    assert(JS_SetPropertyStr(ctx, proto, "work", method) >= 0);
    JS_FreeValue(ctx, proto);
    JSValue arg = JS_NewInt32(ctx, 73), v = JS_CallConstructor(ctx, argv[0], 1, &arg);
    check(ctx, v);
    JSValue a = JS_GetPropertyStr(ctx, v, "a");
    int32_t n;
    assert(!JS_ToInt32(ctx, &n, a) && n == 73);
    JS_FreeValue(ctx, a);
    JS_FreeValue(ctx, v);
    JS_FreeContext(other);
    return JS_UNDEFINED;
}
static uint64_t entered(void)
{
    return JS_LinuxVirtualArgumentsStats ? atomic_load(&JS_LinuxVirtualArgumentsStats[1]) : 0;
}

static int stop_after_two(JSContext *ctx, void *opaque)
{
    (void)ctx;
    return ++*(unsigned *)opaque >= 2;
}

static void public_boundaries(JSContext *ctx)
{
    JSRuntime *rt = JS_GetRuntime(ctx);
    uint64_t before = entered();
    const char *source =
        "(function(){var C=function(){this.work.apply(this,arguments);};C.prototype.work=function(a,b){this.a=a;this.b=b;};return C;})()";
    JSValue ctor = JS_Eval(ctx, source, strlen(source), "public-copy.js", 0);
    check(ctx, ctor);
    JSValue args[3];
    for (unsigned j = 0; j < 3; ++j) {
        args[j] = JS_NewObjectClass(ctx, token_class);
        check(ctx, args[j]);
        born++;
    }
    for (unsigned j = 0; j < 64; ++j) {
        JSValue value = JS_CallConstructor(ctx, ctor, 3, args);
        check(ctx, value);
        JS_RunGC(rt);
        JSValue a = JS_GetPropertyStr(ctx, value, "a");
        assert(JS_VALUE_GET_PTR(a) == JS_VALUE_GET_PTR(args[0]));
        JS_FreeValue(ctx, a);
        JS_FreeValue(ctx, value);
    }
    assert(entered() == before); /* COPY roots retain the complete original path. */
    for (unsigned j = 0; j < 3; ++j)
        JS_FreeValue(ctx, args[j]);
    JS_FreeValue(ctx, ctor);

    unsigned interrupts = 0;
    JS_SetInterruptHandler(rt, stop_after_two, &interrupts);
    source =
        "(function(){var C=function(){this.work.apply(this,arguments);};C.prototype.work=function(a){this.a=a;};for(var i=0;i<100000;i++)new C(i);})()";
    JSValue value = JS_Eval(ctx, source, strlen(source), "interrupt-forward.js", 0);
    JS_SetInterruptHandler(rt, NULL, NULL);
    assert(JS_IsException(value) && interrupts == 2 && entered() == before);
    value = JS_GetException(ctx);
    JS_FreeValue(ctx, value);

    JS_SetMaxStackSize(rt, 128 * 1024);
    source =
        "(function(){var C=function(){this.work.apply(this,arguments);};C.prototype.work=function(n){if(n>0)new C(n-1);};new C(10000);})()";
    value = JS_Eval(ctx, source, strlen(source), "quota-forward.js", 0);
    JS_SetMaxStackSize(rt, 1024 * 1024);
    assert(JS_IsException(value));
    value = JS_GetException(ctx);
    JS_FreeValue(ctx, value);
    source = "21+21";
    value = JS_Eval(ctx, source, strlen(source), "post-quota-recovery.js", 0);
    check(ctx, value);
    int32_t n;
    assert(!JS_ToInt32(ctx, &n, value) && n == 42);
    JS_FreeValue(ctx, value);
    JS_RunGC(rt);
}

static size_t fault_trial(size_t fault)
{
    Allocator memory = {0};
    JSRuntime *rt = JS_NewRuntime2(&functions, &memory);
    assert(rt);
    JSContext *ctx = JS_NewContext(rt);
    assert(ctx);
    const char *src =
        "(function(){function C(){this.work.apply(this,arguments);}C.prototype.work=function(a,b){this.a=a;this.b=b;};return function invoke(){var out;for(var i=0;i<32;i++){out=new C({n:i},{n:i+1},{extra:i});}return out.a.n+out.b.n;};})()";
    JSValue fn = JS_Eval(ctx, src, strlen(src), "forward-oom.js", 0);
    check(ctx, fn);
    JSValue v = JS_Call(ctx, fn, JS_UNDEFINED, 0, NULL);
    check(ctx, v);
    JS_FreeValue(ctx, v);
    size_t start = memory.sequence;
    memory.fail_at = fault ? start + fault : 0;
    v = JS_Call(ctx, fn, JS_UNDEFINED, 0, NULL);
    memory.fail_at = 0;
    size_t allocations = memory.sequence - start;
    if (JS_IsException(v))
        v = JS_GetException(ctx);
    JS_FreeValue(ctx, v);
    v = JS_Call(ctx, fn, JS_UNDEFINED, 0, NULL);
    check(ctx, v);
    int32_t n;
    assert(!JS_ToInt32(ctx, &n, v) && n == 63);
    JS_FreeValue(ctx, v);
    JS_FreeValue(ctx, fn);
    JS_RunGC(rt);
    JS_FreeContext(ctx);
    JS_FreeRuntime(rt);
    assert(!memory.live && !memory.bytes);
    return allocations;
}
int main(int argc, char **argv)
{
    if (argc == 2 && !strcmp(argv[1], "oom")) {
        size_t n = fault_trial(0);
        for (size_t i = 1; i <= n + 2; i++)
            fault_trial(i);
        printf("VIRTUAL_ARGUMENTS_OOM_OK allocations=%zu trials=%zu\n", n, n + 3);
        return 0;
    }
    assert(argc == 2);
    FILE *f = fopen(argv[1], "rb");
    assert(f);
    fseek(f, 0, SEEK_END);
    long length = ftell(f);
    rewind(f);
    char *source = malloc(length + 1);
    assert(source);
    assert(fread(source, 1, length, f) == (size_t)length);
    fclose(f);
    source[length] = 0;
    JSRuntime *rt = JS_NewRuntime();
    assert(rt);
    JSContext *ctx = JS_NewContext(rt);
    assert(ctx);
    active = ctx;
    reader = JS_UNDEFINED;
    JS_NewClassID(rt, &token_class);
    JSClassDef def = {0};
    def.class_name = "ForwardToken";
    def.finalizer = finish;
    assert(!JS_NewClass(rt, token_class, &def));
    JSValue global = JS_GetGlobalObject(ctx);
    assert(JS_SetPropertyStr(ctx, global, "makeToken",
                             JS_NewCFunction(ctx, make_token, "makeToken", 1)) >= 0);
    assert(JS_SetPropertyStr(ctx, global, "collect", JS_NewCFunction(ctx, collect, "collect", 0)) >=
           0);
    assert(JS_SetPropertyStr(ctx, global, "print", JS_NewCFunction(ctx, print_line, "print", 1)) >=
           0);
    assert(JS_SetPropertyStr(ctx, global, "runRealm", JS_NewCFunction(ctx, realm, "runRealm", 1)) >=
           0);
    JS_FreeValue(ctx, global);
    global = JS_GetGlobalObject(ctx);
    assert(JS_SetPropertyStr(ctx, global, "watch", JS_NewCFunction(ctx, watch, "watch", 1)) >= 0);
    JS_FreeValue(ctx, global);
    JSValue v = JS_Eval(ctx, source, length, "virtual-arguments-semantics.js", 0);
    check(ctx, v);
    JS_FreeValue(ctx, v);
    free(source);
    if (getenv("REQUIRE_VIRTUAL_HIT"))
        assert(JS_LinuxVirtualArgumentsStats && entered() > 0);
    if (getenv("REQUIRE_VIRTUAL_FALLBACK"))
        assert(entered() == 0);
    public_boundaries(ctx);
    if (getenv("REQUIRE_VIRTUAL_FALLBACK"))
        assert(entered() == 0);
    if (JS_LinuxVirtualArgumentsStats) {
        printf("VIRTUAL_ARGUMENTS_STATS eligible=%llu entered=%llu\n",
               (unsigned long long)atomic_load(&JS_LinuxVirtualArgumentsStats[0]),
               (unsigned long long)atomic_load(&JS_LinuxVirtualArgumentsStats[1]));
        if (getenv("REQUIRE_VIRTUAL_HIT"))
            assert(atomic_load(&JS_LinuxVirtualArgumentsStats[1]) > 0);
    }
    JS_RunGC(rt);
    JS_FreeValue(ctx, reader);
    reader = JS_UNDEFINED;
    JS_FreeContext(ctx);
    JS_FreeRuntime(rt);
    assert(born == dead && reentries > 0);
    printf("VIRTUAL_ARGUMENTS_HOST_OK born=%u dead=%u reentries=%u\n", born, dead, reentries);
    return 0;
}
