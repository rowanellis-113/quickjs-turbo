/* Prove automatic VM fills/hits and live weak invalidation without Prepare. */
#include "quickjs.h"
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

extern void JS_FrameCallLinkStats(const JSValue *, uint64_t[8]);
extern unsigned JS_FrameCallLinkVMState(void);
#ifdef FRAME_TEST_CALL_METADATA
extern unsigned JS_FrameCallMetaState(void);
extern unsigned JS_FrameCallMetaExtraBytes(const JSValue *);
extern uint64_t JS_FrameCallDestHits;
#endif
#define CHECK(x)                                                                                   \
    do {                                                                                           \
        if (!(x)) {                                                                                \
            fprintf(stderr, "CALL_LINK_VM line=%d: %s\n", __LINE__, #x);                           \
            exit(1);                                                                               \
        }                                                                                          \
    } while (0)

static JSValue evaluate(JSContext *ctx, const char *source)
{
    JSValue value = JS_Eval(ctx, source, strlen(source), "call-link-vm.js", 0);
    CHECK(!JS_IsException(value));
    return value;
}

static void invoke(JSContext *ctx, JSValue owner, JSValue target, int input, int expected)
{
    JSValue args[2] = {target, JS_NewInt32(ctx, input)};
    JSValue result = JS_Call(ctx, owner, JS_UNDEFINED, 2, args);
    CHECK(!JS_IsException(result));
    int32_t actual = 0;
    CHECK(JS_ToInt32(ctx, &actual, result) == 0 && actual == expected);
    JS_FreeValue(ctx, result);
}

int main(void)
{
    JSRuntime *rt = JS_NewRuntime();
    CHECK(rt);
    JSContext *ctx = JS_NewContext(rt);
    CHECK(ctx);
    JSValue owner =
        evaluate(ctx, "(function owner(f,x){let r=0;for(let i=0;i<2;i++)r=f(x);return r+3;})");
    JSValue first = evaluate(ctx, "(function first(x){for(let i=0;i<2;i++)x++;return x;})");
    JSValue second = evaluate(ctx, "(function second(x){for(let i=0;i<4;i++)x++;return x;})");
    uint64_t stats[8];
    for (unsigned i = 0; i < 200; i++) {
        invoke(ctx, owner, first, 7, 12);
        invoke(ctx, owner, second, 7, 14);
    }
    JS_FrameCallLinkStats(&owner, stats);
    int default_off = getenv("FRAME_TEST_CALL_LINK_DEFAULT_OFF") != NULL;
    int disabled = default_off || getenv("QJS_DISABLE_CALL_LINK") != NULL ||
                   getenv("QJS_DISABLE_CALL_LINK_VM") != NULL;
    CHECK(JS_FrameCallLinkVMState() == (disabled ? 2u : 1u));
    if (disabled)
        CHECK(stats[0] == 0 && stats[5] == 0);
    else {
        CHECK(stats[0] == 1 && stats[5] == 2);
#ifdef QJS_INTERP_FRAME_DIAGNOSTICS
        CHECK(stats[1] > 300 && stats[3] >= 2);
#endif
    }
    uint64_t hits = stats[1];
#ifdef FRAME_TEST_CALL_METADATA
    /* The GNU default-off case exercises VM link policy and weak lifetime.
       Metadata modes are checked in the explicit opt-in/control cases below;
       turning VM links off does not by itself turn the metadata cache off. */
    if (!default_off) {
        unsigned meta_mode = getenv("QJS_DISABLE_CALL_META_DIRECT")
                                 ? 2u
                                 : (getenv("QJS_DISABLE_CALL_META_DESTINATION") ? 3u : 1u);
        CHECK(JS_FrameCallMetaState() == meta_mode);
        CHECK(JS_FrameCallMetaExtraBytes(&owner) == (!disabled && meta_mode != 2 ? 40u : 0u));
#ifdef QJS_INTERP_FRAME_DIAGNOSTICS
        CHECK((JS_FrameCallDestHits > 300) == (!disabled && meta_mode == 1));
#endif
    }
#endif
    JS_FreeValue(ctx, first);
    JS_RunGC(rt);
    JS_FrameCallLinkStats(&owner, stats);
    CHECK(stats[5] == (disabled ? 0u : 1u));
    JS_FreeValue(ctx, second);
    JS_RunGC(rt);
    JS_FrameCallLinkStats(&owner, stats);
    CHECK(stats[5] == 0);
    JSValue replacement =
        evaluate(ctx, "(function replacement(x){for(let i=0;i<6;i++)x++;return x;})");
    for (unsigned i = 0; i < 20; i++)
        invoke(ctx, owner, replacement, 7, 16);
    JS_FrameCallLinkStats(&owner, stats);
    CHECK(stats[5] == (disabled ? 0u : 1u));
    JS_FreeValue(ctx, replacement);
    JS_FreeValue(ctx, owner);
    JS_RunGC(rt);
    JS_FreeContext(ctx);
    JS_FreeRuntime(rt);
    printf("CALL_LINK_VM_PASS disabled=%d automatic_hits=%llu primary_secondary_gc_refill=1\n",
           disabled, (unsigned long long)hits);
    return 0;
}
