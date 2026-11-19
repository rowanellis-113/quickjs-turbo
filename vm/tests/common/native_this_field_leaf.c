#ifdef NDEBUG
#undef NDEBUG
#endif
#include "quickjs.h"
#include "interpreter-private-abi-values.h"
#include <assert.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <windows.h>

typedef JSValue (*CallEntry)(JSContext *, JSValueConst, JSValueConst, JSValueConst, int,
                             JSValueConst *, int);
extern JSValue JS_FrameRootLeafSelect(JSContext *, JSValueConst, JSValueConst, JSValueConst, int,
                                      JSValueConst *, int);
extern JSValue JS_FrameLegacyChildLeaf(JSContext *, JSValueConst, JSValueConst, JSValueConst, int,
                                       JSValueConst *, int);
extern JSValue JS_FrameDispatchInternal(JSContext *, JSValueConst, JSValueConst, JSValueConst, int,
                                        JSValueConst *, int);
extern JSValue qjs_frame_core_JS_CallInternal(JSContext *, JSValueConst, JSValueConst, JSValueConst,
                                              int, JSValueConst *, int);
extern void JS_FrameThisFieldLeaf(void);
extern void JS_FrameThisFieldLeaf_end(void);
extern void JS_FrameSymbolFieldLeaf(void);
extern void JS_FrameSymbolFieldLeaf_end(void);
extern void JS_FrameRootLeafSelect_end(void);
extern void JS_FrameLegacyChildLeaf_end(void);
extern JS_EXTERN unsigned char JS_FrameGetterLeafControl;
static unsigned checks, finalizers, interrupts;

