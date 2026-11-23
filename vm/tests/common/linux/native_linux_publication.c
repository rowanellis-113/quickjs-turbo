/* Public GC/ownership, C reentry, backtrace and fault recovery. MIT. */
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
#ifdef QJS_TEST_ARGUMENT_PROTOCOL
#define QJS_PROTOCOL_API_MARKER "LINUX_ARGUMENTS_API_OK"
#define QJS_PROTOCOL_OOM_MARKER "LINUX_ARGUMENTS_OOM_OK"
#elif defined(QJS_TEST_INDEXED_PROTOCOL)
#define QJS_PROTOCOL_API_MARKER "LINUX_INDEXED_API_OK"
#define QJS_PROTOCOL_OOM_MARKER "LINUX_INDEXED_OOM_OK"
#elif defined(QJS_TEST_VARARGS_LITERAL_PROTOCOL)
#define QJS_PROTOCOL_API_MARKER "LINUX_VARARGS_LITERALS_API_OK"
#define QJS_PROTOCOL_OOM_MARKER "LINUX_VARARGS_LITERALS_OOM_OK"
#elif defined(QJS_TEST_ITERATOR_PROTOCOL)
#define QJS_PROTOCOL_API_MARKER "LINUX_ITERATORS_API_OK"
#define QJS_PROTOCOL_OOM_MARKER "LINUX_ITERATORS_OOM_OK"
#else
#define QJS_PROTOCOL_API_MARKER "LINUX_PUBLICATION_API_OK"
#define QJS_PROTOCOL_OOM_MARKER "LINUX_PUBLICATION_OOM_OK"
#endif

static JSClassID resource_class;
#ifdef QJS_TEST_VARARGS_LITERAL_PROTOCOL
static JSClassID ordinary_class;
#endif
static unsigned made, finalized, probes, reentries, interrupts, depth;
static JSContext *foreign;
static JSValue foreign_driver;

static JSValue eval(JSContext *ctx, const char *text)
{
    JSValue v = JS_Eval(ctx, text, strlen(text), "publication-api", JS_EVAL_TYPE_GLOBAL);
    if (JS_IsException(v)) {
        JSValue e = JS_GetException(ctx);
        const char *message = JS_ToCString(ctx, e);
        fprintf(stderr, "PUBLICATION_API_ERROR %s\n", message ? message : "unknown");
        JS_FreeCString(ctx, message);
        JS_FreeValue(ctx, e);
        abort();
    }
    return v;
}
static void number(JSContext *ctx, JSValue v, int expected)
{
    int32_t n;
    assert(!JS_IsException(v) && !JS_ToInt32(ctx, &n, v) && n == expected);
    JS_FreeValue(ctx, v);
}
static void finalize(JSRuntime *rt, JSValue v)
{
    (void)rt;
    assert(JS_GetOpaque(v, resource_class) == (void *)(uintptr_t)1729);
    ++finalized;
}
#ifdef QJS_TEST_VARARGS_LITERAL_PROTOCOL
/* A normal literal now owns a native, cyclic prototype. Reset it before GC;
   any remaining cache reference belongs solely to the physical VM owner. */
static void restore_proto(JSContext *ctx)
{
    JSValue g = JS_GetGlobalObject(ctx), ctor = JS_GetPropertyStr(ctx, g, "Object"),
            proto = JS_GetPropertyStr(ctx, ctor, "prototype");
    assert(!JS_IsException(proto));
    JS_SetClassProto(ctx, ordinary_class, proto);
    JS_FreeValue(ctx, ctor);
    JS_FreeValue(ctx, g);
}
#endif
static JSValue fresh(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)self;
    (void)argc;
    (void)argv;
    JSValue v = JS_NewObjectClass(ctx, resource_class);
    if (JS_IsException(v))
        return v;
    JS_SetOpaque(v, (void *)(uintptr_t)1729);
    ++made;
    if (JS_SetPropertyStr(ctx, v, "self", JS_DupValue(ctx, v)) < 0) {
        JS_FreeValue(ctx, v);
        return JS_EXCEPTION;
    }
#ifdef QJS_TEST_VARARGS_LITERAL_PROTOCOL
    JS_SetClassProto(ctx, ordinary_class, JS_DupValue(ctx, v));
