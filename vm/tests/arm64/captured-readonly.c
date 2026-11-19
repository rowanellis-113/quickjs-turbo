/* Public captured-parameter proof/ownership and actual native admission. MIT. */
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
#include "src/arm64/linux/interpreter-observe.h"
extern int qjs_aarch64_vm_function_info(JSValueConst, uintptr_t *);
extern void qjs_aarch64_vm_forward_counts(uint64_t[16]);
extern int JS_LinuxJSFrameProbe(JSRuntime *, uintptr_t *);
typedef struct {
    JSContext *other;
    JSValue nested;
    unsigned measuring, calls, borrowed, owned, root2, unobserved;
} Fixture;
static int present(const char *n)
{
    return getenv(n) != NULL;
}
static JSValue eval(JSContext *c, const char *s)
{
    JSValue v = JS_Eval(c, s, strlen(s), "captured-readonly", JS_EVAL_TYPE_GLOBAL);
    if (JS_IsException(v)) {
        JSValue e = JS_GetException(c);
        const char *t = JS_ToCString(c, e);
        fprintf(stderr, "EVAL %s\n", t ? t : "unknown");
        abort();
    }
    return v;
}
static JSValue inspect(JSContext *c, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)self;
    assert(argc == 2);
    Fixture *f = JS_GetContextOpaque(c);
    assert(f);
    if (f->measuring) {
        uintptr_t w[10];
        int observed = JS_LinuxJSFrameProbe(JS_GetRuntime(c), w);
        if (observed) {
            assert(w[8] == (uintptr_t)JS_VALUE_GET_PTR(argv[0]));
            assert(w[4] > 0);
            if (w[0] == w[1]) {
                assert(w[2] == w[3]);
                ++f->owned;
            } else {
                assert(!w[2]);
                ++f->borrowed;
            }
            if (w[9] == 2)
                ++f->root2;
        } else {
            assert(present("QJS_DISABLE_REGISTER_INTERP") || present("QJS_DISABLE_INTERP_FRAME"));
            ++f->unobserved;
        }
        ++f->calls;
    }
    JS_RunGC(JS_GetRuntime(c));
    JSValue v = JS_Call(f->other, f->nested, JS_UNDEFINED, 0, NULL);
    int32_t n;
    assert(!JS_IsException(v) && !JS_ToInt32(f->other, &n, v) && n == 31);
    JS_FreeValue(f->other, v);
    JS_RunGC(JS_GetRuntime(c));
    return JS_UNDEFINED;
}
typedef struct {
    const char *name;
    unsigned forwarded, missing, caller_capture, unused_functions, negative;
} Case;
static void cohort(const Case *k)
{
    Allocator a = {0};
    JSRuntime *r = JS_NewRuntime2(&functions, &a);
    assert(r);
    JS_SetMaxStackSize(r, 4 * 1024 * 1024);
    JSContext *c = JS_NewContext(r), *other = JS_NewContext(r);
    assert(c && other);
    Fixture f = {0};
    f.other = other;
    f.nested = eval(other, "(function(){return 31})");
    JS_SetContextOpaque(c, &f);
    JSValue global = JS_GetGlobalObject(c);
    assert(JS_SetPropertyStr(c, global, "inspect", JS_NewCFunction(c, inspect, "inspect", 2)) >= 0);
    JS_FreeValue(c, global);
    char code[24000];
    size_t n = (size_t)snprintf(code, sizeof(code), "(function(a,b){");
    for (unsigned i = 0; i < k->unused_functions; i++)
        n += (size_t)snprintf(code + n, sizeof(code) - n, "function unused%u(){return 0}", i);
    if (k->negative == 1)
        n += (size_t)snprintf(code + n, sizeof(code) - n, "let never=()=>{a=undefined};");
    if (k->negative == 2)
        n += (size_t)snprintf(code + n, sizeof(code) - n, "let never=async()=>0;");
    n += (size_t)snprintf(code + n, sizeof(code) - n, "inspect(currentTarget,a);return()=>a})");
    assert(n < sizeof(code));
    JSValue target = eval(c, code), seed = JS_NewObject(c), receiver = JS_NewObject(c);
    assert(!JS_IsException(seed) && !JS_IsException(receiver));
    assert(JS_SetPropertyStr(c, seed, "cycle", JS_DupValue(c, seed)) >= 0);
    global = JS_GetGlobalObject(c);
    assert(JS_SetPropertyStr(c, global, "currentTarget", JS_DupValue(c, target)) >= 0);
    JS_FreeValue(c, global);
    JSValue warm[2] = {seed, seed};
    JSValue v = JS_Call(c, target, JS_UNDEFINED, 2, warm);
    assert(!JS_IsException(v));
    JS_FreeValue(c, v);
    uintptr_t info[6];
    assert(qjs_aarch64_vm_function_info(target, info));
    int proof = !present("QJS_DISABLE_FRAME_CAPTURED_READONLY") && !k->negative &&
                k->unused_functions <= 62;
    assert(present("QJS_DISABLE_INTERP_FRAME") ? info[0] == 0
                                               : (info[0] & 7) == (unsigned)(proof ? 7 : 5));
    const char *call = k->forwarded ? (k->missing ? "f.call(r,v)" : "f.call(r,v,v)")
                                    : (k->missing ? "f(v)" : "f(v,v)");
    snprintf(code, sizeof(code), "(function(f,r,v){%s%slet out=%s;%sreturn out})",
             k->caller_capture ? "let keep=()=>v;" : "",
             k->forwarded ? "forwardReserve(v,v,v,v,v,v,v,v);" : "", call,
             k->caller_capture ? "if(keep()!==v)throw Error('caller capture overwritten');" : "");
    JSValue reserve = eval(c, "globalThis.forwardReserve=function(){return 0}");
    JS_FreeValue(c, reserve);
    JSValue driver = eval(c, code), args[3] = {target, receiver, seed};
    for (unsigned i = 0; i < 4; i++) {
        v = JS_Call(c, driver, JS_UNDEFINED, 3, args);
        assert(!JS_IsException(v));
        JS_FreeValue(c, v);
    }
    uint64_t before[16], after[16];
    QJSArmVMCounts vb, va;
    qjs_aarch64_vm_forward_counts(before);
    qjs_aarch64_vm_counts(&vb);
    f.measuring = 1;
    for (unsigned i = 0; i < 32; i++) {
        v = JS_Call(c, driver, JS_UNDEFINED, 3, args);
        assert(!JS_IsException(v));
        JSValue got = JS_Call(c, v, JS_UNDEFINED, 0, NULL);
        JS_FreeValue(c, v);
        assert(!JS_IsException(got) && JS_IsSameValue(c, got, seed));
        JS_FreeValue(c, got);
    }
    f.measuring = 0;
    qjs_aarch64_vm_forward_counts(after);
    qjs_aarch64_vm_counts(&va);
    uint64_t own = after[5] - before[5], borrow = after[6] - before[6],
             missing = after[7] - before[7];
    printf("CAPTURED_READONLY_PATH %s kind=%" PRIuPTR " native=%" PRIu64
           " own=%u borrow=%u root2=%u forward=%" PRIu64 ",%" PRIu64 ",%" PRIu64 "\n",
           k->name, info[0], va.native_calls - vb.native_calls, f.owned, f.borrowed, f.root2, own,
           borrow, missing);
    fflush(stdout);
    assert(f.calls == 32);
    int native = !present("QJS_DISABLE_REGISTER_INTERP") && !present("QJS_DISABLE_INTERP_FRAME");
    int entry = native && !present("QJS_DISABLE_AARCH64_CAPTURED_ENTRY");
    int want_borrow = proof && entry;
    if (!k->forwarded) {
        if (k->missing && (k->caller_capture || present("QJS_DISABLE_AARCH64_MISSING_WINDOW")))
            want_borrow = 0;
        int expected = entry && (want_borrow ||
                                 (!present("QJS_DISABLE_AARCH64_OWNED_ARGS") &&
                                  (!k->missing || !present("QJS_DISABLE_AARCH64_OWNED_MISSING"))));
        int caller_leaf = 0;
#ifdef QJS_AARCH64_FAST_VM
        caller_leaf = !present("QJS_DISABLE_FRAME_LEAF_ENTRY");
#endif
        assert(va.native_calls - vb.native_calls ==
               32 * (unsigned)(expected + (native && k->caller_capture && !caller_leaf)));
        assert(!own && !borrow && !missing && !f.root2);
    } else {
        int forward = native && !present("QJS_DISABLE_FRAME_CALL_FORWARD") &&
                      !present("QJS_DISABLE_FRAME_CALL_FORWARD_NATIVE") &&
                      !present("QJS_DISABLE_FRAME_CALL_FORWARD_OWNED");
        want_borrow = proof && forward && !present("QJS_DISABLE_FRAME_CALL_FORWARD_BORROW") &&
                      (!k->missing || !present("QJS_DISABLE_FRAME_CALL_FORWARD_BORROW_MISSING"));
        if (forward) {
            assert(f.root2 == 32);
            assert(own + borrow + missing == 32);
            assert(want_borrow ? (k->missing ? missing == 32 : borrow == 32) : own == 32);
        } else
            assert(!own && !borrow && !missing);
    }
    assert(f.owned + f.borrowed + f.unobserved == 32);
    if (native)
        assert(want_borrow ? f.borrowed == 32 : f.owned == 32);
    JS_FreeValue(c, driver);
    JS_FreeValue(c, target);
    JS_FreeValue(c, seed);
    JS_FreeValue(c, receiver);
    JS_FreeValue(other, f.nested);
    JS_RunGC(r);
    JS_FreeContext(c);
    JS_FreeContext(other);
    JS_FreeRuntime(r);
    assert(!a.live && !a.bytes);
}
int main(void)
{
    const Case cases[] = {{"ordinary-provided", 0, 0, 0, 0, 0},
                          {"ordinary-missing", 0, 1, 0, 0, 0},
                          {"ordinary-captured-caller-missing", 0, 1, 1, 0, 0},
                          {"forward-provided", 1, 0, 0, 0, 0},
                          {"forward-missing", 1, 1, 0, 0, 0},
                          {"unexecuted-writer", 1, 0, 0, 0, 1},
                          {"async-descendant", 1, 0, 0, 0, 2},
                          {"exact64nodes", 1, 0, 0, 62, 0},
                          {"over64nodes", 1, 0, 0, 63, 0}};
    for (unsigned i = 0; i < sizeof(cases) / sizeof(cases[0]); i++)
        cohort(&cases[i]);
    puts("AARCH64_CAPTURED_READONLY_OK nine-real-graph-and-lifetime-cohorts zero-ledgers");
    return 0;
}
