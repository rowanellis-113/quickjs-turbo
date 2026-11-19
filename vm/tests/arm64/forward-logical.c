#ifdef NDEBUG
#undef NDEBUG
#endif
#include <quickjs.h>
#include <assert.h>
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "tests/common/native_oom_allocator.h"
extern void qjs_aarch64_vm_forward_counts(uint64_t words[16]);
static JSValue eval(JSContext *c, const char *s)
{
    JSValue v = JS_Eval(c, s, strlen(s), "forward-native-return", JS_EVAL_TYPE_GLOBAL);
    assert(!JS_IsException(v));
    return v;
}
int main(void)
{
    Allocator a = {0};
    JSRuntime *r = JS_NewRuntime2(&functions, &a);
    assert(r);
    JSContext *c = JS_NewContext(r);
    assert(c);
    JS_SetMaxStackSize(r, 4 * 1024 * 1024);
    JSValue target = eval(
        c,
        "globalThis.forwardSeed={n:42};globalThis.forwardRecv={};globalThis.forwardFn=function(v){return v};globalThis.keepForwardOwners=[forwardSeed,forwardRecv,forwardFn,Function.prototype.call].map(function(v){return Array(64).fill(v)});(function run(){return forwardFn.call(forwardRecv,forwardSeed)})");
    JSValue seed = eval(c, "forwardSeed");
    uint64_t before[16], after[16];
    JSValue value = JS_Call(c, target, JS_UNDEFINED, 0, NULL);
    assert(JS_IsSameValue(c, value, seed));
    JS_FreeValue(c, value);
    qjs_aarch64_vm_forward_counts(before);
    for (unsigned i = 0; i < 32; i++) {
        value = JS_Call(c, target, JS_UNDEFINED, 0, NULL);
        assert(!JS_IsException(value) && JS_IsSameValue(c, value, seed));
        JS_FreeValue(c, value);
    }
    qjs_aarch64_vm_forward_counts(after);
    printf("FORWARD_STAGE1_PATHS C_entries=%" PRIu64 " C_children=%" PRIu64 " C_leaves=%" PRIu64
           " native_root2_returns=%" PRIu64 "\n",
           after[0] - before[0], after[1] - before[1], after[2] - before[2], after[3] - before[3]);
    if (getenv("QJS_DISABLE_FRAME_CALL_FORWARD"))
        assert(after[1] == before[1] && after[2] == before[2] && after[3] == before[3]);
    else if (getenv("QJS_DISABLE_FRAME_CALL_FORWARD_LEAF"))
        assert(after[1] - before[1] == 32 && after[3] - before[3] == 32 && after[2] == before[2]);
    else
        assert(after[2] - before[2] == 32 && after[1] == before[1] && after[3] == before[3]);
    JS_FreeValue(c, seed);
    JS_FreeValue(c, target);
    JS_FreeContext(c);
    JS_FreeRuntime(r);
    assert(!a.live && !a.bytes);
    puts("FORWARD_STAGE1_PATHS_OK zero-ledgers");
    return 0;
}
