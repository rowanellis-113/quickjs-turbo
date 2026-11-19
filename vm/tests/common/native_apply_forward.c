#include "quickjs.h"
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

extern _Atomic(uint64_t) JS_FrameApplyForwardStats[14];
#define CHECK(c)                                                                                   \
    do {                                                                                           \
        if (!(c)) {                                                                                \
            fprintf(stderr, "apply host:%d:%s\n", __LINE__, #c);                                   \
            exit(1);                                                                               \
        }                                                                                          \
    } while (0)
static JSValue evaluate(JSContext *ctx, const char *source)
{
    JSValue result =
        JS_Eval(ctx, source, strlen(source), "apply-public-host.js", JS_EVAL_TYPE_GLOBAL);
    if (JS_IsException(result)) {
        JSValue error = JS_GetException(ctx);
        const char *message = JS_ToCString(ctx, error);
        fprintf(stderr, "%s\n", message ? message : "exception");
        JS_FreeCString(ctx, message);
        JS_FreeValue(ctx, error);
        exit(2);
    }
    return result;
}
int main(void)
{
    JSRuntime *rt = JS_NewRuntime();
    CHECK(rt);
    JSContext *ctx = JS_NewContext(rt), *foreign = JS_NewContext(rt);
    CHECK(ctx && foreign);
    JSValue target = evaluate(
        foreign,
        "function Foreign(a,b){return this.base+a+b;} Foreign.call({base:10},1,2);Foreign;");
    JSValue apply = evaluate(foreign, "Function.prototype.apply;");
    JSValue error_ctor = evaluate(foreign, "RangeError;");
    JSValue throwing = evaluate(
        foreign,
        "function ForeignThrow(){throw new RangeError('foreign');}try{ForeignThrow();}catch(e){} ForeignThrow;");
    JSValue global = JS_GetGlobalObject(ctx);
    CHECK(JS_SetPropertyStr(ctx, global, "Foreign", target) >= 0);
    CHECK(JS_SetPropertyStr(ctx, global, "ForeignApply", apply) >= 0);
    CHECK(JS_SetPropertyStr(ctx, global, "ForeignRangeError", error_ctor) >= 0);
    CHECK(JS_SetPropertyStr(ctx, global, "ForeignThrow", throwing) >= 0);
    JS_FreeValue(ctx, global);
    const char *script =
        "'use strict';function check(v){if(!v)throw Error('public apply host');}"
        "const receiver={base:10};function sum(a,b){return this.base+a+b;}sum.call(receiver,1,2);"
        "function invoke(fn,list){const result=fn.apply(receiver,list);return result;}"
        "for(let i=0;i<32;i++)check(invoke(sum,[i,2])===12+i);"
        "for(let i=0;i<16;i++)check(invoke(Foreign,[i,2])===12+i);"
        "sum.apply=ForeignApply;for(let i=0;i<16;i++)check(invoke(sum,[i,2])===12+i);delete sum.apply;"
        "try{invoke(ForeignThrow,[]);check(false);}catch(e){check(Object.getPrototypeOf(e)===ForeignRangeError.prototype);}"
        "check(invoke(sum,[3,4])===17);";
    JSValue result = evaluate(ctx, script);
    JS_FreeValue(ctx, result);
    uint64_t accepted = atomic_load_explicit(&JS_FrameApplyForwardStats[12], memory_order_relaxed);
    uint64_t foreign_misses =
        atomic_load_explicit(&JS_FrameApplyForwardStats[4], memory_order_relaxed);
    uint64_t failed = atomic_load_explicit(&JS_FrameApplyForwardStats[11], memory_order_relaxed);
    int off = getenv("QJS_DISABLE_FRAME_APPLY_DIRECT") != NULL;
    CHECK(!failed);
    CHECK(off ? accepted == 0 : (accepted == 33 && foreign_misses == 33));
    JS_RunGC(rt);
    JS_FreeContext(foreign);
    JS_FreeContext(ctx);
    JS_FreeRuntime(rt);
    printf("APPLY_PUBLIC_HOST_OK admitted=%llu foreign=%llu off=%d\n", (unsigned long long)accepted,
           (unsigned long long)foreign_misses, off);
    return 0;
}
