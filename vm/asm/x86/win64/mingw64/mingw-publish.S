.include "interpreter-private-abi-gas.inc"
.intel_syntax noprefix
.section .qjzzpc,"xr"
.p2align 4
.globl JS_FrameAlwaysPublishBefore_FrameAddLocalBig, JS_FrameAlwaysPublishBefore_FrameAddLocalBig_end
.def JS_FrameAlwaysPublishBefore_FrameAddLocalBig; .scl 2; .type 32; .endef
JS_FrameAlwaysPublishBefore_FrameAddLocalBig:
    mov r10, QWORD PTR [rbx+56]
/* 0.15.1 scans the live operand cursor; publish it before reentry. */
.if QJS_ABI_HAS_CORO_OWNER == 0
    mov QWORD PTR [rbp+QJS_ABI_OFF_JSStackFrame_cur_pc], r12
    mov QWORD PTR [rbp+QJS_ABI_OFF_JSStackFrame_cur_sp], r13
.endif
    mov QWORD PTR [r10+QJS_ABI_OFF_JSRuntime_current_stack_frame], rbp
    jmp JS_FrameAddLocalBig
JS_FrameAlwaysPublishBefore_FrameAddLocalBig_end:
.p2align 4
.globl JS_FrameAlwaysPublishBefore_FrameAddLocalString, JS_FrameAlwaysPublishBefore_FrameAddLocalString_end
.def JS_FrameAlwaysPublishBefore_FrameAddLocalString; .scl 2; .type 32; .endef
JS_FrameAlwaysPublishBefore_FrameAddLocalString:
    mov r10, QWORD PTR [rbx+56]
/* 0.15.1 scans the live operand cursor; publish it before reentry. */
.if QJS_ABI_HAS_CORO_OWNER == 0
    mov QWORD PTR [rbp+QJS_ABI_OFF_JSStackFrame_cur_pc], r12
    mov QWORD PTR [rbp+QJS_ABI_OFF_JSStackFrame_cur_sp], r13
.endif
    mov QWORD PTR [r10+QJS_ABI_OFF_JSRuntime_current_stack_frame], rbp
    jmp JS_FrameAddLocalString
JS_FrameAlwaysPublishBefore_FrameAddLocalString_end:
.p2align 4
.globl JS_FrameAlwaysPublishBefore_FrameInterpAddDirect, JS_FrameAlwaysPublishBefore_FrameInterpAddDirect_end
.def JS_FrameAlwaysPublishBefore_FrameInterpAddDirect; .scl 2; .type 32; .endef
JS_FrameAlwaysPublishBefore_FrameInterpAddDirect:
    mov r10, QWORD PTR [rbx+56]
/* 0.15.1 scans the live operand cursor; publish it before reentry. */
.if QJS_ABI_HAS_CORO_OWNER == 0
    mov QWORD PTR [rbp+QJS_ABI_OFF_JSStackFrame_cur_pc], r12
    mov QWORD PTR [rbp+QJS_ABI_OFF_JSStackFrame_cur_sp], r13
.endif
    mov QWORD PTR [r10+QJS_ABI_OFF_JSRuntime_current_stack_frame], rbp
    jmp JS_FrameInterpAddDirect
JS_FrameAlwaysPublishBefore_FrameInterpAddDirect_end:
.p2align 4
.globl JS_FrameAlwaysPublishBefore_FrameInterpBig_mul, JS_FrameAlwaysPublishBefore_FrameInterpBig_mul_end
.def JS_FrameAlwaysPublishBefore_FrameInterpBig_mul; .scl 2; .type 32; .endef
JS_FrameAlwaysPublishBefore_FrameInterpBig_mul:
    mov r10, QWORD PTR [rbx+56]
/* 0.15.1 scans the live operand cursor; publish it before reentry. */
.if QJS_ABI_HAS_CORO_OWNER == 0
    mov QWORD PTR [rbp+QJS_ABI_OFF_JSStackFrame_cur_pc], r12
    mov QWORD PTR [rbp+QJS_ABI_OFF_JSStackFrame_cur_sp], r13
.endif
    mov QWORD PTR [r10+QJS_ABI_OFF_JSRuntime_current_stack_frame], rbp
    jmp JS_FrameInterpBig_mul
