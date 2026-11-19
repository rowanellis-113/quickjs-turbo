/* Private standard-C call boundary. This is not a register-VM entry contract. */
#ifndef QJS_AARCH64_CALL_ABI_H
#define QJS_AARCH64_CALL_ABI_H
#include "quickjs.h"
#include "qjs-aarch64-call-types.h"
#include "qjs-aarch64-abi-values.h"
#if !defined(__aarch64__) || !defined(__linux__) || !defined(__LP64__)
#error Linux AArch64 LP64 required
#endif
_Static_assert(sizeof(JSValue) == QJS_AARCH64_SIZE_JSValue, "Actual value ABI changed");
_Static_assert(_Alignof(JSValue) == QJS_AARCH64_ALIGN_JSValue, "Actual value alignment changed");
JSValue qjs_aarch64_call_generic(JSCFunction *, JSContext *, JSValueConst, int, JSValueConst *);
JSValue qjs_aarch64_call_magic(JSCFunctionMagic *, JSContext *, JSValueConst, int, JSValueConst *,
                               int);
JSValue qjs_aarch64_call_data(JSCFunctionData *, JSContext *, JSValueConst, int, JSValueConst *,
                              int, JSValueConst *);
double qjs_aarch64_call_double(__typeof__(((JSCFunctionType *)0)->f_f), double);
JSValue qjs_aarch64_call_internal(QJSAArch64CoreCall *, JSContext *, JSValueConst, JSValueConst,
                                  JSValueConst, int, JSValueConst *, int);
#endif
