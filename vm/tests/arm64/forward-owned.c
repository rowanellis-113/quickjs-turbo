/* Native forwarding constructor path/ownership controls using public calls. */
#ifdef NDEBUG
#undef NDEBUG
#endif
#include <quickjs.h>
#include <assert.h>
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "tests/common/native_oom_allocator.h"
extern void qjs_aarch64_vm_forward_counts(uint64_t words[16]);
static JSValue eval(JSContext *c, const char *s)
{
    JSValue v = JS_Eval(c, s, strlen(s), "forward-owned-paths", JS_EVAL_TYPE_GLOBAL);
    if (JS_IsException(v)) {
        JSValue e = JS_GetException(c);
        const char *t = JS_ToCString(c, e);
        fprintf(stderr, "EVAL %s\n", t ? t : "unknown");
        abort();
    }
    return v;
}
static int disabled(const char *s)
{
    return getenv(s) != NULL;
}
static void cohort(JSContext *c, const char *name, const char *target, const char *call,
                   unsigned slot, int undef)
{
    char code[2048];
    int n = snprintf(code, sizeof(code),
                     "(function(f,r,v){forwardReserve(v,v,v,v,v,v,v,v);return %s})", call);
    assert(n > 0 && (size_t)n < sizeof(code));
    JSValue driver = eval(c, code), fn = eval(c, target), seed = JS_NewObject(c),
            recv = JS_NewObject(c);
    assert(!JS_IsException(seed) && !JS_IsException(recv));
    assert(JS_SetPropertyStr(c, seed, "cycle", JS_DupValue(c, seed)) >= 0);
    JSValue args[3] = {fn, recv, seed};
    for (unsigned warm = 0; warm < 4; warm++) {
        JSValue v = JS_Call(c, driver, JS_UNDEFINED, 3, args);
        assert(!JS_IsException(v));
        assert(undef ? JS_IsUndefined(v) : JS_IsSameValue(c, v, seed));
        JS_FreeValue(c, v);
    }
    uint64_t before[16], after[16];
    qjs_aarch64_vm_forward_counts(before);
    for (unsigned repeat = 0; repeat < 32; repeat++) {
        JSValue v = JS_Call(c, driver, JS_UNDEFINED, 3, args);
        assert(!JS_IsException(v));
        assert(undef ? JS_IsUndefined(v) : JS_IsSameValue(c, v, seed));
        JS_FreeValue(c, v);
    }
    qjs_aarch64_vm_forward_counts(after);
    uint64_t d[16];
    for (unsigned i = 0; i < 16; i++)
        d[i] = after[i] - before[i];
    printf("FORWARD_OWNED_PATH %s C=%" PRIu64 " Cchild=%" PRIu64 " pop=%" PRIu64 " leaf=%" PRIu64
           " own=%" PRIu64 " borrow=%" PRIu64 " missing=%" PRIu64 "\n",
           name, d[0], d[1], d[3], d[4], d[5], d[6], d[7]);
    fflush(stdout);
    int active = !disabled("QJS_DISABLE_FRAME_CALL_FORWARD") &&
                 !disabled("QJS_DISABLE_REGISTER_INTERP") && !disabled("QJS_DISABLE_INTERP_FRAME");
    if (!active) {
        assert(!d[4] && !d[5] && !d[6] && !d[7]);
    } else if (disabled("QJS_DISABLE_FRAME_CALL_FORWARD_NATIVE") ||
               disabled("QJS_DISABLE_FRAME_CALL_FORWARD_OWNED")) {
        assert(!d[4] && !d[5] && !d[6] && !d[7]);
        assert(d[1] == 32);
    } else {
        unsigned expected = slot;
        if (disabled("QJS_DISABLE_FRAME_CALL_FORWARD_BORROW") ||
            (slot == 7 && disabled("QJS_DISABLE_FRAME_CALL_FORWARD_BORROW_MISSING")))
            expected = 5;
        assert(d[expected] == 32 && !d[0]);
        for (unsigned i = 5; i <= 7; i++)
            if (i != expected)
                assert(!d[i]);
    }
    JS_FreeValue(c, driver);
    JS_FreeValue(c, fn);
    JS_FreeValue(c, seed);
    JS_FreeValue(c, recv);
    JS_RunGC(JS_GetRuntime(c));
}
int main(void)
{
    Allocator a = {0};
    JSRuntime *r = JS_NewRuntime2(&functions, &a);
    assert(r);
    JSContext *c = JS_NewContext(r);
    assert(c);
    JS_SetMaxStackSize(r, 4 * 1024 * 1024);
    JSValue reserve = eval(c, "globalThis.forwardReserve=function(a,b,c,d,e,f,g,h){return 0}");
    JS_FreeValue(c, reserve);
    cohort(c, "own", "(function(a){let keep=a;a=undefined;return keep})", "f.call(r,v)", 5, 0);
    cohort(c, "provided", "(function(a){let keep=a;return keep})", "f.call(r,v)", 6, 0);
    cohort(c, "extra", "(function(a){let keep=a;return keep})", "f.call(r,v,v,v,v)", 6, 0);
    const char *missing =
        "(function(a,b,c,d){let keep=a;if(b!==undefined||c!==undefined||d!==undefined)throw Error('padding');return keep})";
    cohort(c, "missing", missing, "f.call(r,v)", 7, 0);
    cohort(c, "zero-native", missing, "f.call()", 7, 1);
    cohort(c, "this-only", missing, "f.call(r)", 7, 1);
    char large[4096];
    size_t used = (size_t)snprintf(large, sizeof(large), "(function(");
    for (unsigned i = 0; i < 128; i++)
        used += (size_t)snprintf(large + used, sizeof(large) - used, "%sa%u", i ? "," : "", i);
    used += (size_t)snprintf(
        large + used, sizeof(large) - used,
        "){let keep=a0;if(a127!==undefined)throw Error('far padding');return keep})");
    assert(used < sizeof(large));
    cohort(c, "missing-outside-declared-stack", large, "f.call(r,v)", 5, 0);
    JS_FreeContext(c);
    JS_FreeRuntime(r);
    assert(!a.live && !a.bytes);
    puts("FORWARD_OWNED_PATHS_OK seven-cohorts zero-ledgers");
    return 0;
}
