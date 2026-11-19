.include "interpreter-private-abi-gas.inc"
.include "register-state.inc"
.intel_syntax noprefix
.section .qjzzpc,"xr"
.p2align 4
.globl JS_FrameOrdinaryLiteralOpClean, JS_FrameOrdinaryLiteralOpClean_end
.def JS_FrameOrdinaryLiteralOpClean; .scl 2; .type 32; .endef
JS_FrameOrdinaryLiteralOpClean:
    cmp BYTE PTR [rbx+FRAME_STATE_LITERAL_ACTIVE], 4
    je ordinary_lazy_Clean_active
    cmp BYTE PTR [rbx+FRAME_STATE_LITERAL_LAZY], 1
    jne interp_slow
    cmp DWORD PTR [rbx+FRAME_STATE_ITERATOR_DEPTH], 0
    jne interp_slow
    cmp BYTE PTR [r12], 75
    jne ordinary_vm_Clean_cold
    test DWORD PTR [rip+JS_FrameOrdinaryLiteralMode], 1024
    jz interp_slow
    jmp ordinary_vm_Clean_cold
ordinary_lazy_Clean_active:
    cmp DWORD PTR [rbx+FRAME_STATE_ITERATOR_DEPTH], 0
    jne interp_slow
    cmp BYTE PTR [r12], 75
    jne ordinary_vm_Clean_cold
    cmp BYTE PTR [rbx+FRAME_STATE_EXCEPTION], 0
    jne ordinary_vm_Clean_cold
    mov edx, DWORD PTR [rip+JS_FrameOrdinaryLiteralMode]
    test edx, 1
    jz ordinary_vm_Clean_cold
    test edx, 138
    jnz ordinary_vm_Clean_cold
    cmp QWORD PTR [r13-24], -1
    jne ordinary_vm_Clean_cold
    mov r8, QWORD PTR [r13-32]
    cmp WORD PTR [r8+QJS_ABI_OFF_JSObject_class_id], 1
    jne ordinary_vm_Clean_cold
.if QJS_ABI_HAS_PREFIX_RC
    movzx eax, BYTE PTR [r8+16]
    and eax, 11
    cmp eax, 2
    jne ordinary_vm_Clean_cold
.else
    test BYTE PTR [r8+QJS_ABI_BIT_JSObject_is_prototype_BYTE], QJS_ABI_BIT_JSObject_is_prototype_MASK
    jnz ordinary_vm_Clean_cold
    movzx eax, BYTE PTR [r8+QJS_ABI_BIT_JSObject_extensible_BYTE]
    and eax, QJS_ABI_BIT_JSObject_extensible_MASK | QJS_ABI_BIT_JSObject_is_exotic_MASK
    cmp eax, QJS_ABI_BIT_JSObject_extensible_MASK
    jne ordinary_vm_Clean_cold
.endif
    mov r9, QWORD PTR [r8+QJS_ABI_OFF_JSObject_shape]
    cmp BYTE PTR [r9+QJS_ABI_OFF_JSShape_is_hashed], 0
    je ordinary_vm_Clean_cold
    cmp DWORD PTR [r9+QJS_ABI_OFF_JSShape_deleted_prop_count], 0
    jne ordinary_vm_Clean_cold
    mov eax, DWORD PTR [r9+QJS_ABI_OFF_JSShape_prop_count]
    cmp eax, DWORD PTR [r9+QJS_ABI_OFF_JSShape_prop_size]
    jae ordinary_vm_Clean_cold
    test edx, 2048
    jz ordinary_vm_Clean_spare_capacity
    cmp DWORD PTR [r9+QJS_ABI_OFF_JSShape_prop_size], 2
    jne ordinary_vm_Clean_cold
ordinary_vm_Clean_spare_capacity:
    mov rcx, QWORD PTR [rbx+FRAME_STATE_CACHE_NEXT]
    test rcx, rcx
    jz ordinary_vm_Clean_cold
ordinary_vm_Clean_hash:
    mov rax, r12
    mov r10, r12
    shr r10, 5
    xor rax, r10
    mov r10, r12
    shr r10, 11
    xor rax, r10
    and eax, 63
    mov rax, QWORD PTR [rcx+rax*8+336]
    mov r10, QWORD PTR [rbp+80]
ordinary_vm_Clean_loop:
    test rax, rax
    jz ordinary_vm_Clean_cold
    cmp QWORD PTR [rax], r12
    jne ordinary_vm_Clean_next
    cmp QWORD PTR [rax+8], r10
    je ordinary_vm_Clean_found
ordinary_vm_Clean_next:
    mov rax, QWORD PTR [rax+40]
    jmp ordinary_vm_Clean_loop
ordinary_vm_Clean_found:
    cmp QWORD PTR [rax+16], r9
    jne ordinary_vm_Clean_cold
    mov r10d, DWORD PTR [r12+1]
    cmp DWORD PTR [rax+32], r10d
    jne ordinary_vm_Clean_cold
    mov r10, QWORD PTR [rax+24]
    test r10, r10
    jz ordinary_vm_Clean_cold
    cmp BYTE PTR [r10+QJS_ABI_OFF_JSShape_is_hashed], 0
    je ordinary_vm_Clean_cold
    mov r11d, DWORD PTR [r9+QJS_ABI_OFF_JSShape_prop_count]
    cmp DWORD PTR [rax+36], r11d
    jne ordinary_vm_Clean_cold
    inc r11d
    cmp DWORD PTR [r10+QJS_ABI_OFF_JSShape_prop_count], r11d
    jne ordinary_vm_Clean_cold
    mov r11d, DWORD PTR [r9+QJS_ABI_OFF_JSShape_prop_size]
    cmp DWORD PTR [r10+QJS_ABI_OFF_JSShape_prop_size], r11d
    jne ordinary_vm_Clean_cold
    inc DWORD PTR [r10+QJS_ABI_REF_COUNT_OFFSET]
    mov QWORD PTR [r8+QJS_ABI_OFF_JSObject_shape], r10
    mov r11d, DWORD PTR [rax+36]
    shl r11, 4
    mov r8, QWORD PTR [r8+QJS_ABI_OFF_JSObject_prop]
    movdqu xmm0, XMMWORD PTR [r13-16]
    movdqu XMMWORD PTR [r8+r11], xmm0
    dec DWORD PTR [r9+QJS_ABI_REF_COUNT_OFFSET]
    sub r13, 16
    mov QWORD PTR [r13], 0
    mov QWORD PTR [r13+8], 3
    add r12, 5
    test edx, 4
    jnz ordinary_vm_Clean_counter
    jmp ordinary_vm_Clean_dispatch
ordinary_vm_Clean_counter:
    lock inc QWORD PTR [rip+JS_FrameOrdinaryLiteralStats+40]
    lock inc QWORD PTR [rip+JS_FrameOrdinaryLiteralStats+128]
    cmp DWORD PTR [r9+QJS_ABI_OFF_JSShape_prop_size], 2
    jbe ordinary_vm_Clean_dispatch
    lock inc QWORD PTR [rip+JS_FrameOrdinaryLiteralStats+184]
ordinary_vm_Clean_dispatch:
    movzx eax, BYTE PTR [r12]
    jmp QWORD PTR [rdi+rax*8]
ordinary_vm_Clean_cold:
    mov QWORD PTR [rbx], rbp
    mov QWORD PTR [rbx+16], r12
    mov QWORD PTR [rbx+24], r13
    mov r10, QWORD PTR [rbx+56]
    mov QWORD PTR [r10+QJS_ABI_OFF_JSRuntime_current_stack_frame], rbp
    mov rcx, rbx
    call JS_FrameOrdinaryLiteralStep
    test eax, eax
    jz JS_FrameNativeLifetimeResume
    mov rbp, QWORD PTR [rbx]
    mov r12, QWORD PTR [rbx+16]
    mov r13, QWORD PTR [rbx+24]
    jmp interp_exit
JS_FrameOrdinaryLiteralOpClean_end:
.p2align 4
.globl JS_FrameOrdinaryLiteralOpDirty, JS_FrameOrdinaryLiteralOpDirty_end
.def JS_FrameOrdinaryLiteralOpDirty; .scl 2; .type 32; .endef
JS_FrameOrdinaryLiteralOpDirty:
    cmp BYTE PTR [rbx+FRAME_STATE_LITERAL_ACTIVE], 4
    je ordinary_lazy_Dirty_active
    cmp BYTE PTR [rbx+FRAME_STATE_LITERAL_LAZY], 1
    jne dirty_interp_slow
    cmp DWORD PTR [rbx+FRAME_STATE_ITERATOR_DEPTH], 0
    jne dirty_interp_slow
    cmp BYTE PTR [r12], 75
    jne ordinary_vm_Dirty_cold
    test DWORD PTR [rip+JS_FrameOrdinaryLiteralMode], 1024
    jz dirty_interp_slow
    jmp ordinary_vm_Dirty_cold
ordinary_lazy_Dirty_active:
    cmp DWORD PTR [rbx+FRAME_STATE_ITERATOR_DEPTH], 0
    jne dirty_interp_slow
    cmp BYTE PTR [r12], 75
    jne ordinary_vm_Dirty_cold
    cmp BYTE PTR [rbx+FRAME_STATE_EXCEPTION], 0
    jne ordinary_vm_Dirty_cold
    mov edx, DWORD PTR [rip+JS_FrameOrdinaryLiteralMode]
    test edx, 1
    jz ordinary_vm_Dirty_cold
    test edx, 138
    jnz ordinary_vm_Dirty_cold
    cmp QWORD PTR [r13-24], -1
    jne ordinary_vm_Dirty_cold
    mov r8, QWORD PTR [r13-32]
    cmp WORD PTR [r8+QJS_ABI_OFF_JSObject_class_id], 1
    jne ordinary_vm_Dirty_cold
