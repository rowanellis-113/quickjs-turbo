#ifdef NDEBUG
#undef NDEBUG
#endif
#include "quickjs.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <execinfo.h>

#include "src/arm64/linux/interpreter-observe.h"
#include "interpreter-aarch64-values.h"
static uintptr_t observed_sp;
static unsigned samples;

static JSValue sample(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)ctx;
    (void)self;
    (void)argc;
    (void)argv;
    __asm__ volatile("mov %0, sp" : "=r"(observed_sp));
    assert((observed_sp & 15) == 0);
    void *trace[32];
    assert(backtrace(trace, 32) >= 6);
    samples++;
    JS_RunGC(JS_GetRuntime(ctx));
    return JS_NewInt32(ctx, 1);
}

static JSValue checked(JSContext *ctx, JSValue value)
{
    if (JS_IsException(value)) {
        JSValue error = JS_GetException(ctx);
        const char *message = JS_ToCString(ctx, error);
        fprintf(stderr, "ARM register VM: %s\n", message ? message : "<exception>");
        JS_FreeCString(ctx, message);
        JS_FreeValue(ctx, error);
        abort();
    }
    return value;
}

static void eval(JSContext *ctx, const char *text)
{
    JS_FreeValue(ctx, checked(ctx, JS_Eval(ctx, text, strlen(text), "<arm-register-vm>",
                                           JS_EVAL_TYPE_GLOBAL)));
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
    JSValue global = JS_GetGlobalObject(ctx);
    assert(JS_SetPropertyStr(ctx, global, "sample", JS_NewCFunction(ctx, sample, "sample", 0)) ==
           1);
    eval(ctx, "function depth(n){if(n===0)return sample();return depth(n-1)+1;}"
              "function primitives(a,b,c,d){let x=1;return a+b+c+d+x;}"
              "function fallback(){try{throw 7;}catch(e){return e;}}"
              "function closure(x){return function(y){return x+y;};}"
              "function check(v,msg){if(!v)throw Error(msg);}"
              "check(primitives(2,3,4,5)===15,'arguments');"
              "check(fallback()===7,'unsupported function');"
              "check(closure(12)(9)===21,'captured owner');"
              "check((2147483647+1)===2147483648,'overflow');"
              "check(((-2147483648)-1)===-2147483649,'underflow');"
              "check(Object.is((-0)+(-0),-0),'minus zero');"
              "check(Number.isNaN(NaN+1),'nan');"
              "check(('x'+2)==='x2','string fallback');");
    JSValue driver = JS_GetPropertyStr(ctx, global, "depth");
    QJSArmVMCounts before, after;
    qjs_aarch64_vm_counts(&before);
    JSValue arg = JS_NewInt32(ctx, 10);
    JSValue result = checked(ctx, JS_Call(ctx, driver, JS_UNDEFINED, 1, &arg));
    int32_t value;
    assert(JS_ToInt32(ctx, &value, result) == 0 && value == 11);
    JS_FreeValue(ctx, result);
    uintptr_t shallow = observed_sp;
    qjs_aarch64_vm_counts(&after);
    if (native)
        assert(after.activations - before.activations == 1 && after.native_ops > before.native_ops);
    else
        assert(after.activations == 0);
    before = after;
    uint64_t op_before[256], op_after[256];
    qjs_aarch64_vm_opcode_counts(op_before);
    arg = JS_NewInt32(ctx, 200);
    result = checked(ctx, JS_Call(ctx, driver, JS_UNDEFINED, 1, &arg));
    assert(JS_ToInt32(ctx, &value, result) == 0 && value == 201);
    JS_FreeValue(ctx, result);
    uintptr_t deep = observed_sp;
    qjs_aarch64_vm_counts(&after);
    qjs_aarch64_vm_opcode_counts(op_after);
    for (unsigned i = 0; i < 256; i++)
        if (op_after[i] != op_before[i])
            fprintf(stderr, "REGISTER_VM_C_OPCODE opcode=%u count=%llu\n", i,
                    (unsigned long long)(op_after[i] - op_before[i]));
    fprintf(stderr, "REGISTER_VM_C_TRANSFERS total=%llu\n",
            (unsigned long long)(after.c_steps - before.c_steps));
    uintptr_t delta = shallow > deep ? shallow - deep : deep - shallow;
    if (native) {
        assert(after.activations - before.activations == 1);
        assert(after.native_ops - before.native_ops > 200);
        uint64_t call_fallbacks = op_after[ARM_OP_call1] - op_before[ARM_OP_call1];
        uint64_t global_steps = op_after[ARM_OP_get_var] - op_before[ARM_OP_get_var];
        assert(call_fallbacks <= 10);
        assert(global_steps == (ARM_HAS_GLOBAL_BINDING ? 0u : 201u));
        for (unsigned i = 0; i < 256; i++)
            if (i != ARM_OP_call1 && i != ARM_OP_get_var)
                assert(op_after[i] == op_before[i]);
        // Retain the real sample host call and every fallback;native globals
        // remove201C opcode entries,not the independently observed C owners.
        assert(after.c_steps - before.c_steps == call_fallbacks + global_steps + 1);
        assert(after.native_calls - before.native_calls >= 190);
        assert(after.native_returns - before.native_returns >= 190);
        assert(delta < 512);
    } else
        assert(after.activations == 0);
    assert(samples == 2);
    JS_FreeValue(ctx, driver);
    JS_FreeValue(ctx, global);
    JS_FreeContext(ctx);
    JS_FreeRuntime(rt);
    printf(
        "AARCH64_REGISTER_VM_OK mode=%s activations=%llu native_ops=%llu c_steps=%llu depth=200 host_sp_delta=%llu calls=%llu returns=%llu\n",
        argv[1], (unsigned long long)after.activations, (unsigned long long)after.native_ops,
        (unsigned long long)after.c_steps, (unsigned long long)delta,
        (unsigned long long)after.native_calls, (unsigned long long)after.native_returns);
    return 0;
}
