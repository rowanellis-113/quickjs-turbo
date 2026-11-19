/* Compile -S to bind every assembly bridge to actual public-header prototypes. */
#include "src/arm64/linux/abi/call-abi.h"
#define REF __attribute__((noinline, noclone))
REF JSValue reference_generic(JSCFunction *f, JSContext *c, JSValueConst v, int n, JSValueConst *a)
{
    return f(c, v, n, a);
}
REF JSValue reference_magic(JSCFunctionMagic *f, JSContext *c, JSValueConst v, int n,
                            JSValueConst *a, int m)
{
    return f(c, v, n, a, m);
}
REF JSValue reference_data(JSCFunctionData *f, JSContext *c, JSValueConst v, int n, JSValueConst *a,
                           int m, JSValueConst *d)
{
    return f(c, v, n, a, m, d);
}
REF double reference_float(__typeof__(((JSCFunctionType *)0)->f_f) f, double d)
{
    return f(d);
}
REF JSValue reference_stack(QJSAArch64CoreCall *f, JSContext *c, JSValueConst a, JSValueConst b,
                            JSValueConst n, int count, JSValueConst *v, int flags)
{
    return f(c, a, b, n, count, v, flags);
}