.if QJS_ABI_HAS_PREFIX_RC
    movzx eax, BYTE PTR [r8+16]
    and eax, 11
    cmp eax, 2
    jne ordinary_vm_Dirty_cold
.else
    test BYTE PTR [r8+QJS_ABI_BIT_JSObject_is_prototype_BYTE], QJS_ABI_BIT_JSObject_is_prototype_MASK
    jnz ordinary_vm_Dirty_cold
    movzx eax, BYTE PTR [r8+QJS_ABI_BIT_JSObject_extensible_BYTE]
    and eax, QJS_ABI_BIT_JSObject_extensible_MASK | QJS_ABI_BIT_JSObject_is_exotic_MASK
    cmp eax, QJS_ABI_BIT_JSObject_extensible_MASK
    jne ordinary_vm_Dirty_cold
.endif
    mov r9, QWORD PTR [r8+QJS_ABI_OFF_JSObject_shape]
    cmp BYTE PTR [r9+QJS_ABI_OFF_JSShape_is_hashed], 0
    je ordinary_vm_Dirty_cold
    cmp DWORD PTR [r9+QJS_ABI_OFF_JSShape_deleted_prop_count], 0
    jne ordinary_vm_Dirty_cold
    mov eax, DWORD PTR [r9+QJS_ABI_OFF_JSShape_prop_count]
    cmp eax, DWORD PTR [r9+QJS_ABI_OFF_JSShape_prop_size]
    jae ordinary_vm_Dirty_cold
    test edx, 2048
    jz ordinary_vm_Dirty_spare_capacity
    cmp DWORD PTR [r9+QJS_ABI_OFF_JSShape_prop_size], 2
    jne ordinary_vm_Dirty_cold
ordinary_vm_Dirty_spare_capacity:
    mov rcx, QWORD PTR [rbx+FRAME_STATE_CACHE_NEXT]
    test rcx, rcx
    jz ordinary_vm_Dirty_cold
ordinary_vm_Dirty_hash:
    mov rax, r12
    mov r10, r12
    shr r10, 5
    xor rax, r10
    mov r10, r12
    shr r10, 11
    xor rax, r10
    and eax, 63
    mov rax, QWORD PTR [rcx+rax*8+336]
    mov r10, QWORD PTR [rbp+80]
ordinary_vm_Dirty_loop:
    test rax, rax
    jz ordinary_vm_Dirty_cold
    cmp QWORD PTR [rax], r12
    jne ordinary_vm_Dirty_next
    cmp QWORD PTR [rax+8], r10
    je ordinary_vm_Dirty_found
ordinary_vm_Dirty_next:
    mov rax, QWORD PTR [rax+40]
    jmp ordinary_vm_Dirty_loop
ordinary_vm_Dirty_found:
    cmp QWORD PTR [rax+16], r9
    jne ordinary_vm_Dirty_cold
    mov r10d, DWORD PTR [r12+1]
    cmp DWORD PTR [rax+32], r10d
    jne ordinary_vm_Dirty_cold
    mov r10, QWORD PTR [rax+24]
    test r10, r10
    jz ordinary_vm_Dirty_cold
    cmp BYTE PTR [r10+QJS_ABI_OFF_JSShape_is_hashed], 0
    je ordinary_vm_Dirty_cold
    mov r11d, DWORD PTR [r9+QJS_ABI_OFF_JSShape_prop_count]
    cmp DWORD PTR [rax+36], r11d
    jne ordinary_vm_Dirty_cold
    inc r11d
    cmp DWORD PTR [r10+QJS_ABI_OFF_JSShape_prop_count], r11d
    jne ordinary_vm_Dirty_cold
    mov r11d, DWORD PTR [r9+QJS_ABI_OFF_JSShape_prop_size]
    cmp DWORD PTR [r10+QJS_ABI_OFF_JSShape_prop_size], r11d
    jne ordinary_vm_Dirty_cold
    inc DWORD PTR [r10+QJS_ABI_REF_COUNT_OFFSET]
    mov QWORD PTR [r8+QJS_ABI_OFF_JSObject_shape], r10
    mov r11d, DWORD PTR [rax+36]
    shl r11, 4
    mov r8, QWORD PTR [r8+QJS_ABI_OFF_JSObject_prop]
    movdqu xmm0, XMMWORD PTR [r13-16]
    movdqu XMMWORD PTR [r8+r11], xmm0
    dec DWORD PTR [r9+QJS_ABI_REF_COUNT_OFFSET]
    sub r13, 16
    mov QWORD PTR [r13], 0
    mov QWORD PTR [r13+8], 3
    add r12, 5
    test edx, 4
    jnz ordinary_vm_Dirty_counter
    jmp ordinary_vm_Dirty_dispatch
ordinary_vm_Dirty_counter:
    lock inc QWORD PTR [rip+JS_FrameOrdinaryLiteralStats+40]
    lock inc QWORD PTR [rip+JS_FrameOrdinaryLiteralStats+128]
    cmp DWORD PTR [r9+QJS_ABI_OFF_JSShape_prop_size], 2
    jbe ordinary_vm_Dirty_dispatch
    lock inc QWORD PTR [rip+JS_FrameOrdinaryLiteralStats+184]
ordinary_vm_Dirty_dispatch:
    movzx eax, BYTE PTR [r12]
    jmp QWORD PTR [rdi+rax*8]
ordinary_vm_Dirty_cold:
    mov QWORD PTR [rbx], rbp
    mov QWORD PTR [rbx+16], r12
    mov QWORD PTR [rbx+24], r13
    mov r10, QWORD PTR [rbx+56]
    mov QWORD PTR [r10+QJS_ABI_OFF_JSRuntime_current_stack_frame], rbp
    mov rcx, rbx
    call JS_FrameOrdinaryLiteralStep
    test eax, eax
    jz JS_FrameNativeLifetimeResume
    mov rbp, QWORD PTR [rbx]
    mov r12, QWORD PTR [rbx+16]
    mov r13, QWORD PTR [rbx+24]
    jmp interp_exit
JS_FrameOrdinaryLiteralOpDirty_end:
.p2align 4
.globl JS_FrameStackInsert2Clean, JS_FrameStackInsert2Clean_end
.def JS_FrameStackInsert2Clean; .scl 2; .type 32; .endef
JS_FrameStackInsert2Clean:
    mov edx, DWORD PTR [rip+JS_FrameOrdinaryLiteralMode]
    test edx, edx
    jz interp_slow
    test edx, 4096
    jnz interp_slow
    movdqu xmm0, XMMWORD PTR [r13-16]
    movdqu xmm1, XMMWORD PTR [r13-32]
    cmp DWORD PTR [r13-8], -9
    jb JS_FrameStackInsert2Clean_value
    mov rax, QWORD PTR [r13-16]
    add DWORD PTR [rax+QJS_ABI_REF_COUNT_OFFSET], 1
JS_FrameStackInsert2Clean_value:
    movdqu XMMWORD PTR [r13], xmm0
    movdqu XMMWORD PTR [r13-16], xmm1
    movdqu XMMWORD PTR [r13-32], xmm0
    add r13, 16
    inc r12
    test edx, 4
    jz JS_FrameStackInsert2Clean_dispatch
    lock inc QWORD PTR [rip+JS_FrameOrdinaryLiteralStats+192]
JS_FrameStackInsert2Clean_dispatch:
    movzx eax, BYTE PTR [r12]
    jmp QWORD PTR [rdi+rax*8]
JS_FrameStackInsert2Clean_end:
.p2align 4
.globl JS_FrameStackInsert2Dirty, JS_FrameStackInsert2Dirty_end
.def JS_FrameStackInsert2Dirty; .scl 2; .type 32; .endef
JS_FrameStackInsert2Dirty:
    mov edx, DWORD PTR [rip+JS_FrameOrdinaryLiteralMode]
    test edx, edx
    jz dirty_interp_slow
    test edx, 4096
    jnz dirty_interp_slow
    movdqu xmm0, XMMWORD PTR [r13-16]
    movdqu xmm1, XMMWORD PTR [r13-32]
    cmp DWORD PTR [r13-8], -9
    jb JS_FrameStackInsert2Dirty_value
    mov rax, QWORD PTR [r13-16]
    add DWORD PTR [rax+QJS_ABI_REF_COUNT_OFFSET], 1
JS_FrameStackInsert2Dirty_value:
    movdqu XMMWORD PTR [r13], xmm0
    movdqu XMMWORD PTR [r13-16], xmm1
    movdqu XMMWORD PTR [r13-32], xmm0
    add r13, 16
    inc r12
    test edx, 4
    jz JS_FrameStackInsert2Dirty_dispatch
    lock inc QWORD PTR [rip+JS_FrameOrdinaryLiteralStats+192]
JS_FrameStackInsert2Dirty_dispatch:
    movzx eax, BYTE PTR [r12]
    jmp QWORD PTR [rdi+rax*8]
