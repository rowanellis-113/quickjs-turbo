/* Complete original numeric/view workload,then read actual component counts. */
#include "src/arm64/linux/interpreter-observe.h"
#define main original_c_entry_main
#include "../common/linux/native_linux_c_entry.c"
#undef main
int main(int argc, char **argv)
{
    int result = original_c_entry_main(argc, argv);
    assert(!result);
    uint64_t counts[8];
    qjs_aarch64_vm_c_entry_counts(counts);
    int enabled = !getenv("QJS_DISABLE_C_INVOKE") && !getenv("QJS_DISABLE_SHARED_ENTRY") &&
                  !getenv("QJS_DISABLE_DIRECT_HOST_CALL") && !getenv("QJS_RETAIN_SCOPED_HOST") &&
                  !getenv("QJS_DISABLE_REGISTER_INTERP") && !getenv("QJS_DISABLE_INTERP_FRAME");
    if (argc == 1) {
        if (!enabled)
            for (unsigned i = 0; i < 8; i++)
                assert(!counts[i]);
        else {
            if (!getenv("QJS_DISABLE_NATIVE_NUMERIC_INVOKE"))
                assert(counts[1] && !counts[2]);
            else if (!getenv("QJS_DISABLE_NUMERIC_TRAMPOLINE"))
                assert(counts[2] && !counts[1]);
            else
                assert(!counts[1] && !counts[2]);
            int views = !getenv("QJS_DISABLE_NATIVE_SLICE") &&
                        !getenv("QJS_DISABLE_NATIVE_CALL_LINK") &&
                        !getenv("QJS_DISABLE_NATIVE_VM_BRIDGE");
            if (views)
                assert(counts[3] + counts[4] + counts[7]);
            else
                assert(!counts[3] && !counts[4] && !counts[7]);
        }
    }
    for (unsigned i = 0; i < 8; i++)
        printf("AARCH64_C_ENTRY_KIND %u %llu\n", i, (unsigned long long)counts[i]);
    puts("AARCH64_C_ENTRY_COUNTS_OK");
    return 0;
}
