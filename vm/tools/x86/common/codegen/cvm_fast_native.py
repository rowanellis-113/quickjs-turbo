"""Native x86-64 / Win64 coroutine fast-segment executor (JS_CVMRunFastSegment).

Executes contiguous zero-call, zero-allocation coroutine bytecode segments directly
over JSAsyncFunctionState's live frame (pc, sp, locals, args, var_refs, ctx, bc, rt)
using explicit jump-table dispatch on MSVC MASM, MinGW GAS, and Linux ELF GAS.

Any guard miss (type mismatch, rc == 1 release, interrupt_counter <= 1, IC miss,
call/yield/await) restores nothing-mutated state and returns pc/sp cleanly to the
retained C coroutine loop.
"""

from __future__ import annotations

import re
from pathlib import Path


def _load_opcodes(source_root: Path) -> list[str]:
    text = (source_root.parent / "quickjs-opcode.h").read_text(encoding="utf-8")
    ops = re.findall(r"^\s*DEF\(\s*(\w+)\s*,", text, re.M)
    if len(ops) < 200:
        raise ValueError(f"Unexpected opcode count: {len(ops)}")
    return ops


def _build_handlers(abi: dict, ops: list[str], property_ic: bool) -> dict[str, list[str]]:
    from abi_layout import constants as abi_constants

    fields = abi["offsets"]
    rc = abi_constants(abi)["QJS_ABI_REF_COUNT_OFFSET"]
    off_ic_ctr = fields["JSContext.interrupt_counter"]
    off_vr_pvalue = fields["JSVarRef.pvalue"]
    off_bc_buf = fields["JSFunctionBytecode.byte_code_buf"]
    off_bc_cpool = fields["JSFunctionBytecode.cpool"]
    off_bc_ic = fields.get("JSFunctionBytecode.property_ic", abi["sizes"]["JSFunctionBytecode"])
    off_rt_epoch = fields.get("JSRuntime.property_ic_epoch", abi["sizes"]["JSRuntime"])
    off_rt_ic_mode = off_rt_epoch + 8
    off_obj_cid = fields["JSObject.class_id"]
    off_obj_shape = fields["JSObject.shape"]
    off_obj_prop = fields["JSObject.prop"]
    off_arr_vals = fields["JSObject.u.array.u.values"]
    off_arr_count = fields["JSObject.u.array.count"]
    exotic_byte, exotic_mask = abi["bits"]["JSObject.is_exotic"][0]
    fast_arr_byte, fast_arr_mask = abi["bits"]["JSObject.fast_array"][0]
    htmldda_byte, htmldda_mask = abi["bits"]["JSObject.is_HTMLDDA"][0]

    # Register convention (identical for Win64 and Linux SysV inside body):
    #   r15 = JSCVMFastState *state
    #         [r15+0]  pc          [r15+8]  sp
    #         [r15+16] locals      [r15+24] args
    #         [r15+32] refs        [r15+40] ctx
    #         [r15+48] bc          [r15+56] rt
    #   r12 = pc
    #   r13 = sp
    #   r14 = locals (var_buf)
    #   rbp = args   (arg_buf)
    #   rbx = ctx    (b->realm)
    #   rdi = rt     (ctx->rt)
    #   rsi = &cvm_fast_table[0]
    #   scratch = rax, rcx, rdx, r8, r9, r10, r11

    def disp(adv: int = 0) -> list[str]:
        out = []
        if adv == 1:
            out.append("inc r12")
        elif adv > 1:
            out.append(f"add r12, {adv}")
        out += [
            "movzx eax, BYTE PTR [r12]",
            "jmp QWORD PTR [rsi + rax*8]",
        ]
        return out

    def dup_if_rc(ptr_reg: str, tag_reg: str, lbl: str) -> list[str]:
        return [
            f"test {tag_reg}, {tag_reg}",
            f"jns {lbl}",
            f"inc DWORD PTR [{ptr_reg}{rc:+d}]",
            f"{lbl}:",
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
        handlers[name] = [
            f"mov QWORD PTR [r13], {val}",
            "mov QWORD PTR [r13+8], 0",
            "add r13, 16",
            *disp(1),
        ]

    handlers["push_i8"] = [
        "movsx rax, BYTE PTR [r12+1]",
        "mov QWORD PTR [r13], rax",
        "mov QWORD PTR [r13+8], 0",
        "add r13, 16",
        *disp(2),
    ]
    handlers["push_i16"] = [
        "movsx rax, WORD PTR [r12+1]",
        "mov QWORD PTR [r13], rax",
        "mov QWORD PTR [r13+8], 0",
        "add r13, 16",
        *disp(3),
    ]
    handlers["push_i32"] = [
        "movsxd rax, DWORD PTR [r12+1]",
        "mov QWORD PTR [r13], rax",
        "mov QWORD PTR [r13+8], 0",
        "add r13, 16",
        *disp(5),
    ]
    handlers["push_false"] = [
        "mov QWORD PTR [r13], 0",
        "mov QWORD PTR [r13+8], 1",
        "add r13, 16",
        *disp(1),
    ]
    handlers["push_true"] = [
        "mov QWORD PTR [r13], 1",
        "mov QWORD PTR [r13+8], 1",
        "add r13, 16",
        *disp(1),
    ]
    handlers["null"] = [
        "mov QWORD PTR [r13], 0",
        "mov QWORD PTR [r13+8], 2",
        "add r13, 16",
        *disp(1),
    ]
    handlers["undefined"] = [
        "mov QWORD PTR [r13], 0",
        "mov QWORD PTR [r13+8], 3",
        "add r13, 16",
        *disp(1),
    ]
    handlers["push_const8"] = [
        "mov rax, QWORD PTR [r15+48]",
        f"mov rcx, QWORD PTR [rax+{off_bc_cpool}]",
        "movzx edx, BYTE PTR [r12+1]",
        "shl rdx, 4",
        "mov r8, QWORD PTR [rcx+rdx]",
        "mov r9, QWORD PTR [rcx+rdx+8]",
        "mov QWORD PTR [r13], r8",
        "mov QWORD PTR [r13+8], r9",
        "add r13, 16",
        *dup_if_rc("r8", "r9d", "cvm_pc8_done"),
        *disp(2),
    ]

    # --- stack ops ---
    handlers["drop"] = [
        "mov eax, DWORD PTR [r13-8]",
        "test eax, eax",
        "jns cvm_drop_pop",
        "mov rcx, QWORD PTR [r13-16]",
        f"cmp DWORD PTR [rcx{rc:+d}], 1",
        "jle cvm_bail",
        f"dec DWORD PTR [rcx{rc:+d}]",
        "cvm_drop_pop:",
        "sub r13, 16",
        *disp(1),
    ]
    handlers["dup"] = [
        "mov r8, QWORD PTR [r13-16]",
        "mov r9, QWORD PTR [r13-8]",
        "mov QWORD PTR [r13], r8",
        "mov QWORD PTR [r13+8], r9",
        "add r13, 16",
        *dup_if_rc("r8", "r9d", "cvm_dup_done"),
        *disp(1),
    ]
    handlers["dup1"] = [
        "mov r8, QWORD PTR [r13-16]",
        "mov r9, QWORD PTR [r13-8]",
        "mov r10, QWORD PTR [r13-32]",
        "mov r11, QWORD PTR [r13-24]",
        "mov QWORD PTR [r13], r8",
        "mov QWORD PTR [r13+8], r9",
        "mov QWORD PTR [r13-16], r10",
        "mov QWORD PTR [r13-8], r11",
        "add r13, 16",
        *dup_if_rc("r10", "r11d", "cvm_dup1_done"),
        *disp(1),
    ]
    handlers["nip"] = [
        "mov eax, DWORD PTR [r13-24]",
        "test eax, eax",
        "jns cvm_nip_move",
        "mov rcx, QWORD PTR [r13-32]",
        f"cmp DWORD PTR [rcx{rc:+d}], 1",
        "jle cvm_bail",
        f"dec DWORD PTR [rcx{rc:+d}]",
        "cvm_nip_move:",
        "mov r8, QWORD PTR [r13-16]",
        "mov r9, QWORD PTR [r13-8]",
        "mov QWORD PTR [r13-32], r8",
        "mov QWORD PTR [r13-24], r9",
        "sub r13, 16",
        *disp(1),
    ]
    handlers["swap"] = [
        "mov r8, QWORD PTR [r13-32]",
        "mov r9, QWORD PTR [r13-24]",
        "mov r10, QWORD PTR [r13-16]",
        "mov r11, QWORD PTR [r13-8]",
        "mov QWORD PTR [r13-32], r10",
        "mov QWORD PTR [r13-24], r11",
        "mov QWORD PTR [r13-16], r8",
        "mov QWORD PTR [r13-8], r9",
        *disp(1),
    ]

    # --- locals get/put/set ---
    for i in range(4):
        off = i * 16
        handlers[f"get_loc{i}"] = [
            f"mov r8, QWORD PTR [r14+{off}]",
            f"mov r9, QWORD PTR [r14+{off + 8}]",
            "mov QWORD PTR [r13], r8",
            "mov QWORD PTR [r13+8], r9",
            "add r13, 16",
            *dup_if_rc("r8", "r9d", f"cvm_gl{i}_done"),
            *disp(1),
        ]
        handlers[f"put_loc{i}"] = [
            f"mov eax, DWORD PTR [r14+{off + 8}]",
            "test eax, eax",
            f"jns cvm_pl{i}_wr",
            f"mov rcx, QWORD PTR [r14+{off}]",
            f"cmp DWORD PTR [rcx{rc:+d}], 1",
            "jle cvm_bail",
            f"dec DWORD PTR [rcx{rc:+d}]",
            f"cvm_pl{i}_wr:",
            "mov r8, QWORD PTR [r13-16]",
            "mov r9, QWORD PTR [r13-8]",
            f"mov QWORD PTR [r14+{off}], r8",
            f"mov QWORD PTR [r14+{off + 8}], r9",
            "sub r13, 16",
            *disp(1),
        ]
        handlers[f"set_loc{i}"] = [
            f"mov eax, DWORD PTR [r14+{off + 8}]",
            "test eax, eax",
            f"jns cvm_sl{i}_wr",
            f"mov rcx, QWORD PTR [r14+{off}]",
            f"cmp DWORD PTR [rcx{rc:+d}], 1",
            "jle cvm_bail",
            f"dec DWORD PTR [rcx{rc:+d}]",
            f"cvm_sl{i}_wr:",
            "mov r8, QWORD PTR [r13-16]",
            "mov r9, QWORD PTR [r13-8]",
            f"mov QWORD PTR [r14+{off}], r8",
            f"mov QWORD PTR [r14+{off + 8}], r9",
            *dup_if_rc("r8", "r9d", f"cvm_sl{i}_done"),
            *disp(1),
        ]

    handlers["get_loc0_loc1"] = [
        "mov r8, QWORD PTR [r14]",
        "mov r9, QWORD PTR [r14+8]",
        "mov QWORD PTR [r13], r8",
        "mov QWORD PTR [r13+8], r9",
        *dup_if_rc("r8", "r9d", "cvm_gl01_a"),
        "mov r8, QWORD PTR [r14+16]",
        "mov r9, QWORD PTR [r14+24]",
        "mov QWORD PTR [r13+16], r8",
        "mov QWORD PTR [r13+24], r9",
        "add r13, 32",
        *dup_if_rc("r8", "r9d", "cvm_gl01_b"),
        *disp(1),
    ]

    for suffix, load_idx, adv in [
        ("8", "movzx edx, BYTE PTR [r12+1]", 2),
        ("", "movzx edx, WORD PTR [r12+1]", 3),
    ]:
        handlers[f"get_loc{suffix}"] = [
            load_idx,
            "shl rdx, 4",
            "mov r8, QWORD PTR [r14+rdx]",
            "mov r9, QWORD PTR [r14+rdx+8]",
            "mov QWORD PTR [r13], r8",
            "mov QWORD PTR [r13+8], r9",
            "add r13, 16",
            *dup_if_rc("r8", "r9d", f"cvm_glx{suffix}_done"),
            *disp(adv),
        ]
        handlers[f"put_loc{suffix}"] = [
            load_idx,
            "shl rdx, 4",
            "mov eax, DWORD PTR [r14+rdx+8]",
            "test eax, eax",
            f"jns cvm_plx{suffix}_wr",
            "mov rcx, QWORD PTR [r14+rdx]",
            f"cmp DWORD PTR [rcx{rc:+d}], 1",
            "jle cvm_bail",
            f"dec DWORD PTR [rcx{rc:+d}]",
            f"cvm_plx{suffix}_wr:",
            "mov r8, QWORD PTR [r13-16]",
            "mov r9, QWORD PTR [r13-8]",
            "mov QWORD PTR [r14+rdx], r8",
            "mov QWORD PTR [r14+rdx+8], r9",
            "sub r13, 16",
            *disp(adv),
        ]
        handlers[f"set_loc{suffix}"] = [
            load_idx,
            "shl rdx, 4",
            "mov eax, DWORD PTR [r14+rdx+8]",
            "test eax, eax",
            f"jns cvm_slx{suffix}_wr",
            "mov rcx, QWORD PTR [r14+rdx]",
            f"cmp DWORD PTR [rcx{rc:+d}], 1",
            "jle cvm_bail",
            f"dec DWORD PTR [rcx{rc:+d}]",
            f"cvm_slx{suffix}_wr:",
            "mov r8, QWORD PTR [r13-16]",
            "mov r9, QWORD PTR [r13-8]",
            "mov QWORD PTR [r14+rdx], r8",
            "mov QWORD PTR [r14+rdx+8], r9",
            *dup_if_rc("r8", "r9d", f"cvm_slx{suffix}_done"),
            *disp(adv),
        ]

    handlers["get_loc_check"] = [
        "movzx edx, WORD PTR [r12+1]",
        "shl rdx, 4",
        "mov r9, QWORD PTR [r14+rdx+8]",
        "cmp r9d, 4",
        "je cvm_bail",
        "mov r8, QWORD PTR [r14+rdx]",
        "mov QWORD PTR [r13], r8",
        "mov QWORD PTR [r13+8], r9",
        "add r13, 16",
        *dup_if_rc("r8", "r9d", "cvm_glc_done"),
        *disp(3),
    ]
    handlers["put_loc_check"] = [
        "movzx edx, WORD PTR [r12+1]",
        "shl rdx, 4",
        "mov eax, DWORD PTR [r14+rdx+8]",
        "cmp eax, 4",
        "je cvm_bail",
        "test eax, eax",
        "jns cvm_plc_wr",
        "mov rcx, QWORD PTR [r14+rdx]",
        f"cmp DWORD PTR [rcx{rc:+d}], 1",
        "jle cvm_bail",
        f"dec DWORD PTR [rcx{rc:+d}]",
        "cvm_plc_wr:",
        "mov r8, QWORD PTR [r13-16]",
        "mov r9, QWORD PTR [r13-8]",
        "mov QWORD PTR [r14+rdx], r8",
        "mov QWORD PTR [r14+rdx+8], r9",
        "sub r13, 16",
        *disp(3),
    ]
    handlers["put_loc_check_init"] = [
        "movzx edx, WORD PTR [r12+1]",
        "shl rdx, 4",
        "cmp DWORD PTR [r14+rdx+8], 4",
        "jne cvm_bail",
        "mov r8, QWORD PTR [r13-16]",
        "mov r9, QWORD PTR [r13-8]",
        "mov QWORD PTR [r14+rdx], r8",
        "mov QWORD PTR [r14+rdx+8], r9",
        "sub r13, 16",
        *disp(3),
    ]

    # --- args get/put/set ---
    for i in range(4):
        off = i * 16
        handlers[f"get_arg{i}"] = [
            f"mov r8, QWORD PTR [rbp+{off}]",
            f"mov r9, QWORD PTR [rbp+{off + 8}]",
            "mov QWORD PTR [r13], r8",
            "mov QWORD PTR [r13+8], r9",
            "add r13, 16",
            *dup_if_rc("r8", "r9d", f"cvm_ga{i}_done"),
            *disp(1),
        ]
        handlers[f"put_arg{i}"] = [
            f"mov eax, DWORD PTR [rbp+{off + 8}]",
            "test eax, eax",
            f"jns cvm_pa{i}_wr",
            f"mov rcx, QWORD PTR [rbp+{off}]",
            f"cmp DWORD PTR [rcx{rc:+d}], 1",
            "jle cvm_bail",
            f"dec DWORD PTR [rcx{rc:+d}]",
            f"cvm_pa{i}_wr:",
            "mov r8, QWORD PTR [r13-16]",
            "mov r9, QWORD PTR [r13-8]",
            f"mov QWORD PTR [rbp+{off}], r8",
            f"mov QWORD PTR [rbp+{off + 8}], r9",
            "sub r13, 16",
            *disp(1),
        ]
        handlers[f"set_arg{i}"] = [
            f"mov eax, DWORD PTR [rbp+{off + 8}]",
            "test eax, eax",
            f"jns cvm_sa{i}_wr",
            f"mov rcx, QWORD PTR [rbp+{off}]",
            f"cmp DWORD PTR [rcx{rc:+d}], 1",
            "jle cvm_bail",
            f"dec DWORD PTR [rcx{rc:+d}]",
            f"cvm_sa{i}_wr:",
            "mov r8, QWORD PTR [r13-16]",
            "mov r9, QWORD PTR [r13-8]",
            f"mov QWORD PTR [rbp+{off}], r8",
            f"mov QWORD PTR [rbp+{off + 8}], r9",
            *dup_if_rc("r8", "r9d", f"cvm_sa{i}_done"),
            *disp(1),
        ]

    handlers["get_arg"] = [
        "movzx edx, WORD PTR [r12+1]",
        "shl rdx, 4",
        "mov r8, QWORD PTR [rbp+rdx]",
        "mov r9, QWORD PTR [rbp+rdx+8]",
        "mov QWORD PTR [r13], r8",
        "mov QWORD PTR [r13+8], r9",
        "add r13, 16",
        *dup_if_rc("r8", "r9d", "cvm_gax_done"),
        *disp(3),
    ]

    # --- closure var_refs ---
    for i in range(4):
        handlers[f"get_var_ref{i}"] = [
            "mov rax, QWORD PTR [r15+32]",
            f"mov rax, QWORD PTR [rax+{i * 8}]",
            f"mov rcx, QWORD PTR [rax+{off_vr_pvalue}]",
            "mov r8, QWORD PTR [rcx]",
            "mov r9, QWORD PTR [rcx+8]",
            "mov QWORD PTR [r13], r8",
            "mov QWORD PTR [r13+8], r9",
            "add r13, 16",
            *dup_if_rc("r8", "r9d", f"cvm_gvr{i}_done"),
            *disp(1),
        ]
        handlers[f"put_var_ref{i}"] = [
            "mov rax, QWORD PTR [r15+32]",
            f"mov rax, QWORD PTR [rax+{i * 8}]",
            f"mov rdx, QWORD PTR [rax+{off_vr_pvalue}]",
            "mov eax, DWORD PTR [rdx+8]",
            "test eax, eax",
            f"jns cvm_pvr{i}_wr",
            "mov rcx, QWORD PTR [rdx]",
            f"cmp DWORD PTR [rcx{rc:+d}], 1",
            "jle cvm_bail",
            f"dec DWORD PTR [rcx{rc:+d}]",
            f"cvm_pvr{i}_wr:",
            "mov r8, QWORD PTR [r13-16]",
            "mov r9, QWORD PTR [r13-8]",
            "mov QWORD PTR [rdx], r8",
            "mov QWORD PTR [rdx+8], r9",
            "sub r13, 16",
            *disp(1),
        ]
        handlers[f"set_var_ref{i}"] = [
            "mov rax, QWORD PTR [r15+32]",
            f"mov rax, QWORD PTR [rax+{i * 8}]",
            f"mov rdx, QWORD PTR [rax+{off_vr_pvalue}]",
            "mov eax, DWORD PTR [rdx+8]",
            "test eax, eax",
            f"jns cvm_svr{i}_wr",
            "mov rcx, QWORD PTR [rdx]",
            f"cmp DWORD PTR [rcx{rc:+d}], 1",
            "jle cvm_bail",
            f"dec DWORD PTR [rcx{rc:+d}]",
            f"cvm_svr{i}_wr:",
            "mov r8, QWORD PTR [r13-16]",
            "mov r9, QWORD PTR [r13-8]",
            "mov QWORD PTR [rdx], r8",
            "mov QWORD PTR [rdx+8], r9",
            *dup_if_rc("r8", "r9d", f"cvm_svr{i}_done"),
            *disp(1),
        ]

    handlers["get_var_ref"] = [
        "mov rax, QWORD PTR [r15+32]",
        "movzx edx, WORD PTR [r12+1]",
        "mov rax, QWORD PTR [rax+rdx*8]",
        f"mov rcx, QWORD PTR [rax+{off_vr_pvalue}]",
        "mov r8, QWORD PTR [rcx]",
        "mov r9, QWORD PTR [rcx+8]",
        "mov QWORD PTR [r13], r8",
        "mov QWORD PTR [r13+8], r9",
        "add r13, 16",
        *dup_if_rc("r8", "r9d", "cvm_gvrx_done"),
        *disp(3),
    ]
    handlers["get_var_ref_check"] = [
        "mov rax, QWORD PTR [r15+32]",
        "movzx edx, WORD PTR [r12+1]",
        "mov rax, QWORD PTR [rax+rdx*8]",
        f"mov rcx, QWORD PTR [rax+{off_vr_pvalue}]",
        "mov r9, QWORD PTR [rcx+8]",
        "cmp r9d, 4",
        "je cvm_bail",
        "mov r8, QWORD PTR [rcx]",
        "mov QWORD PTR [r13], r8",
        "mov QWORD PTR [r13+8], r9",
        "add r13, 16",
        *dup_if_rc("r8", "r9d", "cvm_gvrc_done"),
        *disp(3),
    ]

    # --- in-place int32 local updates ---
    handlers["inc_loc"] = [
        "movzx edx, BYTE PTR [r12+1]",
        "shl rdx, 4",
        "cmp DWORD PTR [r14+rdx+8], 0",
        "jne cvm_bail",
        "mov eax, DWORD PTR [r14+rdx]",
        "add eax, 1",
        "jo cvm_bail",
        "movsxd rax, eax",
        "mov QWORD PTR [r14+rdx], rax",
        *disp(2),
    ]
    handlers["dec_loc"] = [
        "movzx edx, BYTE PTR [r12+1]",
        "shl rdx, 4",
        "cmp DWORD PTR [r14+rdx+8], 0",
        "jne cvm_bail",
        "mov eax, DWORD PTR [r14+rdx]",
        "sub eax, 1",
        "jo cvm_bail",
        "movsxd rax, eax",
        "mov QWORD PTR [r14+rdx], rax",
        *disp(2),
    ]
    handlers["add_loc"] = [
        "movzx edx, BYTE PTR [r12+1]",
        "shl rdx, 4",
        "mov eax, DWORD PTR [r14+rdx+8]",
        "or eax, DWORD PTR [r13-8]",
        "jnz cvm_bail",
        "mov eax, DWORD PTR [r14+rdx]",
        "add eax, DWORD PTR [r13-16]",
        "jo cvm_bail",
        "movsxd rax, eax",
        "mov QWORD PTR [r14+rdx], rax",
        "sub r13, 16",
        *disp(2),
    ]

    # --- int32 arithmetic & bitwise ---
    handlers["inc"] = [
        "cmp DWORD PTR [r13-8], 0",
        "jne cvm_bail",
        "mov eax, DWORD PTR [r13-16]",
        "add eax, 1",
        "jo cvm_bail",
        "movsxd rax, eax",
        "mov QWORD PTR [r13-16], rax",
        *disp(1),
    ]
    handlers["dec"] = [
        "cmp DWORD PTR [r13-8], 0",
        "jne cvm_bail",
        "mov eax, DWORD PTR [r13-16]",
        "sub eax, 1",
        "jo cvm_bail",
        "movsxd rax, eax",
        "mov QWORD PTR [r13-16], rax",
        *disp(1),
    ]
    handlers["add"] = [
        "mov eax, DWORD PTR [r13-24]",
        "or eax, DWORD PTR [r13-8]",
        "jnz cvm_bail",
        "mov eax, DWORD PTR [r13-32]",
        "add eax, DWORD PTR [r13-16]",
        "jo cvm_bail",
        "movsxd rax, eax",
        "mov QWORD PTR [r13-32], rax",
        "sub r13, 16",
        *disp(1),
    ]
    handlers["sub"] = [
        "mov eax, DWORD PTR [r13-24]",
        "or eax, DWORD PTR [r13-8]",
        "jnz cvm_bail",
        "mov eax, DWORD PTR [r13-32]",
        "sub eax, DWORD PTR [r13-16]",
        "jo cvm_bail",
        "movsxd rax, eax",
        "mov QWORD PTR [r13-32], rax",
        "sub r13, 16",
        *disp(1),
    ]
    handlers["mul"] = [
        "mov eax, DWORD PTR [r13-24]",
        "or eax, DWORD PTR [r13-8]",
        "jnz cvm_bail",
        "mov eax, DWORD PTR [r13-32]",
        "mov ecx, DWORD PTR [r13-16]",
        "imul eax, ecx",
        "jo cvm_bail",
        "test eax, eax",
        "jnz cvm_mul_ok",
        # Reject negative-zero case when either operand is negative and product is 0
        "mov edx, DWORD PTR [r13-32]",
        "or edx, ecx",
        "js cvm_bail",
        "cvm_mul_ok:",
        "movsxd rax, eax",
        "mov QWORD PTR [r13-32], rax",
        "sub r13, 16",
        *disp(1),
    ]
    handlers["div"] = [
        "mov eax, DWORD PTR [r13-24]",
        "or eax, DWORD PTR [r13-8]",
        "jnz cvm_bail",
        "mov eax, DWORD PTR [r13-32]",
        "mov ecx, DWORD PTR [r13-16]",
        "test eax, eax",
        "js cvm_bail",
        "test ecx, ecx",
        "jle cvm_bail",
        "xor edx, edx",
        "div ecx",
        "test edx, edx",
        "jnz cvm_bail",
        "mov QWORD PTR [r13-32], rax",
        "sub r13, 16",
        *disp(1),
    ]
    handlers["mod"] = [
        "mov eax, DWORD PTR [r13-24]",
        "or eax, DWORD PTR [r13-8]",
        "jnz cvm_bail",
        "mov eax, DWORD PTR [r13-32]",
        "mov ecx, DWORD PTR [r13-16]",
        "test eax, eax",
        "js cvm_bail",
        "test ecx, ecx",
        "jle cvm_bail",
        "xor edx, edx",
        "div ecx",
        "mov QWORD PTR [r13-32], rdx",
        "sub r13, 16",
        *disp(1),
    ]
    for name, op in [("and", "and"), ("or", "or"), ("xor", "xor")]:
        handlers[name] = [
            "mov eax, DWORD PTR [r13-24]",
            "or eax, DWORD PTR [r13-8]",
            "jnz cvm_bail",
            "mov eax, DWORD PTR [r13-32]",
            f"{op} eax, DWORD PTR [r13-16]",
            "movsxd rax, eax",
            "mov QWORD PTR [r13-32], rax",
            "sub r13, 16",
            *disp(1),
        ]
    for name, op in [("shl", "shl"), ("sar", "sar")]:
        handlers[name] = [
            "mov eax, DWORD PTR [r13-24]",
            "or eax, DWORD PTR [r13-8]",
            "jnz cvm_bail",
            "mov eax, DWORD PTR [r13-32]",
            "mov ecx, DWORD PTR [r13-16]",
            f"{op} eax, cl",
            "movsxd rax, eax",
            "mov QWORD PTR [r13-32], rax",
            "sub r13, 16",
            *disp(1),
        ]
    handlers["shr"] = [
        "mov eax, DWORD PTR [r13-24]",
        "or eax, DWORD PTR [r13-8]",
        "jnz cvm_bail",
        "mov eax, DWORD PTR [r13-32]",
        "mov ecx, DWORD PTR [r13-16]",
        "shr eax, cl",
        "test eax, eax",
        "js cvm_bail",
        "mov QWORD PTR [r13-32], rax",
        "sub r13, 16",
        *disp(1),
    ]
    handlers["lnot"] = [
        "mov eax, DWORD PTR [r13-8]",
        "cmp eax, 3",
        "ja cvm_bail",
        "xor ecx, ecx",
        "cmp DWORD PTR [r13-16], 0",
        "sete cl",
        "mov QWORD PTR [r13-16], rcx",
        "mov QWORD PTR [r13-8], 1",
        *disp(1),
    ]

    # --- comparisons ---
    for name, setcc in [("lt", "setl"), ("lte", "setle"), ("gt", "setg"), ("gte", "setge")]:
        handlers[name] = [
            "mov eax, DWORD PTR [r13-24]",
            "or eax, DWORD PTR [r13-8]",
            "jnz cvm_bail",
            "mov eax, DWORD PTR [r13-32]",
            "xor ecx, ecx",
            "cmp eax, DWORD PTR [r13-16]",
            f"{setcc} cl",
            "mov QWORD PTR [r13-32], rcx",
            "mov QWORD PTR [r13-24], 1",
            "sub r13, 16",
            *disp(1),
        ]
    for name, setcc, obj_eq_val in [
        ("strict_eq", "sete", 1),
        ("strict_neq", "setne", 0),
        ("eq", "sete", 1),
        ("neq", "setne", 0),
    ]:
        # Fast path: both int32, OR both same primitive tag in {1=bool,2=null,3=undef}, OR both JS_TAG_OBJECT (-1) with rc > 1
        handlers[name] = [
            "mov eax, DWORD PTR [r13-24]",
            "mov edx, DWORD PTR [r13-8]",
            "cmp eax, edx",
            f"jne cvm_{name}_diff",
            "cmp eax, 3",
            f"ja cvm_{name}_chk_obj",
            "mov ecx, DWORD PTR [r13-32]",
            "xor eax, eax",
            "cmp ecx, DWORD PTR [r13-16]",
            f"{setcc} al",
            "mov QWORD PTR [r13-32], rax",
            "mov QWORD PTR [r13-24], 1",
            "sub r13, 16",
            *disp(1),
            f"cvm_{name}_chk_obj:",
            "cmp eax, -1",
            "jne cvm_bail",
            "mov r8, QWORD PTR [r13-32]",
            "mov r9, QWORD PTR [r13-16]",
            "cmp r8, r9",
            f"je cvm_{name}_same_obj",
            f"cmp DWORD PTR [r8{rc:+d}], 1",
            "jle cvm_bail",
            f"cmp DWORD PTR [r9{rc:+d}], 1",
            "jle cvm_bail",
            f"dec DWORD PTR [r8{rc:+d}]",
            f"dec DWORD PTR [r9{rc:+d}]",
            f"mov QWORD PTR [r13-32], {1 - obj_eq_val}",
            "mov QWORD PTR [r13-24], 1",
            "sub r13, 16",
            *disp(1),
            f"cvm_{name}_same_obj:",
            f"cmp DWORD PTR [r8{rc:+d}], 2",
            "jle cvm_bail",
            f"sub DWORD PTR [r8{rc:+d}], 2",
            f"mov QWORD PTR [r13-32], {obj_eq_val}",
            "mov QWORD PTR [r13-24], 1",
            "sub r13, 16",
            *disp(1),
            f"cvm_{name}_diff:",
            # For strict_eq/strict_neq: int/bool/null/undef with different tags (none float/bigint) are never equal!
            *(
                [
                    "cmp eax, 3",
                    "ja cvm_bail",
                    "cmp edx, 3",
                    "ja cvm_bail",
                    f"mov QWORD PTR [r13-32], {1 - obj_eq_val}",
                    "mov QWORD PTR [r13-24], 1",
                    "sub r13, 16",
                    *disp(1),
                ]
                if name.startswith("strict_")
                else ["jmp cvm_bail"]
            ),
        ]

    # --- branches & gotos (with exact interrupt_counter polling!) ---
    for name, load_delta in [
        ("goto8", "movsx rcx, BYTE PTR [r12+1]"),
        ("goto16", "movsx rcx, WORD PTR [r12+1]"),
        ("goto", "movsxd rcx, DWORD PTR [r12+1]"),
    ]:
        handlers[name] = [
            f"cmp DWORD PTR [rbx+{off_ic_ctr}], 1",
            "jle cvm_bail",
            f"dec DWORD PTR [rbx+{off_ic_ctr}]",
            load_delta,
            "lea r12, [r12 + rcx + 1]",
            *disp(0),
        ]

    for name, load_delta, fall_adv, jump_on_nz in [
        ("if_false8", "movsx rcx, BYTE PTR [r12+1]", 2, False),
        ("if_true8", "movsx rcx, BYTE PTR [r12+1]", 2, True),
        ("if_false", "movsxd rcx, DWORD PTR [r12+1]", 5, False),
        ("if_true", "movsxd rcx, DWORD PTR [r12+1]", 5, True),
    ]:
        j_take = "jnz" if jump_on_nz else "jz"
        handlers[name] = [
            f"cmp DWORD PTR [rbx+{off_ic_ctr}], 1",
            "jle cvm_bail",
            "mov eax, DWORD PTR [r13-8]",
            "cmp eax, 3",
            f"jbe cvm_{name}_prim",
            "cmp eax, -1",
            "jne cvm_bail",
            "mov r8, QWORD PTR [r13-16]",
            f"test BYTE PTR [r8+{htmldda_byte}], {htmldda_mask}",
            "jnz cvm_bail",
            f"cmp DWORD PTR [r8{rc:+d}], 1",
            "jle cvm_bail",
            f"dec DWORD PTR [r8{rc:+d}]",
            f"dec DWORD PTR [rbx+{off_ic_ctr}]",
            "sub r13, 16",
            *([load_delta, "lea r12, [r12 + rcx + 1]", *disp(0)] if jump_on_nz else disp(fall_adv)),
            f"cvm_{name}_prim:",
            f"dec DWORD PTR [rbx+{off_ic_ctr}]",
            "mov eax, DWORD PTR [r13-16]",
            "sub r13, 16",
            "test eax, eax",
            f"{j_take} cvm_{name}_take",
            *disp(fall_adv),
            f"cvm_{name}_take:",
            load_delta,
            "lea r12, [r12 + rcx + 1]",
            *disp(0),
        ]

    # --- fast dense array element read (get_array_el) ---
    handlers["get_array_el"] = [
        "cmp DWORD PTR [r13-24], -1",
        "jne cvm_bail",
        "cmp DWORD PTR [r13-8], 0",
        "jne cvm_bail",
        "mov r8, QWORD PTR [r13-32]",
        f"cmp WORD PTR [r8+{off_obj_cid}], 2",
        "jne cvm_bail",
        f"test BYTE PTR [r8+{fast_arr_byte}], {fast_arr_mask}",
        "jz cvm_bail",
        "mov eax, DWORD PTR [r13-16]",
        f"cmp eax, DWORD PTR [r8+{off_arr_count}]",
        "jae cvm_bail",
        f"cmp DWORD PTR [r8{rc:+d}], 1",
        "jle cvm_bail",
        f"mov rcx, QWORD PTR [r8+{off_arr_vals}]",
        "shl rax, 4",
        "mov r9, QWORD PTR [rcx+rax]",
        "mov r10, QWORD PTR [rcx+rax+8]",
        "mov QWORD PTR [r13-32], r9",
        "mov QWORD PTR [r13-24], r10",
        "sub r13, 16",
        *dup_if_rc("r9", "r10d", "cvm_gael_dup"),
        f"dec DWORD PTR [r8{rc:+d}]",
        *disp(1),
    ]

    # --- Property IC fast paths (get_field, get_field2, put_field) ---
    if property_ic:
        for fname, is_gf2 in [("get_field", False), ("get_field2", True)]:
            p = f"cvm_{fname}"
            g = [
                "cmp DWORD PTR [r13-8], -1",
                "jne cvm_bail",
                "mov r8, QWORD PTR [r13-16]",
            ]
            if not is_gf2:
                g += [f"cmp DWORD PTR [r8{rc:+d}], 1", "jle cvm_bail"]
            g += [
                f"test BYTE PTR [r8+{exotic_byte}], {exotic_mask}",
                "jnz cvm_bail",
                f"cmp DWORD PTR [rdi+{off_rt_ic_mode}], 1",
                "jne cvm_bail",
                "mov rax, QWORD PTR [r15+48]",
                f"mov r9, QWORD PTR [rax+{off_bc_ic}]",
                "cmp r9, 4095",
                "jbe cvm_bail",
                "mov rcx, r12",
                f"sub rcx, QWORD PTR [rax+{off_bc_buf}]",
                "shr rcx, 2",
                "cmp ecx, DWORD PTR [r9+8]",
                "jae cvm_bail",
                "mov r11, QWORD PTR [r9+rcx*8+56]",
                "test r11, r11",
                "jz cvm_bail",
                "cmp BYTE PTR [r11+54], 0",
                "jne cvm_bail",
                f"mov r10, QWORD PTR [r8+{off_obj_shape}]",
                "cmp QWORD PTR [r11], r10",
                f"je {p}_hit",
                # Check secondary ways (up to 3 inline)
                "movzx ecx, BYTE PTR [r11+52]",
                "cmp ecx, 1",
                "jbe cvm_bail",
                "mov r11, QWORD PTR [r11+40]",
                "test r11, r11",
                "jz cvm_bail",
                "cmp QWORD PTR [r11], r10",
                f"je {p}_hit",
                "cmp ecx, 2",
                "jbe cvm_bail",
                "add r11, 40",
                "cmp QWORD PTR [r11], r10",
                f"je {p}_hit",
                "cmp ecx, 3",
                "jbe cvm_bail",
                "add r11, 40",
                "cmp QWORD PTR [r11], r10",
                "jne cvm_bail",
                f"{p}_hit:",
                "mov eax, DWORD PTR [r11+12]",
                "cmp eax, 1",
                f"jne {p}_non_own",
                # JS_IC_OWN (1)
                "mov ecx, DWORD PTR [r11+8]",
                "shl rcx, 4",
                f"mov rdx, QWORD PTR [r8+{off_obj_prop}]",
                f"{p}_load:",
                "mov r9, QWORD PTR [rdx+rcx]",
                "mov r10, QWORD PTR [rdx+rcx+8]",
                "cmp r10d, 4",
                "je cvm_bail",
                *dup_if_rc("r9", "r10d", f"{p}_dup"),
            ]
            if is_gf2:
                g += [
                    "mov QWORD PTR [r13], r9",
                    "mov QWORD PTR [r13+8], r10",
                    "add r13, 16",
                    *disp(5),
                ]
            else:
                g += [
                    f"dec DWORD PTR [r8{rc:+d}]",
                    "mov QWORD PTR [r13-16], r9",
                    "mov QWORD PTR [r13-8], r10",
                    *disp(5),
                ]
            g += [
                f"{p}_non_own:",
                f"mov rcx, QWORD PTR [rdi+{off_rt_epoch}]",
                "test rcx, rcx",
                "jz cvm_bail",
                "cmp QWORD PTR [r11+24], rcx",
                "jne cvm_bail",
                "cmp eax, 2",
                f"jne {p}_chk_unset",
                # JS_IC_PROTO (2)
                "mov rdx, QWORD PTR [r11+16]",
                f"mov rdx, QWORD PTR [rdx+{off_obj_prop}]",
                "mov ecx, DWORD PTR [r11+8]",
                "shl rcx, 4",
                f"jmp {p}_load",
                f"{p}_chk_unset:",
                "cmp eax, 3",
                f"jne {p}_chk_getter",
                # JS_IC_UNSET (3) -> undefined
                "xor r9d, r9d",
                "mov r10d, 3",
                f"jmp {p}_store_prim",
                f"{p}_chk_getter:",
                f"cmp DWORD PTR [rbx+{off_ic_ctr}], 2",
                "jle cvm_bail",
                "cmp eax, 7",
                f"jne {p}_chk_gbool",
                # JS_IC_GETTER_FIELD (7)
                "mov ecx, DWORD PTR [r11+8]",
                "shl rcx, 4",
                f"mov rdx, QWORD PTR [r8+{off_obj_prop}]",
                "mov r9, QWORD PTR [rdx+rcx]",
                "mov r10, QWORD PTR [rdx+rcx+8]",
                "cmp r10d, 4",
                "je cvm_bail",
                f"dec DWORD PTR [rbx+{off_ic_ctr}]",
                *dup_if_rc("r9", "r10d", f"{p}_gf_dup"),
                f"jmp {p}_store_prim",
                f"{p}_chk_gbool:",
                "cmp eax, 8",
                "jne cvm_bail",
                # JS_IC_GETTER_BOOL (8)
                f"dec DWORD PTR [rbx+{off_ic_ctr}]",
                "mov r9d, DWORD PTR [r11+8]",
                "mov r10d, 1",
                f"{p}_store_prim:",
            ]
            if is_gf2:
                g += [
                    "mov QWORD PTR [r13], r9",
                    "mov QWORD PTR [r13+8], r10",
                    "add r13, 16",
                    *disp(5),
                ]
            else:
                g += [
                    f"dec DWORD PTR [r8{rc:+d}]",
                    "mov QWORD PTR [r13-16], r9",
                    "mov QWORD PTR [r13-8], r10",
                    *disp(5),
                ]
            handlers[fname] = g

        # put_field (JS_IC_REPLACE = 4)
        handlers["put_field"] = [
            "cmp DWORD PTR [r13-24], -1",
            "jne cvm_bail",
            "mov r8, QWORD PTR [r13-32]",
            f"cmp DWORD PTR [r8{rc:+d}], 1",
            "jle cvm_bail",
            f"test BYTE PTR [r8+{exotic_byte}], {exotic_mask}",
            "jnz cvm_bail",
            f"cmp DWORD PTR [rdi+{off_rt_ic_mode}], 1",
            "jne cvm_bail",
            "mov rax, QWORD PTR [r15+48]",
            f"mov r9, QWORD PTR [rax+{off_bc_ic}]",
            "cmp r9, 4095",
            "jbe cvm_bail",
            "mov rcx, r12",
            f"sub rcx, QWORD PTR [rax+{off_bc_buf}]",
            "shr rcx, 2",
            "cmp ecx, DWORD PTR [r9+8]",
            "jae cvm_bail",
            "mov r11, QWORD PTR [r9+rcx*8+56]",
            "test r11, r11",
            "jz cvm_bail",
            "cmp BYTE PTR [r11+54], 0",
            "jne cvm_bail",
            f"mov r10, QWORD PTR [r8+{off_obj_shape}]",
            "cmp QWORD PTR [r11], r10",
            "je cvm_pf_hit",
            "movzx ecx, BYTE PTR [r11+52]",
            "cmp ecx, 1",
            "jbe cvm_bail",
            "mov r11, QWORD PTR [r11+40]",
            "test r11, r11",
            "jz cvm_bail",
            "cmp QWORD PTR [r11], r10",
            "je cvm_pf_hit",
            "cmp ecx, 2",
            "jbe cvm_bail",
            "add r11, 40",
            "cmp QWORD PTR [r11], r10",
            "jne cvm_bail",
            "cvm_pf_hit:",
            "cmp DWORD PTR [r11+12], 4",
            "jne cvm_bail",
            "mov ecx, DWORD PTR [r11+8]",
            "shl rcx, 4",
            f"mov rdx, QWORD PTR [r8+{off_obj_prop}]",
            "mov eax, DWORD PTR [rdx+rcx+8]",
            "test eax, eax",
            "jns cvm_pf_wr",
            "mov r9, QWORD PTR [rdx+rcx]",
            "cmp r9, r8",
            "je cvm_bail",
            f"cmp DWORD PTR [r9{rc:+d}], 1",
            "jle cvm_bail",
            f"dec DWORD PTR [r9{rc:+d}]",
            "cvm_pf_wr:",
            "mov r9, QWORD PTR [r13-16]",
            "mov r10, QWORD PTR [r13-8]",
            "mov QWORD PTR [rdx+rcx], r9",
            "mov QWORD PTR [rdx+rcx+8], r10",
            f"dec DWORD PTR [r8{rc:+d}]",
            "sub r13, 32",
            *disp(5),
        ]

    # Filter to valid opcodes in quickjs-opcode.h
    op_set = set(ops)
    return {k: v for k, v in handlers.items() if k in op_set}


def emit_win64(
    source_root: Path, abi: dict, property_ic: bool
) -> tuple[list[str], list[str], list[str]]:
    """Return (masm_lines, gas_lines, eligible_names) for Win64 MASM & MinGW GAS."""
    ops = _load_opcodes(source_root)
    handlers = _build_handlers(abi, ops, property_ic)

    def masm_inst(inst: str) -> str:
        if inst.endswith(":"):
            return inst + ":"
        if inst.startswith("lea rsi, [rip + "):
            sym = inst[len("lea rsi, [rip + ") : -1]
            return f"lea rsi, {sym}"
        return inst

    body: list[str] = [
        "push rbx",
        "push rbp",
        "push rsi",
        "push rdi",
        "push r12",
        "push r13",
        "push r14",
        "push r15",
        "mov r15, rcx",
        "mov r12, QWORD PTR [r15]",
        "mov r13, QWORD PTR [r15+8]",
        "mov r14, QWORD PTR [r15+16]",
        "mov rbp, QWORD PTR [r15+24]",
        "mov rbx, QWORD PTR [r15+40]",
        "mov rdi, QWORD PTR [r15+56]",
        "lea rsi, [rip + cvm_fast_table]",
        "movzx eax, BYTE PTR [r12]",
        "jmp QWORD PTR [rsi + rax*8]",
    ]
    for name in sorted(handlers):
        body.append(f"cvm_op_{name}:")
        body.extend(handlers[name])
    body += [
        "cvm_bail:",
        "mov QWORD PTR [r15], r12",
        "mov QWORD PTR [r15+8], r13",
        "pop r15",
        "pop r14",
        "pop r13",
        "pop r12",
        "pop rdi",
        "pop rsi",
        "pop rbp",
        "pop rbx",
        "ret",
    ]

    table_targets = [
        f"cvm_op_{ops[i]}" if i < len(ops) and ops[i] in handlers else "cvm_bail"
        for i in range(256)
    ]

    masm = [
        ".qjscold SEGMENT ALIGN(16) 'CODE'",
        "ALIGN 16",
        "PUBLIC JS_CVMRunFastSegment",
        "PUBLIC JS_CVMRunFastSegment_end",
        "JS_CVMRunFastSegment PROC",
        *(masm_inst(x) for x in body),
        "JS_CVMRunFastSegment_end LABEL BYTE",
        "JS_CVMRunFastSegment ENDP",
        ".qjscold ENDS",
        ".xdata SEGMENT ALIGN(4) READONLY 'DATA'",
        "ALIGN 4",
        "JS_CVMRunFastSegment_unwind LABEL BYTE",
        "DB 1, 12, 8, 0",
        "DB 12, 0F0h, 10, 0E0h, 8, 0D0h, 6, 0C0h, 4, 070h, 3, 060h, 2, 050h, 1, 030h",
        ".xdata ENDS",
        ".pdata$zzqjscold SEGMENT ALIGN(4) READONLY 'DATA'",
        "DD IMAGEREL JS_CVMRunFastSegment, IMAGEREL JS_CVMRunFastSegment_end, IMAGEREL JS_CVMRunFastSegment_unwind",
        ".pdata$zzqjscold ENDS",
        ".rdata$zzqjscvm SEGMENT ALIGN(8) READONLY 'CONST'",
        "cvm_fast_table LABEL QWORD",
        *(f"DQ {t}" for t in table_targets),
        ".rdata$zzqjscvm ENDS",
    ]

    gas = [
        '.section .qjscold,"xr"',
        ".p2align 4",
        ".globl JS_CVMRunFastSegment, JS_CVMRunFastSegment_end",
        ".def JS_CVMRunFastSegment; .scl 2; .type 32; .endef",
        "JS_CVMRunFastSegment:",
        *body,
        "JS_CVMRunFastSegment_end:",
        '.section .xdata,"dr"',
        ".p2align 2",
        "JS_CVMRunFastSegment_unwind:",
        ".byte 1, 12, 8, 0",
        ".byte 12, 0xf0, 10, 0xe0, 8, 0xd0, 6, 0xc0, 4, 0x70, 3, 0x60, 2, 0x50, 1, 0x30",
        '.section .pdata$zzqjscold,"dr"',
        ".p2align 2",
        ".rva JS_CVMRunFastSegment, JS_CVMRunFastSegment_end, JS_CVMRunFastSegment_unwind",
        '.section .rdata$zzqjscvm,"dr"',
        ".p2align 3",
        "cvm_fast_table:",
        *(f".quad {t}" for t in table_targets),
    ]

    return masm, gas, sorted(handlers)


def emit_linux_elf(source_root: Path, abi: dict, property_ic: bool, cet: bool = True) -> list[str]:
    """Return Intel-syntax ELF GAS lines for Linux x86-64."""
    ops = _load_opcodes(source_root)
    handlers = _build_handlers(abi, ops, property_ic)

    lines = [
        '.section .text.qjs_cvm_fast,"ax",@progbits',
        ".p2align 4",
        ".hidden JS_CVMRunFastSegment",
        ".globl JS_CVMRunFastSegment",
        ".type JS_CVMRunFastSegment,@function",
        "JS_CVMRunFastSegment:",
        ".cfi_startproc",
    ]
    if cet:
        lines.append("endbr64")
    lines += [
        "push rbx",
        ".cfi_def_cfa_offset 16",
        ".cfi_offset rbx, -16",
        "push rbp",
        ".cfi_def_cfa_offset 24",
        ".cfi_offset rbp, -24",
        "push rsi",
        ".cfi_def_cfa_offset 32",
        "push rdi",
        ".cfi_def_cfa_offset 40",
        "push r12",
        ".cfi_def_cfa_offset 48",
        ".cfi_offset r12, -48",
        "push r13",
        ".cfi_def_cfa_offset 56",
        ".cfi_offset r13, -56",
        "push r14",
        ".cfi_def_cfa_offset 64",
        ".cfi_offset r14, -64",
        "push r15",
        ".cfi_def_cfa_offset 72",
        ".cfi_offset r15, -72",
        "mov r15, rdi",
        "mov r12, QWORD PTR [r15]",
        "mov r13, QWORD PTR [r15+8]",
        "mov r14, QWORD PTR [r15+16]",
        "mov rbp, QWORD PTR [r15+24]",
        "mov rbx, QWORD PTR [r15+40]",
        "mov rdi, QWORD PTR [r15+56]",
        "lea rsi, [rip + cvm_fast_table]",
        "movzx eax, BYTE PTR [r12]",
        "jmp QWORD PTR [rsi + rax*8]",
    ]
    for name in sorted(handlers):
        lines.append(f"cvm_op_{name}:")
        lines.extend(handlers[name])
    lines += [
        "cvm_bail:",
        "mov QWORD PTR [r15], r12",
        "mov QWORD PTR [r15+8], r13",
        "pop r15",
        ".cfi_def_cfa_offset 64",
        "pop r14",
        ".cfi_def_cfa_offset 56",
        "pop r13",
        ".cfi_def_cfa_offset 48",
        "pop r12",
        ".cfi_def_cfa_offset 40",
        "pop rdi",
        ".cfi_def_cfa_offset 32",
        "pop rsi",
        ".cfi_def_cfa_offset 24",
        "pop rbp",
        ".cfi_def_cfa_offset 16",
        "pop rbx",
        ".cfi_def_cfa_offset 8",
        "ret",
        ".cfi_endproc",
        ".size JS_CVMRunFastSegment,.-JS_CVMRunFastSegment",
        '.section .data.rel.ro.local.qjs_cvm_fast,"aw",@progbits',
        ".p2align 3",
        "cvm_fast_table:",
    ]
    for i in range(256):
        target = f"cvm_op_{ops[i]}" if i < len(ops) and ops[i] in handlers else "cvm_bail"
        lines.append(f".quad {target}")
    return lines