JS_FrameAlwaysPublishBefore_FrameInterpBig_mul_end:
.p2align 4
.globl JS_FrameAlwaysPublishBefore_FrameInterpClose, JS_FrameAlwaysPublishBefore_FrameInterpClose_end
.def JS_FrameAlwaysPublishBefore_FrameInterpClose; .scl 2; .type 32; .endef
JS_FrameAlwaysPublishBefore_FrameInterpClose:
    mov r10, QWORD PTR [rbx+56]
/* 0.15.1 scans the live operand cursor; publish it before reentry. */
.if QJS_ABI_HAS_CORO_OWNER == 0
    mov QWORD PTR [rbp+QJS_ABI_OFF_JSStackFrame_cur_pc], r12
    mov QWORD PTR [rbp+QJS_ABI_OFF_JSStackFrame_cur_sp], r13
.endif
    mov QWORD PTR [r10+QJS_ABI_OFF_JSRuntime_current_stack_frame], rbp
    jmp JS_FrameInterpClose
JS_FrameAlwaysPublishBefore_FrameInterpClose_end:
.p2align 4
.globl JS_FrameAlwaysPublishBefore_FrameInterpFree, JS_FrameAlwaysPublishBefore_FrameInterpFree_end
.def JS_FrameAlwaysPublishBefore_FrameInterpFree; .scl 2; .type 32; .endef
JS_FrameAlwaysPublishBefore_FrameInterpFree:
    mov r10, QWORD PTR [rbx+56]
/* 0.15.1 scans the live operand cursor; publish it before reentry. */
.if QJS_ABI_HAS_CORO_OWNER == 0
    mov QWORD PTR [rbp+QJS_ABI_OFF_JSStackFrame_cur_pc], r12
    mov QWORD PTR [rbp+QJS_ABI_OFF_JSStackFrame_cur_sp], r13
.endif
    mov QWORD PTR [r10+QJS_ABI_OFF_JSRuntime_current_stack_frame], rbp
    jmp JS_FrameInterpFree
JS_FrameAlwaysPublishBefore_FrameInterpFree_end:
.p2align 4
.globl JS_FrameAlwaysPublishBefore_FrameInterpOp_div, JS_FrameAlwaysPublishBefore_FrameInterpOp_div_end
.def JS_FrameAlwaysPublishBefore_FrameInterpOp_div; .scl 2; .type 32; .endef
JS_FrameAlwaysPublishBefore_FrameInterpOp_div:
    mov r10, QWORD PTR [rbx+56]
/* 0.15.1 scans the live operand cursor; publish it before reentry. */
.if QJS_ABI_HAS_CORO_OWNER == 0
    mov QWORD PTR [rbp+QJS_ABI_OFF_JSStackFrame_cur_pc], r12
    mov QWORD PTR [rbp+QJS_ABI_OFF_JSStackFrame_cur_sp], r13
.endif
    mov QWORD PTR [r10+QJS_ABI_OFF_JSRuntime_current_stack_frame], rbp
    jmp JS_FrameInterpOp_div
JS_FrameAlwaysPublishBefore_FrameInterpOp_div_end:
.p2align 4
.globl JS_FrameAlwaysPublishBefore_FrameInterpOp_eq, JS_FrameAlwaysPublishBefore_FrameInterpOp_eq_end
.def JS_FrameAlwaysPublishBefore_FrameInterpOp_eq; .scl 2; .type 32; .endef
JS_FrameAlwaysPublishBefore_FrameInterpOp_eq:
    mov r10, QWORD PTR [rbx+56]
/* 0.15.1 scans the live operand cursor; publish it before reentry. */
.if QJS_ABI_HAS_CORO_OWNER == 0
    mov QWORD PTR [rbp+QJS_ABI_OFF_JSStackFrame_cur_pc], r12
    mov QWORD PTR [rbp+QJS_ABI_OFF_JSStackFrame_cur_sp], r13
.endif
    mov QWORD PTR [r10+QJS_ABI_OFF_JSRuntime_current_stack_frame], rbp
    jmp JS_FrameInterpOp_eq
JS_FrameAlwaysPublishBefore_FrameInterpOp_eq_end:
.p2align 4
.globl JS_FrameAlwaysPublishBefore_FrameInterpOp_gt, JS_FrameAlwaysPublishBefore_FrameInterpOp_gt_end
.def JS_FrameAlwaysPublishBefore_FrameInterpOp_gt; .scl 2; .type 32; .endef
JS_FrameAlwaysPublishBefore_FrameInterpOp_gt:
    mov r10, QWORD PTR [rbx+56]
