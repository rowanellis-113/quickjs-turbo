.include "interpreter-private-abi-gas.inc"
.include "register-state.inc"
.intel_syntax noprefix
.section .qzrocl$readonlycallgate,"xr"
.p2align 4
.globl JS_FrameReadonlyCallGuard0, JS_FrameReadonlyCallGuard0_end
.def JS_FrameReadonlyCallGuard0; .scl 2; .type 32; .endef
JS_FrameReadonlyCallGuard0:
    cmp DWORD PTR [rip+JS_FrameReadonlyArgumentsControl],2
    je .Lrocall0_decline
    test BYTE PTR [r9+QJS_ABI_OFF_JSFunctionBytecode_byte_code_buf-1],17
    jnz .Lrocall0_decline
    mov eax,DWORD PTR [r9+QJS_ABI_OFF_JSFunctionBytecode_byte_code_len]
    lea r10d,[eax-1]
    cmp r10d,2047
    ja .Lrocall0_decline
    cmp BYTE PTR [rip+JS_FrameOwnBytecodeData],1
    jne .Lrocall0_decline
    mov r10,QWORD PTR [r9+QJS_ABI_OFF_JSFunctionBytecode_byte_code_buf]
    test r10b,3
    jnz .Lrocall0_decline
    add eax,3
    and eax,-4
    lea r10,[r10+rax*2]
    cmp BYTE PTR [r10],2
    je .Lrocall0_decline
    mov rax,rsp
    sub rax,QWORD PTR [rbx+32]
    jc .Lrocall0_decline
    sub rax,8192
    jc .Lrocall0_decline
    cmp rax,QWORD PTR [rbx+FRAME_STATE_NATIVE_LIMIT]
    jb .Lrocall0_decline
    mov DWORD PTR [rsp+60],ecx
    mov QWORD PTR [rbx],rbp
    mov QWORD PTR [rbx+16],r12
    mov QWORD PTR [rbx+24],r13
    mov eax,DWORD PTR [rsp+56]
    add rax,r12
    mov QWORD PTR [rbp+48],rax
    mov QWORD PTR [rbp+64],r13
    mov QWORD PTR [rbp+104],r13
    mov rax,QWORD PTR [rbx+56]
    mov QWORD PTR [rax+QJS_ABI_OFF_JSRuntime_current_stack_frame],rbp
    mov rcx,rbx
    call JS_FrameReadonlyCallTry
    test eax,eax
    jz .Lrocall0_restore
    cmp eax,1
    je interp_reload
    mov rbp,QWORD PTR [rbx]
    mov r12,QWORD PTR [rbx+16]
    mov r13,QWORD PTR [rbx+24]
    mov eax,1
    jmp interp_exit
.Lrocall0_restore:
    mov QWORD PTR [rbp+64],0
    mov ecx,DWORD PTR [rsp+60]
    mov r8,rcx
    shl r8,4
    neg r8
    add r8,r13
    mov rdx,QWORD PTR [r8-16]
    mov r9,QWORD PTR [rdx+QJS_ABI_OFF_JSObject_u_func_function_bytecode]
.Lrocall0_decline:
    movzx eax,BYTE PTR [r9+QJS_ABI_OFF_JSFunctionBytecode_byte_code_buf-1]
    and eax,21
    jmp JS_FrameCallLinkOldM_JS_FrameLeafGuard
JS_FrameReadonlyCallGuard0_end:
.p2align 4
.globl JS_FrameReadonlyCallGuard1, JS_FrameReadonlyCallGuard1_end
.def JS_FrameReadonlyCallGuard1; .scl 2; .type 32; .endef
JS_FrameReadonlyCallGuard1:
    cmp DWORD PTR [rip+JS_FrameReadonlyArgumentsControl],2
    je .Lrocall1_decline
    test BYTE PTR [r9+QJS_ABI_OFF_JSFunctionBytecode_byte_code_buf-1],17
    jnz .Lrocall1_decline
    mov eax,DWORD PTR [r9+QJS_ABI_OFF_JSFunctionBytecode_byte_code_len]
    lea r10d,[eax-1]
    cmp r10d,2047
    ja .Lrocall1_decline
    cmp BYTE PTR [rip+JS_FrameOwnBytecodeData],1
    jne .Lrocall1_decline
    mov r10,QWORD PTR [r9+QJS_ABI_OFF_JSFunctionBytecode_byte_code_buf]
    test r10b,3
    jnz .Lrocall1_decline
    add eax,3
    and eax,-4
    lea r10,[r10+rax*2]
    cmp BYTE PTR [r10],2
    je .Lrocall1_decline
    mov rax,rsp
    sub rax,QWORD PTR [rbx+32]
    jc .Lrocall1_decline
    sub rax,8192
    jc .Lrocall1_decline
    cmp rax,QWORD PTR [rbx+FRAME_STATE_NATIVE_LIMIT]
    jb .Lrocall1_decline
    mov DWORD PTR [rsp+60],ecx
    mov QWORD PTR [rbx],rbp
    mov QWORD PTR [rbx+16],r12
    mov QWORD PTR [rbx+24],r13
    mov eax,DWORD PTR [rsp+56]
    add rax,r12
    mov QWORD PTR [rbp+48],rax
    mov QWORD PTR [rbp+64],r13
    mov QWORD PTR [rbp+104],r13
    mov rax,QWORD PTR [rbx+56]
    mov QWORD PTR [rax+QJS_ABI_OFF_JSRuntime_current_stack_frame],rbp
    mov rcx,rbx
    call JS_FrameReadonlyCallTry
    test eax,eax
    jz .Lrocall1_restore
    cmp eax,1
    je interp_reload
    mov rbp,QWORD PTR [rbx]
    mov r12,QWORD PTR [rbx+16]
    mov r13,QWORD PTR [rbx+24]
    mov eax,1
    jmp interp_exit
.Lrocall1_restore:
    mov QWORD PTR [rbp+64],0
    mov ecx,DWORD PTR [rsp+60]
    mov r8,rcx
    shl r8,4
    neg r8
    add r8,r13
    mov rdx,QWORD PTR [r8-16]
    mov r9,QWORD PTR [rdx+QJS_ABI_OFF_JSObject_u_func_function_bytecode]
.Lrocall1_decline:
    movzx eax,BYTE PTR [r9+QJS_ABI_OFF_JSFunctionBytecode_byte_code_buf-1]
    and eax,21
    jmp JS_FrameLeafGuard
JS_FrameReadonlyCallGuard1_end:
.section .pdata$zzreadonlycall,"dr"
.p2align 2
.rva JS_FrameReadonlyCallGuard0, JS_FrameReadonlyCallGuard0_end, JS_FrameInterpPropertyCold_unwind
.rva JS_FrameReadonlyCallGuard1, JS_FrameReadonlyCallGuard1_end, JS_FrameInterpPropertyCold_unwind
