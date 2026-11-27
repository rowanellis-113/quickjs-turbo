/* Real SysV generic/magic call, with a fixed CFA across dynamic argv padding.
* @...@ values are rendered from the actual Linux compiler layout. MIT. */
.section .text.qjs_linux_c_invoke,"ax",@progbits
.p2align 4
.globl qjs_linux_c_invoke_private
.hidden qjs_linux_c_invoke_private, JS_LinuxCInvokeControl
.type qjs_linux_c_invoke_private,@function
qjs_linux_c_invoke_private:
.cfi_startproc
    endbr64
    cmp QWORD PTR [rsp+72], 1
    ja linux_c_invoke_guard
    je linux_c_invoke_fallback
/* The root's unused scratch0..31 saves volatile private input registers.
* Align this real CALL, and retain its caller's complete CFI. */
    sub rsp, 8
.cfi_adjust_cfa_offset 8
    mov QWORD PTR [rsp+16], rdx
    mov DWORD PTR [rsp+24], r8d
    mov DWORD PTR [rsp+28], r9d
    mov rcx, rbx
    call @INIT_BRIDGE@
    mov rdx, QWORD PTR [rsp+16]
    mov r8d, DWORD PTR [rsp+24]
    mov r9d, DWORD PTR [rsp+28]
    test rax, rax
    jz linux_c_invoke_scope_disabled
    mov QWORD PTR [rsp+80], rax
/* One anchor for this VM activation, blocked between coherent host calls.
* The input saves have been consumed before their root scratch is reused. */
    mov r10, QWORD PTR [rax]
    mov QWORD PTR [rsp+16], r10
    mov QWORD PTR [rsp+24], rbx
    mov DWORD PTR [rsp+32], 3
    lea r10, [rsp+16]
    mov QWORD PTR [rax], r10
    jmp linux_c_invoke_scope_ready
linux_c_invoke_scope_disabled:
    mov QWORD PTR [rsp+80], 1
linux_c_invoke_scope_ready:
    mov rcx, rbx
    add rsp, 8
.cfi_adjust_cfa_offset -8
    cmp QWORD PTR [rsp+72], 1
    je linux_c_invoke_fallback
/* Revalidate after initialization, before retaining any callee metadata. */
    cmp QWORD PTR [rdx-8], @TAG_OBJECT@
    jne linux_c_invoke_generic_fallback
    mov rax, QWORD PTR [rdx-16]
    cmp WORD PTR [rax+@OBJ_CLASS@], @CLASS_C_FUNCTION@
    jne linux_c_invoke_generic_fallback
    cmp BYTE PTR [rax+@OBJ_CPROTO@], @CPROTO_MAGIC@
    jbe linux_c_invoke_guard
    cmp BYTE PTR [rax+@OBJ_CPROTO@], @CPROTO_UNARY@
    je linux_c_invoke_guard
    cmp BYTE PTR [rax+@OBJ_CPROTO@], @CPROTO_BINARY@
    jne linux_c_invoke_generic_fallback
linux_c_invoke_guard:
    mov r10, QWORD PTR [rbx+56]
    mov rcx, QWORD PTR [rbx+32]
    cmp rcx, QWORD PTR [rbx+64]
    jne linux_c_invoke_fallback
    mov rcx, QWORD PTR [rbx]
    cmp QWORD PTR [r10+@RT_SF@], rcx
    jne linux_c_invoke_fallback
    cmp DWORD PTR [rsi+@CTX_INTERRUPT@], 1
    jle linux_c_invoke_fallback
    mov rax, QWORD PTR [rdx-16]
    mov rcx, QWORD PTR [rax+@OBJ_REALM@]
    cmp QWORD PTR [rcx+@CTX_RT@], r10
    jne linux_c_invoke_fallback
    movzx ecx, BYTE PTR [rax+@OBJ_LENGTH@]
    cmp BYTE PTR [rax+@OBJ_CPROTO@], @CPROTO_MAGIC@
    ja linux_c_numeric_guard
