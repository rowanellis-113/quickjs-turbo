/* Public API tests for compiler analysis and lexical resource ownership. */
#ifndef _WIN32
#define _POSIX_C_SOURCE 200809L
#endif
#ifdef NDEBUG
#undef NDEBUG
#endif
#include "quickjs.h"
#include <assert.h>
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>

typedef struct {
    unsigned born, finalized;
    size_t length;
    char trace[32768];
} State;
static JSClassID resource_class;
static void event(JSRuntime *rt, char kind, int value)
{
    State *state = JS_GetRuntimeOpaque(rt);
    int size = snprintf(state->trace + state->length, sizeof(state->trace) - state->length, "%c%d;",
                        kind, value);
    assert(size > 0 && (size_t)size < sizeof(state->trace) - state->length);
    state->length += (size_t)size;
}
static void finalize(JSRuntime *rt, JSValue value)
{
    State *state = JS_GetRuntimeOpaque(rt);
    int id = (int)(intptr_t)JS_GetOpaque(value, resource_class);
    state->finalized++;
    event(rt, 'F', id);
}
static JSValue make(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    int32_t id;
    if (argc != 1 || JS_ToInt32(ctx, &id, argv[0]))
        return JS_EXCEPTION;
    JSValue value = JS_NewObjectClass(ctx, resource_class);
    if (JS_IsException(value))
        return value;
    JS_SetOpaque(value, (void *)(intptr_t)id);
    State *state = JS_GetRuntimeOpaque(JS_GetRuntime(ctx));
    state->born++;
    event(JS_GetRuntime(ctx), 'N', id);
    return value;
}
static JSValue use(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    assert(argc == 1);
    int id = (int)(intptr_t)JS_GetOpaque(argv[0], resource_class);
    assert(id);
    event(JS_GetRuntime(ctx), 'U', id);
    return JS_NewInt32(ctx, id);
}
static JSValue mark(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    int32_t id;
    if (argc != 1 || JS_ToInt32(ctx, &id, argv[0]))
        return JS_EXCEPTION;
    event(JS_GetRuntime(ctx), 'M', id);
    JS_RunGC(JS_GetRuntime(ctx));
    return JS_UNDEFINED;
}
static JSValue gc(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    event(JS_GetRuntime(ctx), 'G', 0);
    JS_RunGC(JS_GetRuntime(ctx));
    return JS_UNDEFINED;
}

static void feature(const char *name, int disabled)
{
#ifdef _WIN32
    assert(_putenv_s(name, disabled ? "0" : "") == 0);
#else
    assert((disabled ? setenv(name, "0", 1) : unsetenv(name)) == 0);
#endif
}
static size_t compile_probe(JSContext *ctx, int checks_off, int entry_off)
{
    const char *code = "function planProof(n){let a=n+1;let b=a*2;return a+b;}planProof(4);";
    feature("QJS_DISABLE_TDZ_PLAN", checks_off);
    feature("QJS_DISABLE_TDZ_INIT", entry_off);
    JSValue compiled = JS_Eval(ctx, code, strlen(code), "compiler-plan-probe.js",
                               JS_EVAL_TYPE_GLOBAL | JS_EVAL_FLAG_COMPILE_ONLY);
    assert(!JS_IsException(compiled));
    size_t length = 0;
    uint8_t *bytes = JS_WriteObject(ctx, &length, compiled, JS_WRITE_OBJ_BYTECODE);
    assert(bytes && length);
    JS_FreeValue(ctx, compiled);
    JSValue restored = JS_ReadObject(ctx, bytes, length, JS_READ_OBJ_BYTECODE);
    js_free(ctx, bytes);
    assert(!JS_IsException(restored));
    JSValue result = JS_EvalFunction(ctx, restored);
    int32_t value = 0;
    assert(!JS_IsException(result) && JS_ToInt32(ctx, &value, result) == 0 && value == 15);
    JS_FreeValue(ctx, result);
    return length;
}
static int bytecode_probe(void)
{
    JSRuntime *rt = JS_NewRuntime();
    assert(rt);
    JS_SetMaxStackSize(rt, 2 * 1024 * 1024);
    JSContext *ctx = JS_NewContext(rt);
    assert(ctx);
    size_t original = compile_probe(ctx, 1, 1), checks_only = compile_probe(ctx, 0, 1),
           optimized = compile_probe(ctx, 0, 0), entry_only = compile_probe(ctx, 1, 0),
           original_again = compile_probe(ctx, 1, 1);
    assert(optimized < original && optimized <= checks_only && checks_only <= original &&
           entry_only <= original && original_again == original);
    JS_FreeContext(ctx);
    JS_FreeRuntime(rt);
    printf("COMPILER_PLAN_BYTECODE_OK original=%zu checks=%zu optimized=%zu entry=%zu\n", original,
           checks_only, optimized, entry_only);
    return 0;
}

