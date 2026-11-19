/* Public-host regression: narrow tag readers, persistent owners and polls. */
#include "quickjs.h"
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static unsigned checks, born, freed, interrupts;
static JSClassID owner_class;
static int abort_interrupt;
#define CHECK(value)                                                                               \
    do {                                                                                           \
        checks++;                                                                                  \
        if (!(value)) {                                                                            \
            fprintf(stderr, "COROUTINE_HOST line %d\n", __LINE__);                                 \
            exit(1);                                                                               \
        }                                                                                          \
    } while (0)

static void finalizer(JSRuntime *rt, JSValue value)
{
    (void)rt;
    (void)value;
    freed++;
}

static JSValue owner(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    JSValue value;
    (void)self;
    (void)argc;
    (void)argv;
    value = JS_NewObjectClass(ctx, owner_class);
    if (!JS_IsException(value))
        born++;
    return value;
}

static JSValue tagged(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    JSValue value;
    int32_t tag, payload;
    (void)self;
    CHECK(argc == 2);
    CHECK(JS_ToInt32(ctx, &tag, argv[0]) == 0 && JS_ToInt32(ctx, &payload, argv[1]) == 0);
    CHECK(tag >= JS_TAG_INT && tag <= JS_TAG_UNINITIALIZED);
    value = JS_MKVAL(tag, payload);
#ifndef JS_NAN_BOXING
    /* JS_VALUE_GET_TAG explicitly reads int32_t. Exercise the host/core
       boundary without requiring callers to normalize the unused upper half. */
    uint64_t wide = UINT64_C(0x1234567800000000) | (uint32_t)tag;
    memcpy(&value.tag, &wide, sizeof(wide));
#endif
    return value;
}

static int interrupt(JSRuntime *rt, void *opaque)
{
    (void)opaque;
    interrupts++;
    JS_RunGC(rt);
    return abort_interrupt && interrupts == 2;
}

static JSValue evaluate(JSContext *ctx, const char *text)
{
    JSValue result = JS_Eval(ctx, text, strlen(text), "coroutine-host", JS_EVAL_TYPE_GLOBAL);
    if (JS_IsException(result)) {
        JSValue error = JS_GetException(ctx);
        const char *message = JS_ToCString(ctx, error);
        fprintf(stderr, "%s\n", message ? message : "exception");
        JS_FreeCString(ctx, message);
        JS_FreeValue(ctx, error);
        CHECK(0);
    }
    return result;
}

int main(void)
{
    JSRuntime *rt = JS_NewRuntime();
    CHECK(rt != NULL);
    JSContext *ctx = JS_NewContext(rt);
    CHECK(ctx != NULL);
    JSClassDef definition;
    memset(&definition, 0, sizeof(definition));
    definition.class_name = "coroutine_owner";
    definition.finalizer = finalizer;
    CHECK(JS_NewClassID(rt, &owner_class) != 0 && JS_NewClass(rt, owner_class, &definition) == 0);
    JSValue global = JS_GetGlobalObject(ctx);
    CHECK(JS_SetPropertyStr(ctx, global, "tagged", JS_NewCFunction(ctx, tagged, "tagged", 2)) >= 0);
    CHECK(JS_SetPropertyStr(ctx, global, "owner", JS_NewCFunction(ctx, owner, "owner", 0)) >= 0);
    JS_FreeValue(ctx, global);
    JSValue value =
        evaluate(ctx, "function* tags(){let a=tagged(0,-17),b=tagged(1,0);yield a+2;yield b?1:2;}"
                      "let tagResult=[...tags()];tagResult[0]===-15&&tagResult[1]===2");
    CHECK(JS_ToBool(ctx, value) == 1);
    JS_FreeValue(ctx, value);
    value =
        evaluate(ctx, "let tdzResult=false;try{(function*(){let x=tagged(4,0);yield x;})().next();}"
                      "catch(e){tdzResult=e instanceof ReferenceError;}tdzResult");
    CHECK(JS_ToBool(ctx, value) == 1);
    JS_FreeValue(ctx, value);
    value = evaluate(ctx, "function* owners(){let x=owner();yield 1;x=42;yield x;}"
                          "globalThis.generator=owners();generator.next();");
    JS_FreeValue(ctx, value);
    CHECK(born == 1 && freed == 0);
    JS_RunGC(rt);
    CHECK(freed == 0);
    value = evaluate(ctx, "generator.next().value");
    int32_t result;
    CHECK(JS_ToInt32(ctx, &result, value) == 0 && result == 42);
    JS_FreeValue(ctx, value);
    CHECK(freed == 1);
    value = evaluate(ctx, "generator.next();generator=null;");
    JS_FreeValue(ctx, value);
    value =
        evaluate(ctx, "function* polling(){let x=owner(),a=0;for(let i=0;i<30000;i++){a=(a+i)%997;"
                      "if((i%4096)===0)yield a;}return a;}"
                      "function pollBody(){let sum=0;for(const v of polling())sum+=v;return sum;}");
    JS_FreeValue(ctx, value);
    JS_SetInterruptHandler(rt, interrupt, NULL);
    value = evaluate(ctx, "pollBody()");
    JS_FreeValue(ctx, value);
    JS_SetInterruptHandler(rt, NULL, NULL);
    CHECK(interrupts > 2);
    unsigned complete_polls = interrupts;
    interrupts = 0;
    abort_interrupt = 1;
    JS_SetInterruptHandler(rt, interrupt, NULL);
    value = JS_Eval(ctx, "pollBody()", 10, "coroutine-abort", JS_EVAL_TYPE_GLOBAL);
    CHECK(JS_IsException(value));
    JS_FreeValue(ctx, JS_GetException(ctx));
    JS_SetInterruptHandler(rt, NULL, NULL);
    CHECK(interrupts == 2);
    JS_RunGC(rt);
    JS_FreeContext(ctx);
    JS_FreeRuntime(rt);
    CHECK(born == freed);
    printf("COROUTINE_HOST checks=%u born=%u freed=%u polls=%u abort_polls=%u\n", checks, born,
           freed, complete_polls, interrupts);
    return 0;
}
