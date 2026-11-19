.include "interpreter-private-abi-gas.inc"
.include "register-state.inc"
.intel_syntax noprefix
.section .qjzzpc,"xr"
.p2align 4
.globl JS_FrameArgumentsGuard, JS_FrameArgumentsGuard_end
.def JS_FrameArgumentsGuard; .scl 2; .type 32; .endef
JS_FrameArgumentsGuard:
    test BYTE PTR [rip+JS_FrameArgumentsMode], 2
    jnz args_vm_decline
    test BYTE PTR [r9+QJS_ABI_OFF_JSFunctionBytecode_byte_code_buf-1], 1
    jnz args_vm_decline
    cmp BYTE PTR [r9+QJS_ABI_OFF_JSFunctionBytecode_byte_code_buf-1], 2
    jne args_vm_unknown
    cmp BYTE PTR [r9+QJS_ABI_OFF_JSFunctionBytecode_pc2line_len+4], 128
    je JS_FrameArgumentsReady
    cmp BYTE PTR [r9+QJS_ABI_OFF_JSFunctionBytecode_pc2line_len+4], 64
    je args_vm_decline
args_vm_unknown:
    mov eax, DWORD PTR [r9+QJS_ABI_OFF_JSFunctionBytecode_byte_code_len]
    cmp eax, 2
    jb args_vm_negative
    cmp eax, 2048
    ja args_vm_negative
    cmp eax, 17
    jbe args_vm_size
    mov eax, 17
args_vm_size:
    mov r10, QWORD PTR [r9+QJS_ABI_OFF_JSFunctionBytecode_byte_code_buf]
    lea r11, [r10+rax]
args_vm_prefix:
    cmp r10, r11
    jae args_vm_negative
    cmp BYTE PTR [r10], 8
    je args_vm_this
    cmp BYTE PTR [r10], 12
    jne args_vm_negative
    inc r10
    cmp r10, r11
    jae args_vm_negative
    movzx eax, BYTE PTR [r10]
    cmp eax, 1
    jbe JS_FrameArgumentsCold
    cmp eax, 4
    ja args_vm_negative
    inc r10
    jmp args_vm_store
args_vm_this:
    inc r10
args_vm_store:
    cmp r10, r11
    jae args_vm_negative
    movzx eax, BYTE PTR [r10]
    cmp eax, 200
    je args_vm_local8
    sub eax, 207
    cmp eax, 3
    ja args_vm_negative
    inc r10
    jmp args_vm_prefix
args_vm_local8:
    add r10, 2
    jmp args_vm_prefix
args_vm_negative:
    cmp BYTE PTR [r9+QJS_ABI_OFF_JSFunctionBytecode_byte_code_buf-1], 2
    jne args_vm_decline
    mov BYTE PTR [r9+QJS_ABI_OFF_JSFunctionBytecode_pc2line_len+4], 64
    jmp args_vm_decline
args_vm_decline:
    movzx eax, BYTE PTR [r9+QJS_ABI_OFF_JSFunctionBytecode_byte_code_buf-1]
    and eax, 21
    jmp JS_FrameLeafGuard
JS_FrameArgumentsGuard_end:
.p2align 4
.globl JS_FrameArgumentsCold, JS_FrameArgumentsCold_end
.def JS_FrameArgumentsCold; .scl 2; .type 32; .endef
JS_FrameArgumentsCold:
    mov rax, rsp
    sub rax, QWORD PTR [rbx+32]
    jc args_cold_decline
    sub rax, 8192
    jc args_cold_decline
    cmp rax, QWORD PTR [rbx+FRAME_STATE_NATIVE_LIMIT]
    jb args_cold_decline
    mov DWORD PTR [rsp+60], ecx
    mov QWORD PTR [rbx], rbp
    mov QWORD PTR [rbx+16], r12
    mov QWORD PTR [rbx+24], r13
    mov eax, DWORD PTR [rsp+56]
    add rax, r12
    mov QWORD PTR [rbp+48], rax
    mov QWORD PTR [rbp+64], r13
    mov QWORD PTR [rbp+104], r13
    mov rax, QWORD PTR [rbx+56]
    mov QWORD PTR [rax+QJS_ABI_OFF_JSRuntime_current_stack_frame], rbp
    mov rcx, rbx
    call JS_FrameArgumentsTry
    test eax, eax
    jg JS_FrameNativeLifetimeResume
    js args_cold_exception
    mov QWORD PTR [rbp+64], 0
    mov ecx, DWORD PTR [rsp+60]
    mov r8, rcx
    shl r8, 4
    neg r8
    add r8, r13
    mov rdx, QWORD PTR [r8-16]
    mov r9, QWORD PTR [rdx+QJS_ABI_OFF_JSObject_u_func_function_bytecode]
