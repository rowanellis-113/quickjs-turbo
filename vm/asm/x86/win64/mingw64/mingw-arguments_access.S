.include "interpreter-private-abi-gas.inc"
.intel_syntax noprefix
.section .qjzzpc,"xr"
.p2align 4
.globl JS_FrameArgumentsGetClean, JS_FrameArgumentsGetClean_end
.def JS_FrameArgumentsGetClean; .scl 2; .type 32; .endef
JS_FrameArgumentsGetClean:
    test BYTE PTR [rip+JS_FrameArgumentsMode], 1
    jz interp_slow
    test BYTE PTR [rip+JS_FrameArgumentsMode], 96
    jnz interp_slow
    test BYTE PTR [r8+QJS_ABI_BIT_JSObject_fast_array_BYTE], QJS_ABI_BIT_JSObject_fast_array_MASK
    jz interp_slow
    cmp WORD PTR [r8+QJS_ABI_OFF_JSObject_class_id], 8
    je js_frameargumentsgetclean_plain
    cmp WORD PTR [r8+QJS_ABI_OFF_JSObject_class_id], 9
    jne interp_slow
    mov r10, QWORD PTR [r8+QJS_ABI_OFF_JSObject_u_array_u_values]
    mov r10, QWORD PTR [r10+rcx*8]
    test r10, r10
    jz interp_slow
    mov r10, QWORD PTR [r10+QJS_ABI_OFF_JSVarRef_pvalue]
    test r10, r10
    jz interp_slow
    jmp js_frameargumentsgetclean_slot
js_frameargumentsgetclean_plain:
    mov r10, QWORD PTR [r8+QJS_ABI_OFF_JSObject_u_array_u_values]
    shl rcx, 4
    add r10, rcx
js_frameargumentsgetclean_slot:
    mov rax, QWORD PTR [r10]
    mov rdx, QWORD PTR [r10+8]
    test edx, edx
    jns js_frameargumentsgetclean_value
    inc DWORD PTR [rax+QJS_ABI_REF_COUNT_OFFSET]
js_frameargumentsgetclean_value:
    test BYTE PTR [rip+JS_FrameArgumentsMode], 4
    jz js_frameargumentsgetclean_counted
    lock inc QWORD PTR [rip+JS_FrameArgumentsAccessStats+0]
js_frameargumentsgetclean_counted:
    dec DWORD PTR [r8+QJS_ABI_REF_COUNT_OFFSET]
    mov QWORD PTR [r13-32], rax
    mov QWORD PTR [r13-24], rdx
    sub r13, 16
    inc r12
    movzx eax, BYTE PTR [r12]
    jmp QWORD PTR [rdi+rax*8]
JS_FrameArgumentsGetClean_end:
.p2align 4
.globl JS_FrameArgumentsGet2Clean, JS_FrameArgumentsGet2Clean_end
.def JS_FrameArgumentsGet2Clean; .scl 2; .type 32; .endef
JS_FrameArgumentsGet2Clean:
    test BYTE PTR [rip+JS_FrameArgumentsMode], 1
    jz interp_slow
    test BYTE PTR [rip+JS_FrameArgumentsMode], 96
    jnz interp_slow
    test BYTE PTR [r8+QJS_ABI_BIT_JSObject_fast_array_BYTE], QJS_ABI_BIT_JSObject_fast_array_MASK
    jz interp_slow
    cmp WORD PTR [r8+QJS_ABI_OFF_JSObject_class_id], 8
    je js_frameargumentsget2clean_plain
    cmp WORD PTR [r8+QJS_ABI_OFF_JSObject_class_id], 9
    jne interp_slow
    mov r10, QWORD PTR [r8+QJS_ABI_OFF_JSObject_u_array_u_values]
    mov r10, QWORD PTR [r10+rcx*8]
    test r10, r10
    jz interp_slow
    mov r10, QWORD PTR [r10+QJS_ABI_OFF_JSVarRef_pvalue]
    test r10, r10
    jz interp_slow
    jmp js_frameargumentsget2clean_slot