#endif
    return v;
}
static JSValue inspect(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)self;
    assert(argc == 1 && JS_GetOpaque(argv[0], resource_class) == (void *)(uintptr_t)1729);
    unsigned before = finalized;
    ++probes;
#ifdef QJS_TEST_VARARGS_LITERAL_PROTOCOL
    restore_proto(ctx);
#endif
    JS_RunGC(JS_GetRuntime(ctx));
    assert(finalized == before);
    if (foreign && !depth) {
        ++depth;
        number(foreign, JS_Call(foreign, foreign_driver, JS_UNDEFINED, 1, argv), 20);
        --depth;
        ++reentries;
    }
    assert(finalized == before && JS_GetOpaque(argv[0], resource_class) == (void *)(uintptr_t)1729);
    return JS_NewInt32(ctx, 17);
}
static JSValue raise_error(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    JSValue v = inspect(ctx, self, argc, argv);
    if (JS_IsException(v))
        return v;
    JS_FreeValue(ctx, v);
    return JS_ThrowTypeError(ctx, "publication-boundary");
}
static const char source[] =
#ifdef QJS_TEST_INDEXED_PROTOCOL
    "function pubCtor(){}"
    "function pubIndexedRead(a,k){let out=a[k];return out}"
    "function pubIndexedWrite(a,k,v){a[k]=v;return a}"
    "function pubIndexedMethod(a,k,v){let out=a[k](v);return out}"
    "function pubIndexedInspect(v){let keep=v;let out=inspect(v);if(keep!==v)throw Error('callee owner');return out}"
    "function pubIndexedEcho(v){if(this.tag!==37)throw Error('method this');return 17}"
#ifdef QJS_TEST_INDEXED_COERCION
    "function pubLeaf(v){let own=v;let a=[pubIndexedEcho,0,0];delete a[1];a.tag=37;let count=0,n=0;"
    "let key={toString(){count++;if(count===1)n=inspect(v);return count<3?'2':'0'}};"
    "pubIndexedWrite(a,key,v);let held=pubIndexedRead(a,key);let out=pubIndexedMethod(a,key,held);"
    "if(held!==own||count!==3||n!==17||out!==17||v instanceof pubCtor)throw Error('coercion owner');return out}"
#else
    "function pubLeaf(v){let own=v;let a=[pubIndexedInspect,0,0];delete a[1];a.tag=37;"
    "for(let i=0;i<4;i++)pubIndexedWrite(a,2,v);let held=pubIndexedRead(a,2);"
    "if(held!==own||v instanceof pubCtor)throw Error('indexed owner');let n=pubIndexedMethod(a,0,held);return n}"
#endif
#elif defined(QJS_TEST_VARARGS_LITERAL_PROTOCOL)
#ifdef QJS_TEST_VARARGS_WIDE
    "function pubApplyInspect(v,p1,p2,p3,p4,p5,p6,p7,p8,p9,p10,p11,p12,p13,p14,p15,p16,p17,p18,p19,p20,p21,p22,p23,p24,p25,p26,p27,p28,p29,p30,p31,p32,p33,p34,p35,p36,p37,p38,p39,p40,p41,p42,p43,p44,p45,p46,p47,p48,p49,p50,p51,p52,p53,p54,p55,p56,p57,p58,p59,p60,p61,p62,p63,p64,p65,p66,p67,p68,p69,p70,p71,p72,p73,p74,p75,p76,p77,p78,p79,p80,p81,p82,p83,p84,p85,p86,p87,p88,p89,p90,p91,p92,p93,p94,p95,p96,p97,p98){let keep=v;if(p96!==v||p97!==undefined||p98!==undefined)throw Error('wide actuals');let out=inspect(v);if(keep!==v)throw Error('child owner');return out}"
    "function pubSpreadInspect(v){let keep=v;let list=[v,v,v,v,v,v,v,v,v,v,v,v,v,v,v,v,v,v,v,v,v,v,v,v,v,v,v,v,v,v,v,v,v,v,v,v,v,v,v,v,v,v,v,v,v,v,v,v,v,v,v,v,v,v,v,v,v,v,v,v,v,v,v,v,v,v,v,v,v,v,v,v,v,v,v,v,v,v,v,v,v,v,v,v,v,v,v,v,v,v,v,v,v,v,v,v,v];let out=pubApplyInspect(...list);if(keep!==v)throw Error('spread owner');return out}"
