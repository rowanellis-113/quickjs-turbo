/* SysV entry policy. Native leaves and activation constructors live in ELF.
 * Configuration cannot run JS, allocate engine objects or publish a frame. */
#include <stdatomic.h>
__attribute__((visibility("hidden"))) _Atomic unsigned char JS_LinuxEntryReady;
__attribute__((visibility("hidden"))) _Atomic unsigned char JS_LinuxRootControl;
__attribute__((visibility("hidden"))) _Atomic unsigned char JS_LinuxRootZeroControl;
__attribute__((visibility("hidden"))) _Atomic unsigned char JS_LinuxRootArgsControl;
__attribute__((visibility("hidden"))) _Atomic unsigned char JS_LinuxPublicRootControl;
__attribute__((visibility("hidden"))) _Atomic unsigned char JS_LinuxChildControl;
__attribute__((visibility("hidden"))) _Atomic unsigned char JS_FrameGetterLeafControl;

_Static_assert(sizeof(JSFrameRegisterState) == 168 && sizeof(JSFrame) == 128 &&
                   sizeof(JSFrameSegment) == 32 && sizeof(JSFrameSharedAnchor) == 24 &&
                   offsetof(JSFrameRegisterState, caller_ctx) == 136 &&
                   offsetof(JSFrameRegisterState, sites) == 144 &&
                   offsetof(JSFrameRegisterState, cache_next) == 152 &&
                   offsetof(JSRuntime, u) - offsetof(JSRuntime, module_loader_has_attr) == 8,
               "actual release SysV entry, frame, segment and policy padding");

static SHARED_INLINE void js_linux_entry_mode(_Atomic unsigned char *slot, const char *name)
{
    unsigned char expected = 0;
    unsigned char mode = getenv(name) ? 2 : 1;
    atomic_compare_exchange_strong_explicit(slot, &expected, mode, memory_order_relaxed,
                                            memory_order_relaxed);
}

SHARED_CODE void JS_LinuxEntryInit(JSContext *ctx)
{
    JSRuntime *rt = ctx->rt;
    js_linux_entry_mode(&JS_LinuxRootControl, "QJS_DISABLE_NATIVE_ROOT_ENTRY");
    js_linux_entry_mode(&JS_LinuxRootZeroControl, "QJS_DISABLE_NATIVE_ROOT_ZERO");
    js_linux_entry_mode(&JS_LinuxRootArgsControl, "QJS_DISABLE_NATIVE_ROOT_ARGS");
    js_linux_entry_mode(&JS_LinuxPublicRootControl, "QJS_DISABLE_PUBLIC_ROOT");
    js_linux_entry_mode(&JS_LinuxChildControl, "QJS_DISABLE_NATIVE_CHILD");
    if (!atomic_load_explicit(&JS_FrameGetterLeafControl, memory_order_relaxed)) {
        const char *value = getenv("QJS_DISABLE_THIS_FIELD_LEAF");
        unsigned char expected = 0, mode = value && value[0] != '0' ? 2 : 1;
        atomic_compare_exchange_strong_explicit(&JS_FrameGetterLeafControl, &expected, mode,
                                                memory_order_relaxed, memory_order_relaxed);
    }
    if (!((unsigned char *)rt)[offsetof(JSRuntime, module_loader_has_attr) + 1])
        ((unsigned char *)rt)[offsetof(JSRuntime, module_loader_has_attr) + 1] =
            getenv("QJS_DISABLE_NATIVE_CHILD_LEAF") ? 2 : 1;
    if (!((unsigned char *)rt)[offsetof(JSRuntime, current_stack_frame) - 4])
        ((unsigned char *)rt)[offsetof(JSRuntime, current_stack_frame) - 4] =
            getenv("QJS_DISABLE_DIRECT_HOST_CALL") ? 2 : 1;
    atomic_store_explicit(&JS_LinuxEntryReady, 1, memory_order_release);
}

/* The compiler owns TLS addressing for static, PIE and PIC consumers. */
SHARED_CODE JSFrameSharedAnchor **JS_LinuxEntrySlot(void)
{
    return js_frame_shared_slot();
}

SHARED_CODE int JS_LinuxEntryPoll(JSContext *ctx)
{
    return __js_poll_interrupts(ctx);
}

SHARED_CODE JSValue JS_LinuxEntryOverflow(JSContext *ctx)
{
    return JS_ThrowStackOverflow(ctx);
}

extern JSValue JS_FrameCallEntryDispatch(JSContext *, JSValueConst, JSValueConst, JSValueConst, int,
                                         JSValueConst *, int);
