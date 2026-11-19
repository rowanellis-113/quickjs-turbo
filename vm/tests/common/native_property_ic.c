/* Public API semantic/GC/OOM fixture plus private installed-cache inspection. */
#include "quickjs.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
extern int js_property_ic_inspect(JSValueConst, uint32_t counts[7]);
static unsigned probe_finalized;
static JSClassID alias_class;
static int alias_finalized;
static void alias_finalizer(JSRuntime *rt, JSValue value)
{
    (void)rt;
    (void)value;
    alias_finalized++;
}
static JSValue make_alias(JSContext *ctx, JSValueConst this_val, int argc, JSValueConst *argv)
{
    JSValue value = JS_NewObjectProtoClass(ctx, JS_NULL, alias_class);
    (void)this_val;
    (void)argc;
    (void)argv;
    if (JS_IsException(value))
        return value;
    if (JS_SetPropertyStr(ctx, value, "value", JS_DupValue(ctx, value)) < 0) {
        JS_FreeValue(ctx, value);
        return JS_EXCEPTION;
    }
    return value;
}
static JSValue alias_count(JSContext *ctx, JSValueConst this_val, int argc, JSValueConst *argv)
{
    (void)this_val;
    (void)argc;
    (void)argv;
    return JS_NewInt32(ctx, alias_finalized);
}
static void probe_finalizer(JSRuntime *rt, JSValue value)
{
    (void)rt;
    (void)value;
    probe_finalized++;
}

