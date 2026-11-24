/* Public-value alias cleanup, real finalizers and legal cross-runtime reentry. */
#undef NDEBUG
#include <quickjs.h>
#include <assert.h>
#include <execinfo.h>
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "tests/common/native_oom_allocator.h"
#include "src/arm64/linux/interpreter-observe.h"
#include "interpreter-aarch64-values.h"

typedef struct {
    Allocator memory, other_memory;
    JSRuntime *rt, *other;
    JSContext *ctx, *other_ctx;
    JSValue nested;
    JSClassID token;
    unsigned made, finalized, reentered, unwound;
    uint64_t reentry_c_returns, reentry_native_returns;
} State;

static int disabled(void);

static JSValue checked(JSContext *ctx, JSValue value)
{
    if (JS_IsException(value)) {
        JSValue error = JS_GetException(ctx);
        const char *message = JS_ToCString(ctx, error);
        fprintf(stderr, "RETURN_ALIAS_EXCEPTION %s\n", message ? message : "unknown");
        abort();
    }
    return value;
}

static JSValue eval(JSContext *ctx, const char *text)
{
    return checked(ctx, JS_Eval(ctx, text, strlen(text), "return-alias", JS_EVAL_TYPE_GLOBAL));
}

static void finalize(JSRuntime *rt, JSValue value)
{
    State *s = JS_GetRuntimeOpaque(rt);
    assert(JS_GetOpaque(value, s->token) == s);
    ++s->finalized;
    void *frames[64];
    assert(backtrace(frames, 64) >= 5);
    ++s->unwound;
    /* The destroying runtime is passive. Active GC and JS use another runtime. */
    QJSArmVMCounts nested_before, nested_after;
    uint64_t nested_ops_before[256], nested_ops_after[256];
    qjs_aarch64_vm_counts(&nested_before);
    qjs_aarch64_vm_opcode_counts(nested_ops_before);
    JS_RunGC(s->other);
    JSValue result = checked(s->other_ctx, JS_Call(s->other_ctx, s->nested, JS_UNDEFINED, 0, NULL));
    int32_t n;
    assert(!JS_ToInt32(s->other_ctx, &n, result) && n == 77);
    JS_FreeValue(s->other_ctx, result);
    qjs_aarch64_vm_counts(&nested_after);
    qjs_aarch64_vm_opcode_counts(nested_ops_after);
    s->reentry_native_returns += nested_after.native_returns - nested_before.native_returns;
    s->reentry_c_returns += nested_ops_after[ARM_OP_return] - nested_ops_before[ARM_OP_return] +
                            nested_ops_after[ARM_OP_return_undef] -
                            nested_ops_before[ARM_OP_return_undef];
    ++s->reentered;
}

static JSValue make_token(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)self;
    (void)argc;
    (void)argv;
    State *s = JS_GetRuntimeOpaque(JS_GetRuntime(ctx));
    JS_RunGC(s->rt);
    JSValue result = JS_NewObjectClass(ctx, s->token);
    if (!JS_IsException(result)) {
        JS_SetOpaque(result, s);
        ++s->made;
    }
    return result;
}

static void setup(State *s)
{
    memset(s, 0, sizeof(*s));
    s->rt = JS_NewRuntime2(&functions, &s->memory);
    s->other = JS_NewRuntime2(&functions, &s->other_memory);
    assert(s->rt && s->other);
    JS_SetMaxStackSize(s->rt, 4 * 1024 * 1024);
    JS_SetMaxStackSize(s->other, 4 * 1024 * 1024);
    JS_SetRuntimeOpaque(s->rt, s);
    s->ctx = JS_NewContext(s->rt);
    s->other_ctx = JS_NewContext(s->other);
    assert(s->ctx && s->other_ctx);
    s->nested = eval(s->other_ctx, "(function(){return 77})");
    JS_NewClassID(s->rt, &s->token);
    JSClassDef definition = {0};
    definition.class_name = "ReturnAliasToken";
    definition.finalizer = finalize;
    assert(!JS_NewClass(s->rt, s->token, &definition));
    JSValue global = JS_GetGlobalObject(s->ctx);
    assert(JS_SetPropertyStr(s->ctx, global, "makeReturnAliasToken",
                             JS_NewCFunction(s->ctx, make_token, "makeReturnAliasToken", 0)) >= 0);
    JS_FreeValue(s->ctx, global);
}

