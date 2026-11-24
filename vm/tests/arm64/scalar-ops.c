#ifdef NDEBUG
#undef NDEBUG
#endif
#include "quickjs.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
extern void qjs_aarch64_vm_scalar_counts(uint64_t[22]);
extern int qjs_aarch64_vm_function_info(JSValueConst, uintptr_t *);
extern size_t qjs_aarch64_vm_function_code(JSValueConst, const uint8_t **);
static const char *names[22] = {"or",
                                "xor",
                                "shl",
                                "sar",
                                "shr",
                                "mod",
                                "inc",
                                "dec",
                                "not",
                                "neg",
                                "post_inc",
                                "post_dec",
                                "swap",
                                "get_loc0_loc1",
                                "push_empty_string",
                                "push_atom_value",
                                "is_undefined",
                                "is_null",
                                "is_undefined_or_null",
                                "to_propkey",
                                "to_propkey2",
                                "check_ctor"};
static JSValue checked(JSContext *c, JSValue v)
{
    if (JS_IsException(v)) {
        JSValue e = JS_GetException(c);
        const char *s = JS_ToCString(c, e);
        fprintf(stderr, "scalar exception:%s\n", s ? s : "oom");
        JS_FreeCString(c, s);
        JS_FreeValue(c, e);
        abort();
    }
    return v;
}
static JSValue eval(JSContext *c, const char *s)
{
    return checked(c, JS_Eval(c, s, strlen(s), "scalar-paths.js", JS_EVAL_TYPE_GLOBAL));
}
static void probe(JSContext *c, unsigned index, const char *source, JSValue args[3], int reset,
                  int expected, const char *text)
{
    JSValue f = eval(c, source), driver = eval(c, "(function(f,a,b,c){return f(a,b,c)})"),
            call_args[4] = {f, args[0], args[1], args[2]};
    uint64_t before[22], after[22];
    qjs_aarch64_vm_scalar_counts(before);
    for (unsigned i = 0; i < 130; i++) {
        if (reset)
            assert(JS_SetPropertyStr(c, args[0], "v", JS_NewInt32(c, 7)) >= 0);
        JSValue out = checked(c, JS_Call(c, driver, JS_UNDEFINED, 4, call_args));
        if (text) {
            const char *s = JS_ToCString(c, out);
            assert(s && !strcmp(s, text));
            JS_FreeCString(c, s);
        } else {
            int32_t n;
            assert(!JS_ToInt32(c, &n, out) && n == expected);
        }
        JS_FreeValue(c, out);
    }
    qjs_aarch64_vm_scalar_counts(after);
    uintptr_t info[6];
    assert(qjs_aarch64_vm_function_info(f, info));
    const uint8_t *code;
    size_t len = qjs_aarch64_vm_function_code(f, &code);
    printf("SCALAR_PATH %s hits=%llu kind=%llu bytes=", names[index],
           (unsigned long long)(after[index] - before[index]), (unsigned long long)info[0]);
    for (size_t i = 0; i < len; i++)
        printf("%02x", code[i]);
    puts("");
    JS_FreeValue(c, driver);
    JS_FreeValue(c, f);
}
int main(void)
{
    JSRuntime *r = JS_NewRuntime();
    assert(r);
    JSContext *c = JS_NewContext(r);
    assert(c);
    JSValue o = JS_NewObject(c),
            args[3] = {JS_NewInt32(c, 5), JS_NewInt32(c, 3), JS_NewInt32(c, 9)};
    probe(c, 0, "(function(a,b){return a|b})", args, 0, 7, NULL);
    probe(c, 1, "(function(a,b){return a^b})", args, 0, 6, NULL);
    probe(c, 2, "(function(a,b){return a<<b})", args, 0, 40, NULL);
    args[0] = JS_NewInt32(c, -8);
    args[1] = JS_NewInt32(c, 2);
    probe(c, 3, "(function(a,b){return a>>b})", args, 0, -2, NULL);
    args[0] = JS_NewInt32(c, 8);
    probe(c, 4, "(function(a,b){return a>>>b})", args, 0, 2, NULL);
    args[0] = JS_NewInt32(c, 17);
    args[1] = JS_NewInt32(c, 5);
    probe(c, 5, "(function(a,b){return a%b})", args, 0, 2, NULL);
    args[0] = o;
    probe(c, 6, "(function(a){return ++a.v})", args, 1, 8, NULL);
    probe(c, 7, "(function(a){return --a.v})", args, 1, 6, NULL);
    args[0] = JS_NewInt32(c, 7);
    probe(c, 8, "(function(a){return ~a})", args, 0, -8, NULL);
    probe(c, 9, "(function(a){return -a})", args, 0, -7, NULL);
    args[0] = o;
    probe(c, 10, "(function(a){return a.v++})", args, 1, 7, NULL);
    probe(c, 11, "(function(a){return a.v--})", args, 1, 7, NULL);
    args[1] = JS_NewString(c, "v");
    probe(c, 12, "(function(a,b,c){a[b]=c;return a[b]})", args, 1, 9, NULL);
    JS_FreeValue(c, args[1]);
    args[1] = JS_UNDEFINED;
    args[1] = o;
    probe(c, 13, "(function(a,b){let x=a,y=b;return x===y})", args, 0, 1, NULL);
    probe(c, 14, "(function(){return ''})", args, 0, 0, "");
    probe(c, 15, "(function(){return 'scalar_value'})", args, 0, 0, "scalar_value");
    probe(c, 16, "(function(a){return a===void 0})", args, 0, 0, NULL);
    probe(c, 17, "(function(a){return a===null})", args, 0, 0, NULL);
    probe(c, 18, "(function(a){return (a??null)===a})", args, 0, 1, NULL);
    args[1] = JS_NewString(c, "v");
    probe(c, 19, "(function(a,b,c){a[b]=c;return a[b]})", args, 1, 9, NULL);
    probe(c, 20, "(function(a,b){return a[b]++})", args, 1, 7, NULL);
    probe(c, 12, "(function(a){let x;[x]=[a];return x.v})", args, 1, 7, NULL);
    probe(c, 19, "(function(a,b){let x;({[b]:x}=a);return x})", args, 1, 7, NULL);
    probe(c, 19, "(function(a,b){return `key:${b}!`})", args, 0, 0, "key:v!");
    JS_FreeValue(c, args[1]);
    args[1] = JS_UNDEFINED;
    JSValue ctor = eval(c, "(class C{constructor(){this.v=9}})");
    args[0] = ctor;
    probe(c, 21, "(function(C){return (new C()).v})", args, 0, 9, NULL);
    JS_FreeValue(c, ctor);
    ctor = eval(c, "(class C{v=9;})");
    args[0] = ctor;
    probe(c, 12, "(function(C){return (new C()).v})", args, 0, 9, NULL);
    JS_FreeValue(c, ctor);
    uint64_t counts[22];
    qjs_aarch64_vm_scalar_counts(counts);
    printf("SCALAR_TOTAL");
    for (unsigned i = 0; i < 22; i++)
        printf(" %llu", (unsigned long long)counts[i]);
    puts("");
    if (getenv("QJS_DISABLE_AARCH64_SCALAR_OPS") || getenv("QJS_DISABLE_REGISTER_INTERP") ||
        getenv("QJS_DISABLE_INTERP_FRAME")) {
        for (unsigned i = 0; i < 22; i++)
            assert(counts[i] == 0);
    } else {
        for (unsigned i = 0; i < 22; i++)
            assert(counts[i] > 0);
    }
    JS_FreeValue(c, o);
    JS_RunGC(r);
    JS_FreeContext(c);
    JS_FreeRuntime(r);
    puts("AARCH64_SCALAR_PATHS_OK");
    return 0;
}