args_cold_decline:
    movzx eax, BYTE PTR [r9+QJS_ABI_OFF_JSFunctionBytecode_byte_code_buf-1]
    and eax, 21
    jmp JS_FrameLeafGuard
args_cold_exception:
    mov rcx, rbx
    call JS_FrameSlowDirectSelect
    test eax, eax
    jz JS_FrameNativeLifetimeResume
    mov rbp, QWORD PTR [rbx]
    mov r12, QWORD PTR [rbx+16]
    mov r13, QWORD PTR [rbx+24]
    jmp interp_exit
JS_FrameArgumentsCold_end:
.p2align 4
.globl JS_FrameArgumentsOpClean, JS_FrameArgumentsOpClean_end
.def JS_FrameArgumentsOpClean; .scl 2; .type 32; .endef
JS_FrameArgumentsOpClean:
    mov rax, QWORD PTR [rbp+80]
    cmp BYTE PTR [rax+QJS_ABI_OFF_JSFunctionBytecode_byte_code_buf-1], 2
    jne JS_FrameNullProtoCold
    cmp BYTE PTR [rax+QJS_ABI_OFF_JSFunctionBytecode_pc2line_len+4], 128
    jne JS_FrameNullProtoCold
    mov QWORD PTR [rbx], rbp
    mov QWORD PTR [rbx+16], r12
    mov QWORD PTR [rbx+24], r13
    mov r10, QWORD PTR [rbx+56]
    mov QWORD PTR [r10+QJS_ABI_OFF_JSRuntime_current_stack_frame], rbp
    mov rcx, rbx
    call JS_FrameArgumentsStep
    test eax, eax
    jz JS_FrameNativeLifetimeResume
    mov rbp, QWORD PTR [rbx]
    mov r12, QWORD PTR [rbx+16]
    mov r13, QWORD PTR [rbx+24]
    jmp interp_exit
JS_FrameArgumentsOpClean_end:
.p2align 4
.globl JS_FrameArgumentsOpDirty, JS_FrameArgumentsOpDirty_end
.def JS_FrameArgumentsOpDirty; .scl 2; .type 32; .endef
JS_FrameArgumentsOpDirty:
    mov rax, QWORD PTR [rbp+80]
    cmp BYTE PTR [rax+QJS_ABI_OFF_JSFunctionBytecode_byte_code_buf-1], 2
    jne dirty_JS_FrameNullProtoCold
    cmp BYTE PTR [rax+QJS_ABI_OFF_JSFunctionBytecode_pc2line_len+4], 128
    jne dirty_JS_FrameNullProtoCold
    mov QWORD PTR [rbx], rbp
    mov QWORD PTR [rbx+16], r12
    mov QWORD PTR [rbx+24], r13
    mov r10, QWORD PTR [rbx+56]
    mov QWORD PTR [r10+QJS_ABI_OFF_JSRuntime_current_stack_frame], rbp
    mov rcx, rbx
    call JS_FrameArgumentsStep
    test eax, eax
    jz JS_FrameNativeLifetimeResume
    mov rbp, QWORD PTR [rbx]
    mov r12, QWORD PTR [rbx+16]
    mov r13, QWORD PTR [rbx+24]
    jmp interp_exit
JS_FrameArgumentsOpDirty_end:
.p2align 4
.globl JS_FrameArgumentsEntry, JS_FrameArgumentsEntry_end
.def JS_FrameArgumentsEntry; .scl 2; .type 32; .endef
JS_FrameArgumentsEntry:
    cmp QWORD PTR [r8+8], -1
    jne args_root_decline
    mov r11, QWORD PTR [r8]
    cmp WORD PTR [r11+QJS_ABI_OFF_JSObject_class_id], 13
    jne args_root_decline
    mov QWORD PTR [rsp+8], r9
    mov r9, QWORD PTR [r11+QJS_ABI_OFF_JSObject_u_func_function_bytecode]
    test BYTE PTR [rip+JS_FrameArgumentsMode], 2
    jnz args_root_restore
    test BYTE PTR [r9+QJS_ABI_OFF_JSFunctionBytecode_byte_code_buf-1], 1
    jnz args_root_restore
    cmp BYTE PTR [r9+QJS_ABI_OFF_JSFunctionBytecode_byte_code_buf-1], 2
    jne args_root_unknown
    cmp BYTE PTR [r9+QJS_ABI_OFF_JSFunctionBytecode_pc2line_len+4], 128
    je args_root_admit
    cmp BYTE PTR [r9+QJS_ABI_OFF_JSFunctionBytecode_pc2line_len+4], 64
    je args_root_restore
