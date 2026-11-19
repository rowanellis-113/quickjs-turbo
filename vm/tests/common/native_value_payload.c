/* The host includes the unchanged public header; the engine uses its overlay. */
#include "quickjs.h"
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define CHECK(x)                                                                                   \
    do {                                                                                           \
        if (!(x)) {                                                                                \
            fprintf(stderr, "VALUE_PAYLOAD line %d: %s\n", __LINE__, #x);                          \
            exit(1);                                                                               \
        }                                                                                          \
    } while (0)

static JSValue evaluate(JSContext *ctx, const char *source)
{
    JSValue v = JS_Eval(ctx, source, strlen(source), "value-payload", JS_EVAL_TYPE_GLOBAL);
    CHECK(!JS_IsException(v));
    return v;
}

int main(void)
{
    JSRuntime *rt = JS_NewRuntime();
    CHECK(rt);
    JSContext *ctx = JS_NewContext(rt);
    CHECK(ctx);
    JSValue function = evaluate(ctx, "(x=>x+0.5)");
    const int32_t values[] = {INT32_MIN, -1, 0, 1, INT32_MAX};
    for (unsigned i = 0; i < sizeof(values) / sizeof(values[0]); i++) {
        JSValue arg = JS_NewInt32(ctx, values[i]);
#ifndef JS_NAN_BOXING
        /* The former public ABI leaves this word unspecified. It must not
           change the integer received by code compiled with the new header. */
        uint64_t raw = UINT64_C(0x7654321000000000) | (uint32_t)values[i];
        memcpy(&arg.u, &raw, sizeof(raw));
#endif
        JSValue result = JS_Call(ctx, function, JS_UNDEFINED, 1, &arg);
        double actual;
        CHECK(!JS_IsException(result));
        CHECK(JS_ToFloat64(ctx, &actual, result) == 0 && actual == (double)values[i] + 0.5);
        JS_FreeValue(ctx, result);
    }
    JS_FreeValue(ctx, function);
    function = evaluate(ctx, "(x=>x?17:19)");
    for (int i = 0; i < 2; i++) {
        JSValue arg = JS_NewBool(ctx, i);
#ifndef JS_NAN_BOXING
        uint64_t raw = UINT64_C(0x7654321000000000) | (uint32_t)i;
        memcpy(&arg.u, &raw, sizeof(raw));
#endif
        JSValue result = JS_Call(ctx, function, JS_UNDEFINED, 1, &arg);
        int32_t actual;
        CHECK(!JS_IsException(result));
        CHECK(JS_ToInt32(ctx, &actual, result) == 0 && actual == (i ? 17 : 19));
        JS_FreeValue(ctx, result);
    }
    JS_FreeValue(ctx, function);
    JS_RunGC(rt);
    JS_FreeContext(ctx);
    JS_FreeRuntime(rt);
    puts("VALUE_PAYLOAD_HOST_CORE_ABI_PASS");
    return 0;
}
