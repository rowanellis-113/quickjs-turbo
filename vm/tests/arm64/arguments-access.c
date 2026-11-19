/* Natural argument access paths and public semantic boundaries. MIT. */
#ifdef NDEBUG
#undef NDEBUG
#endif
#include "quickjs.h"
#include <assert.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
extern _Atomic uint64_t JS_FrameArgumentsAccessStats[4];
static JSValue eval(JSContext *c, const char *s)
{
    JSValue v = JS_Eval(c, s, strlen(s), "arguments-access", 0);
    if (JS_IsException(v)) {
        JSValue e = JS_GetException(c);
        const char *p = JS_ToCString(c, e);
        fprintf(stderr, "arguments access: %s\n", p ? p : "exception");
        JS_FreeCString(c, p);
        JS_FreeValue(c, e);
        abort();
    }
    return v;
}
int main(void)
{
    setbuf(stdout, NULL);
    JSRuntime *r = JS_NewRuntime();
    assert(r);
    JSContext *c = JS_NewContext(r);
    assert(c);
    const char *body[2][4] = {
        {"(function(a){'use strict';return arguments[0]})",
         "(function(a){'use strict';return arguments[0]()})",
         "(function(a){'use strict';arguments[0]=42;return arguments[0]})",
         "(function(a){'use strict';return arguments.length})"},
        {"(function(a){return arguments[0]})", "(function(a){return arguments[0]()})",
         "(function(a){arguments[0]=42;return a})", "(function(a){return arguments.length})"}};
    unsigned no_vm = getenv("QJS_DISABLE_FRAME_ARGUMENTS") || getenv("QJS_DISABLE_REGISTER_INTERP");
    for (unsigned mapped = 0; mapped < 2; mapped++)
        for (unsigned k = 0; k < 4; k++) {
            JSValue f = eval(c, body[mapped][k]);
            JSValue arg = k == 1 ? eval(c, "(function(){return this.length+41})")
                                 : JS_NewInt32(c, k == 0 ? 42 : 41);
            JSValue v = JS_Call(c, f, JS_UNDEFINED, 1, &arg);
            assert(!JS_IsException(v));
            JS_FreeValue(c, v);
            uint64_t before = atomic_load(&JS_FrameArgumentsAccessStats[k]);
            for (unsigned i = 0; i < 128; i++) {
                v = JS_Call(c, f, JS_UNDEFINED, 1, &arg);
                int32_t n = -1;
                assert(!JS_IsException(v) && !JS_ToInt32(c, &n, v) && n == (k == 3 ? 1 : 42));
                JS_FreeValue(c, v);
            }
            uint64_t hits = atomic_load(&JS_FrameArgumentsAccessStats[k]) - before;
            unsigned disabled = no_vm || getenv("QJS_DISABLE_FRAME_ARGUMENTS_ACCESS") ||
                                (k == 3 ? (getenv("QJS_DISABLE_FRAME_ARGUMENTS_LENGTH") ||
                                           getenv("QJS_DISABLE_NATIVE_LENGTH"))
                                        : getenv("QJS_DISABLE_FRAME_ARGUMENTS_INDEX") != NULL);
            printf("ACCESS_COHORT mapped=%u op=%u hits=%llu disabled=%u\n", mapped, k,
                   (unsigned long long)hits, disabled);
            assert(disabled ? hits == 0 : hits >= 128);
            JS_FreeValue(c, arg);
            JS_FreeValue(c, f);
        }
    JSValue v = eval(
        c,
        "(function(){function ck(x){if(!x)throw Error('access semantics')}"
        "function mapped(a){let p=arguments;ck(p[0]===a);a={v:42};ck(p[0]===a);p[0]=p;ck(a===p);p[0]=42;return a}ck(mapped({})===42);"
        "function escaped(a){let p=arguments;return [p,()=>a,v=>a=v]}let t=escaped({v:1});let z={v:42};t[2](z);ck(t[0][0]===z);t[0][0]=t;ck(t[1]()===t);t[0][0]=42;ck(t[1]()===42);"
        "function strict(a){'use strict';let p=arguments;p[0]=p;ck(a.v===1&&p[0]===p);p[0]={v:42};return p[0].v}ck(strict({v:1})===42);"
        "function changed(a){let p=arguments;delete p[0];let n=0;Object.defineProperty(p,'0',{get(){n++;return 41},set(v){n+=v},configurable:true});ck(p[0]===41);p[0]=1;ck(n===2&&a===7);delete p.length;p.extra=4;p.length=42;ck(p.length===42);Object.defineProperty(p,'length',{get(){return 43}});ck(p.length===43);return true}ck(changed(7));"
        "function edge(a){let p=arguments;ck(p[-1]===undefined&&p[999]===undefined&&p['x']===undefined);p[-1]=1;p[999]=2;ck(p[-1]+p[999]===3);return p}ck(edge(42)[0]===42);"
        "function readonly(a){let p=arguments;Object.defineProperty(p,'0',{writable:false});p[0]=9;ck(p[0]===a);Object.defineProperty(p,'length',{value:{v:42}});return p.length.v}ck(readonly(7)===42);"
        "function single(a){return arguments}ck(single({v:42})[0].v===42);"
        "function empty(){return arguments.length}ck(empty()===0);return 42})()");
    int32_t n;
    assert(!JS_ToInt32(c, &n, v) && n == 42);
    JS_FreeValue(c, v);
    JS_RunGC(r);
    JS_FreeContext(c);
    JS_RunGC(r);
    JS_FreeRuntime(r);
    puts("AARCH64_ARGUMENTS_ACCESS_OK");
    return 0;
}