/* Borrowed builtin views share the checked C boundary and its caller poll. */
    cmp WORD PTR [rax+@OBJ_LENGTH@], 2
    je linux_c_builtin_slice
    cmp WORD PTR [rax+@OBJ_LENGTH@], 257
    jne linux_c_minmax_check
    test r8d, r8d
    jnz linux_c_builtin_miss
    cmp WORD PTR [rax+@OBJ_MAGIC@], 0
    jne linux_c_builtin_miss
    test BYTE PTR [rip+JS_LinuxBuiltinControl], 32
    jnz linux_c_builtin_miss
    mov r11, QWORD PTR [rip+JS_LinuxBuiltinTargets+8]
    jmp linux_c_builtin_identity
linux_c_minmax_check:
    cmp WORD PTR [rax+@OBJ_LENGTH@], 258
    jne linux_c_builtin_miss
    cmp r8d, 2
    jne linux_c_builtin_miss
    lea r11, [rip+qjs_linux_core_js_math_min_max]
    cmp QWORD PTR [rax+@OBJ_FUNCTION@], r11
    jne linux_c_builtin_miss
    cmp QWORD PTR [rdx+8], @TAG_INT@
    jne linux_c_builtin_miss
    cmp QWORD PTR [rdx+24], @TAG_INT@
    jne linux_c_builtin_miss
    cmp QWORD PTR [r10+@RT_LIMIT@], 0
    je qjs_linux_math_minmax_private
    lea r11, [rsp-368]
    cmp r11, QWORD PTR [r10+@RT_LIMIT@]
    jae qjs_linux_math_minmax_private
    jmp linux_c_builtin_miss
linux_c_builtin_slice:
    mov r11, QWORD PTR [rip+JS_LinuxBuiltinTargets]
    cmp QWORD PTR [rax+@OBJ_FUNCTION@], r11
    je linux_c_builtin_matched
    cmp r8d, 2
    jne linux_c_builtin_miss
    lea r11, [rip+qjs_linux_core_js_math_imul]
    cmp QWORD PTR [rax+@OBJ_FUNCTION@], r11
    jne linux_c_builtin_miss
    cmp QWORD PTR [rdx+8], @TAG_INT@
    jne linux_c_builtin_miss
    cmp QWORD PTR [rdx+24], @TAG_INT@
    jne linux_c_builtin_miss
    cmp QWORD PTR [r10+@RT_LIMIT@], 0
    je qjs_linux_math_imul_private
    lea r11, [rsp-368]
    cmp r11, QWORD PTR [r10+@RT_LIMIT@]
    jae qjs_linux_math_imul_private
    jmp linux_c_builtin_miss
linux_c_builtin_identity:
    cmp QWORD PTR [rax+@OBJ_FUNCTION@], r11
    jne linux_c_builtin_miss
linux_c_builtin_matched:
    movzx r11d, BYTE PTR [rip+JS_LinuxBuiltinControl]
    and r11d, 7
    cmp r11d, 2
    je linux_c_builtin_miss
    cmp r8d, 65535
    ja linux_c_invoke_generic_fallback
    cmp QWORD PTR [r10+@RT_LIMIT@], 0
    je linux_c_builtin_admit
    lea r10, [rsp-512]
    mov rax, QWORD PTR [rbx+56]
    cmp r10, QWORD PTR [rax+@RT_LIMIT@]
    jb linux_c_invoke_generic_fallback
linux_c_builtin_admit:
    cmp r11d, 3
    je qjs_linux_builtin_stack_private
    cmp r11d, 1
    jne qjs_linux_builtin_prepare_private
    mov r10, QWORD PTR [rbx]
    cmp r10, QWORD PTR [rbx+96]
    jne qjs_linux_builtin_prepare_private
    test BYTE PTR [r10+63], 1
    jz qjs_linux_builtin_prepare_private
    mov r11, QWORD PTR [rbx+88]
