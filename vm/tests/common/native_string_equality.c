/* Public embedding API: rope/flat equality and conversion redo paths. */
#ifdef NDEBUG
#undef NDEBUG
#endif
#include "quickjs.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

int main(void)
{
    JSRuntime *rt = JS_NewRuntime();
    assert(rt);
    JSContext *ctx = JS_NewContext(rt);
    assert(ctx);
    const char *source = "(()=>{let x='x'.repeat(10000),r=x+'b',f=[x,'b'].join('');"
                         "return [r,f,{[Symbol.toPrimitive](){return f}},"
                         "{[Symbol.toPrimitive](){return r}},"
                         "{[Symbol.toPrimitive](){throw new RangeError('expected')}}]})()";
    JSValue values =
        JS_Eval(ctx, source, strlen(source), "string-equality-host.js", JS_EVAL_TYPE_GLOBAL);
    assert(!JS_IsException(values));
    JSValue rope = JS_GetPropertyUint32(ctx, values, 0);
    JSValue flat = JS_GetPropertyUint32(ctx, values, 1);
    JSValue flat_object = JS_GetPropertyUint32(ctx, values, 2);
    JSValue rope_object = JS_GetPropertyUint32(ctx, values, 3);
    JSValue broken = JS_GetPropertyUint32(ctx, values, 4);
    for (int i = 0; i < 16; ++i) {
        assert(JS_IsEqual(ctx, rope, flat) == 1);
        assert(JS_IsEqual(ctx, flat, rope) == 1);
        assert(JS_IsEqual(ctx, rope, flat_object) == 1);
        assert(JS_IsEqual(ctx, flat_object, rope) == 1);
        assert(JS_IsEqual(ctx, flat, rope_object) == 1);
        assert(JS_IsEqual(ctx, rope_object, flat) == 1);
        assert(JS_IsStrictEqual(ctx, rope, flat));
        assert(JS_IsEqual(ctx, rope, JS_NULL) == 0);
        JS_RunGC(rt);
    }
    assert(JS_IsEqual(ctx, rope, broken) == -1);
    JSValue error = JS_GetException(ctx);
    assert(JS_IsError(error));
    JS_FreeValue(ctx, error);
    assert(JS_IsEqual(ctx, rope, flat) == 1);
    JS_FreeValue(ctx, broken);
    JS_FreeValue(ctx, rope_object);
    JS_FreeValue(ctx, flat_object);
    JS_FreeValue(ctx, flat);
    JS_FreeValue(ctx, rope);
    JS_FreeValue(ctx, values);
    JS_FreeContext(ctx);
    JS_FreeRuntime(rt);
    puts("public flat/rope string equality and conversion ownership passed");
    return 0;
}
