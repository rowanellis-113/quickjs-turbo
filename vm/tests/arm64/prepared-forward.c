/* Public prepared-descriptor cohorts; private data type is extracted verbatim. */
#ifdef NDEBUG
#undef NDEBUG
#endif
#include <quickjs.h>
#include <assert.h>
#include <inttypes.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "tests/common/native_oom_allocator.h"
#include "aarch64-prepared-data.h"
extern JSFramePrepareData JS_FrameCallPrepareData;
extern void qjs_aarch64_vm_forward_counts(uint64_t words[16]);
typedef struct {
    const char *name, *target;
    unsigned depth, actual;
    int result, closure, native_own, oversized;
} Case;
static JSValue eval(JSContext *c, const char *s)
{
    JSValue v = JS_Eval(c, s, strlen(s), "prepared-forward", JS_EVAL_TYPE_GLOBAL);
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
static void check(JSContext *c, JSValue v, JSValueConst seed, const Case *k)
{
    assert(!JS_IsException(v));
    if (k->closure) {
        JSValue n = JS_Call(c, v, JS_UNDEFINED, 0, NULL);
        JS_FreeValue(c, v);
        v = n;
        assert(!JS_IsException(v));
    }
    if (k->result == 0)
        assert(JS_IsSameValue(c, v, seed));
    else if (k->result == 1)
        assert(JS_IsUndefined(v));
    else if (k->result == 2)
        assert(JS_IsNull(v));
    else if (k->result == 3)
        assert(JS_IsBool(v) && JS_ToBool(c, v));
    else if (k->result == 4)
        assert(JS_IsBool(v) && !JS_ToBool(c, v));
    else {
        double n;
        assert(!JS_ToFloat64(c, &n, v));
        assert(n == (k->result == 5   ? 7
                     : k->result == 6 ? 43
                     : k->result == 7 ? 84
                                      : 2147483648.0));
    }
    JS_FreeValue(c, v);
}
static void cohort(const Case *k, unsigned cross)
{
    Allocator a = {0};
    JSRuntime *r = JS_NewRuntime2(&functions, &a);
    assert(r);
    JSContext *c = JS_NewContext(r), *other = JS_NewContext(r);
    assert(c && other);
    JS_SetMaxStackSize(r, 4 * 1024 * 1024);
    JSContext *owner = cross ? other : c;
    JSValue fn = eval(owner, k->target), wrapper = eval(owner, "Function.prototype.call");
    JSValue seed =
        k->result >= 6 ? JS_NewInt32(c, k->result == 8 ? 2147483647 : 42) : JS_NewObject(c);
    if (JS_IsObject(seed))
        assert(JS_SetPropertyStr(c, seed, "cycle", JS_DupValue(c, seed)) >= 0);
    JSValue receiver = JS_NewObject(c);
    assert(!JS_IsException(seed) && !JS_IsException(receiver));
    char code[8192];
    size_t n = (size_t)snprintf(code, sizeof(code), "(function(f,r,v,c){");
    if (k->depth == 64 && !k->oversized) {
        /* Ordinary source-level wide caller grows its arena naturally to16KiB.
    * Thin64 retains the original4KiB capacity miss as a separate cohort.
    */
        JSValue reserve = eval(c, "globalThis.forwardReserve=function(){return 0}");
        JS_FreeValue(c, reserve);
        n += (size_t)snprintf(code + n, sizeof(code) - n, "forwardReserve(");
        for (unsigned i = 0; i < 300; i++)
            n += (size_t)snprintf(code + n, sizeof(code) - n, "%sv", i ? "," : "");
        n += (size_t)snprintf(code + n, sizeof(code) - n, ");");
    }
    n += (size_t)snprintf(code + n, sizeof(code) - n, "return ");
    if (k->depth == 1)
        n += (size_t)snprintf(code + n, sizeof(code) - n, "f.call(");
    else {
        n += (size_t)snprintf(code + n, sizeof(code) - n, "c.call(");
        for (unsigned i = 0; i < k->depth - 2; i++)
            n += (size_t)snprintf(code + n, sizeof(code) - n, "c,");
        n += (size_t)snprintf(code + n, sizeof(code) - n, "f,");
    }
    n += (size_t)snprintf(code + n, sizeof(code) - n, "r");
    for (unsigned i = 0; i < k->actual; i++)
        n += (size_t)snprintf(code + n, sizeof(code) - n, ",v");
    n += (size_t)snprintf(code + n, sizeof(code) - n, ")})");
    assert(n < sizeof(code));
    JSValue driver = eval(c, code);
    JSValue args[4] = {fn, receiver, seed, wrapper};
    for (unsigned i = 0; i < 4; i++)
        check(c, JS_Call(c, driver, JS_UNDEFINED, 4, args), seed, k);
    uint64_t before[16], after[16];
    qjs_aarch64_vm_forward_counts(before);
    uint64_t leaves = __atomic_load_n(&JS_FrameCallPrepareData.leaf_hits, __ATOMIC_RELAXED),
             entries = __atomic_load_n(&JS_FrameCallPrepareData.prepared_entries, __ATOMIC_RELAXED);
    uint64_t depth = __atomic_load_n(&JS_FrameCallPrepareData.depths[k->depth <= 64 ? k->depth : 0],
                                     __ATOMIC_RELAXED),
             owns = __atomic_load_n(&JS_FrameCallPrepareData.depths[0], __ATOMIC_RELAXED);
    for (unsigned i = 0; i < 32; i++)
        check(c, JS_Call(c, driver, JS_UNDEFINED, 4, args), seed, k);
    qjs_aarch64_vm_forward_counts(after);
    uint64_t d[16];
    for (unsigned i = 0; i < 16; i++)
        d[i] = after[i] - before[i];
    leaves = __atomic_load_n(&JS_FrameCallPrepareData.leaf_hits, __ATOMIC_RELAXED) - leaves;
    entries =
        __atomic_load_n(&JS_FrameCallPrepareData.prepared_entries, __ATOMIC_RELAXED) - entries;
    depth = __atomic_load_n(&JS_FrameCallPrepareData.depths[k->depth <= 64 ? k->depth : 0],
                            __ATOMIC_RELAXED) -
            depth;
    owns = __atomic_load_n(&JS_FrameCallPrepareData.depths[0], __ATOMIC_RELAXED) - owns;
    printf("PREPARED_PATH %s depth=%u cross=%u C=%" PRIu64 " leaf=%" PRIu64 " preparedC=%" PRIu64
           " owned=%" PRIu64 " observed=%" PRIu64 ",%" PRIu64 ",%" PRIu64 ",%" PRIu64 "\n",
           k->name, k->depth, cross, d[0], d[8], d[9], d[10], leaves, entries, depth, owns);
    fflush(stdout);
    int outer = !disabled("QJS_DISABLE_FRAME_CALL_FORWARD") &&
                !disabled("QJS_DISABLE_FRAME_CALL_FORWARD_NATIVE") &&
                !disabled("QJS_DISABLE_FRAME_CALL_PREPARE") &&
                !disabled("QJS_DISABLE_REGISTER_INTERP") && !disabled("QJS_DISABLE_INTERP_FRAME");
    int active = outer && !k->oversized;
    if (active) {
        int own = k->native_own || disabled("QJS_DISABLE_FRAME_CALL_FORWARD_LEAF");
        if (!own) {
            assert(d[8] == 32 && !d[9] && !d[10] && !d[0]);
        } else if (disabled("QJS_DISABLE_FRAME_CALL_PREPARE_OWNED")) {
            assert(d[9] == 32 && !d[8] && !d[10] && !d[0]);
        } else
            assert(d[10] == 32 && !d[8] && !d[9] && !d[0]);
        if (disabled("QJS_OBSERVE_FRAME_CALL_PREPARE")) {
            assert(depth == 32);
            assert(leaves == (own ? 0 : 32));
            assert(entries == (own ? 32 : 0));
            assert(owns == (own && !disabled("QJS_DISABLE_FRAME_CALL_PREPARE_OWNED") ? 32 : 0));
        } else
            assert(!leaves && !entries && !depth && !owns);
    } else if (outer && k->oversized == 2) {
        assert(!d[8] && !d[10]);
        if (disabled("QJS_DISABLE_FRAME_CALL_FORWARD_LEAF"))
            assert(d[9] == 32 && !d[0]);
        else
            assert(d[0] == 32 && !d[9]);
    } else
        assert(!d[8] && !d[9] && !d[10]);
    JS_FreeValue(c, driver);
    JS_FreeValue(owner, fn);
    JS_FreeValue(owner, wrapper);
    JS_FreeValue(c, seed);
    JS_FreeValue(c, receiver);
    JS_RunGC(r);
    JS_FreeContext(other);
    JS_FreeContext(c);
    JS_FreeRuntime(r);
    assert(!a.live && !a.bytes);
}
int main(void)
{
    const Case cases[] = {
        {"one-heap", "(function(a){return a})", 1, 1, 0, 0, 0, 0},
        {"deep-heap", "(function(a){return a})", 8, 1, 0, 0, 0, 0},
        {"last-argument", "(function(a,b,c,d){return d})", 3, 4, 0, 0, 0, 0},
        {"missing-argument", "(function(a,b,c,d){return d})", 64, 0, 1, 0, 0, 0},
        {"constant", "(function(){return 7})", 64, 0, 5, 0, 0, 0},
        {"return-undef", "(function(){return})", 2, 0, 1, 0, 0, 0},
        {"null", "(function(){return null})", 3, 0, 2, 0, 0, 0},
        {"true", "(function(){return true})", 8, 0, 3, 0, 0, 0},
        {"false", "(function(){return false})", 2, 0, 4, 0, 0, 0},
        {"add-small", "(function(a){return a+1})", 8, 1, 6, 0, 0, 0},
        {"add-argument", "(function(a,b){return a+b})", 3, 2, 7, 0, 0, 0},
        {"overflow-owned", "(function(a){return a+1})", 8, 1, 8, 0, 1, 0},
        {"mutable-owned", "(function(a){let keep=a;a=undefined;return keep})", 8, 1, 0, 0, 1, 0},
        {"captured-owned", "(function(a){let held=()=>a;return held})", 8, 1, 0, 1, 1, 0},
        {"captured-max-depth", "(function(a){let held=()=>a;return held})", 64, 1, 0, 1, 1, 0},
        {"over-depth-C", "(function(a){return a})", 65, 1, 0, 0, 0, 1},
        {"thin-max-depth-capacity-C", "(function(){return 7})", 64, 0, 5, 0, 0, 2}};
    for (unsigned i = 0; i < sizeof(cases) / sizeof(cases[0]); i++)
        for (unsigned cross = 0; cross < 2; cross++)
            cohort(&cases[i], cross);
    puts("AARCH64_PREPARED_PATHS_OK 34-fresh-runtime-cohorts zero-ledgers");
    return 0;
}
