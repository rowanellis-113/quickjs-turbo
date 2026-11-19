/* Real source callers and passive native/C string path counters. MIT. */
#ifdef NDEBUG
#undef NDEBUG
#endif
#include "quickjs.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
extern void qjs_aarch64_vm_string_counts(uint64_t out[8]);
static JSValue eval(JSContext *c, const char *s)
{
    JSValue v = JS_Eval(c, s, strlen(s), "string-paths", 0);
    if (JS_IsException(v)) {
        JSValue e = JS_GetException(c);
        const char *p = JS_ToCString(c, e);
        fprintf(stderr, "%s\n", p ? p : "exception");
        abort();
    }
    return v;
}
static void call(JSContext *c, JSValue f, int argc, JSValue *args, const char *expected)
{
    JSValue v = JS_Call(c, f, JS_UNDEFINED, argc, args);
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
    JS_SetMaxStackSize(r, 2 * 1024 * 1024);
    JSValue read = eval(c, "(function(a,i){let v=a[i];return v})");
    JSValue local = eval(c, "(function(a,b){let v=a;for(let i=0;i<8;i++)v+=b;return v})");
    JSValue add = eval(c, "(function(a,b){let v=a+b;return v})");
    JSValue append = eval(
        c,
        "(function(a,b,n){let s=a;let len=0;for(let i=0;i<n;i++)len=(s=s+b).length;return len})");
    JSValue args[] = {JS_NewString(c, "abc"), JS_NewInt32(c, 1)};
    uint64_t before[8], after[8];
    unsigned off = getenv("QJS_DISABLE_REGISTER_INTERP") || getenv("QJS_DISABLE_INTERP_FRAME"),
             indexoff = off || getenv("QJS_DISABLE_FRAME_STRING_INDEX");
#ifndef QJS_TEST_NATIVE_STRING_INDEX
    indexoff = 1;
#endif
    call(c, read, 2, args, "b");
    qjs_aarch64_vm_string_counts(before);
    for (unsigned i = 0; i < 128; i++)
        call(c, read, 2, args, "b");
    qjs_aarch64_vm_string_counts(after);
    printf("STRING_INDEX native=%llu C=%llu\n", (unsigned long long)(after[0] - before[0]),
           (unsigned long long)(after[3] - before[3]));
    assert(after[0] - before[0] == (indexoff ? 0 : 128));
    JS_FreeValue(c, args[0]);
    args[0] = JS_NewString(c, "a");
    args[1] = JS_NewString(c, "b");
    for (unsigned k = 0; k < 2; k++) {
        const char *expected = k ? "ab" : "abbbbbbbb";
        JSValue f = k ? add : local;
        call(c, f, 2, args, expected);
        qjs_aarch64_vm_string_counts(before);
        for (unsigned i = 0; i < 128; i++)
            call(c, f, 2, args, expected);
        qjs_aarch64_vm_string_counts(after);
        printf("STRING_%s native_entry=%llu C=%llu\n", k ? "ADD" : "LOCAL",
               (unsigned long long)(after[1 + k] - before[1 + k]),
               (unsigned long long)(after[4 + k] - before[4 + k]));
        assert(after[1 + k] - before[1 + k] == (off ? 0 : k ? 128 : 1024));
    }
    JSValue longargs[] = {eval(c, "'x'.repeat(640)"), args[1], JS_NewInt32(c, 1024)};
    call(c, append, 3, longargs, "1664");
    qjs_aarch64_vm_string_counts(before);
    for (unsigned i = 0; i < 4; i++)
        call(c, append, 3, longargs, "1664");
    qjs_aarch64_vm_string_counts(after);
    printf("STRING_APPEND native=%llu C=%llu\n", (unsigned long long)(after[7] - before[7]),
           (unsigned long long)(after[5] - before[5]));
    unsigned appendoff =
        off || getenv("QJS_DISABLE_CONCAT_ROPE") || getenv("QJS_DISABLE_NATIVE_ADD_BOUNDARY") ||
        getenv("QJS_DISABLE_LOCAL_ROPE_APPEND") || getenv("QJS_DISABLE_LOCAL_ROPE_SPARE") ||
        getenv("QJS_DISABLE_FRAME_NATIVE_ROPE_APPEND");
    if (appendoff)
        assert(after[7] == before[7]);
    else
        assert(after[7] > before[7]);
    JS_FreeValue(c, longargs[0]);
    JS_FreeValue(c, args[0]);
    JS_FreeValue(c, args[1]);
    JS_FreeValue(c, read);
    JS_FreeValue(c, local);
    JS_FreeValue(c, add);
    JS_FreeValue(c, append);
    JS_RunGC(r);
    JS_FreeContext(c);
    JS_FreeRuntime(r);
    puts("AARCH64_STRING_PATHS_OK");
    return 0;
}