/* 0.15.1 scans the live operand cursor; publish it before reentry. */
.if QJS_ABI_HAS_CORO_OWNER == 0
    mov QWORD PTR [rbp+QJS_ABI_OFF_JSStackFrame_cur_pc], r12
    mov QWORD PTR [rbp+QJS_ABI_OFF_JSStackFrame_cur_sp], r13
.endif
    mov QWORD PTR [r10+QJS_ABI_OFF_JSRuntime_current_stack_frame], rbp
    jmp JS_FrameInterpOp_gt
JS_FrameAlwaysPublishBefore_FrameInterpOp_gt_end:
.p2align 4
.globl JS_FrameAlwaysPublishBefore_FrameInterpOp_gte, JS_FrameAlwaysPublishBefore_FrameInterpOp_gte_end
.def JS_FrameAlwaysPublishBefore_FrameInterpOp_gte; .scl 2; .type 32; .endef
JS_FrameAlwaysPublishBefore_FrameInterpOp_gte:
    mov r10, QWORD PTR [rbx+56]
/* 0.15.1 scans the live operand cursor; publish it before reentry. */
.if QJS_ABI_HAS_CORO_OWNER == 0
    mov QWORD PTR [rbp+QJS_ABI_OFF_JSStackFrame_cur_pc], r12
    mov QWORD PTR [rbp+QJS_ABI_OFF_JSStackFrame_cur_sp], r13
.endif
    mov QWORD PTR [r10+QJS_ABI_OFF_JSRuntime_current_stack_frame], rbp
    jmp JS_FrameInterpOp_gte
JS_FrameAlwaysPublishBefore_FrameInterpOp_gte_end:
.p2align 4
.globl JS_FrameAlwaysPublishBefore_FrameInterpOp_lt, JS_FrameAlwaysPublishBefore_FrameInterpOp_lt_end
.def JS_FrameAlwaysPublishBefore_FrameInterpOp_lt; .scl 2; .type 32; .endef
JS_FrameAlwaysPublishBefore_FrameInterpOp_lt:
    mov r10, QWORD PTR [rbx+56]
/* 0.15.1 scans the live operand cursor; publish it before reentry. */
.if QJS_ABI_HAS_CORO_OWNER == 0
    mov QWORD PTR [rbp+QJS_ABI_OFF_JSStackFrame_cur_pc], r12
    mov QWORD PTR [rbp+QJS_ABI_OFF_JSStackFrame_cur_sp], r13
.endif
    mov QWORD PTR [r10+QJS_ABI_OFF_JSRuntime_current_stack_frame], rbp
    jmp JS_FrameInterpOp_lt
JS_FrameAlwaysPublishBefore_FrameInterpOp_lt_end:
.p2align 4
.globl JS_FrameAlwaysPublishBefore_FrameInterpOp_lte, JS_FrameAlwaysPublishBefore_FrameInterpOp_lte_end
.def JS_FrameAlwaysPublishBefore_FrameInterpOp_lte; .scl 2; .type 32; .endef
JS_FrameAlwaysPublishBefore_FrameInterpOp_lte:
    mov r10, QWORD PTR [rbx+56]
/* 0.15.1 scans the live operand cursor; publish it before reentry. */
.if QJS_ABI_HAS_CORO_OWNER == 0
    mov QWORD PTR [rbp+QJS_ABI_OFF_JSStackFrame_cur_pc], r12
    mov QWORD PTR [rbp+QJS_ABI_OFF_JSStackFrame_cur_sp], r13
.endif
    mov QWORD PTR [r10+QJS_ABI_OFF_JSRuntime_current_stack_frame], rbp
    jmp JS_FrameInterpOp_lte
JS_FrameAlwaysPublishBefore_FrameInterpOp_lte_end:
.p2align 4
.globl JS_FrameAlwaysPublishBefore_FrameInterpOp_mod, JS_FrameAlwaysPublishBefore_FrameInterpOp_mod_end
.def JS_FrameAlwaysPublishBefore_FrameInterpOp_mod; .scl 2; .type 32; .endef
JS_FrameAlwaysPublishBefore_FrameInterpOp_mod:
    mov r10, QWORD PTR [rbx+56]
