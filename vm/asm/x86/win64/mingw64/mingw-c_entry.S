.include "interpreter-private-abi-gas.inc"
.intel_syntax noprefix
.section .qjzzec,"xr"
.p2align 4
.globl JS_FrameCEntry, JS_FrameCEntry_end
.def JS_FrameCEntry; .scl 2; .type 32; .endef
JS_FrameCEntry:
    cmp QWORD PTR [r8+8], -1
    jne JS_FrameCEntryDecline
    mov r11, QWORD PTR [r8]
    cmp WORD PTR [r11+QJS_ABI_OFF_JSObject_class_id], 12
    jne JS_FrameCEntryDecline
    test DWORD PTR [rsp+64], -3
    jnz JS_FrameCEntryDecline
    mov r10, QWORD PTR [rdx+QJS_ABI_OFF_JSContext_rt]
    cmp BYTE PTR [r10+QJS_ABI_OFF_JSRuntime_current_stack_frame-1], 2
    je JS_FrameCEntryDecline
    cmp BYTE PTR [r10+QJS_ABI_OFF_JSRuntime_current_stack_frame-2], 2
    je JS_FrameCEntryDecline
    cmp BYTE PTR [rip+JS_FrameCEntryControl], 0
    je JS_FrameCEntryConfig
    cmp BYTE PTR [rip+JS_FrameCEntryControl], 1
    jne JS_FrameCEntryDecline
    dec DWORD PTR [rdx+QJS_ABI_OFF_JSContext_interrupt_counter]
    jle JS_FrameCEntryPoll
    jmp JS_FrameCEntryCommit
JS_FrameCEntry_end:
.p2align 4
.globl JS_FrameCEntryCommit, JS_FrameCEntryCommit_end
.def JS_FrameCEntryCommit; .scl 2; .type 32; .endef
JS_FrameCEntryCommit:
    mov r10d, DWORD PTR [rsp+48]
    mov r11, QWORD PTR [rsp+56]
    mov eax, DWORD PTR [rsp+64]
    mov DWORD PTR [rsp+40], r10d
    mov QWORD PTR [rsp+48], r11
    mov DWORD PTR [rsp+56], eax
    jmp qjs_frame_core_js_call_c_function
JS_FrameCEntryCommit_end:
.p2align 4
.globl JS_FrameCEntryDecline, JS_FrameCEntryDecline_end
.def JS_FrameCEntryDecline; .scl 2; .type 32; .endef
JS_FrameCEntryDecline:
    jmp qjs_frame_core_JS_CallInternal
JS_FrameCEntryDecline_end:
.p2align 4
.globl JS_FrameCEntryConfig, JS_FrameCEntryConfig_end
.def JS_FrameCEntryConfig; .scl 2; .type 32; .endef
JS_FrameCEntryConfig:
    sub rsp, 72
    mov QWORD PTR [rsp+32], rcx
    mov QWORD PTR [rsp+40], rdx
    mov QWORD PTR [rsp+48], r8
    mov QWORD PTR [rsp+56], r9
    lea rcx, [rip+JS_FrameCEntryDisable0]
    call QWORD PTR [rip+__imp_getenv]
    test rax, rax
    jnz c_entry_disabled
    lea rcx, [rip+JS_FrameCEntryDisable1]
    call QWORD PTR [rip+__imp_getenv]
    test rax, rax
    jnz c_entry_disabled
    lea rcx, [rip+JS_FrameCEntryDisable2]
    call QWORD PTR [rip+__imp_getenv]
    test rax, rax
    jnz c_entry_disabled
    lea rcx, [rip+JS_FrameCEntryDisable3]
    call QWORD PTR [rip+__imp_getenv]
    test rax, rax
    jnz c_entry_disabled
    mov dl, 1
    jmp c_entry_configured
c_entry_disabled:
    mov dl, 2
c_entry_configured:
    xor eax, eax
    lock cmpxchg BYTE PTR [rip+JS_FrameCEntryControl], dl
    mov rcx, QWORD PTR [rsp+32]
    mov rdx, QWORD PTR [rsp+40]
    mov r8, QWORD PTR [rsp+48]
    mov r9, QWORD PTR [rsp+56]
    add rsp, 72
JS_FrameCEntryConfig_end:
.globl JS_FrameCEntryConfigTail, JS_FrameCEntryConfigTail_end
.def JS_FrameCEntryConfigTail; .scl 2; .type 32; .endef
JS_FrameCEntryConfigTail:
    jmp JS_FrameCEntry