/* Argument padding may reuse every inactive window byte. Release ownership
* is per invocation, not cached payload: a lifetime-window call owns no
* transient segment even when its previous bytes were undefined slots. */
    mov QWORD PTR [r11+120], 0
    jmp qjs_linux_builtin_window_private
linux_c_builtin_miss:
    mov rax, QWORD PTR [rdx-16]
/* Exact dense-pop (argc==0) and dense-push (argc==1) method leaves.
* Every rejection remains the same generic/magic native C invocation. */
    test r9d, r9d
    jz linux_c_invoke_ordinary
    test r8d, r8d
    jnz linux_c_dense_push_check
    cmp WORD PTR [rax+@OBJ_LENGTH@], 256
    jne linux_c_invoke_ordinary
    cmp WORD PTR [rax+@OBJ_MAGIC@], 0
    jne linux_c_invoke_ordinary
    lea r10, [rip+JS_FrameDenseArrayPop]
    cmp QWORD PTR [rax+@OBJ_FUNCTION@], r10
    jne linux_c_invoke_ordinary
    cmp BYTE PTR [rip+JS_LinuxDensePopControl], 1
    jne linux_c_invoke_ordinary
    cmp BYTE PTR [rip+JS_LinuxDensePopLeafControl], 1
    jne linux_c_invoke_ordinary
    cmp QWORD PTR [rdx-24], @TAG_OBJECT@
    jne linux_c_invoke_ordinary
    mov r10, QWORD PTR [rdx-32]
    cmp WORD PTR [r10+@OBJ_CLASS@], @CLASS_ARRAY@
    jne linux_c_invoke_ordinary
    movzx r11d, BYTE PTR [r10+@OBJ_ARRAY_FLAGS@]
    and r11d, @OBJ_ARRAY_FLAG_MASK@
    cmp r11d, @OBJ_ARRAY_FLAG_MASK@
    jne linux_c_invoke_ordinary
    mov r11, QWORD PTR [r10+@OBJ_SHAPE@]
    mov eax, DWORD PTR [r11+@SHAPE_HASH_MASK@]
    lea r11, [r11+rax*4+@SHAPE_PROP_BASE@]
    cmp DWORD PTR [r11+@SHAPE_ATOM@], @ATOM_LENGTH@
    jne linux_c_invoke_ordinary
    mov r11d, DWORD PTR [r11]
    shr r11d, @SHAPE_FLAGS_SHIFT@
    cmp r11d, @LENGTH_FLAGS@
    jne linux_c_invoke_ordinary
    mov r11, QWORD PTR [r10+@OBJ_PROPERTIES@]
    cmp QWORD PTR [r11+8], @TAG_INT@
    jne linux_c_invoke_ordinary
    mov r9d, DWORD PTR [r10+@ARRAY_COUNT@]
    cmp DWORD PTR [r11], r9d
    jne linux_c_invoke_restore_method
    cmp r9d, 2147483647
    ja linux_c_invoke_restore_method
    movq xmm4, r10
    mov r10, QWORD PTR [rbx+56]
    cmp QWORD PTR [r10+@RT_LIMIT@], 0
    je qjs_linux_dense_pop_private
    lea r11, [rsp-368]
    cmp r11, QWORD PTR [r10+@RT_LIMIT@]
    jae qjs_linux_dense_pop_private
    jmp linux_c_invoke_restore_method
