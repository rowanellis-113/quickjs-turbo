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
    JSValue v = JS_Eval(c, s, strlen(s), "forward-native-leaf", JS_EVAL_TYPE_GLOBAL);
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
    JSValue driver = eval(
        c,
        "globalThis.forwardInteger=function(v){return v+1};(function run(){return forwardInteger.call(undefined,42)})");
    JSValue out = JS_Call(c, driver, JS_UNDEFINED, 0, NULL);
    int32_t n;
    assert(!JS_IsException(out) && !JS_ToInt32(c, &n, out) && n == 43);
    JS_FreeValue(c, out);
    uint64_t before[16], after[16];
    qjs_aarch64_vm_forward_counts(before);
    for (unsigned i = 0; i < 32; i++) {
        out = JS_Call(c, driver, JS_UNDEFINED, 0, NULL);
        assert(!JS_IsException(out) && !JS_ToInt32(c, &n, out) && n == 43);
        JS_FreeValue(c, out);
    }
    qjs_aarch64_vm_forward_counts(after);
    printf("FORWARD_NATIVE_INTEGER_PATH C_entries=%" PRIu64 " C_leaf=%" PRIu64
           " native_leaf=%" PRIu64 "\n",
           after[0] - before[0], after[2] - before[2], after[4] - before[4]);
    if (getenv("QJS_DISABLE_FRAME_CALL_FORWARD") ||
        getenv("QJS_DISABLE_FRAME_CALL_FORWARD_NATIVE")) {
        assert(after[4] == before[4]);
        if (getenv("QJS_DISABLE_FRAME_CALL_FORWARD_NATIVE") &&
            !getenv("QJS_DISABLE_FRAME_CALL_FORWARD"))
            assert(after[0] - before[0] == 32 && after[2] - before[2] == 32);
    } else
        assert(after[4] - before[4] == 32 && after[0] == before[0] && after[2] == before[2]);
    JS_FreeValue(c, driver);
    JS_FreeContext(c);
    JS_FreeRuntime(r);
    assert(!a.live && !a.bytes);
    puts("FORWARD_NATIVE_INTEGER_PATH_OK zero-ledgers");
    return 0;
}
