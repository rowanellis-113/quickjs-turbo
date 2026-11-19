#ifdef NDEBUG
#undef NDEBUG
#endif
/* ABI regression assertions must run in Release as well as Diagnostics. */
#ifdef NDEBUG
#undef NDEBUG
#endif
/* Validate asynchronous Win64 unwind through every prolog/epilog transition
 * of the fixed-register engine, including recovery of all nonvolatiles. */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <windows.h>
#include "tests/common/native_vm_unwind.h"
extern int JS_FrameInterp(void *);
extern void JS_FrameInterpPropertyCold(void);
extern void JS_FrameInterpPropertyCold_end(void);
extern void JS_FrameInterpShortBig(void);
extern void JS_FrameInterpShortBig_end(void);
#ifdef FRAME_TEST_GNU_STACK_INSERT
extern void JS_FramePublishDirty_FrameInterpShortBig(void);
extern void JS_FramePublishDirty_FrameInterpShortBig_end(void);
#endif
extern void JS_FrameInterpCallMeta(void);
extern void JS_FrameInterpCallMeta_end(void);
extern void JS_FrameInterpCallMeta_prepare(void);
extern void JS_FrameInterpCallMeta_init(void);

static void check(const unsigned char *start, PRUNTIME_FUNCTION fn, DWORD64 base, size_t offset,
                  ULONG64 *stack, int slot, int altered)
{
    CONTEXT c = {0};
    c.ContextFlags = CONTEXT_FULL;
    c.Rip = (DWORD64)(uintptr_t)(start + offset);
    c.Rsp = (DWORD64)(uintptr_t)(stack + slot);
    c.Rbx = altered ? 0 : 0xb001;
    c.Rbp = altered ? 0 : 0xb002;
    c.Rsi = altered ? 0 : 0xb003;
    c.Rdi = altered ? 0 : 0xb004;
    c.R12 = altered ? 0 : 0xb005;
    c.R13 = altered ? 0 : 0xb006;
    c.R14 = altered ? 0 : 0xb007;
    c.R15 = altered ? 0 : 0xb008;
    void *data = NULL;
    DWORD64 establisher = 0;
    RtlVirtualUnwind(UNW_FLAG_NHANDLER, base, c.Rip, fn, &c, &data, &establisher, NULL);
    assert(c.Rip == stack[17]);
    assert(c.Rsp == (DWORD64)(uintptr_t)(stack + 18));
    assert(c.Rbx == 0xb001 && c.Rbp == 0xb002 && c.Rsi == 0xb003 && c.Rdi == 0xb004);
    assert(c.R12 == 0xb005 && c.R13 == 0xb006 && c.R14 == 0xb007 && c.R15 == 0xb008);
}

/* Decode only the fixed native boundary's actual instruction starts. Checking
 * arbitrary bytes inside an x86 immediate would invent impossible contexts. */
