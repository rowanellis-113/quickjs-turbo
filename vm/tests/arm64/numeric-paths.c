/* Original public callers and actual AAPCS64 numeric/FD path observations. */
#ifdef NDEBUG
#undef NDEBUG
#endif
#include "quickjs.h"
#include "dtoa.h"
#include <assert.h>
#include <fenv.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
extern void qjs_aarch64_vm_numeric_counts(uint64_t out[12]);
extern void JS_FrameBigIntRelease(JSContext *, JSValue);
extern double JS_FrameAtod(const char *, const char **, int, int, JSATODTempMem *);
static unsigned finalized;
static void final(JSRuntime *r, JSValue v)
{
    (void)r;
    (void)v;
    finalized++;
}
static JSValue eval(JSContext *c, const char *s)
{
    JSValue v = JS_Eval(c, s, strlen(s), "numeric-paths", 0);
    if (JS_IsException(v)) {
        JSValue e = JS_GetException(c);
        const char *p = JS_ToCString(c, e);
        fprintf(stderr, "numeric paths:%s\n", p ? p : "exception");
        abort();
    }
    return v;
}
static void check(JSContext *c, JSValue v, const char *expected)
{
    assert(!JS_IsException(v));
    const char *p = JS_ToCString(c, v);
    assert(p && !strcmp(p, expected));
    JS_FreeCString(c, p);
    JS_FreeValue(c, v);
}
int main(void)
{
    setbuf(stdout, NULL);
    JSRuntime *r = JS_NewRuntime();
    assert(r);
    JSContext *c = JS_NewContext(r);
    assert(c);
    JSValue large = JS_NewBigInt64(c, INT64_C(1099511627776));
    assert(JS_VALUE_GET_TAG(large) == JS_TAG_BIG_INT);
    JS_FrameBigIntRelease(c, JS_DupValue(c, large));
    uint64_t a[12], b[12];
    unsigned releaseoff = getenv("QJS_DISABLE_BIGINT_RELEASE") != NULL;
    qjs_aarch64_vm_numeric_counts(a);
    for (unsigned i = 0; i < 128; i++)
        JS_FrameBigIntRelease(c, JS_DupValue(c, large));
    qjs_aarch64_vm_numeric_counts(b);
    printf("NUMERIC_RELEASE_NONLAST native=%llu\n", (unsigned long long)(b[0] - a[0]));
    assert(b[0] - a[0] == (releaseoff ? 0 : 128));
    qjs_aarch64_vm_numeric_counts(a);
    for (unsigned i = 0; i < 128; i++)
        JS_FrameBigIntRelease(c, JS_NewBigInt64(c, INT64_C(1099511627776)));
    qjs_aarch64_vm_numeric_counts(b);
    printf("NUMERIC_RELEASE_LAST native=%llu\n", (unsigned long long)(b[1] - a[1]));
    assert(b[1] - a[1] == (releaseoff ? 0 : 128));
    JSClassID klass = 0;
    JS_NewClassID(r, &klass);
    JSClassDef def = {0};
    def.class_name = "NumericGenericFinal";
    def.finalizer = final;
    assert(!JS_NewClass(r, klass, &def));
    qjs_aarch64_vm_numeric_counts(a);
    for (unsigned i = 0; i < 128; i++)
        JS_FrameBigIntRelease(c, JS_NewObjectClass(c, klass));
    qjs_aarch64_vm_numeric_counts(b);
    assert(b[2] - a[2] == 128 && finalized == 128);
    JSValue local = eval(c, "(function(a,b,n){let v=a;for(let i=0;i<n;i++)v+=b;return v})");
    JSValue add = eval(c, "(function(a,b){let v=a+b;return v})"),
            mul = eval(c, "(function(a,b){let v=a*b;return v})");
    JSValue small = JS_NewBigInt64(c, 1), three = JS_NewBigInt64(c, 3);
    assert(JS_VALUE_GET_TAG(small) == JS_TAG_SHORT_BIG_INT);
    unsigned off = getenv("QJS_DISABLE_REGISTER_INTERP") || getenv("QJS_DISABLE_INTERP_FRAME"),
             localoff = off || getenv("QJS_DISABLE_NATIVE_ADD_LOCAL");
    JSValue shortargs[] = {small, small, JS_NewInt32(c, 8)};
    check(c, JS_Call(c, local, JS_UNDEFINED, 3, shortargs), "9");
    qjs_aarch64_vm_numeric_counts(a);
    for (unsigned i = 0; i < 128; i++)
        check(c, JS_Call(c, local, JS_UNDEFINED, 3, shortargs), "9");
    qjs_aarch64_vm_numeric_counts(b);
    printf("NUMERIC_SHORT_LOCAL native=%llu C=%llu\n", (unsigned long long)(b[4] - a[4]),
           (unsigned long long)(b[5] - a[5]));
    assert(b[4] - a[4] == (localoff ? 0 : 1024));
    JSValue longargs[] = {large, three, JS_NewInt32(c, 1)};
    check(c, JS_Call(c, local, JS_UNDEFINED, 3, longargs), "1099511627779");
    qjs_aarch64_vm_numeric_counts(a);
    for (unsigned i = 0; i < 128; i++)
        check(c, JS_Call(c, local, JS_UNDEFINED, 3, longargs), "1099511627779");
    qjs_aarch64_vm_numeric_counts(b);
    printf("NUMERIC_HEAP_LOCAL C=%llu\n", (unsigned long long)(b[5] - a[5]));
    assert(b[5] - a[5] == (localoff ? 0 : 128));
    JSValue args[] = {large, three};
    for (unsigned k = 0; k < 2; k++) {
        JSValue f = k ? mul : add;
        const char *expected = k ? "3298534883328" : "1099511627779";
        check(c, JS_Call(c, f, JS_UNDEFINED, 2, args), expected);
        qjs_aarch64_vm_numeric_counts(a);
        for (unsigned i = 0; i < 128; i++)
            check(c, JS_Call(c, f, JS_UNDEFINED, 2, args), expected);
        qjs_aarch64_vm_numeric_counts(b);
        printf("NUMERIC_PRIMITIVE %u C=%llu\n", k, (unsigned long long)(b[6 + k] - a[6 + k]));
        assert(b[6 + k] - a[6 + k] == (off ? 0 : 128));
    }
    int original = fegetround();
    assert(!fesetround(FE_TONEAREST));
    qjs_aarch64_vm_numeric_counts(a);
    for (unsigned i = 0; i < 128; i++) {
        JSATODTempMem m;
        const char *next = NULL;
        assert(JS_FrameAtod("12.125", &next, 10, 0, &m) == 12.125 && *next == 0);
    }
    qjs_aarch64_vm_numeric_counts(b);
    assert(b[8] - a[8] == 128 && b[9] == a[9]);
    const int modes[] = {FE_UPWARD, FE_DOWNWARD, FE_TOWARDZERO};
    qjs_aarch64_vm_numeric_counts(a);
    for (unsigned k = 0; k < 3; k++) {
        assert(!fesetround(modes[k]));
        for (unsigned i = 0; i < 128; i++) {
            JSATODTempMem m;
            const char *next = NULL;
            assert(JS_FrameAtod("12.125", &next, 10, 0, &m) == 12.125 && *next == 0);
        }
    }
    assert(!fesetround(original));
    qjs_aarch64_vm_numeric_counts(b);
    printf("NUMERIC_ROUNDING fast=128 nonnearest=%llu\n", (unsigned long long)(b[9] - a[9]));
    assert(b[8] == a[8] && b[9] - a[9] == 384);
    qjs_aarch64_vm_numeric_counts(a);
    JSValue proof = eval(c, "(function(n){let a=n+1;let b=a*2;return a+b})");
    qjs_aarch64_vm_numeric_counts(b);
    printf("NUMERIC_COMPILER projection=%llu planner=%llu\n", (unsigned long long)(b[10] - a[10]),
           (unsigned long long)(b[11] - a[11]));
#ifdef QJS_TEST_COMPILER_PROJECTION
    assert(b[10] > a[10] && b[11] > a[11]);
#else
    assert(b[10] == a[10] && b[11] == a[11]);
#endif
    JS_FreeValue(c, proof);
    JS_FreeValue(c, local);
    JS_FreeValue(c, add);
    JS_FreeValue(c, mul);
    JS_FreeValue(c, large);
    JS_FreeValue(c, small);
    JS_FreeValue(c, three);
    JS_RunGC(r);
    JS_FreeContext(c);
    JS_RunGC(r);
    JS_FreeRuntime(r);
    puts("AARCH64_NUMERIC_PATHS_OK");
    return 0;
}
