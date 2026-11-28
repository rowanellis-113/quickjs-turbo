"""Native AArch64 ELF coroutine fast-segment executor (JS_CVMRunFastSegment).

Executes contiguous zero-call, zero-allocation coroutine bytecode segments directly
over JSAsyncFunctionState's live frame (pc, sp, locals, args, var_refs, ctx, bc, rt)
using an 8-byte RELRO jump table in AArch64 ELF GAS.

Because JS_CVMRunFastSegment is a strict leaf function (zero calls), all 10 live
pointers reside in caller-saved registers (x6..x15), leaving x0..x5, x16, x17 as
scratch with zero stack frame and zero callee-saved register spills.

Any guard miss (type mismatch, rc == 1 release, interrupt_counter <= 1, IC miss,
call/yield/await) leaves state unmutated and returns updated pc/sp cleanly to the
retained C coroutine loop.
"""

from __future__ import annotations

from pathlib import Path
import re

from arm64.paths_arm64 import source_file


def _load_opcodes(source: Path) -> tuple[list[str], dict[str, int]]:
    text = source_file(source, "quickjs-opcode.h").read_text(encoding="utf-8")
    matches = re.findall(r"^\s*DEF\(\s*(\w+)\s*,\s*(\d+)\s*,", text, re.M)
    if len(matches) < 200:
        raise ValueError(f"Unexpected opcode count: {len(matches)}")
    ops = [m[0] for m in matches]
    sizes = {m[0]: int(m[1]) for m in matches}
    return ops, sizes