args_root_unknown:
    mov eax, DWORD PTR [r9+QJS_ABI_OFF_JSFunctionBytecode_byte_code_len]
    cmp eax, 2
    jb args_root_negative
    cmp eax, 2048
    ja args_root_negative
    cmp eax, 17
    jbe args_root_size
    mov eax, 17
args_root_size:
    mov r10, QWORD PTR [r9+QJS_ABI_OFF_JSFunctionBytecode_byte_code_buf]
    lea r11, [r10+rax]
args_root_prefix:
    cmp r10, r11
    jae args_root_negative
    cmp BYTE PTR [r10], 8
    je args_root_this
    cmp BYTE PTR [r10], 12
    jne args_root_negative
    inc r10
    cmp r10, r11
    jae args_root_negative
    movzx eax, BYTE PTR [r10]
    cmp eax, 1
    jbe args_root_admit
    cmp eax, 4
    ja args_root_negative
    inc r10
    jmp args_root_store
args_root_this:
    inc r10
args_root_store:
    cmp r10, r11
    jae args_root_negative
    movzx eax, BYTE PTR [r10]
    cmp eax, 200
    je args_root_local8
    sub eax, 207
    cmp eax, 3
    ja args_root_negative
    inc r10
    jmp args_root_prefix
args_root_local8:
    add r10, 2
    jmp args_root_prefix
args_root_negative:
    cmp BYTE PTR [r9+QJS_ABI_OFF_JSFunctionBytecode_byte_code_buf-1], 2
    jne args_root_restore
    mov BYTE PTR [r9+QJS_ABI_OFF_JSFunctionBytecode_pc2line_len+4], 64
    jmp args_root_restore
args_root_admit:
    mov r9, QWORD PTR [rsp+8]
    jmp JS_FrameArgumentsRootBridge
args_root_restore:
    mov r9, QWORD PTR [rsp+8]
args_root_decline:
    jmp JS_FrameCEntry
JS_FrameArgumentsEntry_end:
.p2align 4
.globl JS_FrameArgumentsReady, JS_FrameArgumentsReady_end
.def JS_FrameArgumentsReady; .scl 2; .type 32; .endef
JS_FrameArgumentsReady:
    test BYTE PTR [rip+JS_FrameArgumentsMode], 24
    jnz JS_FrameArgumentsCold
    movzx eax, BYTE PTR [r9+QJS_ABI_OFF_JSFunctionBytecode_byte_code_buf-3]
    cmp ecx, eax
    jb JS_FrameArgumentsCold
    movzx eax, WORD PTR [r9+QJS_ABI_OFF_JSFunctionBytecode_byte_code_buf-6]
    mov r11, QWORD PTR [rbx+8]
    mov r10, QWORD PTR [r11+16]
    add r10, rax
    cmp r10, QWORD PTR [r11+8]
    ja JS_FrameArgumentsCold
    mov r10, QWORD PTR [rbx+32]
    add r10, rax
    mov QWORD PTR [rsp+32], rax
    mov rax, rsp
    sub rax, r10
    mov r10, QWORD PTR [rbx+FRAME_STATE_NATIVE_LIMIT]
    cmp rax, r10
    jb JS_FrameArgumentsCold
    cmp DWORD PTR [rsi+QJS_ABI_OFF_JSContext_interrupt_counter], 1
    jle JS_FrameArgumentsCold
    dec DWORD PTR [rsi+QJS_ABI_OFF_JSContext_interrupt_counter]
    test BYTE PTR [rip+JS_FrameArgumentsMode], 4
    jz args_native_counted
    lock inc QWORD PTR [rip+JS_FrameArgumentsStats+16]
    lock inc QWORD PTR [rip+JS_FrameArgumentsStats+48]
