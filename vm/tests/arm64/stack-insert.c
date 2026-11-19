/* Native insert3 ownership and process-control observations via public calls. */
#ifdef NDEBUG
#undef NDEBUG
#endif
#include "quickjs.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
extern uint64_t qjs_aarch64_vm_stack_insert_count(void);
static JSValue eval(JSContext *c, const char *s)
{
    JSValue v = JS_Eval(c, s, strlen(s), "stack-paths", 0);
    if (JS_IsException(v)) {
        JSValue e = JS_GetException(c);
        const char *p = JS_ToCString(c, e);
        fprintf(stderr, "%s\n", p ? p : "exception");
        abort();
    }
    return v;
}
static void call(JSContext *c, JSValue f, JSValue *args)
{
    JSValue v = JS_Call(c, f, JS_UNDEFINED, 3, args);
    assert(!JS_IsException(v));
    assert(JS_VALUE_GET_TAG(v) == JS_VALUE_GET_TAG(args[2]));
    if (JS_IsObject(v))
        assert(JS_VALUE_GET_PTR(v) == JS_VALUE_GET_PTR(args[2]));
    else {
        int32_t n = 0;
        assert(!JS_ToInt32(c, &n, v) && n == 42);
    }
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
    JSValue f = eval(c, "globalThis.insPut=(function(a,k,v){return a[k]=v});insPut;");
    JSValue driver = eval(c, "(function(a,k,v){return insPut(a,k,v)})");
    JSValue args[] = {JS_NewArray(c), JS_NewInt32(c, 0), JS_NewInt32(c, 42)};
    unsigned off = getenv("QJS_DISABLE_FRAME_STACK_INSERT") ||
                   getenv("QJS_DISABLE_REGISTER_INTERP") || getenv("QJS_DISABLE_INTERP_FRAME");
    for (unsigned kind = 0; kind < 2; kind++) {
        if (kind)
            args[2] = JS_NewObject(c);
        call(c, f, args);
        uint64_t before = qjs_aarch64_vm_stack_insert_count();
        for (unsigned i = 0; i < 128; i++)
            call(c, f, args);
        uint64_t hits = qjs_aarch64_vm_stack_insert_count() - before;
        printf("INSERT3 kind=%u native=%llu\n", kind, (unsigned long long)hits);
        assert(hits == (off ? 0 : 128));
    }
    call(c, driver, args);
    uint64_t before = qjs_aarch64_vm_stack_insert_count();
    for (unsigned i = 0; i < 128; i++)
        call(c, driver, args);
    uint64_t hits = qjs_aarch64_vm_stack_insert_count() - before;
    printf("INSERT3 native_child=%llu\n", (unsigned long long)hits);
    assert(hits == (off ? 0 : 128));
    JS_FreeValue(c, args[2]);
    JS_FreeValue(c, args[0]);
    JS_FreeValue(c, f);
    JS_FreeValue(c, driver);
    JS_RunGC(r);
    JS_FreeContext(c);
    JS_FreeRuntime(r);
    puts("AARCH64_STACK_INSERT_PATHS_OK");
    return 0;
}
