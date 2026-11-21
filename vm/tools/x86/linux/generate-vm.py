import sys as _x86_sys
from pathlib import Path as _X86Path

_x86_sys.path.insert(0, str(_X86Path(__file__).resolve().parents[2]))
from x86.common.paths_x86 import activate_tools as _act_x86

_act_x86()

"""Render the shared VM instruction stream as real ELF/CFI, not COFF.

The development private VM convention retains its existing register protocol.
Public entry and C semantic bridges are compiler-checked SysV boundaries; the
initial private bridge implementation is explicit in the generated manifest.
"""

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys
from control_flow import property_note


def apply_hybrid_gc_native(stream, handlers, layout):
    offs = layout["offsets"]
    if "JSRuntime.drc_ok" not in offs or offs["JSGCObjectHeader.ref_count"] != 0:
        return [], []
    if (
        layout["constants"].get("JS_TAG_STRING") != -7
        or layout["constants"].get("JS_TAG_STRING_ROPE") != -6
    ):
        raise ValueError("Unexpected string tag encoding for fast drop")
    ids = {name: i for i, name in enumerate(stream["opcodes"])}
    code = stream["code"]
    fast_arr_byte, fast_arr_mask = layout["bits"]["JSObject.fast_array"][0]
    cls_array = layout["constants"]["JS_CLASS_ARRAY"]

    # Pillar 4a: Keep interp_drop in hot .text; splice ref_count > 1 inline fast-dec
    # and ref_count == 1 string/rope non-reloading leaf release into interp_property_slow_drop.
    if handlers.get("drop") != "interp_drop":
        raise ValueError("Unexpected drop handler: " + repr(handlers.get("drop")))
    cold_code = stream["cold_code"]
    slow_drop_idx = cold_code.index("interp_property_slow_drop:")
    cold_code[slow_drop_idx + 1 : slow_drop_idx + 1] = [
        "mov rax, QWORD PTR [r13-16]",
        "mov r10, QWORD PTR [rbx+56]",
        f"cmp BYTE PTR [r10+{offs['JSRuntime.drc_ok']}], 1",
        "jne interp_property_slow_drop_c",
        "cmp DWORD PTR [rax+0], 1",
        "je interp_property_slow_drop_rc1",
        "jl interp_property_slow_drop_c",
        "dec DWORD PTR [rax+0]",
        "sub r13, 16",
        "add r12, 1",
        "movzx eax, BYTE PTR [r12]",
        "jmp QWORD PTR [rdi+rax*8]",
        "interp_property_slow_drop_rc1:",
        "mov edx, DWORD PTR [r13-8]",
        "sub edx, -7",
        "cmp edx, 1",
        "ja interp_property_slow_drop_c",
        "call JS_LinuxHybridDropString1",
        "sub r13, 16",
        "add r12, 1",
        "movzx eax, BYTE PTR [r12]",
        "jmp QWORD PTR [rdi+rax*8]",
        "interp_property_slow_drop_c:",
    ]
    cold_code.append(".fill 48, 1, 0x90")

    # Pillar 4b: Borrowed Dense-Array DRC on interp_get_loc0_loc1 with 0-mod-64 dead-shadow NOP alignment
    loc01_idx = code.index("interp_get_loc0_loc1:")
    code[loc01_idx + 1 : loc01_idx + 1] = [
        f"cmp BYTE PTR [r12+1], {ids['get_array_el']}",
        "je JS_LinuxBorrowedLoc01ArrayGet",
        "interp_get_loc0_loc1_fallback:",
    ]
    loc01_end = code.index("jmp QWORD PTR [rdi+rax*8]", loc01_idx)
    code[loc01_end + 1 : loc01_end + 1] = [".fill 52, 1, 0x90"]
    borrowed_loc01 = [
        "mov r10, QWORD PTR [rbx+56]",
        f"cmp BYTE PTR [r10+{offs['JSRuntime.drc_ok']}], 1",
        "jne interp_get_loc0_loc1_fallback",
        f"cmp WORD PTR [rbp+{offs['JSStackFrame.var_ref_count']}], 0",
        "jne interp_get_loc0_loc1_fallback",
        "cmp DWORD PTR [r14+8], -1",
        "jne interp_get_loc0_loc1_fallback",
        "cmp DWORD PTR [r14+24], 0",
        "jne interp_get_loc0_loc1_fallback",
        "mov r8, QWORD PTR [r14+0]",
        f"cmp WORD PTR [r8+{offs['JSObject.class_id']}], {cls_array}",
        "jne interp_get_loc0_loc1_fallback",
        f"test BYTE PTR [r8+{fast_arr_byte}], {fast_arr_mask}",
        "jz interp_get_loc0_loc1_fallback",
        "mov ecx, DWORD PTR [r14+16]",
        "test ecx, ecx",
        "js interp_get_loc0_loc1_fallback",
        f"cmp ecx, DWORD PTR [r8+{offs['JSObject.u.array.count']}]",
        "jae interp_get_loc0_loc1_fallback",
        f"mov r9, QWORD PTR [r8+{offs['JSObject.u.array.u.values']}]",
        "shl rcx, 4",
        "mov rax, QWORD PTR [r9+rcx]",
        "mov rdx, QWORD PTR [r9+rcx+8]",
        "test edx, edx",
        "jns borrowed_loc01_push",
        "inc DWORD PTR [rax+0]",
        "borrowed_loc01_push:",
        "mov QWORD PTR [r13], rax",
        "mov QWORD PTR [r13+8], rdx",
        "add r13, 16",
        "add r12, 2",
        "movzx eax, BYTE PTR [r12]",
        "jmp QWORD PTR [rdi+rax*8]",
        ".fill 292, 1, 0x90",
    ]

    drop_str1_leaf = [
        "push rdi",
        ".cfi_adjust_cfa_offset 8",
        ".cfi_offset rdi, -16",
        "push rsi",
        ".cfi_adjust_cfa_offset 8",
        ".cfi_offset rsi, -24",
        "sub rsp, 8",
        ".cfi_adjust_cfa_offset 8",
        "mov rdi, r10",
        "mov rsi, rax",
        "call js_hybrid_drop_string1",
        "add rsp, 8",
        ".cfi_adjust_cfa_offset -8",
        "pop rsi",
        ".cfi_restore rsi",
        ".cfi_adjust_cfa_offset -8",
        "pop rdi",
        ".cfi_restore rdi",
        ".cfi_adjust_cfa_offset -8",
        "ret",
        ".fill 864, 1, 0x90",
    ]

    return [
        ("JS_LinuxBorrowedLoc01ArrayGet", borrowed_loc01),
    ], [
        ("JS_LinuxHybridDropString1", drop_str1_leaf),
    ]


