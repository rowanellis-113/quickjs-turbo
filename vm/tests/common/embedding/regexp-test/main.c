#include "quickjs.h"
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct Host {
    JSClassID cls;
    unsigned born, freed, gc;
} Host;
static void require(int ok, const char *message)
{
    if (!ok) {
        fprintf(stderr, "REGEXP_TEST_C_FAIL %s\n", message);
        exit(40);
    }
}
static Host *host(JSContext *ctx)
{
    return JS_GetRuntimeOpaque(JS_GetRuntime(ctx));
}
static void finalizer(JSRuntime *rt, JSValue value)
{
    Host *s = JS_GetRuntimeOpaque(rt);
    if (JS_GetOpaque(value, s->cls))
        ++s->freed;
}
static JSValue owner(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    Host *s = host(ctx);
    JSValue value = JS_NewObjectClass(ctx, s->cls);
    if (!JS_IsException(value))
        JS_SetOpaque(value, (void *)(uintptr_t)++s->born);
    return value;
}
static JSValue alive(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    Host *s = host(ctx);
    return JS_NewInt32(ctx, (int)(s->born - s->freed));
}
static void eval_ok(JSContext *ctx, const char *text, const char *name)
{
    JSValue result = JS_Eval(ctx, text, strlen(text), name, JS_EVAL_TYPE_GLOBAL);
    if (JS_IsException(result)) {
        JSValue error = JS_GetException(ctx);
        const char *message = JS_ToCString(ctx, error);
        fprintf(stderr, "exception:%s\n", message ? message : "<oom>");
        JS_FreeCString(ctx, message);
        JS_FreeValue(ctx, error);
        require(0, name);
    }
    JS_FreeValue(ctx, result);
}
static JSValue collect(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    ++host(ctx)->gc;
    JS_RunGC(JS_GetRuntime(ctx));
    eval_ok(ctx, "if(!/inner/.test('inner'))throw Error('native reentry');", "regexp_reentry.js");
    return JS_UNDEFINED;
}
static void install(JSContext *ctx, JSValue global, const char *name, JSCFunction *fn)
{
    require(JS_SetPropertyStr(ctx, global, name, JS_NewCFunction(ctx, fn, name, 0)) == 1,
            "install");
}
int main(void)
{
    Host s = {0};
    JSRuntime *rt = JS_NewRuntime();
    require(rt != NULL, "runtime");
    JS_SetRuntimeOpaque(rt, &s);
    JS_NewClassID(rt, &s.cls);
    JSClassDef cls = {0};
    cls.class_name = "RegExpTestOwner";
    cls.finalizer = finalizer;
    require(JS_NewClass(rt, s.cls, &cls) == 0, "class");
    JSContext *ctx = JS_NewContext(rt);
    require(ctx != NULL, "context");
    JSValue global = JS_GetGlobalObject(ctx);
    install(ctx, global, "makeOwner", owner);
    install(ctx, global, "alive", alive);
    install(ctx, global, "hostGC", collect);
    const char *text =
        "function check(ok,msg){if(!ok)throw Error(msg);}"
        "function throwCase(expected,odd){const test=RegExp.prototype.test;"
        "let sentinel=makeOwner(),caught=null;"
        "let throwing=odd?{get exec(){hostGC();throw sentinel;}}:{exec(v){hostGC();check(v===expected,'throw input');throw sentinel;}};"
        "try{test.call(throwing,{toString(){hostGC();return expected;}});}catch(e){caught=e;}"
        "check(caught===sentinel&&alive()===1,'exception identity and owner');"
        "caught=null;sentinel=null;throwing=null;hostGC();"
        "}"
        "function exercise(){const test=RegExp.prototype.test;"
        "for(let i=0;i<32;i++){let order=[],alias=null,r={},retained=null;"
        "const expected=('prefix:'+i+':').repeat(48)+'\\u4e00needle'+('suffix:'+i+':').repeat(48);"
        "Object.defineProperty(r,'exec',{get(){order.push('get');hostGC();return function(v){"
        "order.push('exec');hostGC();check(this===r&&typeof v==='string'&&v===expected,'converted input');"
        "retained=v;if(i&1){alias=makeOwner();return alias;}return makeOwner();};}});"
        "let input={toString(){order.push('string');hostGC();return ('prefix:'+i+':').repeat(48)+'\\u4e00needle'+('suffix:'+i+':').repeat(48);}};"
        "check(test.call(r,input),'result');check(order.join(',')==='string,get,exec','order');"
        "check(alive()===(i&1),'result lastref or alias');alias=null;hostGC();check(alive()===0,'alias release');"
        "check(retained===expected&&retained.includes('needle'),'retained string');retained=null;input=null;r=null;"
        "throwCase(expected,!!(i&1));hostGC();check(alive()===0,'exception lastref after return');"
        "let native=/needle/gy;native.lastIndex={valueOf(){hostGC();return expected.indexOf('needle');}};"
        "check(test.call(native,{toString(){hostGC();return expected;}}),'native result');"
        "check(native.lastIndex===expected.indexOf('needle')+6,'native lastIndex');hostGC();"
        "}check(alive()===0,'all owners');}exercise();";
    eval_ok(ctx, text, "regexp_test_public.js");
    require(s.born == 64 && s.freed == 64 && s.gc >= 288, "owners and explicit GC");

    JSContext *other = JS_NewContext(rt);
    require(other != NULL, "other context");
    JSValue other_global = JS_GetGlobalObject(other);
    JSValue proto = JS_GetPropertyStr(ctx, global, "RegExp");
    JSValue regexp_proto = JS_GetPropertyStr(ctx, proto, "prototype");
    JSValue test = JS_GetPropertyStr(ctx, regexp_proto, "test");
    JSValue type_error = JS_GetPropertyStr(ctx, global, "TypeError");
    require(!JS_IsException(test) && !JS_IsException(type_error), "foreign builtins");
    require(JS_SetPropertyStr(other, other_global, "otherTest", test) == 1, "foreign method");
    require(JS_SetPropertyStr(other, other_global, "OtherTypeError", type_error) == 1,
            "foreign error");
    eval_ok(
        other,
        "function check(ok,msg){if(!ok)throw Error(msg);}"
        "let log=[],caught;try{otherTest.call(3,{toString(){log.push('input');return 'a';}});}catch(e){caught=e;}"
        "check(caught instanceof OtherTypeError&&!(caught instanceof TypeError)&&log.length===0,'receiver error realm');"
        "caught=undefined;try{otherTest.call({},Symbol('s'));}catch(e){caught=e;}"
        "check(caught instanceof OtherTypeError&&!(caught instanceof TypeError),'conversion error realm');"
        "let sentinel={};caught=undefined;try{otherTest.call({exec(){throw sentinel;}},'a');}catch(e){caught=e;}"
        "check(caught===sentinel,'foreign callback exception identity');"
        "let r={},order=[];Object.defineProperty(r,'exec',{get(){order.push('get');return function(s){check(s==='a','foreign input');return {};};}});"
        "check(otherTest.call(r,{toString(){order.push('string');return 'a';}})&&order.join(',')==='string,get','foreign order');",
        "regexp_test_other_realm.js");
    JS_FreeValue(ctx, regexp_proto);
    JS_FreeValue(ctx, proto);
    JS_FreeValue(other, other_global);
    JS_FreeContext(other);
    JS_FreeValue(ctx, global);
    JS_FreeContext(ctx);
    JS_RunGC(rt);
    JS_FreeRuntime(rt);
    require(s.born == 64 && s.freed == 64, "final owner balance");
    printf("REGEXP_TEST_C_OK born=%u finalized=%u gc=%u realms=2\n", s.born, s.freed, s.gc);
    return 0;
}
