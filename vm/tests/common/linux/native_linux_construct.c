/* Public ownership, realm/reentry, interrupt and allocation-fault checks. MIT. */
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
#ifdef QJS_TEST_ARGUMENT_CONSTRUCT_PROTOCOL
#define QJS_CONSTRUCT_API_MARKER "LINUX_ARGUMENT_CONSTRUCT_API_OK"
#define QJS_CONSTRUCT_OOM_MARKER "LINUX_ARGUMENT_CONSTRUCT_OOM_OK"
#else
#define QJS_CONSTRUCT_API_MARKER "LINUX_CONSTRUCT_API_OK"
#define QJS_CONSTRUCT_OOM_MARKER "LINUX_CONSTRUCT_OOM_OK"
#endif
static JSClassID resource_class;
static unsigned made, finalized, interrupts, reentries;
static JSContext *foreign;
static JSValue foreign_driver, foreign_ctor;
static JSValue eval(JSContext *ctx, const char *s)
{
    JSValue v = JS_Eval(ctx, s, strlen(s), "native-construct", JS_EVAL_TYPE_GLOBAL);
    if (JS_IsException(v)) {
        JSValue e = JS_GetException(ctx);
        const char *p = JS_ToCString(ctx, e);
        fprintf(stderr, "CONSTRUCT_API_ERROR %s\n", p ? p : "unknown");
        JS_FreeCString(ctx, p);
        JS_FreeValue(ctx, e);
        abort();
    }
    return v;
}
static void finalizer(JSRuntime *rt, JSValue v)
{
    (void)rt;
    (void)v;
    ++finalized;
}
static JSValue fresh(JSContext *ctx, JSValueConst self, int n, JSValueConst *av)
{
    (void)self;
    (void)n;
    (void)av;
    JSValue v = JS_NewObjectClass(ctx, resource_class);
    if (JS_IsObject(v))
        ++made;
    return v;
}
static void number(JSContext *ctx, JSValue v, int expected)
{
    int32_t value;
    assert(!JS_IsException(v) && !JS_ToInt32(ctx, &value, v) && value == expected);
    JS_FreeValue(ctx, v);
}
static JSValue gc_reenter(JSContext *ctx, JSValueConst self, int n, JSValueConst *av)
{
    (void)self;
    (void)n;
    (void)av;
    JS_RunGC(JS_GetRuntime(ctx));
    if (foreign) {
        JSValue args[2] = {foreign_ctor, JS_NewInt32(foreign, 31)};
        JSValue object = JS_Call(foreign, foreign_driver, JS_UNDEFINED, 2, args);
        assert(JS_IsObject(object));
        number(foreign, JS_GetPropertyStr(foreign, object, "v"), 31);
        JS_FreeValue(foreign, object);
        ++reentries;
    }
    return JS_UNDEFINED;
}
static JSContext *context(JSRuntime *rt)
{
    JSContext *ctx = JS_NewContext(rt);
    assert(ctx);
    JSValue g = JS_GetGlobalObject(ctx);
    assert(JS_SetPropertyStr(ctx, g, "fresh", JS_NewCFunction(ctx, fresh, "fresh", 0)) > 0);
    assert(JS_SetPropertyStr(ctx, g, "gcReenter",
                             JS_NewCFunction(ctx, gc_reenter, "gcReenter", 0)) > 0);
    JS_FreeValue(ctx, g);
    return ctx;
}
static void setup_class(JSRuntime *rt)
{
    JSClassDef def = {0};
    def.class_name = "ConstructResource";
    def.finalizer = finalizer;
    JS_NewClassID(rt, &resource_class);
    assert(!JS_NewClass(rt, resource_class, &def));
}
static int interrupt(JSContext *ctx, void *opaque)
{
    (void)ctx;
    (void)opaque;
    return ++interrupts >= 3;
}
static size_t fault(size_t fail_at, int grown)
{
    made = finalized = 0;
    Allocator a = {0};
    JSRuntime *rt = JS_NewRuntime2(&functions, &a);
    assert(rt);
    setup_class(rt);
    JSContext *ctx = context(rt);
    if (grown)
        JS_FreeValue(
            ctx,
            eval(
                ctx,
#ifdef QJS_TEST_ARGUMENT_CONSTRUCT_PROTOCOL
                "class DeepConstruct {constructor(v,n){this.v=arguments[0];if(n)this.next=new DeepConstruct(v,n-1)}}"));
#else
                "class DeepConstruct {constructor(v,n){this.v=v;if(n)this.next=new DeepConstruct(v,n-1)}}"));
