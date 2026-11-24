/* Public allocator reentry: observe committed local value at old BigInt free. */
#ifdef NDEBUG
#undef NDEBUG
#endif
#include "quickjs.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "tests/common/native_oom_allocator.h"
extern int qjs_aarch64_test_numeric_saved(JSContext *, JSValue);
typedef struct {
    Allocator ledger;
    JSContext *ctx;
    JSValue reader;
    void *target;
    const char *expected;
    unsigned reentries;
} State;
static State *current;
static JSValue eval(JSContext *ctx, const char *text)
{
    JSValue v = JS_Eval(ctx, text, strlen(text), "numeric-reentry", 0);
    if (JS_IsException(v)) {
        JSValue e = JS_GetException(ctx);
        const char *p = JS_ToCString(ctx, e);
        fprintf(stderr, "%s\n", p ? p : "exception");
        abort();
    }
    return v;
}
static void observed_free(void *opaque, void *ptr)
{
    State *s = opaque;
    /* The public allocator receives the allocation base, including the arena prefix. */
    if (ptr && s->target && (uintptr_t)s->target - (uintptr_t)ptr < usable(ptr)) {
        s->target = NULL;
        uintptr_t sp;
        __asm__ volatile("mov %0, sp" : "=r"(sp));
        assert(!(sp & 15));
        JSValue v = JS_Call(s->ctx, s->reader, JS_UNDEFINED, 0, NULL);
        assert(!JS_IsException(v));
        const char *p = JS_ToCString(s->ctx, v);
        assert(p && !strcmp(p, s->expected));
        JS_FreeCString(s->ctx, p);
        JS_FreeValue(s->ctx, v);
        /* Allocator-free nested GC aborts in the unchanged prior engine too.
         * Reenter ordinary JS here; run GC after the observing call returns. */
        ++s->reentries;
    }
    release(&s->ledger, ptr);
}
static JSValue arm(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)ctx;
    (void)self;
    assert(argc == 2 && JS_VALUE_GET_TAG(argv[0]) == JS_TAG_BIG_INT);
    assert(!current->target && JS_IsUndefined(current->reader));
    current->target = JS_VALUE_GET_PTR(argv[0]);
    current->reader = JS_DupValue(ctx, argv[1]);
    return JS_UNDEFINED;
}
int main(void)
{
    State s = {0};
    current = &s;
    s.reader = JS_UNDEFINED;
    JSMallocFunctions f = functions;
    f.js_free = observed_free;
    JSRuntime *rt = JS_NewRuntime2(&f, &s);
    assert(rt);
    JS_SetMaxStackSize(rt, 2 * 1024 * 1024);
    s.ctx = JS_NewContext(rt);
    assert(s.ctx);
    JSValue global = JS_GetGlobalObject(s.ctx);
    assert(JS_SetPropertyStr(s.ctx, global, "arm", JS_NewCFunction(s.ctx, arm, "arm", 2)) > 0);
    JS_FreeValue(s.ctx, global);
    JSValue warm = JS_NewBigInt64(s.ctx, INT64_C(1099511627777));
    assert(qjs_aarch64_test_numeric_saved(s.ctx, JS_DupValue(s.ctx, warm)) == 0);
    assert(qjs_aarch64_test_numeric_saved(s.ctx, warm) == 0);
    assert(qjs_aarch64_test_numeric_saved(s.ctx, JS_NewString(s.ctx, "generic fallback")) == 0);
    assert(qjs_aarch64_test_numeric_saved(s.ctx, JS_NewInt32(s.ctx, 42)) == 0);
    /* A fresh large BigInt reaches the public allocator on its last release.
     * A small BigInt can share an arena with other live values. */
    s.expected = "3";
    JSValue result =
        eval(s.ctx, "(function(bits){let v=1n<<bits;arm(v,()=>v&255n);v+=3n;return v})(8192n)");
    assert(!s.target && s.reentries == 1);
    JS_FreeValue(s.ctx, result);
    JS_FreeValue(s.ctx, s.reader);
    s.reader = JS_UNDEFINED;
    /* Actual last-reference native tail reaches the same public allocator. */
#ifndef QJS_TEST_LOCAL_ONLY
    s.expected = "42";
    s.reader = eval(s.ctx, "(()=>42)");
    JSValue value = eval(s.ctx, "1n << 8192n");
    s.target = JS_VALUE_GET_PTR(value);
    assert(qjs_aarch64_test_numeric_saved(s.ctx, value) == 0);
    assert(!s.target && s.reentries == 2);
#endif
    JS_FreeValue(s.ctx, s.reader);
    s.reader = JS_UNDEFINED;
    JS_RunGC(rt);
    JS_FreeContext(s.ctx);
    s.ctx = NULL;
    JS_FreeRuntime(rt);
    assert(!s.ledger.live && !s.ledger.bytes);
    printf("AARCH64_NUMERIC_REENTRY_OK reentry=%u live=0 bytes=0\n", s.reentries);
    return 0;
}