JS_FrameStackInsert2Dirty_end:
.p2align 4
.globl JS_FrameTypeofValueClean, JS_FrameTypeofValueClean_end
.def JS_FrameTypeofValueClean; .scl 2; .type 32; .endef
JS_FrameTypeofValueClean:
    mov edx, DWORD PTR [rip+JS_FrameOrdinaryLiteralMode]
    test edx, edx
    jz interp_slow
    test edx, 8192
    jnz interp_slow
    mov eax, DWORD PTR [r13-8]
    cmp eax, -6
    jg JS_FrameTypeofValueClean_immediate
    cmp eax, -9
    jl interp_slow
    mov r8, QWORD PTR [r13-16]
    cmp DWORD PTR [r8+QJS_ABI_REF_COUNT_OFFSET], 1
    jle interp_slow
    sub DWORD PTR [r8+QJS_ABI_REF_COUNT_OFFSET], 1
    jmp JS_FrameTypeofValueClean_classified
JS_FrameTypeofValueClean_immediate:
    cmp eax, 3
    jbe JS_FrameTypeofValueClean_classified
    cmp eax, 7
    je JS_FrameTypeofValueClean_classified
    cmp eax, 8
    jne interp_slow
JS_FrameTypeofValueClean_classified:
    cmp eax, -7
    je JS_FrameTypeofValueClean_atom76
    cmp eax, -6
    je JS_FrameTypeofValueClean_atom76
    cmp eax, -9
    je JS_FrameTypeofValueClean_atom150
    cmp eax, -8
    je JS_FrameTypeofValueClean_atom78
    cmp eax, 0
    je JS_FrameTypeofValueClean_atom74
    cmp eax, 8
    je JS_FrameTypeofValueClean_atom74
    cmp eax, 1
    je JS_FrameTypeofValueClean_atom75
    cmp eax, 2
    je JS_FrameTypeofValueClean_atom77
    cmp eax, 3
    je JS_FrameTypeofValueClean_atom73
    cmp eax, 7
    je JS_FrameTypeofValueClean_atom150
    ud2
JS_FrameTypeofValueClean_atom76:
    mov ecx, 76
    jmp JS_FrameTypeofValueClean_result
JS_FrameTypeofValueClean_atom150:
    mov ecx, 150
    jmp JS_FrameTypeofValueClean_result
JS_FrameTypeofValueClean_atom78:
    mov ecx, 78
    jmp JS_FrameTypeofValueClean_result
JS_FrameTypeofValueClean_atom74:
    mov ecx, 74
    jmp JS_FrameTypeofValueClean_result
JS_FrameTypeofValueClean_atom75:
    mov ecx, 75
    jmp JS_FrameTypeofValueClean_result
JS_FrameTypeofValueClean_atom77:
    mov ecx, 77
    jmp JS_FrameTypeofValueClean_result
JS_FrameTypeofValueClean_atom73:
    mov ecx, 73
    jmp JS_FrameTypeofValueClean_result
JS_FrameTypeofValueClean_result:
    mov r8, QWORD PTR [rbx+56]
    mov r8, QWORD PTR [r8+QJS_ABI_OFF_JSRuntime_atom_array]
    mov r8, QWORD PTR [r8+rcx*8]
    add DWORD PTR [r8+QJS_ABI_REF_COUNT_OFFSET], 1
    mov QWORD PTR [r13-16], r8
    mov QWORD PTR [r13-8], -7
    inc r12
    test edx, 4
    jz JS_FrameTypeofValueClean_dispatch
    lock inc QWORD PTR [rip+JS_FrameOrdinaryLiteralStats+200]
JS_FrameTypeofValueClean_dispatch:
    movzx eax, BYTE PTR [r12]
    jmp QWORD PTR [rdi+rax*8]
JS_FrameTypeofValueClean_end:
.p2align 4
.globl JS_FrameTypeofFunctionClean, JS_FrameTypeofFunctionClean_end
.def JS_FrameTypeofFunctionClean; .scl 2; .type 32; .endef
JS_FrameTypeofFunctionClean:
    mov edx, DWORD PTR [rip+JS_FrameOrdinaryLiteralMode]
    test edx, edx
    jz interp_slow
    test edx, 8192
    jnz interp_slow
    mov eax, DWORD PTR [r13-8]
    cmp eax, -6
    jg JS_FrameTypeofFunctionClean_immediate
    cmp eax, -9
    jl interp_slow
    mov r8, QWORD PTR [r13-16]
    cmp DWORD PTR [r8+QJS_ABI_REF_COUNT_OFFSET], 1
    jle interp_slow
    sub DWORD PTR [r8+QJS_ABI_REF_COUNT_OFFSET], 1
    jmp JS_FrameTypeofFunctionClean_classified
JS_FrameTypeofFunctionClean_immediate:
    cmp eax, 3
    jbe JS_FrameTypeofFunctionClean_classified
    cmp eax, 7
    je JS_FrameTypeofFunctionClean_classified
    cmp eax, 8
    jne interp_slow
JS_FrameTypeofFunctionClean_classified:
    xor ecx, ecx
    mov QWORD PTR [r13-16], rcx
    mov QWORD PTR [r13-8], 1
    inc r12
    test edx, 4
    jz JS_FrameTypeofFunctionClean_dispatch
    lock inc QWORD PTR [rip+JS_FrameOrdinaryLiteralStats+208]
JS_FrameTypeofFunctionClean_dispatch:
    movzx eax, BYTE PTR [r12]
    jmp QWORD PTR [rdi+rax*8]
JS_FrameTypeofFunctionClean_end:
.p2align 4
.globl JS_FrameTypeofUndefinedClean, JS_FrameTypeofUndefinedClean_end
.def JS_FrameTypeofUndefinedClean; .scl 2; .type 32; .endef
JS_FrameTypeofUndefinedClean:
    mov edx, DWORD PTR [rip+JS_FrameOrdinaryLiteralMode]
    test edx, edx
    jz interp_slow
    test edx, 8192
    jnz interp_slow
    mov eax, DWORD PTR [r13-8]
    cmp eax, -6
    jg JS_FrameTypeofUndefinedClean_immediate
    cmp eax, -9
    jl interp_slow
    mov r8, QWORD PTR [r13-16]
    cmp DWORD PTR [r8+QJS_ABI_REF_COUNT_OFFSET], 1
    jle interp_slow
    sub DWORD PTR [r8+QJS_ABI_REF_COUNT_OFFSET], 1
    jmp JS_FrameTypeofUndefinedClean_classified
JS_FrameTypeofUndefinedClean_immediate:
    cmp eax, 3
    jbe JS_FrameTypeofUndefinedClean_classified
    cmp eax, 7
    je JS_FrameTypeofUndefinedClean_classified
    cmp eax, 8
    jne interp_slow
JS_FrameTypeofUndefinedClean_classified:
    cmp eax, 3
    sete cl
    movzx ecx, cl
    mov QWORD PTR [r13-16], rcx
    mov QWORD PTR [r13-8], 1
    inc r12
    test edx, 4
    jz JS_FrameTypeofUndefinedClean_dispatch
    lock inc QWORD PTR [rip+JS_FrameOrdinaryLiteralStats+216]
JS_FrameTypeofUndefinedClean_dispatch:
    movzx eax, BYTE PTR [r12]
    jmp QWORD PTR [rdi+rax*8]
JS_FrameTypeofUndefinedClean_end:
.p2align 4
.globl JS_FrameTypeofValueDirty, JS_FrameTypeofValueDirty_end
.def JS_FrameTypeofValueDirty; .scl 2; .type 32; .endef
JS_FrameTypeofValueDirty:
    mov edx, DWORD PTR [rip+JS_FrameOrdinaryLiteralMode]
    test edx, edx
    jz dirty_interp_slow
    test edx, 8192
    jnz dirty_interp_slow
    mov eax, DWORD PTR [r13-8]
    cmp eax, -6
    jg JS_FrameTypeofValueDirty_immediate
    cmp eax, -9
    jl dirty_interp_slow
    mov r8, QWORD PTR [r13-16]
    cmp DWORD PTR [r8+QJS_ABI_REF_COUNT_OFFSET], 1
    jle dirty_interp_slow
    sub DWORD PTR [r8+QJS_ABI_REF_COUNT_OFFSET], 1
    jmp JS_FrameTypeofValueDirty_classified
JS_FrameTypeofValueDirty_immediate:
    cmp eax, 3
    jbe JS_FrameTypeofValueDirty_classified
    cmp eax, 7
    je JS_FrameTypeofValueDirty_classified
    cmp eax, 8
    jne dirty_interp_slow
JS_FrameTypeofValueDirty_classified:
    cmp eax, -7
    je JS_FrameTypeofValueDirty_atom76
    cmp eax, -6
    je JS_FrameTypeofValueDirty_atom76
    cmp eax, -9
    je JS_FrameTypeofValueDirty_atom150
    cmp eax, -8
    je JS_FrameTypeofValueDirty_atom78
    cmp eax, 0
    je JS_FrameTypeofValueDirty_atom74
    cmp eax, 8
    je JS_FrameTypeofValueDirty_atom74
    cmp eax, 1
    je JS_FrameTypeofValueDirty_atom75
    cmp eax, 2
    je JS_FrameTypeofValueDirty_atom77
    cmp eax, 3
    je JS_FrameTypeofValueDirty_atom73
    cmp eax, 7
    je JS_FrameTypeofValueDirty_atom150
    ud2
JS_FrameTypeofValueDirty_atom76:
    mov ecx, 76
    jmp JS_FrameTypeofValueDirty_result