js_frameargumentsget2clean_plain:
    mov r10, QWORD PTR [r8+QJS_ABI_OFF_JSObject_u_array_u_values]
    shl rcx, 4
    add r10, rcx
js_frameargumentsget2clean_slot:
    mov rax, QWORD PTR [r10]
    mov rdx, QWORD PTR [r10+8]
    test edx, edx
    jns js_frameargumentsget2clean_value
    inc DWORD PTR [rax+QJS_ABI_REF_COUNT_OFFSET]
js_frameargumentsget2clean_value:
    test BYTE PTR [rip+JS_FrameArgumentsMode], 4
    jz js_frameargumentsget2clean_counted
    lock inc QWORD PTR [rip+JS_FrameArgumentsAccessStats+8]
js_frameargumentsget2clean_counted:
    mov QWORD PTR [r13-16], rax
    mov QWORD PTR [r13-8], rdx
    inc r12
    movzx eax, BYTE PTR [r12]
    jmp QWORD PTR [rdi+rax*8]
JS_FrameArgumentsGet2Clean_end:
.p2align 4
.globl JS_FrameArgumentsPutClean, JS_FrameArgumentsPutClean_end
.def JS_FrameArgumentsPutClean; .scl 2; .type 32; .endef
JS_FrameArgumentsPutClean:
    test BYTE PTR [rip+JS_FrameArgumentsMode], 1
    jz interp_slow
    test BYTE PTR [rip+JS_FrameArgumentsMode], 96
    jnz interp_slow
    test BYTE PTR [r8+QJS_ABI_BIT_JSObject_fast_array_BYTE], QJS_ABI_BIT_JSObject_fast_array_MASK
    jz interp_slow
    cmp WORD PTR [r8+QJS_ABI_OFF_JSObject_class_id], 8
    je js_frameargumentsputclean_plain
    cmp WORD PTR [r8+QJS_ABI_OFF_JSObject_class_id], 9
    jne interp_slow
    cmp DWORD PTR [r8+QJS_ABI_REF_COUNT_OFFSET], 1
    jle interp_slow
    mov ecx, DWORD PTR [r13-32]
    cmp ecx, DWORD PTR [r8+QJS_ABI_OFF_JSObject_u_array_count]
    jae interp_slow
    mov r10, QWORD PTR [r8+QJS_ABI_OFF_JSObject_u_array_u_values]
    mov r10, QWORD PTR [r10+rcx*8]
    test r10, r10
    jz interp_slow
    mov r10, QWORD PTR [r10+QJS_ABI_OFF_JSVarRef_pvalue]
    test r10, r10
    jz interp_slow
    jmp js_frameargumentsputclean_slot
js_frameargumentsputclean_plain:
    cmp DWORD PTR [r8+QJS_ABI_REF_COUNT_OFFSET], 1
    jle interp_slow
    mov ecx, DWORD PTR [r13-32]
    cmp ecx, DWORD PTR [r8+QJS_ABI_OFF_JSObject_u_array_count]
    jae interp_slow
    mov r10, QWORD PTR [r8+QJS_ABI_OFF_JSObject_u_array_u_values]
    shl rcx, 4
    add r10, rcx
js_frameargumentsputclean_slot:
    cmp QWORD PTR [r10+8], 0
    jge js_frameargumentsputclean_store
    mov r11, QWORD PTR [r10]
    cmp r11, r8
    je interp_slow
    cmp DWORD PTR [r11+QJS_ABI_REF_COUNT_OFFSET], 1
    jle interp_slow
    dec DWORD PTR [r11+QJS_ABI_REF_COUNT_OFFSET]
js_frameargumentsputclean_store:
    mov rax, QWORD PTR [r13-16]
    mov rdx, QWORD PTR [r13-8]
    mov QWORD PTR [r10], rax
    mov QWORD PTR [r10+8], rdx
    test BYTE PTR [rip+JS_FrameArgumentsMode], 4
    jz js_frameargumentsputclean_counted
    lock inc QWORD PTR [rip+JS_FrameArgumentsAccessStats+16]