/* 0.15.1 scans the live operand cursor; publish it before reentry. */
.if QJS_ABI_HAS_CORO_OWNER == 0
    mov QWORD PTR [rbp+QJS_ABI_OFF_JSStackFrame_cur_pc], r12
    mov QWORD PTR [rbp+QJS_ABI_OFF_JSStackFrame_cur_sp], r13
.endif
    mov QWORD PTR [r10+QJS_ABI_OFF_JSRuntime_current_stack_frame], rbp
    jmp JS_FrameInterpOp_mod
JS_FrameAlwaysPublishBefore_FrameInterpOp_mod_end:
.p2align 4
.globl JS_FrameAlwaysPublishBefore_FrameInterpOp_neq, JS_FrameAlwaysPublishBefore_FrameInterpOp_neq_end
.def JS_FrameAlwaysPublishBefore_FrameInterpOp_neq; .scl 2; .type 32; .endef
JS_FrameAlwaysPublishBefore_FrameInterpOp_neq:
    mov r10, QWORD PTR [rbx+56]
/* 0.15.1 scans the live operand cursor; publish it before reentry. */
.if QJS_ABI_HAS_CORO_OWNER == 0
    mov QWORD PTR [rbp+QJS_ABI_OFF_JSStackFrame_cur_pc], r12
    mov QWORD PTR [rbp+QJS_ABI_OFF_JSStackFrame_cur_sp], r13
.endif
    mov QWORD PTR [r10+QJS_ABI_OFF_JSRuntime_current_stack_frame], rbp
    jmp JS_FrameInterpOp_neq
JS_FrameAlwaysPublishBefore_FrameInterpOp_neq_end:
.p2align 4
.globl JS_FrameAlwaysPublishBefore_FrameInterpOp_strict_eq, JS_FrameAlwaysPublishBefore_FrameInterpOp_strict_eq_end
.def JS_FrameAlwaysPublishBefore_FrameInterpOp_strict_eq; .scl 2; .type 32; .endef
JS_FrameAlwaysPublishBefore_FrameInterpOp_strict_eq:
    mov r10, QWORD PTR [rbx+56]
/* 0.15.1 scans the live operand cursor; publish it before reentry. */
.if QJS_ABI_HAS_CORO_OWNER == 0
    mov QWORD PTR [rbp+QJS_ABI_OFF_JSStackFrame_cur_pc], r12
    mov QWORD PTR [rbp+QJS_ABI_OFF_JSStackFrame_cur_sp], r13
.endif
    mov QWORD PTR [r10+QJS_ABI_OFF_JSRuntime_current_stack_frame], rbp
    jmp JS_FrameInterpOp_strict_eq
JS_FrameAlwaysPublishBefore_FrameInterpOp_strict_eq_end:
.p2align 4
.globl JS_FrameAlwaysPublishBefore_FrameInterpOp_strict_neq, JS_FrameAlwaysPublishBefore_FrameInterpOp_strict_neq_end
.def JS_FrameAlwaysPublishBefore_FrameInterpOp_strict_neq; .scl 2; .type 32; .endef
JS_FrameAlwaysPublishBefore_FrameInterpOp_strict_neq:
    mov r10, QWORD PTR [rbx+56]
/* 0.15.1 scans the live operand cursor; publish it before reentry. */
.if QJS_ABI_HAS_CORO_OWNER == 0
    mov QWORD PTR [rbp+QJS_ABI_OFF_JSStackFrame_cur_pc], r12
    mov QWORD PTR [rbp+QJS_ABI_OFF_JSStackFrame_cur_sp], r13
.endif
    mov QWORD PTR [r10+QJS_ABI_OFF_JSRuntime_current_stack_frame], rbp
    jmp JS_FrameInterpOp_strict_neq
JS_FrameAlwaysPublishBefore_FrameInterpOp_strict_neq_end:
.p2align 4
.globl JS_FrameAlwaysPublishBefore_FrameInterpOp_sub, JS_FrameAlwaysPublishBefore_FrameInterpOp_sub_end
.def JS_FrameAlwaysPublishBefore_FrameInterpOp_sub; .scl 2; .type 32; .endef
JS_FrameAlwaysPublishBefore_FrameInterpOp_sub:
    mov r10, QWORD PTR [rbx+56]