int main(int argc, char **argv)
{
    if (argc == 2 && !strcmp(argv[1], "--bytecode"))
        return bytecode_probe();
    State state = {0};
    JSRuntime *rt = JS_NewRuntime();
    assert(rt);
    JS_SetRuntimeOpaque(rt, &state);
    JS_SetMaxStackSize(rt, 2 * 1024 * 1024);
    JSContext *ctx = JS_NewContext(rt);
    assert(ctx);
    JS_NewClassID(rt, &resource_class);
    JSClassDef definition = {0};
    definition.class_name = "EntryInitResource";
    definition.finalizer = finalize;
    assert(JS_NewClass(rt, resource_class, &definition) == 0);
    JSValue global = JS_GetGlobalObject(ctx);
    assert(JS_SetPropertyStr(ctx, global, "make", JS_NewCFunction(ctx, make, "make", 1)) > 0);
    assert(JS_SetPropertyStr(ctx, global, "use", JS_NewCFunction(ctx, use, "use", 1)) > 0);
    assert(JS_SetPropertyStr(ctx, global, "mark", JS_NewCFunction(ctx, mark, "mark", 1)) > 0);
    assert(JS_SetPropertyStr(ctx, global, "gcNative", JS_NewCFunction(ctx, gc, "gcNative", 0)) > 0);
    JS_FreeValue(ctx, global);
    const char *code =
        "function first(n){let value=(mark(100+n),make(n));use(value);return n;}first(1);first(2);"
        "function loops(){for(var i=0;i<3;i++){let value=(mark(200+i),make(10+i));use(value);if(i===1)gcNative();}mark(299);}loops();"
        "function captured(){let value=make(30);return ()=>use(value);}globalThis.keep=captured();gcNative();keep();keep=null;gcNative();"
        "function failed(){let value=(mark(400),(()=>{throw Error('initializer');})());return value;}try{failed();throw Error('missing throw');}catch(e){if(e.message!=='initializer')throw e;}"
        "function named(){let self=named;return self;}named.owner=make(40);if(named()!==named)throw Error('self binding');named.owner=null;"
        "function fused(){let a=make(50);a=make(51);{let b=a;use(b);}}fused();gcNative();"
        "function initGC(){let a=make(52);{let b=(gcNative(),a);use(b);}}initGC();gcNative();"
        "function args(a){let own=arguments;if(own[0]!==a)throw Error('arguments');}args(7);gcNative();";
    JSValue result =
        JS_Eval(ctx, code, strlen(code), "entry-init-ownership.js", JS_EVAL_TYPE_GLOBAL);
    if (JS_IsException(result)) {
        JSValue error = JS_GetException(ctx);
        const char *message = JS_ToCString(ctx, error);
        fprintf(stderr, "%s\n", message ? message : "exception");
        JS_FreeCString(ctx, message);
        JS_FreeValue(ctx, error);
        return 2;
    }
    JS_FreeValue(ctx, result);
    JS_RunGC(rt);
    JS_FreeContext(ctx);
    JS_FreeRuntime(rt);
    assert(state.born == 10 && state.finalized == state.born);
    printf("TRACE %s\nENTRY_INIT_OWNERSHIP_OK born=%u finalized=%u\n", state.trace, state.born,
           state.finalized);
    return 0;
}