js_frameargumentsputclean_counted:
    dec DWORD PTR [r8+QJS_ABI_REF_COUNT_OFFSET]
    sub r13, 48
    inc r12
    movzx eax, BYTE PTR [r12]
    jmp QWORD PTR [rdi+rax*8]
JS_FrameArgumentsPutClean_end:
.p2align 4
.globl JS_FrameArgumentsGetDirty, JS_FrameArgumentsGetDirty_end
.def JS_FrameArgumentsGetDirty; .scl 2; .type 32; .endef
JS_FrameArgumentsGetDirty:
    test BYTE PTR [rip+JS_FrameArgumentsMode], 1
    jz dirty_interp_slow
    test BYTE PTR [rip+JS_FrameArgumentsMode], 96
    jnz dirty_interp_slow
    test BYTE PTR [r8+QJS_ABI_BIT_JSObject_fast_array_BYTE], QJS_ABI_BIT_JSObject_fast_array_MASK
    jz dirty_interp_slow
    cmp WORD PTR [r8+QJS_ABI_OFF_JSObject_class_id], 8
    je js_frameargumentsgetdirty_plain
    cmp WORD PTR [r8+QJS_ABI_OFF_JSObject_class_id], 9
    jne dirty_interp_slow
    mov r10, QWORD PTR [r8+QJS_ABI_OFF_JSObject_u_array_u_values]
    mov r10, QWORD PTR [r10+rcx*8]
    test r10, r10
    jz dirty_interp_slow
    mov r10, QWORD PTR [r10+QJS_ABI_OFF_JSVarRef_pvalue]
    test r10, r10
    jz dirty_interp_slow
    jmp js_frameargumentsgetdirty_slot
js_frameargumentsgetdirty_plain:
    mov r10, QWORD PTR [r8+QJS_ABI_OFF_JSObject_u_array_u_values]
    shl rcx, 4
    add r10, rcx
js_frameargumentsgetdirty_slot:
    mov rax, QWORD PTR [r10]
    mov rdx, QWORD PTR [r10+8]
    test edx, edx
    jns js_frameargumentsgetdirty_value
    inc DWORD PTR [rax+QJS_ABI_REF_COUNT_OFFSET]
js_frameargumentsgetdirty_value:
    test BYTE PTR [rip+JS_FrameArgumentsMode], 4
    jz js_frameargumentsgetdirty_counted
    lock inc QWORD PTR [rip+JS_FrameArgumentsAccessStats+0]
js_frameargumentsgetdirty_counted:
    dec DWORD PTR [r8+QJS_ABI_REF_COUNT_OFFSET]
    mov QWORD PTR [r13-32], rax
    mov QWORD PTR [r13-24], rdx
    sub r13, 16
    inc r12
    movzx eax, BYTE PTR [r12]
    jmp QWORD PTR [rdi+rax*8]
JS_FrameArgumentsGetDirty_end:
.p2align 4
.globl JS_FrameArgumentsGet2Dirty, JS_FrameArgumentsGet2Dirty_end
.def JS_FrameArgumentsGet2Dirty; .scl 2; .type 32; .endef
JS_FrameArgumentsGet2Dirty:
    test BYTE PTR [rip+JS_FrameArgumentsMode], 1
    jz dirty_interp_slow
    test BYTE PTR [rip+JS_FrameArgumentsMode], 96
    jnz dirty_interp_slow
    test BYTE PTR [r8+QJS_ABI_BIT_JSObject_fast_array_BYTE], QJS_ABI_BIT_JSObject_fast_array_MASK
    jz dirty_interp_slow
    cmp WORD PTR [r8+QJS_ABI_OFF_JSObject_class_id], 8
    je js_frameargumentsget2dirty_plain
    cmp WORD PTR [r8+QJS_ABI_OFF_JSObject_class_id], 9
    jne dirty_interp_slow
    mov r10, QWORD PTR [r8+QJS_ABI_OFF_JSObject_u_array_u_values]
    mov r10, QWORD PTR [r10+rcx*8]
    test r10, r10
    jz dirty_interp_slow
    mov r10, QWORD PTR [r10+QJS_ABI_OFF_JSVarRef_pvalue]
    test r10, r10
    jz dirty_interp_slow
    jmp js_frameargumentsget2dirty_slot