/* 0.15.1 scans the live operand cursor; publish it before reentry. */
.if QJS_ABI_HAS_CORO_OWNER == 0
    mov QWORD PTR [rbp+QJS_ABI_OFF_JSStackFrame_cur_pc], r12
    mov QWORD PTR [rbp+QJS_ABI_OFF_JSStackFrame_cur_sp], r13
.endif
    mov QWORD PTR [r10+QJS_ABI_OFF_JSRuntime_current_stack_frame], rbp
    jmp JS_FrameInterpOp_sub
JS_FrameAlwaysPublishBefore_FrameInterpOp_sub_end:
.p2align 4
.globl JS_FrameAlwaysPublishBefore_FrameInterpProperty_call_constructor, JS_FrameAlwaysPublishBefore_FrameInterpProperty_call_constructor_end
.def JS_FrameAlwaysPublishBefore_FrameInterpProperty_call_constructor; .scl 2; .type 32; .endef
JS_FrameAlwaysPublishBefore_FrameInterpProperty_call_constructor:
    mov r10, QWORD PTR [rbx+56]
/* 0.15.1 scans the live operand cursor; publish it before reentry. */
.if QJS_ABI_HAS_CORO_OWNER == 0
    mov QWORD PTR [rbp+QJS_ABI_OFF_JSStackFrame_cur_pc], r12
    mov QWORD PTR [rbp+QJS_ABI_OFF_JSStackFrame_cur_sp], r13
.endif
    mov QWORD PTR [r10+QJS_ABI_OFF_JSRuntime_current_stack_frame], rbp
    jmp JS_FrameInterpProperty_call_constructor
JS_FrameAlwaysPublishBefore_FrameInterpProperty_call_constructor_end:
.p2align 4
.globl JS_FrameAlwaysPublishBefore_FrameInterpProperty_drop, JS_FrameAlwaysPublishBefore_FrameInterpProperty_drop_end
.def JS_FrameAlwaysPublishBefore_FrameInterpProperty_drop; .scl 2; .type 32; .endef
JS_FrameAlwaysPublishBefore_FrameInterpProperty_drop:
    mov r10, QWORD PTR [rbx+56]
/* 0.15.1 scans the live operand cursor; publish it before reentry. */
.if QJS_ABI_HAS_CORO_OWNER == 0
    mov QWORD PTR [rbp+QJS_ABI_OFF_JSStackFrame_cur_pc], r12
    mov QWORD PTR [rbp+QJS_ABI_OFF_JSStackFrame_cur_sp], r13
.endif
    mov QWORD PTR [r10+QJS_ABI_OFF_JSRuntime_current_stack_frame], rbp
    jmp JS_FrameInterpProperty_drop
JS_FrameAlwaysPublishBefore_FrameInterpProperty_drop_end:
.p2align 4
.globl JS_FrameAlwaysPublishBefore_FrameInterpProperty_get_field, JS_FrameAlwaysPublishBefore_FrameInterpProperty_get_field_end
.def JS_FrameAlwaysPublishBefore_FrameInterpProperty_get_field; .scl 2; .type 32; .endef
JS_FrameAlwaysPublishBefore_FrameInterpProperty_get_field:
    mov r10, QWORD PTR [rbx+56]
/* 0.15.1 scans the live operand cursor; publish it before reentry. */
.if QJS_ABI_HAS_CORO_OWNER == 0
    mov QWORD PTR [rbp+QJS_ABI_OFF_JSStackFrame_cur_pc], r12
    mov QWORD PTR [rbp+QJS_ABI_OFF_JSStackFrame_cur_sp], r13
.endif
    mov QWORD PTR [r10+QJS_ABI_OFF_JSRuntime_current_stack_frame], rbp
    jmp JS_FrameInterpProperty_get_field
JS_FrameAlwaysPublishBefore_FrameInterpProperty_get_field_end:
.p2align 4
.globl JS_FrameAlwaysPublishBefore_FrameInterpProperty_get_field2, JS_FrameAlwaysPublishBefore_FrameInterpProperty_get_field2_end
.def JS_FrameAlwaysPublishBefore_FrameInterpProperty_get_field2; .scl 2; .type 32; .endef
JS_FrameAlwaysPublishBefore_FrameInterpProperty_get_field2:
    mov r10, QWORD PTR [rbx+56]