JS_FrameTypeofValueDirty_atom150:
    mov ecx, 150
    jmp JS_FrameTypeofValueDirty_result
JS_FrameTypeofValueDirty_atom78:
    mov ecx, 78
    jmp JS_FrameTypeofValueDirty_result
JS_FrameTypeofValueDirty_atom74:
    mov ecx, 74
    jmp JS_FrameTypeofValueDirty_result
JS_FrameTypeofValueDirty_atom75:
    mov ecx, 75
    jmp JS_FrameTypeofValueDirty_result
JS_FrameTypeofValueDirty_atom77:
    mov ecx, 77
    jmp JS_FrameTypeofValueDirty_result
JS_FrameTypeofValueDirty_atom73:
    mov ecx, 73
    jmp JS_FrameTypeofValueDirty_result
JS_FrameTypeofValueDirty_result:
    mov r8, QWORD PTR [rbx+56]
    mov r8, QWORD PTR [r8+QJS_ABI_OFF_JSRuntime_atom_array]
    mov r8, QWORD PTR [r8+rcx*8]
    add DWORD PTR [r8+QJS_ABI_REF_COUNT_OFFSET], 1
    mov QWORD PTR [r13-16], r8
    mov QWORD PTR [r13-8], -7
    inc r12
    test edx, 4
    jz JS_FrameTypeofValueDirty_dispatch
    lock inc QWORD PTR [rip+JS_FrameOrdinaryLiteralStats+200]
JS_FrameTypeofValueDirty_dispatch:
    movzx eax, BYTE PTR [r12]
    jmp QWORD PTR [rdi+rax*8]
JS_FrameTypeofValueDirty_end:
.p2align 4
.globl JS_FrameTypeofFunctionDirty, JS_FrameTypeofFunctionDirty_end
.def JS_FrameTypeofFunctionDirty; .scl 2; .type 32; .endef
JS_FrameTypeofFunctionDirty:
    mov edx, DWORD PTR [rip+JS_FrameOrdinaryLiteralMode]
    test edx, edx
    jz dirty_interp_slow
    test edx, 8192
    jnz dirty_interp_slow
    mov eax, DWORD PTR [r13-8]
    cmp eax, -6
    jg JS_FrameTypeofFunctionDirty_immediate
    cmp eax, -9
    jl dirty_interp_slow
    mov r8, QWORD PTR [r13-16]
    cmp DWORD PTR [r8+QJS_ABI_REF_COUNT_OFFSET], 1
    jle dirty_interp_slow
    sub DWORD PTR [r8+QJS_ABI_REF_COUNT_OFFSET], 1
    jmp JS_FrameTypeofFunctionDirty_classified
JS_FrameTypeofFunctionDirty_immediate:
    cmp eax, 3
    jbe JS_FrameTypeofFunctionDirty_classified
    cmp eax, 7
    je JS_FrameTypeofFunctionDirty_classified
    cmp eax, 8
    jne dirty_interp_slow
JS_FrameTypeofFunctionDirty_classified:
    xor ecx, ecx
    mov QWORD PTR [r13-16], rcx
    mov QWORD PTR [r13-8], 1
    inc r12
    test edx, 4
    jz JS_FrameTypeofFunctionDirty_dispatch
    lock inc QWORD PTR [rip+JS_FrameOrdinaryLiteralStats+208]
JS_FrameTypeofFunctionDirty_dispatch:
    movzx eax, BYTE PTR [r12]
    jmp QWORD PTR [rdi+rax*8]
JS_FrameTypeofFunctionDirty_end:
.p2align 4
.globl JS_FrameTypeofUndefinedDirty, JS_FrameTypeofUndefinedDirty_end
.def JS_FrameTypeofUndefinedDirty; .scl 2; .type 32; .endef
JS_FrameTypeofUndefinedDirty:
    mov edx, DWORD PTR [rip+JS_FrameOrdinaryLiteralMode]
    test edx, edx
    jz dirty_interp_slow
    test edx, 8192
    jnz dirty_interp_slow
    mov eax, DWORD PTR [r13-8]
    cmp eax, -6
    jg JS_FrameTypeofUndefinedDirty_immediate
    cmp eax, -9
    jl dirty_interp_slow
    mov r8, QWORD PTR [r13-16]
    cmp DWORD PTR [r8+QJS_ABI_REF_COUNT_OFFSET], 1
    jle dirty_interp_slow
    sub DWORD PTR [r8+QJS_ABI_REF_COUNT_OFFSET], 1
    jmp JS_FrameTypeofUndefinedDirty_classified
JS_FrameTypeofUndefinedDirty_immediate:
    cmp eax, 3
    jbe JS_FrameTypeofUndefinedDirty_classified
    cmp eax, 7
    je JS_FrameTypeofUndefinedDirty_classified
    cmp eax, 8
    jne dirty_interp_slow
JS_FrameTypeofUndefinedDirty_classified:
    cmp eax, 3
    sete cl
    movzx ecx, cl
    mov QWORD PTR [r13-16], rcx
    mov QWORD PTR [r13-8], 1
    inc r12
    test edx, 4
    jz JS_FrameTypeofUndefinedDirty_dispatch
    lock inc QWORD PTR [rip+JS_FrameOrdinaryLiteralStats+216]
JS_FrameTypeofUndefinedDirty_dispatch:
    movzx eax, BYTE PTR [r12]
    jmp QWORD PTR [rdi+rax*8]
JS_FrameTypeofUndefinedDirty_end:
.p2align 4
.globl JS_FramePredicateClassify, JS_FramePredicateClassify_end
.def JS_FramePredicateClassify; .scl 2; .type 32; .endef
JS_FramePredicateClassify:
    mov eax, DWORD PTR [rip+JS_FrameOrdinaryLiteralMode]
    test eax, eax
    jz JS_FrameLeafUnready
    test eax, 16384
    jnz JS_FrameLeafUnready
    test BYTE PTR [r9+QJS_ABI_OFF_JSFunctionBytecode_byte_code_buf-1], 4
    jnz JS_FrameLeafUnready
    cmp WORD PTR [r9+QJS_ABI_OFF_JSFunctionBytecode_var_count], 0
    jne JS_FrameLeafUnready
    cmp WORD PTR [r9+QJS_ABI_OFF_JSFunctionBytecode_var_ref_count], 0
    jne JS_FrameLeafUnready
    cmp DWORD PTR [r9+QJS_ABI_OFF_JSFunctionBytecode_byte_code_len], 16
    jne JS_FrameLeafUnready
    mov r10, QWORD PTR [r9+QJS_ABI_OFF_JSFunctionBytecode_byte_code_buf]
    movzx eax, BYTE PTR [r10]
    cmp al, BYTE PTR [r10+7]
    jne JS_FrameLeafUnready
    sub eax, 215
    cmp eax, 3
    ja JS_FrameLeafUnready
    mov rax, QWORD PTR [r10]
    mov r11, 0x00ffffffffffff00
    and rax, r11
    mov r11, 3952675878864640
    cmp rax, r11
    jne JS_FrameLeafUnready
    mov rax, QWORD PTR [r10+8]
    mov r11, 2930435982539687062
    cmp rax, r11
    jne JS_FrameLeafUnready
    mov eax, 7
    jmp JS_FramePredicateStore
JS_FramePredicateClassify_end:
.p2align 4
.globl JS_FramePredicateValue, JS_FramePredicateValue_end
.def JS_FramePredicateValue; .scl 2; .type 32; .endef
JS_FramePredicateValue:
    cmp DWORD PTR [r9+QJS_ABI_OFF_JSFunctionBytecode_byte_code_len], 2
    je JS_FramePredicateLiteral
    cmp DWORD PTR [r9+QJS_ABI_OFF_JSFunctionBytecode_byte_code_len], 16
    jne JS_FrameLeafReject
    movzx eax, BYTE PTR [r10]
    sub eax, 215
    cmp eax, ecx
    jae JS_FrameLeafReject
    shl rax, 4
    add rax, r8
    mov edx, DWORD PTR [rax+8]
    cmp edx, 3
    jbe predicate_primitive
    cmp edx, 7
    je predicate_primitive
    cmp edx, 8
    je predicate_primitive
    add edx, 9
    cmp edx, 3
    ja JS_FrameLeafReject
predicate_primitive:
    test DWORD PTR [rip+JS_FrameOrdinaryLiteralMode], 4
    jz predicate_result
    lock inc QWORD PTR [rip+JS_FrameOrdinaryLiteralStats+224]
predicate_result:
    xor eax, eax
    jmp JS_FramePredicateBoolean
JS_FramePredicateValue_end:
.p2align 4
.globl JS_FrameTruthLnotClean, JS_FrameTruthLnotClean_end
.def JS_FrameTruthLnotClean; .scl 2; .type 32; .endef
JS_FrameTruthLnotClean:
    mov edx, DWORD PTR [rip+JS_FrameOrdinaryLiteralMode]
    test edx, edx
    jz interp_slow
    test edx, 32768
    jnz interp_slow
    mov eax, DWORD PTR [r13-8]
    cmp eax, -1
    je JS_FrameTruthLnotClean_object
    cmp eax, -7
    je JS_FrameTruthLnotClean_string
    cmp eax, -6
    jne JS_FrameTruthLnotClean_number
    mov r8, QWORD PTR [r13-16]
    cmp DWORD PTR [r8+QJS_ABI_REF_COUNT_OFFSET], 1
    jle interp_slow
    xor eax, eax
    cmp DWORD PTR [r8+QJS_ABI_OFF_JSStringRope_len], 0
    setne al
    jmp JS_FrameTruthLnotClean_release