#endif
#ifdef QJS_TEST_ARGUMENT_CONSTRUCT_PROTOCOL
    JSValue ctor = eval(
                ctx,
                grown ? "DeepConstruct"
                      : "(class {constructor(v){this.v=arguments[0];this.extra={v};return this}})"),
#else
    JSValue ctor =
                eval(ctx, grown ? "DeepConstruct"
                                : "(class {constructor(v){this.v=v;this.extra={v};return this}})"),
#endif
            driver = eval(ctx, grown ? "(function(C){return new C(fresh(),48)})"
                                     : "(function(C){let r=new C(fresh());return {r}})");
    for (unsigned i = 0; i < (grown ? 2u : 12u); i++) {
        JSValue v = JS_Call(ctx, driver, JS_UNDEFINED, 1, &ctor);
        assert(!JS_IsException(v));
        JS_FreeValue(ctx, v);
    }
    assert(made == finalized);
    AllocatorArenaDrain drain = {0};
    oom_drain_arenas(rt, &a, &drain);
    a.sequence = 0;
    a.fail_at = fail_at;
    JSValue v = JS_Call(ctx, driver, JS_UNDEFINED, 1, &ctor);
    size_t attempts = a.sequence;
    a.fail_at = 0;
    if (JS_IsException(v)) {
        JSValue e = JS_GetException(ctx);
        JS_FreeValue(ctx, e);
        JS_ResetUncatchableError(ctx);
    } else
        JS_FreeValue(ctx, v);
    if (fail_at)
        assert(a.rejected == 1);
    v = JS_Call(ctx, driver, JS_UNDEFINED, 1, &ctor);
    assert(!JS_IsException(v));
    JS_FreeValue(ctx, v);
    JS_FreeValue(ctx, driver);
    JS_FreeValue(ctx, ctor);
    oom_undrain_arenas(rt, &drain);
    JS_RunGC(rt);
    JS_FreeContext(ctx);
    JS_FreeRuntime(rt);
    assert(made == finalized && !a.live && !a.bytes);
    return attempts;
}
int main(int argc, char **argv)
{
    if (argc == 2 && (!strcmp(argv[1], "oom") || !strcmp(argv[1], "oom-grown"))) {
        int grown = !strcmp(argv[1], "oom-grown");
        size_t count = fault(0, grown);
        assert(count && count < (grown ? 512u : 64u));
        for (size_t i = 1; i <= count; i++)
            fault(i, grown);
        printf(QJS_CONSTRUCT_OOM_MARKER " grown=%d faults=%zu zero-ledgers\n", grown, count);
        return 0;
    }
    Allocator a = {0};
    JSRuntime *rt = JS_NewRuntime2(&functions, &a);
    assert(rt);
    setup_class(rt);
    JS_SetMaxStackSize(rt, 1024 * 1024);
    JSContext *ctx = context(rt);
    foreign = context(rt);
#ifdef QJS_TEST_ARGUMENT_CONSTRUCT_PROTOCOL
    foreign_ctor = eval(foreign, "(class {constructor(v){this.v=arguments[0]}})");
#else
    foreign_ctor = eval(foreign, "(class {constructor(v){this.v=v}})");
#endif
    foreign_driver = eval(foreign, "(function(C,v){return new C(v)})");
    JSValue driver = eval(ctx, "(function(C,v){let r=new C(v);return r})");
    const char *definitions[] = {
#ifdef QJS_TEST_ARGUMENT_CONSTRUCT_PROTOCOL
        "(class {constructor(v){this.v=arguments[0]}})",
#else
        "(class {constructor(v){this.v=v}})",
#endif
#ifdef QJS_TEST_ARGUMENT_CONSTRUCT_PROTOCOL
        "(class {constructor(v){this.v=arguments[0];return 'ignored'}})",
#else
        "(class {constructor(v){this.v=v;return 'ignored'}})",
#endif
#ifdef QJS_TEST_ARGUMENT_CONSTRUCT_PROTOCOL
        "(class {constructor(v){this.v=arguments[0];return 12345678901234567890n}})",
#else
        "(class {constructor(v){this.v=v;return 12345678901234567890n}})",
#endif
#ifdef QJS_TEST_ARGUMENT_CONSTRUCT_PROTOCOL
        "(class {constructor(v){this.v=arguments[0];return {v}}})",
#else
        "(class {constructor(v){this.v=v;return {v}}})",
#endif
#ifdef QJS_TEST_ARGUMENT_CONSTRUCT_PROTOCOL
        "(class {constructor(v){this.v=arguments[0];gcReenter();return this}})",
#else
        "(class {constructor(v){this.v=v;gcReenter();return this}})",
#endif
#ifdef QJS_TEST_ARGUMENT_CONSTRUCT_PROTOCOL
        "(class {constructor(v){this.count=arguments.length;this.read=()=>v;v=17}})"};
#else
        "(class {constructor(v){this.read=()=>v;v=17}})"};
