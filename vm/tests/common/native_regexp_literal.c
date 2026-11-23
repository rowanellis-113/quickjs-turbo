/* MIT. Private literal format, export, interrupt and callback lifetime checks. */
#include "quickjs.h"
#include "cutils.h"
#include "src/common/regexp/libregexp.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
#include <windows.h>
#endif
#ifdef NDEBUG
#error Literal fixture requires active assertions.
#endif

enum {
#define DEF(id, size) OP_##id,
#include "src/common/regexp/libregexp-opcode.h"
#undef DEF
};
static unsigned checks, interrupts;

static uint8_t *compile(JSContext *ctx, const char *pattern, int flags, int *length)
{
    char error[128];
    uint8_t *code = lre_compile(length, error, sizeof(error), pattern, strlen(pattern), flags, ctx);
    assert(code && !error[0] && *length > 24 && code[19] == OP_literal_hint);
    assert(!lre_prepare_bytecode(code, *length, true));
    return code;
}

static void raw_cases(JSContext *ctx)
{
    int length;
    uint8_t *code = compile(ctx, "ab", 0, &length);
    uint8_t *capture[32], *copy = malloc(length);
    const uint8_t bytes[] = "zzabxab";
    const uint16_t units[] = {0x4e2d, 'a', 'b', 'a', 'b'};
    assert(copy);
    assert(lre_exec(capture, code, bytes, 0, 7, 0, ctx) == 1);
    assert(capture[0] == bytes + 2 && capture[1] == bytes + 4);
    assert(lre_exec(capture, code, bytes, 3, 7, 0, ctx) == 1);
    assert(capture[0] == bytes + 5 && capture[1] == bytes + 7);
    assert(lre_exec(capture, code, (const uint8_t *)units, 0, 5, 1, ctx) == 1);
    assert(capture[0] == (const uint8_t *)(units + 1));
    assert(capture[1] == (const uint8_t *)(units + 3));
    checks += 3;
    for (unsigned mutation = 0; mutation < 10; mutation++) {
        memcpy(copy, code, length);
        switch (mutation) {
        case 0:
            put_u16(copy + 20, 0);
            break;
        case 1:
            put_u16(copy + 20, 3);
            break;
        case 2:
            copy[22] = 1;
            break;
        case 3:
            copy[23] = 0;
            break;
        case 4:
            copy[26] = OP_any;
            break;
        case 5:
            copy[0] |= LRE_FLAG_IGNORECASE;
            break;
        case 6:
            copy[2] = 2;
            break;
        case 7:
            copy[3] = 1;
            break;
        case 8:
            put_u32(copy + 9, 5);
            break;
        case 9:
            copy[length - 1] = OP_any;
            break;
        }
        assert(lre_prepare_bytecode(copy, length, true) == -1);
        checks++;
    }
    memcpy(copy, code, length);
    assert(!lre_prepare_bytecode(copy, length, false));
    assert(copy[19] == OP_goto && !get_u32(copy + 20));
    assert(!lre_prepare_bytecode(copy, length, true));
    assert(lre_exec(capture, copy, bytes, 0, 7, 0, ctx) == 1);
    assert(capture[0] == bytes + 2 && capture[1] == bytes + 4);
    checks++;
#ifdef _WIN32
    SYSTEM_INFO info;
    GetSystemInfo(&info);
    SIZE_T page = info.dwPageSize;
    uint8_t *pages = VirtualAlloc(NULL, page * 2, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
    DWORD previous;
    assert(pages && VirtualProtect(pages + page, page, PAGE_NOACCESS, &previous));
    for (int truncated = 20; truncated < length; truncated++) {
        uint8_t *bad = pages + page - truncated;
        memcpy(bad, code, truncated);
        put_u32(bad + 4, truncated - 8);
        assert(lre_prepare_bytecode(bad, truncated, true) == -1);
        if (truncated >= 24)
            assert(lre_exec(capture, bad, bytes, 0, 7, 0, ctx) == LRE_RET_BYTECODE_ERROR);
        checks++;
    }
    uint8_t *edge = pages + page - 2;
    edge[0] = 'a';
    edge[1] = 'b';
    assert(lre_exec(capture, code, edge, 0, 2, 0, ctx) == 1);
    assert(lre_exec(capture, code, edge + 1, 0, 1, 0, ctx) == 0);
    checks += 2;
    uint8_t *odd = pages + page - 3;
    odd[0] = 'a';
    odd[1] = 'b';
    assert(lre_exec(capture, code, odd, 0, 2, 0, ctx) == 1);
    assert(capture[0] == odd && capture[1] == odd + 2);
    checks++;
    assert(VirtualFree(pages, 0, MEM_RELEASE));
#endif
    free(copy);
    js_free(ctx, code);
}

static void wire(JSContext *ctx, JSRuntime *runtime)
{
    const char source[] = "/ab/dg.exec('zzab')";
    JSValue fn = JS_Eval(ctx, source, strlen(source), "literal-wire",
                         JS_EVAL_TYPE_GLOBAL | JS_EVAL_FLAG_COMPILE_ONLY);
    assert(!JS_IsException(fn));
    size_t length;
    uint8_t *data = JS_WriteObject(ctx, &length, fn, JS_WRITE_OBJ_BYTECODE);
    JSContext *other = JS_NewContext(runtime);
    assert(data && length && other);
    JSValue imported = JS_ReadObject(other, data, length, JS_READ_OBJ_BYTECODE);
    assert(!JS_IsException(imported));
    JSValue result = JS_EvalFunction(other, imported);
    assert(!JS_IsException(result) && JS_IsObject(result));
    JSValue index = JS_GetPropertyStr(other, result, "index");
    int32_t value;
    assert(!JS_ToInt32(other, &value, index) && value == 2);
    JS_FreeValue(other, index);
    JS_FreeValue(other, result);
    JS_FreeContext(other);
    js_free(ctx, data);
    JS_FreeValue(ctx, fn);
    checks++;
}

static int stop(JSContext *ctx, void *opaque)
{
    (void)ctx;
    (void)opaque;
    interrupts++;
    return 1;
}

typedef struct {
    JSContext *ctx;
    uint8_t *code, *inner;
    int length, entered;
} Reentry;

static int reenter(JSContext *ctx, void *opaque)
{
    JSRuntime *runtime = JS_GetRuntime(ctx);
    Reentry *state = opaque;
    if (state->entered++)
        return 0;
    const uint8_t input[] = "Q";
    uint8_t *capture[32];
    JS_RunGC(runtime);
    assert(lre_exec(capture, state->inner, input, 0, 1, 0, state->ctx) == 1);
    assert(capture[0] == input && capture[1] == input + 1);
    /* Raw caller owns the code. The outer execution must already have copied
     * its bounded literal before the first observable timeout callback. */
    memset(state->code, 0, state->length);
    return 0;
}

static void callbacks(JSContext *ctx, JSRuntime *runtime)
{
    int length;
    uint8_t *code = compile(ctx, "ab", 0, &length);
    uint8_t *input = malloc(100002), *capture[32];
    uint16_t *wide = malloc(100002 * sizeof(*wide));
    assert(input && wide);
    memset(input, 'z', 100002);
    for (unsigned i = 0; i < 100002; i++)
        wide[i] = 'z';
    JS_SetInterruptHandler(runtime, stop, NULL);
    assert(lre_exec(capture, code, input, 0, 100002, 0, ctx) == LRE_RET_TIMEOUT);
    assert(lre_exec(capture, code, (const uint8_t *)wide, 0, 100002, 1, ctx) == LRE_RET_TIMEOUT);
    assert(interrupts == 2);
    JS_SetInterruptHandler(runtime, NULL, NULL);
    int inner_length;
    Reentry state = {ctx, code, compile(ctx, "Q", 0, &inner_length), length, 0};
    input[100000] = 'a';
    input[100001] = 'b';
    JS_SetInterruptHandler(runtime, reenter, &state);
    assert(lre_exec(capture, code, input, 0, 100002, 0, ctx) == 1);
    assert(state.entered && capture[0] == input + 100000 && capture[1] == input + 100002);
    JS_SetInterruptHandler(runtime, NULL, NULL);
    js_free(ctx, state.inner);
    js_free(ctx, code);
    free(input);
    free(wide);
    checks += 3;
}

int main(void)
{
    JSRuntime *runtime = JS_NewRuntime();
    assert(runtime);
    JSContext *ctx = JS_NewContext(runtime);
    assert(ctx);
    raw_cases(ctx);
    wire(ctx, runtime);
    callbacks(ctx, runtime);
    JS_FreeValue(ctx, JS_GetException(ctx));
    JS_RunGC(runtime);
    JS_FreeContext(ctx);
    JS_FreeRuntime(runtime);
    printf("REGEXP_LITERAL_RAW_OK %u interrupt=%u\n", checks, interrupts);
    return 0;
}
