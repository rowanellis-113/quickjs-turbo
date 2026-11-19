#if !defined(_WIN32) || !defined(__x86_64__)
#error "The frame entry requires the Windows x86-64 ABI"
#endif
#include "interpreter-private-abi-gas.inc"
/* Same standard Win64 ABI, stack discipline and tail transfers as MASM. */
.section .text$zzqjsentry,"xr"
.globl JS_Call
.def JS_Call; .scl 2; .type 32; .endef
.seh_proc JS_Call
JS_Call:
.seh_endprologue
    movq QJS_ABI_OFF_JSContext_rt(%rdx), %r10
/* FRAME_STATE is the padding byte immediately before current_stack_frame. */
    cmpb $2, QJS_ABI_OFF_JSRuntime_current_stack_frame-1(%r10)
    jne qjs_frame_select_entry
    jmp JS_LegacyCall
.seh_endproc

.globl qjs_frame_select_entry
.def qjs_frame_select_entry; .scl 2; .type 32; .endef
.seh_proc qjs_frame_select_entry
qjs_frame_select_entry:
    subq $72, %rsp
.seh_stackalloc 72
.seh_endprologue
    movq %rcx, 32(%rsp)
    movq %rdx, 40(%rsp)
    movq %r8, 48(%rsp)
    movq %r9, 56(%rsp)
    movq %rdx, %rcx
    movq %r8, %rdx
    call JS_FrameResolveCall
    movq 32(%rsp), %rcx
    movq 40(%rsp), %rdx
    movq 48(%rsp), %r8
    movq 56(%rsp), %r9
    testl %eax, %eax
    jz .Llegacy_tail
    addq $72, %rsp
    jmp *frame_run_target(%rip)
.Llegacy_tail:
    addq $72, %rsp
    jmp *frame_legacy_target(%rip)
.seh_endproc

.section .rdata$qjsfrm,"dr"
.p2align 3
frame_run_target:
.quad JS_FrameRunCall
frame_legacy_target:
.quad JS_LegacyCall
