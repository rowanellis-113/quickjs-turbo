/* Natural source-owned snapshot/fusion/apply execution and component controls. */
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
extern void qjs_aarch64_vm_varargs_counts(uint64_t output[4]);
extern _Atomic uint64_t JS_FrameApplyForwardStats[14];
static JSValue eval(JSContext *c, const char *s)
{
    JSValue v = JS_Eval(c, s, strlen(s), "varargs-paths", 0);
    if (JS_IsException(v)) {
        JSValue e = JS_GetException(c);
        const char *p = JS_ToCString(c, e);
        fprintf(stderr, "varargs paths: %s\n", p ? p : "exception");
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
    JSValue f = eval(c, "(function(a,b,c){return a+b+c})");
    JSValue g = eval(c, "(function(a,b){return this.base+a+b})");
    JSValue receiver = eval(c, "({base:10})");
    JSValue object = JS_DupValue(c, receiver);
    JS_SetPropertyStr(c, object, "f", JS_DupValue(c, g));
    JSValue list = eval(c, "[13,14,15]"), shortlist = eval(c, "[17,15]");
    JSValue warmargs[] = {JS_NewInt32(c, 13), JS_NewInt32(c, 14), JS_NewInt32(c, 15)};
    JSValue v = JS_Call(c, f, JS_UNDEFINED, 3, warmargs);
    assert(!JS_IsException(v));
    JS_FreeValue(c, v);
    v = JS_Call(c, g, receiver, 2, warmargs);
    assert(!JS_IsException(v));
    JS_FreeValue(c, v);
    JSValue drivers[] = {
        eval(c, "(function(f,list){let result=f(...list);return result})"),
        eval(c, "(function(f,list){let result=f(10,...list);return result})"),
        eval(c, "(function(o,list){let result=o.f(...list);return result})"),
        eval(c, "(function(f,self,list){let result=f.apply(self,list);return result})")};
    unsigned off = getenv("QJS_DISABLE_INTERP_FRAME") || getenv("QJS_DISABLE_REGISTER_INTERP");
    for (unsigned k = 0; k < 4; k++) {
        JSValue args[] = {k == 2   ? object
                          : k == 3 ? g
                                   : f,
                          k == 0   ? list
                          : k == 3 ? receiver
                                   : shortlist,
                          shortlist};
        unsigned argc = k == 3 ? 3 : 2;
        v = JS_Call(c, drivers[k], JS_UNDEFINED, argc, args);
        assert(!JS_IsException(v));
        JS_FreeValue(c, v);
        uint64_t a[4], b[4], ap = atomic_load(&JS_FrameApplyForwardStats[12]);
        QJSArmVMCounts x, y;
        qjs_aarch64_vm_counts(&x);
        qjs_aarch64_vm_varargs_counts(a);
        for (unsigned i = 0; i < 128; i++) {
            v = JS_Call(c, drivers[k], JS_UNDEFINED, argc, args);
            int32_t n = -1;
            assert(!JS_IsException(v) && !JS_ToInt32(c, &n, v) && n == 42);
            JS_FreeValue(c, v);
        }
        qjs_aarch64_vm_counts(&y);
        qjs_aarch64_vm_varargs_counts(b);
        for (unsigned i = 0; i < 4; i++)
            b[i] -= a[i];
        ap = atomic_load(&JS_FrameApplyForwardStats[12]) - ap;
        unsigned directoff = off || getenv("QJS_DISABLE_FRAME_VARARGS") ||
                             getenv("QJS_DISABLE_FRAME_VARARGS_DIRECT");
        unsigned fuseoff = directoff || getenv("QJS_DISABLE_FRAME_VARARGS_FUSION");
        unsigned applyoff = off || getenv("QJS_DISABLE_FRAME_APPLY_DIRECT") ||
                            getenv("QJS_DISABLE_FRAME_CALL_FORWARD");
        printf(
            "VARARGS_COHORT %u snapshots=%llu fused=%llu attempts=%llu published=%llu apply=%llu activations=%llu\n",
            k, (unsigned long long)b[0], (unsigned long long)b[1], (unsigned long long)b[2],
            (unsigned long long)b[3], (unsigned long long)ap,
            (unsigned long long)(y.activations - x.activations));
        if (k < 3) {
            assert(directoff ? b[0] == 0 : b[0] == 128);
            assert(fuseoff || k == 1 ? b[1] == 0 : b[1] == 128);
            assert(directoff ? b[3] == 0 : b[3] == 128);
            if (!directoff)
                assert(y.activations - x.activations == 128);
        } else {
            assert(applyoff ? ap == 0 : ap == 128);
            if (!applyoff)
                assert(y.activations - x.activations == 128);
        }
    }
    for (unsigned k = 0; k < 4; k++)
        JS_FreeValue(c, drivers[k]);
    JS_FreeValue(c, f);
    JS_FreeValue(c, g);
    JS_FreeValue(c, receiver);
    JS_FreeValue(c, object);
    JS_FreeValue(c, list);
    JS_FreeValue(c, shortlist);
    JS_RunGC(r);
    JS_FreeContext(c);
    JS_RunGC(r);
    JS_FreeRuntime(r);
    puts("AARCH64_VARARGS_PATHS_OK");
    return 0;
}