#endif
    for (unsigned k = 0; k < sizeof(definitions) / sizeof(definitions[0]); k++) {
        JSValue ctor = eval(ctx, definitions[k]);
        for (unsigned i = 0; i < 32; i++) {
            JSValue resource = fresh(ctx, JS_UNDEFINED, 0, NULL), args[2] = {ctor, resource};
            unsigned before = finalized;
            JSValue v = JS_Call(ctx, driver, JS_UNDEFINED, 2, args);
            assert(JS_IsObject(v));
            JS_RunGC(rt);
            assert(finalized == before);
            JS_FreeValue(ctx, resource);
            JS_FreeValue(ctx, v);
            assert(made == finalized);
        }
        JS_FreeValue(ctx, ctor);
    }
    assert(reentries == 32);
#ifdef QJS_TEST_ARGUMENT_CONSTRUCT_PROTOCOL
    JSValue thrown =
        eval(ctx, "(class {constructor(v){this.v=arguments[0];gcReenter();throw 'ctor-error'}})");
#else
    JSValue thrown = eval(ctx, "(class {constructor(v){this.v=v;gcReenter();throw 'ctor-error'}})");
#endif
    JSValue resource = fresh(ctx, JS_UNDEFINED, 0, NULL), args[2] = {thrown, resource};
    JSValue v = JS_Call(ctx, driver, JS_UNDEFINED, 2, args);
    assert(JS_IsException(v));
    JSValue e = JS_GetException(ctx);
    JS_FreeValue(ctx, e);
    JS_FreeValue(ctx, resource);
    assert(made == finalized);
    JS_FreeValue(ctx, thrown);
    JSValue loop = eval(ctx, "(function(C,n){let o;while(n-->0)o=new C(n);return o.v})");
    args[0] = foreign_ctor;
    args[1] = JS_NewInt32(ctx, 200000);
    JS_SetInterruptHandler(rt, interrupt, NULL);
    v = JS_Call(ctx, loop, JS_UNDEFINED, 2, args);
    assert(JS_IsException(v) && interrupts >= 3);
    e = JS_GetException(ctx);
    JS_FreeValue(ctx, e);
    JS_ResetUncatchableError(ctx);
    JS_SetInterruptHandler(rt, NULL, NULL);
    args[1] = JS_NewInt32(ctx, 3);
    number(ctx, JS_Call(ctx, loop, JS_UNDEFINED, 2, args), 0);
    JS_FreeValue(ctx, loop);
    JS_FreeValue(ctx, driver);
    JS_FreeValue(foreign, foreign_driver);
    JS_FreeValue(foreign, foreign_ctor);
    JS_FreeContext(foreign);
    foreign = NULL;
    JS_RunGC(rt);
    JS_FreeContext(ctx);
    JS_FreeRuntime(rt);
    assert(made == finalized && !a.live && !a.bytes);
    printf(QJS_CONSTRUCT_API_MARKER " resources=%u reentries=%u interrupts=%u zero-ledgers\n", made,
           reentries, interrupts);
    return 0;
}