static size_t cold_instruction_size(const unsigned char *p, size_t left)
{
    /* Exact GNU insert3 leaf forms; none writes RSP or a nonvolatile GP. */
    if (left >= 7 && p[0] == 0xf6 && p[1] == 0x05 && p[6] == 32)
        return 7;
    if (left >= 5 && p[0] == 0x41 && p[1] == 0x83 && p[2] == 0x7d && p[3] == 0xf8 && p[4] == 0)
        return 5;
    if (left >= 2 && p[0] == 0x79)
        return 2;
    if (left >= 4 && p[0] == 0x49 && p[1] == 0x8b && p[2] == 0x45 && p[3] == 0xf0)
        return 4;
    if (left >= 2 && p[0] == 0xff && p[1] == 0x00)
        return 2;
    if (left >= 6 && p[0] == 0xf3 && p[1] == 0x41 && p[2] == 0x0f &&
        ((p[3] == 0x6f &&
          ((p[4] == 0x45 && p[5] == 0xf0) || (p[4] == 0x4d && (p[5] == 0xe0 || p[5] == 0xd0)))) ||
         (p[3] == 0x7f && ((p[4] == 0x45 && (p[5] == 0 || p[5] == 0xd0)) ||
                           (p[4] == 0x4d && (p[5] == 0xf0 || p[5] == 0xe0))))))
        return 6;
    if (left >= 4 && p[0] == 0x49 && p[1] == 0x83 && p[2] == 0xc5 && p[3] == 16)
        return 4;
    /* Native check_ctor: exact byte62/kind3 comparison, no broad decode. */
    if (left >= 4 && p[0] == 0x80 && p[1] == 0x7d && p[2] == 62 && p[3] == 3)
        return 4;
    if (left >= 5 && (p[0] == 0xe8 || p[0] == 0xe9))
        return 5;
    if (left >= 2 && p[0] == 0xeb)
        return 2;
    if (left >= 6 && p[0] == 0x0f && (p[1] == 0x84 || p[1] == 0x85 || p[1] == 0x80))
        return 6;
    if (left >= 2 && p[0] == 0x74)
        return 2;
    if (left >= 2 && p[0] == 0x85 && p[1] == 0xc0)
        return 2;
    if (left >= 3 && p[0] == 0x48 && (p[1] == 0x89 || p[1] == 0x8b) &&
        (p[2] == 0x2b || p[2] == 0xd9 || p[2] == 0xcb))
        return 3;
    if (left >= 4 && p[0] == 0x4c && (p[1] == 0x89 || p[1] == 0x8b) &&
        (p[2] == 0x63 || p[2] == 0x6b) && (p[3] == 0x10 || p[3] == 0x18))
        return 4;
    if (left >= 4 && p[0] == 0x48 && p[1] == 0xff && p[2] == 0x43)
        return 4;
    if (left >= 7 && p[0] == 0x48 && p[1] == 0xff && p[2] == 0x83)
        return 7;
    if (left >= 5 && p[0] == 0x41 && p[1] == 0x83 && p[2] == 0x7d &&
        (p[3] == 0xe8 || p[3] == 0xf8) && p[4] == 7)
        return 5;
    if (left >= 4 && p[0] == 0x41 && (p[1] == 0x8b || p[1] == 0x03) && p[2] == 0x45 &&
        (p[3] == 0xe0 || p[3] == 0xf0))
        return 4;
    if (left >= 5 && p[0] == 0x41 && p[1] == 0x0f && p[2] == 0xaf && p[3] == 0x45 && p[4] == 0xf0)
        return 5;
    if (left >= 4 && p[0] == 0x49 && p[1] == 0x89 && p[2] == 0x45 && p[3] == 0xe0)
        return 4;
    if (left >= 4 && p[0] == 0x49 && p[1] == 0x83 &&
        ((p[2] == 0xed && p[3] == 16) || (p[2] == 0xc4 && p[3] == 1)))
        return 4;
    if (left >= 5 && p[0] == 0x41 && p[1] == 0x0f && p[2] == 0xb6 && p[3] == 0x04 && p[4] == 0x24)
        return 5;
    if (left >= 3 && p[0] == 0xff && p[1] == 0x24 && p[2] == 0xc7)
        return 3;
    fprintf(stderr, "Unexpected cold instruction: %02x %02x %02x, left=%zu\n", p[0], p[1], p[2],
            left);
    assert(!"Unexpected instruction in native cold boundary");
    return 0;
}

static int check_cold_unwind(PRUNTIME_FUNCTION primary, DWORD64 image_base, ULONG64 *stack,
                             const unsigned char *start, const unsigned char *end)
{
    DWORD64 base = 0;
    PRUNTIME_FUNCTION cold = RtlLookupFunctionEntry((DWORD64)(uintptr_t)start, &base, NULL);
    assert(cold && base == image_base && cold != primary && end > start);
    assert(base + cold->BeginAddress == (DWORD64)(uintptr_t)start);
    assert(base + cold->EndAddress == (DWORD64)(uintptr_t)end);
    const unsigned char *info = (const unsigned char *)(uintptr_t)(base + cold->UnwindData);
    assert(info[0] == 0x21 && !info[1] && !info[2] && !info[3]);
    assert(!memcmp(info + 4, primary, sizeof(*primary)));
    int count = 0;
    for (size_t at = 0; at < (size_t)(end - start);) {
        DWORD64 observed_base = 0;
        PRUNTIME_FUNCTION observed =
            RtlLookupFunctionEntry((DWORD64)(uintptr_t)(start + at), &observed_base, NULL);
        assert(observed == cold && observed_base == base);
        check(start, cold, base, at, stack, 0, 1);
        at += cold_instruction_size(start + at, (size_t)(end - start) - at);
        count++;
    }
    return count;
}

/* Keep the complete legacy branch and add the declared return-trampoline ABI.
 * No broad opcode skipping: every leaf instruction and branch is checked. */