JS_FrameTruthLnotClean_string:
    mov r8, QWORD PTR [r13-16]
    cmp DWORD PTR [r8+QJS_ABI_REF_COUNT_OFFSET], 1
    jle interp_slow
    xor eax, eax
    test DWORD PTR [r8+QJS_ABI_BIT_JSString_len_BYTE], 2147483647
    setne al
    jmp JS_FrameTruthLnotClean_release
JS_FrameTruthLnotClean_object:
    mov r8, QWORD PTR [r13-16]
    cmp DWORD PTR [r8+QJS_ABI_REF_COUNT_OFFSET], 1
    jle interp_slow
    xor eax, eax
    test BYTE PTR [r8+QJS_ABI_BIT_JSObject_is_HTMLDDA_BYTE], QJS_ABI_BIT_JSObject_is_HTMLDDA_MASK
    sete al
JS_FrameTruthLnotClean_release:
    sub DWORD PTR [r8+QJS_ABI_REF_COUNT_OFFSET], 1
    test edx, 4
    jz JS_FrameTruthLnotClean_commit
    lock inc QWORD PTR [rip+JS_FrameOrdinaryLiteralStats+232]
JS_FrameTruthLnotClean_commit:
    xor eax, 1
    mov QWORD PTR [r13-16], rax
    mov QWORD PTR [r13-8], 1
    inc r12
JS_FrameTruthLnotClean_dispatch:
    movzx eax, BYTE PTR [r12]
    jmp QWORD PTR [rdi+rax*8]
JS_FrameTruthLnotClean_number:
    cmp eax, 8
    jne interp_slow
    test edx, 65536
    jnz interp_slow
    pxor xmm0, xmm0
    ucomisd xmm0, QWORD PTR [r13-16]
    setne al
    movzx eax, al
    test edx, 4
    jz JS_FrameTruthLnotClean_number_commit
    lock inc QWORD PTR [rip+JS_FrameOrdinaryLiteralStats+232]
JS_FrameTruthLnotClean_number_commit:
    jmp JS_FrameTruthLnotClean_commit
JS_FrameTruthLnotClean_end:
.p2align 4
.globl JS_FrameTruthIfTrueClean, JS_FrameTruthIfTrueClean_end
.def JS_FrameTruthIfTrueClean; .scl 2; .type 32; .endef
JS_FrameTruthIfTrueClean:
    mov edx, DWORD PTR [rip+JS_FrameOrdinaryLiteralMode]
    test edx, edx
    jz interp_slow
    test edx, 32768
    jnz interp_slow
    mov eax, DWORD PTR [r13-8]
    cmp eax, -1
    je JS_FrameTruthIfTrueClean_object
    cmp eax, -7
    je JS_FrameTruthIfTrueClean_string
    cmp eax, -6
    jne JS_FrameTruthIfTrueClean_number
    mov r8, QWORD PTR [r13-16]
    cmp DWORD PTR [r8+QJS_ABI_REF_COUNT_OFFSET], 1
    jle interp_slow
    xor eax, eax
    cmp DWORD PTR [r8+QJS_ABI_OFF_JSStringRope_len], 0
    setne al
    jmp JS_FrameTruthIfTrueClean_release
JS_FrameTruthIfTrueClean_string:
    mov r8, QWORD PTR [r13-16]
    cmp DWORD PTR [r8+QJS_ABI_REF_COUNT_OFFSET], 1
    jle interp_slow
    xor eax, eax
    test DWORD PTR [r8+QJS_ABI_BIT_JSString_len_BYTE], 2147483647
    setne al
    jmp JS_FrameTruthIfTrueClean_release
JS_FrameTruthIfTrueClean_object:
    mov r8, QWORD PTR [r13-16]
    cmp DWORD PTR [r8+QJS_ABI_REF_COUNT_OFFSET], 1
    jle interp_slow
    xor eax, eax
    test BYTE PTR [r8+QJS_ABI_BIT_JSObject_is_HTMLDDA_BYTE], QJS_ABI_BIT_JSObject_is_HTMLDDA_MASK
    sete al
JS_FrameTruthIfTrueClean_release:
    sub DWORD PTR [r8+QJS_ABI_REF_COUNT_OFFSET], 1
    test edx, 4
    jz JS_FrameTruthIfTrueClean_commit
    lock inc QWORD PTR [rip+JS_FrameOrdinaryLiteralStats+240]
JS_FrameTruthIfTrueClean_commit:
    sub r13, 16
    dec DWORD PTR [rsi+QJS_ABI_OFF_JSContext_interrupt_counter]
    test eax, eax
    jz JS_FrameTruthIfTrueClean_untaken
    movsxd rax, DWORD PTR [r12+1]
    lea r12, [r12+rax+1]
    jmp JS_FrameTruthIfTrueClean_dispatch
JS_FrameTruthIfTrueClean_untaken:
    add r12, 5
JS_FrameTruthIfTrueClean_dispatch:
    movzx eax, BYTE PTR [r12]
    jmp QWORD PTR [rdi+rax*8]
JS_FrameTruthIfTrueClean_number:
    cmp eax, 8
    jne interp_slow
    test edx, 65536
    jnz interp_slow
    pxor xmm0, xmm0
    ucomisd xmm0, QWORD PTR [r13-16]
    setne al
    movzx eax, al
    test edx, 4
    jz JS_FrameTruthIfTrueClean_number_commit
    lock inc QWORD PTR [rip+JS_FrameOrdinaryLiteralStats+240]
JS_FrameTruthIfTrueClean_number_commit:
    jmp JS_FrameTruthIfTrueClean_commit
JS_FrameTruthIfTrueClean_end:
.p2align 4
.globl JS_FrameTruthIfFalseClean, JS_FrameTruthIfFalseClean_end
.def JS_FrameTruthIfFalseClean; .scl 2; .type 32; .endef
JS_FrameTruthIfFalseClean:
    mov edx, DWORD PTR [rip+JS_FrameOrdinaryLiteralMode]
    test edx, edx
    jz interp_slow
    test edx, 32768
    jnz interp_slow
    mov eax, DWORD PTR [r13-8]
    cmp eax, -1
    je JS_FrameTruthIfFalseClean_object
    cmp eax, -7
    je JS_FrameTruthIfFalseClean_string
    cmp eax, -6
    jne JS_FrameTruthIfFalseClean_number
    mov r8, QWORD PTR [r13-16]
    cmp DWORD PTR [r8+QJS_ABI_REF_COUNT_OFFSET], 1
    jle interp_slow
    xor eax, eax
    cmp DWORD PTR [r8+QJS_ABI_OFF_JSStringRope_len], 0
    setne al
    jmp JS_FrameTruthIfFalseClean_release
JS_FrameTruthIfFalseClean_string:
    mov r8, QWORD PTR [r13-16]
    cmp DWORD PTR [r8+QJS_ABI_REF_COUNT_OFFSET], 1
    jle interp_slow
    xor eax, eax
    test DWORD PTR [r8+QJS_ABI_BIT_JSString_len_BYTE], 2147483647
    setne al
    jmp JS_FrameTruthIfFalseClean_release
JS_FrameTruthIfFalseClean_object:
    mov r8, QWORD PTR [r13-16]
    cmp DWORD PTR [r8+QJS_ABI_REF_COUNT_OFFSET], 1
    jle interp_slow
    xor eax, eax
    test BYTE PTR [r8+QJS_ABI_BIT_JSObject_is_HTMLDDA_BYTE], QJS_ABI_BIT_JSObject_is_HTMLDDA_MASK
    sete al
JS_FrameTruthIfFalseClean_release:
    sub DWORD PTR [r8+QJS_ABI_REF_COUNT_OFFSET], 1
    test edx, 4
    jz JS_FrameTruthIfFalseClean_commit
    lock inc QWORD PTR [rip+JS_FrameOrdinaryLiteralStats+248]
JS_FrameTruthIfFalseClean_commit:
    sub r13, 16
    dec DWORD PTR [rsi+QJS_ABI_OFF_JSContext_interrupt_counter]
    test eax, eax
    jnz JS_FrameTruthIfFalseClean_untaken
    movsxd rax, DWORD PTR [r12+1]
    lea r12, [r12+rax+1]
    jmp JS_FrameTruthIfFalseClean_dispatch
JS_FrameTruthIfFalseClean_untaken:
    add r12, 5
JS_FrameTruthIfFalseClean_dispatch:
    movzx eax, BYTE PTR [r12]
    jmp QWORD PTR [rdi+rax*8]
JS_FrameTruthIfFalseClean_number:
    cmp eax, 8
    jne interp_slow
    test edx, 65536
    jnz interp_slow
    pxor xmm0, xmm0
    ucomisd xmm0, QWORD PTR [r13-16]
    setne al
    movzx eax, al
    test edx, 4
    jz JS_FrameTruthIfFalseClean_number_commit
    lock inc QWORD PTR [rip+JS_FrameOrdinaryLiteralStats+248]
JS_FrameTruthIfFalseClean_number_commit:
    jmp JS_FrameTruthIfFalseClean_commit