js_frameargumentsget2dirty_plain:
    mov r10, QWORD PTR [r8+QJS_ABI_OFF_JSObject_u_array_u_values]
    shl rcx, 4
    add r10, rcx
js_frameargumentsget2dirty_slot:
    mov rax, QWORD PTR [r10]
    mov rdx, QWORD PTR [r10+8]
    test edx, edx
    jns js_frameargumentsget2dirty_value
    inc DWORD PTR [rax+QJS_ABI_REF_COUNT_OFFSET]
js_frameargumentsget2dirty_value:
    test BYTE PTR [rip+JS_FrameArgumentsMode], 4
    jz js_frameargumentsget2dirty_counted
    lock inc QWORD PTR [rip+JS_FrameArgumentsAccessStats+8]
js_frameargumentsget2dirty_counted:
    mov QWORD PTR [r13-16], rax
    mov QWORD PTR [r13-8], rdx
    inc r12
    movzx eax, BYTE PTR [r12]
    jmp QWORD PTR [rdi+rax*8]
JS_FrameArgumentsGet2Dirty_end:
.p2align 4
.globl JS_FrameArgumentsPutDirty, JS_FrameArgumentsPutDirty_end
.def JS_FrameArgumentsPutDirty; .scl 2; .type 32; .endef
JS_FrameArgumentsPutDirty:
    test BYTE PTR [rip+JS_FrameArgumentsMode], 1
    jz dirty_interp_slow
    test BYTE PTR [rip+JS_FrameArgumentsMode], 96
    jnz dirty_interp_slow
    test BYTE PTR [r8+QJS_ABI_BIT_JSObject_fast_array_BYTE], QJS_ABI_BIT_JSObject_fast_array_MASK
    jz dirty_interp_slow
    cmp WORD PTR [r8+QJS_ABI_OFF_JSObject_class_id], 8
    je js_frameargumentsputdirty_plain
    cmp WORD PTR [r8+QJS_ABI_OFF_JSObject_class_id], 9
    jne dirty_interp_slow
    cmp DWORD PTR [r8+QJS_ABI_REF_COUNT_OFFSET], 1
    jle dirty_interp_slow
    mov ecx, DWORD PTR [r13-32]
    cmp ecx, DWORD PTR [r8+QJS_ABI_OFF_JSObject_u_array_count]
    jae dirty_interp_slow
    mov r10, QWORD PTR [r8+QJS_ABI_OFF_JSObject_u_array_u_values]
    mov r10, QWORD PTR [r10+rcx*8]
    test r10, r10
    jz dirty_interp_slow
    mov r10, QWORD PTR [r10+QJS_ABI_OFF_JSVarRef_pvalue]
    test r10, r10
    jz dirty_interp_slow
    jmp js_frameargumentsputdirty_slot
js_frameargumentsputdirty_plain:
    cmp DWORD PTR [r8+QJS_ABI_REF_COUNT_OFFSET], 1
    jle dirty_interp_slow
    mov ecx, DWORD PTR [r13-32]
    cmp ecx, DWORD PTR [r8+QJS_ABI_OFF_JSObject_u_array_count]
    jae dirty_interp_slow
    mov r10, QWORD PTR [r8+QJS_ABI_OFF_JSObject_u_array_u_values]
    shl rcx, 4
    add r10, rcx
