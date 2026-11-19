.include "interpreter-private-abi-gas.inc"
.intel_syntax noprefix
.section .qjzzpc,"xr"
.p2align 4
.globl JS_FrameArgumentsForwardProbe, JS_FrameArgumentsForwardProbe_end
.def JS_FrameArgumentsForwardProbe; .scl 2; .type 32; .endef
JS_FrameArgumentsForwardProbe:
    test DWORD PTR [rip+JS_FrameArgumentsMode], 258
    jnz JS_FrameCallForwardNativeProbe
    mov rax, QWORD PTR [rcx+16]
    movzx eax, BYTE PTR [rax]
    cmp eax, 36
    je args_forward_method
    cmp eax, 37
    jne JS_FrameCallForwardNativeProbe
args_forward_method:
    mov rax, QWORD PTR [rcx+16]
    movzx r8d, WORD PTR [rax+1]
    cmp r8d, 32765
    ja JS_FrameCallForwardNativeProbe
    shl r8, 4
    neg r8
    add r8, QWORD PTR [rcx+24]
    cmp QWORD PTR [r8-24], -1
    jne JS_FrameCallForwardNativeProbe
    mov rdx, QWORD PTR [r8-32]
    cmp WORD PTR [rdx+QJS_ABI_OFF_JSObject_class_id], 13
    je args_forward_js
    cmp WORD PTR [rdx+QJS_ABI_OFF_JSObject_class_id], 12
    jne JS_FrameCallForwardNativeProbe
    lea r9, [rip+qjs_frame_core_js_function_call]
    cmp QWORD PTR [rdx+QJS_ABI_OFF_JSObject_u_cfunc_c_function], r9
    jne JS_FrameCallForwardNativeProbe
    cmp BYTE PTR [rdx+QJS_ABI_OFF_JSObject_u_cfunc_cproto], 0
    jne JS_FrameCallForwardNativeProbe
    cmp WORD PTR [rdx+QJS_ABI_OFF_JSObject_u_cfunc_magic], 0
    jne JS_FrameCallForwardNativeProbe
    cmp BYTE PTR [rdx+QJS_ABI_OFF_JSObject_u_cfunc_length], 1
    jne JS_FrameCallForwardNativeProbe
    jmp JS_FrameArgumentsForwardTry
args_forward_js:
    mov r9, QWORD PTR [rdx+QJS_ABI_OFF_JSObject_u_func_function_bytecode]
    test BYTE PTR [rip+JS_FrameArgumentsMode], 2
    jnz JS_FrameCallForwardNativeProbe
    test BYTE PTR [r9+QJS_ABI_OFF_JSFunctionBytecode_byte_code_buf-1], 1
    jnz JS_FrameCallForwardNativeProbe
    cmp BYTE PTR [r9+QJS_ABI_OFF_JSFunctionBytecode_byte_code_buf-1], 2
    jne args_forward_unknown
    cmp BYTE PTR [r9+QJS_ABI_OFF_JSFunctionBytecode_pc2line_len+4], 128
    je JS_FrameArgumentsForwardTry
    cmp BYTE PTR [r9+QJS_ABI_OFF_JSFunctionBytecode_pc2line_len+4], 64
    je JS_FrameCallForwardNativeProbe
args_forward_unknown:
    mov eax, DWORD PTR [r9+QJS_ABI_OFF_JSFunctionBytecode_byte_code_len]
    cmp eax, 2
    jb args_forward_negative
    cmp eax, 2048
    ja args_forward_negative
    cmp eax, 17
    jbe args_forward_size
    mov eax, 17
args_forward_size:
    mov r10, QWORD PTR [r9+QJS_ABI_OFF_JSFunctionBytecode_byte_code_buf]
    lea r11, [r10+rax]
args_forward_prefix:
    cmp r10, r11
    jae args_forward_negative
    cmp BYTE PTR [r10], 8
    je args_forward_this
    cmp BYTE PTR [r10], 12
    jne args_forward_negative
    inc r10
    cmp r10, r11
    jae args_forward_negative
    movzx eax, BYTE PTR [r10]
    cmp eax, 1
    jbe JS_FrameArgumentsForwardTry
    cmp eax, 4
    ja args_forward_negative
    inc r10
    jmp args_forward_store
args_forward_this:
    inc r10
args_forward_store:
    cmp r10, r11
    jae args_forward_negative
    movzx eax, BYTE PTR [r10]
    cmp eax, 200
    je args_forward_local8
    sub eax, 207
    cmp eax, 3
    ja args_forward_negative
    inc r10
    jmp args_forward_prefix
args_forward_local8:
    add r10, 2
    jmp args_forward_prefix
args_forward_negative:
    cmp BYTE PTR [r9+QJS_ABI_OFF_JSFunctionBytecode_byte_code_buf-1], 2
    jne JS_FrameCallForwardNativeProbe
    mov BYTE PTR [r9+QJS_ABI_OFF_JSFunctionBytecode_pc2line_len+4], 64
    jmp JS_FrameCallForwardNativeProbe

JS_FrameArgumentsForwardProbe_end:
.p2align 2
arguments_forward_leaf_unwind:
.byte 1,0,0,0
.section .pdata$zzzzzznullfast,"dr"
.p2align 2
.rva JS_FrameArgumentsForwardProbe, JS_FrameArgumentsForwardProbe_end, arguments_forward_leaf_unwind