static void cleanup(State *s)
{
    JS_RunGC(s->rt);
    JS_FreeContext(s->ctx);
    JS_FreeRuntime(s->rt);
    assert(s->made == s->finalized);
    JS_FreeValue(s->other_ctx, s->nested);
    JS_FreeContext(s->other_ctx);
    JS_FreeRuntime(s->other);
    assert(!s->memory.live && !s->memory.bytes);
    assert(!s->other_memory.live && !s->other_memory.bytes);
}

static void same_value_cohort(State *s, const char *name, JSValue seed, const char *driver_text,
                              const char *child_text)
{
    JSContext *ctx = s->ctx;
    JSValue driver = eval(ctx, driver_text), child = eval(ctx, child_text);
    JSValue args[2] = {child, seed};
    QJSArmVMCounts before, after;
    uint64_t op_before[256], op_after[256];
    qjs_aarch64_vm_counts(&before);
    qjs_aarch64_vm_opcode_counts(op_before);
    for (unsigned i = 0; i < 16; ++i) {
        JSValue result = checked(ctx, JS_Call(ctx, driver, JS_UNDEFINED, 2, args));
        assert(JS_IsSameValue(ctx, result, seed));
        JS_FreeValue(ctx, result);
        JS_RunGC(s->rt);
    }
    qjs_aarch64_vm_counts(&after);
    qjs_aarch64_vm_opcode_counts(op_after);
    printf("RETURN_ALIAS_CASE %s native_returns=%" PRIu64 " c_returns=%" PRIu64 "\n", name,
           after.native_returns - before.native_returns,
           op_after[ARM_OP_return] - op_before[ARM_OP_return] + op_after[ARM_OP_return_undef] -
               op_before[ARM_OP_return_undef]);
    if (!strcmp(name, "over-32-cell-quota") && !disabled()) {
#ifdef QJS_TEST_LINEAR_RETURN
        assert(after.native_returns - before.native_returns >= 512);
        assert(op_after[ARM_OP_return] - op_before[ARM_OP_return] < 4);
#else
        assert(op_after[ARM_OP_return] - op_before[ARM_OP_return] >= 512);
#endif
    }
    JS_FreeValue(ctx, driver);
    JS_FreeValue(ctx, child);
    JS_FreeValue(ctx, seed);
}

static int disabled(void)
{
    return getenv("QJS_DISABLE_REGISTER_INTERP") || getenv("QJS_DISABLE_INTERP_FRAME");
}

static void arithmetic(State *s, int candidate)
{
    JSContext *ctx = s->ctx;
    JSValue driver = eval(ctx, "(function(){let sum=0;for(let "
                               "i=0;i<64;i++)sum+=returnAliasChild(i,1,2);return sum})");
    JSValue definition = eval(ctx, "globalThis.returnAliasChild=function(a,b,c){let "
                                   "v=a+b+c;for(let j=0;j<4;j++)v=(v+j)|0;return v}");
    JS_FreeValue(ctx, definition);
    QJSArmVMCounts before, after;
    uint64_t op_before[256], op_after[256];
    qjs_aarch64_vm_counts(&before);
    qjs_aarch64_vm_opcode_counts(op_before);
    JSValue result = checked(ctx, JS_Call(ctx, driver, JS_UNDEFINED, 0, NULL));
    int32_t n;
    assert(!JS_ToInt32(ctx, &n, result) && n == 2592);
    JS_FreeValue(ctx, result);
    qjs_aarch64_vm_counts(&after);
    qjs_aarch64_vm_opcode_counts(op_after);
    uint64_t native = after.native_returns - before.native_returns;
    uint64_t slow = op_after[ARM_OP_return] - op_before[ARM_OP_return];
    if (disabled())
        assert(!native && !after.activations);
    else if (candidate)
        assert(native >= 64 && slow < 4);
    else
        assert(slow >= 64);
    printf("RETURN_ALIAS_PATH arithmetic native_returns=%" PRIu64 " c_returns=%" PRIu64 "\n",
           native, slow);
    JS_FreeValue(ctx, driver);
}

