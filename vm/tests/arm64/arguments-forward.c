/* Actual argument .call children,logical wrapper depth and public semantics. */
#ifdef NDEBUG
#undef NDEBUG
#endif
#include "quickjs.h"
#include "src/arm64/linux/interpreter-observe.h"
#include <assert.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
extern _Atomic uint64_t JS_FrameArgumentsForwardStats[2];
static JSValue eval(JSContext *c, const char *s)
{
    JSValue v = JS_Eval(c, s, strlen(s), "arguments-forward", 0);
    if (JS_IsException(v)) {
        JSValue e = JS_GetException(c);
        const char *p = JS_ToCString(c, e);
        fprintf(stderr, "arguments forward: %s\n", p ? p : "exception");
        JS_FreeCString(c, p);
        JS_FreeValue(c, e);
        abort();
    }
    return v;
}
int main(void)
{
    setbuf(stdout, NULL);
    JSRuntime *r = JS_NewRuntime();
    assert(r);
    JSContext *c = JS_NewContext(r);
    assert(c);
    JSValue drivers[] = {
        eval(c, "(function(f,a,b){let r=f.call(undefined,a,b);return r})"),
        eval(c, "(function(f,a,b){return f.call(undefined,a,b)})"),
        eval(c, "(function(f,a,b){return Function.prototype.call.call(f,undefined,a,b)})")};
    JSValue targets[] = {
        eval(c, "(function(a,b,c){'use strict';let p=arguments;return p.length+p[0]+p[1]})"),
        eval(c, "(function(a,b,c){let p=arguments;return p.length+p[0]+p[1]})")};
    unsigned disabled =
        getenv("QJS_DISABLE_FRAME_ARGUMENTS") || getenv("QJS_DISABLE_FRAME_ARGUMENTS_FORWARD") ||
        getenv("QJS_DISABLE_FRAME_CALL_FORWARD") || getenv("QJS_DISABLE_REGISTER_INTERP");
    for (unsigned k = 0; k < 3; k++)
        for (unsigned mapped = 0; mapped < 2; mapped++) {
            JSValue args[] = {targets[mapped], JS_NewInt32(c, 17), JS_NewInt32(c, 23)};
            JSValue v = JS_Call(c, drivers[k], JS_UNDEFINED, 3, args);
            assert(!JS_IsException(v));
            JS_FreeValue(c, v);
            uint64_t before = atomic_load(&JS_FrameArgumentsForwardStats[0]),
                     depth = atomic_load(&JS_FrameArgumentsForwardStats[1]);
            QJSArmVMCounts a, b;
            qjs_aarch64_vm_counts(&a);
            for (unsigned i = 0; i < 128; i++) {
                v = JS_Call(c, drivers[k], JS_UNDEFINED, 3, args);
                int32_t n = -1;
                assert(!JS_IsException(v) && !JS_ToInt32(c, &n, v) && n == 42);
                JS_FreeValue(c, v);
            }
            qjs_aarch64_vm_counts(&b);
            uint64_t hits = atomic_load(&JS_FrameArgumentsForwardStats[0]) - before,
                     levels = atomic_load(&JS_FrameArgumentsForwardStats[1]) - depth;
            printf(
                "FORWARD_COHORT driver=%u mapped=%u children=%llu logical=%llu activations=%llu disabled=%u\n",
                k, mapped, (unsigned long long)hits, (unsigned long long)levels,
                (unsigned long long)(b.activations - a.activations), disabled);
            assert(disabled ? hits == 0 : hits == 128);
            if (!disabled) {
                assert(levels == 128 * (k == 2 ? 2 : 1));
                assert(b.activations - a.activations == 128);
            }
        }
    JSValue v = eval(
        c,
        "(function(){function ck(x){if(!x)throw Error('argument forwarding semantics')}"
        "function target(a,b){return arguments}function empty(f){return f.call(undefined)}let z=empty(target);ck(z.length===0&&z[0]===undefined);"
        "function extra(f){return f.call(undefined,10,11,18)}let t=extra(target);ck(t.length===3&&t[2]===18);"
        "function hold(a){return [()=>a,arguments]}function run(f,x){return f.call(undefined,x)}let h=run(hold,{v:1});let owner={v:42};h[1][0]=owner;ck(h[0]()===owner);"
        "function reject(a){throw arguments[0]}let token={};try{run(reject,token);ck(false)}catch(e){ck(e===token)}"
        "let fake=function(){return 42};Object.defineProperty(fake,'call',{value:function(){return 7}});ck(run(fake,1)===7);"
        "let bound=target.bind(null,17);let b=run(bound,23);ck(b.length===2&&b[0]===17&&b[1]===23);return 42})()");
    int32_t n;
    assert(!JS_ToInt32(c, &n, v) && n == 42);
    JS_FreeValue(c, v);
    for (unsigned k = 0; k < 3; k++)
        JS_FreeValue(c, drivers[k]);
    for (unsigned k = 0; k < 2; k++)
        JS_FreeValue(c, targets[k]);
    JS_RunGC(r);
    JS_FreeContext(c);
    JS_RunGC(r);
    JS_FreeRuntime(r);
    puts("AARCH64_ARGUMENTS_FORWARD_OK");
    return 0;
}