args_native_counted:
    mov eax, DWORD PTR [rsp+56]
    add r12, rax
    mov QWORD PTR [rbp+48], r12
    mov QWORD PTR [rbp+104], r13
    mov eax, DWORD PTR [rsp+48]
    lea eax, [rax+rcx+1]
    or eax, DWORD PTR [rsp+52]
    mov WORD PTR [rbp+126], ax
    mov r10, QWORD PTR [r11+16]
    mov rax, QWORD PTR [r11+24]
    add rax, r10
    mov r10, QWORD PTR [rsp+32]
    mov DWORD PTR [rax+120], r10d
    add QWORD PTR [r11+16], r10
    add QWORD PTR [rbx+32], r10
    mov QWORD PTR [rax+112], r11
    mov QWORD PTR [rax], rbp
    mov QWORD PTR [rax+8], rdx
    mov QWORD PTR [rax+16], -1
    mov QWORD PTR [rax+80], r9
    mov QWORD PTR [rax+24], r8
    mov QWORD PTR [rax+128], r8
    mov DWORD PTR [rax+136], ecx
    mov DWORD PTR [rax+140], 0x41524746
    lea r14, [rax+144]
    mov QWORD PTR [rax+32], r14
    pxor xmm1, xmm1
    movq QWORD PTR [rax+40], xmm1
    movdqu XMMWORD PTR [rax+48], xmm1
    movdqu XMMWORD PTR [rax+64], xmm1
    mov DWORD PTR [rax+124], 0
    movzx edx, BYTE PTR [r9+QJS_ABI_OFF_JSFunctionBytecode_byte_code_buf-3]
    cmp edx, ecx
    cmovb edx, ecx
    mov WORD PTR [rax+58], dx
    movzx edx, BYTE PTR [r9+QJS_ABI_BIT_JSFunctionBytecode_is_strict_mode_BYTE]
    and edx, 1
    mov BYTE PTR [rax+60], dl
    movdqu xmm1, XMMWORD PTR [rdi+2048]
    movdqu XMMWORD PTR [rax+88], xmm1
    cmp DWORD PTR [rsp+48], 0
    je args_native_call_this_done
    movdqu xmm0, XMMWORD PTR [r8-32]
    movdqu XMMWORD PTR [rax+88], xmm0
args_native_call_this_done:
    mov rbp, rax
    mov r15, r8
.if QJS_FRAME_DIAGNOSTICS
/* The diagnostic VM publishes eagerly and keeps its selected clean table. */
    mov r10, QWORD PTR [rbx+56]
    mov QWORD PTR [r10+QJS_ABI_OFF_JSRuntime_current_stack_frame], rbp
.else
    lea rdi, [rip+JS_FramePublishDirtyTable]
.endif
    movzx ecx, BYTE PTR [r9+QJS_ABI_OFF_JSFunctionBytecode_byte_code_buf-4]
    mov r13, r14
    test ecx, ecx
    jz args_native_call_locals_done
args_native_call_locals_loop:
    movdqu XMMWORD PTR [r13], xmm1
    add r13, 16
    dec ecx
    jnz args_native_call_locals_loop
args_native_call_locals_done:
    cmp WORD PTR [r9+QJS_ABI_OFF_JSFunctionBytecode_var_ref_count], 0
    je args_native_call_refs_done
    movzx ecx, WORD PTR [r9+QJS_ABI_OFF_JSFunctionBytecode_var_ref_count]
    mov WORD PTR [rbp+56], cx
    movzx edx, WORD PTR [r9+QJS_ABI_OFF_JSFunctionBytecode_stack_size]
    shl rdx, 4
    lea r8, [r13+rdx]
    mov QWORD PTR [rbp+40], r8
args_native_call_refs_loop:
    mov QWORD PTR [r8], 0
    add r8, 8
    dec ecx
    jnz args_native_call_refs_loop
args_native_call_refs_done:
    mov r12, QWORD PTR [r9+QJS_ABI_OFF_JSFunctionBytecode_byte_code_buf]
    mov rsi, QWORD PTR [r9+QJS_ABI_OFF_JSFunctionBytecode_realm]
    movzx eax, BYTE PTR [r12]
    jmp QWORD PTR [rdi+rax*8]
JS_FrameArgumentsReady_end:
.p2align 2
arguments_vm_unwind:
.byte 33,0,0,0
.rva JS_FrameInterpUnscoped, JS_FrameInterp_end, JS_FrameInterp_unwind
arguments_leaf_unwind:
.byte 1,0,0,0
.section .pdata$zzzzzznullfast,"dr"
.p2align 2
.rva JS_FrameArgumentsGuard, JS_FrameArgumentsGuard_end, arguments_vm_unwind
.rva JS_FrameArgumentsCold, JS_FrameArgumentsCold_end, arguments_vm_unwind
.rva JS_FrameArgumentsOpClean, JS_FrameArgumentsOpClean_end, arguments_vm_unwind
.rva JS_FrameArgumentsOpDirty, JS_FrameArgumentsOpDirty_end, arguments_vm_unwind
.rva JS_FrameArgumentsEntry, JS_FrameArgumentsEntry_end, arguments_leaf_unwind
.rva JS_FrameArgumentsReady, JS_FrameArgumentsReady_end, arguments_vm_unwind