static int oom(void)
{
    unsigned rejected = 0, failures = 0;
    for (unsigned step = 1; step <= 96; ++step) {
        State s;
        setup(&s);
        JSContext *ctx = s.ctx;
        JSValue driver =
            eval(ctx, "(function(v){function f(a,b,c,d){let x=a,y=b,z=c;a=d;b=x;c=y;return z}"
                      "let result;for(let i=0;i<32;i++)result=f(v,v,v,v);return result})");
        JSValue seed = checked(ctx, JS_NewObject(ctx));
        AllocatorArenaDrain drain = {0};
        oom_drain_arenas(s.rt, &s.memory, &drain);
        s.memory.fail_at = s.memory.sequence + step;
        JSValue result = JS_Call(ctx, driver, JS_UNDEFINED, 1, &seed);
        s.memory.fail_at = 0;
        oom_undrain_arenas(s.rt, &drain);
        if (JS_IsException(result)) {
            ++failures;
            JS_FreeValue(ctx, JS_GetException(ctx));
        } else {
            assert(JS_IsSameValue(ctx, result, seed));
            JS_FreeValue(ctx, result);
        }
        result = checked(ctx, JS_Call(ctx, driver, JS_UNDEFINED, 1, &seed));
        assert(JS_IsSameValue(ctx, result, seed));
        JS_FreeValue(ctx, result);
        rejected += s.memory.rejected;
        JS_FreeValue(ctx, seed);
        JS_FreeValue(ctx, driver);
        cleanup(&s);
    }
    assert(rejected && failures);
    printf("AARCH64_RETURN_ALIAS_OOM_OK trials=96 rejected=%u failures=%u "
           "recovery zero_ledgers\n",
           rejected, failures);
    return 0;
}

static void cross_range_last_owner(State *s)
{
    JSContext *ctx = s->ctx;
    JSValue driver = eval(ctx, "(function(f){let result=f(makeReturnAliasToken(),1,2);return "
                               "result+0})");
    JSValue children[2] = {
        eval(ctx, "(function(a,b,c){let keep=a;a=undefined;if(keep===null)return "
                  "0;let n=b+c;for(let j=0;j<4;j++)n+=j;return n+33})"),
        eval(ctx, "(function(a,b,c){let keep=a;a=undefined;let "
                  "n=b+c;if(keep===null)return 0;for(let j=0;j<4;j++)n+=j;return "
                  "n+33})")};
    /* Classify both children through ordinary public calls before counting. */
    JSValue warm = eval(ctx, "(function(f,v){let result=f(v,1,2);return result+0})");
    JSValue seed = checked(ctx, JS_NewObject(ctx));
    for (unsigned i = 0; i < 4; ++i) {
        JSValue args[2] = {children[i & 1], seed};
        JSValue result = checked(ctx, JS_Call(ctx, warm, JS_UNDEFINED, 2, args));
        int32_t n;
        assert(!JS_ToInt32(ctx, &n, result) && n == 42);
        JS_FreeValue(ctx, result);
    }
    JS_FreeValue(ctx, seed);
    JS_FreeValue(ctx, warm);
    unsigned base = s->made;
    uint64_t nested_c_base = s->reentry_c_returns;
    uint64_t nested_native_base = s->reentry_native_returns;
    QJSArmVMCounts before, after;
    uint64_t op_before[256], op_after[256];
    qjs_aarch64_vm_counts(&before);
    qjs_aarch64_vm_opcode_counts(op_before);
    for (unsigned i = 0; i < 32; ++i) {
        JSValue argument = children[i & 1];
        JSValue result = checked(ctx, JS_Call(ctx, driver, JS_UNDEFINED, 1, &argument));
        int32_t n;
        assert(!JS_ToInt32(ctx, &n, result) && n == 42);
        JS_FreeValue(ctx, result);
        assert(s->made == base + i + 1 && s->finalized == base + i + 1);
        assert(s->reentered == s->finalized);
    }
    qjs_aarch64_vm_counts(&after);
    qjs_aarch64_vm_opcode_counts(op_after);
    uint64_t calls = after.native_calls - before.native_calls;
    uint64_t slow = op_after[ARM_OP_return] - op_before[ARM_OP_return];
    uint64_t nested_c = s->reentry_c_returns - nested_c_base;
    uint64_t native = after.native_returns - before.native_returns;
    uint64_t nested_native = s->reentry_native_returns - nested_native_base;
    assert(slow >= nested_c && native >= nested_native);
    slow -= nested_c;
    native -= nested_native;
    if (!disabled()) {
        assert(calls >= 32);
#ifdef QJS_TEST_LINEAR_RETURN
        assert(native >= 64);
        assert(slow < 4);
#else
        assert(slow >= 32);
#endif
    }
    printf("RETURN_ALIAS_CROSS_RANGE_LAST_OWNER calls=%" PRIu64 " c_returns=%" PRIu64
           " finalizers=32 nested_c_returns=%" PRIu64 " nested_native_returns=%" PRIu64 "\n",
           calls, slow, nested_c, nested_native);
    JS_FreeValue(ctx, children[0]);
    JS_FreeValue(ctx, children[1]);
    JS_FreeValue(ctx, driver);
}