js_frameargumentsputdirty_slot:
    cmp QWORD PTR [r10+8], 0
    jge js_frameargumentsputdirty_store
    mov r11, QWORD PTR [r10]
    cmp r11, r8
    je dirty_interp_slow
    cmp DWORD PTR [r11+QJS_ABI_REF_COUNT_OFFSET], 1
    jle dirty_interp_slow
    dec DWORD PTR [r11+QJS_ABI_REF_COUNT_OFFSET]
js_frameargumentsputdirty_store:
    mov rax, QWORD PTR [r13-16]
    mov rdx, QWORD PTR [r13-8]
    mov QWORD PTR [r10], rax
    mov QWORD PTR [r10+8], rdx
    test BYTE PTR [rip+JS_FrameArgumentsMode], 4
    jz js_frameargumentsputdirty_counted
    lock inc QWORD PTR [rip+JS_FrameArgumentsAccessStats+16]
js_frameargumentsputdirty_counted:
    dec DWORD PTR [r8+QJS_ABI_REF_COUNT_OFFSET]
    sub r13, 48
    inc r12
    movzx eax, BYTE PTR [r12]
    jmp QWORD PTR [rdi+rax*8]
JS_FrameArgumentsPutDirty_end:
.p2align 4
.globl JS_FrameArgumentsLengthClean, JS_FrameArgumentsLengthClean_end
.def JS_FrameArgumentsLengthClean; .scl 2; .type 32; .endef
JS_FrameArgumentsLengthClean:
    test BYTE PTR [rip+JS_FrameArgumentsMode], 1
    jz interp_slow
    test BYTE PTR [rip+JS_FrameArgumentsMode], 160
    jnz interp_slow
    cmp BYTE PTR [rip+JS_FrameLengthData], 1
    jne interp_slow
    cmp QWORD PTR [r13-8], -1
    jne interp_slow
    mov r8, QWORD PTR [r13-16]
    movzx eax, WORD PTR [r8+QJS_ABI_OFF_JSObject_class_id]
    sub eax, 8
    cmp eax, 1
    ja interp_slow
    cmp DWORD PTR [r8+QJS_ABI_REF_COUNT_OFFSET], 1
    jle interp_slow
    mov r10, QWORD PTR [r8+QJS_ABI_OFF_JSObject_shape]
    cmp DWORD PTR [r10+QJS_ABI_OFF_JSShape_prop_count], 1
    jb interp_slow
.if QJS_ABI_HAS_PREFIX_RC
    mov ecx, DWORD PTR [r10+QJS_ABI_OFF_JSShape_prop_hash_mask]
    lea r10, [r10+rcx*4+QJS_ABI_SIZE_JSShape+4]
.else
    lea r10, [r10+QJS_ABI_OFF_JSShape_prop]
.endif
    cmp DWORD PTR [r10+4], 51
    jne interp_slow
    test DWORD PTR [r10], 0xc0000000
    jnz interp_slow
    mov r10, QWORD PTR [r8+QJS_ABI_OFF_JSObject_prop]
    mov rax, QWORD PTR [r10]
    mov rdx, QWORD PTR [r10+8]
    test rdx, rdx
    jz js_frameargumentslengthclean_value
    cmp rdx, 8
    jne interp_slow
js_frameargumentslengthclean_value:
    test BYTE PTR [rip+JS_FrameArgumentsMode], 4
    jz js_frameargumentslengthclean_counted
    lock inc QWORD PTR [rip+JS_FrameArgumentsAccessStats+24]
js_frameargumentslengthclean_counted:
    dec DWORD PTR [r8+QJS_ABI_REF_COUNT_OFFSET]
    mov QWORD PTR [r13-16], rax
    mov QWORD PTR [r13-8], rdx
    inc r12
    movzx eax, BYTE PTR [r12]
    jmp QWORD PTR [rdi+rax*8]
