#ifdef NDEBUG
#undef NDEBUG
#endif
/* Exercise the actual public-entry object independently of its C executors.
 * Unused context bytes are poisoned so reading a stale ctx->rt offset cannot
 * happen to work by following an unrelated GC-list link. */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "quickjs.h"
#include "interpreter-private-abi-values.h"

static unsigned char context_bytes[QJS_ABI_SIZE_JSContext];
static unsigned char runtime_bytes[QJS_ABI_SIZE_JSRuntime];
static JSValue arguments[3];
static int selected, resolutions, executions;

static void check_arguments(JSContext *ctx, JSValueConst function, JSValueConst this_value,
                            int argc, JSValueConst *argv)
{
    assert(ctx == (JSContext *)context_bytes);
    assert(JS_VALUE_GET_INT(function) == 11);
    assert(JS_VALUE_GET_INT(this_value) == 12);
    assert(argc == 3 && argv == arguments);
    for (int i = 0; i < argc; ++i)
        assert(JS_VALUE_GET_INT(argv[i]) == 21 + i);
}

int JS_FrameResolveCall(JSContext *ctx, const JSValue *function)
{
    assert(ctx == (JSContext *)context_bytes);
    assert(JS_VALUE_GET_INT(*function) == 11);
    ++resolutions;
    return selected;
}

JSValue JS_LegacyCall(JSContext *ctx, JSValueConst function, JSValueConst this_value, int argc,
                      JSValueConst *argv)
{
    check_arguments(ctx, function, this_value, argc, argv);
    ++executions;
    return JS_NewInt32(ctx, 31);
}

JSValue JS_FrameRunCall(JSContext *ctx, JSValueConst function, JSValueConst this_value, int argc,
                        JSValueConst *argv)
{
    check_arguments(ctx, function, this_value, argc, argv);
    ++executions;
    return JS_NewInt32(ctx, 32);
}

/* The ordinary GNU profile aliases the run target to its public root selector. */
JSValue JS_FramePublicRootSelect(JSContext *ctx, JSValueConst function, JSValueConst this_value,
                                 int argc, JSValueConst *argv)
{
    return JS_FrameRunCall(ctx, function, this_value, argc, argv);
}

int main(void)
{
    memset(context_bytes, 0xff, sizeof(context_bytes));
    JSRuntime *rt = (JSRuntime *)runtime_bytes;
    memcpy(context_bytes + QJS_ABI_OFF_JSContext_rt, &rt, sizeof(rt));
    for (int i = 0; i < 3; ++i)
        arguments[i] = JS_NewInt32(NULL, 21 + i);
    for (int mode = 0; mode <= 2; ++mode) {
        runtime_bytes[QJS_ABI_OFF_JSRuntime_current_stack_frame - 1] = (unsigned char)mode;
        for (selected = 0; selected <= 1; ++selected) {
            resolutions = executions = 0;
            JSValue result = JS_Call((JSContext *)context_bytes, JS_NewInt32(NULL, 11),
                                     JS_NewInt32(NULL, 12), 3, arguments);
            assert(executions == 1);
            assert(resolutions == (mode == 2 ? 0 : 1));
            assert(JS_VALUE_GET_INT(result) == (mode != 2 && selected ? 32 : 31));
        }
    }
    puts("public entry: measured layout, cached disable, selector, arguments and result passed");
    return 0;
}
