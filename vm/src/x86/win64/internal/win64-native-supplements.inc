/* Source-level Windows x86-64 native ASM VM supplements.
 * Provides shared entry dispatch, CRT-portable getenv bridge for ASM islands,
 * and the decoupled native Property IC / own-bytecode tail controller. */
#include "src/common/internal/turbo-config.h"

SHARED_CODE JSValue JS_FrameCallEntryDispatch(JSContext *ctx, JSValueConst func,
                                              JSValueConst this_value, JSValueConst new_target,
                                              int argc, JSValueConst *argv, int flags)
{
    return JS_FrameCallEntryShared(ctx, func, this_value, new_target, argc, argv, flags);
}

/* CRT-portable getenv bridge (works identically under /MD, /MT, MSVC, clang-cl). */
const char *JS_FrameGetenv(const char *name)
{
    return getenv(name);
}

/* Source-level WIN_X86_64 declines varargs-construct specialization to the C slow path. */
int JS_FrameVarargsConstructCall(JSFrameRegisterState *state)
{
    (void)state;
    return -1;
}

/* Native Property IC & own-bytecode control block (80-byte ABI).
 * Byte 0: tail mode (1 = tail ON, 2 = OFF, 4 = PIC-only no tail)
 * Byte 5 (reserved[3]): PIC dispatch active (1 = native PIC ON, 2 = OFF) */
struct JSFrameOwnBytecodeState {
    unsigned char mode;
    unsigned char initialized;
    unsigned char reserved[6];
    uint64_t counts[9];
};

struct JSFrameOwnBytecodeState JS_FrameOwnBytecodeData = {0};

static void qjs_win64_own_bytecode_apply_mode(unsigned char mode)
{
    JS_FrameOwnBytecodeData.mode = mode;
    JS_FrameOwnBytecodeData.reserved[3] = (mode == 1 || mode == 4) ? 1 : 2;
    JS_FrameOwnBytecodeData.initialized = 1;
}

static void qjs_win64_own_bytecode_set_tail(int enabled)
{
#ifdef QJS_PROPERTY_IC
    /* Win64 source-level VM uses PIC-only mode (zero tail copy overhead) when
     * Property IC is enabled, regardless of tail toggle, unless PIC is disabled. */
    (void)enabled;
    int pic_disabled = (qjs_turbo_default_property_ic_mode() != 1);
    qjs_win64_own_bytecode_apply_mode(pic_disabled ? 2 : 4);
#else
    (void)enabled;
    qjs_win64_own_bytecode_apply_mode(2);
#endif
}

static int qjs_win64_own_bytecode_tail_active(void)
{
    return JS_FrameOwnBytecodeData.mode == 1 ? 1 : 0;
}

static void qjs_win64_own_bytecode_init(void)
{
    if (!JS_FrameOwnBytecodeData.initialized) {
#ifdef QJS_PROPERTY_IC
        int pic_disabled = (qjs_turbo_default_property_ic_mode() != 1);
        qjs_win64_own_bytecode_apply_mode(pic_disabled ? 2 : 4);
#else
        qjs_win64_own_bytecode_apply_mode(2);
#endif
    }
    qjs_turbo_register_own_bytecode_hooks(qjs_win64_own_bytecode_set_tail,
                                          qjs_win64_own_bytecode_tail_active);
}

#if defined(_MSC_VER)
#pragma section(".CRT$XCU", read)
__declspec(allocate(".CRT$XCU")) void (*const qjs_win64_own_bytecode_ctor)(void) =
    qjs_win64_own_bytecode_init;
#pragma comment(linker, "/include:qjs_win64_own_bytecode_ctor")
#else
__attribute__((constructor)) static void qjs_win64_own_bytecode_ctor(void)
{
    qjs_win64_own_bytecode_init();
}
#endif