JS_FrameArgumentsLengthClean_end:
.p2align 4
.globl JS_FrameArgumentsLengthDirty, JS_FrameArgumentsLengthDirty_end
.def JS_FrameArgumentsLengthDirty; .scl 2; .type 32; .endef
JS_FrameArgumentsLengthDirty:
    test BYTE PTR [rip+JS_FrameArgumentsMode], 1
    jz dirty_interp_slow
    test BYTE PTR [rip+JS_FrameArgumentsMode], 160
    jnz dirty_interp_slow
    cmp BYTE PTR [rip+JS_FrameLengthData], 1
    jne dirty_interp_slow
    cmp QWORD PTR [r13-8], -1
    jne dirty_interp_slow
    mov r8, QWORD PTR [r13-16]
    movzx eax, WORD PTR [r8+QJS_ABI_OFF_JSObject_class_id]
    sub eax, 8
    cmp eax, 1
    ja dirty_interp_slow
    cmp DWORD PTR [r8+QJS_ABI_REF_COUNT_OFFSET], 1
    jle dirty_interp_slow
    mov r10, QWORD PTR [r8+QJS_ABI_OFF_JSObject_shape]
    cmp DWORD PTR [r10+QJS_ABI_OFF_JSShape_prop_count], 1
    jb dirty_interp_slow
.if QJS_ABI_HAS_PREFIX_RC
    mov ecx, DWORD PTR [r10+QJS_ABI_OFF_JSShape_prop_hash_mask]
    lea r10, [r10+rcx*4+QJS_ABI_SIZE_JSShape+4]
.else
    lea r10, [r10+QJS_ABI_OFF_JSShape_prop]
.endif
    cmp DWORD PTR [r10+4], 51
    jne dirty_interp_slow
    test DWORD PTR [r10], 0xc0000000
    jnz dirty_interp_slow
    mov r10, QWORD PTR [r8+QJS_ABI_OFF_JSObject_prop]
    mov rax, QWORD PTR [r10]
    mov rdx, QWORD PTR [r10+8]
    test rdx, rdx
    jz js_frameargumentslengthdirty_value
    cmp rdx, 8
    jne dirty_interp_slow
js_frameargumentslengthdirty_value:
    test BYTE PTR [rip+JS_FrameArgumentsMode], 4
    jz js_frameargumentslengthdirty_counted
    lock inc QWORD PTR [rip+JS_FrameArgumentsAccessStats+24]
js_frameargumentslengthdirty_counted:
    dec DWORD PTR [r8+QJS_ABI_REF_COUNT_OFFSET]
    mov QWORD PTR [r13-16], rax
    mov QWORD PTR [r13-8], rdx
    inc r12
    movzx eax, BYTE PTR [r12]
    jmp QWORD PTR [rdi+rax*8]
JS_FrameArgumentsLengthDirty_end:
.p2align 2
arguments_access_unwind:
.byte 33,0,0,0
.rva JS_FrameInterpUnscoped, JS_FrameInterp_end, JS_FrameInterp_unwind
.section .pdata$zzzzzznullfast,"dr"
.p2align 2
.rva JS_FrameArgumentsGetClean, JS_FrameArgumentsGetClean_end, arguments_access_unwind
.rva JS_FrameArgumentsGet2Clean, JS_FrameArgumentsGet2Clean_end, arguments_access_unwind
.rva JS_FrameArgumentsPutClean, JS_FrameArgumentsPutClean_end, arguments_access_unwind
.rva JS_FrameArgumentsGetDirty, JS_FrameArgumentsGetDirty_end, arguments_access_unwind
.rva JS_FrameArgumentsGet2Dirty, JS_FrameArgumentsGet2Dirty_end, arguments_access_unwind
.rva JS_FrameArgumentsPutDirty, JS_FrameArgumentsPutDirty_end, arguments_access_unwind
.rva JS_FrameArgumentsLengthClean, JS_FrameArgumentsLengthClean_end, arguments_access_unwind
.rva JS_FrameArgumentsLengthDirty, JS_FrameArgumentsLengthDirty_end, arguments_access_unwind