static size_t check_native_exit(const unsigned char *start, PRUNTIME_FUNCTION fn, DWORD64 base,
                                size_t length, ULONG64 *stack)
{
    static const unsigned char legacy[] = {0x48, 0x83, 0xc4, 0x48, 0x41, 0x5f, 0x41, 0x5e, 0x41,
                                           0x5d, 0x41, 0x5c, 0x5f, 0x5e, 0x5d, 0x5b, 0xc3};
    assert(length >= sizeof(legacy));
    if (!memcmp(start + length - sizeof(legacy), legacy, sizeof(legacy)))
        return length - sizeof(legacy);
    assert(length >= 22);
    size_t exit = length - 22;
    assert(!memcmp(start + exit, legacy, 16));
    const unsigned char *jump = start + exit + 16;
    assert(jump[0] == 0xff && jump[1] == 0x25); /* allowed ModRM00 memory JMP */
    int32_t relative;
    memcpy(&relative, jump + 2, 4);
    const unsigned char *slot = jump + 6 + relative;
    const unsigned char *leaf;
    memcpy(&leaf, slot, sizeof(leaf));
    MEMORY_BASIC_INFORMATION protection;
    assert(VirtualQuery(slot, &protection, sizeof(protection)) == sizeof(protection));
    DWORD access = protection.Protect & 255;
    assert(access == PAGE_READONLY || access == PAGE_EXECUTE_READ);
    DWORD64 leaf_base = 0;
    PRUNTIME_FUNCTION leaf_fn = RtlLookupFunctionEntry((DWORD64)(uintptr_t)leaf, &leaf_base, NULL);
    assert(leaf_fn && leaf_base == base &&
           base + leaf_fn->BeginAddress == (DWORD64)(uintptr_t)leaf);
    assert(!memcmp((const void *)(uintptr_t)(base + leaf_fn->UnwindData), "\x01\0\0\0", 4));
    static const unsigned char prefix[] = {0x4c, 0x8b, 0x54, 0x24, 0x20, 0x4d, 0x85, 0xd2};
    static const unsigned char restore[] = {0x4c, 0x8b, 0x5c, 0x24, 0x08, 0x4d, 0x89, 0x1a, 0xc3};
    assert(!memcmp(leaf, prefix, sizeof(prefix)));
    size_t branch;
    int32_t skip;
    if (leaf[8] == 0x74) {
        branch = 2;
        skip = (int8_t)leaf[9];
    } else {
        assert(leaf[8] == 0x0f && leaf[9] == 0x84);
        branch = 6;
        memcpy(&skip, leaf + 10, 4);
    }
    assert(skip == 8 && !memcmp(leaf + 8 + branch, restore, sizeof(restore)));
    assert(leaf_fn->EndAddress - leaf_fn->BeginAddress == 8 + branch + sizeof(restore));
    const size_t points[] = {0, 5, 8, 8 + branch, 13 + branch, 16 + branch};
    for (unsigned i = 0; i < sizeof(points) / sizeof(points[0]); i++)
        check(leaf, leaf_fn, base, points[i], stack, 17, 0);
    puts(
        "register Interp: exact readonly return target, original-C leaf and all six leaf instruction contexts passed");
    return exit;
}

#ifdef FRAME_TEST_GNU_NUMBER_TRUTH
#define NUMBER_TRUTH_DECL(name)                                                                    \
    extern void JS_FrameTruth##name(void), JS_FrameTruth##name##_end(void)
NUMBER_TRUTH_DECL(LnotClean);
NUMBER_TRUTH_DECL(IfTrueClean);
NUMBER_TRUTH_DECL(IfFalseClean);
NUMBER_TRUTH_DECL(IfTrue8Clean);
NUMBER_TRUTH_DECL(IfFalse8Clean);
NUMBER_TRUTH_DECL(LnotDirty);
NUMBER_TRUTH_DECL(IfTrueDirty);
NUMBER_TRUTH_DECL(IfFalseDirty);
NUMBER_TRUTH_DECL(IfTrue8Dirty);
NUMBER_TRUTH_DECL(IfFalse8Dirty);
#undef NUMBER_TRUTH_DECL

/* Only the twelve precise leaf instructions are accepted; no general opcode
 * skipping. The unique suffix follows the original indirect dispatch. */
