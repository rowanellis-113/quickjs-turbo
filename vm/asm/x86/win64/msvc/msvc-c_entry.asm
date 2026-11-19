INCLUDE interpreter-private-abi-masm.inc
OPTION CASEMAP:NONE
OPTION DOTNAME
EXTERN __imp_getenv:BYTE
EXTERN qjs_frame_core_JS_CallInternal:PROC
EXTERN qjs_frame_core___js_poll_interrupts:PROC
EXTERN qjs_frame_core_js_call_c_function:PROC
.qjzzec SEGMENT ALIGN(16) 'CODE'
    ALIGN 16
PUBLIC JS_FrameCEntry, JS_FrameCEntry_end
JS_FrameCEntry PROC
    cmp QWORD PTR [r8+8], -1
    jne NEAR PTR JS_FrameCEntryDecline
    mov r11, QWORD PTR [r8]
    cmp WORD PTR [r11+QJS_ABI_OFF_JSObject_class_id], 12
    jne NEAR PTR JS_FrameCEntryDecline
    test DWORD PTR [rsp+64], -3
    jnz NEAR PTR JS_FrameCEntryDecline
    mov r10, QWORD PTR [rdx+QJS_ABI_OFF_JSContext_rt]
    cmp BYTE PTR [r10+QJS_ABI_OFF_JSRuntime_current_stack_frame-1], 2
    je NEAR PTR JS_FrameCEntryDecline
    cmp BYTE PTR [r10+QJS_ABI_OFF_JSRuntime_current_stack_frame-2], 2
    je NEAR PTR JS_FrameCEntryDecline
    cmp BYTE PTR [JS_FrameCEntryControl], 0
    je NEAR PTR JS_FrameCEntryConfig
    cmp BYTE PTR [JS_FrameCEntryControl], 1
    jne NEAR PTR JS_FrameCEntryDecline
    dec DWORD PTR [rdx+QJS_ABI_OFF_JSContext_interrupt_counter]
    jle NEAR PTR JS_FrameCEntryPoll
    jmp NEAR PTR JS_FrameCEntryCommit
JS_FrameCEntry_end LABEL BYTE
JS_FrameCEntry ENDP
    ALIGN 16
PUBLIC JS_FrameCEntryCommit, JS_FrameCEntryCommit_end
JS_FrameCEntryCommit PROC
    mov r10d, DWORD PTR [rsp+48]
    mov r11, QWORD PTR [rsp+56]
    mov eax, DWORD PTR [rsp+64]
    mov DWORD PTR [rsp+40], r10d
    mov QWORD PTR [rsp+48], r11
    mov DWORD PTR [rsp+56], eax
    jmp NEAR PTR qjs_frame_core_js_call_c_function
JS_FrameCEntryCommit_end LABEL BYTE
JS_FrameCEntryCommit ENDP
    ALIGN 16
PUBLIC JS_FrameCEntryDecline, JS_FrameCEntryDecline_end
JS_FrameCEntryDecline PROC
    jmp NEAR PTR qjs_frame_core_JS_CallInternal
JS_FrameCEntryDecline_end LABEL BYTE
JS_FrameCEntryDecline ENDP
    ALIGN 16
PUBLIC JS_FrameCEntryConfig, JS_FrameCEntryConfig_end
JS_FrameCEntryConfig PROC
    sub rsp, 72
    mov QWORD PTR [rsp+32], rcx
    mov QWORD PTR [rsp+40], rdx
    mov QWORD PTR [rsp+48], r8
    mov QWORD PTR [rsp+56], r9
    lea rcx, [JS_FrameCEntryDisable0]
    call QWORD PTR [__imp_getenv]
    test rax, rax
    jnz NEAR PTR c_entry_disabled
    lea rcx, [JS_FrameCEntryDisable1]
    call QWORD PTR [__imp_getenv]
    test rax, rax
    jnz NEAR PTR c_entry_disabled
    lea rcx, [JS_FrameCEntryDisable2]
    call QWORD PTR [__imp_getenv]
    test rax, rax
    jnz NEAR PTR c_entry_disabled
    lea rcx, [JS_FrameCEntryDisable3]
    call QWORD PTR [__imp_getenv]
    test rax, rax
    jnz NEAR PTR c_entry_disabled
    mov dl, 1
    jmp NEAR PTR c_entry_configured
PUBLIC c_entry_disabled
c_entry_disabled::
    mov dl, 2
PUBLIC c_entry_configured
c_entry_configured::
    xor eax, eax
    lock cmpxchg BYTE PTR [JS_FrameCEntryControl], dl
    mov rcx, QWORD PTR [rsp+32]
    mov rdx, QWORD PTR [rsp+40]
    mov r8, QWORD PTR [rsp+48]
    mov r9, QWORD PTR [rsp+56]
    add rsp, 72
JS_FrameCEntryConfig_end LABEL BYTE
JS_FrameCEntryConfig ENDP
PUBLIC JS_FrameCEntryConfigTail, JS_FrameCEntryConfigTail_end
JS_FrameCEntryConfigTail PROC
    jmp NEAR PTR JS_FrameCEntry
JS_FrameCEntryConfigTail_end LABEL BYTE
JS_FrameCEntryConfigTail ENDP
    ALIGN 16
