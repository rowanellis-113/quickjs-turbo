.include "interpreter-private-abi-gas.inc"
.intel_syntax noprefix
.section .qjscold$zzzzzzzzzzzzzzzzzzzzzzstringnumeric,"xr"
.p2align 4
.globl JS_FrameStringNumericSelect, JS_FrameStringNumericSelect_end
.def JS_FrameStringNumericSelect; .scl 2; .type 32; .endef
JS_FrameStringNumericSelect:
    cmp DWORD PTR [rip+JS_FrameStringNumericMode], 0
    je JS_FrameInterpGenericFast
    cmp DWORD PTR [rdx-8], -1
    jne JS_FrameInterpGenericFast
    mov r10, QWORD PTR [rdx-16]
    cmp WORD PTR [r10+QJS_ABI_OFF_JSObject_class_id], 12
    jne JS_FrameInterpGenericFast
    mov rax, QWORD PTR [r10+QJS_ABI_OFF_JSObject_u_cfunc_c_function]
    lea r11, [rip+qjs_frame_core_js_string_charCodeAt]
    cmp rax, r11
    je JS_FrameStringNumericSelect_hit
    lea r11, [rip+qjs_frame_core_js_string_codePointAt]
    cmp rax, r11
    jne JS_FrameInterpGenericFast
JS_FrameStringNumericSelect_hit:
    jmp JS_FrameStringNumericHost
JS_FrameStringNumericSelect_end:
.section .xdata$zzpurenumeric,"dr"
.p2align 2
JS_FrameStringNumericSelect_unwind:
.byte 1,0,0,0
.section .pdata$zzpurenumeric,"dr"
.p2align 2
.rva JS_FrameStringNumericSelect, JS_FrameStringNumericSelect_end, JS_FrameStringNumericSelect_unwind