static size_t number_instruction_size(const unsigned char *p, size_t left)
{
    static const unsigned char cmp[] = {0x83, 0xf8, 0x08};
    static const unsigned char mode[] = {0xf7, 0xc2, 0, 0, 1, 0};
    static const unsigned char observe[] = {0xf7, 0xc2, 4, 0, 0, 0};
    static const unsigned char zero[] = {0x66, 0x0f, 0xef, 0xc0};
    static const unsigned char compare[] = {0x66, 0x41, 0x0f, 0x2e, 0x45, 0xf0};
    static const unsigned char set[] = {0x0f, 0x95, 0xc0};
    static const unsigned char extend[] = {0x0f, 0xb6, 0xc0};
    if (left >= 3 && !memcmp(p, cmp, 3))
        return 3;
    if (left >= 6 && p[0] == 0x0f && p[1] == 0x85)
        return 6;
    if (left >= 6 && (!memcmp(p, mode, 6) || !memcmp(p, observe, 6)))
        return 6;
    if (left >= 4 && !memcmp(p, zero, 4))
        return 4;
    if (left >= 6 && !memcmp(p, compare, 6))
        return 6;
    if (left >= 3 && (!memcmp(p, set, 3) || !memcmp(p, extend, 3)))
        return 3;
    if (left >= 2 && p[0] == 0x74 && p[1] == 8)
        return 2;
    if (left >= 8 && p[0] == 0xf0 && p[1] == 0x48 && p[2] == 0xff && p[3] == 5)
        return 8;
    if (left >= 2 && p[0] == 0xeb)
        return 2;
    if (left >= 5 && p[0] == 0xe9)
        return 5;
    assert(!"unreviewed Number truth leaf instruction");
    return 0;
}

static int check_number_truth_unwind(PRUNTIME_FUNCTION primary, DWORD64 image_base, ULONG64 *stack)
{
    struct NumberRange {
        void (*begin)(void), (*end)(void);
    } ranges[] = {
#define NUMBER_RANGE(name) {JS_FrameTruth##name, JS_FrameTruth##name##_end}
        NUMBER_RANGE(LnotClean),    NUMBER_RANGE(IfTrueClean),   NUMBER_RANGE(IfFalseClean),
        NUMBER_RANGE(IfTrue8Clean), NUMBER_RANGE(IfFalse8Clean), NUMBER_RANGE(LnotDirty),
        NUMBER_RANGE(IfTrueDirty),  NUMBER_RANGE(IfFalseDirty),  NUMBER_RANGE(IfTrue8Dirty),
        NUMBER_RANGE(IfFalse8Dirty)
#undef NUMBER_RANGE
    };
    static const unsigned char anchor[] = {0x41, 0x0f, 0xb6, 0x04, 0x24, 0xff, 0x24,
                                           0xc7, 0x83, 0xf8, 0x08, 0x0f, 0x85};
    int total = 0;
    for (unsigned n = 0; n < sizeof(ranges) / sizeof(ranges[0]); n++) {
        const unsigned char *start = (const unsigned char *)(uintptr_t)ranges[n].begin;
        const unsigned char *end = (const unsigned char *)(uintptr_t)ranges[n].end;
        DWORD64 base = 0;
        assert(end > start);
        PRUNTIME_FUNCTION fn = RtlLookupFunctionEntry((DWORD64)(uintptr_t)start, &base, NULL);
        assert(fn && fn != primary && base == image_base);
        assert(base + fn->BeginAddress == (DWORD64)(uintptr_t)start);
        assert(base + fn->EndAddress == (DWORD64)(uintptr_t)end);
        const unsigned char *info = (const unsigned char *)(uintptr_t)(base + fn->UnwindData);
        assert(!memcmp(info, "\x21\0\0\0", 4) && !memcmp(info + 4, primary, sizeof(*primary)));
        size_t length = (size_t)(end - start), begin = 0;
        unsigned matches = 0;
        for (size_t i = 0; i + sizeof(anchor) <= length; i++)
            if (!memcmp(start + i, anchor, sizeof(anchor))) {
                begin = i + 8;
                matches++;
            }
        assert(matches == 1 && begin < length);
        int count = 0;
        for (size_t at = begin; at < length;) {
            DWORD64 observed_base = 0;
            PRUNTIME_FUNCTION observed =
                RtlLookupFunctionEntry((DWORD64)(uintptr_t)(start + at), &observed_base, NULL);
            assert(observed == fn && observed_base == base);
            check(start, fn, base, at, stack, 0, 1);
            at += number_instruction_size(start + at, length - at);
            assert(at <= length);
            count++;
        }
        assert(count == 12);
        total += count;
    }
    assert(total == 120);
    return total;
}
#endif