def apply_regression_fast_paths(stream, handlers, layout, slot_blocks=()):
    """Add shared cold-section fast paths for dup2, put_var, and float-tagged int inc/dec."""
    offs = layout["offsets"]
    consts = layout["constants"]
    if (
        consts.get("JS_TAG_INT") != 0
        or consts.get("JS_TAG_FLOAT64") != 8
        or consts.get("JS_PROP_WRITABLE") != 2
        or consts.get("JS_PROP_LENGTH") != 8
        or consts.get("JS_PROP_TMASK") != 48
        or offs.get("JSGCObjectHeader.ref_count") != 0
        or offs.get("JSShapeProperty.atom") != 4
    ):
        raise ValueError("Unexpected layout constants for native regression fast paths")

    extra_blocks = []

    # 1. OP_dup2: duplicates top two stack slots (used heavily by compound array/indexed updates).
    if handlers.get("dup2", "interp_slow") == "interp_slow":
        dup2_rows = [
            "mov rax, QWORD PTR [r13-32]",
            "mov rdx, QWORD PTR [r13-24]",
            "test edx, edx",
            "jns linux_dup2_first_ready",
            "inc DWORD PTR [rax+0]",
            "linux_dup2_first_ready:",
            "mov QWORD PTR [r13], rax",
            "mov QWORD PTR [r13+8], rdx",
            "mov rax, QWORD PTR [r13-16]",
            "mov rdx, QWORD PTR [r13-8]",
            "test edx, edx",
            "jns linux_dup2_second_ready",
            "inc DWORD PTR [rax+0]",
            "linux_dup2_second_ready:",
            "mov QWORD PTR [r13+16], rax",
            "mov QWORD PTR [r13+24], rdx",
            "add r13, 32",
            "inc r12",
            "movzx eax, BYTE PTR [r12]",
            "jmp QWORD PTR [rdi+rax*8]",
        ]
        extra_blocks.append(("JS_LinuxDup2", dup2_rows))
        handlers["dup2"] = "JS_LinuxDup2"

    # 2. OP_put_var: direct own-property write on global_var_obj / global_obj when slot is writable
    # normal data and previous value is non-refcounted (refcounted/exotic/readonly/TDZ fall back).
    if handlers.get("put_var", "interp_slow") == "interp_slow":
        gvar_off = offs["JSContext.global_var_obj"]
        gobj_off = offs["JSContext.global_obj"]
        shape_off = offs["JSObject.shape"]
        prop_off = offs["JSObject.prop"]
        mask_off = offs["JSShape.prop_hash_mask"]
        sprop_off = offs["JSShape.prop"]
        flags_mask = consts["JS_PROP_TMASK"] | consts["JS_PROP_LENGTH"] | consts["JS_PROP_WRITABLE"]
        flags_writable = consts["JS_PROP_WRITABLE"]
        put_var_rows = [
            "mov r9d, DWORD PTR [r12+1]",
            f"mov r8, QWORD PTR [rsi+{gvar_off}]",
            f"mov r10, QWORD PTR [r8+{shape_off}]",
            f"mov ecx, DWORD PTR [r10+{mask_off}]",
            "mov edx, r9d",
            "and edx, ecx",
            "neg rdx",
            "mov ecx, DWORD PTR [r10+rdx*4-4]",
            f"lea r11, [r10+{sprop_off}]",
            "linux_put_var_lex_probe:",
            "test ecx, ecx",
            "jz linux_put_var_global",
            "lea rax, [r11+rcx*8-8]",
            "cmp DWORD PTR [rax+4], r9d",
            "je linux_put_var_lex_found",
            "mov ecx, DWORD PTR [rax]",
            "and ecx, 67108863",
            "jmp linux_put_var_lex_probe",
            "linux_put_var_lex_found:",
            "mov edx, DWORD PTR [rax]",
            "shr edx, 26",
            f"and edx, {flags_mask}",
            f"cmp edx, {flags_writable}",
            "jne linux_put_var_slow",
            "dec ecx",
            "shl rcx, 4",
            f"mov r10, QWORD PTR [r8+{prop_off}]",
            "add r10, rcx",
            "mov edx, DWORD PTR [r10+8]",
            "cmp edx, 4",
            "je linux_put_var_slow",
            "test edx, edx",
            "js linux_put_var_slow",
            "jmp linux_put_var_store",
            "linux_put_var_global:",
            f"mov r8, QWORD PTR [rsi+{gobj_off}]",
            f"mov r10, QWORD PTR [r8+{shape_off}]",
            f"mov ecx, DWORD PTR [r10+{mask_off}]",
            "mov edx, r9d",
            "and edx, ecx",
            "neg rdx",
            "mov ecx, DWORD PTR [r10+rdx*4-4]",
            f"lea r11, [r10+{sprop_off}]",
            "linux_put_var_obj_probe:",
            "test ecx, ecx",
            "jz linux_put_var_slow",
            "lea rax, [r11+rcx*8-8]",
            "cmp DWORD PTR [rax+4], r9d",
            "je linux_put_var_obj_found",
            "mov ecx, DWORD PTR [rax]",
            "and ecx, 67108863",
            "jmp linux_put_var_obj_probe",
            "linux_put_var_obj_found:",
            "mov edx, DWORD PTR [rax]",
            "shr edx, 26",
            f"and edx, {flags_mask}",
            f"cmp edx, {flags_writable}",
            "jne linux_put_var_slow",
            "dec ecx",
            "shl rcx, 4",
            f"mov r10, QWORD PTR [r8+{prop_off}]",
            "add r10, rcx",
            "cmp DWORD PTR [r10+8], 0",
            "jl linux_put_var_slow",
            "linux_put_var_store:",
            "mov rax, QWORD PTR [r13-16]",
            "mov rdx, QWORD PTR [r13-8]",
            "mov QWORD PTR [r10], rax",
            "mov QWORD PTR [r10+8], rdx",
            "sub r13, 16",
            "add r12, 5",
            "movzx eax, BYTE PTR [r12]",
            "jmp QWORD PTR [rdi+rax*8]",
            "linux_put_var_slow:",
            "lea rax, [rip+JS_FramePublishDirtyTable]",
            "cmp rdi, rax",
            "je dirty_interp_slow",
            "jmp interp_slow",
        ]
        extra_blocks.append(("JS_LinuxPutVar", put_var_rows))
        handlers["put_var"] = "JS_LinuxPutVar"

    # 3. Normalize exact int32 FLOAT64 operands to JS_TAG_INT on cold inc/dec branches
    # (zero hot-path overhead; prevents downward loops initialized from float64 ints from trapping in slow path).
    code = stream["code"]

    def patch_cold_jne(label, expected_cmp, target):
        idx = code.index(label)
        if (
            code[idx + expected_cmp[0]] != expected_cmp[1]
            or code[idx + expected_cmp[0] + 1] != "jne interp_slow"
        ):
            raise ValueError("Review inc/dec handler shape for " + label)
        code[idx + expected_cmp[0] + 1] = "jne " + target

    patch_cold_jne("interp_inc_loc:", (4, "cmp DWORD PTR [r8+8], 0"), "JS_LinuxFloatIncLoc")
    patch_cold_jne("interp_dec_loc:", (4, "cmp DWORD PTR [r8+8], 0"), "JS_LinuxFloatDecLoc")
    patch_cold_jne("interp_inc:", (1, "cmp DWORD PTR [r13-8], 0"), "JS_LinuxFloatInc")
    patch_cold_jne("interp_dec:", (1, "cmp DWORD PTR [r13-8], 0"), "JS_LinuxFloatDec")
    patch_cold_jne("interp_post_inc:", (1, "cmp DWORD PTR [r13-8], 0"), "JS_LinuxFloatPostInc")
    patch_cold_jne("interp_post_dec:", (1, "cmp DWORD PTR [r13-8], 0"), "JS_LinuxFloatPostDec")

    def float_loc_stub(op_instr):
        return [
            "cmp DWORD PTR [r8+8], 8",
            "jne linux_float_incdec_slow",
            "movsd xmm0, QWORD PTR [r8]",
            "cvttsd2si eax, xmm0",
            "cvtsi2sd xmm1, eax",
            "ucomisd xmm0, xmm1",
            "jne linux_float_incdec_slow",
            "jp linux_float_incdec_slow",
            op_instr,
            "jo linux_float_incdec_slow",
            "mov QWORD PTR [r8], rax",
            "mov QWORD PTR [r8+8], 0",
            "add r12, 2",
            "movzx eax, BYTE PTR [r12]",
            "jmp QWORD PTR [rdi+rax*8]",
        ]

    def float_tos_stub(op_instr):
        return [
            "cmp DWORD PTR [r13-8], 8",
            "jne linux_float_incdec_slow",
            "movsd xmm0, QWORD PTR [r13-16]",
            "cvttsd2si eax, xmm0",
            "cvtsi2sd xmm1, eax",
            "ucomisd xmm0, xmm1",
            "jne linux_float_incdec_slow",
            "jp linux_float_incdec_slow",
            op_instr,
            "jo linux_float_incdec_slow",
            "mov QWORD PTR [r13-16], rax",
            "mov QWORD PTR [r13-8], 0",
            "add r12, 1",
            "movzx eax, BYTE PTR [r12]",
            "jmp QWORD PTR [rdi+rax*8]",
        ]

    def float_post_stub(op_instr, include_slow=False):
        rows = [
            "cmp DWORD PTR [r13-8], 8",
            "jne linux_float_incdec_slow",
            "movsd xmm0, QWORD PTR [r13-16]",
            "cvttsd2si eax, xmm0",
            "cvtsi2sd xmm1, eax",
            "ucomisd xmm0, xmm1",
            "jne linux_float_incdec_slow",
            "jp linux_float_incdec_slow",
            op_instr,
            "jo linux_float_incdec_slow",
            "xor edx, edx",
            "inc r12",
            "mov QWORD PTR [r13], rax",
            "mov QWORD PTR [r13+8], rdx",
            "add r13, 16",
            "movzx eax, BYTE PTR [r12]",
            "jmp QWORD PTR [rdi+rax*8]",
        ]
        if include_slow:
            rows += [
                "linux_float_incdec_slow:",
                "lea rax, [rip+JS_FramePublishDirtyTable]",
                "cmp rdi, rax",
                "je dirty_interp_slow",
                "jmp interp_slow",
            ]
        return rows

    extra_blocks += [
        ("JS_LinuxFloatIncLoc", float_loc_stub("add eax, 1")),
        ("JS_LinuxFloatDecLoc", float_loc_stub("sub eax, 1")),
        ("JS_LinuxFloatInc", float_tos_stub("add eax, 1")),
        ("JS_LinuxFloatDec", float_tos_stub("sub eax, 1")),
        ("JS_LinuxFloatPostInc", float_post_stub("add eax, 1")),
        ("JS_LinuxFloatPostDec", float_post_stub("sub eax, 1", include_slow=True)),
    ]

    # 4. OP_push_bigint_i32: push 32-bit immediate as JS_TAG_SHORT_BIG_INT (tag 7).
    if handlers.get("push_bigint_i32", "interp_slow") == "interp_slow":
        push_bigint_rows = [
            "mov eax, DWORD PTR [r12+1]",
            "mov QWORD PTR [r13], rax",
            "mov QWORD PTR [r13+8], 7",
            "add r13, 16",
            "add r12, 5",
            "movzx eax, BYTE PTR [r12]",
            "jmp QWORD PTR [rdi+rax*8]",
        ]
        extra_blocks.append(("JS_LinuxPushBigIntI32", push_bigint_rows))
        handlers["push_bigint_i32"] = "JS_LinuxPushBigIntI32"

    # 5. Route already-rejected bytecode functions (FRAME_KIND == 2, declined by arguments guard)
    # directly to the fast host call bridge instead of exiting through the 7-layer interp_slow chain.
    call_code = stream["call_code"]
    unready_idx = call_code.index("interp_meta_unready:")
    if call_code[unready_idx + 1 : unready_idx + 3] != ["test eax, 1", "jz interp_slow"]:
        raise ValueError("Review interp_meta_unready shape")
    kind_off = offs["JSFunctionBytecode.byte_code_buf"] - 1
    call_code[unready_idx + 1 : unready_idx + 3] = [
        "test eax, 1",
        "jnz interp_meta_supported_unready",
        f"cmp BYTE PTR [r9+{kind_off}], 2",
        "je linux_forward_original_host",
        "jmp interp_slow",
        "interp_meta_supported_unready:",
    ]

    # 6. OP_set_loc_uninitialized: handle refcounted locals (rc > 1 inline dec, rc == 1 string/rope
    # leaf drop) in cold block instead of falling through the 7-layer interp_slow chain.
    if "JSRuntime.drc_ok" in offs:
        drc_off = offs["JSRuntime.drc_ok"]
        uninit_idx = code.index("interp_set_loc_uninitialized:")
        if code[uninit_idx + 4 : uninit_idx + 6] != ["cmp DWORD PTR [r8+8], 0", "jl interp_slow"]:
            raise ValueError("Review interp_set_loc_uninitialized shape")
        code[uninit_idx + 5] = "jl JS_LinuxSetLocUninitRef"
        extra_blocks.append(
            (
                "JS_LinuxSetLocUninitRef",
                [
                    "mov rax, QWORD PTR [r8]",
                    "mov r10, QWORD PTR [rbx+56]",
                    f"cmp BYTE PTR [r10+{drc_off}], 1",
                    "jne linux_set_loc_uninit_slow",
                    "cmp DWORD PTR [rax+0], 1",
                    "je linux_set_loc_uninit_rc1",
                    "jl linux_set_loc_uninit_slow",
                    "dec DWORD PTR [rax+0]",
                    "mov QWORD PTR [r8], 0",
                    "mov QWORD PTR [r8+8], 4",
                    "add r12, 3",
                    "movzx eax, BYTE PTR [r12]",
                    "jmp QWORD PTR [rdi+rax*8]",
                    "linux_set_loc_uninit_rc1:",
                    "mov edx, DWORD PTR [r8+8]",
                    "sub edx, -7",
                    "cmp edx, 1",
                    "ja linux_set_loc_uninit_slow",
                    "mov QWORD PTR [r8], 0",
                    "mov QWORD PTR [r8+8], 4",
                    "call JS_LinuxHybridDropString1",
                    "add r12, 3",
                    "movzx eax, BYTE PTR [r12]",
                    "jmp QWORD PTR [rdi+rax*8]",
                    "linux_set_loc_uninit_slow:",
                    "lea rax, [rip+JS_FramePublishDirtyTable]",
                    "cmp rdi, rax",
                    "je dirty_interp_slow",
                    "jmp interp_slow",
                ],
            )
        )

        # 7. slot_store_last: bypass JS_FrameInterpFree bridge for rc == 1 string/rope overwrites.
        for sname, srows in slot_blocks:
            if sname == "JS_LinuxSlotCold":
                idx = srows.index("slot_store_last_ready:")
                if srows[idx + 1 : idx + 6] != [
                    "and r9d, 127",
                    "add r12, r9",
                    "movdqu xmm0, XMMWORD PTR [r8]",
                    "mov QWORD PTR [r8], rax",
                    "mov QWORD PTR [r8+8], rdx",
                ]:
                    raise ValueError("Review slot_store_last_ready shape")
                srows[idx + 3 : idx + 6] = [
                    "movdqu xmm0, XMMWORD PTR [r8]",
                    "mov rcx, QWORD PTR [r8]",
                    "mov r11d, DWORD PTR [r8+8]",
                    "mov QWORD PTR [r8], rax",
                    "mov QWORD PTR [r8+8], rdx",
                    f"cmp BYTE PTR [r10+{drc_off}], 1",
                    "jne slot_store_last_bridge",
                    "cmp DWORD PTR [rcx+0], 1",
                    "jne slot_store_last_bridge",
                    "sub r11d, -7",
                    "cmp r11d, 1",
                    "ja slot_store_last_bridge",
                    "mov edx, r11d",
                    "mov rax, rcx",
                    "call JS_LinuxHybridDropString1",
                    "movzx eax, BYTE PTR [r12]",
                    "jmp QWORD PTR [rdi+rax*8]",
                    "slot_store_last_bridge:",
                ]
    return extra_blocks


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", type=Path, required=True)
    ap.add_argument("--layout", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--property-ic", action="store_true")
    ap.add_argument("--sysv-bridges", action="store_true")
    ap.add_argument("--shared-entry", action="store_true")
    ap.add_argument(
        "--allow-existing", action="store_true", help="Regenerate a CMake-owned output directory"
    )
    ap.add_argument("--numeric-compare", action="store_true")
    ap.add_argument("--disable-global-bindings", action="store_true")
    a = ap.parse_args()
    source, layout_path, output = [p.resolve() for p in (a.source, a.layout, a.output)]
    output.mkdir(parents=True, exist_ok=a.allow_existing)
    sys.path.insert(0, str(source / "tools"))
    from x86.common.paths_x86 import activate_tools

    activate_tools()
    spec = importlib.util.spec_from_file_location(
        "linux_shared_vm_generator", source / "tools/x86/common/codegen/generate-register.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    layout = json.loads(layout_path.read_text())
    cet = layout["compiler_features"]["cet"]
    native_c_invoke = a.sysv_bridges and a.shared_entry
    global_enabled = native_c_invoke and not a.disable_global_bindings

    def render(stream):
        # Reuse the accepted stack kernel, while keeping existing worker
        # placement independent of this optional noncalling continuation.
        stack_insert_blocks = []
        if native_c_invoke:
            rows = stream["short_code"]
            first = rows.index("interp_insert3:")
            kernel = rows[first + 1 :]
            if kernel[:2] != [
                "test BYTE PTR [rip+JS_FrameSlowDirectData], 32",
                "jnz interp_slow",
            ] or kernel[-2:] != ["movzx eax, BYTE PTR [r12]", "jmp QWORD PTR [rdi+rax*8]"]:
                raise ValueError("Review shared native insert3 kernel")
            stream["short_code"] = rows[:first]
            kernel = [
                row.replace("interp_insert3_copy", "linux_stack_insert_copy") for row in kernel
            ]
            kernel[1] = "jnz linux_stack_insert_fallback"
            kernel += [
                "linux_stack_insert_fallback:",
                "lea rax, [rip+JS_FramePublishDirtyTable]",
                "cmp rdi, rax",
                "je dirty_interp_slow",
                "jmp interp_slow",
            ]
            stack_insert_blocks = [("JS_LinuxStackInsert", kernel)]
            stream["handlers"]["insert3"] = "JS_LinuxStackInsert"
        root = "qjs_linux_vm_enter_private"
        if native_c_invoke:
            text = "\n".join(stream["code"])
            original = "call JS_FrameInterpHostDispatch\ntest eax, eax\njnz interp_host_exception\nmovdqu xmm0, XMMWORD PTR [rbx+40]"
            if text.count(original) != 1:
                raise ValueError("Review the shared host result ownership continuation")
            stream["code"] = text.replace(original, original.rsplit("\n", 1)[0], 1).splitlines()
            text = "\n".join(stream["code"])
            old = "call JS_FrameInterpSlow\ntest eax, eax\njz interp_reload"
            if text.count(old) != 1:
                raise ValueError("Review native-window lifetime at the slow/new-frame transition")
            stream["code"] = text.replace(
                old,
                "call JS_FrameInterpSlow\nmov QWORD PTR [rbx+96], 0\ntest eax, eax\njz interp_reload",
                1,
            ).splitlines()
        js_call_blocks, js_call_globals, js_call_contract = [], [], None
        if a.sysv_bridges:
            from js_calls import append as append_js_calls

            js_call_blocks, js_call_globals, js_call_contract = append_js_calls(
                source, stream, layout
            )
        forward_blocks, forward_leaves, forward_globals, forward_contract = [], [], [], None
        if a.sysv_bridges:
            from forwarding import append as append_forwarding

            forward_blocks, forward_leaves, forward_globals, forward_contract = append_forwarding(
                source, stream, layout
            )
        construct_blocks, construct_contract = [], None
        if a.sysv_bridges and a.shared_entry:
            from constructors import append as append_constructors

            construct_blocks, construct_contract = append_constructors(
                source, stream, layout, forward_blocks
            )
        leaf_blocks, leaf_globals, leaf_contract = [], [], None
        if a.sysv_bridges:
            from vm_leaves import append as append_vm_leaves

            leaf_blocks, leaf_globals, leaf_contract = append_vm_leaves(
                source, output, stream, layout, a.property_ic
            )
        native_entries = None
        if a.sysv_bridges and a.shared_entry:
            from native_entries import generate as generate_native_entries

            ids = {name: index for index, name in enumerate(stream["opcodes"])}
            native_entries = generate_native_entries(source, output, layout, ids)
        blocks = (
            [
                ("JS_FrameInterpPropertyCold", stream["cold_code"]),
                ("JS_FrameInterpShortBig", stream["short_code"]),
                ("JS_FrameInterpCallMeta", stream["call_code"]),
                ("JS_FrameInterpPrimitiveEq", stream["eq_code"]),
            ]
            + js_call_blocks
            + forward_blocks
            + construct_blocks
            + leaf_blocks
        )
        handlers = dict(stream["handlers"])
        string_blocks, string_globals, string_contract = [], [], None
        if a.sysv_bridges:
            from string_vm import append as append_strings

            string_blocks, string_globals, string_contract = append_strings(source, stream, layout)
            blocks += string_blocks
        array_blocks, array_globals, array_contract = [], [], None
        if a.sysv_bridges:
            from array_vm import append as append_arrays

            array_blocks, array_globals, array_contract = append_arrays(source, stream, layout)
            blocks += array_blocks
        native_admission = a.sysv_bridges
        if native_admission:
            from admission import vm_block

            blocks.append(("JS_FrameLinuxRegExpOpcode", vm_block()))
            handlers["regexp"] = "JS_FrameLinuxRegExpOpcode"
            blocks.append(
                (
                    "JS_FrameLinuxSetNameOpcode",
                    [
                        s.replace("JS_FrameInterpRegExp", "JS_FrameLinuxSetNameStep")
                        for s in vm_block()
                    ],
                )
            )
            handlers["set_name"] = "JS_FrameLinuxSetNameOpcode"
        global_vm = []
        if a.property_ic and a.sysv_bridges and not global_enabled:
            from x86.common.codegen.property_ic_native import global_cell_probe

            for opcode in ("get_var", "get_var_undef"):
                name = "JS_FrameLinuxGlobal_" + opcode
                rows = global_cell_probe(
                    layout,
                    "linux_global_" + opcode,
                    "interp_" + opcode + "_ready",
                    "interp_slow",
                    measured_tail=True,
                )
                blocks.append((name, rows + ["jmp interp_" + opcode]))
                handlers[opcode] = name
                global_vm.append(name)
        ic_contracts = []
        if a.property_ic:
            if not layout["property_ic"]:
                raise ValueError("Native IC requires the actual property-IC core overlay")
            from x86.common.codegen.property_ic_native import blocks as property_blocks

            generation = dict(aliases=["M"], msvc=False, diagnostics=False)
            extra, _, _, ic_contracts = property_blocks(None, layout, generation)
            blocks += extra
            for kind, name in enumerate(("get_field", "get_field2", "put_field"), 1):
                handlers[name] = "JS_FrameOwnBytecodeM" + str(kind)
        argument_blocks, argument_contract = [], None
        if native_c_invoke:
            from arguments import append as append_arguments

            argument_blocks, argument_contract = append_arguments(
                source, output, stream, blocks, handlers, forward_leaves, layout
            )
            blocks += argument_blocks
        null_blocks, null_contract = [], None
        if native_c_invoke:
            from null_proto import append as append_null_proto

            null_blocks, null_contract = append_null_proto(source, output, blocks, layout)
            blocks += null_blocks
        iterator_contract = None
        if native_c_invoke:
            from iterators import append as append_iterators

            iterator_blocks, iterator_contract = append_iterators(source, output, stream, handlers)
            blocks += iterator_blocks
        varargs_contract = None
        if native_c_invoke:
            from varargs_native import append as append_varargs

            varargs_blocks, varargs_contract = append_varargs(
                source, output, stream, handlers, layout
            )
            blocks += varargs_blocks
        literal_contract = None
        if native_c_invoke:
            from literal_shapes import append as append_literals

            literal_blocks, literal_contract = append_literals(
                source, output, stream, blocks, handlers, layout, leaf_contract
            )
            blocks += literal_blocks
        indexed_contract = None
        if native_c_invoke:
            from indexed_ops import append as append_indexed

            indexed_blocks, indexed_contract = append_indexed(
                source, output, stream, handlers, layout
            )
            blocks += indexed_blocks
        property_contract = None
        property_globals = []
        property_blocks_ = []
        if native_c_invoke and a.property_ic:
            from property_family import append as append_properties

            property_blocks_, property_globals, property_contract = append_properties(
                source,
                output,
                stream,
                blocks,
                handlers,
                forward_leaves,
                layout,
                shared_global=global_enabled,
            )
            blocks += property_blocks_
        comparison_contract = None
        comparison_blocks = []
        if native_c_invoke:
            from comparisons import append as append_comparisons

            comparison_blocks, comparison_contract = append_comparisons(
                source, output, stream, blocks, layout
            )
            blocks += comparison_blocks
        numeric_blocks, numeric_contract = [], None
        if native_c_invoke:
            from numeric import append as append_numeric

            numeric_blocks, numeric_contract = append_numeric(
                source, output, stream, blocks, layout
            )
            blocks += numeric_blocks
        global_blocks, global_contract = [], None
        if global_enabled:
            from global_bindings import append as append_global_bindings

            global_blocks, global_contract = append_global_bindings(
                source, output, stream, handlers, layout
            )
        slot_blocks, slot_contract = [], None
        if native_c_invoke:
            from slot_store import append as append_slots

            slot_blocks, slot_contract = append_slots(source, stream, layout)
            blocks += slot_blocks
        hybrid_blocks, hybrid_leaves = [], []
        extra_fast_blocks = []
        if native_c_invoke:
            hybrid_blocks, hybrid_leaves = apply_hybrid_gc_native(stream, handlers, layout)
            blocks += hybrid_blocks
            forward_leaves += hybrid_leaves
            extra_fast_blocks = apply_regression_fast_paths(stream, handlers, layout, slot_blocks)
        publication = None
        publish_blocks, publish_proxies = [], []
        if native_c_invoke:
            from publication import generate as generate_publication

            publish_blocks, publish_proxies, publication = generate_publication(
                source,
                output,
                stream,
                blocks,
                handlers,
                forward_leaves,
                layout,
                dirty_stats_banks=comparison_contract["dirty_stats_banks"]
                if comparison_contract
                else None,
                shared_blocks=global_blocks + stack_insert_blocks + extra_fast_blocks,
            )
            blocks += publish_blocks
        blocks += global_blocks + stack_insert_blocks + extra_fast_blocks
        returning = forward_leaves + publish_proxies
        defined = {
            "JS_FrameInterp",
            "JS_FrameInterpHostDispatch",
            *(["js_hybrid_drop_string1"] if hybrid_leaves else []),
            *(name for name, _ in blocks + returning),
        }
        for rows in [stream["code"], *(rows for _, rows in blocks + returning)]:
            defined.update(m[1] for row in rows if (m := re.match(r"^(\w+):", row)))
        helpers = set()
        for rows in [stream["code"], *(rows for _, rows in blocks + returning)]:
            for row in rows:
                match = re.fullmatch(r"(?:call|jmp|j\w+) (\w+)", row)
                if match and match[1] not in defined:
                    helpers.add(match[1])
        helpers.update(("JS_FrameInterpHostDirect", "JS_FrameInterpHost"))
        if native_c_invoke:
            helpers.add("JS_LinuxCInvokeInit")
        if any(not name.startswith("JS_") for name in helpers):
            raise ValueError(
                "Unresolved VM labels must never be treated as C helpers: " + repr(sorted(helpers))
            )
        mapping = {name: "qjs_linux_bridge_" + name for name in helpers}
        mapping["JS_FrameInterp"] = root
        mapping["JS_FrameInterpHostDispatch"] = "qjs_linux_vm_host_dispatch_private"
        pattern = re.compile(
            r"\b(?:" + "|".join(map(re.escape, sorted(mapping, key=len, reverse=True))) + r")\b"
        )

        def rewrite(row):
            return pattern.sub(lambda m: mapping[m[0]], row)

        destinations = {
            handlers.get(stream["opcodes"][i], "interp_slow")
            if i < len(stream["opcodes"])
            else "interp_slow"
            for i in range(256)
        }
        if publication:
            destinations.update(
                publication["clean_destinations"] + publication["dirty_destinations"]
            )
        if not destinations <= defined:
            raise ValueError("Undefined indirect dispatch destination")

        def body(rows, allow_slot_getenv=False):
            result = []
            for row in rows:
                if (
                    row.startswith(("jmp ", "call "))
                    and not re.fullmatch(r"(?:jmp|call) \w+", row)
                    and not (allow_slot_getenv and row == "call getenv@PLT")
                    and row not in ("jmp QWORD PTR [rdi+rax*8]", "jmp QWORD PTR [rdi+rcx*8]")
                ):
                    raise ValueError("Review new indirect VM transfer before CET admission: " + row)
                result.append(rewrite(row))
                if cet & 1 and row.endswith(":") and row[:-1] in destinations:
                    result.append("endbr64")
            return result

        lines = [
            "/* Generated real Linux ELF; development VM foundation. */",
            ".intel_syntax noprefix",
            '.section .text.qjs_linux_vm,"ax",@progbits',
            ".p2align 6" if hybrid_blocks else ".p2align 4",
            *([".fill 16, 1, 0x90"] if hybrid_blocks else []),
            ".globl " + root,
            ".hidden " + root,
            ".type " + root + ",@function",
            root + ":",
            ".cfi_startproc",
            "endbr64",
        ]
        cfa = 8
        for reg in stream["saved_registers"]:
            lines += ["push " + reg, ".cfi_adjust_cfa_offset 8"]
            cfa += 8
            lines += [".cfi_offset " + reg + ", -" + str(cfa)]
        if native_c_invoke:
            # The inherited stream owns scratch32..63. The canonical anchor
            # leases0..23 and the TLS cache leases64..71; check operand widths
            # as well as their starts, and reject unreviewed dynamic addressing.
            for rows in [stream["code"], *(rows for _, rows in blocks)]:
                for row in rows:
                    # Shared compound quota guard computes a lower address;
                    # LEA neither accesses scratch nor aliases the TLS anchor.
                    if row == "lea r11, [rsp-272]":
                        continue
                    # Exact16byte old-value lease32..47 is consumed by the
                    # existing typed free helper;it cannot alias anchor/TLS.
                    if row == "lea r8, [rsp+32]":
                        continue
                    for operand in re.finditer(r"\[[^\]]*\brsp\b[^\]]*\]", row):
                        memory = re.fullmatch(r"\[rsp\+(\d+)\]", operand[0])
                        width = re.search(
                            r"\b(XMMWORD|QWORD|DWORD|WORD|BYTE) PTR $", row[: operand.start()]
                        )
                        if not memory or not width:
                            raise ValueError("Review new VM stack addressing: " + row)
                        start = int(memory[1])
                        size = dict(XMMWORD=16, QWORD=8, DWORD=4, WORD=2, BYTE=1)[width[1]]
                        if not 32 <= start < start + size <= 64:
                            raise ValueError(
                                "Shared VM overlaps native C activation scratch: " + row
                            )
        lines += ["sub rsp, 72", ".cfi_adjust_cfa_offset 72"]
        if native_c_invoke:
            lines += ["mov QWORD PTR [rsp+64], 0"]
        lines += ["mov rbx, " + ("rdi" if a.sysv_bridges else "rcx")]
        if native_c_invoke:
            lines += ["mov QWORD PTR [rbx+96], 0"]
        lines += ["jmp " + publication["entry"]] if publication else ["lea rdi, [rip+interp_table]"]
        lines += body(stream["code"])
        if native_c_invoke:
            lines += [
                "mov r10, QWORD PTR [rsp+64]",
                "cmp r10, 1",
                "jbe qjs_linux_scope_restored",
                "mov r11, QWORD PTR [rsp]",
                "mov QWORD PTR [r10], r11",
                "qjs_linux_scope_restored:",
            ]
        lines += ["add rsp, 72", ".cfi_adjust_cfa_offset -72"]
        for reg in reversed(stream["saved_registers"]):
            lines += ["pop " + reg, ".cfi_restore " + reg, ".cfi_adjust_cfa_offset -8"]
        lines += ["ret", ".cfi_endproc", ".size " + root + ", .-" + root]
        # Cold blocks are JMP continuations inside the live VM activation.
        # Each FDE describes that same CFA and saved-register state.
        for name, rows in blocks:
            section = (
                ".qjs_linux_slots"
                if name in ("JS_LinuxSlotCold", "dirty_JS_LinuxSlotCold")
                else (
                    ".qjs_linux_stack" if name == "JS_LinuxStackInsert" else ".text.qjs_linux_cold"
                )
            )
            lines += [
                ".section " + section + ',"ax",@progbits',
                ".p2align 4",
                ".hidden " + name,
                ".type " + name + ",@function",
                name + ":",
                ".cfi_startproc simple",
                ".cfi_def_cfa rsp, 144",
                ".cfi_offset rip, -8",
            ]
            offset = 16
            for reg in stream["saved_registers"]:
                lines += [".cfi_offset " + reg + ", -" + str(offset)]
                offset += 8
            if cet & 1 and name in destinations:
                lines += ["endbr64"]
            lines += body(
                rows, allow_slot_getenv=name in ("JS_LinuxSlotCold", "dirty_JS_LinuxSlotCold")
            )
            lines += [".cfi_endproc", ".size " + name + ", .-" + name]
        # Returning probes have a real CALL return address and their own32-byte
        # incoming scratch reservation in ForwardEnter. Cold JMP continuations
        # above retain the live VM CFA; these leaf functions use ordinary CFA8.
        for name, rows in returning:
            section = (
                ".text.qjs_linux_publish_proxy"
                if name in {n for n, _ in publish_proxies}
                else ".text.qjs_linux_forward"
            )
            lines += [
                ".section " + section + ',"ax",@progbits',
                ".p2align 4",
                ".hidden " + name,
                ".type " + name + ",@function",
                name + ":",
                ".cfi_startproc",
                "endbr64",
                *body(rows),
                ".cfi_endproc",
                ".size " + name + ", .-" + name,
            ]
        host = mapping["JS_FrameInterpHostDispatch"]
        lines += [
            '.section .text.qjs_linux_host,"ax",@progbits',
            ".p2align 4",
            ".hidden " + host,
            ".type " + host + ",@function",
            host + ":",
            ".cfi_startproc",
            "cmp BYTE PTR [rcx+161], 0",
            "je qjs_linux_host_legacy",
            "cmp QWORD PTR [rdx-8], -1",
            "jne qjs_linux_host_legacy",
            "mov rax, QWORD PTR [rdx-16]",
            "cmp WORD PTR [rax+" + str(layout["offsets"]["JSObject.class_id"]) + "], 12",
            "jne qjs_linux_host_legacy",
            "cmp BYTE PTR [rax+" + str(layout["offsets"]["JSObject.u.cfunc.cproto"]) + "], 1",
            *(
                [
                    "jbe qjs_linux_host_c_ready",
                    "cmp BYTE PTR [rax+"
                    + str(layout["offsets"]["JSObject.u.cfunc.cproto"])
                    + "], 6",
                    "je qjs_linux_host_c_ready",
                    "cmp BYTE PTR [rax+"
                    + str(layout["offsets"]["JSObject.u.cfunc.cproto"])
                    + "], 7",
                    "jne qjs_linux_host_legacy",
                    "qjs_linux_host_c_ready:",
                ]
                if native_c_invoke
                else ["ja qjs_linux_host_legacy"]
            ),
            "jmp "
            + (
                "qjs_linux_c_invoke_private"
                if native_c_invoke
                else mapping["JS_FrameInterpHostDirect"]
            ),
            "qjs_linux_host_legacy:",
            "jmp " + mapping["JS_FrameInterpHost"],
            ".cfi_endproc",
            ".size " + host + ", .-" + host,
            '.section .data.rel.ro.local.qjs_linux_dispatch,"aw",@progbits',
            ".p2align 3",
            "interp_table:",
        ]
        for index in range(256):
            dest = (
                handlers.get(stream["opcodes"][index], "interp_slow")
                if index < len(stream["opcodes"])
                else "interp_slow"
            )
            lines += [".quad " + rewrite(dest)]
        lines += [".quad 0, 3"]
        if publication:
            for name, targets in (
                (publication["clean_table"], publication["clean_destinations"]),
                (publication["dirty_table"], publication["dirty_destinations"]),
            ):
                lines += [
                    '.section .data.rel.ro.local.qjs_linux_publish,"aw",@progbits',
                    ".p2align 3",
                    ".hidden " + name,
                    ".type " + name + ",@object",
                    name + ":",
                ]
                lines += [".quad " + rewrite(target) for target in targets]
                lines += [".quad 0, 3", ".size " + name + ",.-" + name]
        if native_c_invoke:
            from c_invoke import render as render_c_invoke

            lines += render_c_invoke(source, layout, mapping)
        if comparison_contract:
            from comparisons import render_native as render_comparison_native

            lines += render_comparison_native(source, layout)
        if numeric_contract:
            from numeric import render_native as render_numeric_native

            lines += render_numeric_native(source, layout)
        if indexed_contract:
            from indexed_ops import render_native as render_indexed_native

            lines += render_indexed_native(source, layout)
        if global_contract:
            from global_bindings import render_native as render_global_bindings

            lines += render_global_bindings()
        if indexed_contract and literal_contract and iterator_contract:
            from indexed_ops import render_slow_selector

            lines += render_slow_selector(
                {name: index for index, name in enumerate(stream["opcodes"])}
            )
            indexed_contract["unified_slow_selector"] = dict(
                entry="JS_LinuxUnifiedSlowSelect",
                mode_owner="JS_FrameSlowDirectData",
                disabled_or_observed="original selector",
                target="complete JS_FrameVarargsSlow",
                frame_growth=0,
                state_growth=0,
            )
            (output / "INDEXED-VM.json").write_text(json.dumps(indexed_contract, indent=2) + "\n")
        if slot_contract:
            from slot_store import readonly as slot_readonly

            lines += slot_readonly()
        lines += [*property_note(cet), '.section .note.GNU-stack,"",@progbits']
        for target in sorted(mapping.values()):
            if target.startswith("qjs_linux_bridge_"):
                lines.insert(2, ".hidden " + target)
        for target in (
            string_globals
            + array_globals
            + js_call_globals
            + forward_globals
            + leaf_globals
            + property_globals
            + (["JS_FramePublishControl"] if publication else [])
            + (
                [
                    "JS_FrameArgumentsMode",
                    "JS_FrameArgumentsStats",
                    "JS_FrameArgumentsAccessStats",
                    "JS_FrameArgumentsForwardStats",
                    "JS_LinuxArgumentsLengthControl",
                ]
                if argument_contract
                else []
            )
            + (
                ["qjs_linux_core_js_function_apply", "JS_FrameApplyForwardStats"]
                if varargs_contract
                else []
            )
            + (
                ["JS_FrameOrdinaryLiteralMode", "JS_FrameOrdinaryLiteralStats"]
                if literal_contract
                else []
            )
            + (["JS_FrameSlowDirectData"] if indexed_contract else [])
            + (["js_hybrid_drop_string1"] if hybrid_leaves else [])
        ):
            lines.insert(2, ".hidden " + target)
        for target in comparison_contract["globals"] if comparison_contract else []:
            lines.insert(2, ".hidden " + target)
        text = "\n".join(lines) + "\n"
        (output / "quickjs-linux-vm.S").write_text(text)
        record = dict(
            status="generated-development-ELF-VM-instruction-stream",
            handlers=len(handlers),
            helpers=sorted(helpers),
            helper_mapping={n: mapping[n] for n in sorted(helpers)},
            private_entry=root,
            layout_sha256=hashlib.sha256(layout_path.read_bytes()).hexdigest(),
            entry_protocol="SysV" if a.sysv_bridges else "development-ms-abi",
            shared_entry=a.shared_entry,
            compiler_cet=cet,
            native_c_invoke=native_c_invoke,
            host_result_protocol="XMM0 with exception spill" if native_c_invoke else "state-result",
            native_c_scope="activation-owned blocked anchor; coherent only inside checked C calls"
            if native_c_invoke
            else None,
            extra_native_functions=[
                "qjs_linux_c_invoke_private",
                "qjs_linux_numeric_invoke_private",
                "qjs_linux_dense_pop_private",
                "qjs_linux_builtin_prepare_private",
                "qjs_linux_builtin_window_private",
                "qjs_linux_builtin_stack_private",
            ]
            + [name for name, _ in publish_proxies]
            + ([comparison_contract["sysv_leaf"]] if comparison_contract else [])
            + (["JS_FrameBigIntRelease"] if numeric_contract else [])
            + (["JS_LinuxFastArrayOwnGet"] if indexed_contract else [])
            if native_c_invoke
            else [],
            native_builtin_view=dict(
                bytes=128,
                window_owner=96,
                window_marker=63,
                modes=[
                    "lifetime-window",
                    "disabled",
                    "C-stack",
                    "transient-arena",
                    "geometry-recheck",
                ],
                publication="typed SF/TLS/coherent anchor; charged window/transient ownership",
                private_nonvolatile_resaves=0,
            )
            if native_c_invoke
            else None,
            native_admission=native_admission,
            native_strings=a.sysv_bridges,
            string_contract=string_contract,
            native_arrays=a.sysv_bridges,
            array_contract=array_contract,
            native_js_calls=a.sysv_bridges,
            js_call_contract=js_call_contract,
            native_forwarding=a.sysv_bridges,
            forwarding_contract=forward_contract,
            native_entries=native_entries,
            native_vm_leaves=leaf_contract,
            native_construct=construct_contract,
            native_publication=publication,
            native_arguments=argument_contract,
            native_null_proto=null_contract,
            native_iterators=iterator_contract,
            native_varargs=varargs_contract,
            native_literals=literal_contract,
            native_indexed=indexed_contract,
            native_properties=property_contract,
            native_comparisons=comparison_contract,
            native_stack_insert=dict(
                function="JS_LinuxStackInsert",
                section=".qjs_linux_stack",
                shared_publication_token=True,
                fallback="incoming Clean/Dirty C owner",
                frame_growth=0,
                state_growth=0,
            )
            if native_c_invoke
            else None,
            native_slots=slot_contract,
            native_numeric=numeric_contract,
            native_global_bindings=global_contract,
            returning_forward_functions=[name for name, _ in forward_leaves],
            native_global_cells=dict(
                bytecode_ic=layout["offsets"]["JSFunctionBytecode.property_ic"],
                runtime_mode=layout["offsets"]["JSRuntime.property_ic_mode"],
                map=layout["offsets"]["JSPropertyIC.map"],
            )
            if a.property_ic and a.sysv_bridges
            else None,
            extra_vm_functions=(
                ["JS_FrameLinuxRegExpOpcode", "JS_FrameLinuxSetNameOpcode"]
                if native_admission
                else []
            )
            + global_vm
            + [
                name
                for name, _ in string_blocks
                + array_blocks
                + js_call_blocks
                + forward_blocks
                + construct_blocks
                + leaf_blocks
                + argument_blocks
                + null_blocks
                + property_blocks_
                + comparison_blocks
                + numeric_blocks
                + publish_blocks
                + global_blocks
                + stack_insert_blocks
                + extra_fast_blocks
                + slot_blocks
                + hybrid_blocks
            ],
            direct_only_vm_functions=[
                name
                for name, _ in string_blocks
                + array_blocks
                + js_call_blocks
                + forward_blocks
                + construct_blocks
                + leaf_blocks
                + argument_blocks
                + null_blocks
                + property_blocks_
                + comparison_blocks
                + numeric_blocks
                + publish_blocks
                + global_blocks
                + stack_insert_blocks
                + extra_fast_blocks
                + slot_blocks
                + hybrid_blocks
                if name not in destinations
            ],
            indirect_destinations=sorted(rewrite(name) for name in destinations),
            helper_protocol="audited-sysv-assembly" if a.sysv_bridges else "typed-ms-abi-C",
            property_ic=a.property_ic,
            property_ic_contracts=ic_contracts,
            numeric_compare=a.numeric_compare,
            assembly_sha256=hashlib.sha256(text.encode()).hexdigest(),
            scope="Register VM development stage, supplements not ported; private bridges still need compilation and runtime proof",
        )
        (output / "VM.json").write_text(json.dumps(record, indent=2) + "\n")
        print(
            "LINUX ELF VM STREAM", record["handlers"], "handlers;", len(helpers), "C bridge targets"
        )

    module.generate(
        source,
        output,
        internal_entry=True,
        foundation_only=True,
        layout_override=layout,
        instruction_stream=render,
        numeric_compare=a.numeric_compare,
        linux_borrowed_field=a.property_ic and a.sysv_bridges and a.shared_entry,
        linux_stack_insert=native_c_invoke,
        linux_reference_stores=native_c_invoke,
    )


if __name__ == "__main__":
    main()