JS_FrameTruthIfFalseClean_end:
.p2align 4
.globl JS_FrameTruthIfTrue8Clean, JS_FrameTruthIfTrue8Clean_end
.def JS_FrameTruthIfTrue8Clean; .scl 2; .type 32; .endef
JS_FrameTruthIfTrue8Clean:
    mov edx, DWORD PTR [rip+JS_FrameOrdinaryLiteralMode]
    test edx, edx
    jz interp_slow
    test edx, 32768
    jnz interp_slow
    mov eax, DWORD PTR [r13-8]
    cmp eax, -1
    je JS_FrameTruthIfTrue8Clean_object
    cmp eax, -7
    je JS_FrameTruthIfTrue8Clean_string
    cmp eax, -6
    jne JS_FrameTruthIfTrue8Clean_number
    mov r8, QWORD PTR [r13-16]
    cmp DWORD PTR [r8+QJS_ABI_REF_COUNT_OFFSET], 1
    jle interp_slow
    xor eax, eax
    cmp DWORD PTR [r8+QJS_ABI_OFF_JSStringRope_len], 0
    setne al
    jmp JS_FrameTruthIfTrue8Clean_release
JS_FrameTruthIfTrue8Clean_string:
    mov r8, QWORD PTR [r13-16]
    cmp DWORD PTR [r8+QJS_ABI_REF_COUNT_OFFSET], 1
    jle interp_slow
    xor eax, eax
    test DWORD PTR [r8+QJS_ABI_BIT_JSString_len_BYTE], 2147483647
    setne al
    jmp JS_FrameTruthIfTrue8Clean_release
JS_FrameTruthIfTrue8Clean_object:
    mov r8, QWORD PTR [r13-16]
    cmp DWORD PTR [r8+QJS_ABI_REF_COUNT_OFFSET], 1
    jle interp_slow
    xor eax, eax
    test BYTE PTR [r8+QJS_ABI_BIT_JSObject_is_HTMLDDA_BYTE], QJS_ABI_BIT_JSObject_is_HTMLDDA_MASK
    sete al
JS_FrameTruthIfTrue8Clean_release:
    sub DWORD PTR [r8+QJS_ABI_REF_COUNT_OFFSET], 1
    test edx, 4
    jz JS_FrameTruthIfTrue8Clean_commit
    lock inc QWORD PTR [rip+JS_FrameOrdinaryLiteralStats+256]
JS_FrameTruthIfTrue8Clean_commit:
    sub r13, 16
    dec DWORD PTR [rsi+QJS_ABI_OFF_JSContext_interrupt_counter]
    test eax, eax
    jz JS_FrameTruthIfTrue8Clean_untaken
    movsx rax, BYTE PTR [r12+1]
    lea r12, [r12+rax+1]
    jmp JS_FrameTruthIfTrue8Clean_dispatch
JS_FrameTruthIfTrue8Clean_untaken:
    add r12, 2
JS_FrameTruthIfTrue8Clean_dispatch:
    movzx eax, BYTE PTR [r12]
    jmp QWORD PTR [rdi+rax*8]
JS_FrameTruthIfTrue8Clean_number:
    cmp eax, 8
    jne interp_slow
    test edx, 65536
    jnz interp_slow
    pxor xmm0, xmm0
    ucomisd xmm0, QWORD PTR [r13-16]
    setne al
    movzx eax, al
    test edx, 4
    jz JS_FrameTruthIfTrue8Clean_number_commit
    lock inc QWORD PTR [rip+JS_FrameOrdinaryLiteralStats+256]
JS_FrameTruthIfTrue8Clean_number_commit:
    jmp JS_FrameTruthIfTrue8Clean_commit
JS_FrameTruthIfTrue8Clean_end:
.p2align 4
.globl JS_FrameTruthIfFalse8Clean, JS_FrameTruthIfFalse8Clean_end
.def JS_FrameTruthIfFalse8Clean; .scl 2; .type 32; .endef
JS_FrameTruthIfFalse8Clean:
    mov edx, DWORD PTR [rip+JS_FrameOrdinaryLiteralMode]
    test edx, edx
    jz interp_slow
    test edx, 32768
    jnz interp_slow
    mov eax, DWORD PTR [r13-8]
    cmp eax, -1
    je JS_FrameTruthIfFalse8Clean_object
    cmp eax, -7
    je JS_FrameTruthIfFalse8Clean_string
    cmp eax, -6
    jne JS_FrameTruthIfFalse8Clean_number
    mov r8, QWORD PTR [r13-16]
    cmp DWORD PTR [r8+QJS_ABI_REF_COUNT_OFFSET], 1
    jle interp_slow
    xor eax, eax
    cmp DWORD PTR [r8+QJS_ABI_OFF_JSStringRope_len], 0
    setne al
    jmp JS_FrameTruthIfFalse8Clean_release
JS_FrameTruthIfFalse8Clean_string:
    mov r8, QWORD PTR [r13-16]
    cmp DWORD PTR [r8+QJS_ABI_REF_COUNT_OFFSET], 1
    jle interp_slow
    xor eax, eax
    test DWORD PTR [r8+QJS_ABI_BIT_JSString_len_BYTE], 2147483647
    setne al
    jmp JS_FrameTruthIfFalse8Clean_release
JS_FrameTruthIfFalse8Clean_object:
    mov r8, QWORD PTR [r13-16]
    cmp DWORD PTR [r8+QJS_ABI_REF_COUNT_OFFSET], 1
    jle interp_slow
    xor eax, eax
    test BYTE PTR [r8+QJS_ABI_BIT_JSObject_is_HTMLDDA_BYTE], QJS_ABI_BIT_JSObject_is_HTMLDDA_MASK
    sete al
JS_FrameTruthIfFalse8Clean_release:
    sub DWORD PTR [r8+QJS_ABI_REF_COUNT_OFFSET], 1
    test edx, 4
    jz JS_FrameTruthIfFalse8Clean_commit
    lock inc QWORD PTR [rip+JS_FrameOrdinaryLiteralStats+264]
JS_FrameTruthIfFalse8Clean_commit:
    sub r13, 16
    dec DWORD PTR [rsi+QJS_ABI_OFF_JSContext_interrupt_counter]
    test eax, eax
    jnz JS_FrameTruthIfFalse8Clean_untaken
    movsx rax, BYTE PTR [r12+1]
    lea r12, [r12+rax+1]
    jmp JS_FrameTruthIfFalse8Clean_dispatch
JS_FrameTruthIfFalse8Clean_untaken:
    add r12, 2
JS_FrameTruthIfFalse8Clean_dispatch:
    movzx eax, BYTE PTR [r12]
    jmp QWORD PTR [rdi+rax*8]
JS_FrameTruthIfFalse8Clean_number:
    cmp eax, 8
    jne interp_slow
    test edx, 65536
    jnz interp_slow
    pxor xmm0, xmm0
    ucomisd xmm0, QWORD PTR [r13-16]
    setne al
    movzx eax, al
    test edx, 4
    jz JS_FrameTruthIfFalse8Clean_number_commit
    lock inc QWORD PTR [rip+JS_FrameOrdinaryLiteralStats+264]
JS_FrameTruthIfFalse8Clean_number_commit:
    jmp JS_FrameTruthIfFalse8Clean_commit
JS_FrameTruthIfFalse8Clean_end:
.p2align 4
.globl JS_FrameTruthLnotDirty, JS_FrameTruthLnotDirty_end
.def JS_FrameTruthLnotDirty; .scl 2; .type 32; .endef
JS_FrameTruthLnotDirty:
    mov edx, DWORD PTR [rip+JS_FrameOrdinaryLiteralMode]
    test edx, edx
    jz dirty_interp_slow
    test edx, 32768
    jnz dirty_interp_slow
    mov eax, DWORD PTR [r13-8]
    cmp eax, -1
    je JS_FrameTruthLnotDirty_object
    cmp eax, -7
    je JS_FrameTruthLnotDirty_string
    cmp eax, -6
    jne JS_FrameTruthLnotDirty_number
    mov r8, QWORD PTR [r13-16]
    cmp DWORD PTR [r8+QJS_ABI_REF_COUNT_OFFSET], 1
    jle dirty_interp_slow
    xor eax, eax
    cmp DWORD PTR [r8+QJS_ABI_OFF_JSStringRope_len], 0
    setne al
    jmp JS_FrameTruthLnotDirty_release
JS_FrameTruthLnotDirty_string:
    mov r8, QWORD PTR [r13-16]
    cmp DWORD PTR [r8+QJS_ABI_REF_COUNT_OFFSET], 1
    jle dirty_interp_slow
    xor eax, eax
    test DWORD PTR [r8+QJS_ABI_BIT_JSString_len_BYTE], 2147483647
    setne al
    jmp JS_FrameTruthLnotDirty_release
JS_FrameTruthLnotDirty_object:
    mov r8, QWORD PTR [r13-16]
    cmp DWORD PTR [r8+QJS_ABI_REF_COUNT_OFFSET], 1
    jle dirty_interp_slow
    xor eax, eax
    test BYTE PTR [r8+QJS_ABI_BIT_JSObject_is_HTMLDDA_BYTE], QJS_ABI_BIT_JSObject_is_HTMLDDA_MASK
    sete al
JS_FrameTruthLnotDirty_release:
    sub DWORD PTR [r8+QJS_ABI_REF_COUNT_OFFSET], 1
    test edx, 4
    jz JS_FrameTruthLnotDirty_commit
    lock inc QWORD PTR [rip+JS_FrameOrdinaryLiteralStats+232]
