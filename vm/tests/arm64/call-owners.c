#ifdef NDEBUG
#undef NDEBUG
#endif
#include "quickjs.h"
#include "src/arm64/linux/interpreter-observe.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static JSClassID token_class;
static unsigned born, finalized, reentered, interrupted;
static JSContext *reentry_ctx;
static JSValue reentry_func;

static void finalizer(JSRuntime *rt, JSValue value)
{
    (void)value;
    (void)rt;
    ++finalized;
    JSValue result = JS_Call(reentry_ctx, reentry_func, JS_UNDEFINED, 0, NULL);
    int32_t number;
    assert(!JS_IsException(result) && JS_ToInt32(reentry_ctx, &number, result) == 0 &&
           number == 47);
    JS_FreeValue(reentry_ctx, result);
    ++reentered;
}
static JSValue make_token(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)self;
    (void)argc;
    (void)argv;
    JS_RunGC(JS_GetRuntime(ctx));
    JSValue value = JS_NewObjectClass(ctx, token_class);
    assert(!JS_IsException(value));
    ++born;
    return value;
}
static void eval(JSContext *ctx, const char *source)
{
    JSValue result = JS_Eval(ctx, source, strlen(source), "<arm-call-owners>", JS_EVAL_TYPE_GLOBAL);
    if (JS_IsException(result)) {
        JSValue error = JS_GetException(ctx);
        const char *text = JS_ToCString(ctx, error);
        fprintf(stderr, "%s\n", text ? text : "<exception>");
        JS_FreeCString(ctx, text);
        JS_FreeValue(ctx, error);
        abort();
    }
    JS_FreeValue(ctx, result);
}
static int interrupt(JSRuntime *rt, void *opaque)
{
    (void)opaque;
    JS_RunGC(rt);
    ++interrupted;
    return interrupted == 3;
}
int main(int argc, char **argv)
{
    assert(argc == 2);
    int native = !strcmp(argv[1], "native");
    JSRuntime *rt = JS_NewRuntime();
    assert(rt);
    JS_SetMaxStackSize(rt, 4 * 1024 * 1024);
    JSContext *ctx = JS_NewContext(rt);
    assert(ctx);
    reentry_ctx = JS_NewContext(rt);
    assert(reentry_ctx);
    JS_NewClassID(rt, &token_class);
    JSClassDef cls = {0};
    cls.class_name = "AArch64CallOwner";
    cls.finalizer = finalizer;
    assert(JS_NewClass(rt, token_class, &cls) == 0);
    const char *nested = "(function(){return 47;})";
    reentry_func =
        JS_Eval(reentry_ctx, nested, strlen(nested), "<foreign-reentry>", JS_EVAL_TYPE_GLOBAL);
    assert(!JS_IsException(reentry_func));
    JSValue global = JS_GetGlobalObject(ctx);
    assert(JS_SetPropertyStr(ctx, global, "makeToken",
                             JS_NewCFunction(ctx, make_token, "makeToken", 0)) == 1);
    JS_FreeValue(ctx, global);
    QJSArmVMCounts before, after;
    qjs_aarch64_vm_counts(&before);
    eval(ctx, "'use strict';"
              "function tail(n){if(n===0)return 37;return tail(n-1);}"
              "function owned(n){let token=makeToken();return tail(n);}"
              "function captured(n){let x=n;let g=()=>x;return tail(g());}"
              "function writable(a){a++;return a;}"
              "function missing(a,b,c){return a+(b===undefined?1:0)+(c===undefined?1:0);}"
              "function extra(a){return a;}"
              "function throwing(){throw Error('expected');}"
              "function check(x,s){if(!x)throw Error(s);}"
              "for(let i=0;i<40;i++){"
              "check(owned(20)===37,'tail-owned');"
              "check(captured(12)===37,'captured tail');"
              "check(writable(5)===6,'writable');"
              "check(missing(7)===9,'missing');"
              "check(extra(7,makeToken(),makeToken())===7,'extra owning args');"
              "let o={base:9,f(a,b,c,d){return this.base+a+b+c+d;}};"
              "check(o.f(1,2,3,4)===19,'wide method');"
              "let same={};function alias(a,b,c){return a;}"
              "check(alias(same,same,same)===same,'alias return');"
              "try{throwing();throw 0;}catch(e){check(e.message==='expected','throw');}"
              "}");
    qjs_aarch64_vm_counts(&after);
    assert(born == 120 && finalized == born && reentered == born);
    if (native) {
        assert(after.native_calls - before.native_calls > 500);
        assert(after.native_returns - before.native_returns > 500);
        assert(after.tail_calls - before.tail_calls > 500);
        assert(after.tail_returns - before.tail_returns > 500);
        assert(after.return_resumes - before.return_resumes > 0);
    } else
        assert(after.native_calls == 0 && after.native_returns == 0);
    JS_SetMaxStackSize(rt, 48 * 1024);
    JSValue result = JS_Eval(ctx, "tail(1000000)", 13, "<quota>", JS_EVAL_TYPE_GLOBAL);
    assert(JS_IsException(result));
    JS_FreeValue(ctx, JS_GetException(ctx));
    JS_SetMaxStackSize(rt, 4 * 1024 * 1024);
    eval(ctx, "if(tail(10)!==37)throw Error('quota recovery');");
    JS_SetInterruptHandler(rt, interrupt, NULL);
    const char *loop = "(function forever(n){for(;;)n=tail(3);})(0)";
    result = JS_Eval(ctx, loop, strlen(loop), "<interrupt>", JS_EVAL_TYPE_GLOBAL);
    assert(JS_IsException(result) && interrupted == 3);
    JS_FreeValue(ctx, JS_GetException(ctx));
    JS_SetInterruptHandler(rt, NULL, NULL);
    eval(ctx, "if(owned(4)!==37)throw Error('interrupt recovery');");
    JS_FreeValue(reentry_ctx, reentry_func);
    JS_FreeContext(reentry_ctx);
    JS_FreeContext(ctx);
    JS_RunGC(rt);
    JS_FreeRuntime(rt);
    assert(finalized == born && reentered == born);
    printf(
        "AARCH64_CALL_OWNERS_OK mode=%s born=%u finalized=%u reentry=%u interrupts=%u calls=%llu returns=%llu tail_calls=%llu tail_returns=%llu resumes=%llu\n",
        argv[1], born, finalized, reentered, interrupted, (unsigned long long)after.native_calls,
        (unsigned long long)after.native_returns, (unsigned long long)after.tail_calls,
        (unsigned long long)after.tail_returns, (unsigned long long)after.return_resumes);
    return 0;
}
