/* Public callers prove actual native indexed paths and their independent controls. */
#ifdef NDEBUG
#undef NDEBUG
#endif
#include "quickjs.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
extern void qjs_aarch64_vm_indexed_counts(uint64_t out[10]);
static JSValue eval(JSContext *c, const char *s)
{
    JSValue v = JS_Eval(c, s, strlen(s), "indexed-paths", 0);
    if (JS_IsException(v)) {
        JSValue e = JS_GetException(c);
        const char *p = JS_ToCString(c, e);
        fprintf(stderr, "indexed paths: %s\n", p ? p : "exception");
        JS_FreeCString(c, p);
        JS_FreeValue(c, e);
        abort();
    }
    return v;
}
static void call(JSContext *c, JSValue f, int argc, JSValue *args, double expected)
{
    JSValue v = JS_Call(c, f, JS_UNDEFINED, argc, args);
    double n = -1;
    if (JS_IsException(v)) {
        JSValue e = JS_GetException(c);
        const char *p = JS_ToCString(c, e);
        fprintf(stderr, "indexed call: %s\n", p ? p : "exception");
        abort();
    }
    assert(!JS_ToFloat64(c, &n, v) && n == expected);
    JS_FreeValue(c, v);
}
int main(void)
{
    setbuf(stdout, NULL);
    JSRuntime *r = JS_NewRuntime();
    assert(r);
    JSContext *c = JS_NewContext(r);
    assert(c);
    JSValue read = eval(c, "(function(a,i){let v=a[i];return v})");
    JSValue method = eval(c, "(function(a,i){let v=a[i]();return v})");
    JSValue write = eval(c, "(function(a,i,v){a[i]=v;return 42})");
    JSValue instance = eval(c, "(function(a,C){let v=a instanceof C;return v?42:0})");
    JSValue dense = eval(c, "[42,0]"), methods = eval(c, "[function(){return 42}]");
    JSValue own =
        eval(c, "(()=>{let a=[0,42];Object.defineProperty(a,'0',{writable:false});return a})()");
    JSValue ownmethods = eval(
        c,
        "(()=>{let a=[0,function(){return 42}];Object.defineProperty(a,'0',{writable:false});return a})()");
    JSValue ta = eval(c, "new Uint32Array([4294967295])");
    JSValue append = eval(c, "(()=>{let a=[];a[0]=0;a.pop();return a})()");
    JSValue ctor = eval(c, "(function C(){})");
    JSValue object = JS_CallConstructor(c, ctor, 0, NULL);
    assert(!JS_IsException(object));
    const struct {
        JSValue f;
        JSValue a, b, d;
        unsigned argc, counter;
        double expected;
    } cases[] = {{read, dense, JS_NewInt32(c, 0), JS_UNDEFINED, 2, 0, 42},
                 {method, methods, JS_NewInt32(c, 0), JS_UNDEFINED, 2, 1, 42},
                 {write, dense, JS_NewInt32(c, 1), JS_NewInt32(c, 42), 3, 2, 42},
                 {read, own, JS_NewInt32(c, 1), JS_UNDEFINED, 2, 3, 42},
                 {method, ownmethods, JS_NewInt32(c, 1), JS_UNDEFINED, 2, 4, 42},
                 {write, own, JS_NewInt32(c, 1), JS_NewInt32(c, 42), 3, 5, 42},
                 {read, ta, JS_NewInt32(c, 0), JS_UNDEFINED, 2, 6, 4294967295.0},
                 {write, ta, JS_NewInt32(c, 0), JS_NewInt32(c, 42), 3, 7, 42},
                 {write, append, JS_NewInt32(c, 0), JS_NewInt32(c, 42), 3, 8, 42},
                 {instance, object, ctor, JS_UNDEFINED, 2, 9, 42}};
    unsigned off = getenv("QJS_DISABLE_INTERP_FRAME") || getenv("QJS_DISABLE_REGISTER_INTERP");
    for (unsigned k = 0; k < sizeof(cases) / sizeof(*cases); k++) {
        JSValue args[] = {cases[k].a, cases[k].b, cases[k].d};
        uint64_t before[10], after[10];
        call(c, cases[k].f, cases[k].argc, args, cases[k].expected);
        if (k == 8)
            assert(JS_SetPropertyStr(c, append, "length", JS_NewInt32(c, 0)) >= 0);
        qjs_aarch64_vm_indexed_counts(before);
        for (unsigned i = 0; i < 128; i++) {
            call(c, cases[k].f, cases[k].argc, args, cases[k].expected);
            if (k == 8)
                assert(JS_SetPropertyStr(c, append, "length", JS_NewInt32(c, 0)) >= 0);
        }
        qjs_aarch64_vm_indexed_counts(after);
        unsigned disabled = off || (k >= 3 && k <= 5 && getenv("QJS_DISABLE_FRAME_INDEXED_OWN")) ||
                            (k == 8 && getenv("QJS_DISABLE_FRAME_ARRAY_APPEND")) ||
                            (k == 9 && (getenv("QJS_DISABLE_FRAME_SLOW_DIRECT") ||
                                        getenv("QJS_DISABLE_FRAME_INSTANCEOF_STEP") ||
                                        getenv("QJS_DISABLE_FRAME_INSTANCEOF_LEAF") ||
                                        getenv("QJS_DISABLE_FRAME_INSTANCEOF") ||
                                        getenv("QJS_OBSERVE_FRAME_INSTANCEOF")));
        uint64_t hits = after[cases[k].counter] - before[cases[k].counter];
        printf("INDEXED_COHORT %u hits=%llu disabled=%u\n", k, (unsigned long long)hits,
               !!disabled);
        assert(hits == (disabled ? 0 : 128));
    }
    JS_FreeValue(c, read);
    JS_FreeValue(c, method);
    JS_FreeValue(c, write);
    JS_FreeValue(c, instance);
    JS_FreeValue(c, dense);
    JS_FreeValue(c, methods);
    JS_FreeValue(c, own);
    JS_FreeValue(c, ownmethods);
    JS_FreeValue(c, ta);
    JS_FreeValue(c, append);
    JS_FreeValue(c, ctor);
    JS_FreeValue(c, object);
    JS_RunGC(r);
    JS_FreeContext(c);
    JS_RunGC(r);
    JS_FreeRuntime(r);
    puts("AARCH64_INDEXED_PATHS_OK");
    return 0;
}