JS_FrameTruthLnotDirty_commit:
    xor eax, 1
    mov QWORD PTR [r13-16], rax
    mov QWORD PTR [r13-8], 1
    inc r12
JS_FrameTruthLnotDirty_dispatch:
    movzx eax, BYTE PTR [r12]
    jmp QWORD PTR [rdi+rax*8]
JS_FrameTruthLnotDirty_number:
    cmp eax, 8
    jne dirty_interp_slow
    test edx, 65536
    jnz dirty_interp_slow
    pxor xmm0, xmm0
    ucomisd xmm0, QWORD PTR [r13-16]
    setne al
    movzx eax, al
    test edx, 4
    jz JS_FrameTruthLnotDirty_number_commit
    lock inc QWORD PTR [rip+JS_FrameOrdinaryLiteralStats+232]
JS_FrameTruthLnotDirty_number_commit:
    jmp JS_FrameTruthLnotDirty_commit
JS_FrameTruthLnotDirty_end:
.p2align 4
.globl JS_FrameTruthIfTrueDirty, JS_FrameTruthIfTrueDirty_end
.def JS_FrameTruthIfTrueDirty; .scl 2; .type 32; .endef
JS_FrameTruthIfTrueDirty:
    mov edx, DWORD PTR [rip+JS_FrameOrdinaryLiteralMode]
    test edx, edx
    jz dirty_interp_slow
    test edx, 32768
    jnz dirty_interp_slow
    mov eax, DWORD PTR [r13-8]
    cmp eax, -1
    je JS_FrameTruthIfTrueDirty_object
    cmp eax, -7
    je JS_FrameTruthIfTrueDirty_string
    cmp eax, -6
    jne JS_FrameTruthIfTrueDirty_number
    mov r8, QWORD PTR [r13-16]
    cmp DWORD PTR [r8+QJS_ABI_REF_COUNT_OFFSET], 1
    jle dirty_interp_slow
    xor eax, eax
    cmp DWORD PTR [r8+QJS_ABI_OFF_JSStringRope_len], 0
    setne al
    jmp JS_FrameTruthIfTrueDirty_release
JS_FrameTruthIfTrueDirty_string:
    mov r8, QWORD PTR [r13-16]
    cmp DWORD PTR [r8+QJS_ABI_REF_COUNT_OFFSET], 1
    jle dirty_interp_slow
    xor eax, eax
    test DWORD PTR [r8+QJS_ABI_BIT_JSString_len_BYTE], 2147483647
    setne al
    jmp JS_FrameTruthIfTrueDirty_release
JS_FrameTruthIfTrueDirty_object:
    mov r8, QWORD PTR [r13-16]
    cmp DWORD PTR [r8+QJS_ABI_REF_COUNT_OFFSET], 1
    jle dirty_interp_slow
    xor eax, eax
    test BYTE PTR [r8+QJS_ABI_BIT_JSObject_is_HTMLDDA_BYTE], QJS_ABI_BIT_JSObject_is_HTMLDDA_MASK
    sete al
JS_FrameTruthIfTrueDirty_release:
    sub DWORD PTR [r8+QJS_ABI_REF_COUNT_OFFSET], 1
    test edx, 4
    jz JS_FrameTruthIfTrueDirty_commit
    lock inc QWORD PTR [rip+JS_FrameOrdinaryLiteralStats+240]
JS_FrameTruthIfTrueDirty_commit:
    sub r13, 16
    dec DWORD PTR [rsi+QJS_ABI_OFF_JSContext_interrupt_counter]
    test eax, eax
    jz JS_FrameTruthIfTrueDirty_untaken
    movsxd rax, DWORD PTR [r12+1]
    lea r12, [r12+rax+1]
    jmp JS_FrameTruthIfTrueDirty_dispatch
JS_FrameTruthIfTrueDirty_untaken:
    add r12, 5
JS_FrameTruthIfTrueDirty_dispatch:
    movzx eax, BYTE PTR [r12]
    jmp QWORD PTR [rdi+rax*8]
JS_FrameTruthIfTrueDirty_number:
    cmp eax, 8
    jne dirty_interp_slow
    test edx, 65536
    jnz dirty_interp_slow
    pxor xmm0, xmm0
    ucomisd xmm0, QWORD PTR [r13-16]
    setne al
    movzx eax, al
    test edx, 4
    jz JS_FrameTruthIfTrueDirty_number_commit
    lock inc QWORD PTR [rip+JS_FrameOrdinaryLiteralStats+240]
JS_FrameTruthIfTrueDirty_number_commit:
    jmp JS_FrameTruthIfTrueDirty_commit
JS_FrameTruthIfTrueDirty_end:
.p2align 4
.globl JS_FrameTruthIfFalseDirty, JS_FrameTruthIfFalseDirty_end
.def JS_FrameTruthIfFalseDirty; .scl 2; .type 32; .endef
JS_FrameTruthIfFalseDirty:
    mov edx, DWORD PTR [rip+JS_FrameOrdinaryLiteralMode]
    test edx, edx
    jz dirty_interp_slow
    test edx, 32768
    jnz dirty_interp_slow
    mov eax, DWORD PTR [r13-8]
    cmp eax, -1
    je JS_FrameTruthIfFalseDirty_object
    cmp eax, -7
    je JS_FrameTruthIfFalseDirty_string
    cmp eax, -6
    jne JS_FrameTruthIfFalseDirty_number
    mov r8, QWORD PTR [r13-16]
    cmp DWORD PTR [r8+QJS_ABI_REF_COUNT_OFFSET], 1
    jle dirty_interp_slow
    xor eax, eax
    cmp DWORD PTR [r8+QJS_ABI_OFF_JSStringRope_len], 0
    setne al
    jmp JS_FrameTruthIfFalseDirty_release
JS_FrameTruthIfFalseDirty_string:
    mov r8, QWORD PTR [r13-16]
    cmp DWORD PTR [r8+QJS_ABI_REF_COUNT_OFFSET], 1
    jle dirty_interp_slow
    xor eax, eax
    test DWORD PTR [r8+QJS_ABI_BIT_JSString_len_BYTE], 2147483647
    setne al
    jmp JS_FrameTruthIfFalseDirty_release
JS_FrameTruthIfFalseDirty_object:
    mov r8, QWORD PTR [r13-16]
    cmp DWORD PTR [r8+QJS_ABI_REF_COUNT_OFFSET], 1
    jle dirty_interp_slow
    xor eax, eax
    test BYTE PTR [r8+QJS_ABI_BIT_JSObject_is_HTMLDDA_BYTE], QJS_ABI_BIT_JSObject_is_HTMLDDA_MASK
    sete al
JS_FrameTruthIfFalseDirty_release:
    sub DWORD PTR [r8+QJS_ABI_REF_COUNT_OFFSET], 1
    test edx, 4
    jz JS_FrameTruthIfFalseDirty_commit
    lock inc QWORD PTR [rip+JS_FrameOrdinaryLiteralStats+248]
JS_FrameTruthIfFalseDirty_commit:
    sub r13, 16
    dec DWORD PTR [rsi+QJS_ABI_OFF_JSContext_interrupt_counter]
    test eax, eax
    jnz JS_FrameTruthIfFalseDirty_untaken
    movsxd rax, DWORD PTR [r12+1]
    lea r12, [r12+rax+1]
    jmp JS_FrameTruthIfFalseDirty_dispatch
JS_FrameTruthIfFalseDirty_untaken:
    add r12, 5
JS_FrameTruthIfFalseDirty_dispatch:
    movzx eax, BYTE PTR [r12]
    jmp QWORD PTR [rdi+rax*8]
JS_FrameTruthIfFalseDirty_number:
    cmp eax, 8
    jne dirty_interp_slow
    test edx, 65536
    jnz dirty_interp_slow
    pxor xmm0, xmm0
    ucomisd xmm0, QWORD PTR [r13-16]
    setne al
    movzx eax, al
    test edx, 4
    jz JS_FrameTruthIfFalseDirty_number_commit
    lock inc QWORD PTR [rip+JS_FrameOrdinaryLiteralStats+248]
JS_FrameTruthIfFalseDirty_number_commit:
    jmp JS_FrameTruthIfFalseDirty_commit
JS_FrameTruthIfFalseDirty_end:
.p2align 4
.globl JS_FrameTruthIfTrue8Dirty, JS_FrameTruthIfTrue8Dirty_end
.def JS_FrameTruthIfTrue8Dirty; .scl 2; .type 32; .endef
JS_FrameTruthIfTrue8Dirty:
    mov edx, DWORD PTR [rip+JS_FrameOrdinaryLiteralMode]
    test edx, edx
    jz dirty_interp_slow
    test edx, 32768
    jnz dirty_interp_slow
    mov eax, DWORD PTR [r13-8]
    cmp eax, -1
    je JS_FrameTruthIfTrue8Dirty_object
    cmp eax, -7
    je JS_FrameTruthIfTrue8Dirty_string
    cmp eax, -6
    jne JS_FrameTruthIfTrue8Dirty_number
    mov r8, QWORD PTR [r13-16]
    cmp DWORD PTR [r8+QJS_ABI_REF_COUNT_OFFSET], 1
    jle dirty_interp_slow
    xor eax, eax
    cmp DWORD PTR [r8+QJS_ABI_OFF_JSStringRope_len], 0
    setne al
    jmp JS_FrameTruthIfTrue8Dirty_release
