; Public JS_Call ABI: RCX=result buffer, RDX=ctx, R8=&func, R9=&this.
; The incoming stack has argc at +40 and argv at +48. Leave both untouched.
; The C selector returns before either executor runs, even on the first call.
OPTION CASEMAP:NONE
OPTION DOTNAME
INCLUDE interpreter-private-abi-masm.inc
EXTERN JS_LegacyCall:PROC
EXTERN JS_FrameRunCall:PROC
EXTERN JS_FrameResolveCall:PROC

.text$zzqjsentry SEGMENT ALIGN(16) 'CODE'
PUBLIC JS_Call
JS_Call PROC
    mov r10, QWORD PTR [rdx+QJS_ABI_OFF_JSContext_rt]
; FRAME_STATE is the padding byte immediately before current_stack_frame.
    cmp BYTE PTR [r10+QJS_ABI_OFF_JSRuntime_current_stack_frame-1], 2
    jne qjs_frame_select_entry
    jmp JS_LegacyCall
JS_Call ENDP

PUBLIC qjs_frame_select_entry
qjs_frame_select_entry PROC FRAME
    sub rsp, 72
.allocstack 72
.endprolog
; 32-byte outgoing home space, followed by the four incoming registers.
    mov QWORD PTR [rsp+32], rcx
    mov QWORD PTR [rsp+40], rdx
    mov QWORD PTR [rsp+48], r8
    mov QWORD PTR [rsp+56], r9
    mov rcx, rdx
    mov rdx, r8
    call JS_FrameResolveCall
    mov rcx, QWORD PTR [rsp+32]
    mov rdx, QWORD PTR [rsp+40]
    mov r8, QWORD PTR [rsp+48]
    mov r9, QWORD PTR [rsp+56]
    test eax, eax
    jz legacy_tail
    add rsp, 72
; RIP-relative memory tail jumps have the permitted epilog ModRM form.
    jmp QWORD PTR [frame_run_target]
legacy_tail:
    add rsp, 72
    jmp QWORD PTR [frame_legacy_target]
qjs_frame_select_entry ENDP
.text$zzqjsentry ENDS

.rdata$qjsfrm SEGMENT ALIGN(8) READONLY 'CONST'
frame_run_target DQ JS_FrameRunCall
frame_legacy_target DQ JS_LegacyCall
.rdata$qjsfrm ENDS
END
