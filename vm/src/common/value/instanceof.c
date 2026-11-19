/* Guarded default instanceof intrinsic. The original VM step owns operands. */
#include "quickjs-interpreter-private.h"
#include <stdatomic.h>

static _Atomic unsigned char instance_mode;
static _Atomic unsigned long long instance_hits, instance_misses[7];

static void instance_report(void)
{
    printf("INSTANCEOF {\"hits\":%llu,\"misses\":[%llu,%llu,%llu,%llu,%llu,%llu,%llu]}\n",
           atomic_load_explicit(&instance_hits, memory_order_relaxed),
           atomic_load_explicit(&instance_misses[0], memory_order_relaxed),
           atomic_load_explicit(&instance_misses[1], memory_order_relaxed),
           atomic_load_explicit(&instance_misses[2], memory_order_relaxed),
           atomic_load_explicit(&instance_misses[3], memory_order_relaxed),
           atomic_load_explicit(&instance_misses[4], memory_order_relaxed),
           atomic_load_explicit(&instance_misses[5], memory_order_relaxed),
           atomic_load_explicit(&instance_misses[6], memory_order_relaxed));
}

static unsigned instance_config(void)
{
    unsigned char mode = atomic_load_explicit(&instance_mode, memory_order_relaxed);
    if (!mode) {
        unsigned char wanted = (getenv("QJS_DISABLE_FRAME_INSTANCEOF") ? 2 : 1) |
                               (getenv("QJS_OBSERVE_FRAME_INSTANCEOF") ? 4 : 0),
                      expected = 0;
        if (atomic_compare_exchange_strong_explicit(&instance_mode, &expected, wanted,
                                                    memory_order_relaxed, memory_order_relaxed)) {
            mode = wanted;
            if (mode & 4)
                atexit(instance_report);
        } else
            mode = expected;
    }
    return mode;
}

/* No allocating/reentrant operation occurs in the proof. The exact built-in
 * target is an added alias to the original function, not a name/arity guess.
 * Every observer, unsupported function and interrupt callback boundary keeps
 * the original complete algorithm. Bound every prototype walk.
 */
static int instance_try(JSContext *ctx, JSValueConst value, JSValueConst ctor, int *result)
{
    JSObject *function, *walk, *target, *method;
    JSShapeProperty *shape;
    JSProperty *property;
    unsigned depth;
    if (ctx->interrupt_counter <= 1)
        return 1;
    if (!JS_IsObject(ctor))
        return 2;
    function = JS_VALUE_GET_OBJ(ctor);
    if (function->class_id != JS_CLASS_BYTECODE_FUNCTION)
        return 2;
    walk = function;
    for (depth = 0; walk && depth < 16; depth++, walk = walk->shape->proto) {
        if (walk->class_id != JS_CLASS_OBJECT && walk->class_id != JS_CLASS_BYTECODE_FUNCTION &&
            walk->class_id != JS_CLASS_C_FUNCTION)
            return 3;
        shape = find_own_property(&property, walk, JS_ATOM_Symbol_hasInstance);
        if (shape)
            break;
    }
    if (!walk || depth == 16 || !shape || (shape->flags & JS_PROP_TMASK) ||
        !JS_IsObject(property->u.value))
        return 3;
    method = JS_VALUE_GET_OBJ(property->u.value);
    if (method->class_id != JS_CLASS_C_FUNCTION || method->u.cfunc.cproto != JS_CFUNC_generic ||
        method->u.cfunc.magic != 0 || method->u.cfunc.length != 1 ||
        method->u.cfunc.c_function.generic != js_function_hasInstance)
        return 3;
    if (!JS_IsObject(value)) {
        *result = 0;
    } else {
        shape = find_own_property(&property, function, JS_ATOM_prototype);
        if (!shape || (shape->flags & JS_PROP_TMASK) || !JS_IsObject(property->u.value))
            return 4;
        target = JS_VALUE_GET_OBJ(property->u.value);
        walk = JS_VALUE_GET_OBJ(value);
        for (depth = 0; depth < 32; depth++) {
            if (walk->class_id == JS_CLASS_PROXY)
                return 5;
            walk = walk->shape->proto;
            if (!walk) {
                *result = 0;
                break;
            }
            if (walk == target) {
                *result = 1;
                break;
            }
        }
        if (depth == 32)
            return 6;
    }
    /* The inherited JS_CallFree -> C built-in entry polls the caller context
     * once. No callback can run while the counter is >1; preserve that debit.
     */
    --ctx->interrupt_counter;
    return 0;
}

int JS_FrameInstanceOf(JSContext *ctx, JSValueConst value, JSValueConst ctor)
{
    unsigned mode = instance_config();
    int result, reason;
    if (mode & 1) {
        reason = instance_try(ctx, value, ctor, &result);
        if (!reason) {
            if (mode & 4)
                atomic_fetch_add_explicit(&instance_hits, 1, memory_order_relaxed);
            return result;
        }
        if (mode & 4)
            atomic_fetch_add_explicit(&instance_misses[reason], 1, memory_order_relaxed);
    }
    return JS_IsInstanceOf(ctx, value, ctor);
}
