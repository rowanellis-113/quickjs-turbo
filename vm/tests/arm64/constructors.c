/* Natural root3/return paths,passive counters and public zero ledgers. MIT. */
#ifdef NDEBUG
#undef NDEBUG
#endif
#include "quickjs.h"
#include "src/arm64/linux/interpreter-observe.h"
#include "interpreter-aarch64-values.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "tests/common/native_oom_allocator.h"
static JSContext *ctx;
static JSValue checked(JSValue v)
{
    if (JS_IsException(v)) {
        JSValue e = JS_GetException(ctx);
        const char *s = JS_ToCString(ctx, e);
        fprintf(stderr, "ARM_CONSTRUCTOR_EXCEPTION %s\n", s ? s : "unknown");
        abort();
    }
    return v;
}
static JSValue eval(const char *s)
{
    return checked(JS_Eval(ctx, s, strlen(s), "arm-constructor-paths", JS_EVAL_TYPE_GLOBAL));
}
static void call(JSValue f, JSValue ctor, int n)
{
    JSValue argv[] = {ctor, JS_NewInt32(ctx, n)};
    JSValue r = checked(JS_Call(ctx, f, JS_UNDEFINED, 2, argv));
    int32_t value = -1;
    assert(!JS_ToInt32(ctx, &value, r) && value == n * (n - 1) / 2);
    JS_FreeValue(ctx, r);
}
int main(void)
{
    Allocator memory = {0};
    JSRuntime *rt = JS_NewRuntime2(&functions, &memory);
    assert(rt);
    ctx = JS_NewContext(rt);
    assert(ctx);
    JS_SetMaxStackSize(rt, 4 * 1024 * 1024);
    int native = ARM_HAS_CONSTRUCTORS && !getenv("QJS_DISABLE_REGISTER_INTERP") &&
                 !getenv("QJS_DISABLE_INTERP_FRAME") && !getenv("QJS_DISABLE_MIN_CALL_FRAME");
    int enabled = native && !getenv("QJS_DISABLE_FRAME_CONSTRUCT_CONTINUATION");
    const char *bodies[] = {
        "(function Plain(v){this.v=v})",
        "(function Immediate(v){this.v=v;return 3})",
        "(function StringResult(v){this.v=v;return 'ignored'})",
        "(function SymbolResult(v){this.v=v;return Symbol('ignored')})",
        "(function BigResult(v){this.v=v;return 123456789012345678901234567890n})",
        "(function ObjectResult(v){return {v:v}})",
        "(function ThisResult(v){this.v=v;return this})",
        "(function Mutable(v){v++;this.v=v-1;return undefined})"};
    JSValue driver = eval(
        "(function makeMany(C,n){let sum=0;for(let i=0;i<n;++i){let r=new C(i);sum+=r.v;}return sum})");
    for (unsigned kind = 0; kind < sizeof(bodies) / sizeof(bodies[0]); kind++) {
        JSValue ctor = eval(bodies[kind]);
        call(driver, ctor, 0);
        call(driver, ctor, 32);
        uint64_t a[8], b[8], old_ops[256], new_ops[256];
        qjs_aarch64_vm_constructor_counts(a);
        qjs_aarch64_vm_opcode_counts(old_ops);
        call(driver, ctor, 32);
        qjs_aarch64_vm_constructor_counts(b);
        qjs_aarch64_vm_opcode_counts(new_ops);
        fprintf(
            stderr,
            "ARM_CONSTRUCTOR_PATH kind=%u enabled=%d pushes=%llu pops=%llu immediate=%llu heap=%llu create=%llu Csteps=%llu Cexec=%llu finish=%llu return=%llu\n",
            kind, enabled, (unsigned long long)(b[0] - a[0]), (unsigned long long)(b[1] - a[1]),
            (unsigned long long)(b[2] - a[2]), (unsigned long long)(b[3] - a[3]),
            (unsigned long long)(b[7] - a[7]),
            (unsigned long long)(new_ops[ARM_OP_call_constructor] -
                                 old_ops[ARM_OP_call_constructor]),
            (unsigned long long)(b[4] - a[4]), (unsigned long long)(b[6] - a[6]),
            (unsigned long long)(b[5] - a[5]));
        assert(b[0] - a[0] == (enabled ? 32u : 0u));
        assert(b[7] - a[7] == (enabled ? 32u : 0u));
        /* Disabling the original host consumer retains its complete C tail
         * continuation: Symbol() returns from root3 there, before ASM pop. */
        int c_tail = enabled && kind == 3 && getenv("QJS_DISABLE_AARCH64_HOST_RETURN");
        assert(b[1] - a[1] == (enabled && !c_tail ? 32u : 0u));
        assert(b[2] - a[2] == (enabled && (kind < 2 || kind == 7) ? 32u : 0u));
        assert(b[3] - a[3] == (enabled && !c_tail && kind >= 2 && kind <= 6 ? 32u : 0u));
        if (c_tail) {
            /* Other admitted C opcodes also enter the complete executor;
             * its total is not the count of consumed host-call resumes. */
            assert(b[6] - a[6] == 32u); /* Resume finish_call,never replay. */
            assert(b[5] == a[5]);       /* No return_frame resume was substituted. */
        }
        if (native)
            assert(new_ops[ARM_OP_call_constructor] == old_ops[ARM_OP_call_constructor]);
        JS_FreeValue(ctx, ctor);
        JS_RunGC(rt);
    }
    JS_FreeValue(ctx, driver);
    JS_FreeContext(ctx);
    JS_RunGC(rt);
    JS_FreeRuntime(rt);
    assert(!memory.live && !memory.bytes);
    printf("AARCH64_CONSTRUCTOR_PATHS_OK cohorts=8 enabled=%d zero_ledgers\n", enabled);
    return 0;
}
