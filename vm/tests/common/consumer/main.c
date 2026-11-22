/* Public API consumer: no engine build tree, private header or PE finalizer. */
#ifdef NDEBUG
#undef NDEBUG
#endif
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "quickjs-turbo.h"
#include "quickjs.h"

static JSValue callback(JSContext *ctx, JSValueConst this_value, int argc, JSValueConst *argv)
{
    assert(argc == 2);
    return JS_Call(ctx, argv[0], JS_UNDEFINED, 1, argv + 1);
}

int main(void)
{
    QJSTurboOptions turbo_opts;
    QJS_TurboOptionsInit(&turbo_opts);
    turbo_opts.own_bytecode_tail = QJS_TURBO_OFF;
    turbo_opts.property_ic_warmup = 4;
    assert(QJS_SetTurboDefaults(&turbo_opts) == 0);

    JSRuntime *runtime = JS_NewRuntime();
    assert(runtime);
    QJSTurboInfo turbo_info;
    assert(QJS_GetTurboInfo(runtime, &turbo_info) == 0);
    assert(turbo_info.backend_name != NULL && turbo_info.backend_name[0] != '\0');
    JSContext *context = JS_NewContext(runtime);
    assert(context);
    JSValue global = JS_GetGlobalObject(context);
    assert(JS_SetPropertyStr(context, global, "relay",
                             JS_NewCFunction(context, callback, "relay", 2)) >= 0);
    const char *source = "(function(a){let b=relay(x=>x+1,a);try{throw b+1}catch(e){return e}})";
    JSValue function = JS_Eval(context, source, strlen(source), "consumer.js", JS_EVAL_TYPE_GLOBAL);
    assert(!JS_IsException(function));
    for (int i = 0; i < 300; i++) {
        JSValue argument = JS_NewInt32(context, i);
        JSValue result = JS_Call(context, function, JS_UNDEFINED, 1, &argument);
        int32_t value = 0;
        assert(!JS_IsException(result));
        assert(JS_ToInt32(context, &value, result) == 0 && value == i + 2);
        JS_FreeValue(context, result);
        JS_FreeValue(context, argument);
    }
    JS_FreeValue(context, function);
    JS_FreeValue(context, global);
    (void)JS_PurgePropertyIC(runtime);
    JS_FreeContext(context);
    JS_FreeRuntime(runtime);
    puts("INSTALLED_CONSUMER_PASS: JS -> C -> JS, closure and exception returns");
    return 0;
}