JS_FrameTruthIfTrue8Dirty_string:
    mov r8, QWORD PTR [r13-16]
    cmp DWORD PTR [r8+QJS_ABI_REF_COUNT_OFFSET], 1
    jle dirty_interp_slow
    xor eax, eax
    test DWORD PTR [r8+QJS_ABI_BIT_JSString_len_BYTE], 2147483647
    setne al
    jmp JS_FrameTruthIfTrue8Dirty_release
JS_FrameTruthIfTrue8Dirty_object:
    mov r8, QWORD PTR [r13-16]
    cmp DWORD PTR [r8+QJS_ABI_REF_COUNT_OFFSET], 1
    jle dirty_interp_slow
    xor eax, eax
    test BYTE PTR [r8+QJS_ABI_BIT_JSObject_is_HTMLDDA_BYTE], QJS_ABI_BIT_JSObject_is_HTMLDDA_MASK
    sete al
JS_FrameTruthIfTrue8Dirty_release:
    sub DWORD PTR [r8+QJS_ABI_REF_COUNT_OFFSET], 1
    test edx, 4
    jz JS_FrameTruthIfTrue8Dirty_commit
    lock inc QWORD PTR [rip+JS_FrameOrdinaryLiteralStats+256]
JS_FrameTruthIfTrue8Dirty_commit:
    sub r13, 16
    dec DWORD PTR [rsi+QJS_ABI_OFF_JSContext_interrupt_counter]
    test eax, eax
    jz JS_FrameTruthIfTrue8Dirty_untaken
    movsx rax, BYTE PTR [r12+1]
    lea r12, [r12+rax+1]
    jmp JS_FrameTruthIfTrue8Dirty_dispatch
JS_FrameTruthIfTrue8Dirty_untaken:
    add r12, 2
JS_FrameTruthIfTrue8Dirty_dispatch:
    movzx eax, BYTE PTR [r12]
    jmp QWORD PTR [rdi+rax*8]
JS_FrameTruthIfTrue8Dirty_number:
    cmp eax, 8
    jne dirty_interp_slow
    test edx, 65536
    jnz dirty_interp_slow
    pxor xmm0, xmm0
    ucomisd xmm0, QWORD PTR [r13-16]
    setne al
    movzx eax, al
    test edx, 4
    jz JS_FrameTruthIfTrue8Dirty_number_commit
    lock inc QWORD PTR [rip+JS_FrameOrdinaryLiteralStats+256]
JS_FrameTruthIfTrue8Dirty_number_commit:
    jmp JS_FrameTruthIfTrue8Dirty_commit
JS_FrameTruthIfTrue8Dirty_end:
.p2align 4
.globl JS_FrameTruthIfFalse8Dirty, JS_FrameTruthIfFalse8Dirty_end
.def JS_FrameTruthIfFalse8Dirty; .scl 2; .type 32; .endef
JS_FrameTruthIfFalse8Dirty:
    mov edx, DWORD PTR [rip+JS_FrameOrdinaryLiteralMode]
    test edx, edx
    jz dirty_interp_slow
    test edx, 32768
    jnz dirty_interp_slow
    mov eax, DWORD PTR [r13-8]
    cmp eax, -1
    je JS_FrameTruthIfFalse8Dirty_object
    cmp eax, -7
    je JS_FrameTruthIfFalse8Dirty_string
    cmp eax, -6
    jne JS_FrameTruthIfFalse8Dirty_number
    mov r8, QWORD PTR [r13-16]
    cmp DWORD PTR [r8+QJS_ABI_REF_COUNT_OFFSET], 1
    jle dirty_interp_slow
    xor eax, eax
    cmp DWORD PTR [r8+QJS_ABI_OFF_JSStringRope_len], 0
    setne al
    jmp JS_FrameTruthIfFalse8Dirty_release
JS_FrameTruthIfFalse8Dirty_string:
    mov r8, QWORD PTR [r13-16]
    cmp DWORD PTR [r8+QJS_ABI_REF_COUNT_OFFSET], 1
    jle dirty_interp_slow
    xor eax, eax
    test DWORD PTR [r8+QJS_ABI_BIT_JSString_len_BYTE], 2147483647
    setne al
    jmp JS_FrameTruthIfFalse8Dirty_release
JS_FrameTruthIfFalse8Dirty_object:
    mov r8, QWORD PTR [r13-16]
    cmp DWORD PTR [r8+QJS_ABI_REF_COUNT_OFFSET], 1
    jle dirty_interp_slow
    xor eax, eax
    test BYTE PTR [r8+QJS_ABI_BIT_JSObject_is_HTMLDDA_BYTE], QJS_ABI_BIT_JSObject_is_HTMLDDA_MASK
    sete al
JS_FrameTruthIfFalse8Dirty_release:
    sub DWORD PTR [r8+QJS_ABI_REF_COUNT_OFFSET], 1
    test edx, 4
    jz JS_FrameTruthIfFalse8Dirty_commit
    lock inc QWORD PTR [rip+JS_FrameOrdinaryLiteralStats+264]
JS_FrameTruthIfFalse8Dirty_commit:
    sub r13, 16
    dec DWORD PTR [rsi+QJS_ABI_OFF_JSContext_interrupt_counter]
    test eax, eax
    jnz JS_FrameTruthIfFalse8Dirty_untaken
    movsx rax, BYTE PTR [r12+1]
    lea r12, [r12+rax+1]
    jmp JS_FrameTruthIfFalse8Dirty_dispatch
JS_FrameTruthIfFalse8Dirty_untaken:
    add r12, 2
JS_FrameTruthIfFalse8Dirty_dispatch:
    movzx eax, BYTE PTR [r12]
    jmp QWORD PTR [rdi+rax*8]
JS_FrameTruthIfFalse8Dirty_number:
    cmp eax, 8
    jne dirty_interp_slow
    test edx, 65536
    jnz dirty_interp_slow
    pxor xmm0, xmm0
    ucomisd xmm0, QWORD PTR [r13-16]
    setne al
    movzx eax, al
    test edx, 4
    jz JS_FrameTruthIfFalse8Dirty_number_commit
    lock inc QWORD PTR [rip+JS_FrameOrdinaryLiteralStats+264]
JS_FrameTruthIfFalse8Dirty_number_commit:
    jmp JS_FrameTruthIfFalse8Dirty_commit
JS_FrameTruthIfFalse8Dirty_end:
.p2align 2
ordinary_literal_unwind:
.byte 33,0,0,0
.rva JS_FrameInterpUnscoped, JS_FrameInterp_end, JS_FrameInterp_unwind
.section .pdata$zzzzzznullfast,"dr"
.p2align 2
.rva JS_FrameOrdinaryLiteralOpClean, JS_FrameOrdinaryLiteralOpClean_end, ordinary_literal_unwind
.rva JS_FrameOrdinaryLiteralOpDirty, JS_FrameOrdinaryLiteralOpDirty_end, ordinary_literal_unwind
.rva JS_FrameStackInsert2Clean, JS_FrameStackInsert2Clean_end, ordinary_literal_unwind
.rva JS_FrameStackInsert2Dirty, JS_FrameStackInsert2Dirty_end, ordinary_literal_unwind
.rva JS_FrameTypeofValueClean, JS_FrameTypeofValueClean_end, ordinary_literal_unwind
.rva JS_FrameTypeofFunctionClean, JS_FrameTypeofFunctionClean_end, ordinary_literal_unwind
.rva JS_FrameTypeofUndefinedClean, JS_FrameTypeofUndefinedClean_end, ordinary_literal_unwind
.rva JS_FrameTypeofValueDirty, JS_FrameTypeofValueDirty_end, ordinary_literal_unwind
.rva JS_FrameTypeofFunctionDirty, JS_FrameTypeofFunctionDirty_end, ordinary_literal_unwind
.rva JS_FrameTypeofUndefinedDirty, JS_FrameTypeofUndefinedDirty_end, ordinary_literal_unwind
.rva JS_FramePredicateClassify, JS_FramePredicateClassify_end, ordinary_literal_unwind
.rva JS_FramePredicateValue, JS_FramePredicateValue_end, ordinary_literal_unwind
.rva JS_FrameTruthLnotClean, JS_FrameTruthLnotClean_end, ordinary_literal_unwind
.rva JS_FrameTruthIfTrueClean, JS_FrameTruthIfTrueClean_end, ordinary_literal_unwind
.rva JS_FrameTruthIfFalseClean, JS_FrameTruthIfFalseClean_end, ordinary_literal_unwind
.rva JS_FrameTruthIfTrue8Clean, JS_FrameTruthIfTrue8Clean_end, ordinary_literal_unwind
.rva JS_FrameTruthIfFalse8Clean, JS_FrameTruthIfFalse8Clean_end, ordinary_literal_unwind
.rva JS_FrameTruthLnotDirty, JS_FrameTruthLnotDirty_end, ordinary_literal_unwind
.rva JS_FrameTruthIfTrueDirty, JS_FrameTruthIfTrueDirty_end, ordinary_literal_unwind
.rva JS_FrameTruthIfFalseDirty, JS_FrameTruthIfFalseDirty_end, ordinary_literal_unwind
.rva JS_FrameTruthIfTrue8Dirty, JS_FrameTruthIfTrue8Dirty_end, ordinary_literal_unwind
.rva JS_FrameTruthIfFalse8Dirty, JS_FrameTruthIfFalse8Dirty_end, ordinary_literal_unwind