def _build_handlers(ops: list[str], property_ic: bool) -> tuple[dict[str, list[str]], list[str]]:
    op_id = {name: i for i, name in enumerate(ops)}
    op_if_false8 = op_id["if_false8"]
    op_if_true8 = op_id["if_true8"]
    op_push_atom_value = op_id["push_atom_value"]
    op_strict_eq = op_id["strict_eq"]
    op_strict_neq = op_id["strict_neq"]

    # Zero-spill leaf register convention inside JS_CVMRunFastSegment:
    #   x15 = JSCVMFastState *state
    #         [x15, #0]  pc      [x15, #8]  sp
    #         [x15, #16] locals  [x15, #24] args
    #         [x15, #32] refs    [x15, #40] ctx
    #         [x15, #48] bc      [x15, #56] rt
    #   x14 = pc
    #   x13 = sp
    #   x12 = locals (var_buf)
    #   x11 = args   (arg_buf)
    #   x10 = refs   (var_refs)
    #   x9  = ctx    (b->realm)
    #   x8  = bc     (JSFunctionBytecode *)
    #   x7  = rt     (JSRuntime *)
    #   x6  = &.Lcvm_fast_table
    #   scratch = x0, x1, x2, x3, x4, x5, x16, x17

    def disp(adv: int = 0) -> list[str]:
        if adv == 0:
            return [
                "    ldrb w0, [x14]",
                "    ldr x1, [x6, x0, lsl #3]",
                "    br x1",
            ]
        return [
            f"    ldrb w0, [x14, #{adv}]!",
            "    ldr x1, [x6, x0, lsl #3]",
            "    br x1",
        ]

    def dup_if_rc(ptr_x: str, tag_w: str, lbl: str) -> list[str]:
        # Local skip label is always 3 instructions away (well within tbz range).
        return [
            f"    tbz {tag_w}, #31, {lbl}",
            f"    ldur w17, [{ptr_x}, #ARM_REF_COUNT_OFFSET]",
            "    add w17, w17, #1",
            f"    stur w17, [{ptr_x}, #ARM_REF_COUNT_OFFSET]",
            f"{lbl}:",
        ]

    def dec_rc_or_bail(ptr_x: str, tmp_w: str = "w17") -> list[str]:
        return [
            f"    ldur {tmp_w}, [{ptr_x}, #ARM_REF_COUNT_OFFSET]",
            f"    cmp {tmp_w}, #1",
            "    b.le .Lcvm_bail",
            f"    sub {tmp_w}, {tmp_w}, #1",
            f"    stur {tmp_w}, [{ptr_x}, #ARM_REF_COUNT_OFFSET]",
        ]

    handlers: dict[str, list[str]] = {}

    # --- nop ---
    handlers["nop"] = disp(1)

    # --- push constants ---
    for name, val in [
        ("push_minus1", -1),
        ("push_0", 0),
        ("push_1", 1),
        ("push_2", 2),
        ("push_3", 3),
        ("push_4", 4),
        ("push_5", 5),
        ("push_6", 6),
        ("push_7", 7),
    ]:
        if val == 0:
            handlers[name] = [
                "    stp xzr, xzr, [x13], #16",
                *disp(1),
            ]
        else:
            handlers[name] = [
                f"    mov x2, #{val}",
                "    stp x2, xzr, [x13], #16",
                *disp(1),
            ]

    handlers["push_i8"] = [
        "    ldrsb x2, [x14, #1]",
        "    stp x2, xzr, [x13], #16",
        *disp(2),
    ]
    handlers["push_i16"] = [
        "    ldursh x2, [x14, #1]",
        "    stp x2, xzr, [x13], #16",
        *disp(3),
    ]
    handlers["push_i32"] = [
        "    ldursw x2, [x14, #1]",
        "    stp x2, xzr, [x13], #16",
        *disp(5),
    ]
    handlers["push_false"] = [
        "    mov x3, #1",
        "    stp xzr, x3, [x13], #16",
        *disp(1),
    ]
    handlers["push_true"] = [
        "    mov x2, #1",
        "    stp x2, x2, [x13], #16",
        *disp(1),
    ]
    handlers["null"] = [
        "    mov x3, #2",
        "    stp xzr, x3, [x13], #16",
        *disp(1),
    ]
    handlers["undefined"] = [
        "    mov x3, #3",
        "    stp xzr, x3, [x13], #16",
        *disp(1),
    ]
    handlers["push_const8"] = [
        "    ldr x1, [x8, #ARM_OFF_JSFunctionBytecode_cpool]",
        "    ldrb w2, [x14, #1]",
        "    add x1, x1, w2, uxtw #4",
        "    ldp x2, x3, [x1]",
        "    stp x2, x3, [x13], #16",
        *dup_if_rc("x2", "w3", ".Lcvm_pc8_done"),
        *disp(2),
    ]
    handlers["push_const"] = [
        "    ldr x1, [x8, #ARM_OFF_JSFunctionBytecode_cpool]",
        "    ldur w2, [x14, #1]",
        "    add x1, x1, w2, uxtw #4",
        "    ldp x2, x3, [x1]",
        "    stp x2, x3, [x13], #16",
        *dup_if_rc("x2", "w3", ".Lcvm_pc32_done"),
        *disp(5),
    ]
    handlers["push_empty_string"] = [
        "    ldr x1, [x7, #ARM_OFF_JSRuntime_atom_array]",
        "    ldr x2, [x1, #(ARM_CONST_JS_ATOM_empty_string * 8)]",
        "    ldur w17, [x2, #ARM_REF_COUNT_OFFSET]",
        "    add w17, w17, #1",
        "    stur w17, [x2, #ARM_REF_COUNT_OFFSET]",
        "    mov x3, #-7",
        "    stp x2, x3, [x13], #16",
        *disp(1),
    ]
    handlers["push_atom_value"] = [
        "    ldur w1, [x14, #1]",
        "    cmp w1, #0",
        "    b.lt .Lcvm_bail",
        "    ldr x4, [x7, #ARM_OFF_JSRuntime_atom_array]",
        "    ldr x2, [x4, w1, uxtw #3]",
        "    ldrb w5, [x2, #7]",
        "    lsr w5, w5, #6",
        "    mov x3, #-7",
        "    cmp w5, #1",
        "    b.eq .Lcvm_pav_ok",
        "    mov x3, #-8",
        ".Lcvm_pav_ok:",
        "    ldur w17, [x2, #ARM_REF_COUNT_OFFSET]",
        "    add w17, w17, #1",
        "    stur w17, [x2, #ARM_REF_COUNT_OFFSET]",
        "    stp x2, x3, [x13], #16",
        *disp(5),
    ]

    # --- stack ops ---
    handlers["drop"] = [
        "    ldur w0, [x13, #-8]",
        "    tbz w0, #31, .Lcvm_drop_pop",
        "    ldur x1, [x13, #-16]",
        *dec_rc_or_bail("x1"),
        ".Lcvm_drop_pop:",
        "    sub x13, x13, #16",
        *disp(1),
    ]
    handlers["dup"] = [
        "    ldp x2, x3, [x13, #-16]",
        "    stp x2, x3, [x13], #16",
        *dup_if_rc("x2", "w3", ".Lcvm_dup_done"),
        *disp(1),
    ]
    handlers["dup1"] = [
        "    ldp x4, x5, [x13, #-32]",
        "    ldp x2, x3, [x13, #-16]",
        "    stp x4, x5, [x13, #-16]",
        "    stp x2, x3, [x13], #16",
        *dup_if_rc("x4", "w5", ".Lcvm_dup1_done"),
        *disp(1),
    ]
    handlers["dup2"] = [
        "    ldp x2, x3, [x13, #-32]",
        "    stp x2, x3, [x13, #0]",
        *dup_if_rc("x2", "w3", ".Lcvm_dup2_a"),
        "    ldp x2, x3, [x13, #-16]",
        "    stp x2, x3, [x13, #16]",
        "    add x13, x13, #32",
        *dup_if_rc("x2", "w3", ".Lcvm_dup2_b"),
        *disp(1),
    ]
    handlers["dup3"] = [
        "    ldp x2, x3, [x13, #-48]",
        "    stp x2, x3, [x13, #0]",
        *dup_if_rc("x2", "w3", ".Lcvm_dup3_a"),
        "    ldp x2, x3, [x13, #-32]",
        "    stp x2, x3, [x13, #16]",
        *dup_if_rc("x2", "w3", ".Lcvm_dup3_b"),
        "    ldp x2, x3, [x13, #-16]",
        "    stp x2, x3, [x13, #32]",
        "    add x13, x13, #48",
        *dup_if_rc("x2", "w3", ".Lcvm_dup3_c"),
        *disp(1),
    ]
    handlers["nip"] = [
        "    ldur w0, [x13, #-24]",
        "    tbz w0, #31, .Lcvm_nip_move",
        "    ldur x1, [x13, #-32]",
        *dec_rc_or_bail("x1"),
        ".Lcvm_nip_move:",
        "    ldp x2, x3, [x13, #-16]",
        "    stp x2, x3, [x13, #-32]",
        "    sub x13, x13, #16",
        *disp(1),
    ]
    handlers["nip1"] = [
        "    ldur w0, [x13, #-40]",
        "    tbz w0, #31, .Lcvm_nip1_move",
        "    ldur x1, [x13, #-48]",
        *dec_rc_or_bail("x1"),
        ".Lcvm_nip1_move:",
        "    ldp x2, x3, [x13, #-32]",
        "    ldp x4, x5, [x13, #-16]",
        "    stp x2, x3, [x13, #-48]",
        "    stp x4, x5, [x13, #-32]",
        "    sub x13, x13, #16",
        *disp(1),
    ]
    handlers["swap"] = [
        "    ldp x2, x3, [x13, #-32]",
        "    ldp x4, x5, [x13, #-16]",
        "    stp x4, x5, [x13, #-32]",
        "    stp x2, x3, [x13, #-16]",
        *disp(1),
    ]
    handlers["insert2"] = [
        # obj a -> a obj a
        "    ldp x4, x5, [x13, #-32]",
        "    ldp x2, x3, [x13, #-16]",
        "    stp x2, x3, [x13, #-32]",
        "    stp x4, x5, [x13, #-16]",
        "    stp x2, x3, [x13], #16",
        *dup_if_rc("x2", "w3", ".Lcvm_ins2_done"),
        *disp(1),
    ]
    handlers["insert3"] = [
        # obj prop a -> a obj prop a
        "    ldp x2, x3, [x13, #-16]",
        "    ldp x4, x5, [x13, #-32]",
        "    ldp x0, x1, [x13, #-48]",
        "    stp x2, x3, [x13, #-48]",
        "    stp x0, x1, [x13, #-32]",
        "    stp x4, x5, [x13, #-16]",
        "    stp x2, x3, [x13], #16",
        *dup_if_rc("x2", "w3", ".Lcvm_ins3_done"),
        *disp(1),
    ]
    handlers["perm3"] = [
        # obj a b -> a obj b
        "    ldp x2, x3, [x13, #-48]",
        "    ldp x4, x5, [x13, #-32]",
        "    stp x4, x5, [x13, #-48]",
        "    stp x2, x3, [x13, #-32]",
        *disp(1),
    ]
    handlers["rot3l"] = [
        # x a b -> a b x
        "    ldp x0, x1, [x13, #-48]",
        "    ldp x2, x3, [x13, #-32]",
        "    ldp x4, x5, [x13, #-16]",
        "    stp x2, x3, [x13, #-48]",
        "    stp x4, x5, [x13, #-32]",
        "    stp x0, x1, [x13, #-16]",
        *disp(1),
    ]
    handlers["rot3r"] = [
        # a b x -> x a b
        "    ldp x0, x1, [x13, #-16]",
        "    ldp x2, x3, [x13, #-32]",
        "    ldp x4, x5, [x13, #-48]",
        "    stp x0, x1, [x13, #-48]",
        "    stp x4, x5, [x13, #-32]",
        "    stp x2, x3, [x13, #-16]",
        *disp(1),
    ]

    # --- fast type / object checks ---
    handlers["to_object"] = [
        "    ldur w0, [x13, #-8]",
        "    cmn w0, #1",
        "    b.ne .Lcvm_bail",
        *disp(1),
    ]
    handlers["typeof_is_undefined"] = [
        "    ldur w0, [x13, #-8]",
        "    cmp w0, #3",
        "    b.eq .Lcvm_tiu_t",
        "    cmp w0, #2",
        "    b.ls .Lcvm_tiu_f",
        "    cmn w0, #7",
        "    b.eq .Lcvm_tiu_rc",
        "    cmn w0, #1",
        "    b.ne .Lcvm_bail",
        "    ldur x2, [x13, #-16]",
        "    ldrb w1, [x2, #ARM_BIT_JSObject_is_HTMLDDA_BYTE]",
        "    tst w1, #ARM_BIT_JSObject_is_HTMLDDA_MASK",
        "    b.ne .Lcvm_bail",
        *dec_rc_or_bail("x2"),
        "    b .Lcvm_tiu_f",
        ".Lcvm_tiu_rc:",
        "    ldur x2, [x13, #-16]",
        *dec_rc_or_bail("x2"),
        ".Lcvm_tiu_f:",
        "    mov w0, #0",
        "    sub x13, x13, #16",
        "    add x14, x14, #1",
        "    b .Lcvm_cmp_done",
        ".Lcvm_tiu_t:",
        "    mov w0, #1",
        "    sub x13, x13, #16",
        "    add x14, x14, #1",
        "    b .Lcvm_cmp_done",
    ]
    handlers["typeof_is_function"] = [
        "    ldur w0, [x13, #-8]",
        "    cmp w0, #3",
        "    b.ls .Lcvm_tif_f",
        "    cmn w0, #7",
        "    b.eq .Lcvm_tif_str",
        "    cmn w0, #1",
        "    b.ne .Lcvm_bail",
        "    ldur x2, [x13, #-16]",
        "    ldrh w1, [x2, #ARM_OFF_JSObject_class_id]",
        "    cmp w1, #ARM_CONST_JS_CLASS_BYTECODE_FUNCTION",
        "    b.eq .Lcvm_tif_obj_t",
        "    cmp w1, #ARM_CONST_JS_CLASS_C_FUNCTION",
        "    b.eq .Lcvm_tif_obj_t",
        "    cmp w1, #ARM_CONST_JS_CLASS_OBJECT",
        "    b.eq .Lcvm_tif_obj_f",
        "    cmp w1, #ARM_CONST_JS_CLASS_ARRAY",
        "    b.ne .Lcvm_bail",
        ".Lcvm_tif_obj_f:",
        *dec_rc_or_bail("x2"),
        "    b .Lcvm_tif_f",
        ".Lcvm_tif_obj_t:",
        *dec_rc_or_bail("x2"),
        "    mov w0, #1",
        "    sub x13, x13, #16",
        "    add x14, x14, #1",
        "    b .Lcvm_cmp_done",
        ".Lcvm_tif_str:",
        "    ldur x2, [x13, #-16]",
        *dec_rc_or_bail("x2"),
        ".Lcvm_tif_f:",
        "    mov w0, #0",
        "    sub x13, x13, #16",
        "    add x14, x14, #1",
        "    b .Lcvm_cmp_done",
    ]

    # --- locals get/put/set ---
    for i in range(4):
        off = i * 16
        handlers[f"get_loc{i}"] = [
            f"    ldp x2, x3, [x12, #{off}]",
            "    ldrb w0, [x14, #1]!",
            "    ldr x1, [x6, x0, lsl #3]",
            "    stp x2, x3, [x13], #16",
            *dup_if_rc("x2", "w3", f".Lcvm_gl{i}_done"),
            "    br x1",
        ]
        handlers[f"put_loc{i}"] = [
            f"    ldr w0, [x12, #{off + 8}]",
            f"    tbz w0, #31, .Lcvm_pl{i}_wr",
            f"    ldr x1, [x12, #{off}]",
            *dec_rc_or_bail("x1"),
            f".Lcvm_pl{i}_wr:",
            "    ldp x2, x3, [x13, #-16]!",
            f"    stp x2, x3, [x12, #{off}]",
            *disp(1),
        ]
        handlers[f"set_loc{i}"] = [
            f"    ldr w0, [x12, #{off + 8}]",
            f"    tbz w0, #31, .Lcvm_sl{i}_wr",
            f"    ldr x1, [x12, #{off}]",
            *dec_rc_or_bail("x1"),
            f".Lcvm_sl{i}_wr:",
            "    ldp x2, x3, [x13, #-16]",
            f"    stp x2, x3, [x12, #{off}]",
            *dup_if_rc("x2", "w3", f".Lcvm_sl{i}_done"),
            *disp(1),
        ]

    handlers["get_loc0_loc1"] = [
        "    ldp x2, x3, [x12, #0]",
        "    stp x2, x3, [x13, #0]",
        *dup_if_rc("x2", "w3", ".Lcvm_gl01_a"),
        "    ldp x2, x3, [x12, #16]",
        "    stp x2, x3, [x13, #16]",
        "    add x13, x13, #32",
        *dup_if_rc("x2", "w3", ".Lcvm_gl01_b"),
        *disp(1),
    ]

    for suffix, load_idx, adv in [
        ("8", "    ldrb w4, [x14, #1]", 2),
        ("", "    ldurh w4, [x14, #1]", 3),
    ]:
        handlers[f"get_loc{suffix}"] = [
            load_idx,
            "    add x5, x12, w4, uxtw #4",
            "    ldp x2, x3, [x5]",
            f"    ldrb w0, [x14, #{adv}]!",
            "    ldr x1, [x6, x0, lsl #3]",
            "    stp x2, x3, [x13], #16",
            *dup_if_rc("x2", "w3", f".Lcvm_glx{suffix}_done"),
            "    br x1",
        ]
        handlers[f"put_loc{suffix}"] = [
            load_idx,
            "    add x5, x12, w4, uxtw #4",
            "    ldr w0, [x5, #8]",
            f"    tbz w0, #31, .Lcvm_plx{suffix}_wr",
            "    ldr x1, [x5, #0]",
            *dec_rc_or_bail("x1"),
            f".Lcvm_plx{suffix}_wr:",
            "    ldp x2, x3, [x13, #-16]!",
            "    stp x2, x3, [x5]",
            *disp(adv),
        ]
        handlers[f"set_loc{suffix}"] = [
            load_idx,
            "    add x5, x12, w4, uxtw #4",
            "    ldr w0, [x5, #8]",
            f"    tbz w0, #31, .Lcvm_slx{suffix}_wr",
            "    ldr x1, [x5, #0]",
            *dec_rc_or_bail("x1"),
            f".Lcvm_slx{suffix}_wr:",
            "    ldp x2, x3, [x13, #-16]",
            "    stp x2, x3, [x5]",
            *dup_if_rc("x2", "w3", f".Lcvm_slx{suffix}_done"),
            *disp(adv),
        ]

    handlers["set_loc_uninitialized"] = [
        "    ldurh w4, [x14, #1]",
        "    add x5, x12, w4, uxtw #4",
        "    ldr w0, [x5, #8]",
        "    tbz w0, #31, .Lcvm_slu_wr",
        "    ldr x1, [x5, #0]",
        *dec_rc_or_bail("x1"),
        ".Lcvm_slu_wr:",
        "    mov x3, #4",
        "    stp xzr, x3, [x5]",
        *disp(3),
    ]
    # Prefetch next opcode before tag check to hide ldp load-to-use latency in hot loops.
    handlers["get_loc_check"] = [
        "    ldurh w4, [x14, #1]",
        "    ldrb w0, [x14, #3]",
        "    add x5, x12, w4, uxtw #4",
        "    ldp x2, x3, [x5]",
        "    ldr x1, [x6, x0, lsl #3]",
        "    cmp w3, #4",
        "    b.eq .Lcvm_bail",
        "    add x14, x14, #3",
        "    stp x2, x3, [x13], #16",
        *dup_if_rc("x2", "w3", ".Lcvm_glc_done"),
        "    br x1",
    ]
    handlers["put_loc_check"] = [
        "    ldurh w4, [x14, #1]",
        "    add x5, x12, w4, uxtw #4",
        "    ldr w0, [x5, #8]",
        "    cmp w0, #4",
        "    b.eq .Lcvm_bail",
        "    tbz w0, #31, .Lcvm_plc_wr",
        "    ldr x1, [x5, #0]",
        *dec_rc_or_bail("x1"),
        ".Lcvm_plc_wr:",
        "    ldp x2, x3, [x13, #-16]!",
        "    stp x2, x3, [x5]",
        *disp(3),
    ]
    handlers["put_loc_check_init"] = [
        "    ldurh w4, [x14, #1]",
        "    add x5, x12, w4, uxtw #4",
        "    ldr w0, [x5, #8]",
        "    cmp w0, #4",
        "    b.ne .Lcvm_bail",
        "    ldp x2, x3, [x13, #-16]!",
        "    stp x2, x3, [x5]",
        *disp(3),
    ]

    # --- args get/put/set ---
    for i in range(4):
        off = i * 16
        handlers[f"get_arg{i}"] = [
            f"    ldp x2, x3, [x11, #{off}]",
            "    ldrb w0, [x14, #1]!",
            "    ldr x1, [x6, x0, lsl #3]",
            "    stp x2, x3, [x13], #16",
            *dup_if_rc("x2", "w3", f".Lcvm_ga{i}_done"),
            "    br x1",
        ]
        handlers[f"put_arg{i}"] = [
            f"    ldr w0, [x11, #{off + 8}]",
            f"    tbz w0, #31, .Lcvm_pa{i}_wr",
            f"    ldr x1, [x11, #{off}]",
            *dec_rc_or_bail("x1"),
            f".Lcvm_pa{i}_wr:",
            "    ldp x2, x3, [x13, #-16]!",
            f"    stp x2, x3, [x11, #{off}]",
            *disp(1),
        ]
        handlers[f"set_arg{i}"] = [
            f"    ldr w0, [x11, #{off + 8}]",
            f"    tbz w0, #31, .Lcvm_sa{i}_wr",
            f"    ldr x1, [x11, #{off}]",
            *dec_rc_or_bail("x1"),
            f".Lcvm_sa{i}_wr:",
            "    ldp x2, x3, [x13, #-16]",
            f"    stp x2, x3, [x11, #{off}]",
            *dup_if_rc("x2", "w3", f".Lcvm_sa{i}_done"),
            *disp(1),
        ]

    handlers["get_arg"] = [
        "    ldurh w4, [x14, #1]",
        "    add x5, x11, w4, uxtw #4",
        "    ldp x2, x3, [x5]",
        "    ldrb w0, [x14, #3]!",
        "    ldr x1, [x6, x0, lsl #3]",
        "    stp x2, x3, [x13], #16",
        *dup_if_rc("x2", "w3", ".Lcvm_gax_done"),
        "    br x1",
    ]
    handlers["put_arg"] = [
        "    ldurh w4, [x14, #1]",
        "    add x5, x11, w4, uxtw #4",
        "    ldr w0, [x5, #8]",
        "    tbz w0, #31, .Lcvm_pax_wr",
        "    ldr x1, [x5, #0]",
        *dec_rc_or_bail("x1"),
        ".Lcvm_pax_wr:",
        "    ldp x2, x3, [x13, #-16]!",
        "    stp x2, x3, [x5]",
        *disp(3),
    ]
    handlers["set_arg"] = [
        "    ldurh w4, [x14, #1]",
        "    add x5, x11, w4, uxtw #4",
        "    ldr w0, [x5, #8]",
        "    tbz w0, #31, .Lcvm_sax_wr",
        "    ldr x1, [x5, #0]",
        *dec_rc_or_bail("x1"),
        ".Lcvm_sax_wr:",
        "    ldp x2, x3, [x13, #-16]",
        "    stp x2, x3, [x5]",
        *dup_if_rc("x2", "w3", ".Lcvm_sax_done"),
        *disp(3),
    ]

    # --- closure var_refs ---
    for i in range(4):
        handlers[f"get_var_ref{i}"] = [
            f"    ldr x4, [x10, #{i * 8}]",
            "    ldr x5, [x4, #ARM_OFF_JSVarRef_pvalue]",
            "    ldp x2, x3, [x5]",
            "    ldrb w0, [x14, #1]!",
            "    ldr x1, [x6, x0, lsl #3]",
            "    stp x2, x3, [x13], #16",
            *dup_if_rc("x2", "w3", f".Lcvm_gvr{i}_done"),
            "    br x1",
        ]
        handlers[f"put_var_ref{i}"] = [
            f"    ldr x4, [x10, #{i * 8}]",
            "    ldr x5, [x4, #ARM_OFF_JSVarRef_pvalue]",
            "    ldr w0, [x5, #8]",
            f"    tbz w0, #31, .Lcvm_pvr{i}_wr",
            "    ldr x1, [x5, #0]",
            *dec_rc_or_bail("x1"),
            f".Lcvm_pvr{i}_wr:",
            "    ldp x2, x3, [x13, #-16]!",
            "    stp x2, x3, [x5]",
            *disp(1),
        ]
        handlers[f"set_var_ref{i}"] = [
            f"    ldr x4, [x10, #{i * 8}]",
            "    ldr x5, [x4, #ARM_OFF_JSVarRef_pvalue]",
            "    ldr w0, [x5, #8]",
            f"    tbz w0, #31, .Lcvm_svr{i}_wr",
            "    ldr x1, [x5, #0]",
            *dec_rc_or_bail("x1"),
            f".Lcvm_svr{i}_wr:",
            "    ldp x2, x3, [x13, #-16]",
            "    stp x2, x3, [x5]",
            *dup_if_rc("x2", "w3", f".Lcvm_svr{i}_done"),
            *disp(1),
        ]

    handlers["get_var_ref"] = [
        "    ldurh w4, [x14, #1]",
        "    ldr x4, [x10, w4, uxtw #3]",
        "    ldr x5, [x4, #ARM_OFF_JSVarRef_pvalue]",
        "    ldp x2, x3, [x5]",
        "    ldrb w0, [x14, #3]!",
        "    ldr x1, [x6, x0, lsl #3]",
        "    stp x2, x3, [x13], #16",
        *dup_if_rc("x2", "w3", ".Lcvm_gvrx_done"),
        "    br x1",
    ]
    handlers["get_var_ref_check"] = [
        "    ldurh w4, [x14, #1]",
        "    ldrb w0, [x14, #3]",
        "    ldr x4, [x10, w4, uxtw #3]",
        "    ldr x5, [x4, #ARM_OFF_JSVarRef_pvalue]",
        "    ldp x2, x3, [x5]",
        "    ldr x1, [x6, x0, lsl #3]",
        "    cmp w3, #4",
        "    b.eq .Lcvm_bail",
        "    add x14, x14, #3",
        "    stp x2, x3, [x13], #16",
        *dup_if_rc("x2", "w3", ".Lcvm_gvrc_done"),
        "    br x1",
    ]
    handlers["put_var_ref"] = [
        "    ldurh w4, [x14, #1]",
        "    ldr x4, [x10, w4, uxtw #3]",
        "    ldr x5, [x4, #ARM_OFF_JSVarRef_pvalue]",
        "    ldr w0, [x5, #8]",
        "    tbz w0, #31, .Lcvm_pvrx_wr",
        "    ldr x1, [x5, #0]",
        *dec_rc_or_bail("x1"),
        ".Lcvm_pvrx_wr:",
        "    ldp x2, x3, [x13, #-16]!",
        "    stp x2, x3, [x5]",
        *disp(3),
    ]
    handlers["set_var_ref"] = [
        "    ldurh w4, [x14, #1]",
        "    ldr x4, [x10, w4, uxtw #3]",
        "    ldr x5, [x4, #ARM_OFF_JSVarRef_pvalue]",
        "    ldr w0, [x5, #8]",
        "    tbz w0, #31, .Lcvm_svrx_wr",
        "    ldr x1, [x5, #0]",
        *dec_rc_or_bail("x1"),
        ".Lcvm_svrx_wr:",
        "    ldp x2, x3, [x13, #-16]",
        "    stp x2, x3, [x5]",
        *dup_if_rc("x2", "w3", ".Lcvm_svrx_done"),
        *disp(3),
    ]
    handlers["put_var_ref_check"] = [
        "    ldurh w4, [x14, #1]",
        "    ldr x4, [x10, w4, uxtw #3]",
        "    ldr x5, [x4, #ARM_OFF_JSVarRef_pvalue]",
        "    ldr w0, [x5, #8]",
        "    cmp w0, #4",
        "    b.eq .Lcvm_bail",
        "    tbz w0, #31, .Lcvm_pvrc_wr",
        "    ldr x1, [x5, #0]",
        *dec_rc_or_bail("x1"),
        ".Lcvm_pvrc_wr:",
        "    ldp x2, x3, [x13, #-16]!",
        "    stp x2, x3, [x5]",
        *disp(3),
    ]
    handlers["put_var_ref_check_init"] = [
        "    ldurh w4, [x14, #1]",
        "    ldr x4, [x10, w4, uxtw #3]",
        "    ldr x5, [x4, #ARM_OFF_JSVarRef_pvalue]",
        "    ldr w0, [x5, #8]",
        "    cmp w0, #4",
        "    b.ne .Lcvm_bail",
        "    ldp x2, x3, [x13, #-16]!",
        "    stp x2, x3, [x5]",
        *disp(3),
    ]

    # --- global var reads (get_var / get_var_undef; w16 holds atom) ---
    def global_hash_probe(obj_off: str, prefix: str, absent_lbl: str, check_tdz: bool) -> list[str]:
        out = [
            f"    ldr x2, [x9, #{obj_off}]",
            "    ldr x3, [x2, #ARM_OFF_JSObject_shape]",
            "    movz x0, #0x83eb",
            "    movk x0, #0x80b5, lsl #16",
            "    movk x0, #0x8646, lsl #32",
            "    movk x0, #0x61c8, lsl #48",
            "    uxtw x1, w16",
            "    mul x1, x1, x0",
            "    lsr x1, x1, #32",
            "    ldr w4, [x3, #ARM_OFF_JSShape_prop_hash_mask]",
            "    add x5, x3, w4, uxtw #2",
            "    add x5, x5, #(ARM_OFF_JSShape_hash_table + 4)",
            "    uxtw x17, w4",
            "    add x17, x17, #1",
            "    mul x1, x1, x17",
            "    lsr x1, x1, #32",
            "    sub x17, x5, x1, lsl #2",
            "    ldur w4, [x17, #-4]",
            f".L{prefix}_probe:",
            f"    cbz w4, {absent_lbl}",
            "    sub w1, w4, #1",
            "    add x0, x5, w1, uxtw #3",
            "    ldr w3, [x0, #4]",
            "    cmp w3, w16",
            f"    b.eq .L{prefix}_found",
            "    ldr w4, [x0, #0]",
            "    and w4, w4, #ARM_PROPERTY_DESC_NEXT_MASK",
            f"    b .L{prefix}_probe",
            f".L{prefix}_found:",
            "    ldr w3, [x0, #0]",
            "    tst w3, #ARM_PROPERTY_DESC_TMASK",
            "    b.ne .Lcvm_bail",
            "    ldr x3, [x2, #ARM_OFF_JSObject_prop]",
            "    add x3, x3, w1, uxtw #4",
            "    ldp x2, x3, [x3]",
        ]
        if check_tdz:
            out += [
                "    cmp w3, #4",
                "    b.eq .Lcvm_bail",
            ]
        out += [
            "    stp x2, x3, [x13], #16",
            *dup_if_rc("x2", "w3", f".L{prefix}_done"),
            *disp(5),
        ]
        return out

    for gv_name in ("get_var", "get_var_undef"):
        p = f"cvm_{gv_name}"
        handlers[gv_name] = [
            "    ldur w16, [x14, #1]",
            *global_hash_probe("ARM_OFF_JSContext_global_var_obj", f"{p}_lex", f".L{p}_obj", True),
            f".L{p}_obj:",
            *global_hash_probe("ARM_OFF_JSContext_global_obj", f"{p}_glob", ".Lcvm_bail", False),
        ]

    # --- in-place int32 local updates ---
    handlers["inc_loc"] = [
        "    ldrb w4, [x14, #1]",
        "    add x5, x12, w4, uxtw #4",
        "    ldr w0, [x5, #8]",
        "    cbnz w0, .Lcvm_bail",
        "    ldr w0, [x5, #0]",
        "    adds w0, w0, #1",
        "    b.vs .Lcvm_bail",
        "    sxtw x0, w0",
        "    str x0, [x5, #0]",
        *disp(2),
    ]
    handlers["dec_loc"] = [
        "    ldrb w4, [x14, #1]",
        "    add x5, x12, w4, uxtw #4",
        "    ldr w0, [x5, #8]",
        "    cbnz w0, .Lcvm_bail",
        "    ldr w0, [x5, #0]",
        "    subs w0, w0, #1",
        "    b.vs .Lcvm_bail",
        "    sxtw x0, w0",
        "    str x0, [x5, #0]",
        *disp(2),
    ]
    handlers["add_loc"] = [
        "    ldrb w4, [x14, #1]",
        "    add x5, x12, w4, uxtw #4",
        "    ldr w0, [x5, #8]",
        "    ldur w1, [x13, #-8]",
        "    orr w0, w0, w1",
        "    cbnz w0, .Lcvm_bail",
        "    ldr w0, [x5, #0]",
        "    ldur w1, [x13, #-16]",
        "    adds w0, w0, w1",
        "    b.vs .Lcvm_bail",
        "    sxtw x0, w0",
        "    str x0, [x5, #0]",
        "    sub x13, x13, #16",
        *disp(2),
    ]

    # --- int32 arithmetic & bitwise ---
    handlers["plus"] = [
        "    ldur w0, [x13, #-8]",
        "    cbz w0, .Lcvm_plus_ok",
        "    cmp w0, #8",
        "    b.ne .Lcvm_bail",
        ".Lcvm_plus_ok:",
        *disp(1),
    ]
    handlers["neg"] = [
        "    ldur w0, [x13, #-8]",
        "    cbnz w0, .Lcvm_bail",
        "    ldur w0, [x13, #-16]",
        "    cbz w0, .Lcvm_bail",
        "    negs w0, w0",
        "    b.vs .Lcvm_bail",
        "    sxtw x0, w0",
        "    stur x0, [x13, #-16]",
        *disp(1),
    ]
    handlers["not"] = [
        "    ldur w0, [x13, #-8]",
        "    cbnz w0, .Lcvm_bail",
        "    ldur w0, [x13, #-16]",
        "    mvn w0, w0",
        "    sxtw x0, w0",
        "    stur x0, [x13, #-16]",
        *disp(1),
    ]
    handlers["inc"] = [
        "    ldur w0, [x13, #-8]",
        "    cbnz w0, .Lcvm_bail",
        "    ldur w0, [x13, #-16]",
        "    adds w0, w0, #1",
        "    b.vs .Lcvm_bail",
        "    sxtw x0, w0",
        "    stur x0, [x13, #-16]",
        *disp(1),
    ]
    handlers["dec"] = [
        "    ldur w0, [x13, #-8]",
        "    cbnz w0, .Lcvm_bail",
        "    ldur w0, [x13, #-16]",
        "    subs w0, w0, #1",
        "    b.vs .Lcvm_bail",
        "    sxtw x0, w0",
        "    stur x0, [x13, #-16]",
        *disp(1),
    ]
    handlers["post_inc"] = [
        "    ldur w0, [x13, #-8]",
        "    cbnz w0, .Lcvm_bail",
        "    ldur w0, [x13, #-16]",
        "    adds w0, w0, #1",
        "    b.vs .Lcvm_bail",
        "    sxtw x0, w0",
        "    stp x0, xzr, [x13], #16",
        *disp(1),
    ]
    handlers["post_dec"] = [
        "    ldur w0, [x13, #-8]",
        "    cbnz w0, .Lcvm_bail",
        "    ldur w0, [x13, #-16]",
        "    subs w0, w0, #1",
        "    b.vs .Lcvm_bail",
        "    sxtw x0, w0",
        "    stp x0, xzr, [x13], #16",
        *disp(1),
    ]
    handlers["add"] = [
        "    ldur w0, [x13, #-24]",
        "    ldur w1, [x13, #-8]",
        "    orr w0, w0, w1",
        "    cbnz w0, .Lcvm_bail",
        "    ldur w0, [x13, #-32]",
        "    ldur w1, [x13, #-16]",
        "    adds w0, w0, w1",
        "    b.vs .Lcvm_bail",
        "    sxtw x0, w0",
        "    stur x0, [x13, #-32]",
        "    sub x13, x13, #16",
        *disp(1),
    ]
    handlers["sub"] = [
        "    ldur w0, [x13, #-24]",
        "    ldur w1, [x13, #-8]",
        "    orr w0, w0, w1",
        "    cbnz w0, .Lcvm_bail",
        "    ldur w0, [x13, #-32]",
        "    ldur w1, [x13, #-16]",
        "    subs w0, w0, w1",
        "    b.vs .Lcvm_bail",
        "    sxtw x0, w0",
        "    stur x0, [x13, #-32]",
        "    sub x13, x13, #16",
        *disp(1),
    ]
    handlers["mul"] = [
        "    ldur w0, [x13, #-24]",
        "    ldur w1, [x13, #-8]",
        "    orr w0, w0, w1",
        "    cbnz w0, .Lcvm_bail",
        "    ldur w0, [x13, #-32]",
        "    ldur w1, [x13, #-16]",
        "    smull x2, w0, w1",
        "    cmp x2, w2, sxtw",
        "    b.ne .Lcvm_bail",
        "    cbnz w2, .Lcvm_mul_ok",
        "    orr w3, w0, w1",
        "    cmp w3, #0",
        "    b.lt .Lcvm_bail",
        ".Lcvm_mul_ok:",
        "    stur x2, [x13, #-32]",
        "    sub x13, x13, #16",
        *disp(1),
    ]
    handlers["div"] = [
        "    ldur w0, [x13, #-24]",
        "    ldur w1, [x13, #-8]",
        "    orr w0, w0, w1",
        "    cbnz w0, .Lcvm_bail",
        "    ldur w0, [x13, #-32]",
        "    ldur w1, [x13, #-16]",
        "    cmp w0, #0",
        "    b.lt .Lcvm_bail",
        "    cmp w1, #0",
        "    b.le .Lcvm_bail",
        "    udiv w2, w0, w1",
        "    msub w3, w2, w1, w0",
        "    cbnz w3, .Lcvm_bail",
        "    stur x2, [x13, #-32]",
        "    sub x13, x13, #16",
        *disp(1),
    ]
    handlers["mod"] = [
        "    ldur w0, [x13, #-24]",
        "    ldur w1, [x13, #-8]",
        "    orr w0, w0, w1",
        "    cbnz w0, .Lcvm_bail",
        "    ldur w0, [x13, #-32]",
        "    ldur w1, [x13, #-16]",
        "    cmp w0, #0",
        "    b.lt .Lcvm_bail",
        "    cmp w1, #0",
        "    b.le .Lcvm_bail",
        "    udiv w2, w0, w1",
        "    msub w3, w2, w1, w0",
        "    stur x3, [x13, #-32]",
        "    sub x13, x13, #16",
        *disp(1),
    ]
    for name, insn in [("and", "and"), ("or", "orr"), ("xor", "eor")]:
        handlers[name] = [
            "    ldur w0, [x13, #-24]",
            "    ldur w1, [x13, #-8]",
            "    orr w0, w0, w1",
            "    cbnz w0, .Lcvm_bail",
            "    ldur w0, [x13, #-32]",
            "    ldur w1, [x13, #-16]",
            f"    {insn} w0, w0, w1",
            "    sxtw x0, w0",
            "    stur x0, [x13, #-32]",
            "    sub x13, x13, #16",
            *disp(1),
        ]
    for name, insn in [("shl", "lsl"), ("sar", "asr")]:
        handlers[name] = [
            "    ldur w0, [x13, #-24]",
            "    ldur w1, [x13, #-8]",
            "    orr w0, w0, w1",
            "    cbnz w0, .Lcvm_bail",
            "    ldur w0, [x13, #-32]",
            "    ldur w1, [x13, #-16]",
            f"    {insn} w0, w0, w1",
            "    sxtw x0, w0",
            "    stur x0, [x13, #-32]",
            "    sub x13, x13, #16",
            *disp(1),
        ]
    handlers["shr"] = [
        "    ldur w0, [x13, #-24]",
        "    ldur w1, [x13, #-8]",
        "    orr w0, w0, w1",
        "    cbnz w0, .Lcvm_bail",
        "    ldur w0, [x13, #-32]",
        "    ldur w1, [x13, #-16]",
        "    lsr w0, w0, w1",
        "    cmp w0, #0",
        "    b.lt .Lcvm_bail",
        "    stur x0, [x13, #-32]",
        "    sub x13, x13, #16",
        *disp(1),
    ]
    handlers["lnot"] = [
        "    ldur w0, [x13, #-8]",
        "    cmp w0, #3",
        "    b.hi .Lcvm_bail",
        "    ldur w1, [x13, #-16]",
        "    cmp w1, #0",
        "    cset w0, eq",
        "    sub x13, x13, #16",
        "    add x14, x14, #1",
        "    b .Lcvm_cmp_done",
    ]
    for pred_name, target_tag in [("is_undefined", 3), ("is_null", 2)]:
        handlers[pred_name] = [
            "    ldur w0, [x13, #-8]",
            f"    cmp w0, #{target_tag}",
            f"    b.eq .Lcvm_{pred_name}_t",
            f"    tbz w0, #31, .Lcvm_{pred_name}_f",
            "    ldur x2, [x13, #-16]",
            *dec_rc_or_bail("x2"),
            f".Lcvm_{pred_name}_f:",
            "    mov w0, #0",
            "    sub x13, x13, #16",
            "    add x14, x14, #1",
            "    b .Lcvm_cmp_done",
            f".Lcvm_{pred_name}_t:",
            "    mov w0, #1",
            "    sub x13, x13, #16",
            "    add x14, x14, #1",
            "    b .Lcvm_cmp_done",
        ]
    handlers["is_undefined_or_null"] = [
        "    ldur w0, [x13, #-8]",
        "    cmp w0, #2",
        "    b.eq .Lcvm_iuon_t",
        "    cmp w0, #3",
        "    b.eq .Lcvm_iuon_t",
        "    tbz w0, #31, .Lcvm_iuon_f",
        "    ldur x2, [x13, #-16]",
        *dec_rc_or_bail("x2"),
        ".Lcvm_iuon_f:",
        "    mov w0, #0",
        "    sub x13, x13, #16",
        "    add x14, x14, #1",
        "    b .Lcvm_cmp_done",
        ".Lcvm_iuon_t:",
        "    mov w0, #1",
        "    sub x13, x13, #16",
        "    add x14, x14, #1",
        "    b .Lcvm_cmp_done",
    ]

    # --- comparisons (with fused if_false8 / if_true8 tail via .Lcvm_cmp_done) ---
    for name, cond in [("lt", "lt"), ("lte", "le"), ("gt", "gt"), ("gte", "ge")]:
        handlers[name] = [
            "    ldur w0, [x13, #-24]",
            "    ldur w1, [x13, #-8]",
            "    orr w0, w0, w1",
            "    cbnz w0, .Lcvm_bail",
            "    ldur w2, [x13, #-32]",
            "    ldur w3, [x13, #-16]",
            "    cmp w2, w3",
            f"    cset w0, {cond}",
            "    sub x13, x13, #32",
            "    add x14, x14, #1",
            "    b .Lcvm_cmp_done",
        ]

    for name, cond, obj_eq_val in [
        ("strict_eq", "eq", 1),
        ("strict_neq", "ne", 0),
        ("eq", "eq", 1),
        ("neq", "ne", 0),
    ]:
        if name.startswith("strict_"):
            diff_code = [
                "    cmp w0, #3",
                f"    b.hi .Lcvm_{name}_diff_lrc",
                "    cmp w1, #3",
                f"    b.ls .Lcvm_{name}_diff_ne",
                "    cmn w1, #1",
                f"    b.eq .Lcvm_{name}_diff_dec_r",
                "    cmn w1, #7",
                "    b.ne .Lcvm_bail",
                f".Lcvm_{name}_diff_dec_r:",
                "    ldur x3, [x13, #-16]",
                *dec_rc_or_bail("x3"),
                f"    b .Lcvm_{name}_diff_ne",
                f".Lcvm_{name}_diff_lrc:",
                "    cmn w0, #1",
                f"    b.eq .Lcvm_{name}_diff_l_ok",
                "    cmn w0, #7",
                "    b.ne .Lcvm_bail",
                f".Lcvm_{name}_diff_l_ok:",
                "    cmp w1, #3",
                f"    b.ls .Lcvm_{name}_diff_dec_l",
                "    cmn w1, #1",
                f"    b.eq .Lcvm_{name}_diff_both_rc",
                "    cmn w1, #7",
                "    b.ne .Lcvm_bail",
                f".Lcvm_{name}_diff_both_rc:",
                "    ldur x2, [x13, #-32]",
                "    ldur x3, [x13, #-16]",
                "    ldur w16, [x2, #ARM_REF_COUNT_OFFSET]",
                "    cmp w16, #1",
                "    b.le .Lcvm_bail",
                "    ldur w17, [x3, #ARM_REF_COUNT_OFFSET]",
                "    cmp w17, #1",
                "    b.le .Lcvm_bail",
                "    sub w16, w16, #1",
                "    sub w17, w17, #1",
                "    stur w16, [x2, #ARM_REF_COUNT_OFFSET]",
                "    stur w17, [x3, #ARM_REF_COUNT_OFFSET]",
                f"    b .Lcvm_{name}_diff_ne",
                f".Lcvm_{name}_diff_dec_l:",
                "    ldur x2, [x13, #-32]",
                *dec_rc_or_bail("x2"),
                f".Lcvm_{name}_diff_ne:",
                f"    mov w0, #{1 - obj_eq_val}",
                "    sub x13, x13, #32",
                "    add x14, x14, #1",
                "    b .Lcvm_cmp_done",
            ]
        else:
            diff_code = ["    b .Lcvm_bail"]

        handlers[name] = [
            "    ldur w0, [x13, #-24]",
            "    ldur w1, [x13, #-8]",
            "    cmp w0, w1",
            f"    b.ne .Lcvm_{name}_diff",
            "    cmp w0, #3",
            f"    b.hi .Lcvm_{name}_chk_obj",
            "    ldur w2, [x13, #-32]",
            "    ldur w3, [x13, #-16]",
            "    cmp w2, w3",
            f"    cset w0, {cond}",
            "    sub x13, x13, #32",
            "    add x14, x14, #1",
            "    b .Lcvm_cmp_done",
            f".Lcvm_{name}_chk_obj:",
            "    cmn w0, #1",
            f"    b.ne .Lcvm_{name}_chk_str",
            "    ldur x2, [x13, #-32]",
            "    ldur x3, [x13, #-16]",
            "    cmp x2, x3",
            f"    b.eq .Lcvm_{name}_same_rc",
            "    ldur w16, [x2, #ARM_REF_COUNT_OFFSET]",
            "    cmp w16, #1",
            "    b.le .Lcvm_bail",
            "    ldur w17, [x3, #ARM_REF_COUNT_OFFSET]",
            "    cmp w17, #1",
            "    b.le .Lcvm_bail",
            "    sub w16, w16, #1",
            "    sub w17, w17, #1",
            "    stur w16, [x2, #ARM_REF_COUNT_OFFSET]",
            "    stur w17, [x3, #ARM_REF_COUNT_OFFSET]",
            f"    mov w0, #{1 - obj_eq_val}",
            "    sub x13, x13, #32",
            "    add x14, x14, #1",
            "    b .Lcvm_cmp_done",
            f".Lcvm_{name}_same_rc:",
            "    ldur w16, [x2, #ARM_REF_COUNT_OFFSET]",
            "    cmp w16, #2",
            "    b.le .Lcvm_bail",
            "    sub w16, w16, #2",
            "    stur w16, [x2, #ARM_REF_COUNT_OFFSET]",
            f"    mov w0, #{obj_eq_val}",
            "    sub x13, x13, #32",
            "    add x14, x14, #1",
            "    b .Lcvm_cmp_done",
            f".Lcvm_{name}_chk_str:",
            "    cmn w0, #7",
            "    b.ne .Lcvm_bail",
            "    ldur x2, [x13, #-32]",
            "    ldur x3, [x13, #-16]",
            "    cmp x2, x3",
            f"    b.eq .Lcvm_{name}_same_rc",
            "    ldur w16, [x2, #ARM_REF_COUNT_OFFSET]",
            "    cmp w16, #1",
            "    b.le .Lcvm_bail",
            "    ldur w17, [x3, #ARM_REF_COUNT_OFFSET]",
            "    cmp w17, #1",
            "    b.le .Lcvm_bail",
            "    ldr w0, [x2, #0]",
            "    ldr w1, [x3, #0]",
            "    and w4, w0, #0x7fffffff",
            "    and w5, w1, #0x7fffffff",
            "    cmp w4, w5",
            f"    b.ne .Lcvm_{name}_str_ne",
            "    orr w0, w0, w1",
            "    cmp w0, #0",
            "    b.lt .Lcvm_bail",
            "    ldrb w0, [x2, #7]",
            "    ldrb w1, [x3, #7]",
            "    orr w0, w0, w1",
            "    tst w0, #48",
            "    b.ne .Lcvm_bail",
            f"    cbz w4, .Lcvm_{name}_str_eq",
            "    cmp w4, #1",
            f"    b.eq .Lcvm_{name}_str_len1",
            "    cmp w4, #2",
            f"    b.eq .Lcvm_{name}_str_len2",
            "    cmp w4, #32",
            "    b.hi .Lcvm_bail",
            "    mov w16, w4",
            "    add x4, x2, #ARM_SIZE_JSString",
            "    add x5, x3, #ARM_SIZE_JSString",
            f".Lcvm_{name}_str_loop:",
            "    ldrb w0, [x4], #1",
            "    ldrb w1, [x5], #1",
            "    cmp w0, w1",
            f"    b.ne .Lcvm_{name}_str_ne",
            "    subs w16, w16, #1",
            f"    b.ne .Lcvm_{name}_str_loop",
            f"    b .Lcvm_{name}_str_eq",
            f".Lcvm_{name}_str_len1:",
            "    ldrb w0, [x2, #ARM_SIZE_JSString]",
            "    ldrb w1, [x3, #ARM_SIZE_JSString]",
            "    cmp w0, w1",
            f"    b.eq .Lcvm_{name}_str_eq",
            f"    b .Lcvm_{name}_str_ne",
            f".Lcvm_{name}_str_len2:",
            "    ldrh w0, [x2, #ARM_SIZE_JSString]",
            "    ldrh w1, [x3, #ARM_SIZE_JSString]",
            "    cmp w0, w1",
            f"    b.eq .Lcvm_{name}_str_eq",
            f".Lcvm_{name}_str_ne:",
            "    ldur w16, [x2, #ARM_REF_COUNT_OFFSET]",
            "    ldur w17, [x3, #ARM_REF_COUNT_OFFSET]",
            "    sub w16, w16, #1",
            "    sub w17, w17, #1",
            "    stur w16, [x2, #ARM_REF_COUNT_OFFSET]",
            "    stur w17, [x3, #ARM_REF_COUNT_OFFSET]",
            f"    mov w0, #{1 - obj_eq_val}",
            "    sub x13, x13, #32",
            "    add x14, x14, #1",
            "    b .Lcvm_cmp_done",
            f".Lcvm_{name}_str_eq:",
            "    ldur w16, [x2, #ARM_REF_COUNT_OFFSET]",
            "    ldur w17, [x3, #ARM_REF_COUNT_OFFSET]",
            "    sub w16, w16, #1",
            "    sub w17, w17, #1",
            "    stur w16, [x2, #ARM_REF_COUNT_OFFSET]",
            "    stur w17, [x3, #ARM_REF_COUNT_OFFSET]",
            f"    mov w0, #{obj_eq_val}",
            "    sub x13, x13, #32",
            "    add x14, x14, #1",
            "    b .Lcvm_cmp_done",
            f".Lcvm_{name}_diff:",
            *diff_code,
        ]

    # --- branches & gotos (with exact interrupt_counter polling) ---
    for name, load_delta in [
        ("goto8", "    ldrsb x1, [x14, #1]"),
        ("goto16", "    ldursh x1, [x14, #1]"),
        ("goto", "    ldursw x1, [x14, #1]"),
    ]:
        handlers[name] = [
            "    ldr w2, [x9, #ARM_OFF_JSContext_interrupt_counter]",
            "    cmp w2, #1",
            "    b.le .Lcvm_bail",
            "    sub w2, w2, #1",
            "    str w2, [x9, #ARM_OFF_JSContext_interrupt_counter]",
            load_delta,
            "    add x1, x1, #1",
            "    add x14, x14, x1",
            *disp(0),
        ]

    for name, load_delta, fall_adv, jump_on_nz in [
        ("if_false8", "    ldrsb x1, [x14, #1]", 2, False),
        ("if_true8", "    ldrsb x1, [x14, #1]", 2, True),
        ("if_false", "    ldursw x1, [x14, #1]", 5, False),
        ("if_true", "    ldursw x1, [x14, #1]", 5, True),
    ]:
        b_take = "cbnz" if jump_on_nz else "cbz"
        handlers[name] = [
            "    ldr w2, [x9, #ARM_OFF_JSContext_interrupt_counter]",
            "    cmp w2, #1",
            "    b.le .Lcvm_bail",
            "    ldur w0, [x13, #-8]",
            "    cmp w0, #3",
            f"    b.ls .Lcvm_{name}_prim",
            "    cmn w0, #1",
            f"    b.eq .Lcvm_{name}_obj",
            "    cmn w0, #7",
            "    b.ne .Lcvm_bail",
            "    ldur x3, [x13, #-16]",
            "    ldur w17, [x3, #ARM_REF_COUNT_OFFSET]",
            "    cmp w17, #1",
            "    b.le .Lcvm_bail",
            "    ldr w0, [x3, #0]",
            "    and w0, w0, #0x7fffffff",
            "    sub w17, w17, #1",
            "    stur w17, [x3, #ARM_REF_COUNT_OFFSET]",
            "    sub w2, w2, #1",
            "    str w2, [x9, #ARM_OFF_JSContext_interrupt_counter]",
            "    sub x13, x13, #16",
            f"    {b_take} w0, .Lcvm_{name}_take",
            *disp(fall_adv),
            f".Lcvm_{name}_obj:",
            "    ldur x3, [x13, #-16]",
            "    ldrb w4, [x3, #ARM_BIT_JSObject_is_HTMLDDA_BYTE]",
            "    tst w4, #ARM_BIT_JSObject_is_HTMLDDA_MASK",
            "    b.ne .Lcvm_bail",
            "    ldur w17, [x3, #ARM_REF_COUNT_OFFSET]",
            "    cmp w17, #1",
            "    b.le .Lcvm_bail",
            "    sub w17, w17, #1",
            "    stur w17, [x3, #ARM_REF_COUNT_OFFSET]",
            "    sub w2, w2, #1",
            "    str w2, [x9, #ARM_OFF_JSContext_interrupt_counter]",
            "    sub x13, x13, #16",
            *(
                [load_delta, "    add x1, x1, #1", "    add x14, x14, x1", *disp(0)]
                if jump_on_nz
                else disp(fall_adv)
            ),
            f".Lcvm_{name}_prim:",
            "    sub w2, w2, #1",
            "    str w2, [x9, #ARM_OFF_JSContext_interrupt_counter]",
            "    ldur w0, [x13, #-16]",
            "    sub x13, x13, #16",
            f"    {b_take} w0, .Lcvm_{name}_take",
            *disp(fall_adv),
            f".Lcvm_{name}_take:",
            load_delta,
            "    add x1, x1, #1",
            "    add x14, x14, x1",
            *disp(0),
        ]

    # --- fast length (Array & String) ---
    handlers["get_length"] = [
        "    ldur w0, [x13, #-8]",
        "    cmn w0, #1",
        "    b.eq .Lcvm_glen_obj",
        "    cmn w0, #7",
        "    b.ne .Lcvm_bail",
        "    ldur x2, [x13, #-16]",
        "    ldur w17, [x2, #ARM_REF_COUNT_OFFSET]",
        "    cmp w17, #1",
        "    b.le .Lcvm_bail",
        "    ldr w0, [x2, #0]",
        "    and w0, w0, #0x7fffffff",
        "    sub w17, w17, #1",
        "    stur w17, [x2, #ARM_REF_COUNT_OFFSET]",
        "    stp x0, xzr, [x13, #-16]",
        *disp(1),
        ".Lcvm_glen_obj:",
        "    ldur x2, [x13, #-16]",
        "    ldur w17, [x2, #ARM_REF_COUNT_OFFSET]",
        "    cmp w17, #1",
        "    b.le .Lcvm_bail",
        "    ldrh w0, [x2, #ARM_OFF_JSObject_class_id]",
        "    cmp w0, #ARM_CONST_JS_CLASS_ARRAY",
        "    b.ne .Lcvm_bail",
        "    ldrb w0, [x2, #ARM_BIT_JSObject_fast_array_BYTE]",
        "    tst w0, #ARM_BIT_JSObject_fast_array_MASK",
        "    b.eq .Lcvm_bail",
        "    ldr x3, [x2, #ARM_OFF_JSObject_prop]",
        "    cbz x3, .Lcvm_bail",
        "    ldp x0, x1, [x3]",
        "    cmp w1, #0",
        "    b.lt .Lcvm_bail",
        "    sub w17, w17, #1",
        "    stur w17, [x2, #ARM_REF_COUNT_OFFSET]",
        "    stp x0, x1, [x13, #-16]",
        *disp(1),
    ]

    # --- fast dense Array, TypedArray (Uint8/Int8/Int32/Uint32), & fused str[i] === "x" ---
    handlers["get_array_el"] = [
        "    ldur w0, [x13, #-8]",
        "    cbnz w0, .Lcvm_bail",
        "    ldur w0, [x13, #-24]",
        "    cmn w0, #1",
        "    b.ne .Lcvm_gael_chk_str",
        "    ldur x2, [x13, #-32]",
        "    ldrh w0, [x2, #ARM_OFF_JSObject_class_id]",
        "    cmp w0, #ARM_CONST_JS_CLASS_ARRAY",
        "    b.ne .Lcvm_gael_typed",
        "    ldrb w0, [x2, #ARM_BIT_JSObject_fast_array_BYTE]",
        "    tst w0, #ARM_BIT_JSObject_fast_array_MASK",
        "    b.eq .Lcvm_bail",
        "    ldur w1, [x13, #-16]",
        "    ldr w3, [x2, #ARM_OFF_JSObject_u_array_count]",
        "    cmp w1, w3",
        "    b.hs .Lcvm_bail",
        "    ldur w17, [x2, #ARM_REF_COUNT_OFFSET]",
        "    cmp w17, #1",
        "    b.le .Lcvm_bail",
        "    ldr x3, [x2, #ARM_OFF_JSObject_u_array_u_values]",
        "    add x3, x3, w1, uxtw #4",
        "    ldp x4, x5, [x3]",
        "    stp x4, x5, [x13, #-32]",
        "    sub x13, x13, #16",
        *dup_if_rc("x4", "w5", ".Lcvm_gael_dup"),
        "    ldur w17, [x2, #ARM_REF_COUNT_OFFSET]",
        "    sub w17, w17, #1",
        "    stur w17, [x2, #ARM_REF_COUNT_OFFSET]",
        *disp(1),
        ".Lcvm_gael_typed:",
        "    ldur w1, [x13, #-16]",
        "    ldr w3, [x2, #ARM_OFF_JSObject_u_array_count]",
        "    cmp w1, w3",
        "    b.hs .Lcvm_bail",
        "    ldur w17, [x2, #ARM_REF_COUNT_OFFSET]",
        "    cmp w17, #1",
        "    b.le .Lcvm_bail",
        "    ldr x3, [x2, #ARM_OFF_JSObject_u_array_u_values]",
        "    cmp w0, #ARM_CONST_JS_CLASS_UINT8_ARRAY",
        "    b.eq .Lcvm_gael_u8",
        "    cmp w0, #ARM_CONST_JS_CLASS_UINT8C_ARRAY",
        "    b.eq .Lcvm_gael_u8",
        "    cmp w0, #ARM_CONST_JS_CLASS_INT8_ARRAY",
        "    b.eq .Lcvm_gael_i8",
        "    cmp w0, #ARM_CONST_JS_CLASS_INT32_ARRAY",
        "    b.eq .Lcvm_gael_i32",
        "    cmp w0, #ARM_CONST_JS_CLASS_UINT32_ARRAY",
        "    b.ne .Lcvm_bail",
        "    ldr w4, [x3, w1, uxtw #2]",
        "    cmp w4, #0",
        "    b.lt .Lcvm_bail",
        "    b .Lcvm_gael_tcommit",
        ".Lcvm_gael_i32:",
        "    ldrsw x4, [x3, w1, uxtw #2]",
        "    b .Lcvm_gael_tcommit",
        ".Lcvm_gael_i8:",
        "    ldrsb x4, [x3, w1, uxtw]",
        "    b .Lcvm_gael_tcommit",
        ".Lcvm_gael_u8:",
        "    ldrb w4, [x3, w1, uxtw]",
        ".Lcvm_gael_tcommit:",
        "    sub w17, w17, #1",
        "    stur w17, [x2, #ARM_REF_COUNT_OFFSET]",
        "    stp x4, xzr, [x13, #-32]",
        "    sub x13, x13, #16",
        *disp(1),
        ".Lcvm_gael_chk_str:",
        "    cmn w0, #7",
        "    b.ne .Lcvm_bail",
        "    ldrb w0, [x14, #1]",
        f"    cmp w0, #{op_push_atom_value}",
        "    b.ne .Lcvm_bail",
        "    ldrb w17, [x14, #6]",
        f"    cmp w17, #{op_strict_eq}",
        "    b.eq .Lcvm_gael_str_cmp",
        f"    cmp w17, #{op_strict_neq}",
        "    b.ne .Lcvm_bail",
        ".Lcvm_gael_str_cmp:",
        "    ldur x2, [x13, #-32]",
        "    ldur w16, [x2, #ARM_REF_COUNT_OFFSET]",
        "    cmp w16, #1",
        "    b.le .Lcvm_bail",
        "    ldr w0, [x2, #0]",
        "    cmp w0, #0",
        "    b.lt .Lcvm_bail",
        "    ldrb w1, [x2, #7]",
        "    tst w1, #48",
        "    b.ne .Lcvm_bail",
        "    ldur w4, [x13, #-16]",
        "    cmp w4, w0",
        "    b.hs .Lcvm_bail",
        "    ldur w5, [x14, #2]",
        "    cmp w5, #0",
        "    b.lt .Lcvm_bail",
        "    ldr x3, [x7, #ARM_OFF_JSRuntime_atom_array]",
        "    ldr x3, [x3, w5, uxtw #3]",
        "    ldrb w0, [x3, #7]",
        "    lsr w0, w0, #6",
        "    cmp w0, #1",
        "    b.ne .Lcvm_bail",
        "    ldr w0, [x3, #0]",
        "    cmp w0, #0",
        "    b.lt .Lcvm_bail",
        "    ldrb w1, [x3, #7]",
        "    tst w1, #48",
        "    b.ne .Lcvm_bail",
        "    mov w5, #0",
        "    cmp w0, #1",
        "    b.ne .Lcvm_gael_str_res",
        "    add x4, x2, w4, uxtw",
        "    ldrb w0, [x4, #ARM_SIZE_JSString]",
        "    ldrb w1, [x3, #ARM_SIZE_JSString]",
        "    cmp w0, w1",
        "    cset w5, eq",
        ".Lcvm_gael_str_res:",
        f"    cmp w17, #{op_strict_neq}",
        "    b.ne .Lcvm_gael_str_done",
        "    eor w5, w5, #1",
        ".Lcvm_gael_str_done:",
        "    sub w16, w16, #1",
        "    stur w16, [x2, #ARM_REF_COUNT_OFFSET]",
        "    mov w0, w5",
        "    sub x13, x13, #32",
        "    add x14, x14, #7",
        "    b .Lcvm_cmp_done",
    ]

    # --- fast dense Array and Uint8/Int8/Int32/Uint32 TypedArray element store ---
    handlers["put_array_el"] = [
        "    ldur w0, [x13, #-24]",
        "    cbnz w0, .Lcvm_bail",
        "    ldur w0, [x13, #-40]",
        "    cmn w0, #1",
        "    b.ne .Lcvm_bail",
        "    ldur x2, [x13, #-48]",
        "    ldur w16, [x2, #ARM_REF_COUNT_OFFSET]",
        "    cmp w16, #1",
        "    b.le .Lcvm_bail",
        "    ldrh w0, [x2, #ARM_OFF_JSObject_class_id]",
        "    cmp w0, #ARM_CONST_JS_CLASS_ARRAY",
        "    b.ne .Lcvm_pael_typed",
        "    ldrb w0, [x2, #ARM_BIT_JSObject_fast_array_BYTE]",
        "    tst w0, #ARM_BIT_JSObject_fast_array_MASK",
        "    b.eq .Lcvm_bail",
        "    ldur w1, [x13, #-32]",
        "    ldr w3, [x2, #ARM_OFF_JSObject_u_array_count]",
        "    cmp w1, w3",
        "    b.hs .Lcvm_bail",
        "    ldr x5, [x2, #ARM_OFF_JSObject_u_array_u_values]",
        "    add x5, x5, w1, uxtw #4",
        "    ldr w0, [x5, #8]",
        "    tbz w0, #31, .Lcvm_pael_arr_wr",
        "    ldr x4, [x5, #0]",
        "    cmp x4, x2",
        "    b.eq .Lcvm_bail",
        *dec_rc_or_bail("x4", "w17"),
        ".Lcvm_pael_arr_wr:",
        "    ldp x0, x1, [x13, #-16]",
        "    stp x0, x1, [x5]",
        "    sub w16, w16, #1",
        "    stur w16, [x2, #ARM_REF_COUNT_OFFSET]",
        "    sub x13, x13, #48",
        *disp(1),
        ".Lcvm_pael_typed:",
        "    ldur w1, [x13, #-8]",
        "    cbnz w1, .Lcvm_bail",
        "    ldur w1, [x13, #-32]",
        "    ldr w3, [x2, #ARM_OFF_JSObject_u_array_count]",
        "    cmp w1, w3",
        "    b.hs .Lcvm_bail",
        "    ldr x4, [x2, #ARM_OFF_JSObject_u_typed_array]",
        "    ldr x4, [x4, #ARM_OFF_JSTypedArray_buffer]",
        "    ldr x4, [x4, #ARM_OFF_JSObject_u_array_buffer]",
        "    ldrb w3, [x4, #ARM_OFF_JSArrayBuffer_immutable]",
        "    cbnz w3, .Lcvm_bail",
        "    ldr x5, [x2, #ARM_OFF_JSObject_u_array_u_values]",
        "    ldur w3, [x13, #-16]",
        "    cmp w0, #ARM_CONST_JS_CLASS_UINT8_ARRAY",
        "    b.eq .Lcvm_pael_t8",
        "    cmp w0, #ARM_CONST_JS_CLASS_INT8_ARRAY",
        "    b.eq .Lcvm_pael_t8",
        "    cmp w0, #ARM_CONST_JS_CLASS_INT32_ARRAY",
        "    b.eq .Lcvm_pael_t32",
        "    cmp w0, #ARM_CONST_JS_CLASS_UINT32_ARRAY",
        "    b.ne .Lcvm_bail",
        ".Lcvm_pael_t32:",
        "    str w3, [x5, w1, uxtw #2]",
        "    sub w16, w16, #1",
        "    stur w16, [x2, #ARM_REF_COUNT_OFFSET]",
        "    sub x13, x13, #48",
        *disp(1),
        ".Lcvm_pael_t8:",
        "    strb w3, [x5, w1, uxtw]",
        "    sub w16, w16, #1",
        "    stur w16, [x2, #ARM_REF_COUNT_OFFSET]",
        "    sub x13, x13, #48",
        *disp(1),
    ]

    # --- Property IC fast paths (get_field, get_field2, put_field) ---
    if property_ic:
        for fname, is_gf2 in [("get_field", False), ("get_field2", True)]:
            p = f"cvm_{fname}"
            g = [
                "#if ARM_HAS_PROPERTY_IC",
                "    ldur w0, [x13, #-8]",
                "    cmn w0, #1",
                "    b.ne .Lcvm_bail",
                "    ldur x2, [x13, #-16]",
            ]
            if not is_gf2:
                g += [
                    "    ldur w16, [x2, #ARM_REF_COUNT_OFFSET]",
                    "    cmp w16, #1",
                    "    b.le .Lcvm_bail",
                ]
            g += [
                "    ldrb w0, [x2, #ARM_BIT_JSObject_is_exotic_BYTE]",
                "    tst w0, #ARM_BIT_JSObject_is_exotic_MASK",
                "    b.ne .Lcvm_bail",
                "    ldr w0, [x7, #ARM_OFF_JSRuntime_property_ic_mode]",
                "    cmp w0, #1",
                "    b.ne .Lcvm_bail",
                "    ldr x3, [x8, #ARM_OFF_JSFunctionBytecode_property_ic]",
                "    cmp x3, #4095",
                "    b.ls .Lcvm_bail",
                "    ldr x1, [x8, #ARM_OFF_JSFunctionBytecode_byte_code_buf]",
                "    sub x1, x14, x1",
                "    lsr x1, x1, #2",
                "    ldr w4, [x3, #8]",
                "    cmp w1, w4",
                "    b.hs .Lcvm_bail",
                "    add x3, x3, #ARM_OFF_JSPropertyIC_map",
                "    ldr x3, [x3, w1, uxtw #3]",
                "    cbz x3, .Lcvm_bail",
                "    ldrb w4, [x3, #ARM_OFF_JSPropertyICSite_megamorphic]",
                "    cbnz w4, .Lcvm_bail",
                "    ldr x4, [x2, #ARM_OFF_JSObject_shape]",
                "    ldr x5, [x3, #ARM_OFF_JSPropertyICWay_shape]",
                "    cmp x5, x4",
                f"    b.eq .L{p}_hit",
                "    ldrb w1, [x3, #52]",
                "    cmp w1, #1",
                "    b.ls .Lcvm_bail",
                "    ldr x3, [x3, #ARM_OFF_JSPropertyICSite_secondary]",
                "    cbz x3, .Lcvm_bail",
                "    ldr x5, [x3, #ARM_OFF_JSPropertyICWay_shape]",
                "    cmp x5, x4",
                f"    b.eq .L{p}_hit",
                "    cmp w1, #2",
                "    b.ls .Lcvm_bail",
                "    add x3, x3, #ARM_SIZE_JSPropertyICWay",
                "    ldr x5, [x3, #ARM_OFF_JSPropertyICWay_shape]",
                "    cmp x5, x4",
                f"    b.eq .L{p}_hit",
                "    cmp w1, #3",
                "    b.ls .Lcvm_bail",
                "    add x3, x3, #ARM_SIZE_JSPropertyICWay",
                "    ldr x5, [x3, #ARM_OFF_JSPropertyICWay_shape]",
                "    cmp x5, x4",
                "    b.ne .Lcvm_bail",
                f".L{p}_hit:",
                "    ldr w0, [x3, #ARM_OFF_JSPropertyICWay_kind]",
                "    cmp w0, #1",
                f"    b.ne .L{p}_non_own",
                "    ldr w1, [x3, #ARM_OFF_JSPropertyICWay_slot]",
                "    ldr x5, [x2, #ARM_OFF_JSObject_prop]",
                f".L{p}_load:",
                "    add x5, x5, w1, uxtw #4",
                "    ldp x4, x5, [x5]",
                "    cmp w5, #4",
                "    b.eq .Lcvm_bail",
                *dup_if_rc("x4", "w5", f".L{p}_dup"),
            ]
            if is_gf2:
                g += [
                    "    stp x4, x5, [x13], #16",
                    *disp(5),
                ]
            else:
                g += [
                    "    ldur w17, [x2, #ARM_REF_COUNT_OFFSET]",
                    "    sub w17, w17, #1",
                    "    stur w17, [x2, #ARM_REF_COUNT_OFFSET]",
                    "    stp x4, x5, [x13, #-16]",
                    *disp(5),
                ]
            g += [
                f".L{p}_non_own:",
                "    ldr x1, [x7, #ARM_OFF_JSRuntime_property_ic_epoch]",
                "    cbz x1, .Lcvm_bail",
                "    ldr x4, [x3, #ARM_OFF_JSPropertyICWay_epoch]",
                "    cmp x4, x1",
                "    b.ne .Lcvm_bail",
                "    cmp w0, #2",
                f"    b.ne .L{p}_chk_unset",
                "    ldr x5, [x3, #ARM_OFF_JSPropertyICWay_holder]",
                "    ldr x5, [x5, #ARM_OFF_JSObject_prop]",
                "    ldr w1, [x3, #ARM_OFF_JSPropertyICWay_slot]",
                f"    b .L{p}_load",
                f".L{p}_chk_unset:",
                "    cmp w0, #3",
                f"    b.ne .L{p}_chk_getter",
                "    mov x4, #0",
                "    mov x5, #3",
                f"    b .L{p}_store_prim",
                f".L{p}_chk_getter:",
                "    ldr w17, [x9, #ARM_OFF_JSContext_interrupt_counter]",
                "    cmp w17, #2",
                "    b.le .Lcvm_bail",
                "    cmp w0, #7",
                f"    b.ne .L{p}_chk_gbool",
                "    ldr w1, [x3, #ARM_OFF_JSPropertyICWay_slot]",
                "    ldr x5, [x2, #ARM_OFF_JSObject_prop]",
                "    add x5, x5, w1, uxtw #4",
                "    ldp x4, x5, [x5]",
                "    cmp w5, #4",
                "    b.eq .Lcvm_bail",
                "    sub w17, w17, #1",
                "    str w17, [x9, #ARM_OFF_JSContext_interrupt_counter]",
                *dup_if_rc("x4", "w5", f".L{p}_gf_dup"),
                f"    b .L{p}_store_prim",
                f".L{p}_chk_gbool:",
                "    cmp w0, #8",
                "    b.ne .Lcvm_bail",
                "    sub w17, w17, #1",
                "    str w17, [x9, #ARM_OFF_JSContext_interrupt_counter]",
                "    ldr w4, [x3, #ARM_OFF_JSPropertyICWay_slot]",
                "    mov x5, #1",
                f".L{p}_store_prim:",
            ]
            if is_gf2:
                g += [
                    "    stp x4, x5, [x13], #16",
                    *disp(5),
                ]
            else:
                g += [
                    "    ldur w17, [x2, #ARM_REF_COUNT_OFFSET]",
                    "    sub w17, w17, #1",
                    "    stur w17, [x2, #ARM_REF_COUNT_OFFSET]",
                    "    stp x4, x5, [x13, #-16]",
                    *disp(5),
                ]
            g += [
                "#else",
                "    b .Lcvm_bail",
                "#endif",
            ]
            handlers[fname] = g

        # put_field (JS_IC_REPLACE = 4)
        handlers["put_field"] = [
            "#if ARM_HAS_PROPERTY_IC",
            "    ldur w0, [x13, #-24]",
            "    cmn w0, #1",
            "    b.ne .Lcvm_bail",
            "    ldur x2, [x13, #-32]",
            "    ldur w16, [x2, #ARM_REF_COUNT_OFFSET]",
            "    cmp w16, #1",
            "    b.le .Lcvm_bail",
            "    ldrb w0, [x2, #ARM_BIT_JSObject_is_exotic_BYTE]",
            "    tst w0, #ARM_BIT_JSObject_is_exotic_MASK",
            "    b.ne .Lcvm_bail",
            "    ldr w0, [x7, #ARM_OFF_JSRuntime_property_ic_mode]",
            "    cmp w0, #1",
            "    b.ne .Lcvm_bail",
            "    ldr x3, [x8, #ARM_OFF_JSFunctionBytecode_property_ic]",
            "    cmp x3, #4095",
            "    b.ls .Lcvm_bail",
            "    ldr x1, [x8, #ARM_OFF_JSFunctionBytecode_byte_code_buf]",
            "    sub x1, x14, x1",
            "    lsr x1, x1, #2",
            "    ldr w4, [x3, #8]",
            "    cmp w1, w4",
            "    b.hs .Lcvm_bail",
            "    add x3, x3, #ARM_OFF_JSPropertyIC_map",
            "    ldr x3, [x3, w1, uxtw #3]",
            "    cbz x3, .Lcvm_bail",
            "    ldrb w4, [x3, #ARM_OFF_JSPropertyICSite_megamorphic]",
            "    cbnz w4, .Lcvm_bail",
            "    ldr x4, [x2, #ARM_OFF_JSObject_shape]",
            "    ldr x5, [x3, #ARM_OFF_JSPropertyICWay_shape]",
            "    cmp x5, x4",
            "    b.eq .Lcvm_pf_hit",
            "    ldrb w1, [x3, #52]",
            "    cmp w1, #1",
            "    b.ls .Lcvm_bail",
            "    ldr x3, [x3, #ARM_OFF_JSPropertyICSite_secondary]",
            "    cbz x3, .Lcvm_bail",
            "    ldr x5, [x3, #ARM_OFF_JSPropertyICWay_shape]",
            "    cmp x5, x4",
            "    b.eq .Lcvm_pf_hit",
            "    cmp w1, #2",
            "    b.ls .Lcvm_bail",
            "    add x3, x3, #ARM_SIZE_JSPropertyICWay",
            "    ldr x5, [x3, #ARM_OFF_JSPropertyICWay_shape]",
            "    cmp x5, x4",
            "    b.eq .Lcvm_pf_hit",
            "    cmp w1, #3",
            "    b.ls .Lcvm_bail",
            "    add x3, x3, #ARM_SIZE_JSPropertyICWay",
            "    ldr x5, [x3, #ARM_OFF_JSPropertyICWay_shape]",
            "    cmp x5, x4",
            "    b.ne .Lcvm_bail",
            ".Lcvm_pf_hit:",
            "    ldr w0, [x3, #ARM_OFF_JSPropertyICWay_kind]",
            "    cmp w0, #4",
            "    b.ne .Lcvm_bail",
            "    ldr w1, [x3, #ARM_OFF_JSPropertyICWay_slot]",
            "    ldr x5, [x2, #ARM_OFF_JSObject_prop]",
            "    add x5, x5, w1, uxtw #4",
            "    ldr w0, [x5, #8]",
            "    tbz w0, #31, .Lcvm_pf_wr",
            "    ldr x4, [x5, #0]",
            "    cmp x4, x2",
            "    b.eq .Lcvm_bail",
            *dec_rc_or_bail("x4", "w17"),
            ".Lcvm_pf_wr:",
            "    ldp x0, x1, [x13, #-16]",
            "    stp x0, x1, [x5]",
            "    sub w16, w16, #1",
            "    stur w16, [x2, #ARM_REF_COUNT_OFFSET]",
            "    sub x13, x13, #32",
            *disp(5),
            "#else",
            "    b .Lcvm_bail",
            "#endif",
        ]

    # Shared compare + branch fusion tail (w0 = 0/1, x13 points at result slot, x14 points at next op).
    shared_tails = [
        ".Lcvm_cmp_done:",
        "    ldrb w1, [x14]",
        f"    cmp w1, #{op_if_false8}",
        "    b.eq .Lcvm_cmp_if_false8",
        f"    cmp w1, #{op_if_true8}",
        "    b.eq .Lcvm_cmp_if_true8",
        "    mov x2, #1",
        "    stp x0, x2, [x13], #16",
        "    ldr x3, [x6, x1, lsl #3]",
        "    br x3",
        ".Lcvm_cmp_if_false8:",
        "    ldr w2, [x9, #ARM_OFF_JSContext_interrupt_counter]",
        "    cmp w2, #1",
        "    b.le .Lcvm_cmp_store_bail",
        "    sub w2, w2, #1",
        "    str w2, [x9, #ARM_OFF_JSContext_interrupt_counter]",
        "    cbz w0, .Lcvm_cmp_take8",
        "    ldrb w0, [x14, #2]!",
        "    ldr x1, [x6, x0, lsl #3]",
        "    br x1",
        ".Lcvm_cmp_if_true8:",
        "    ldr w2, [x9, #ARM_OFF_JSContext_interrupt_counter]",
        "    cmp w2, #1",
        "    b.le .Lcvm_cmp_store_bail",
        "    sub w2, w2, #1",
        "    str w2, [x9, #ARM_OFF_JSContext_interrupt_counter]",
        "    cbnz w0, .Lcvm_cmp_take8",
        "    ldrb w0, [x14, #2]!",
        "    ldr x1, [x6, x0, lsl #3]",
        "    br x1",
        ".Lcvm_cmp_take8:",
        "    ldrsb x1, [x14, #1]",
        "    add x1, x1, #1",
        "    add x14, x14, x1",
        "    ldrb w0, [x14]",
        "    ldr x1, [x6, x0, lsl #3]",
        "    br x1",
        ".Lcvm_cmp_store_bail:",
        "    mov x2, #1",
        "    stp x0, x2, [x13], #16",
        "    b .Lcvm_bail",
    ]

    op_set = set(ops)
    return {k: v for k, v in handlers.items() if k in op_set}, shared_tails


