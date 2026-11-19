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
        fprintf(stderr, "SPARSE_LENGTH_C_FAIL %s\n", message);
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
    JSValue v = JS_NewObjectClass(ctx, s->cls);
    if (!JS_IsException(v))
        JS_SetOpaque(v, (void *)(uintptr_t)++s->born);
    return v;
}
static JSValue alive(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    Host *s = host(ctx);
    return JS_NewInt32(ctx, (int)(s->born - s->freed));
}
static JSValue is_owner(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    return JS_NewBool(ctx, argc == 1 && JS_GetOpaque(argv[0], host(ctx)->cls) != NULL);
}
static JSValue collect(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    ++host(ctx)->gc;
    JS_RunGC(JS_GetRuntime(ctx));
    const char *text = "21*2";
    JSValue v = JS_Eval(ctx, text, strlen(text), "length_reentry.js", JS_EVAL_TYPE_GLOBAL);
    int32_t number = 0;
    require(!JS_IsException(v) && JS_ToInt32(ctx, &number, v) == 0 && number == 42, "C reentry");
    JS_FreeValue(ctx, v);
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
    cls.class_name = "SparseLengthOwner";
    cls.finalizer = finalizer;
    require(JS_NewClass(rt, s.cls, &cls) == 0, "class");
    JSContext *ctx = JS_NewContext(rt);
    require(ctx != NULL, "context");
    JSValue global = JS_GetGlobalObject(ctx);
    install(ctx, global, "makeOwner", owner);
    install(ctx, global, "alive", alive);
    install(ctx, global, "isOwner", is_owner);
    install(ctx, global, "hostGC", collect);
    const char *text =
        "function check(ok,msg){if(!ok)throw Error(msg);}"
        "function sparse(){let a=[];for(let k=48;k<58;k++)a[k]=k;for(let k=65;k<91;k++)a[k]=k;for(let k=97;k<123;k++)a[k]=k;return a;}"
        "function highGone(a,start){for(let k=start;k<126;k++)check(!Object.hasOwn(a,k),'retained high key');}"
        "function exercise(){"
        "for(let i=0;i<16;i++){let a=sparse(),saved=null,alias=null;"
        "if(i&1){saved=makeOwner();a[122]=saved;alias=saved;}else a[122]=makeOwner();"
        "let target={valueOf(){hostGC();a[125]=125;return 54;}};"
        "if(i%3===0)a.length=target;else if(i%3===1)check(Reflect.set(a,'length',target),'Reflect.set');else Object.defineProperty(a,'length',{value:target,writable:!!(i&1)});"
        "check(a.length===54,'length');highGone(a,54);"
        "if(i&1){check(isOwner(alias)&&alive()===1,'alias lost');saved=null;alias=null;}"
        "check(alive()===0,'last owner retained');a=null;hostGC();}"
        "for(let mode=0;mode<2;mode++){let a=sparse();a[122]=makeOwner();Object.defineProperty(a,'66',{configurable:false});"
        "if(mode===0)check(!Reflect.set(a,'length',54),'nonconfig set');else{let threw=false;try{Object.defineProperty(a,'length',{value:54,writable:false});}catch(e){threw=e instanceof TypeError;}check(threw,'nonconfig define');check(!Object.getOwnPropertyDescriptor(a,'length').writable,'writable rollback');}"
        "check(a.length===67&&a[66]===66,'nonconfig boundary');highGone(a,67);check(alive()===0,'nonconfig last owner');a=null;hostGC();}"
        "let a=sparse();a[122]=makeOwner();let caught=false;try{a.length={valueOf(){hostGC();throw Error('coercion');}};}catch(e){caught=e.message==='coercion';}"
        "check(caught&&a.length===123&&isOwner(a[122])&&alive()===1,'coercion rollback');a=null;hostGC();check(alive()===0,'coercion last owner');}"
        "exercise();";
    JSValue result =
        JS_Eval(ctx, text, strlen(text), "sparse_length_public.js", JS_EVAL_TYPE_GLOBAL);
    if (JS_IsException(result)) {
        JSValue e = JS_GetException(ctx);
        const char *message = JS_ToCString(ctx, e);
        fprintf(stderr, "exception:%s\n", message ? message : "<oom>");
        JS_FreeCString(ctx, message);
        JS_FreeValue(ctx, e);
        require(0, "eval");
    }
    JS_FreeValue(ctx, result);
    JS_FreeValue(ctx, global);
    JS_FreeContext(ctx);
    JS_RunGC(rt);
    JS_FreeRuntime(rt);
    require(s.born == 19 && s.freed == 19 && s.gc >= 35, "owner and GC balance");
    printf("SPARSE_LENGTH_C_OK born=%u finalized=%u gc=%u\n", s.born, s.freed, s.gc);
    return 0;
}