/* 0.15.1 scans the live operand cursor; publish it before reentry. */
.if QJS_ABI_HAS_CORO_OWNER == 0
    mov QWORD PTR [rbp+QJS_ABI_OFF_JSStackFrame_cur_pc], r12
    mov QWORD PTR [rbp+QJS_ABI_OFF_JSStackFrame_cur_sp], r13
.endif
    mov QWORD PTR [r10+QJS_ABI_OFF_JSRuntime_current_stack_frame], rbp
    jmp JS_FrameInterpProperty_get_field2
JS_FrameAlwaysPublishBefore_FrameInterpProperty_get_field2_end:
.p2align 4
.globl JS_FrameAlwaysPublishBefore_FrameInterpProperty_put_field, JS_FrameAlwaysPublishBefore_FrameInterpProperty_put_field_end
.def JS_FrameAlwaysPublishBefore_FrameInterpProperty_put_field; .scl 2; .type 32; .endef
JS_FrameAlwaysPublishBefore_FrameInterpProperty_put_field:
    mov r10, QWORD PTR [rbx+56]
/* 0.15.1 scans the live operand cursor; publish it before reentry. */
.if QJS_ABI_HAS_CORO_OWNER == 0
    mov QWORD PTR [rbp+QJS_ABI_OFF_JSStackFrame_cur_pc], r12
    mov QWORD PTR [rbp+QJS_ABI_OFF_JSStackFrame_cur_sp], r13
.endif
    mov QWORD PTR [r10+QJS_ABI_OFF_JSRuntime_current_stack_frame], rbp
    jmp JS_FrameInterpProperty_put_field
JS_FrameAlwaysPublishBefore_FrameInterpProperty_put_field_end:
.p2align 4
.globl JS_FrameAlwaysPublishBefore_FrameInterpSlow, JS_FrameAlwaysPublishBefore_FrameInterpSlow_end
.def JS_FrameAlwaysPublishBefore_FrameInterpSlow; .scl 2; .type 32; .endef
JS_FrameAlwaysPublishBefore_FrameInterpSlow:
    mov r10, QWORD PTR [rbx+56]
/* 0.15.1 scans the live operand cursor; publish it before reentry. */
.if QJS_ABI_HAS_CORO_OWNER == 0
    mov QWORD PTR [rbp+QJS_ABI_OFF_JSStackFrame_cur_pc], r12
    mov QWORD PTR [rbp+QJS_ABI_OFF_JSStackFrame_cur_sp], r13
.endif
    mov QWORD PTR [r10+QJS_ABI_OFF_JSRuntime_current_stack_frame], rbp
    jmp JS_FrameIteratorSelectEntry
JS_FrameAlwaysPublishBefore_FrameInterpSlow_end:
.p2align 4
.globl JS_FrameAlwaysPublishBefore_FrameNativeCallLinkDispatch, JS_FrameAlwaysPublishBefore_FrameNativeCallLinkDispatch_end
.def JS_FrameAlwaysPublishBefore_FrameNativeCallLinkDispatch; .scl 2; .type 32; .endef
JS_FrameAlwaysPublishBefore_FrameNativeCallLinkDispatch:
    mov r10, QWORD PTR [rbx+56]
/* 0.15.1 scans the live operand cursor; publish it before reentry. */
.if QJS_ABI_HAS_CORO_OWNER == 0
    mov QWORD PTR [rbp+QJS_ABI_OFF_JSStackFrame_cur_pc], r12
    mov QWORD PTR [rbp+QJS_ABI_OFF_JSStackFrame_cur_sp], r13
.endif
    mov QWORD PTR [r10+QJS_ABI_OFF_JSRuntime_current_stack_frame], rbp
    jmp JS_FrameNativeCallLinkDispatch
JS_FrameAlwaysPublishBefore_FrameNativeCallLinkDispatch_end:
.p2align 4
.globl JS_FrameAlwaysPublishBefore_FrameNewNullObject, JS_FrameAlwaysPublishBefore_FrameNewNullObject_end
.def JS_FrameAlwaysPublishBefore_FrameNewNullObject; .scl 2; .type 32; .endef
JS_FrameAlwaysPublishBefore_FrameNewNullObject:
    mov r10, QWORD PTR [rbx+56]
