/* Verify Darwin libunwind actually recovers caller IP/SP and saved registers
 * from interior PCs spanning the independent Mach-O __TEXT,__qjs_cvm bounds
 * of JS_CVMRunFastSegment (CFA = RSP + 72). */
#include <libunwind.h>
#include <mach-o/getsect.h>
#include <mach-o/ldsyms.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

extern void JS_CVMRunFastSegment(void *state) __attribute__((visibility("hidden")));

/* Exact prologue (8 pushes, 12B) and epilogue (8 pops + ret, 13B) bytes. */
static const uint8_t CVM_ENDBR64[] = {0xf3, 0x0f, 0x1e, 0xfa};
static const uint8_t CVM_PROLOGUE_BYTES[12] = {
    0x53, 0x55, 0x56, 0x57, 0x41, 0x54, 0x41, 0x55, 0x41, 0x56, 0x41, 0x57,
};
static const uint8_t CVM_EPILOGUE_BYTES[13] = {
    0x41, 0x5f, 0x41, 0x5e, 0x41, 0x5d, 0x41, 0x5c, 0x5f, 0x5e, 0x5d, 0x5b, 0xc3,
};

static __attribute__((noinline)) void cvm_unwind_dummy_caller(void)
{
    __asm__ volatile("" ::: "memory");
}

static void check_body_pc(unw_word_t body_pc, unw_word_t expected_start, unw_word_t expected_end,
                          unw_word_t caller_rip)
{
    /* Layout after JS_CVMRunFastSegment prologue (8 pushes above return addr):
     *   [rsp +  0] = r15  (CFA - 72)
     *   [rsp +  8] = r14  (CFA - 64)
     *   [rsp + 16] = r13  (CFA - 56)
     *   [rsp + 24] = r12  (CFA - 48)
     *   [rsp + 32] = rdi  (CFA - 40)
     *   [rsp + 40] = rsi  (CFA - 32)
     *   [rsp + 48] = rbp  (CFA - 24)
     *   [rsp + 56] = rbx  (CFA - 16)
     *   [rsp + 64] = rip  (CFA -  8)
     *   [rsp + 72] = caller rsp (CFA)
     */
    uint64_t frame[10];
    const uint64_t s_r15 = UINT64_C(0x1111222233334415);
    const uint64_t s_r14 = UINT64_C(0x1111222233334414);
    const uint64_t s_r13 = UINT64_C(0x1111222233334413);
    const uint64_t s_r12 = UINT64_C(0x1111222233334412);
    const uint64_t s_rdi = UINT64_C(0x1111222233334407);
    const uint64_t s_rsi = UINT64_C(0x1111222233334406);
    const uint64_t s_rbp = UINT64_C(0x1111222233334405);
    const uint64_t s_rbx = UINT64_C(0x1111222233334403);
    const uint64_t poison = UINT64_C(0xdeadbeefcafebabe);

    frame[0] = s_r15;
    frame[1] = s_r14;
    frame[2] = s_r13;
    frame[3] = s_r12;
    frame[4] = s_rdi;
    frame[5] = s_rsi;
    frame[6] = s_rbp;
    frame[7] = s_rbx;
    frame[8] = (uint64_t)caller_rip;
    frame[9] = 0;

    unw_context_t ctx;
    unw_cursor_t cur;
    unw_proc_info_t pi;
    unw_word_t reg = 0;

    if (unw_getcontext(&ctx) != 0 || unw_init_local(&cur, &ctx) != 0) {
        fprintf(stderr, "libunwind init failed\n");
        exit(1);
    }
    if (unw_set_reg(&cur, UNW_REG_IP, body_pc) != 0 ||
        unw_set_reg(&cur, UNW_REG_SP, (unw_word_t)(uintptr_t)&frame[0]) != 0 ||
        unw_set_reg(&cur, UNW_X86_64_RBX, poison) != 0 ||
        unw_set_reg(&cur, UNW_X86_64_RBP, poison) != 0 ||
        unw_set_reg(&cur, UNW_X86_64_RSI, poison) != 0 ||
        unw_set_reg(&cur, UNW_X86_64_RDI, poison) != 0 ||
        unw_set_reg(&cur, UNW_X86_64_R12, poison) != 0 ||
        unw_set_reg(&cur, UNW_X86_64_R13, poison) != 0 ||
        unw_set_reg(&cur, UNW_X86_64_R14, poison) != 0 ||
        unw_set_reg(&cur, UNW_X86_64_R15, poison) != 0) {
        fprintf(stderr, "libunwind set_reg failed\n");
        exit(1);
    }
    if (unw_get_proc_info(&cur, &pi) != 0) {
        fprintf(stderr, "unw_get_proc_info failed at pc=0x%llx\n", (unsigned long long)body_pc);
        exit(1);
    }
    if (pi.start_ip != expected_start || pi.end_ip != expected_end || body_pc < pi.start_ip ||
        body_pc >= pi.end_ip) {
        fprintf(stderr,
                "unexpected proc span [0x%llx..0x%llx), expected [0x%llx..0x%llx) pc=0x%llx\n",
                (unsigned long long)pi.start_ip, (unsigned long long)pi.end_ip,
                (unsigned long long)expected_start, (unsigned long long)expected_end,
                (unsigned long long)body_pc);
        exit(1);
    }
    int step_rc = unw_step(&cur);
    if (step_rc <= 0) {
        fprintf(stderr, "unw_step failed (%d) at pc=0x%llx\n", step_rc,
                (unsigned long long)body_pc);
        exit(1);
    }

    struct {
        int regnum;
        const char *name;
        uint64_t expected;
    } checks[] = {
        {UNW_REG_IP, "RIP", (uint64_t)caller_rip},
        {UNW_REG_SP, "RSP", (uint64_t)(uintptr_t)&frame[9]},
        {UNW_X86_64_RBX, "RBX", s_rbx},
        {UNW_X86_64_RBP, "RBP", s_rbp},
        {UNW_X86_64_RSI, "RSI", s_rsi},
        {UNW_X86_64_RDI, "RDI", s_rdi},
        {UNW_X86_64_R12, "R12", s_r12},
        {UNW_X86_64_R13, "R13", s_r13},
        {UNW_X86_64_R14, "R14", s_r14},
        {UNW_X86_64_R15, "R15", s_r15},
    };
    for (size_t i = 0; i < sizeof(checks) / sizeof(checks[0]); i++) {
        if (unw_get_reg(&cur, checks[i].regnum, &reg) != 0 || (uint64_t)reg != checks[i].expected) {
            fprintf(stderr, "unwind mismatch for %s at pc=0x%llx: got 0x%llx, expected 0x%llx\n",
                    checks[i].name, (unsigned long long)body_pc, (unsigned long long)reg,
                    (unsigned long long)checks[i].expected);
            exit(1);
        }
    }
}

