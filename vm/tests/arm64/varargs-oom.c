/* Fresh runtime faults/recovery of large owned spread and apply windows. */
#ifdef NDEBUG
#undef NDEBUG
#endif
#include "quickjs.h"
#include "interpreter-aarch64-values.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "tests/common/native_oom_allocator.h"
static uintptr_t word(JSRuntime *rt, size_t offset)
{
    uintptr_t v;
    memcpy(&v, (const char *)rt + offset, sizeof(v));
    return v;
}
static JSValue eval(JSContext *c, const char *s)
{
    JSValue v = JS_Eval(c, s, strlen(s), "varargs-fault", 0);
    assert(!JS_IsException(v));
    return v;
}
int main(void)
{
    unsigned failures = 0, successes = 0, rejected = 0, trials = 0;
    for (unsigned variant = 0; variant < 3; variant++)
        for (unsigned point = 1; point <= 32; point++) {
            Allocator ledger = {0};
            JSRuntime *r = JS_NewRuntime2(&functions, &ledger);
            assert(r);
            JS_SetMaxStackSize(r, 4 * 1024 * 1024);
            JSContext *c = JS_NewContext(r);
            assert(c);
            JSValue f = eval(c, "(function(a){return a})"), object = eval(c, "({value:42})");
            JSValue list = JS_NewArray(c);
            assert(!JS_IsException(list));
            for (unsigned i = 0; i < 2048; i++)
                assert(JS_SetPropertyUint32(c, list, i, JS_DupValue(c, object)) >= 0);
            JSValue driver =
                eval(c, variant == 0   ? "(function(f,o,list){let r=f(...list);return r})"
                        : variant == 1 ? "(function(f,o,list){let r=f(o,...list);return r})"
                                       : "(function(f,o,list){let r=f.apply(o,list);return r})");
            JSValue v = JS_Call(c, f, JS_UNDEFINED, 1, &object);
            assert(!JS_IsException(v));
            JS_FreeValue(c, v);
            /* Prime lazy iterator/apply intrinsic definitions before injecting
           faults into the call window itself. The unprimed inherited case
           is separately retained against both prior and disabled images. */
            v = eval(c, "(function(){let n=0;for(const x of [1,2])n+=x;return n})()");
            JS_FreeValue(c, v);
            v = eval(c, "Function.prototype.apply");
            JS_FreeValue(c, v);
            JSValue args[] = {f, object, list};
            uintptr_t top = word(r, ARM_OFF_JSRuntime_stack_top),
                      limit = word(r, ARM_OFF_JSRuntime_stack_limit);
            ledger.fail_at = ledger.sequence + point;
            v = JS_Call(c, driver, JS_UNDEFINED, 3, args);
            ledger.fail_at = 0;
            rejected += ledger.rejected;
            ++trials;
            if (JS_IsException(v)) {
                ++failures;
                JS_FreeValue(c, JS_GetException(c));
            } else {
                ++successes;
                assert(JS_VALUE_GET_TAG(v) == JS_TAG_OBJECT &&
                       JS_VALUE_GET_PTR(v) == JS_VALUE_GET_PTR(object));
            }
            JS_FreeValue(c, v);
            JS_RunGC(r);
            assert(word(r, ARM_OFF_JSRuntime_stack_top) == top &&
                   word(r, ARM_OFF_JSRuntime_stack_limit) == limit);
            v = JS_Call(c, driver, JS_UNDEFINED, 3, args);
            assert(!JS_IsException(v) && JS_VALUE_GET_PTR(v) == JS_VALUE_GET_PTR(object));
            JS_FreeValue(c, v);
            JS_RunGC(r);
            assert(word(r, ARM_OFF_JSRuntime_stack_top) == top &&
                   word(r, ARM_OFF_JSRuntime_stack_limit) == limit);
            JS_FreeValue(c, driver);
            JS_FreeValue(c, list);
            JS_FreeValue(c, object);
            JS_FreeValue(c, f);
            JS_FreeContext(c);
            JS_RunGC(r);
            JS_FreeRuntime(r);
            assert(ledger.live == 0 && ledger.bytes == 0);
        }
    assert(failures > 0 && successes > 0 && rejected > 0 && trials == 96);
    printf(
        "AARCH64_VARARGS_OOM_OK trials=%u failures=%u successes=%u rejected=%u live=0 quota_restored=96\n",
        trials, failures, successes, rejected);
    return 0;
}