/* 0.15.1 scans the live operand cursor; publish it before reentry. */
.if QJS_ABI_HAS_CORO_OWNER == 0
    mov QWORD PTR [rbp+QJS_ABI_OFF_JSStackFrame_cur_pc], r12
    mov QWORD PTR [rbp+QJS_ABI_OFF_JSStackFrame_cur_sp], r13
.endif
    mov QWORD PTR [r10+QJS_ABI_OFF_JSRuntime_current_stack_frame], rbp
    jmp JS_FrameNewNullObject
JS_FrameAlwaysPublishBefore_FrameNewNullObject_end:
.p2align 4
.globl JS_FrameAlwaysPublishBefore_FrameProtoPersistentFill, JS_FrameAlwaysPublishBefore_FrameProtoPersistentFill_end
.def JS_FrameAlwaysPublishBefore_FrameProtoPersistentFill; .scl 2; .type 32; .endef
JS_FrameAlwaysPublishBefore_FrameProtoPersistentFill:
    mov r10, QWORD PTR [rbx+56]
/* 0.15.1 scans the live operand cursor; publish it before reentry. */
.if QJS_ABI_HAS_CORO_OWNER == 0
    mov QWORD PTR [rbp+QJS_ABI_OFF_JSStackFrame_cur_pc], r12
    mov QWORD PTR [rbp+QJS_ABI_OFF_JSStackFrame_cur_sp], r13
.endif
    mov QWORD PTR [r10+QJS_ABI_OFF_JSRuntime_current_stack_frame], rbp
    jmp JS_FrameProtoPersistentFill
JS_FrameAlwaysPublishBefore_FrameProtoPersistentFill_end:
.p2align 4
.globl JS_FrameAlwaysPublishBefore_FreeValue, JS_FrameAlwaysPublishBefore_FreeValue_end
.def JS_FrameAlwaysPublishBefore_FreeValue; .scl 2; .type 32; .endef
JS_FrameAlwaysPublishBefore_FreeValue:
    mov r10, QWORD PTR [rbx+56]
/* 0.15.1 scans the live operand cursor; publish it before reentry. */
.if QJS_ABI_HAS_CORO_OWNER == 0
    mov QWORD PTR [rbp+QJS_ABI_OFF_JSStackFrame_cur_pc], r12
    mov QWORD PTR [rbp+QJS_ABI_OFF_JSStackFrame_cur_sp], r13
.endif
    mov QWORD PTR [r10+QJS_ABI_OFF_JSRuntime_current_stack_frame], rbp
    jmp JS_FreeValue