linux_c_dense_push_check:
    cmp r8d, 1
    jne linux_c_invoke_ordinary
    cmp WORD PTR [rax+@OBJ_LENGTH@], 257
    jne linux_c_invoke_ordinary
    cmp WORD PTR [rax+@OBJ_MAGIC@], 0
    jne linux_c_invoke_ordinary
    lea r10, [rip+qjs_linux_core_js_array_push]
    cmp QWORD PTR [rax+@OBJ_FUNCTION@], r10
    jne linux_c_invoke_ordinary
    cmp QWORD PTR [rax+@OBJ_REALM@], rsi
    jne linux_c_invoke_ordinary
    cmp QWORD PTR [rdx-24], @TAG_OBJECT@
    jne linux_c_invoke_ordinary
    mov r10, QWORD PTR [rdx-32]
    cmp WORD PTR [r10+@OBJ_CLASS@], @CLASS_ARRAY@
    jne linux_c_invoke_ordinary
    movzx r11d, BYTE PTR [r10+@OBJ_ARRAY_FLAGS@]
    and r11d, @OBJ_ARRAY_FLAG_MASK@
    cmp r11d, @OBJ_ARRAY_FLAG_MASK@
    jne linux_c_invoke_ordinary
    test BYTE PTR [rsi+@CTX_STD_ARR_BYTE@], @CTX_STD_ARR_MASK@
    jz linux_c_invoke_ordinary
    mov r11, QWORD PTR [r10+@OBJ_SHAPE@]
    mov rax, QWORD PTR [rsi+@CTX_CLASS_PROTO@]
    mov r9, QWORD PTR [r11+@SHAPE_PROTO@]
    cmp r9, QWORD PTR [rax+32]
    jne linux_c_invoke_restore_method
    mov eax, DWORD PTR [r11+@SHAPE_HASH_MASK@]
    lea r11, [r11+rax*4+@SHAPE_PROP_BASE@]
    cmp DWORD PTR [r11+@SHAPE_ATOM@], @ATOM_LENGTH@
    jne linux_c_invoke_restore_method
    mov r11d, DWORD PTR [r11]
    shr r11d, @SHAPE_FLAGS_SHIFT@
    cmp r11d, @LENGTH_FLAGS@
    jne linux_c_invoke_restore_method
    mov r11, QWORD PTR [r10+@OBJ_PROPERTIES@]
    cmp QWORD PTR [r11+8], @TAG_INT@
    jne linux_c_invoke_restore_method
    mov r9d, DWORD PTR [r10+@ARRAY_COUNT@]
    cmp DWORD PTR [r11], r9d
    jne linux_c_invoke_restore_method
    cmp r9d, 2147483647
    jae linux_c_invoke_restore_method
    cmp r9d, DWORD PTR [r10+@ARRAY_SIZE@]
    jae linux_c_invoke_restore_method
    movq xmm4, r10
    mov r10, QWORD PTR [rbx+56]
    cmp QWORD PTR [r10+@RT_LIMIT@], 0
    je qjs_linux_dense_push_private
    lea r11, [rsp-368]
    cmp r11, QWORD PTR [r10+@RT_LIMIT@]
    jae qjs_linux_dense_push_private
linux_c_invoke_restore_method:
    mov r9d, 1
linux_c_invoke_ordinary:
    mov r10, QWORD PTR [rbx+56]
    xor r11d, r11d
    cmp r8d, ecx
    jae linux_c_invoke_have_argv
    mov r11d, ecx
    shl r11, 4
linux_c_invoke_have_argv:
/* A low-stack rejection uses the original checked C bridge, not a new throw.
* This bound includes our header, argument copy and a conservative C reserve. */
    cmp QWORD PTR [r10+@RT_LIMIT@], 0
    je linux_c_invoke_stack_ready
    lea r10, [rsp-368]
    sub r10, r11
    mov rax, QWORD PTR [rbx+56]
    cmp r10, QWORD PTR [rax+@RT_LIMIT@]
    jb linux_c_invoke_fallback
linux_c_invoke_stack_ready:
    dec DWORD PTR [rsi+@CTX_INTERRUPT@]
    push rbp
.cfi_adjust_cfa_offset 8
.cfi_offset rbp, -16
    sub rsp, 112
.cfi_adjust_cfa_offset 112
    mov rbp, rsp