int main(void)
{
    unw_context_t ctx;
    unw_cursor_t cur;
    unw_proc_info_t pi;
    unsigned long sec_size = 0;
    const uint8_t *sec_data = getsectiondata(&_mh_execute_header, "__TEXT", "__qjs_cvm", &sec_size);
    unw_word_t start_ip = (unw_word_t)(uintptr_t)&JS_CVMRunFastSegment;
    unw_word_t caller_rip = (unw_word_t)(uintptr_t)&cvm_unwind_dummy_caller;

    cvm_unwind_dummy_caller();
    if (!sec_data || sec_size < 128) {
        fprintf(stderr, "missing or invalid __TEXT,__qjs_cvm section (size=%lu)\n", sec_size);
        return 1;
    }
    unw_word_t sec_start = (unw_word_t)(uintptr_t)sec_data;
    unw_word_t sec_end = sec_start + (unw_word_t)sec_size;
    if (start_ip != sec_start) {
        fprintf(stderr, "JS_CVMRunFastSegment (0x%llx) != __TEXT,__qjs_cvm start (0x%llx)\n",
                (unsigned long long)start_ip, (unsigned long long)sec_start);
        return 1;
    }
    if (unw_getcontext(&ctx) != 0 || unw_init_local(&cur, &ctx) != 0 ||
        unw_set_reg(&cur, UNW_REG_IP, sec_start + 0x40) != 0 || unw_get_proc_info(&cur, &pi) != 0) {
        fprintf(stderr, "failed to locate JS_CVMRunFastSegment unwind info\n");
        return 1;
    }
    if (pi.start_ip != sec_start || pi.end_ip <= sec_start || pi.end_ip > sec_end) {
        fprintf(
            stderr,
            "invalid JS_CVMRunFastSegment proc info: [0x%llx..0x%llx) vs section [0x%llx..0x%llx)\n",
            (unsigned long long)pi.start_ip, (unsigned long long)pi.end_ip,
            (unsigned long long)sec_start, (unsigned long long)sec_end);
        return 1;
    }
    unw_word_t trailing = sec_end - pi.end_ip;
    if (trailing >= 16) {
        fprintf(stderr, "truncated JS_CVMRunFastSegment FDE: %llu of %lu bytes covered\n",
                (unsigned long long)(pi.end_ip - pi.start_ip), sec_size);
        return 1;
    }
    for (unw_word_t i = 0; i < trailing; i++) {
        uint8_t b = sec_data[(size_t)(pi.end_ip - sec_start + i)];
        if (b != 0x90 && b != 0x00) {
            fprintf(stderr, "non-padding byte 0x%02x after FDE end at +0x%llx\n", b,
                    (unsigned long long)i);
            return 1;
        }
    }

    unw_word_t fde_size = pi.end_ip - sec_start;
    size_t prefix_size =
        memcmp(sec_data, CVM_ENDBR64, sizeof(CVM_ENDBR64)) == 0 ? sizeof(CVM_ENDBR64) : 0;
    if (fde_size < prefix_size + sizeof(CVM_PROLOGUE_BYTES) + sizeof(CVM_EPILOGUE_BYTES) ||
        memcmp(sec_data + prefix_size, CVM_PROLOGUE_BYTES, sizeof(CVM_PROLOGUE_BYTES)) != 0 ||
        memcmp(sec_data + fde_size - sizeof(CVM_EPILOGUE_BYTES), CVM_EPILOGUE_BYTES,
               sizeof(CVM_EPILOGUE_BYTES)) != 0) {
        fprintf(stderr, "JS_CVMRunFastSegment machine-code prologue/epilogue mismatch\n");
        return 1;
    }

    /* CFA=RSP+72 applies after the eighth push until the first pop completes.
     * The non-signal cursor uses pc - 1, so probe the first and last covered bytes. */
    unw_word_t body_start = sec_start + prefix_size + sizeof(CVM_PROLOGUE_BYTES);
    unw_word_t body_end = pi.end_ip - sizeof(CVM_EPILOGUE_BYTES) + 2;
    unw_word_t pcs[3] = {
        body_start + 1,
        body_start + (body_end - body_start) / 2,
        body_end,
    };
    for (size_t i = 0; i < 3; i++)
        check_body_pc(pcs[i], sec_start, pi.end_ip, caller_rip);

    printf("MACOS_CVM_UNWIND_OK start=0x%llx section_size=%lu fde_size=%llu pcs=3\n",
           (unsigned long long)sec_start, sec_size, (unsigned long long)fde_size);
    return 0;
}