#else
    "function pubApplyInspect(v,p1,missing){let keep=v;if(p1!==v||missing!==undefined)throw Error('missing formal');let out=inspect(v);if(keep!==v)throw Error('child owner');return out}"
    "function pubSpreadInspect(v){let keep=v;let list=[v,v];let out=pubApplyInspect(...list);if(keep!==v)throw Error('spread owner');return out}"
#endif
    "function pubLeaf(v){let own=v;let holder;for(let i=0;i<4;i++)holder={a:v,b:1,c:2};"
    "let args=[holder.a];let n=pubSpreadInspect.apply(holder,args);if(own!==args[0]||holder.a!==v)throw Error('owner');return n}"
#elif defined(QJS_TEST_ARGUMENT_PROTOCOL)
    "function pubLeaf(v){let own=v;let args=arguments;let n=inspect(args[0]);if(own!==args[0])throw Error('owner');return n}"
#else
#ifdef QJS_TEST_ITERATOR_PROTOCOL
    "function pubNext(){if(this.done)return this.end;this.done=true;this.result.value=inspect(this.value);return this.result}"
    "function pubIter(v){return {value:v,done:false,result:{done:false,value:0},end:{done:true},next:pubNext,[Symbol.iterator]:function(){return this}}}"
    "function pubLeaf(v){let own=v;let n=0;for(const out of pubIter(v))n+=out;if(own!==v)throw Error('owner');return n}"
#else
    "function pubLeaf(v){let own=v;let n=inspect(v);if(own!==v)throw Error('owner');return n}"
#endif
#endif
    "function pubMiddle(v){let out=pubLeaf(v);return out+1}"
    "function pubOuter(v){let out=pubMiddle(v);return out+1}"
#ifdef QJS_TEST_ARGUMENT_PROTOCOL
    "function pubMissing(v,a,b,c,d,e,f,g,h,i,j){'use strict';let args=arguments;if(args.length!==1)throw Error('argc');let out=pubOuter(args[0]);return out+(j===undefined)}"
#else
    "function pubMissing(v,a,b,c,d,e,f,g,h,i,j){let out=pubOuter(v);return out+(j===undefined)}"
#endif
    "function pubOwned(v){let keep=7;let hold=()=>keep;let out=pubMissing(v);"
    "if(hold()!==7)throw Error('captured parent');return out}"
#ifdef QJS_TEST_ARGUMENT_PROTOCOL
    "function pubDeep(v,n){let saved=v;let args=arguments;if(args.length!==2)throw Error('deep argc');let out=n?pubDeep(v,n-1):pubOwned(v);"
#else
    "function pubDeep(v,n){let saved=v;let out=n?pubDeep(v,n-1):pubOwned(v);"
#endif
    "if(saved!==v)throw Error('deep owner');return out}"
    "function pubRun(){let v=fresh();let out=pubOwned(v);return out}"
#ifdef QJS_TEST_INDEXED_PROTOCOL
    "function pubFailureInner(v){let a=[raiseError,0,0];delete a[1];let out=pubIndexedMethod(a,0,v);return out}"
#elif defined(QJS_TEST_VARARGS_LITERAL_PROTOCOL)
    "function pubRaise(v){let keep=v;let out=raiseError(v);if(keep!==v)throw Error('raise owner');return out}"
    "function pubFailureInner(v){let holder={a:v,b:0};let args=[holder.a];let out=pubRaise.apply(holder,args);return out}"
#elif defined(QJS_TEST_ARGUMENT_PROTOCOL)
    "function pubFailureInner(v){let args=arguments;let out=raiseError(args[0]);return out}"
#else
#ifdef QJS_TEST_ITERATOR_PROTOCOL
    "function pubThrowNext(){return raiseError(this.value)}"
    "function pubErrorIter(v){return {value:v,next:pubThrowNext,[Symbol.iterator]:function(){return this}}}"
    "function pubFailureInner(v){for(const out of pubErrorIter(v))return out;return 0}"
#else
    "function pubFailureInner(v){let out=raiseError(v);return out}"