.cfi_def_cfa rbp, 128
    mov QWORD PTR [rbp+80], rdi
    mov QWORD PTR [rbp+88], rsi
    mov DWORD PTR [rbp+96], r8d
    mov WORD PTR [rbp+102], cx
    mov r10, QWORD PTR [rbx+56]
    mov rax, QWORD PTR [r10+@RT_SF@]
    mov QWORD PTR [rbp+@SF_PREV@], rax
    movdqu xmm0, XMMWORD PTR [rdx-16]
    movdqu XMMWORD PTR [rbp+@SF_FUNC@], xmm0
    mov QWORD PTR [rbp+@SF_ARGV@], rdx
    mov eax, r8d
    cmp eax, ecx
    cmovb eax, ecx
    mov WORD PTR [rbp+@SF_ARGC@], ax
    mov BYTE PTR [rbp+@SF_STRICT@], 0
    mov BYTE PTR [rbp+@SF_CTOR@], 0
    mov QWORD PTR [rbp+@SF_GC_OBJ@], 0
    test r9d, r9d
    jz linux_c_invoke_undefined_this
    movdqu xmm2, XMMWORD PTR [rdx-32]
    jmp linux_c_invoke_this_ready
linux_c_invoke_undefined_this:
    movdqu xmm2, XMMWORD PTR [rip+interp_table+2048]
linux_c_invoke_this_ready:
    test r11, r11
    jz linux_c_invoke_args_ready
/* At most255 slots. Touch the fixed header first, then the <=4080-byte
* dynamic window, so no guard page is skipped. Copies remain borrowed. */
    sub rsp, r11
    mov QWORD PTR [rbp+@SF_ARGV@], rsp
    mov rsi, rdx
    mov rdi, rsp
    mov ecx, DWORD PTR [rbp+96]
    shl ecx, 1
    rep movsq
    movzx ecx, WORD PTR [rbp+102]
    sub ecx, DWORD PTR [rbp+96]
linux_c_invoke_fill:
    mov QWORD PTR [rdi], 0
    mov QWORD PTR [rdi+8], @TAG_UNDEFINED@
    add rdi, 16
    dec ecx
    jnz linux_c_invoke_fill
linux_c_invoke_args_ready:
    mov r10, QWORD PTR [rbx+56]
    mov al, BYTE PTR [r10+@RT_SHARED@]
    and al, 4
    mov BYTE PTR [rbp+100], al
    mov QWORD PTR [r10+@RT_SF@], rbp
    or BYTE PTR [r10+@RT_SHARED@], 4
/* rootSP is RBP+128; its canonical kind is rootSP+16. */
    mov DWORD PTR [rbp+144], 0
    mov rax, QWORD PTR [rbp+@SF_FUNC@]
    mov rdi, QWORD PTR [rax+@OBJ_REALM@]
    mov r11, QWORD PTR [rax+@OBJ_FUNCTION@]
    movsx r9d, WORD PTR [rax+@OBJ_MAGIC@]
    movq rsi, xmm2
    movhlps xmm1, xmm2
    movq rdx, xmm1
    mov ecx, DWORD PTR [rbp+96]
    mov r8, QWORD PTR [rbp+@SF_ARGV@]
linux_c_invoke_call:
    call r11
linux_c_invoke_return:
/* Public SysV returns the aggregate in RAX/RDX; the private VM keeps it in
* XMM0 until its existing owning argument-release/return consumer needs it. */
    movq xmm0, rax
    movq xmm1, rdx
    punpcklqdq xmm0, xmm1
    cmp rdx, @TAG_EXCEPTION@
    sete BYTE PTR [rbx+160]
    jne linux_c_invoke_result_ready
    mov QWORD PTR [rbx+40], rax
    mov QWORD PTR [rbx+48], rdx
