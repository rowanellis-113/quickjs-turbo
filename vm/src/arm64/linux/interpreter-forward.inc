#include "interpreter-aarch64-values.h"
/* Actual AAPCS64 metadata and typed original builtin identity. MIT. */
_Static_assert(JS_CLASS_BYTECODE_FUNCTION == 13 && JS_CLASS_C_FUNCTION == 12 && JS_TAG_INT == 0 &&
                   JS_TAG_FIRST == -9 && JS_TAG_UNDEFINED == 3,
               "original forwarding function/value profile");
_Static_assert(sizeof(JSFrame) == 128 && sizeof(JSStackFrame) == 72 && sizeof(JSValue) == 16 &&
                   offsetof(JSFrame, sf) == 0 && offsetof(JSFrame, bytecode) == 80 &&
                   offsetof(JSFrame, this_value) == 88 && offsetof(JSFrame, saved_sp) == 104 &&
                   offsetof(JSFrame, segment) == 112 && offsetof(JSFrame, frame_bytes) == 120 &&
                   offsetof(JSFrame, owned_args) == 124 && offsetof(JSFrame, pending) == 126 &&
                   offsetof(JSFrameRegisterState, used_bytes) == 32 &&
                   offsetof(JSFrameRegisterState, rt) == 56 &&
                   offsetof(JSFrameRegisterState, native_stack_limit) == 72 &&
                   offsetof(JSFrameSegment, capacity) == 8 &&
                   offsetof(JSFrameSegment, used) == 16 && offsetof(JSFrameSegment, data) == 24 &&
                   offsetof(JSGCObjectHeader, ref_count) == 0,
               "measured AAPCS64 frame/segment/quota and inline refcount");
_Static_assert(__builtin_types_compatible_p(__typeof__(&js_function_call), JSCFunction *),
               "actual original generic builtin identity type");
extern __typeof__(js_function_call) qjs_aarch64_core_js_function_call
    __attribute__((alias("js_function_call"), visibility("hidden")));
__attribute__((visibility("hidden"),
               section(".data.qjs_arm_forward"))) unsigned char JS_FrameCallForwardNativeControl =
    255;
__attribute__((visibility("hidden"),
               section(".data.qjs_arm_forward"))) unsigned char JS_FrameCallForwardOwnedControl =
    255;
__attribute__((visibility("hidden"),
               section(".data.qjs_arm_forward"))) unsigned char JS_FrameCallForwardBorrowControl =
    255;
__attribute__((
    visibility("hidden"),
    section(".data.qjs_arm_forward"))) unsigned char JS_FrameCallForwardBorrowMissingControl = 255;
_Static_assert(FRAME_ITERATOR_OFFSET + 3 == ARM_FORWARD_MODE_OFFSET,
               "actual existing forward metadata byte");

/* Private noncalling AAPCS64 continuations; compiler derives actual types. */
typedef int QJSAArch64ForwardChild(JSFrameRegisterState *, JSFunctionBytecode *, JSValue *,
                                   unsigned);
extern QJSAArch64ForwardChild JS_AArch64ForwardOwnedTry;
extern QJSAArch64ForwardChild JS_AArch64ForwardBorrowTry;
extern QJSAArch64ForwardChild JS_AArch64ForwardBorrowMissingTry;
_Static_assert(sizeof(unsigned) == 4 && sizeof(void *) == 8 &&
                   sizeof(JSVarRef *) == ARM_VAR_REF_POINTER_BYTES,
               "private continuation integer/pointer contract");
_Static_assert(__builtin_types_compatible_p(__typeof__(&JS_AArch64ForwardOwnedTry),
                                            __typeof__(&JS_AArch64ForwardBorrowTry)) &&
                   __builtin_types_compatible_p(__typeof__(&JS_AArch64ForwardOwnedTry),
                                                __typeof__(&JS_AArch64ForwardBorrowMissingTry)),
               "same actual private continuation type");

extern QJSAArch64ForwardChild JS_AArch64CallPrepareOne;
extern int JS_AArch64CallPrepareDeep(JSFrameRegisterState *, JSObject *, JSValue *, unsigned);
extern int JS_AArch64CallPrepareExecute(JSFrameRegisterState *, JSFunctionBytecode *, JSValue *,
                                        unsigned, JSValueConst *, unsigned);
extern int JS_AArch64CallPrepareOwned(JSFrameRegisterState *);
extern int JS_AArch64CallPrepareFallback(JSFrameRegisterState *);
