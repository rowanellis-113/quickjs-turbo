/* Actual Linux native-forward ABI; all algorithms remain in shared owners. */
_Static_assert(JS_CLASS_BYTECODE_FUNCTION == 13 && JS_CLASS_C_FUNCTION == 12 && JS_TAG_INT == 0 &&
                   JS_TAG_FIRST == -9 && JS_TAG_UNDEFINED == 3,
               "Exact original class/value tags used by shared native probes");
_Static_assert(sizeof(JSFrame) == 128 && sizeof(JSStackFrame) == QJS_ABI_SIZE_JSStackFrame &&
                   sizeof(JSValue) == 16 && offsetof(JSFrame, sf) == 0 &&
                   offsetof(JSFrame, bytecode) == 80 && offsetof(JSFrame, this_value) == 88 &&
                   offsetof(JSFrame, saved_sp) == 104 && offsetof(JSFrame, segment) == 112 &&
                   offsetof(JSFrame, frame_bytes) == 120 && offsetof(JSFrame, owned_args) == 124 &&
                   offsetof(JSFrame, pending) == 126 &&
                   offsetof(JSFrameRegisterState, used_bytes) == 32 &&
                   offsetof(JSFrameRegisterState, rt) == 56 &&
                   offsetof(JSFrameRegisterState, native_stack_limit) == 72 &&
                   offsetof(JSFrameSegment, capacity) == 8 &&
                   offsetof(JSFrameSegment, used) == 16 && offsetof(JSFrameSegment, data) == 24 &&
                   (offsetof(JSMallocBlockHeader, user_data) -
                        offsetof(JSMallocBlockHeader, ref_count) ==
                    -QJS_ABI_REF_COUNT_OFFSET),
               "Measured SysV native-forward cells,quota and prefix refcount");
_Static_assert(__builtin_types_compatible_p(__typeof__(&js_function_call), JSCFunction *),
               "Forward identity is the actual original generic function");
extern __typeof__(js_function_call) qjs_linux_core_js_function_call
    __attribute__((alias("js_function_call"), visibility("hidden")));
__attribute__((visibility("hidden"),
               section(".data.qjs_linux_forward"))) unsigned char JS_FrameCallForwardNativeControl =
    255;
__attribute__((visibility("hidden"),
               section(".data.qjs_linux_forward"))) unsigned char JS_FrameCallForwardOwnedControl =
    255;
__attribute__((visibility("hidden"),
               section(".data.qjs_linux_forward"))) unsigned char JS_FrameCallForwardBorrowControl =
    255;
__attribute__((
    visibility("hidden"),
    section(".data.qjs_linux_forward"))) unsigned char JS_FrameCallForwardBorrowMissingControl =
    255;