#endif
#endif
    "function pubFailureMiddle(v){let out=pubFailureInner(v);return out}"
    "function pubFailureOuter(v){let out=pubFailureMiddle(v);return out}"
    "function pubThrow(){let v=fresh();try{pubFailureOuter(v)}catch(e){"
    "if(!(e instanceof TypeError))throw Error('exception type');"
#ifdef QJS_TEST_VARARGS_LITERAL_PROTOCOL
    "for(const name of ['pubRaise','pubFailureInner','pubFailureMiddle','pubFailureOuter'])"
#elif defined(QJS_TEST_ITERATOR_PROTOCOL)
    "for(const name of ['pubThrowNext','pubFailureInner','pubFailureMiddle','pubFailureOuter'])"
#else
    "for(const name of ['pubFailureInner','pubFailureMiddle','pubFailureOuter'])"
#endif
    "if(!e.stack.includes(name))throw Error('missing published frame '+name);return 23}"
    "throw Error('no exception')}"
    "function pubInteger(x){let y=x+1;return y}"
#ifdef QJS_TEST_INDEXED_PROTOCOL
    "function pubIntegerMiddle(x){let same=pubCtor instanceof pubCtor;return x+(same?9:2)}"
#elif defined(QJS_TEST_VARARGS_LITERAL_PROTOCOL)
    "function pubIntegerMiddle(x){let args=[x];let y=pubInteger(...args);return y+1}"
#else
    "function pubIntegerMiddle(x){let y=pubInteger(x);return y+1}"
#endif
#ifdef QJS_TEST_ITERATOR_PROTOCOL
    "function pubCountNext(){let n=this.count--;this.result.value=n;return n>=0?this.result:this.end}"
    "function pubCountIter(n){return {count:n,result:{done:false,value:0},end:{done:true},next:pubCountNext,[Symbol.iterator]:function(){return this}}}"
    "function pubLoop(n){let sum=0;for(const value of pubCountIter(n))sum+=value;return sum}";
#else
    "function pubLoop(n){let sum=0;while(n-->0)sum+=pubIntegerMiddle(n);return sum}";
#endif

