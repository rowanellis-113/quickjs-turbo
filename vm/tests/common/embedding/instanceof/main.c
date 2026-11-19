#include "quickjs.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static unsigned checks;
static void require(int ok, const char *message)
{
    if (!ok) {
        fprintf(stderr, "PUBLIC_INSTANCEOF_FAILURE %s\n", message);
        exit(20);
    }
}
static JSValue evaluate(JSContext *ctx, const char *s)
{
    JSValue v = JS_Eval(ctx, s, strlen(s), "public-instanceof.js", JS_EVAL_TYPE_GLOBAL);
    require(!JS_IsException(v), "setup eval");
    return v;
}
static void exception_realm(JSContext *ctx, JSValueConst expected)
{
    JSValue error = JS_GetException(ctx), proto = JS_GetPrototype(ctx, error);
    require(JS_IsObject(proto) && JS_IsObject(expected) &&
                JS_VALUE_GET_PTR(proto) == JS_VALUE_GET_PTR(expected),
            "TypeError realm");
    JS_FreeValue(ctx, proto);
    JS_FreeValue(ctx, error);
}
static void exercise(JSContext *ctx, JSValueConst entry, JSValueConst value, JSValueConst ctor,
                     int expected, JSValueConst error_proto)
{
    int original = JS_IsInstanceOf(ctx, value, ctor);
    require(original == expected, "original API result");
    if (original < 0)
        exception_realm(ctx, error_proto);
    JSValueConst args[2] = {value, ctor};
    for (int i = 0; i < 64; i++) {
        JSValue v = JS_Call(ctx, entry, JS_UNDEFINED, 2, args);
        int actual = JS_IsException(v) ? -1 : JS_ToBool(ctx, v);
        require(actual == original, "nested native/ordinary result");
        if (actual < 0)
            exception_realm(ctx, error_proto);
        JS_FreeValue(ctx, v);
        checks++;
    }
}
static void both(JSContext *a, JSContext *b, JSValueConst ea, JSValueConst eb, JSValueConst v,
                 JSValueConst f, int expected, JSValueConst error_proto)
{
    exercise(a, ea, v, f, expected, error_proto);
    exercise(b, eb, v, f, expected, error_proto);
}
int main(void)
{
    JSRuntime *rt = JS_NewRuntime();
    require(rt != NULL, "runtime");
    JS_SetMaxStackSize(rt, 2 * 1024 * 1024);
    JSContext *a = JS_NewContext(rt), *b = JS_NewContext(rt);
    require(a && b, "contexts");
    const char *entry =
        "(function(){function check(v,c){return v instanceof c;}return function entry(v,c){return check(v,c);};})()";
    JSValue ea = evaluate(a, entry), eb = evaluate(b, entry), f = evaluate(a, "(function F(){})");
    JSValue proto = JS_GetPropertyStr(a, f, "prototype");
    require(JS_IsObject(proto), "function prototype");
    JSValue yes = JS_NewObjectProto(b, proto), no = JS_NewObject(b), primitive = JS_NewInt32(b, 7);
    JSValue error_a = evaluate(a, "TypeError.prototype"),
            error_b = evaluate(b, "TypeError.prototype");
    JSValue method_b = evaluate(b, "Function.prototype[Symbol.hasInstance]");
    JSValue symbol = evaluate(b, "Symbol.hasInstance");
    JSAtom atom = JS_ValueToAtom(b, symbol);
    JS_FreeValue(b, symbol);
    require(atom != JS_ATOM_NULL, "symbol atom");
    both(a, b, ea, eb, yes, f, 1, JS_UNDEFINED);
    both(a, b, ea, eb, no, f, 0, JS_UNDEFINED);
    both(a, b, ea, eb, primitive, f, 0, JS_UNDEFINED);
    require(JS_SetPropertyStr(a, f, "prototype", JS_NewInt32(a, 3)) >= 0, "invalid prototype A");
    both(a, b, ea, eb, yes, f, -1, error_a);
    both(a, b, ea, eb, primitive, f, 0, JS_UNDEFINED);
    require(JS_SetPropertyStr(a, f, "prototype", JS_DupValue(a, proto)) >= 0,
            "restore prototype A");
    require(JS_DefinePropertyValue(a, f, atom, JS_DupValue(a, method_b), JS_PROP_C_W_E) >= 0,
            "foreign default method");
    both(a, b, ea, eb, yes, f, 1, JS_UNDEFINED);
    both(a, b, ea, eb, no, f, 0, JS_UNDEFINED);
    both(a, b, ea, eb, primitive, f, 0, JS_UNDEFINED);
    require(JS_SetPropertyStr(a, f, "prototype", JS_NewInt32(a, 3)) >= 0, "invalid prototype B");
    both(a, b, ea, eb, yes, f, -1, error_b);
    both(a, b, ea, eb, primitive, f, 0, JS_UNDEFINED);
    JSValue getter_b = evaluate(b, "(function(){throw new TypeError('foreign getter');})");
    require(JS_DefinePropertyGetSet(a, f, atom, getter_b, JS_UNDEFINED, JS_PROP_CONFIGURABLE) >= 0,
            "foreign getter");
    both(a, b, ea, eb, yes, f, -1, error_b);
    both(a, b, ea, eb, primitive, f, -1, error_b);
    require(JS_DefinePropertyValue(a, f, atom, JS_DupValue(a, method_b), JS_PROP_C_W_E) >= 0,
            "restore foreign method");
    require(JS_SetPropertyStr(a, f, "prototype", JS_DupValue(a, proto)) >= 0,
            "restore prototype B");
    JS_FreeContext(a);
    a = NULL;
    JS_RunGC(rt);
    exercise(b, eb, yes, f, 1, JS_UNDEFINED);
    exercise(b, eb, no, f, 0, JS_UNDEFINED);
    exercise(b, eb, primitive, f, 0, JS_UNDEFINED);
    JS_FreeAtom(b, atom);
    JS_FreeValue(b, ea);
    JS_FreeValue(b, eb);
    JS_FreeValue(b, f);
    JS_FreeValue(b, yes);
    JS_FreeValue(b, no);
    JS_FreeValue(b, primitive);
    JS_FreeValue(b, proto);
    JS_FreeValue(b, method_b);
    JS_FreeValue(b, error_a);
    JS_FreeValue(b, error_b);
    JS_RunGC(rt);
    JS_FreeContext(b);
    JS_FreeRuntime(rt);
    require(checks == 1728, "complete cases");
    printf("PUBLIC_INSTANCEOF_OK checks=%u\n", checks);
    return 0;
}