static JSValue eval(JSContext *ctx, const char *source)
{
    JSValue result =
        JS_Eval(ctx, source, strlen(source), "this-field-leaf.js", JS_EVAL_TYPE_GLOBAL);
    assert(!JS_IsException(result));
    return result;
}
static void finalize(JSRuntime *rt, JSValue value)
{
    (void)rt;
    (void)value;
    finalizers++;
}
static JSValue collect(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)self;
    (void)argc;
    (void)argv;
    JS_RunGC(JS_GetRuntime(ctx));
    return JS_UNDEFINED;
}
static int interrupted(JSRuntime *rt, void *opaque)
{
    (void)rt;
    (void)opaque;
    interrupts++;
    return 0;
}
static JSValue floating(double number)
{
    JSValue result;
    result.tag = JS_TAG_FLOAT64;
    result.u.float64 = number;
    return result;
}
static void compare(JSContext *ctx, JSValueConst function, JSValueConst receiver)
{
    CallEntry entries[] = {JS_FrameRootLeafSelect, JS_FrameLegacyChildLeaf,
                           JS_FrameDispatchInternal};
    for (unsigned flags = 0; flags <= 2; flags += 2) {
        for (unsigned i = 0; i < sizeof(entries) / sizeof(entries[0]); i++) {
            JSValue expected = qjs_frame_core_JS_CallInternal(ctx, function, receiver, JS_UNDEFINED,
                                                              0, NULL, (int)flags);
            bool throws = JS_IsException(expected);
            if (throws) {
                JSValue error = JS_GetException(ctx);
                JS_FreeValue(ctx, error);
            }
            JSValue result = entries[i](ctx, function, receiver, JS_UNDEFINED, 0, NULL, (int)flags);
            assert(JS_IsException(result) == throws);
            if (throws) {
                JSValue error = JS_GetException(ctx);
                JS_FreeValue(ctx, error);
            } else {
                assert(JS_IsSameValue(ctx, result, expected));
                JS_FreeValue(ctx, result);
                JS_FreeValue(ctx, expected);
            }
            checks++;
        }
    }
}
static void unwind_leaf(uintptr_t address, uintptr_t end)
{
    DWORD64 base = 0;
    PRUNTIME_FUNCTION row = RtlLookupFunctionEntry((DWORD64)address, &base, NULL);
    assert(row && base + row->BeginAddress == address && base + row->EndAddress == end);
    const unsigned char *info = (const unsigned char *)(uintptr_t)(base + row->UnwindData);
    assert(info[0] == 1 && info[1] == 0 && info[2] == 0 && info[3] == 0);
    DWORD64 stack[2] = {0x12345678};
    CONTEXT state;
    memset(&state, 0, sizeof(state));
    state.ContextFlags = CONTEXT_FULL;
    state.Rip = (DWORD64)address;
    state.Rsp = (DWORD64)(uintptr_t)stack;
    state.Rbx = 0x1111;
    state.R12 = 0x2222;
    state.R15 = 0x3333;
    PVOID handler = NULL;
    DWORD64 frame = 0;
    RtlVirtualUnwind(UNW_FLAG_NHANDLER, base, state.Rip, row, &state, &handler, &frame, NULL);
    assert(state.Rip == stack[0] && state.Rsp == (DWORD64)(uintptr_t)(stack + 1));
    assert(state.Rbx == 0x1111 && state.R12 == 0x2222 && state.R15 == 0x3333);
}
static void symbol_getters(JSContext *ctx, JSValueConst receiver)
{
    JSValue fixture = eval(
        ctx, "(()=>{let kind={code:Symbol.for('field-symbol')};return ["
             "function(){return this.slot==kind.code},function(){return this.slot===kind.code},"
             "function(v){kind=v},kind]})()");
    JSValue functions[2] = {JS_GetPropertyUint32(ctx, fixture, 0),
                            JS_GetPropertyUint32(ctx, fixture, 1)};
    JSValue setter = JS_GetPropertyUint32(ctx, fixture, 2),
            kind = JS_GetPropertyUint32(ctx, fixture, 3);
    JSValue symbol = JS_GetPropertyStr(ctx, kind, "code");
    assert(JS_IsSymbol(symbol));
    assert(JS_SetPropertyStr(ctx, receiver, "slot", JS_DupValue(ctx, symbol)) > 0);
    for (unsigned i = 0; i < 2; i++) {
        for (unsigned j = 0; j < 4; j++) {
            JSValue result = JS_Call(ctx, functions[i], receiver, 0, NULL);
            assert(!JS_IsException(result) && JS_ToBool(ctx, result) == 1);
            JS_FreeValue(ctx, result);
        }
        unsigned char *object = JS_VALUE_GET_PTR(functions[i]);
        unsigned char *b =
            *(unsigned char **)(object + QJS_ABI_OFF_JSObject_u_func_function_bytecode);
        assert(*(int32_t *)(b + QJS_ABI_OFF_JSFunctionBytecode_byte_code_len) == 18);
        assert(*(uint16_t *)(b + QJS_ABI_OFF_JSFunctionBytecode_closure_var_count) == 1);
        assert(*(uint16_t *)(b + QJS_ABI_OFF_JSFunctionBytecode_stack_size) == 2);
        compare(ctx, functions[i], receiver);
    }
    const char *left_values[] = {
        "Symbol.for('field-symbol')",
        "Symbol('other')",
        "1",
        "1n",
        "null",
        "undefined",
        "'field-symbol'",
        "({})",
        "Object(Symbol.for('field-symbol'))",
        "({valueOf(){thisFieldCollect();return Symbol.for('field-symbol')}})"};
    for (unsigned i = 0; i < sizeof(left_values) / sizeof(left_values[0]); i++) {
        assert(JS_SetPropertyStr(ctx, receiver, "slot", eval(ctx, left_values[i])) > 0);
        for (unsigned j = 0; j < 2; j++)
            compare(ctx, functions[j], receiver);
    }
    assert(JS_SetPropertyStr(ctx, receiver, "slot", JS_DupValue(ctx, symbol)) > 0);
    /* Read the current captured cell and current own descriptor on every hit,
     * including deletion, prototype/getter/Proxy misses and uninitialized TDZ. */
    const char *right_values[] = {
        "({code:Symbol.for('field-symbol')})",
        "({code:Symbol('other')})",
        "({code:1})",
        "({code:Object(Symbol.for('field-symbol'))})",
        "({})",
        "undefined",
        "null",
        "Object.create({code:Symbol.for('field-symbol')})",
        "({get code(){thisFieldCollect();return Symbol.for('field-symbol')}})",
        "new Proxy({code:Symbol.for('field-symbol')},{get(t,k,r){thisFieldCollect();return Reflect.get(t,k,r)}})"};
    for (unsigned i = 0; i < sizeof(right_values) / sizeof(right_values[0]); i++) {
        JSValue next = eval(ctx, right_values[i]);
        JSValue result = JS_Call(ctx, setter, JS_UNDEFINED, 1, &next);
        assert(!JS_IsException(result));
        JS_FreeValue(ctx, result);
        JS_FreeValue(ctx, next);
        for (unsigned j = 0; j < 2; j++)
            compare(ctx, functions[j], receiver);
        JS_RunGC(JS_GetRuntime(ctx));
    }
    JSValue result = JS_Call(ctx, setter, JS_UNDEFINED, 1, &kind);
    assert(!JS_IsException(result));
    JS_FreeValue(ctx, result);
    JSValue accessor =
        eval(ctx, "({get slot(){thisFieldCollect();return Symbol.for('field-symbol')}})");
    for (unsigned i = 0; i < 2; i++)
        compare(ctx, functions[i], accessor);
    JS_FreeValue(ctx, accessor);
    JSValue tdz =
        eval(ctx, "(()=>{const f=function(){return this.slot===kind.code};return f;let kind})()");
    compare(ctx, tdz, receiver);
    JS_FreeValue(ctx, tdz);
    assert(JS_SetPropertyStr(ctx, kind, "code", eval(ctx, "Symbol('replacement')")) > 0);
    for (unsigned i = 0; i < 2; i++)
        compare(ctx, functions[i], receiver);
    assert(JS_SetPropertyStr(ctx, kind, "code", JS_DupValue(ctx, symbol)) > 0);
    for (unsigned i = 0; i < 2; i++)
        compare(ctx, functions[i], receiver);
    assert(JS_SetPropertyStr(ctx, receiver, "slot", JS_NewInt32(ctx, 42)) > 0);
    JS_FreeValue(ctx, symbol);
    JS_FreeValue(ctx, kind);
    JS_FreeValue(ctx, setter);
    for (unsigned i = 0; i < 2; i++)
        JS_FreeValue(ctx, functions[i]);
    JS_FreeValue(ctx, fixture);
}
int main(void)
{
    SetErrorMode(SEM_FAILCRITICALERRORS | SEM_NOGPFAULTERRORBOX);
    unwind_leaf((uintptr_t)JS_FrameThisFieldLeaf, (uintptr_t)JS_FrameThisFieldLeaf_end);
    unwind_leaf((uintptr_t)JS_FrameSymbolFieldLeaf, (uintptr_t)JS_FrameSymbolFieldLeaf_end);
    unwind_leaf((uintptr_t)JS_FrameRootLeafSelect, (uintptr_t)JS_FrameRootLeafSelect_end);
    unwind_leaf((uintptr_t)JS_FrameLegacyChildLeaf, (uintptr_t)JS_FrameLegacyChildLeaf_end);
    JSRuntime *rt = JS_NewRuntime();
    assert(rt);
    JSContext *ctx = JS_NewContext(rt);
    assert(ctx);
    JSValue function = eval(ctx, "(function(){return this.slot})"), receiver = JS_NewObject(ctx);
    assert(JS_SetPropertyStr(ctx, receiver, "slot", JS_NewInt32(ctx, 42)) > 0);
    for (unsigned i = 0; i < 16; i++) {
        JSValue result = JS_Call(ctx, function, receiver, 0, NULL);
        int32_t number;
        assert(!JS_IsException(result) && JS_ToInt32(ctx, &number, result) == 0 && number == 42);
        JS_FreeValue(ctx, result);
    }
    if (!getenv("QJS_DISABLE_INTERP_FRAME") && !getenv("QJS_DISABLE_INTERNAL_INTERP") &&
        !getenv("QJS_DISABLE_NATIVE_CHILD_LEAF"))
        assert(JS_FrameGetterLeafControl == ((getenv("QJS_DISABLE_THIS_FIELD_LEAF") &&
                                              getenv("QJS_DISABLE_THIS_FIELD_LEAF")[0] != '0')
                                                 ? 2
                                                 : 1));
    unsigned char *object = JS_VALUE_GET_PTR(function);
    unsigned char *bytecode =
        *(unsigned char **)(object + QJS_ABI_OFF_JSObject_u_func_function_bytecode);
    assert(*(uint16_t *)(bytecode + QJS_ABI_OFF_JSFunctionBytecode_var_count) == 1);
    assert(*(uint16_t *)(bytecode + QJS_ABI_OFF_JSFunctionBytecode_stack_size) == 1);
    assert(*(int32_t *)(bytecode + QJS_ABI_OFF_JSFunctionBytecode_byte_code_len) == 9);
    JSValue values[] = {JS_UNDEFINED,
                        JS_NULL,
                        JS_FALSE,
                        JS_TRUE,
                        JS_NewInt32(ctx, -1),
                        JS_NewInt32(ctx, INT32_MAX),
                        floating(-0.0),
                        floating(NAN),
                        floating(INFINITY),
                        floating(1.5),
                        JS_NewBigInt64(ctx, 1),
                        eval(ctx, "2n**90n"),
                        JS_NewString(ctx, "hello"),
                        eval(ctx, "'x'.repeat(4096)+'y'.repeat(4096)"),
                        eval(ctx, "Symbol('value')"),
                        JS_NewObject(ctx),
                        JS_NewArray(ctx),
                        eval(ctx, "(function f(){})")};
    unsigned count = sizeof(values) / sizeof(values[0]);
    for (unsigned round = 0; round < 4; round++) {
        for (unsigned i = 0; i < count; i++) {
            assert(JS_SetPropertyStr(ctx, receiver, "slot", JS_DupValue(ctx, values[i])) > 0);
            compare(ctx, function, receiver);
        }
        /* Exercise live hash changes and deleted slots, without retaining a
         * shape/slot hint. The receiver and the bytecode keep their own atoms. */
        for (unsigned i = 0; i < 80; i++) {
            char name[32];
            snprintf(name, sizeof(name), "field%u", round * 80 + i);
            assert(JS_SetPropertyStr(ctx, receiver, name, JS_NewInt32(ctx, (int)i)) > 0);
        }
        JSAtom atom = JS_NewAtom(ctx, "slot");
        assert(JS_DeleteProperty(ctx, receiver, atom, JS_PROP_THROW) > 0);
        JS_FreeAtom(ctx, atom);
        compare(ctx, function, receiver);
        assert(JS_SetPropertyStr(ctx, receiver, "slot", JS_NewInt32(ctx, 42)) > 0);
        JS_RunGC(rt);
    }
    const char *fallbacks[] = {"Object.create({slot:42})",
                               "({get slot(){return 42}})",
                               "({get slot(){throw new TypeError('expected')}})",
                               "new Proxy({slot:42},{get(t,k,r){return Reflect.get(t,k,r)}})",
                               "Object.assign([],{slot:42})",
                               "Object.assign(new Int32Array(2),{slot:42})",
                               "Object.assign(function(){},{slot:42})",
                               "Object.create(null)",
                               "null",
                               "undefined",
                               "1",
                               "'x'"};
    for (unsigned i = 0; i < sizeof(fallbacks) / sizeof(fallbacks[0]); i++) {
        JSValue value = eval(ctx, fallbacks[i]);
        compare(ctx, function, value);
        JS_FreeValue(ctx, value);
    }
    JSValue global = JS_GetGlobalObject(ctx);
    assert(JS_SetPropertyStr(ctx, global, "thisFieldCollect",
                             JS_NewCFunction(ctx, collect, "thisFieldCollect", 0)) > 0);
    JSValue stress = eval(
        ctx,
        "(function(){class C{get value(){return this.slot}} let o=new C;"
        "let live={n:42};live.self=live;Object.defineProperty(o,'slot',{get(){thisFieldCollect();return live}});"
        "for(let i=0;i<128;i++){let v=o.value;if(v!==live||v.self!==live)throw Error('lost getter root')}return live.n})");
    for (unsigned i = 0; i < 16; i++) {
        JSValue result = JS_Call(ctx, stress, JS_UNDEFINED, 0, NULL);
        int32_t number;
        assert(!JS_IsException(result) && JS_ToInt32(ctx, &number, result) == 0 && number == 42);
        JS_FreeValue(ctx, result);
    }
    JS_FreeValue(ctx, stress);
    symbol_getters(ctx, receiver);
    JS_FreeValue(ctx, global);
    JSClassID resource_class = 0;
    JS_NewClassID(rt, &resource_class);
    JSClassDef definition = {0};
    definition.class_name = "ThisFieldResource";
    definition.finalizer = finalize;
    assert(JS_NewClass(rt, resource_class, &definition) == 0);
    CallEntry entries[] = {JS_FrameRootLeafSelect, JS_FrameLegacyChildLeaf,
                           JS_FrameDispatchInternal};
    for (unsigned i = 0; i < sizeof(entries) / sizeof(entries[0]); i++) {
        JSValue owner = JS_NewObject(ctx), resource = JS_NewObjectClass(ctx, resource_class);
        assert(JS_SetPropertyStr(ctx, owner, "slot", resource) > 0);
        JSValue result = entries[i](ctx, function, owner, JS_UNDEFINED, 0, NULL, 2);
        assert(!JS_IsException(result));
        unsigned before = finalizers;
        JS_FreeValue(ctx, owner);
        JS_RunGC(rt);
        assert(finalizers == before);
        JS_FreeValue(ctx, result);
        assert(finalizers == before + 1);
        owner = JS_NewObject(ctx);
        assert(JS_SetPropertyStr(ctx, owner, "slot", JS_DupValue(ctx, owner)) > 0);
        result = entries[i](ctx, function, owner, JS_UNDEFINED, 0, NULL, 2);
        assert(JS_IsSameValue(ctx, result, owner));
        JS_FreeValue(ctx, owner);
        JS_FreeValue(ctx, result);
        JS_RunGC(rt);
    }
    JSContext *other = JS_NewContext(rt);
    assert(other);
    compare(other, function, receiver);
    JS_FreeContext(other);
    JS_SetInterruptHandler(rt, interrupted, NULL);
    for (unsigned i = 0; i < sizeof(entries) / sizeof(entries[0]); i++) {
        *(int32_t *)((unsigned char *)ctx + QJS_ABI_OFF_JSContext_interrupt_counter) = 1;
        unsigned before = interrupts;
        JSValue result = entries[i](ctx, function, receiver, JS_UNDEFINED, 0, NULL, 2);
        assert(!JS_IsException(result) && interrupts > before);
        JS_FreeValue(ctx, result);
    }
    JS_SetInterruptHandler(rt, NULL, NULL);
    for (unsigned i = 0; i < count; i++)
        JS_FreeValue(ctx, values[i]);
    JS_FreeValue(ctx, receiver);
    JS_FreeValue(ctx, function);
    JS_RunGC(rt);
    JS_FreeContext(ctx);
    JS_FreeRuntime(rt);
    printf("this-field leaf: %u differential checks, %u finalizers, %u interrupts\n", checks,
           finalizers, interrupts);
    return 0;
}