JS_FrameCEntryConfigTail_end:
.p2align 4
.globl JS_FrameCEntryPoll, JS_FrameCEntryPoll_end
.def JS_FrameCEntryPoll; .scl 2; .type 32; .endef
JS_FrameCEntryPoll:
    sub rsp, 72
    mov QWORD PTR [rsp+32], rcx
    mov QWORD PTR [rsp+40], rdx
    mov QWORD PTR [rsp+48], r8
    mov QWORD PTR [rsp+56], r9
    mov rcx, rdx
    call qjs_frame_core___js_poll_interrupts
    mov DWORD PTR [rsp+64], eax
    mov rcx, QWORD PTR [rsp+32]
    mov rdx, QWORD PTR [rsp+40]
    mov r8, QWORD PTR [rsp+48]
    mov r9, QWORD PTR [rsp+56]
    mov r10d, DWORD PTR [rsp+64]
    add rsp, 72
JS_FrameCEntryPoll_end:
.globl JS_FrameCEntryPollTail, JS_FrameCEntryPollTail_end
.def JS_FrameCEntryPollTail; .scl 2; .type 32; .endef
JS_FrameCEntryPollTail:
    test r10d, r10d
    jnz JS_FrameCEntryException
    jmp JS_FrameCEntryCommit
JS_FrameCEntryPollTail_end:
.p2align 4
.globl JS_FrameCEntryException, JS_FrameCEntryException_end
.def JS_FrameCEntryException; .scl 2; .type 32; .endef
JS_FrameCEntryException:
    mov QWORD PTR [rcx], 0
    mov QWORD PTR [rcx+8], 6
    mov rax, rcx
    ret
JS_FrameCEntryException_end:
.p2align 2
.globl JS_FrameCEntryC72Unwind
JS_FrameCEntryC72Unwind:
.byte 1,4,1,0,4,130,0,0
.p2align 2
.globl JS_FrameCEntryLeafUnwind
JS_FrameCEntryLeafUnwind:
.byte 1,0,0,0
.p2align 2
.globl JS_FrameCEntryDisable0
JS_FrameCEntryDisable0:
.byte 81,74,83,95,68,73,83,65,66,76,69,95,67,95,67,65,76,76,95,69,78,84,82,89,0
.p2align 2
.globl JS_FrameCEntryDisable1
JS_FrameCEntryDisable1:
.byte 81,74,83,95,68,73,83,65,66,76,69,95,76,76,73,78,84,95,70,82,65,77,69,0
.p2align 2
.globl JS_FrameCEntryDisable2
JS_FrameCEntryDisable2:
.byte 81,74,83,95,68,73,83,65,66,76,69,95,77,73,78,95,67,65,76,76,95,70,82,65,77,69,0
.p2align 2
.globl JS_FrameCEntryDisable3
JS_FrameCEntryDisable3:
.byte 81,74,83,95,68,73,83,65,66,76,69,95,73,78,84,69,82,78,65,76,95,76,76,73,78,84,0
.section .pdata$zzzzzznullfast,"dr"
.p2align 2
.rva JS_FrameCEntry, JS_FrameCEntry_end, JS_FrameCEntryLeafUnwind
.rva JS_FrameCEntryCommit, JS_FrameCEntryCommit_end, JS_FrameCEntryLeafUnwind
.rva JS_FrameCEntryDecline, JS_FrameCEntryDecline_end, JS_FrameCEntryLeafUnwind
.rva JS_FrameCEntryConfig, JS_FrameCEntryConfig_end, JS_FrameCEntryC72Unwind
.rva JS_FrameCEntryConfigTail, JS_FrameCEntryConfigTail_end, JS_FrameCEntryLeafUnwind
.rva JS_FrameCEntryPoll, JS_FrameCEntryPoll_end, JS_FrameCEntryC72Unwind
.rva JS_FrameCEntryPollTail, JS_FrameCEntryPollTail_end, JS_FrameCEntryLeafUnwind
.rva JS_FrameCEntryException, JS_FrameCEntryException_end, JS_FrameCEntryLeafUnwind
.section .qjzzef$A,"xr"
.p2align 2
.byte 81,74,83,67,69,95,85,78,87,73,78,68,95,118,49,33,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0
.section .qjzzef$Z,"xr"
.p2align 2
.byte 81,74,83,67,69,95,69,78,68,95,118,49,33,33,33,33,20,1,6,0,1,0,0,0
.zero 393492
.section .qjzzom$ZCEntry,"dw"
.p2align 3
.globl JS_FrameCEntryControl, JS_FrameCEntryHits, JS_FrameCEntryPollHits, JS_FrameCEntryDeclineHits
JS_FrameCEntryControl:
.quad 0
JS_FrameCEntryHits:
.quad 0
JS_FrameCEntryPollHits:
.quad 0
JS_FrameCEntryDeclineHits:
.quad 0
