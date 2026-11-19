/* Actual same-activation native Ready path, without private-state writes. */
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
extern _Atomic uint64_t JS_FrameArgumentsStats[7];
static JSValue eval(JSContext *c, const char *s)
{
    JSValue v = JS_Eval(c, s, strlen(s), "native-args-ready", 0);
    assert(!JS_IsException(v));
    return v;
}
int main(void)
{
    JSRuntime *rt = JS_NewRuntime();
    assert(rt);
    JSContext *c = JS_NewContext(rt);
    assert(c);
    JSValue f =
        eval(c, "(function(a,b){'use strict';return arguments.length+arguments[0]+arguments[1]})");
    JSValue drivers[] = {eval(c, "(function(f,a,b){let v=f(a,b);return v})"),
                         eval(c, "(function(f,a,b){return f(a,b)})"),
                         eval(c, "(function(f,a,b){let o={f};return o.f(a,b)})")};
    JSValue args[] = {f, JS_NewInt32(c, 17), JS_NewInt32(c, 23)};
    JSValue v = JS_Call(c, f, JS_UNDEFINED, 2, args + 1);
    int32_t n;
    assert(!JS_IsException(v) && !JS_ToInt32(c, &n, v) && n == 42);
    JS_FreeValue(c, v);
    unsigned disabled =
        getenv("QJS_DISABLE_FRAME_ARGUMENTS") || getenv("QJS_DISABLE_FRAME_ARGUMENTS_NATIVE") ||
        getenv("QJS_DISABLE_FRAME_ARGUMENTS_BORROW") || getenv("QJS_DISABLE_REGISTER_INTERP");
    for (unsigned k = 0; k < 3; k++) {
        uint64_t before = atomic_load(&JS_FrameArgumentsStats[6]);
        QJSArmVMCounts a, b;
        qjs_aarch64_vm_counts(&a);
        for (unsigned i = 0; i < 128; i++) {
            v = JS_Call(c, drivers[k], JS_UNDEFINED, 3, args);
            assert(!JS_IsException(v) && !JS_ToInt32(c, &n, v) && n == 42);
            JS_FreeValue(c, v);
        }
        qjs_aarch64_vm_counts(&b);
        uint64_t hits = atomic_load(&JS_FrameArgumentsStats[6]) - before;
        printf("READY_COHORT %u native=%llu activations=%llu\n", k, (unsigned long long)hits,
               (unsigned long long)(b.activations - a.activations));
        assert(disabled ? hits == 0 : hits == 128);
        if (!disabled)
            assert(b.activations - a.activations == 128);
    }
    for (unsigned k = 0; k < 3; k++) {
        JS_FreeValue(c, drivers[k]);
    }
    JS_FreeValue(c, f);
    JS_FreeContext(c);
    JS_FreeRuntime(rt);
    puts("AARCH64_ARGUMENTS_READY_OK actual128 native children per ordinary/tail/method cohort");
    return 0;
}
