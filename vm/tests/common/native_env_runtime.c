/* Exercise both environment spellings through actual interpreter entry paths. */
#include "quickjs-interpreter-private.h"
#include "src/common/internal/interpreter-env.h"
#undef NDEBUG
#include <assert.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

extern int JS_FrameResolveCall(JSContext *ctx, const JSValue *func);
extern int JS_FrameResolveInternal(JSContext *ctx, const JSValue *func);

static int set_control(const char *key, const char *value)
{
#ifdef _WIN32
    return _putenv_s(key, value ? value : "");
#else
    return value ? setenv(key, value, 1) : unsetenv(key);
#endif
}

int main(int argc, char **argv)
{
    const char *controls[] = {
        "QJS_DISABLE_INTERP_FRAME",    "QJS_DISABLE_" QJS_INTERP_PREVIOUS_MARKER "_FRAME",
        "QJS_DISABLE_INTERNAL_INTERP", "QJS_DISABLE_INTERNAL_" QJS_INTERP_PREVIOUS_MARKER,
        "QJS_DISABLE_REGISTER_INTERP", "QJS_DISABLE_REGISTER_" QJS_INTERP_PREVIOUS_MARKER,
        "QJS_DISABLE_MIN_CALL_FRAME"};
    int selected, expected_entry = 1, expected_internal = 1, expected_register = 1;
    assert(argc == 2);
    selected = atoi(argv[1]);
    assert(selected >= -1 && selected < 6);
    for (size_t i = 0; i < sizeof(controls) / sizeof(controls[0]); i++)
        assert(set_control(controls[i], NULL) == 0);
    if (selected >= 0)
        assert(set_control(controls[selected], "0") == 0);
    if (selected == 0 || selected == 1) {
        expected_entry = 0;
        expected_internal = 0;
        expected_register = 0;
    } else if (selected == 2 || selected == 3) {
        expected_internal = 0;
    } else if (selected == 4 || selected == 5) {
        expected_register = 2;
    }

    JSRuntime *rt = JS_NewRuntime();
    assert(rt);
    JSContext *ctx = JS_NewContext(rt);
    assert(ctx);
    const char *source = "(function(x) { return x + 1; })";
    JSValue function = JS_Eval(ctx, source, strlen(source), "env-runtime.js", JS_EVAL_TYPE_GLOBAL);
    assert(!JS_IsException(function));
    assert(JS_FrameResolveCall(ctx, &function) == expected_entry);
    assert(JS_FrameResolveInternal(ctx, &function) == expected_internal);
    JSValue arg = JS_NewInt32(ctx, 4);
    JSValue result = JS_Call(ctx, function, JS_UNDEFINED, 1, &arg);
    int value;
    assert(!JS_IsException(result) && !JS_ToInt32(ctx, &value, result) && value == 5);
    const unsigned char *state =
        (const unsigned char *)rt + offsetof(JSRuntime, current_stack_frame);
    assert(state[-1] == (expected_entry ? 1 : 2));
    assert(state[-2] == (selected == 2 || selected == 3 ? 2 : 1));
    assert(state[-3] == expected_register);
    printf("ENV_RUNTIME_OK %d\n", selected);
    JS_FreeValue(ctx, result);
    JS_FreeValue(ctx, function);
    JS_FreeContext(ctx);
    JS_FreeRuntime(rt);
    return 0;
}