linux_c_invoke_result_ready:
    mov r10, QWORD PTR [rbx+56]
    mov DWORD PTR [rbp+144], 3
    mov al, BYTE PTR [r10+@RT_SHARED@]
    and al, 251
    or al, BYTE PTR [rbp+100]
    mov BYTE PTR [r10+@RT_SHARED@], al
    mov rax, QWORD PTR [rbp+@SF_PREV@]
    mov QWORD PTR [r10+@RT_SF@], rax
    mov rax, QWORD PTR [rbx+32]
    mov rdx, QWORD PTR [r10+@RT_LIMIT@]
    cmp rax, QWORD PTR [rbx+64]
    jne linux_c_invoke_refresh
    cmp rdx, QWORD PTR [rbx+80]
    je linux_c_invoke_refreshed
linux_c_invoke_refresh:
    mov QWORD PTR [rbx+64], rax
    mov QWORD PTR [rbx+80], rdx
    test rdx, rdx
    jz linux_c_invoke_limit
    sub rdx, rax
linux_c_invoke_limit:
    mov QWORD PTR [rbx+72], rdx
linux_c_invoke_refreshed:
    mov rdi, QWORD PTR [rbp+80]
    mov rsi, QWORD PTR [rbp+88]
    movzx eax, BYTE PTR [rbx+160]
    mov rsp, rbp
.cfi_def_cfa rsp, 128
    add rsp, 112
.cfi_adjust_cfa_offset -112
    pop rbp
.cfi_restore rbp
.cfi_adjust_cfa_offset -8
    ret
linux_c_numeric_guard:
    cmp r8d, ecx
    jb linux_c_invoke_generic_fallback
    cmp r8d, 1
    jl linux_c_invoke_generic_fallback
    test BYTE PTR [rip+JS_LinuxNumericControl], 3
    jz linux_c_invoke_generic_fallback
    cmp QWORD PTR [rdx+8], @TAG_FLOAT@
    je linux_c_numeric_double0
    cmp QWORD PTR [rdx+8], @TAG_INT@
    jne linux_c_invoke_generic_fallback
    cvtsi2sd xmm4, DWORD PTR [rdx]
    jmp linux_c_numeric_arg0
linux_c_numeric_double0:
    movsd xmm4, QWORD PTR [rdx]
linux_c_numeric_arg0:
    cmp BYTE PTR [rax+@OBJ_CPROTO@], @CPROTO_UNARY@
    je linux_c_numeric_stack
    cmp r8d, 2
    jl linux_c_invoke_generic_fallback
    cmp QWORD PTR [rdx+24], @TAG_FLOAT@
    je linux_c_numeric_double1
    cmp QWORD PTR [rdx+24], @TAG_INT@
    jne linux_c_invoke_generic_fallback
    cvtsi2sd xmm5, DWORD PTR [rdx+16]
    jmp linux_c_numeric_stack
linux_c_numeric_double1:
    movsd xmm5, QWORD PTR [rdx+16]
linux_c_numeric_stack:
/* Preserve the accepted formal*16 envelope even though this lane borrows
* actual arguments and never pads them. Every miss precedes publication. */
    mov r10, QWORD PTR [rbx+56]
    cmp QWORD PTR [r10+@RT_LIMIT@], 0
    je qjs_linux_numeric_invoke_private
    mov r11d, ecx
    shl r11, 4
    add r11, 368
    neg r11
    add r11, rsp
    cmp r11, QWORD PTR [r10+@RT_LIMIT@]
    jb linux_c_invoke_generic_fallback
    jmp qjs_linux_numeric_invoke_private
linux_c_invoke_fallback:
/* The retained direct helper only accepts generic/magic. Numeric callers
* rejected by scope, poll or quota must reenter the original typed switch. */
    mov rax, QWORD PTR [rdx-16]
    cmp BYTE PTR [rax+@OBJ_CPROTO@], @CPROTO_MAGIC@
    ja linux_c_invoke_generic_fallback
    mov rcx, rbx
    jmp @FALLBACK_BRIDGE@
linux_c_invoke_generic_fallback:
    mov rcx, rbx
    jmp @GENERIC_BRIDGE@
.cfi_endproc
.size qjs_linux_c_invoke_private, .-qjs_linux_c_invoke_private
