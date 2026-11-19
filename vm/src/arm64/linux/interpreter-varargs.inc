/* Actual C types and AAPCS64 scope for the unchanged complete apply owner. */
#define FRAME_CODE __attribute__((section(".text.qjs_arm_varargs"), noipa))
#define FRAME_INLINE inline __attribute__((always_inline))
#include "src/common/call/interpreter-retained-context.inc"
_Static_assert(__builtin_types_compatible_p(__typeof__(&js_function_apply), JSCFunctionMagic *),
               "apply intrinsic uses the actual original C function type");
extern __typeof__(js_function_apply) qjs_linux_core_js_function_apply;
_Static_assert(FRAME_ITERATOR_OFFSET == offsetof(JSFunctionBytecode, pc2line_len) +
                                            sizeof(((JSFunctionBytecode *)0)->pc2line_len) &&
                   FRAME_ITERATOR_OFFSET + 3 < offsetof(JSFunctionBytecode, pc2line_buf),
               "direct/fusion controls retain the common measured metadata owner");
