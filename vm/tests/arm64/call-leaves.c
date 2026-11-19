#ifdef NDEBUG
#undef NDEBUG
#endif
#include "quickjs.h"
#include <assert.h>
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
extern void qjs_aarch64_vm_call_leaf_counts(uint64_t[12]);
static JSValue evaluate(JSContext *ctx, const char *s)
{
    JSValue v = JS_Eval(ctx, s, strlen(s), "call-leaves-paths.js", JS_EVAL_TYPE_GLOBAL);
    if (JS_IsException(v)) {
        JSValue e = JS_GetException(ctx);
        const char *t = JS_ToCString(ctx, e);
        fprintf(stderr, "eval: %s\n", t ? t : "error");
        JS_FreeCString(ctx, t);
        JS_FreeValue(ctx, e);
    }
    assert(!JS_IsException(v));
    return v;
}
static void run(JSContext *ctx, const char *s)
{
    JSValue v = evaluate(ctx, s);
    JS_FreeValue(ctx, v);
}
static void cohort(JSContext *ctx, const char *body, JSValue *values, unsigned n, int expected)
{
    JSValue f = evaluate(ctx, body),
            driver = evaluate(ctx, n == 1 ? "(function(f,a){return f(a);})"
                                          : "(function(f,a,b){return f(a,b);})");
    JSValue args[3] = {f, values[0], n > 1 ? values[1] : JS_UNDEFINED};
    for (unsigned k = 0; k < 130; k++) {
        JSValue out = JS_Call(ctx, driver, JS_UNDEFINED, n + 1, args);
        int32_t z;
        if (JS_IsException(out)) {
            JSValue e = JS_GetException(ctx);
            const char *s = JS_ToCString(ctx, e);
            fprintf(stderr, "cohort %s: %s\n", body, s ? s : "error");
            JS_FreeCString(ctx, s);
            JS_FreeValue(ctx, e);
        }
        assert(!JS_IsException(out));
        assert(!JS_ToInt32(ctx, &z, out) && z == expected);
        JS_FreeValue(ctx, out);
    }
    JS_FreeValue(ctx, driver);
    JS_FreeValue(ctx, f);
}
int main(void)
{
    JSRuntime *rt = JS_NewRuntime();
    JSContext *ctx = JS_NewContext(rt);
    assert(ctx);
    JSValue f = evaluate(ctx, "(function(x){return x+3})"), a = JS_NewInt32(ctx, 7), v;
    for (unsigned n = 0; n < 130; n++) {
        v = JS_Call(ctx, f, JS_UNDEFINED, 1, &a);
        int32_t z;
        assert(!JS_ToInt32(ctx, &z, v) && z == 10);
        JS_FreeValue(ctx, v);
    }
    JSValue driver = evaluate(ctx, "(function(f,x){return f(x);})"), args[2] = {f, a};
    for (unsigned n = 0; n < 130; n++) {
        v = JS_Call(ctx, driver, JS_UNDEFINED, 2, args);
        int32_t z;
        assert(!JS_ToInt32(ctx, &z, v) && z == 10);
        JS_FreeValue(ctx, v);
    }
    JS_FreeValue(ctx, driver);
    JS_FreeValue(ctx, f);
    run(ctx,
        "function leafRoot(){ let total=0; function id(x){return x;} function plus(x){return x+3;} function red(a,b){return (a+b+1)|0;} let cell=7; function cap(x){cell=(cell+x+1)|0;} const o={x:17,f(){return this.x;}};const sym=Symbol();const box={x:sym};const obj={x:sym,s(){return this.x===box.x;}};function expr(x){return (x%100)===0;}function chars(x){return x=='a'||x=='b'||x=='c';}for(let i=0;i<128;i++){if(id(o)!==o||plus(i)!==i+3||red(2,3)!==6||o.f()!==17||!obj.s()||!expr(200)||!chars('b'))throw Error('leaf');cap(1);total+=i;}if(cell!==263)throw Error('capture');return total;} for(let i=0;i<3;i++)if(leafRoot()!==8128)throw Error('root');");
    JSValue vals[2] = {JS_NewInt32(ctx, 2), JS_NewInt32(ctx, 3)};
    cohort(ctx, "(function(a,b){return (a+b+1)|0;})", vals, 2, 6);
    cohort(ctx, "(function(){let cell=7;return function(a){cell=(cell+a+1)|0;};})()", vals, 1, 0);
    vals[0] = JS_NewInt32(ctx, 200);
    cohort(ctx, "(function(a){return a%100===0;})", vals, 1, 1);
    vals[0] = JS_NewString(ctx, "b");
    cohort(ctx, "(function(a){return a=='a'||a=='b'||a=='c';})", vals, 1, 1);
    JS_FreeValue(ctx, vals[0]);
    JSValue methods = evaluate(ctx, "({x:17,f(){return this.x;}})"),
            mdriver = evaluate(ctx, "(function(o){return o.f();})");
    for (unsigned k = 0; k < 130; k++) {
        v = JS_Call(ctx, mdriver, JS_UNDEFINED, 1, &methods);
        int32_t z;
        assert(!JS_ToInt32(ctx, &z, v) && z == 17);
        JS_FreeValue(ctx, v);
    }
    JS_FreeValue(ctx, mdriver);
    JS_FreeValue(ctx, methods);
    methods = evaluate(
        ctx, "(function(){let s=Symbol(),box={x:s};return {x:s,f(){return this.x===box.x;}};})()");
    mdriver = evaluate(ctx, "(function(o){return o.f();})");
    for (unsigned k = 0; k < 130; k++) {
        v = JS_Call(ctx, mdriver, JS_UNDEFINED, 1, &methods);
        assert(JS_ToBool(ctx, v) == 1);
        JS_FreeValue(ctx, v);
    }
    JS_FreeValue(ctx, mdriver);
    JS_FreeValue(ctx, methods);
    methods = evaluate(
        ctx,
        "(function(){'use strict';return {left:'a',f:function(other){return this.left.localeCompare(other.right);}};})()");
    mdriver = evaluate(ctx, "(function(o,p){return o.f(p);})");
    JSValue other = evaluate(ctx, "({right:'b'})"), pair[2] = {methods, other};
    for (unsigned k = 0; k < 130; k++) {
        v = JS_Call(ctx, mdriver, JS_UNDEFINED, 2, pair);
        int32_t z;
        assert(!JS_ToInt32(ctx, &z, v) && z == -1);
        JS_FreeValue(ctx, v);
    }
    JS_FreeValue(ctx, mdriver);
    JS_FreeValue(ctx, methods);
    JS_FreeValue(ctx, other);
    uint64_t counts[12];
    qjs_aarch64_vm_call_leaf_counts(counts);
    printf("AARCH64_CALL_LEAF_COUNTS");
    for (unsigned i = 0; i < 12; i++)
        printf(" %llu", (unsigned long long)counts[i]);
    puts("");
    if (getenv("QJS_DISABLE_REGISTER_INTERP") || getenv("QJS_DISABLE_INTERP_FRAME")) {
        for (unsigned i = 0; i < 12; i++)
            assert(counts[i] == 0);
    } else {
        const char *getter = getenv("QJS_DISABLE_THIS_FIELD_LEAF");
        if (getenv("QJS_DISABLE_NATIVE_CHILD_LEAF"))
            assert(!counts[0] && !counts[1] && !counts[2] && !counts[3] && !counts[4] &&
                   !counts[9]);
        if (getter && *getter != '0')
            assert(!counts[3] && !counts[4]);
        if (getenv("QJS_DISABLE_FRAME_LEAF_ENTRY"))
            assert(!counts[5] && !counts[7] && !counts[8]);
        if (getenv("QJS_DISABLE_FRAME_CHARACTER_SET_LEAF"))
            assert(!counts[7]);
        if (getenv("QJS_DISABLE_FRAME_COMPOUND_LEAF"))
            assert(!counts[8]);
        if (getenv("QJS_DISABLE_NATIVE_INT_EXPRESSION_LEAF"))
            assert(!counts[6]);
        if (!getenv("QJS_DISABLE_NATIVE_CHILD_LEAF") && !getter &&
            !getenv("QJS_DISABLE_FRAME_LEAF_ENTRY") &&
            !getenv("QJS_DISABLE_FRAME_CHARACTER_SET_LEAF") &&
            !getenv("QJS_DISABLE_FRAME_COMPOUND_LEAF") &&
            !getenv("QJS_DISABLE_NATIVE_INT_EXPRESSION_LEAF"))
            for (unsigned i = 0; i < 11; i++)
                assert(counts[i] > 0);
    }
    JS_RunGC(rt);
    JS_FreeContext(ctx);
    JS_FreeRuntime(rt);
    puts("AARCH64_CALL_LEAVES_OK");
    return 0;
}
