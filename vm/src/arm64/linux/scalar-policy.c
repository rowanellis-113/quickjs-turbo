/* Independent per-activation policy;no inherited core/inline initializer. MIT. */
#include "src/arm64/linux/interpreter-policy.h"
#include <stdatomic.h>
#include <stdlib.h>
#include <string.h>
static _Atomic unsigned scalar_mode __attribute__((section(".bss.qjs_aarch64_scalar")));
__attribute__((noipa, visibility("hidden"), section(".text.qjs_aarch64_scalar_policy"))) uint32_t
qjs_aarch64_vm_scalar_policy(void)
{
    uint32_t inherited = qjs_aarch64_vm_policy();
    unsigned m = atomic_load_explicit(&scalar_mode, memory_order_acquire);
    if (!m) {
        unsigned expected = 0;
        m = getenv("QJS_DISABLE_AARCH64_SCALAR_OPS") ? 2 : 1;
        if (!atomic_compare_exchange_strong_explicit(&scalar_mode, &expected, m,
                                                     memory_order_acq_rel, memory_order_acquire))
            m = expected;
    }
    return inherited | (m == 1 ? 65536u : 0u);
}
#ifdef QJS_AARCH64_VM_INSTRUMENT
__thread uint64_t qjs_aarch64_scalar_counters[22]
    __attribute__((visibility("hidden"), tls_model("local-exec")));
__attribute__((noipa, visibility("hidden"), section(".text.qjs_aarch64_scalar_policy"))) void
qjs_aarch64_vm_scalar_counts(uint64_t out[22])
{
    memcpy(out, qjs_aarch64_scalar_counters, sizeof(qjs_aarch64_scalar_counters));
}
#endif
