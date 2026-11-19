/* Read actual materialized intrinsic identities after normal public calls. MIT. */
#ifdef NDEBUG
#undef NDEBUG
#endif
#include "quickjs.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
extern unsigned qjs_aarch64_regexp_worker_kind(JSValueConst, unsigned *);
int main(void)
{
    JSRuntime *rt = JS_NewRuntime();
    assert(rt);
    JSContext *ctx = JS_NewContext(rt);
    assert(ctx);
    const char *code =
        "(function(){const p=RegExp.prototype,r=/a/g;"
        "if('aba'.replace(r,x=>x.toUpperCase())!=='AbA')throw Error('replace');"
        "if(r[Symbol.match]('aba').length!==2)throw Error('match');r.lastIndex=0;"
        "if(Array.from(r[Symbol.matchAll]('aba')).length!==2)throw Error('matchAll');"
        "if('xay'.split(r).join(',')!=='x,y')throw Error('split');"
        "if(r.flags!=='g')throw Error('flags');r.lastIndex=0;r.exec('aba');r.test('aba');"
        "return [p[Symbol.replace],p[Symbol.match],p[Symbol.matchAll],p[Symbol.split],"
        "Object.getOwnPropertyDescriptor(p,'flags').get,p.exec,p.test];})()";
    JSValue values = JS_Eval(ctx, code, strlen(code), "regexp-native-routing", JS_EVAL_TYPE_GLOBAL);
    assert(!JS_IsException(values));
    unsigned expected_mode = getenv("QJS_DISABLE_LINUX_REGEXP_WORKERS") ? 2 : 1;
    if (getenv("QJS_DISABLE_LINUX_REGEXP_OWNED_ARGV"))
        expected_mode |= 4;
    unsigned combined = 0;
    for (unsigned i = 0; i < 7; ++i) {
        JSValue fn = JS_GetPropertyUint32(ctx, values, i);
        unsigned mode = 0;
        unsigned kind = qjs_aarch64_regexp_worker_kind(fn, &mode);
        assert(kind == (1u << i) && mode == expected_mode);
        combined |= kind;
        JS_FreeValue(ctx, fn);
    }
    JS_FreeValue(ctx, values);
    JS_RunGC(rt);
    JS_FreeContext(ctx);
    JS_FreeRuntime(rt);
    printf("AARCH64_REGEXP_ROUTING_OK intrinsic_mask=%u mode=%u original_exec_test=96\n", combined,
           expected_mode);
    return 0;
}
