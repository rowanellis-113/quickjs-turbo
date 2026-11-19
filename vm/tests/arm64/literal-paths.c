/* Public original callers;real activation-owned/native path observations. */
#ifdef NDEBUG
#undef NDEBUG
#endif
#include "quickjs.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
extern void qjs_aarch64_vm_literal_counts(uint64_t out[34]);
static JSValue eval(JSContext *c, const char *s)
{
    JSValue v = JS_Eval(c, s, strlen(s), "literal-paths", 0);
    if (JS_IsException(v)) {
        JSValue e = JS_GetException(c);
        const char *p = JS_ToCString(c, e);
        fprintf(stderr, "literal paths: %s\n", p ? p : "exception");
        abort();
    }
    return v;
}
static int integer(JSContext *c, JSValue v)
{
    int32_t n;
    assert(!JS_IsException(v) && !JS_ToInt32(c, &n, v));
    JS_FreeValue(c, v);
    return n;
}
int main(void)
{
    setbuf(stdout, NULL);
    JSRuntime *r = JS_NewRuntime();
    assert(r);
    JSContext *c = JS_NewContext(r);
    assert(c);
    JSValue object = JS_NewObject(c), string = JS_NewString(c, "live"),
            number = JS_NewFloat64(c, 1.25);
    JSValue make = eval(c, "(function(i){return {a:i,b:i+1}})");
    JSValue drive = eval(
        c, "(function(f){let sum=0;for(let i=0;i<64;i++){let o=f(i);sum+=o.a+o.b}return sum})");
    JSValue setters = eval(c, "(function(o,v){return o.slot=v})");
    JSValue type = eval(c, "(function(v){return typeof v})");
    JSValue isfunc = eval(c, "(function(v){return typeof v==='function'})");
    JSValue isundef = eval(c, "(function(v){return typeof v==='undefined'})");
    JSValue not = eval(c, "(function(v){return !v})");
    JSValue shortfalse = eval(c, "(function(v){let n=0;if(v)n=1;return n})");
    JSValue shorttrue = eval(c, "(function(v){let n=0;do{if(n)return n;n++;}while(v);return n})");
    JSValue longfalse =
        eval(c, "Function('v','let n=0;if(v){n++;'+('n+=0;'.repeat(150))+'}return n')");
    JSValue longtrue = eval(
        c,
        "Function('v','let n=0;do{if(n)return n;n++;'+('n+=0;'.repeat(150))+'}while(v);return n')");
    JSValue functions[] = {drive, setters,  type,      isfunc,    isundef,
                           not,   longtrue, longfalse, shorttrue, shortfalse};
    unsigned counters[] = {16, 24, 25, 26, 27, 29, 30, 31, 32, 33};
    unsigned off = getenv("QJS_DISABLE_REGISTER_INTERP") || getenv("QJS_DISABLE_INTERP_FRAME");
    for (unsigned k = 0; k < 10; k++) {
        uint64_t a[34], b[34];
        JSValue args[] = {k == 0             ? make
                          : k == 2 || k == 3 ? string
                          : k == 4           ? JS_UNDEFINED
                                             : object,
                          JS_NewInt32(c, 42)};
        unsigned argc = k == 1 ? 2 : 1;
        JSValue warm = JS_Call(c, functions[k], JS_UNDEFINED, argc, args);
        assert(!JS_IsException(warm));
        JS_FreeValue(c, warm);
        qjs_aarch64_vm_literal_counts(a);
        for (unsigned n = 0; n < 128; n++) {
            JSValue v = JS_Call(c, functions[k], JS_UNDEFINED, argc, args);
            if (k == 2) {
                const char *p = JS_ToCString(c, v);
                assert(p && !strcmp(p, "string"));
                JS_FreeCString(c, p);
                JS_FreeValue(c, v);
            } else
                assert(integer(c, v) == (k == 0 ? 4096 : k == 1 ? 42 : k == 3 || k == 5 ? 0 : 1));
        }
        qjs_aarch64_vm_literal_counts(b);
        uint64_t hits = b[counters[k]] - a[counters[k]];
        unsigned disabled = off;
        if (k == 0)
            disabled |= getenv("QJS_DISABLE_FRAME_ORDINARY_LITERAL") ||
                        getenv("QJS_DISABLE_FRAME_ITERATOR_LITERAL_SHAPES") ||
                        getenv("QJS_DISABLE_FRAME_ORDINARY_LITERAL_TRANSITION") ||
                        getenv("QJS_DISABLE_FRAME_ITERATOR_LITERAL_TRANSITION") ||
                        getenv("QJS_DISABLE_FRAME_LITERAL_LAZY") ||
                        getenv("QJS_DISABLE_FRAME_LITERAL_VM_HIT") ||
                        getenv("QJS_ORDINARY_LITERAL_FAIL_CACHE_ALLOC") ||
                        getenv("QJS_LITERAL_LAZY_FAIL_ALLOC");
        if (k == 1)
            disabled |= getenv("QJS_DISABLE_FRAME_STACK_INSERT") != NULL;
        if (k >= 2 && k <= 4)
            disabled |= getenv("QJS_DISABLE_FRAME_TYPEOF") != NULL;
        if (k >= 5)
            disabled |= getenv("QJS_DISABLE_FRAME_TRUTHINESS") != NULL;
        printf("LITERAL_COHORT %u native=%llu disabled=%u\n", k, (unsigned long long)hits,
               !!disabled);
        assert(disabled ? hits == 0 : k == 0 ? hits > 0 : hits == 128);
    }
    /* Original number truth control is independent from heap truth. */
    uint64_t a[34], b[34];
    qjs_aarch64_vm_literal_counts(a);
    for (unsigned i = 0; i < 128; i++)
        assert(integer(c, JS_Call(c, not, JS_UNDEFINED, 1, &number)) == 0);
    qjs_aarch64_vm_literal_counts(b);
    unsigned disabled =
        off || getenv("QJS_DISABLE_FRAME_TRUTHINESS") || getenv("QJS_DISABLE_FRAME_NUMBER_TRUTH");
    printf("LITERAL_NUMBER_TRUTH native=%llu disabled=%u\n", (unsigned long long)(b[29] - a[29]),
           !!disabled);
    assert(b[29] - a[29] == (disabled ? 0 : 128));
    for (unsigned k = 0; k < 10; k++)
        JS_FreeValue(c, functions[k]);
    JS_FreeValue(c, make);
    JS_FreeValue(c, object);
    JS_FreeValue(c, string);
    JS_FreeValue(c, number);
    JS_RunGC(r);
    JS_FreeContext(c);
    JS_RunGC(r);
    JS_FreeRuntime(r);
    puts("AARCH64_LITERAL_PATHS_OK");
    return 0;
}