int main(int argc, char **argv)
{
    assert(argc == 2);
    if (!strcmp(argv[1], "oom"))
        return oom();
    int candidate = !strcmp(argv[1], "candidate");
    assert(candidate || !strcmp(argv[1], "prior"));
    State s;
    setup(&s);
    arithmetic(&s, candidate);
    const char *driver = "(function(f,v){let r;for(let i=0;i<32;i++)r=f(v,v,v,v);return r})";
    const char *child = "(function(a,b,c,d){let x=a,y=b,z=c;a=d;b=x;c=y;return z})";
    JSValue seeds[] = {checked(s.ctx, JS_NewObject(s.ctx)),
                       checked(s.ctx, JS_NewString(s.ctx, "dynamic alias seed")),
                       eval(s.ctx, "Symbol('alias')"),
                       eval(s.ctx, "123456789012345678901234567890n"), JS_NewFloat64(s.ctx, -0.0)};
    const char *names[] = {"object", "string", "symbol", "bigint", "negative-zero"};
    for (unsigned i = 0; i < sizeof(seeds) / sizeof(seeds[0]); ++i)
        same_value_cohort(&s, names[i], seeds[i], driver, child);
    same_value_cohort(&s, "tail", checked(s.ctx, JS_NewObject(s.ctx)),
                      "(function(f,v){return f(v,v,v,v)})", child);
    same_value_cohort(&s, "captured-owner", checked(s.ctx, JS_NewObject(s.ctx)),
                      "(function(f,v){let g=f(v);return g()})",
                      "(function(a){return function(){return a}})");
    char large_driver[4096], large_child[4096];
    size_t dc = (size_t)snprintf(large_driver, sizeof(large_driver),
                                 "(function(f,v){let r;for(let i=0;i<32;i++)r=f(");
    size_t cc = (size_t)snprintf(large_child, sizeof(large_child), "(function(");
    for (unsigned i = 0; i < 40; ++i) {
        dc += (size_t)snprintf(large_driver + dc, sizeof(large_driver) - dc, "%sv", i ? "," : "");
        cc +=
            (size_t)snprintf(large_child + cc, sizeof(large_child) - cc, "%sa%u", i ? "," : "", i);
    }
    dc += (size_t)snprintf(large_driver + dc, sizeof(large_driver) - dc, ");return r})");
    cc += (size_t)snprintf(large_child + cc, sizeof(large_child) - cc,
                           "){let n=0;for(let k=0;k<4;k++)n+=k;a0=undefined;return a39})");
    assert(dc < sizeof(large_driver) && cc < sizeof(large_child));
    same_value_cohort(&s, "over-32-cell-quota", checked(s.ctx, JS_NewObject(s.ctx)), large_driver,
                      large_child);
    JSValue last = eval(s.ctx, "(function(){let token=makeReturnAliasToken();let "
                               "n=0;for(let i=0;i<4;i++)n+=i;return n+36})");
    for (unsigned i = 0; i < 32; ++i) {
        JSValue result = checked(s.ctx, JS_Call(s.ctx, last, JS_UNDEFINED, 0, NULL));
        int32_t n;
        assert(!JS_ToInt32(s.ctx, &n, result) && n == 42);
        JS_FreeValue(s.ctx, result);
        assert(s.made == i + 1 && s.finalized == i + 1 && s.reentered == i + 1);
    }
    JS_FreeValue(s.ctx, last);
    cross_range_last_owner(&s);
    cleanup(&s);
    printf("AARCH64_RETURN_ALIAS_OK candidate=%d finalized=%u reentry=%u "
           "unwind=%u zero_ledgers\n",
           candidate, s.finalized, s.reentered, s.unwound);
    return 0;
}