static int evaluate(JSContext *ctx, const char *source)
{
    JSValue value = JS_Eval(ctx, source, strlen(source), "property-ic-host", JS_EVAL_TYPE_GLOBAL);
    if (JS_IsException(value)) {
        JSValue exception = JS_GetException(ctx);
        const char *text = JS_ToCString(ctx, exception);
        fprintf(stderr, "%s\n", text ? text : "exception");
        JS_FreeCString(ctx, text);
        JS_FreeValue(ctx, exception);
        return -1;
    }
    JS_FreeValue(ctx, value);
    return 0;
}
static JSValue global(JSContext *ctx, const char *name)
{
    JSValue value, object = JS_GetGlobalObject(ctx);
    value = JS_GetPropertyStr(ctx, object, name);
    JS_FreeValue(ctx, object);
    return value;
}
static int eager_lifetimes(JSContext *ctx, JSRuntime *rt, JSClassID cls)
{
    int mode, i;
    for (mode = 0; mode < 4; mode++) {
        unsigned before = probe_finalized;
        JSValue proto = JS_NewObjectProtoClass(ctx, JS_NULL, cls);
        JSValue obj, anchor = JS_UNDEFINED, fn, result, args[2];
        const char *code =
            mode == 2 ? "(function(o,v){o.eagerA=v;o.eagerB=v+1;o.eagerC=v+2;return o.eagerC})"
                      : "(function(o){return o.value})";
        if (JS_IsException(proto) ||
            JS_SetPropertyStr(ctx, proto, "value", JS_NewInt32(ctx, 83)) < 0)
            return -1;
        obj = JS_NewObjectProto(ctx, proto);
        if (mode == 2)
            anchor = JS_NewObjectProto(ctx, proto);
        fn = JS_Eval(ctx, code, strlen(code), "eager-lifetime", JS_EVAL_TYPE_GLOBAL);
        if (JS_IsException(fn) || JS_IsException(obj) || JS_IsException(anchor))
            return -1;
        args[0] = obj;
        args[1] = JS_NewInt32(ctx, 9);
        for (i = 0; i < 128; i++) {
            int32_t value;
            result = JS_Call(ctx, fn, JS_UNDEFINED, 2, args);
            if (JS_IsException(result) || JS_ToInt32(ctx, &value, result) ||
                value != (mode == 2 ? 11 : 83))
                return -1;
            JS_FreeValue(ctx, result);
        }
        if (mode == 3) {
            /* The prototype is the final owner of a cached function. */
            if (JS_SetPropertyStr(ctx, proto, "ownedReader", JS_DupValue(ctx, fn)) < 0)
                return -1;
            JS_FreeValue(ctx, fn);
            fn = JS_UNDEFINED;
        }
        if (!(mode & 1)) {
            JS_FreeValue(ctx, obj);
            JS_FreeValue(ctx, anchor);
            anchor = JS_UNDEFINED;
            /* Reuse a cache-only shape while the prototype is still alive.
             * Mode2 also exercises native transition target reactivation. */
            obj = JS_NewObjectProto(ctx, proto);
            args[0] = obj;
            for (i = 0; i < 4; i++) {
                int32_t value;
                result = JS_Call(ctx, fn, JS_UNDEFINED, 2, args);
                if (JS_IsException(result) || JS_ToInt32(ctx, &value, result) ||
                    value != (mode == 2 ? 11 : 83))
                    return -1;
                JS_FreeValue(ctx, result);
                if (i == 1)
                    JS_RunGC(rt); /* Live instance anchors the weak graph. */
            }
        }
        if (mode & 1) {
            JS_FreeValue(ctx, proto);
            JS_FreeValue(ctx, obj);
        } else {
            JS_FreeValue(ctx, obj);
            JS_FreeValue(ctx, proto);
        }
        JS_FreeValue(ctx, anchor);
        printf("EAGER lifetime mode=%d before_gc=%u\n", mode, probe_finalized - before);
        if (!getenv("QJS_DISABLE_PROPERTY_IC_WEAK_PROTO") && probe_finalized != before + 1)
            return -1;
        JS_RunGC(rt);
        if (probe_finalized != before + 1)
            return -1;
        JS_FreeValue(ctx, fn);
    }
    return 0;
}
static int cycle_anchor_lifetime(JSContext *ctx, JSRuntime *rt, JSClassID cls)
{
    unsigned before = probe_finalized;
    JSValue proto = JS_NewObjectProtoClass(ctx, JS_NULL, cls);
    JSValue anchor = JS_NewObjectProto(ctx, proto), object = JS_NewObjectProto(ctx, proto);
    const char *code = "(function(o){o.x=1;o.self=o;return 1})";
    JSValue fn = JS_Eval(ctx, code, strlen(code), "cycle-anchor-lifetime", JS_EVAL_TYPE_GLOBAL);
    JSValue result = JS_Call(ctx, fn, JS_UNDEFINED, 1, &object);
    uint32_t counts[7];
    if (JS_IsException(result))
        return -1;
    JS_FreeValue(ctx, result);
    JS_FreeValue(ctx, object);
    JS_RunGC(rt);
    if (js_property_ic_inspect(fn, counts) < 0)
        return -1;
    if (!getenv("QJS_DISABLE_PROPERTY_IC") && counts[5] == 0)
        return -1;
    /* Cycle cleanup removed the final ordinary successor reference while
     * a predecessor anchored its IC graph. It must also weaken that edge. */
    JS_FreeValue(ctx, anchor);
    JS_FreeValue(ctx, proto);
    printf("CYCLE_ANCHOR before_second_gc=%u\n", probe_finalized - before);
    if (!getenv("QJS_DISABLE_PROPERTY_IC_WEAK_PROTO") && probe_finalized != before + 1)
        return -1;
    JS_RunGC(rt);
    if (probe_finalized != before + 1)
        return -1;
    JS_FreeValue(ctx, fn);
    return 0;
}
static int inspect(JSContext *ctx, const char *name, unsigned kind, unsigned minimum)
{
    JSValue function = global(ctx, name);
    uint32_t counts[7];
    int sites = js_property_ic_inspect(function, counts);
    JS_FreeValue(ctx, function);
    printf(
        "CACHE %s sites=%d own=%u proto=%u unset=%u replace=%u transition=%u resize=%u mega=%u\n",
        name, sites, counts[1], counts[2], counts[3], counts[4], counts[5], counts[6], counts[0]);
    if (!getenv("QJS_DISABLE_PROPERTY_IC") && (sites <= 0 || counts[kind] < minimum))
        return -1;
    return 0;
}
int main(void)
{
    JSRuntime *rt = JS_NewRuntime();
    JSContext *ctx;
    JSValue obj, fn, result, proto, anchor;
    JSAtom atoms[2];
    JSValue values[2];
    JSClassID probe_class = 0;
    JSClassDef probe_def = {"PropertyICProbe", probe_finalizer, NULL, NULL, NULL};
    JSClassDef alias_def = {"SelfAliasProbe", alias_finalizer, NULL, NULL, NULL};
    uint32_t weak_counts[7];
    JSMemoryUsage before, after;
    int64_t number;
    int i;
    if (!rt || !(ctx = JS_NewContext(rt)))
        return 1;
    if (evaluate(
            ctx,
            "function read(o){return o.value} function missing(o){return o.missing}"
            "function put(o,v){o.value=v} function make(v){this.a=v;this.b=v+1;this.c=v+2;this.d=v+3}"
            "function own(o){return o.value}"
            "var shapes=[{value:0},{a:0,value:1},{b:0,value:2},{c:0,value:3}];"
            "var proto={value:20},o=Object.create(proto),x={value:1};"
            /* Weak transition metadata survives GC only while an actual instance
         * anchors the graph. Keep one instance during coverage inspection. */
            "var makeAnchor=new make(0);"
            "for(var i=0;i<3000;i++){read(shapes[i%4]);missing(x);put(x,i);new make(i)}"
            "function inherited(o){return o.value} for(var i=0;i<1000;i++)inherited(o);"
            "var diverseAnchors=[];function diverse(o){return o.value} for(var i=0;i<60;i++){var t={value:i};t['unique'+i]=1;diverseAnchors.push(t)}"
            "function oomRead(o){try{return o.value}catch(e){return -1}}"
            "function resize(o,v){try{o.c=v;return o.c}catch(e){throw e}}"
            "var resizeAnchor={a:1,b:2};resize(resizeAnchor,3);"
            /* Lazy prototype initialization above may invalidate the conservative
         * runtime epoch. Refresh coverage after setup, without changing keys. */
            "new make(1);resize({a:1,b:2},3);"
            "for(var i=0;i<4;i++)read(shapes[i]);missing(x);put(x,2);inherited(o);"
            /* GC deliberately resets churn. Exercise persistent diversity without
         * intervening object allocations, after all receivers are prepared. */
            "for(var i=0;i<60;i++)diverse(diverseAnchors[i])") < 0)
        return 2;
    if (inspect(ctx, "read", 1, 2) || inspect(ctx, "missing", 3, 1) || inspect(ctx, "put", 4, 1) ||
        inspect(ctx, "make", 5, 1) || inspect(ctx, "make", 6, 1) || inspect(ctx, "resize", 6, 1) ||
        inspect(ctx, "inherited", 2, 1) || inspect(ctx, "diverse", 0, 1))
        return 3;
    /* Exotic array method/length accesses keep the established dispatch rather
     * than repeatedly creating unfillable by-id cache sites. */
    if (evaluate(
            ctx,
            "function arrayPath(a,v){a.push(v);a.length=a.length-1;return a.length} var arrayAnchor=[];for(var i=0;i<1000;i++){if(arrayPath(arrayAnchor,i)!==0)throw Error('array path')}"))
        return 28;
    fn = global(ctx, "arrayPath");
    if (js_property_ic_inspect(fn, weak_counts) < 0)
        return 29;
    for (i = 0; i < 7; i++)
        if (weak_counts[i])
            return 30;
    JS_FreeValue(ctx, fn);
    puts("EXOTIC array method/length bypass PASS");
    JS_NewClassID(rt, &alias_class);
    if (JS_NewClass(rt, alias_class, &alias_def) < 0)
        return 25;
    {
        JSValue global = JS_GetGlobalObject(ctx);
        JS_SetPropertyStr(ctx, global, "makeAliasSelf",
                          JS_NewCFunction(ctx, make_alias, "makeAliasSelf", 0));
        JS_SetPropertyStr(ctx, global, "aliasFinalized",
                          JS_NewCFunction(ctx, alias_count, "aliasFinalized", 0));
        JS_FreeValue(ctx, global);
    }
    if (evaluate(
            ctx,
            "function clearAliasSelf(){makeAliasSelf().value=1;return aliasFinalized()} for(let i=1;i<=100;i++){let n=clearAliasSelf();if(n!==i)throw Error('alias finalizer '+n+' expected '+i)}"))
        return 26;
    if (inspect(ctx, "clearAliasSelf", 4, 1))
        return 27;
    printf("SELF_ALIAS immediate finalizers=%d PASS\n", alias_finalized);
    /* Cached empty predecessor must not be mutated by the public bulk builder. */
    atoms[0] = JS_NewAtom(ctx, "a");
    atoms[1] = JS_NewAtom(ctx, "b");
    values[0] = JS_NewInt32(ctx, 17);
    values[1] = JS_NewInt32(ctx, 18);
    obj = JS_NewObjectFrom(ctx, 2, atoms, values);
    JS_FreeAtom(ctx, atoms[0]);
    JS_FreeAtom(ctx, atoms[1]);
    if (JS_IsException(obj))
        return 4;
    result = JS_GetPropertyStr(ctx, obj, "a");
    if (JS_ToInt64(ctx, &number, result) || number != 17)
        return 5;
    JS_FreeValue(ctx, result);
    JS_FreeValue(ctx, obj);
    /* Try/catch makes this a C opcode body; a failed OPTIONAL cache allocation
     * must preserve a successful already-allocated own data read. */
    fn = global(ctx, "oomRead");
    obj = JS_NewObject(ctx);
    JS_SetPropertyStr(ctx, obj, "value", JS_NewInt32(ctx, 42));
    JS_ComputeMemoryUsage(rt, &before);
    JS_SetMemoryLimit(rt, before.malloc_size);
    result = JS_Call(ctx, fn, JS_UNDEFINED, 1, &obj);
    JS_SetMemoryLimit(rt, 0);
    if (JS_IsException(result) || JS_ToInt64(ctx, &number, result) || number != 42)
        return 6;
    JS_FreeValue(ctx, result);
    JS_FreeValue(ctx, fn);
    JS_FreeValue(ctx, obj);
    /* A cached capacity-changing transition must preserve its predecessor
     * after an allocation failure, then successfully retry under the same IC. */
    fn = global(ctx, "resize");
    obj = JS_NewObject(ctx);
    JS_SetPropertyStr(ctx, obj, "a", JS_NewInt32(ctx, 1));
    JS_SetPropertyStr(ctx, obj, "b", JS_NewInt32(ctx, 2));
    JS_ComputeMemoryUsage(rt, &before);
    JS_SetMemoryLimit(rt, before.malloc_size);
    {
        JSValue args[2] = {obj, JS_NewInt32(ctx, 5)};
        result = JS_Call(ctx, fn, JS_UNDEFINED, 2, args);
        JS_SetMemoryLimit(rt, 0);
        if (!JS_IsException(result))
            return 10;
        result = JS_GetException(ctx);
        JS_FreeValue(ctx, result);
        result = JS_GetPropertyStr(ctx, obj, "c");
        if (!JS_IsUndefined(result))
            return 11;
        JS_FreeValue(ctx, result);
        result = JS_GetPropertyStr(ctx, obj, "a");
        if (JS_ToInt64(ctx, &number, result) || number != 1)
            return 12;
        JS_FreeValue(ctx, result);
        result = JS_Call(ctx, fn, JS_UNDEFINED, 2, args);
        if (JS_IsException(result) || JS_ToInt64(ctx, &number, result) || number != 5)
            return 13;
        JS_FreeValue(ctx, result);
    }
    JS_FreeValue(ctx, fn);
    JS_FreeValue(ctx, obj);
    /* A LIVE bytecode must not keep a dead prototype alive through its IC. */
    JS_NewClassID(rt, &probe_class);
    if (JS_NewClass(rt, probe_class, &probe_def) < 0)
        return 14;
    proto = JS_NewObjectProtoClass(ctx, JS_NULL, probe_class);
    JS_SetPropertyStr(ctx, proto, "value", JS_NewInt32(ctx, 83));
    obj = JS_NewObjectProto(ctx, proto);
    fn = JS_Eval(ctx, "(function(o){try{return o.value}catch(e){throw e}})",
                 strlen("(function(o){try{return o.value}catch(e){throw e}})"), "weak-ic",
                 JS_EVAL_TYPE_GLOBAL);
    result = JS_Call(ctx, fn, JS_UNDEFINED, 1, &obj);
    if (JS_IsException(result) || JS_ToInt64(ctx, &number, result) || number != 83)
        return 15;
    if (js_property_ic_inspect(fn, weak_counts) < 0)
        return 23;
    if (!getenv("QJS_DISABLE_PROPERTY_IC") && weak_counts[2] == 0)
        return 24;
    JS_FreeValue(ctx, result);
    JS_FreeValue(ctx, obj);
    JS_FreeValue(ctx, proto);
    printf("WEAK prototype before_gc=%u\n", probe_finalized);
    if (!getenv("QJS_DISABLE_PROPERTY_IC_WEAK_PROTO") && probe_finalized != 1)
        return 31;
    JS_RunGC(rt);
    if (probe_finalized != 1)
        return 16;
    if (js_property_ic_inspect(fn, weak_counts) < 0)
        return 17;
    if (weak_counts[2] != 0)
        return 18;
    JS_FreeValue(ctx, fn);
    /* Keep a transition while an actual predecessor instance is alive, then
     * clear its whole unanchored graph after the last instance disappears. */
    proto = JS_NewObject(ctx);
    anchor = JS_NewObjectProto(ctx, proto);
    obj = JS_NewObjectProto(ctx, proto);
    fn = JS_Eval(ctx, "(function(o){o.weakTransitionUnique=7;return o.weakTransitionUnique})",
                 strlen("(function(o){o.weakTransitionUnique=7;return o.weakTransitionUnique})"),
                 "conditional-ic", JS_EVAL_TYPE_GLOBAL);
    result = JS_Call(ctx, fn, JS_UNDEFINED, 1, &obj);
    if (JS_IsException(result))
        return 19;
    JS_FreeValue(ctx, result);
    JS_FreeValue(ctx, obj);
    JS_RunGC(rt);
    if (js_property_ic_inspect(fn, weak_counts) < 0)
        return 20;
    if (!getenv("QJS_DISABLE_PROPERTY_IC") && weak_counts[5] == 0)
        return 21;
    JS_FreeValue(ctx, anchor);
    JS_RunGC(rt);
    if (js_property_ic_inspect(fn, weak_counts) < 0 || weak_counts[5] != 0)
        return 22;
    JS_FreeValue(ctx, fn);
    JS_FreeValue(ctx, proto);
    printf("WEAK prototype finalizers=%u; conditional transition pruned PASS\n", probe_finalized);
    if (eager_lifetimes(ctx, rt, probe_class))
        return 32;
    if (cycle_anchor_lifetime(ctx, rt, probe_class))
        return 33;
    JS_FreeContext(ctx);
    JS_RunGC(rt);
    /* Repeated cycles must return to the same live allocation count after GC.
     * Warm the retained runtime bookkeeping before choosing the comparison. */
    for (i = 0; i < 12; i++) {
        ctx = JS_NewContext(rt);
        if (!ctx)
            return 7;
        if (evaluate(
                ctx,
                "for(var i=0;i<100;i++){let p={},o=Object.create(p);let f=Function('o','return o.value');p.f=f;p.value=i;if(f(o)!==i)throw Error('cycle')}"))
            return 8;
        JS_FreeContext(ctx);
        JS_RunGC(rt);
        if (i == 1)
            JS_ComputeMemoryUsage(rt, &before);
    }
    JS_ComputeMemoryUsage(rt, &after);
    printf("CYCLE live allocations %lld -> %lld bytes %lld -> %lld\n",
           (long long)before.malloc_count, (long long)after.malloc_count,
           (long long)before.malloc_size, (long long)after.malloc_size);
    if (after.malloc_count != before.malloc_count || after.malloc_size != before.malloc_size)
        return 9;
    JS_FreeRuntime(rt);
    puts("PROPERTY_IC_HOST PASS");
    return 0;
}
