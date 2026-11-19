/* Public calls plus passive publication counters and natural VM unwind. MIT. */
#ifdef NDEBUG
#undef NDEBUG
#endif
#include "quickjs.h"
#include "src/arm64/linux/interpreter-observe.h"
#include <assert.h>
#include <execinfo.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
struct JSFrameRegisterState;
extern int JS_FrameInterp(struct JSFrameRegisterState *);
extern unsigned char qjs_aarch64_vm_end[];
extern void qjs_aarch64_vm_quota(JSRuntime *, uintptr_t *);
extern const int32_t qjs_aarch64_publish_original[256];
extern const int32_t qjs_aarch64_publish_clean[256];
extern const int32_t qjs_aarch64_publish_dirty[256];
static JSContext *foreign;
static JSValue nested;
static unsigned callbacks, unwinds, inside;
static JSValue eval(JSContext *ctx, const char *text)
{
    JSValue v = JS_Eval(ctx, text, strlen(text), "publication-arm", JS_EVAL_TYPE_GLOBAL);
    if (JS_IsException(v)) {
        JSValue error = JS_GetException(ctx);
        const char *s = JS_ToCString(ctx, error);
        fprintf(stderr, "PUBLICATION_ERROR %s\n", s ? s : "unknown");
        abort();
    }
    return v;
}
static void number(JSContext *ctx, JSValue value, int expected)
{
    int32_t n = 0;
    assert(!JS_IsException(value) && !JS_ToInt32(ctx, &n, value) && n == expected);
    JS_FreeValue(ctx, value);
}
static JSValue inspect(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)self;
    assert(argc == 1);
    int32_t n = 0;
    assert(!JS_ToInt32(ctx, &n, argv[0]));
    uint64_t counts[16];
    qjs_aarch64_vm_publication_counts(counts);
    assert(!counts[6]);
    void *frames[64];
    int total = backtrace(frames, 64), vm = 0;
    for (int i = 0; i < total; i++) {
        uintptr_t ip = (uintptr_t)frames[i];
        vm += ip > (uintptr_t)JS_FrameInterp && ip < (uintptr_t)qjs_aarch64_vm_end;
    }
    if (vm)
        ++unwinds;
    JS_RunGC(JS_GetRuntime(ctx));
    if (!inside) {
        inside = 1;
        number(foreign, JS_Call(foreign, nested, JS_UNDEFINED, 1, argv), n + 17);
        inside = 0;
    }
    ++callbacks;
    return JS_NewInt32(ctx, n + 7);
}
static JSValue inspect_data(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv,
                            int magic, JSValue *data)
{
    (void)data;
    assert(magic == 0);
    return inspect(ctx, self, argc, argv);
}
static JSValue make(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)self;
    (void)argv;
    assert(argc == 0);
    return JS_NewObject(ctx);
}
static JSValue throw_host(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)self;
    (void)argc;
    (void)argv;
    return JS_ThrowTypeError(ctx, "publication retained host exception");
}
static void tables(void)
{
    const int32_t *all[] = {qjs_aarch64_publish_original, qjs_aarch64_publish_clean,
                            qjs_aarch64_publish_dirty};
    unsigned changed = 0;
    for (unsigned i = 0; i < 256; i++) {
        for (unsigned t = 0; t < 3; t++) {
            uintptr_t target = (uintptr_t)all[t] + all[t][i];
            assert(!(target & 3) && target >= (uintptr_t)JS_FrameInterp &&
                   target < (uintptr_t)qjs_aarch64_vm_end);
        }
        changed += (uintptr_t)all[0] + all[0][i] != (uintptr_t)all[1] + all[1][i];
    }
    assert(changed == 10);
}
int main(int argc, char **argv)
{
    assert(argc == 2);
    unsigned enabled = !strcmp(argv[1], "native");
    unsigned legacy = !strcmp(argv[1], "legacy") || !strcmp(argv[1], "register-off");
    tables();
    JSRuntime *rt = JS_NewRuntime();
    assert(rt);
    JS_SetMaxStackSize(rt, 4 * 1024 * 1024);
    JSContext *ctx = JS_NewContext(rt);
    foreign = JS_NewContext(rt);
    assert(ctx && foreign);
    nested = eval(foreign, "(function(v){let out=v+17;return out})");
    JSValue funcs = eval(
        ctx,
        "[function(v){let out=v+1;return out},function(v){v=v+2;return v},function(f,v){let out=f(v);return out}]");
    JSValue a = JS_GetPropertyUint32(ctx, funcs, 0), b = JS_GetPropertyUint32(ctx, funcs, 1),
            t = JS_GetPropertyUint32(ctx, funcs, 2);
    JSValue probe = JS_NewCFunction(ctx, inspect, "publicationInspect", 1);
    JSValue pipe = eval(ctx, "(function(f,a,b,t,n){let x=a(n);let y=b(x);let z=t(f,y);return z})");
    JSValue recurse = eval(
        ctx,
        "(function(self,f,n){if(n>0){let x=self(self,f,n-1);return x+1}let out=f(n);return out})");
    for (unsigned i = 0; i < 64; i++) {
        uintptr_t before[2], after[2];
        qjs_aarch64_vm_quota(rt, before);
        JSValue args[] = {probe, a, b, t, JS_NewInt32(ctx, i)};
        number(ctx, JS_Call(ctx, pipe, JS_UNDEFINED, 5, args), (int)i + 10);
        JSValue deep[] = {recurse, probe, JS_NewInt32(ctx, 24)};
        number(ctx, JS_Call(ctx, recurse, JS_UNDEFINED, 3, deep), 31);
        qjs_aarch64_vm_quota(rt, after);
        assert(!memcmp(before, after, sizeof(before)));
    }
    JSValue with_regexp =
        eval(ctx, "(function(f,a){let n=a(1);let r=/x+/;let out=f(n);return out})");
    JSValue regexp_args[] = {probe, a};
    number(ctx, JS_Call(ctx, with_regexp, JS_UNDEFINED, 2, regexp_args), 9);
    JSValue data = JS_NewCFunctionData(ctx, inspect_data, 1, 0, 0, NULL);
    JSValue typed = eval(ctx, "(function(f,a){let n=a(1);let out=f(n);return out})");
    JSValue typed_args[] = {data, a};
    number(ctx, JS_Call(ctx, typed, JS_UNDEFINED, 2, typed_args), 9);
    JSValue tail = eval(ctx, "(function(self,n){if(n===0)return 37;return self(self,n-1)})");
    JSValue tail_args[] = {tail, JS_NewInt32(ctx, 8)};
    for (unsigned i = 0; i < 3; i++)
        number(ctx, JS_Call(ctx, tail, JS_UNDEFINED, 2, tail_args), 37);
    JSValue tail_owner = eval(ctx, "(function(make,f,n){let token=make();return f(f,n)})");
    JSValue maker = JS_NewCFunction(ctx, make, "makePublicationOwner", 0);
    JSValue owner_args[] = {maker, tail, JS_NewInt32(ctx, 8)};
    uintptr_t quota_before[2], quota_after[2];
    qjs_aarch64_vm_quota(rt, quota_before);
    number(ctx, JS_Call(ctx, tail_owner, JS_UNDEFINED, 3, owner_args), 37);
    qjs_aarch64_vm_quota(rt, quota_after);
    assert(!memcmp(quota_before, quota_after, sizeof(quota_before)));
    /* Single-pass returns consume the former last-owner decline in assembly.
     * A live captured local must still use the exact consumed-tail C owner,
     * close its reference before frame storage is released, and retain the
     * escaped closure across active GC. Keep every original counter assertion. */
    JSValue captured_tail =
        eval(ctx, "(function(make,f,n){let token=make();token.marker=37;"
                  "globalThis.publicationCaptured=function(){return token.marker};"
                  "return f(f,n)})");
    qjs_aarch64_vm_quota(rt, quota_before);
    number(ctx, JS_Call(ctx, captured_tail, JS_UNDEFINED, 3, owner_args), 37);
    qjs_aarch64_vm_quota(rt, quota_after);
    assert(!memcmp(quota_before, quota_after, sizeof(quota_before)));
    JS_RunGC(rt);
    number(ctx, eval(ctx, "publicationCaptured()"), 37);
    JS_FreeValue(ctx, eval(ctx, "delete globalThis.publicationCaptured"));
    JS_FreeValue(ctx, captured_tail);
    // The exception route must still cover the original C finish boundary
    // after successful ordinary host returns move to the native consumer.
    JSValue throwing = JS_NewCFunction(ctx, throw_host, "throwPublicationHost", 1);
    JSValue throw_args[] = {throwing, a};
    JSValue failed = JS_Call(ctx, typed, JS_UNDEFINED, 2, throw_args);
    assert(JS_IsException(failed));
    JS_FreeValue(ctx, JS_GetException(ctx));
    JS_FreeValue(ctx, throwing);
    uint64_t counts[16];
    qjs_aarch64_vm_publication_counts(counts);
    assert(!counts[6] && callbacks == 130);
    for (unsigned i = 0; i < 16; i++)
        fprintf(stderr, "publication[%u]=%llu%c", i, (unsigned long long)counts[i],
                i == 15 ? '\n' : ' ');
    if (enabled) {
        assert(counts[0] && counts[1] && counts[2] && counts[3] && counts[4] && counts[5]);
        assert(counts[7] && counts[8] && counts[9]);
        for (unsigned i = 10; i < 16; i++)
            assert(counts[i]);
        assert(unwinds == callbacks);
    } else
        for (unsigned i = 0; i < 16; i++)
            assert(!counts[i]);
    if (legacy)
        assert(!unwinds);
    printf(
        "AARCH64_PUBLICATION_OK calls=%u unwind=%u push=%llu owned=%llu pop=%llu known=%llu dirtyC=%llu stalePush=%llu stalePop=%llu bad=%llu\n",
        callbacks, unwinds, (unsigned long long)counts[0], (unsigned long long)counts[1],
        (unsigned long long)counts[2], (unsigned long long)counts[3], (unsigned long long)counts[5],
        (unsigned long long)counts[7], (unsigned long long)counts[8],
        (unsigned long long)counts[6]);
    JS_FreeValue(ctx, maker);
    JS_FreeValue(ctx, tail_owner);
    JS_FreeValue(ctx, tail);
    JS_FreeValue(ctx, typed);
    JS_FreeValue(ctx, data);
    JS_FreeValue(ctx, with_regexp);
    JS_FreeValue(ctx, recurse);
    JS_FreeValue(ctx, pipe);
    JS_FreeValue(ctx, probe);
    JS_FreeValue(ctx, a);
    JS_FreeValue(ctx, b);
    JS_FreeValue(ctx, t);
    JS_FreeValue(ctx, funcs);
    JS_FreeValue(foreign, nested);
    JS_FreeContext(foreign);
    JS_FreeContext(ctx);
    JS_FreeRuntime(rt);
    return 0;
}
