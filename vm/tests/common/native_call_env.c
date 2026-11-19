/* Explicit management controls remain live after VM startup admission. */
#include "quickjs-interpreter-private.h"
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

extern void *JS_FrameCallLinkPrepare(JSRuntime *, JSObject *, const uint8_t *, JSObject *);
extern const uint8_t JS_FrameCallLinkOpcodeSizes[OP_COUNT];
#define CHECK(x)                                                                                   \
    do {                                                                                           \
        if (!(x)) {                                                                                \
            fprintf(stderr, "CALL_ENV line %d: %s\n", __LINE__, #x);                               \
            return 1;                                                                              \
        }                                                                                          \
    } while (0)

static int check_value(JSContext *ctx, JSValue value, int expected)
{
    int32_t actual;
    if (JS_IsException(value)) {
        JSValue error = JS_GetException(ctx);
        const char *text = JS_ToCString(ctx, error);
        fprintf(stderr, "CALL_ENV_EXCEPTION %s\n", text ? text : "?");
        JS_FreeCString(ctx, text);
        JS_FreeValue(ctx, error);
        return 1;
    }
    int rc = JS_ToInt32(ctx, &actual, value);
    JS_FreeValue(ctx, value);
    return rc || actual != expected;
}

int main(void)
{
    static char disabled[] = "QJS_DISABLE_CALL_LINK=1";
    static char enabled[] = "QJS_DISABLE_CALL_LINK=";
    CHECK(_putenv(enabled) == 0);
    JSRuntime *rt = JS_NewRuntime();
    CHECK(rt);
    JSContext *ctx = JS_NewContext(rt);
    CHECK(ctx);
    const char *caller_source = "(function owner(fn,x){const r=fn(x);return r+2;})";
    const char *callee_source = "(function target(x){for(let i=0;i<2;i++)x++;return x;})";
    JSValue owner = JS_Eval(ctx, caller_source, strlen(caller_source), "call-env-owner.js", 0);
    JSValue target = JS_Eval(ctx, callee_source, strlen(callee_source), "call-env-target.js", 0);
    CHECK(JS_IsFunction(ctx, owner) && JS_IsFunction(ctx, target));
    JSValue args[2] = {target, JS_NewInt32(ctx, 7)};
    for (unsigned warm = 0; warm < 3; warm++)
        CHECK(check_value(ctx, JS_Call(ctx, owner, JS_UNDEFINED, 2, args), 11) == 0);
    JSObject *caller = JS_VALUE_GET_OBJ(owner), *callee = JS_VALUE_GET_OBJ(target);
    JSFunctionBytecode *b = caller->u.func.function_bytecode;
    const uint8_t *pc = NULL;
    for (unsigned pos = 0; pos < (unsigned)b->byte_code_len;) {
        unsigned op = b->byte_code_buf[pos];
        CHECK(op < OP_COUNT);
        if (op == OP_call1) {
            pc = b->byte_code_buf + pos;
            break;
        }
        unsigned size = JS_FrameCallLinkOpcodeSizes[op];
        CHECK(size && size <= (unsigned)b->byte_code_len - pos);
        pos += size;
    }
    CHECK(pc);
    CHECK(JS_FrameCallLinkPrepare(rt, caller, pc, callee) != NULL);
    CHECK(_putenv(disabled) == 0);
    CHECK(JS_FrameCallLinkPrepare(rt, caller, pc, callee) == NULL);
    CHECK(check_value(ctx, JS_Call(ctx, owner, JS_UNDEFINED, 2, args), 11) == 0);
    CHECK(_putenv(enabled) == 0);
    CHECK(JS_FrameCallLinkPrepare(rt, caller, pc, callee) != NULL);
    JS_FreeValue(ctx, target);
    JS_FreeValue(ctx, owner);
    JS_RunGC(rt);
    JS_FreeContext(ctx);
    JS_FreeRuntime(rt);
    puts("CALL_ENV_PASS explicit-live-disable-preserved");
    return 0;
}