JS_FrameAlwaysPublishBefore_FreeValue_end:
.section .pdata$zzzzzznullfast,"dr"
.p2align 2
.rva JS_FrameAlwaysPublishBefore_FrameAddLocalBig, JS_FrameAlwaysPublishBefore_FrameAddLocalBig_end, JS_FrameInterpAddDirect_unwind
.rva JS_FrameAlwaysPublishBefore_FrameAddLocalString, JS_FrameAlwaysPublishBefore_FrameAddLocalString_end, JS_FrameInterpAddDirect_unwind
.rva JS_FrameAlwaysPublishBefore_FrameInterpAddDirect, JS_FrameAlwaysPublishBefore_FrameInterpAddDirect_end, JS_FrameInterpAddDirect_unwind
.rva JS_FrameAlwaysPublishBefore_FrameInterpBig_mul, JS_FrameAlwaysPublishBefore_FrameInterpBig_mul_end, JS_FrameInterpAddDirect_unwind
.rva JS_FrameAlwaysPublishBefore_FrameInterpClose, JS_FrameAlwaysPublishBefore_FrameInterpClose_end, JS_FrameInterpAddDirect_unwind
.rva JS_FrameAlwaysPublishBefore_FrameInterpFree, JS_FrameAlwaysPublishBefore_FrameInterpFree_end, JS_FrameInterpAddDirect_unwind
.rva JS_FrameAlwaysPublishBefore_FrameInterpOp_div, JS_FrameAlwaysPublishBefore_FrameInterpOp_div_end, JS_FrameInterpAddDirect_unwind
.rva JS_FrameAlwaysPublishBefore_FrameInterpOp_eq, JS_FrameAlwaysPublishBefore_FrameInterpOp_eq_end, JS_FrameInterpAddDirect_unwind
.rva JS_FrameAlwaysPublishBefore_FrameInterpOp_gt, JS_FrameAlwaysPublishBefore_FrameInterpOp_gt_end, JS_FrameInterpAddDirect_unwind
.rva JS_FrameAlwaysPublishBefore_FrameInterpOp_gte, JS_FrameAlwaysPublishBefore_FrameInterpOp_gte_end, JS_FrameInterpAddDirect_unwind
.rva JS_FrameAlwaysPublishBefore_FrameInterpOp_lt, JS_FrameAlwaysPublishBefore_FrameInterpOp_lt_end, JS_FrameInterpAddDirect_unwind
.rva JS_FrameAlwaysPublishBefore_FrameInterpOp_lte, JS_FrameAlwaysPublishBefore_FrameInterpOp_lte_end, JS_FrameInterpAddDirect_unwind
.rva JS_FrameAlwaysPublishBefore_FrameInterpOp_mod, JS_FrameAlwaysPublishBefore_FrameInterpOp_mod_end, JS_FrameInterpAddDirect_unwind
.rva JS_FrameAlwaysPublishBefore_FrameInterpOp_neq, JS_FrameAlwaysPublishBefore_FrameInterpOp_neq_end, JS_FrameInterpAddDirect_unwind
.rva JS_FrameAlwaysPublishBefore_FrameInterpOp_strict_eq, JS_FrameAlwaysPublishBefore_FrameInterpOp_strict_eq_end, JS_FrameInterpAddDirect_unwind
.rva JS_FrameAlwaysPublishBefore_FrameInterpOp_strict_neq, JS_FrameAlwaysPublishBefore_FrameInterpOp_strict_neq_end, JS_FrameInterpAddDirect_unwind
.rva JS_FrameAlwaysPublishBefore_FrameInterpOp_sub, JS_FrameAlwaysPublishBefore_FrameInterpOp_sub_end, JS_FrameInterpAddDirect_unwind
.rva JS_FrameAlwaysPublishBefore_FrameInterpProperty_call_constructor, JS_FrameAlwaysPublishBefore_FrameInterpProperty_call_constructor_end, JS_FrameInterpAddDirect_unwind
.rva JS_FrameAlwaysPublishBefore_FrameInterpProperty_drop, JS_FrameAlwaysPublishBefore_FrameInterpProperty_drop_end, JS_FrameInterpAddDirect_unwind
.rva JS_FrameAlwaysPublishBefore_FrameInterpProperty_get_field, JS_FrameAlwaysPublishBefore_FrameInterpProperty_get_field_end, JS_FrameInterpAddDirect_unwind
.rva JS_FrameAlwaysPublishBefore_FrameInterpProperty_get_field2, JS_FrameAlwaysPublishBefore_FrameInterpProperty_get_field2_end, JS_FrameInterpAddDirect_unwind
.rva JS_FrameAlwaysPublishBefore_FrameInterpProperty_put_field, JS_FrameAlwaysPublishBefore_FrameInterpProperty_put_field_end, JS_FrameInterpAddDirect_unwind
.rva JS_FrameAlwaysPublishBefore_FrameInterpSlow, JS_FrameAlwaysPublishBefore_FrameInterpSlow_end, JS_FrameInterpAddDirect_unwind
.rva JS_FrameAlwaysPublishBefore_FrameNativeCallLinkDispatch, JS_FrameAlwaysPublishBefore_FrameNativeCallLinkDispatch_end, JS_FrameInterpAddDirect_unwind
.rva JS_FrameAlwaysPublishBefore_FrameNewNullObject, JS_FrameAlwaysPublishBefore_FrameNewNullObject_end, JS_FrameInterpAddDirect_unwind
.rva JS_FrameAlwaysPublishBefore_FrameProtoPersistentFill, JS_FrameAlwaysPublishBefore_FrameProtoPersistentFill_end, JS_FrameInterpAddDirect_unwind
.rva JS_FrameAlwaysPublishBefore_FreeValue, JS_FrameAlwaysPublishBefore_FreeValue_end, JS_FrameInterpAddDirect_unwind
.section .qjzzpf$A,"xr"
.p2align 2
.byte 81,74,83,80,85,66,95,85,78,87,73,78,68,95,118,49
.zero 16
.section .qjzzpf$Z,"xr"
.p2align 2
.byte 81,74,83,80,85,66,95,69,78,68,95,118,49,33,33,33
.long 29436, 1
.zero 29436
