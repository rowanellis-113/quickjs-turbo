.include "interpreter-private-abi-gas.inc"
/* R7791; Win64 VM register ABI, no new stack or C call on success. */
.equ FRAME_STRICT_EQ_MODE, 3
.intel_syntax noprefix
.include "strict_reference.inc"
.section .rdata$qjseqmode,"dr"
.p2align 2
.globl JS_FrameStrictEqMode
JS_FrameStrictEqMode:
.long FRAME_STRICT_EQ_MODE
.section .bss$qjseqstat,"bw"
.p2align 3
.globl JS_FrameStrictEqStats
JS_FrameStrictEqStats:
.zero 128
.section .qjscold$zzeq,"xr"
.p2align 4
.globl JS_FrameStrictEqClean, JS_FrameStrictEqClean_end
.def JS_FrameStrictEqClean; .scl 2; .type 32; .endef
JS_FrameStrictEqClean:
.include "strict_body.inc"
JS_FrameStrictEqClean_end:
.section .pdata$zzqjseq,"dr"
.p2align 2
.rva JS_FrameStrictEqClean, JS_FrameStrictEqClean_end, JS_FrameInterpPropertyCold_unwind
.include "strict_identity.inc"
