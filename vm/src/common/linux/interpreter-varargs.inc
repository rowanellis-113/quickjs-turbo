/* Source-owned apply/spread algorithms compile against the actual core TU. */
#define FRAME_CODE __attribute__((section(".text.qjs_linux_varargs"), noipa))
#define FRAME_INLINE inline __attribute__((always_inline))
#include "src/common/call/interpreter-retained-context.inc"
_Static_assert(__builtin_types_compatible_p(__typeof__(&js_function_apply), JSCFunctionMagic *),
               "apply identity uses the actual original SysV magic function");
extern __typeof__(js_function_apply) qjs_linux_core_js_function_apply
    __attribute__((alias("js_function_apply"), visibility("hidden")));
_Static_assert(FRAME_ITERATOR_OFFSET == offsetof(JSFunctionBytecode, pc2line_len) +
                                            sizeof(((JSFunctionBytecode *)0)->pc2line_len) &&
                   FRAME_ITERATOR_OFFSET + 3 < offsetof(JSFunctionBytecode, pc2line_buf),
               "varargs controls use the common bytecode metadata owner");