static JSContext *context(JSRuntime *rt)
{
    JSContext *ctx = JS_NewContext(rt);
    assert(ctx);
#ifdef QJS_TEST_VARARGS_LITERAL_PROTOCOL
    JSValue sample = JS_NewObject(ctx);
    assert(!JS_IsException(sample));
    ordinary_class = JS_GetClassID(sample);
    JS_FreeValue(ctx, sample);
#endif
    JSValue g = JS_GetGlobalObject(ctx);
    assert(JS_SetPropertyStr(ctx, g, "fresh", JS_NewCFunction(ctx, fresh, "fresh", 0)) > 0);
    assert(JS_SetPropertyStr(ctx, g, "inspect", JS_NewCFunction(ctx, inspect, "inspect", 1)) > 0);
    assert(JS_SetPropertyStr(ctx, g, "raiseError",
                             JS_NewCFunction(ctx, raise_error, "raiseError", 1)) > 0);
    JS_FreeValue(ctx, g);
    JS_FreeValue(ctx, eval(ctx, source));
    return ctx;
}
static JSRuntime *runtime(Allocator *a)
{
    made = finalized = probes = reentries = interrupts = depth = 0;
    foreign = NULL;
    JSRuntime *rt = JS_NewRuntime2(&functions, a);
    assert(rt);
    JSClassDef def = {0};
    def.class_name = "PublicationResource";
    def.finalizer = finalize;
    JS_NewClassID(rt, &resource_class);
    assert(!JS_NewClass(rt, resource_class, &def));
    JS_SetMaxStackSize(rt, 1024 * 1024);
    return rt;
}
static void clear_exception(JSContext *ctx)
{
    JSValue e = JS_GetException(ctx);
    JS_FreeValue(ctx, e);
    JS_ResetUncatchableError(ctx);
#ifdef QJS_TEST_VARARGS_LITERAL_PROTOCOL
    restore_proto(ctx);
#endif
}
static int interrupt(JSContext *ctx, void *opaque)
{
    (void)opaque;
    JS_RunGC(JS_GetRuntime(ctx));
    return ++interrupts >= 3;
}
static size_t fault(size_t fail_at)
{
    Allocator a = {0};
    JSRuntime *rt = runtime(&a);
    JSContext *ctx = context(rt);
    JSValue driver = eval(ctx, "(function(){let v=fresh();let out=pubDeep(v,48);return out})");
    for (unsigned i = 0; i < 2; i++) {
        number(ctx, JS_Call(ctx, driver, JS_UNDEFINED, 0, NULL), 20);
        JS_RunGC(rt);
        assert(made == finalized);
    }
    a.sequence = 0;
    a.fail_at = fail_at;
    JSValue v = JS_Call(ctx, driver, JS_UNDEFINED, 0, NULL);
    size_t attempts = a.sequence;
    a.fail_at = 0;
    if (JS_IsException(v))
        clear_exception(ctx);
    else
        number(ctx, v, 20);
    if (fail_at)
        assert(a.rejected == 1);
    JS_RunGC(rt);
    assert(made == finalized);
    number(ctx, JS_Call(ctx, driver, JS_UNDEFINED, 0, NULL), 20);
    JS_RunGC(rt);
    assert(made == finalized);
    JS_FreeValue(ctx, driver);
    JS_FreeContext(ctx);
    JS_FreeRuntime(rt);
    assert(!a.live && !a.bytes && made == finalized);
    return attempts;
}
int main(int argc, char **argv)
{
    if (argc == 2 && !strcmp(argv[1], "oom")) {
        size_t count = fault(0);
        assert(count && count < 512);
        for (size_t i = 1; i <= count; i++)
            fault(i);
        printf(QJS_PROTOCOL_OOM_MARKER " faults=%zu zero-ledgers\n", count);
        return 0;
    }
    Allocator a = {0};
    JSRuntime *rt = runtime(&a);
    JSContext *ctx = context(rt);
#ifdef QJS_TEST_ARGUMENT_PROTOCOL
    JSContext *realm = context(rt);
    foreign_driver =
        eval(realm, "(function(v){let args=arguments;let out=pubOwned(args[0]);return out})");
    foreign = realm;
#else
    JSContext *realm = context(rt);
    foreign_driver = eval(realm, "(function(v){let out=pubOwned(v);return out})");
    foreign = realm;
#endif
    JSValue driver = eval(ctx, "(function(){let out=pubRun();return out})"),
            throwing = eval(ctx, "(function(){let out=pubThrow();return out})"),
            deep = eval(ctx, "(function(){let v=fresh();let out=pubDeep(v,64);return out})");
    for (unsigned i = 0; i < 32; i++) {
        number(ctx, JS_Call(ctx, driver, JS_UNDEFINED, 0, NULL), 20);
        JS_RunGC(rt);
        assert(made == finalized);
        number(ctx, JS_Call(ctx, throwing, JS_UNDEFINED, 0, NULL), 23);
        JS_RunGC(rt);
        assert(made == finalized);
    }
    number(ctx, JS_Call(ctx, deep, JS_UNDEFINED, 0, NULL), 20);
    JS_RunGC(rt);
    assert(made == finalized);
    assert(made == 65 && reentries == 65 && probes == 130);
    JSValue loop = eval(ctx, "pubLoop"), n = JS_NewInt32(ctx, 200000);
    JS_SetInterruptHandler(rt, interrupt, NULL);
    JSValue v = JS_Call(ctx, loop, JS_UNDEFINED, 1, &n);
    assert(JS_IsException(v) && interrupts >= 3);
    clear_exception(ctx);
    JS_SetInterruptHandler(rt, NULL, NULL);
    number(ctx, JS_Call(ctx, driver, JS_UNDEFINED, 0, NULL), 20);
    JS_RunGC(rt);
    assert(made == finalized);
    JS_FreeValue(ctx, loop);
    JS_FreeValue(ctx, driver);
    JS_FreeValue(ctx, throwing);
    JS_FreeValue(ctx, deep);
    JS_FreeValue(realm, foreign_driver);
    foreign = NULL;
    JS_FreeContext(realm);
    JS_RunGC(rt);
    JS_FreeContext(ctx);
    JS_FreeRuntime(rt);
    assert(made == finalized && !a.live && !a.bytes);
    printf(QJS_PROTOCOL_API_MARKER
           " resources=%u probes=%u reentries=%u interrupts=%u zero-ledgers\n",
           made, probes, reentries, interrupts);
    return 0;
}
