/* Passive same-caller next/checkpoint/dense-array evidence. MIT. */
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
static JSValue checked(JSValue r)
{
    if (JS_IsException(r)) {
        JSValue e = JS_GetException(ctx);
        const char *s = JS_ToCString(ctx, e);
        fprintf(stderr, "ITERATOR_PATH_EXCEPTION %s\n", s ? s : "unknown");
        abort();
    }
    return r;
}
static JSValue eval(const char *s)
{
    return checked(JS_Eval(ctx, s, strlen(s), "arm-iterator-paths", JS_EVAL_TYPE_GLOBAL));
}
static JSValue input(int dense)
{
    if (dense)
        return eval("Array.from({length:32},function(_,i){return i})");
    return eval(
        "({i:0,next:function(){let i=this.i++;return {value:i,done:i>=32}},[Symbol.iterator]:function(){return this}})");
}
static void invoke(JSValue driver, int dense)
{
    JSValue arg = input(dense), r = checked(JS_Call(ctx, driver, JS_UNDEFINED, 1, &arg));
    int32_t n = -1;
    assert(!JS_ToInt32(ctx, &n, r) && n == 496);
    JS_FreeValue(ctx, r);
    JS_FreeValue(ctx, arg);
}
int main(void)
{
    Allocator memory = {0};
    JSRuntime *rt = JS_NewRuntime2(&functions, &memory);
    assert(rt);
    ctx = JS_NewContext(rt);
    assert(ctx);
    JS_SetMaxStackSize(rt, 4 * 1024 * 1024);
    JSValue driver = eval("(function sum(it){let s=0;for(const v of it)s+=v;return s})");
    int enabled = ARM_HAS_ITERATORS && !getenv("QJS_DISABLE_FRAME_ITERATOR") &&
                  !getenv("QJS_DISABLE_REGISTER_INTERP") && !getenv("QJS_DISABLE_INTERP_FRAME") &&
                  !getenv("QJS_DISABLE_MIN_CALL_FRAME");
    for (int dense = 0; dense < 2; dense++) {
        invoke(driver, dense);
        invoke(driver, dense);
        uint64_t a[16], b[16], oa[256], ob[256];
        qjs_aarch64_vm_iterator_counts(a);
        qjs_aarch64_vm_opcode_counts(oa);
        invoke(driver, dense);
        qjs_aarch64_vm_iterator_counts(b);
        qjs_aarch64_vm_opcode_counts(ob);
        uint64_t pushes = b[8] - a[8], resumes = b[9] - a[9], array = b[10] - a[10],
                 steps = ob[ARM_OP_for_of_next] - oa[ARM_OP_for_of_next];
        fprintf(
            stderr,
            "ARM_ITERATOR_PATH dense=%d enabled=%d start=%llu next=%llu pushes=%llu resumes=%llu array=%llu slow_array=%llu Csteps=%llu\n",
            dense, enabled, (unsigned long long)(b[0] - a[0]), (unsigned long long)(b[1] - a[1]),
            (unsigned long long)pushes, (unsigned long long)resumes, (unsigned long long)array,
            (unsigned long long)(b[11] - a[11]), (unsigned long long)steps);
        uint64_t expected =
            enabled && !dense && !getenv("QJS_DISABLE_FRAME_ITERATOR_JS_CALL") ? 33 : 0;
        assert(pushes == expected && resumes == expected);
        assert(
            array ==
            (uint64_t)(enabled && dense && !getenv("QJS_DISABLE_FRAME_ARRAY_ITERATOR") ? 32 : 0));
        if (enabled) {
            assert(b[0] - a[0] == 1);
            assert(steps == 0);
        } else
            for (int i = 0; i < 16; i++)
                assert(a[i] == b[i]);
    }
    JS_FreeValue(ctx, driver);
    JS_FreeContext(ctx);
    JS_RunGC(rt);
    JS_FreeRuntime(rt);
    assert(!memory.live && !memory.bytes);
    puts("AARCH64_ITERATOR_PATHS_OK zero_ledgers");
    return 0;
}
