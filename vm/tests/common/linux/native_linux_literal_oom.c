/* Fail each actual literal-execution allocation, recover, and free all owners.
 * The sweep uses public API only and a fresh runtime per fault. MIT. */
#include "quickjs.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef NDEBUG
#error Fault fixture requires active assertions.
#endif
#include "../native_oom_allocator.h"

static unsigned failures, successes, injected;
static void validate(JSContext *ctx, JSValueConst value)
{
    JSValue source = JS_GetPropertyStr(ctx, value, "source");
    const char *text = JS_ToCString(ctx, source);
    assert(text && !strcmp(text, "ab"));
    JS_FreeCString(ctx, text);
    JS_FreeValue(ctx, source);
}
static size_t trial(size_t fault)
{
    Allocator memory = {0};
    JSRuntime *rt = JS_NewRuntime2(&functions, &memory);
    assert(rt);
    JSContext *ctx = JS_NewContext(rt);
    assert(ctx);
    const char *source = "(function linuxOomLiteral(){return /ab/gy;})";
    JSValue fn = JS_Eval(ctx, source, strlen(source), "literal-oom", JS_EVAL_TYPE_GLOBAL);
    assert(!JS_IsException(fn));
    size_t before = memory.sequence;
    memory.fail_at = fault ? before + fault : 0;
    JSValue value = JS_Call(ctx, fn, JS_UNDEFINED, 0, NULL);
    memory.fail_at = 0;
    size_t allocations = memory.sequence - before;
    injected += memory.rejected;
    if (JS_IsException(value)) {
        failures++;
        value = JS_GetException(ctx);
        assert(!JS_IsUndefined(value));
    } else {
        successes++;
        validate(ctx, value);
    }
    JS_FreeValue(ctx, value);
    value = JS_Call(ctx, fn, JS_UNDEFINED, 0, NULL);
    assert(!JS_IsException(value));
    validate(ctx, value);
    JS_FreeValue(ctx, value);
    JS_RunGC(rt);
    JS_FreeValue(ctx, fn);
    JS_FreeContext(ctx);
    JS_FreeRuntime(rt);
    assert(memory.live == 0 && memory.bytes == 0);
    return allocations;
}
int main(void)
{
    size_t count = trial(0);
    for (size_t fault = 1; fault <= count + 2; ++fault)
        trial(fault);
    assert(failures && successes && injected);
    printf("LINUX_LITERAL_OOM_OK allocations=%zu failures=%u successes=%u injected=%u\n", count,
           failures, successes, injected);
    return 0;
}
