#include "src/arm64/linux/interpreter-observe.h"
#include <assert.h>
#define main original_dense_pop_main
#include "../common/native_dense_pop_leaf.c"
#undef main
int main(void)
{
    unsigned cold = JS_FrameDensePopLeafState();
    assert(!cold);
    int result = original_dense_pop_main();
    assert(!result);
    uint64_t counts[8];
    qjs_aarch64_vm_c_entry_counts(counts);
    int enabled = !getenv("QJS_DISABLE_C_INVOKE") && !getenv("QJS_DISABLE_SHARED_ENTRY") &&
                  !getenv("QJS_DISABLE_DIRECT_HOST_CALL") && !getenv("QJS_RETAIN_SCOPED_HOST") &&
                  !getenv("QJS_DISABLE_REGISTER_INTERP") && !getenv("QJS_DISABLE_INTERP_FRAME") &&
                  !getenv("QJS_DISABLE_DENSE_ARRAY_POP") &&
                  !getenv("QJS_DISABLE_DENSE_ARRAY_POP_LEAF");
    fprintf(stderr, "DENSE_POP_OBSERVED cold=%u hits=%llu enabled=%d\n", cold,
            (unsigned long long)counts[5], enabled);
    /* Four warm pops plus200 stress pops;the first cold pop initializes the
     * original policy through its retained C body. The leaf must not run yet. */
    assert(counts[5] == (enabled ? 203u : 0u));
    printf("AARCH64_DENSE_POP_PATH_OK hits=%llu\n", (unsigned long long)counts[5]);
    return 0;
}