int main(void)
{
    DWORD64 base = 0;
    PRUNTIME_FUNCTION fn = qjs_frame_test_raw_vm(&base);
    assert(fn);
    const unsigned char *start = (const unsigned char *)(uintptr_t)(base + fn->BeginAddress);
    size_t length = fn->EndAddress - fn->BeginAddress;
#ifdef _MSC_VER
    __declspec(align(16)) ULONG64 stack[32] = {0};
#else
    ULONG64 stack[32] __attribute__((aligned(16))) = {0};
#endif
    for (int i = 0; i < 8; i++)
        stack[16 - i] = 0xb001 + i;
    stack[17] = (ULONG64)(uintptr_t)main;
    const unsigned char prolog[] = {0x53, 0x55, 0x56, 0x57, 0x41, 0x54, 0x41, 0x55,
                                    0x41, 0x56, 0x41, 0x57, 0x48, 0x83, 0xec, 0x48};
    assert(!memcmp(start, prolog, sizeof(prolog)));
    const size_t offsets[] = {0, 1, 2, 3, 4, 6, 8, 10, 12, 16};
    for (int i = 0; i < 10; i++)
        check(start, fn, base, offsets[i], stack, i == 9 ? 0 : 17 - i, i == 9);
    size_t exit = check_native_exit(start, fn, base, length, stack);
    const size_t ends[] = {0, 4, 6, 8, 10, 12, 13, 14, 15, 16};
    for (int i = 0; i < 10; i++)
        check(start, fn, base, exit + ends[i], stack, i == 0 ? 0 : 8 + i, 0);
    printf("register Interp: %d cold instruction boundaries and chained unwind passed\n",
           check_cold_unwind(fn, base, stack,
                             (const unsigned char *)(uintptr_t)JS_FrameInterpPropertyCold,
                             (const unsigned char *)(uintptr_t)JS_FrameInterpPropertyCold_end));
    printf("register Interp: %d short BigInt instruction boundaries and chained unwind passed\n",
           check_cold_unwind(fn, base, stack,
                             (const unsigned char *)(uintptr_t)JS_FrameInterpShortBig,
                             (const unsigned char *)(uintptr_t)JS_FrameInterpShortBig_end));
#ifdef FRAME_TEST_GNU_STACK_INSERT
    printf(
        "register Interp: %d dirty insert3/short BigInt instruction boundaries and chained unwind passed\n",
        check_cold_unwind(
            fn, base, stack,
            (const unsigned char *)(uintptr_t)JS_FramePublishDirty_FrameInterpShortBig,
            (const unsigned char *)(uintptr_t)JS_FramePublishDirty_FrameInterpShortBig_end));
#endif
    const unsigned char *meta = (const unsigned char *)(uintptr_t)JS_FrameInterpCallMeta;
    const unsigned char *meta_end = (const unsigned char *)(uintptr_t)JS_FrameInterpCallMeta_end;
    DWORD64 meta_base = 0;
    PRUNTIME_FUNCTION meta_fn = RtlLookupFunctionEntry((DWORD64)(uintptr_t)meta, &meta_base, NULL);
    assert(meta_fn && meta_base == base && meta_fn != fn && meta_end > meta);
    assert(base + meta_fn->BeginAddress == (DWORD64)(uintptr_t)meta);
    assert(base + meta_fn->EndAddress == (DWORD64)(uintptr_t)meta_end);
    const unsigned char *meta_info = (const unsigned char *)(uintptr_t)(base + meta_fn->UnwindData);
    assert(!memcmp(meta_info, "\x21\0\0\0", 4) && !memcmp(meta_info + 4, fn, sizeof(*fn)));
    const unsigned char *meta_points[] = {
        meta, (const unsigned char *)(uintptr_t)JS_FrameInterpCallMeta_prepare,
        (const unsigned char *)(uintptr_t)JS_FrameInterpCallMeta_init};
    for (int i = 0; i < 3; i++) {
        assert(meta_points[i] >= meta && meta_points[i] < meta_end);
        check(meta, meta_fn, base, (size_t)(meta_points[i] - meta), stack, 0, 1);
    }
    puts("register Interp: call metadata entry/preparation/initialization chained unwind passed");
#ifdef FRAME_TEST_GNU_NUMBER_TRUTH
    printf("register Interp: %d Number truth instruction boundaries and chained unwind passed\n",
           check_number_truth_unwind(fn, base, stack));
#endif
    puts("register Interp: 20 unwind positions and all eight nonvolatile registers passed");
    return 0;
}
