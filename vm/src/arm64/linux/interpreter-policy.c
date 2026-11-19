#include "interpreter-policy.h"
#include <stdatomic.h>
#include <stdlib.h>
static _Atomic uint32_t policy;
__attribute__((visibility("hidden"), noipa)) uint32_t qjs_aarch64_vm_policy(void)
{
    uint32_t value = atomic_load_explicit(&policy, memory_order_acquire);
    if (!value) {
        uint32_t desired = 0x80000000;
        if (!getenv("QJS_DISABLE_NATIVE_SLOT_STORE"))
            desired |= ARM_POLICY_SLOT_STORE;
        if (!getenv("QJS_DISABLE_FRAME_TRUTHINESS"))
            desired |= ARM_POLICY_TRUTH;
        if (!getenv("QJS_DISABLE_FRAME_NUMBER_TRUTH"))
            desired |= ARM_POLICY_NUMBER_TRUTH;
        if (!getenv("QJS_DISABLE_AARCH64_CAPTURED_REFS"))
            desired |= ARM_POLICY_CAPTURED_REFS;
        if (!getenv("QJS_DISABLE_AARCH64_OWNED_ARGS"))
            desired |= ARM_POLICY_OWNED_ARGS;
        if (!getenv("QJS_DISABLE_AARCH64_CLASS_HOST"))
            desired |= ARM_POLICY_CLASS_HOST;
        if (!getenv("QJS_DISABLE_AARCH64_MISSING_WINDOW"))
            desired |= ARM_POLICY_MISSING_WINDOW;
        if (!getenv("QJS_DISABLE_AARCH64_CAPTURED_ENTRY"))
            desired |= ARM_POLICY_CAPTURED_ENTRY;
        if (!getenv("QJS_DISABLE_AARCH64_OWNED_MISSING"))
            desired |= ARM_POLICY_OWNED_MISSING;
        if (!getenv("QJS_DISABLE_DEFERRED_FRAME_PUBLISH"))
            desired |= ARM_POLICY_DEFERRED_PUBLICATION;
        if (!getenv("QJS_DISABLE_AARCH64_HOST_RETURN"))
            desired |= ARM_POLICY_HOST_RETURN;
        if (!getenv("QJS_DISABLE_AARCH64_PROPERTY_IC"))
            desired |= ARM_POLICY_PROPERTY_IC;
        if (!getenv("QJS_DISABLE_PROTO_LOAD_CACHE"))
            desired |= ARM_POLICY_STRING_PROTO;
        if (!getenv("QJS_DISABLE_AARCH64_PROPERTY_PRIMITIVES"))
            desired |= ARM_POLICY_PROPERTY_PRIMITIVES;
        if (!getenv("QJS_DISABLE_AARCH64_PROPERTY_PROTOTYPES"))
            desired |= ARM_POLICY_PROPERTY_PROTOTYPES;
        if (!getenv("QJS_DISABLE_AARCH64_PROPERTY_STORES"))
            desired |= ARM_POLICY_GENERIC_PROPERTY_STORE;
        if (atomic_compare_exchange_strong_explicit(&policy, &value, desired, memory_order_acq_rel,
                                                    memory_order_acquire))
            value = desired;
    }
    return value;
}