def _eligible_rows(
    ops: list[str], op_sizes: dict[str, int], handlers: dict[str, list[str]]
) -> list[str]:
    uncond_jumps = {"goto", "goto8", "goto16"}
    flags = [
        (255 if ops[i] in uncond_jumps else op_sizes[ops[i]])
        if i < len(ops) and ops[i] in handlers
        else 0
        for i in range(256)
    ]
    return [".byte " + ", ".join(str(x) for x in flags[i : i + 16]) for i in range(0, 256, 16)]


def emit_arm64_cvm_fast(source: Path, property_ic: bool) -> str:
    """Return AArch64 ELF GAS assembly for JS_CVMRunFastSegment and JS_CVMFastEligible."""
    ops, op_sizes = _load_opcodes(source)
    handlers, shared_tails = _build_handlers(ops, property_ic)

    lines = [
        '.section .text.qjs_cvm_fast,"ax",%progbits',
        ".p2align 4",
        ".hidden JS_CVMRunFastSegment",
        ".globl JS_CVMRunFastSegment",
        ".type JS_CVMRunFastSegment, %function",
        "JS_CVMRunFastSegment:",
        "    .cfi_startproc",
        "    mov x15, x0",
        "    ldp x14, x13, [x15, #0]",
        "    ldp x12, x11, [x15, #16]",
        "    ldp x10, x9, [x15, #32]",
        "    ldp x8, x7, [x15, #48]",
        "    adrp x6, .Lcvm_fast_table",
        "    add x6, x6, :lo12:.Lcvm_fast_table",
        "    ldrb w0, [x14]",
        "    ldr x1, [x6, x0, lsl #3]",
        "    br x1",
    ]
    for name in sorted(handlers):
        lines.append(f".Lcvm_op_{name}:")
        lines.extend(handlers[name])
    lines.extend(shared_tails)
    lines += [
        ".Lcvm_bail:",
        "    stp x14, x13, [x15, #0]",
        "    ret",
        "    .cfi_endproc",
        ".size JS_CVMRunFastSegment, .-JS_CVMRunFastSegment",
        '.section .data.rel.ro.local.qjs_cvm_fast,"aw",%progbits',
        ".p2align 3",
        ".Lcvm_fast_table:",
    ]
    for i in range(256):
        target = f".Lcvm_op_{ops[i]}" if i < len(ops) and ops[i] in handlers else ".Lcvm_bail"
        lines.append(f"    .quad {target}")
    lines += [
        '.section .rodata.qjs_cvm_fast,"a",%progbits',
        ".p2align 4",
        ".hidden JS_CVMFastEligible",
        ".globl JS_CVMFastEligible",
        ".type JS_CVMFastEligible, %object",
        "JS_CVMFastEligible:",
        *_eligible_rows(ops, op_sizes, handlers),
        ".size JS_CVMFastEligible, 256",
    ]
    return "\n".join(lines) + "\n"
