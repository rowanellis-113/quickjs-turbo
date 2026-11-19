/* Dormant view overwritten by eleven undefined arguments,then reused. MIT. */
#ifdef NDEBUG
#undef NDEBUG
#endif
#include "quickjs.h"
#include "src/arm64/linux/interpreter-observe.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
extern int JS_LinuxBuiltinProbe(JSRuntime *, uintptr_t *);
extern void qjs_aarch64_vm_quota(JSRuntime *, uintptr_t *);
static unsigned observations, views;
static uintptr_t first_view, first_frame, first_bytes;
static int enabled;
static JSValue stringify(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)self;
    (void)argc;
    (void)argv;
    uintptr_t words[7];
    int found = JS_LinuxBuiltinProbe(JS_GetRuntime(ctx), words);
    ++observations;
    assert(found == enabled);
    if (found) {
        ++views;
        assert(words[1] == words[2]);
        if (!(observations & 1)) {
            if (words[0] == 1)
                assert(words[5] == first_view && words[6] == first_frame &&
                       words[3] >= first_bytes);
        } else {
            first_view = words[5];
            first_frame = words[6];
            first_bytes = words[3];
        }
    }
    JS_RunGC(JS_GetRuntime(ctx));
    return JS_NewString(ctx, "abcdef");
}
static JSValue eval(JSContext *ctx, const char *text)
{
    JSValue v = JS_Eval(ctx, text, strlen(text), "dormant-builtin-window", JS_EVAL_TYPE_GLOBAL);
    if (JS_IsException(v)) {
        JSValue e = JS_GetException(ctx);
        const char *s = JS_ToCString(ctx, e);
        fprintf(stderr, "C_WINDOW_ERROR %s\n", s ? s : "unknown");
        abort();
    }
    return v;
}
int main(void)
{
    enabled = !getenv("QJS_DISABLE_C_INVOKE") && !getenv("QJS_DISABLE_NATIVE_SLICE") &&
              !getenv("QJS_DISABLE_REGISTER_INTERP") && !getenv("QJS_DISABLE_INTERP_FRAME");
    JSRuntime *rt = JS_NewRuntime();
    assert(rt);
    JS_SetMaxStackSize(rt, 4 * 1024 * 1024);
    JSContext *ctx = JS_NewContext(rt);
    assert(ctx);
    JSValue missing = eval(ctx, "(function(a,b,c,d,e,f,g,h,i,j,k){return k})");
    JSValue result = JS_Call(ctx, missing, JS_UNDEFINED, 0, NULL);
    assert(JS_IsUndefined(result));
    JS_FreeValue(ctx, result);
    JSValue receiver = JS_NewObject(ctx), slice = eval(ctx, "String.prototype.slice");
    assert(!JS_IsException(receiver) && !JS_IsException(slice));
    assert(JS_SetPropertyStr(ctx, receiver, "slice", slice) > 0);
    assert(JS_SetPropertyStr(ctx, receiver, "toString",
                             JS_NewCFunction(ctx, stringify, "viewStringify", 0)) > 0);
    JSValue actor =
        eval(ctx, "(function(s,f){let a=s.slice(1,4);let n=f();let b=s.slice(2,5);return a+b+n})");
    JSValue args[] = {receiver, missing};
    QJSArmVMCounts before, after;
    qjs_aarch64_vm_counts(&before);
    for (unsigned i = 0; i < 64; i++) {
        uintptr_t quota[2], restored[2];
        qjs_aarch64_vm_quota(rt, quota);
        result = JS_Call(ctx, actor, JS_UNDEFINED, 2, args);
        assert(!JS_IsException(result));
        const char *text = JS_ToCString(ctx, result);
        assert(text && !strcmp(text, "bcdcdeundefined"));
        JS_FreeCString(ctx, text);
        JS_FreeValue(ctx, result);
        qjs_aarch64_vm_quota(rt, restored);
        assert(!memcmp(quota, restored, sizeof(quota)));
    }
    qjs_aarch64_vm_counts(&after);
    assert(observations == 128 && views == (enabled ? 128u : 0u));
    if (!getenv("QJS_DISABLE_REGISTER_INTERP") && !getenv("QJS_DISABLE_INTERP_FRAME")) {
        assert(after.native_calls - before.native_calls >= 64);
        assert(after.last_window_flags & 1);
    }
    uint64_t entries[8];
    qjs_aarch64_vm_c_entry_counts(entries);
    printf(
        "AARCH64_C_WINDOW_OK observations=%u views=%u missing_calls=%llu flags=%llu hot=%llu quota_restored=64\n",
        observations, views, (unsigned long long)(after.native_calls - before.native_calls),
        (unsigned long long)after.last_window_flags, (unsigned long long)entries[6]);
    JS_FreeValue(ctx, actor);
    JS_FreeValue(ctx, receiver);
    JS_FreeValue(ctx, missing);
    JS_FreeContext(ctx);
    JS_FreeRuntime(rt);
    return 0;
}