PUBLIC JS_FrameCEntryPoll, JS_FrameCEntryPoll_end
JS_FrameCEntryPoll PROC
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
JS_FrameCEntryPoll_end LABEL BYTE
JS_FrameCEntryPoll ENDP
PUBLIC JS_FrameCEntryPollTail, JS_FrameCEntryPollTail_end
JS_FrameCEntryPollTail PROC
    test r10d, r10d
    jnz NEAR PTR JS_FrameCEntryException
    jmp NEAR PTR JS_FrameCEntryCommit
JS_FrameCEntryPollTail_end LABEL BYTE
JS_FrameCEntryPollTail ENDP
    ALIGN 16
PUBLIC JS_FrameCEntryException, JS_FrameCEntryException_end
JS_FrameCEntryException PROC
    mov QWORD PTR [rcx], 0
    mov QWORD PTR [rcx+8], 6
    mov rax, rcx
    ret
JS_FrameCEntryException_end LABEL BYTE
JS_FrameCEntryException ENDP
    ALIGN 4
PUBLIC JS_FrameCEntryC72Unwind
JS_FrameCEntryC72Unwind LABEL BYTE
    DB 1,4,1,0,4,130,0,0
    ALIGN 4
PUBLIC JS_FrameCEntryLeafUnwind
JS_FrameCEntryLeafUnwind LABEL BYTE
    DB 1,0,0,0
    ALIGN 4
PUBLIC JS_FrameCEntryDisable0
JS_FrameCEntryDisable0 LABEL BYTE
    DB 81,74,83,95,68,73,83,65,66,76,69,95,67,95,67,65,76,76,95,69,78,84,82,89,0
    ALIGN 4
PUBLIC JS_FrameCEntryDisable1
JS_FrameCEntryDisable1 LABEL BYTE
    DB 81,74,83,95,68,73,83,65,66,76,69,95,76,76,73,78,84,95,70,82,65,77,69,0
    ALIGN 4
PUBLIC JS_FrameCEntryDisable2
JS_FrameCEntryDisable2 LABEL BYTE
    DB 81,74,83,95,68,73,83,65,66,76,69,95,77,73,78,95,67,65,76,76,95,70,82,65,77,69,0
    ALIGN 4
PUBLIC JS_FrameCEntryDisable3
JS_FrameCEntryDisable3 LABEL BYTE
    DB 81,74,83,95,68,73,83,65,66,76,69,95,73,78,84,69,82,78,65,76,95,76,76,73,78,84,0
.qjzzec ENDS
.pdata$zzzzzznullfast SEGMENT ALIGN(4) READONLY 'DATA'
    DD IMAGEREL JS_FrameCEntry, IMAGEREL JS_FrameCEntry_end, IMAGEREL JS_FrameCEntryLeafUnwind
    DD IMAGEREL JS_FrameCEntryCommit, IMAGEREL JS_FrameCEntryCommit_end, IMAGEREL JS_FrameCEntryLeafUnwind
    DD IMAGEREL JS_FrameCEntryDecline, IMAGEREL JS_FrameCEntryDecline_end, IMAGEREL JS_FrameCEntryLeafUnwind
    DD IMAGEREL JS_FrameCEntryConfig, IMAGEREL JS_FrameCEntryConfig_end, IMAGEREL JS_FrameCEntryC72Unwind
    DD IMAGEREL JS_FrameCEntryConfigTail, IMAGEREL JS_FrameCEntryConfigTail_end, IMAGEREL JS_FrameCEntryLeafUnwind
    DD IMAGEREL JS_FrameCEntryPoll, IMAGEREL JS_FrameCEntryPoll_end, IMAGEREL JS_FrameCEntryC72Unwind
    DD IMAGEREL JS_FrameCEntryPollTail, IMAGEREL JS_FrameCEntryPollTail_end, IMAGEREL JS_FrameCEntryLeafUnwind
    DD IMAGEREL JS_FrameCEntryException, IMAGEREL JS_FrameCEntryException_end, IMAGEREL JS_FrameCEntryLeafUnwind
.pdata$zzzzzznullfast ENDS
.qjzzef$A SEGMENT ALIGN(4) READONLY 'CODE'
    DB 81,74,83,67,69,95,85,78,87,73,78,68,95,118,49,33,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0
.qjzzef$A ENDS
.qjzzef$Z SEGMENT ALIGN(4) READONLY 'CODE'
    DB 81,74,83,67,69,95,69,78,68,95,118,49,33,33,33,33,180,0,6,0,1,0,0,0
    DB 393396 DUP (0)
.qjzzef$Z ENDS
.qjzzom$ZCEntry SEGMENT ALIGN(8) 'DATA'
PUBLIC JS_FrameCEntryControl, JS_FrameCEntryHits, JS_FrameCEntryPollHits, JS_FrameCEntryDeclineHits
JS_FrameCEntryControl LABEL QWORD
    DQ 0
JS_FrameCEntryHits LABEL QWORD
    DQ 0
JS_FrameCEntryPollHits LABEL QWORD
    DQ 0
JS_FrameCEntryDeclineHits LABEL QWORD
    DQ 0
.qjzzom$ZCEntry ENDS
END
