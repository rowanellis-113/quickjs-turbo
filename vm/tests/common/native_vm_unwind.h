/* Locate the fixed-register VM independently of its C activation wrapper.
 * This also works with an unwrapped legacy entry. Opcode kernels chain to
 * the raw register frame; its actual prologue must retain all eight saves. */
#ifndef QJS_FRAME_VM_UNWIND_TEST_H
#define QJS_FRAME_VM_UNWIND_TEST_H
#include <assert.h>
#include <stdint.h>
#include <string.h>
#include <windows.h>
extern void JS_FrameInterpPropertyCold(void);

static PRUNTIME_FUNCTION qjs_frame_test_raw_vm(DWORD64 *image_base)
{
    DWORD64 base = 0, parent_base = 0;
    PRUNTIME_FUNCTION cold =
        RtlLookupFunctionEntry((DWORD64)(uintptr_t)JS_FrameInterpPropertyCold, &base, NULL);
    assert(cold && base + cold->BeginAddress == (DWORD64)(uintptr_t)JS_FrameInterpPropertyCold);
    const unsigned char *info = (const unsigned char *)(uintptr_t)(base + cold->UnwindData);
    assert(info[0] == 0x21 && info[1] == 0 && info[2] == 0 && info[3] == 0);
    const RUNTIME_FUNCTION *chain = (const RUNTIME_FUNCTION *)(info + 4);
    PRUNTIME_FUNCTION raw = RtlLookupFunctionEntry(base + chain->BeginAddress, &parent_base, NULL);
    assert(raw && parent_base == base && !memcmp(raw, chain, sizeof(*raw)));
    static const unsigned char prologue[] = {0x53, 0x55, 0x56, 0x57, 0x41, 0x54, 0x41, 0x55,
                                             0x41, 0x56, 0x41, 0x57, 0x48, 0x83, 0xec, 0x48};
    assert(raw->EndAddress - raw->BeginAddress >= sizeof(prologue));
    assert(
        !memcmp((const void *)(uintptr_t)(base + raw->BeginAddress), prologue, sizeof(prologue)));
    *image_base = base;
    return raw;
}
#endif
