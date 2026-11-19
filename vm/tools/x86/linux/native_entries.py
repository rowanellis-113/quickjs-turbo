"""Actual SysV root/child entries and shared frame-free native call leaves.

The leaf algorithms come from the accepted shared factories. Linux gives their
noncalling private scratch a bounded red zone and returns JSValue in RAX/RDX.
Activation constructors use the measured Linux types and compiler-owned TLS.
"""

import hashlib
import json
import re
from c_workers import module
from control_flow import property_note


def generate(source, output, layout, ids):
    f, bits = layout["offsets"], layout["bits"]
    if layout["reference_count_model"] != "inline-header" or f["JSGCObjectHeader.ref_count"] != 0:
        raise ValueError("Review entry value/reference ABI")
    if layout["sizes"]["JSStackFrame"] != 72 or bits["JSShapeProperty.flags"] != [[3, 4]]:
        raise ValueError("Review entry frame/own-property ABI")
    rt = f["JSRuntime.current_stack_frame"]
    code = f["JSFunctionBytecode.byte_code_buf"]
    bc = f["JSObject.u.func.function_bytecode"]
    ctxrt = f["JSContext.rt"]
    interrupt = f["JSContext.interrupt_counter"]
    limit = f["JSRuntime.stack_limit"]
    top = f["JSRuntime.stack_top"]
    loader = f["JSRuntime.module_loader_has_attr"]
    strict = bits["JSFunctionBytecode.is_strict_mode"][0][0]
    dump, dump_mask = bits["JSRuntime.dump_flags"][0]
    assert dump_mask == 1
    asm = ["/* Actual SysV entry/return; source-owned Linux ELF. */", ".intel_syntax noprefix"]
    functions = []

    def emit(name, rows):
        functions.append(name)
        asm.extend(
            [
                '.section .text.qjs_linux_entry,"ax",@progbits',
                ".p2align 4",
                ".globl " + name,
                *([] if name == "JS_Call" else [".hidden " + name]),
                ".type " + name + ",@function",
                name + ":",
                ".cfi_startproc",
                "endbr64",
                *rows,
                ".cfi_endproc",
                ".size " + name + ",.-" + name,
            ]
        )

    def preserve_call(target):
        rows = ["sub rsp, 56", ".cfi_adjust_cfa_offset 56"]
        for i, reg in enumerate(("rdi", "rsi", "rdx", "rcx", "r8", "r9")):
            rows += [f"mov QWORD PTR [rsp+{8 * i}], {reg}"]
        rows += ["call " + target]
        for i, reg in enumerate(("rdi", "rsi", "rdx", "rcx", "r8", "r9")):
            rows += [f"mov {reg}, QWORD PTR [rsp+{8 * i}]"]
        return rows + ["add rsp, 56", ".cfi_adjust_cfa_offset -56"]

    # No frame is reserved on ordinary warm rejection. The exact original
    # aggregate ABI, including spilled new_target/argv/flags, reaches C.
    dispatch = [
        f"mov rax, QWORD PTR [rdi+{ctxrt}]",
        "test DWORD PTR [rsp+32], -3",
        "jnz JS_FrameCallEntryShared",
        "cmp r9d, 65535",
        "ja JS_FrameCallEntryShared",
        f"cmp BYTE PTR [rax+{rt - 1}], 1",
        "jne JS_FrameCallEntryShared",
        f"cmp BYTE PTR [rax+{rt - 3}], 1",
        "jne JS_FrameCallEntryShared",
        f"test BYTE PTR [rax+{dump}], 128",
        "jnz JS_FrameCallEntryShared",
        "cmp rdx, -1",
        "jne JS_FrameCallEntryShared",
        f"cmp WORD PTR [rsi+{f['JSObject.class_id']}], 13",
        "jne JS_FrameCallEntryShared",
        f"mov r10, QWORD PTR [rsi+{bc}]",
        f"test BYTE PTR [r10+{code - 1}], 1",
        "jz JS_FrameCallEntryShared",
        "cmp BYTE PTR [rip+JS_LinuxEntryReady], 1",
        "jne linux_entry_config",
        f"cmp BYTE PTR [rax+{loader + 1}], 0",
        "je linux_entry_config",
        f"test BYTE PTR [rax+{rt - 5}], 4",
        "jnz JS_LinuxNativeChildSelect",
        "jmp JS_LinuxRootLeaf",
        "linux_entry_config:",
        "lea r11, [rsp-4096]",
        f"cmp r11, QWORD PTR [rax+{limit}]",
        "jb JS_FrameCallEntryShared",
        *preserve_call("JS_LinuxEntryInit"),
        "jmp JS_FrameCallEntryDispatch",
    ]
    emit("JS_FrameCallEntryDispatch", dispatch)

    # A public root has a different real stack layout. Retain the C selector
    # for cold/disabled/nested calls; admitted roots never manufacture a Win
    # hidden return pointer or shadow space.
    public = [
        f"mov rax, QWORD PTR [rdi+{ctxrt}]",
        "cmp r9d, 3",
        "ja JS_LinuxCallPublicFallback",
        "cmp rdx, -1",
        "jne JS_LinuxCallPublicFallback",
        f"cmp WORD PTR [rsi+{f['JSObject.class_id']}], 13",
        "jne JS_LinuxCallPublicFallback",
        f"mov r10, QWORD PTR [rsi+{bc}]",
        f"test BYTE PTR [r10+{code - 1}], 1",
        "jz JS_LinuxCallPublicFallback",
        f"test BYTE PTR [r10+{code - 1}], 4",
        "jnz JS_LinuxCallPublicFallback",
        f"cmp DWORD PTR [r10+{f['JSFunctionBytecode.byte_code_len']}], 4",
        "jbe JS_LinuxCallPublicFallback",
        f"cmp WORD PTR [r10+{f['JSFunctionBytecode.var_count']}], 0",
        "jne JS_LinuxCallPublicFallback",
        f"cmp WORD PTR [r10+{f['JSFunctionBytecode.var_ref_count']}], 0",
        "jne JS_LinuxCallPublicFallback",
        f"movzx r11d, WORD PTR [r10+{f['JSFunctionBytecode.arg_count']}]",
        "cmp r11d, r9d",
        "jne JS_LinuxCallPublicFallback",
        f"cmp WORD PTR [r10+{f['JSFunctionBytecode.stack_size']}], 237",
        "ja JS_LinuxCallPublicFallback",
        f"cmp QWORD PTR [rax+{rt}], 0",
        "jne JS_LinuxCallPublicFallback",
        f"test BYTE PTR [rax+{rt - 5}], 4",
        "jnz JS_LinuxCallPublicFallback",
        f"cmp BYTE PTR [rax+{rt - 1}], 1",
        "jne JS_LinuxCallPublicFallback",
        f"cmp BYTE PTR [rax+{rt - 3}], 1",
        "jne JS_LinuxCallPublicFallback",
        f"test BYTE PTR [rax+{dump}], 128",
        "jnz JS_LinuxCallPublicFallback",
        "cmp BYTE PTR [rip+JS_LinuxEntryReady], 1",
        "jne JS_LinuxCallPublicFallback",
        "cmp BYTE PTR [rip+JS_LinuxRootControl], 1",
        "jne JS_LinuxCallPublicFallback",
        "cmp BYTE PTR [rip+JS_LinuxPublicRootControl], 1",
        "jne JS_LinuxCallPublicFallback",
        "test r9d, r9d",
        "jnz linux_public_nonzero",
        "cmp BYTE PTR [rip+JS_LinuxRootZeroControl], 1",
        "jne JS_LinuxCallPublicFallback",
        "jmp linux_public_controls_ready",
        "linux_public_nonzero:",
        "cmp BYTE PTR [rip+JS_LinuxRootArgsControl], 1",
        "jne JS_LinuxCallPublicFallback",
        "linux_public_controls_ready:",
        "lea r11, [rsp-8320]",
        f"cmp r11, QWORD PTR [rax+{limit}]",
        "jb JS_LinuxCallPublicFallback",
        "jmp JS_LinuxPublicRoot",
    ]
    emit("JS_Call", public)

    root_select = [
        f"mov rax, QWORD PTR [rdi+{ctxrt}]",
        f"mov r10, QWORD PTR [rsi+{bc}]",
        "cmp BYTE PTR [rip+JS_LinuxRootControl], 1",
        "jne JS_FrameCallEntryShared",
        f"cmp DWORD PTR [r10+{f['JSFunctionBytecode.byte_code_len']}], 4",
        "jbe JS_FrameCallEntryShared",
        f"cmp WORD PTR [r10+{f['JSFunctionBytecode.var_ref_count']}], 0",
        "jne JS_FrameCallEntryShared",
        f"cmp WORD PTR [r10+{f['JSFunctionBytecode.var_count']}], 0",
        "jne JS_FrameCallEntryShared",
        "lea r11, [rsp-8192]",
        f"cmp r11, QWORD PTR [rax+{limit}]",
        "jb JS_FrameCallEntryShared",
        "test r9d, r9d",
        "jnz linux_root_args_select",
        f"cmp WORD PTR [r10+{f['JSFunctionBytecode.arg_count']}], 0",
        "jne JS_FrameCallEntryShared",
        f"cmp WORD PTR [r10+{f['JSFunctionBytecode.stack_size']}], 240",
        "ja JS_FrameCallEntryShared",
        "cmp BYTE PTR [rip+JS_LinuxRootZeroControl], 1",
        "jne JS_FrameCallEntryShared",
        "jmp JS_LinuxNativeRootZero",
        "linux_root_args_select:",
        "cmp r9d, 3",
        "ja JS_FrameCallEntryShared",
        f"test BYTE PTR [r10+{code - 1}], 4",
        "jnz JS_FrameCallEntryShared",
        f"movzx r11d, WORD PTR [r10+{f['JSFunctionBytecode.arg_count']}]",
        "cmp r11d, r9d",
        "jne JS_FrameCallEntryShared",
        f"cmp WORD PTR [r10+{f['JSFunctionBytecode.stack_size']}], 237",
        "ja JS_FrameCallEntryShared",
        "cmp BYTE PTR [rip+JS_LinuxRootArgsControl], 1",
        "jne JS_FrameCallEntryShared",
        "jmp JS_LinuxNativeRootArgs",
    ]
    emit("JS_LinuxNativeRootSelect", root_select)

    # Compiler-generated TLS access is isolated behind a real typed call.
    # Only coherent host scopes can lend their cursor; all other anchors keep C.
    child = [
        "cmp BYTE PTR [rip+JS_LinuxChildControl], 1",
        "jne JS_FrameCallEntryShared",
        f"mov rax, QWORD PTR [rdi+{ctxrt}]",
        f"movzx r11d, BYTE PTR [rax+{rt - 5}]",
        "and r11d, 3",
        "cmp r11d, 1",
        "jne JS_FrameCallEntryShared",
        "lea r11, [rsp-4096]",
        f"cmp r11, QWORD PTR [rax+{limit}]",
        "jb JS_FrameCallEntryShared",
        "cmp BYTE PTR [rip+JS_LinuxIntExpressionControl], 0",
        "je JS_LinuxIntExpressionInitChild",
        *preserve_call("JS_LinuxEntrySlot"),
        "mov r11, rax",
        "mov QWORD PTR [rsp-24], r11",
        "mov r10, QWORD PTR [r11]",
        "test r10, r10",
        "jz JS_FrameCallEntryShared",
        "cmp DWORD PTR [r10+16], 0",
        "jne JS_FrameCallEntryShared",
        "mov r10, QWORD PTR [r10+8]",
        f"mov rax, QWORD PTR [rdi+{ctxrt}]",
        "cmp QWORD PTR [r10+56], rax",
        "jne JS_FrameCallEntryShared",
        "mov r11, QWORD PTR [r10+32]",
        "cmp r11, QWORD PTR [r10+64]",
        "jne JS_FrameCallEntryShared",
        "mov QWORD PTR [rsp-40], r10",
        f"mov r10, QWORD PTR [rsi+{bc}]",
        f"test BYTE PTR [r10+{code - 1}], 4",
        "jnz JS_FrameCallEntryShared",
        f"cmp WORD PTR [r10+{f['JSFunctionBytecode.var_ref_count']}], 0",
        "jne JS_FrameCallEntryShared",
        "test DWORD PTR [rsp+32], 2",
        "jz linux_child_borrow_ready",
        f"test BYTE PTR [r10+{code - 1}], 2",
        "jz JS_FrameCallEntryShared",
        "linux_child_borrow_ready:",
        f"movzx r11d, WORD PTR [r10+{f['JSFunctionBytecode.arg_count']}]",
        "cmp r9d, r11d",
        "jl JS_FrameCallEntryShared",
        f"movzx r11d, WORD PTR [r10+{f['JSFunctionBytecode.var_count']}]",
        f"movzx eax, WORD PTR [r10+{f['JSFunctionBytecode.stack_size']}]",
        "add r11d, eax",
        "shl r11d, 4",
        "add r11d, 128",
        "mov QWORD PTR [rsp-32], r11",
        "mov r10, QWORD PTR [rsp-40]",
        "mov r10, QWORD PTR [r10+8]",
        "mov rax, QWORD PTR [r10+8]",
        "sub rax, QWORD PTR [r10+16]",
        "jb JS_FrameCallEntryShared",
        "cmp rax, r11",
        "jb JS_FrameCallEntryShared",
        "mov r10, rsp",
        "sub r10, 4408",
        "sub r10, r11",
        f"mov rax, QWORD PTR [rdi+{ctxrt}]",
        f"cmp r10, QWORD PTR [rax+{limit}]",
        "jb JS_FrameCallEntryShared",
        f"cmp DWORD PTR [rdi+{interrupt}], 1",
        "jle JS_FrameCallEntryShared",
        "jmp JS_LinuxChildLeaf",
    ]
    emit("JS_LinuxNativeChildSelect", child)

    # Reuse the exact shared noncalling algorithms in a SysV leaf red zone.
    # Preserve the original public registers on every miss before tailing C or
    # a constructor. No CALL may appear while these private red-zone views live.
    gas = []
    module(source, "root-leaf").append(["END"], gas, ids)
    module(source, "child-leaf").append(["END"], gas, ids, False)

    def block(name):
        return gas[gas.index(name + ":") + 1 : gas.index(name + "_end:")]

    stack_slots = {8: -72, 16: -40, 24: -64, 32: -32, 48: -88, 56: -80, 64: 32}
    root_leaf = block("JS_FrameRootLeafSelect")
    child_leaf = block("JS_FrameChildLeafFast")
    fields_leaf = block("JS_FrameThisFieldLeaf")
    symbol_leaf = block("JS_FrameSymbolFieldLeaf")
    captured_leaf = block("JS_FrameChildLeafCaptured")
    rename = {
        "JS_FrameCallEntryLegacy": "linux_leaf_root_miss",
        "JS_FrameRootLeafSelect": "JS_LinuxRootLeaf",
        "qjs_frame_core_JS_CallInternal": "linux_leaf_root_miss",
        "JS_FrameChildTrampoline": "linux_leaf_child_miss",
        "JS_FrameRootLeafConfig": "linux_leaf_root_miss",
        "JS_FrameChildLeafConfig": "linux_leaf_child_miss",
        "JS_FrameThisFieldLeaf": "linux_leaf_this_field",
        "JS_FrameSymbolFieldLeaf": "linux_leaf_symbol_field",
        "JS_FrameChildLeafCaptured": "linux_leaf_captured",
    }

    def translate(rows):
        result = []
        for row in rows:
            if row.startswith(("call ", "push ", "pop ", "sub rsp", "add rsp")):
                raise ValueError("Shared leaf acquired a real call/frame: " + row)
            row = re.sub(
                r"\[rsp\+(\d+)\]",
                lambda m: "[rsp"
                + ("+" if stack_slots[int(m[1])] >= 0 else "")
                + str(stack_slots[int(m[1])])
                + "]",
                row,
            )
            for old, new in rename.items():
                row = re.sub(r"\b" + old + r"\b", new, row)
            # Getter control is an actual ELF symbol, not an absolute PE address.
            row = row.replace("[JS_FrameGetterLeafControl]", "[rip+JS_FrameGetterLeafControl]")
            row = row.replace("lea r10, JS_LinuxRootLeaf", "lea r10, [rip+JS_LinuxRootLeaf]")
            if row == "mov rax, rcx":
                result += ["mov rax, QWORD PTR [rsp-56]", "mov rdx, QWORD PTR [rsp-48]"]
            else:
                result.append(row)
        return result

    setup = [
        "mov QWORD PTR [rsp-128], rdi",
        "mov QWORD PTR [rsp-120], rsi",
        "mov QWORD PTR [rsp-112], rdx",
        "mov QWORD PTR [rsp-104], rcx",
        "mov QWORD PTR [rsp-96], r8",
        "mov QWORD PTR [rsp-88], r9",
        "mov rax, QWORD PTR [rsp+24]",
        "mov QWORD PTR [rsp-80], rax",
        f"mov rax, QWORD PTR [rdi+{ctxrt}]",
        "mov QWORD PTR [rsp-72], rax",
        f"mov r11, QWORD PTR [rsi+{bc}]",
        "mov QWORD PTR [rsp-64], r11",
        "lea r8, [rsp-120]",
        "lea r9, [rsp-104]",
        "lea rcx, [rsp-56]",
        "mov rdx, rdi",
    ]
    restore = [
        "mov rdi, QWORD PTR [rsp-128]",
        "mov rsi, QWORD PTR [rsp-120]",
        "mov rdx, QWORD PTR [rsp-112]",
        "mov rcx, QWORD PTR [rsp-104]",
        "mov r8, QWORD PTR [rsp-96]",
        "mov r9, QWORD PTR [rsp-88]",
    ]
    # Both entries have CFA8 throughout and share the same noncalling views.
    leaves = [
        "JS_LinuxChildLeaf:",
        *setup,
        *translate(child_leaf),
        "linux_leaf_captured:",
        *translate(captured_leaf),
        "linux_leaf_this_field:",
        *translate(fields_leaf),
        "linux_leaf_symbol_field:",
        *translate(symbol_leaf),
        "linux_leaf_child_miss:",
        "jmp JS_LinuxIntExpressionLeaf",
        "linux_leaf_child_original_miss:",
        *restore,
        "jmp JS_LinuxNativeChild",
        "linux_leaf_root_miss:",
        *restore,
        "jmp JS_LinuxNativeRootSelect",
    ]
    emit("JS_LinuxRootLeaf", [*setup, *translate(root_leaf), *leaves])

    # One layout is used for zero, equal-arity and direct public activation.
    # The 4096-byte arena, sixteen weak call sites and eight replacement bytes
    # retain the original capacities. SysV returns a value, not a retbuf.
    def root_body(public):
        alloc = 4936
        rows = [
            "sub rsp, 4096",
            ".cfi_adjust_cfa_offset 4096",
            "test BYTE PTR [rsp], 0",
            "sub rsp, 840",
            ".cfi_adjust_cfa_offset 840",
            "mov QWORD PTR [rsp], rdi",
            f"mov rax, QWORD PTR [rdi+{ctxrt}]",
            "mov QWORD PTR [rsp+8], rax",
            f"mov r10, QWORD PTR [rsi+{bc}]",
            "mov QWORD PTR [rsp+16], r10",
            "mov QWORD PTR [rsp+32], rsi",
            "mov QWORD PTR [rsp+40], rdx",
            "mov QWORD PTR [rsp+48], rcx",
            "mov QWORD PTR [rsp+56], r8",
            "mov DWORD PTR [rsp+72], r9d",
            f"mov rax, QWORD PTR [rsp+{alloc + (8 if public else 24)}]",
            "mov QWORD PTR [rsp+64], rax",
        ]
        rows += (
            ["mov DWORD PTR [rsp+76], 2"]
            if public
            else [f"mov eax, DWORD PTR [rsp+{alloc + 32}]", "mov DWORD PTR [rsp+76], eax"]
        )
        p = "linux_public_run" if public else "linux_root_run"
        rows += [
            f"dec DWORD PTR [rdi+{interrupt}]",
            "jg " + p + "_polled",
            "call JS_LinuxEntryPoll",
            "test eax, eax",
            "jnz " + p + "_exception",
            p + "_polled:",
            "mov r10, QWORD PTR [rsp+16]",
            f"movzx r11d, WORD PTR [r10+{f['JSFunctionBytecode.stack_size']}]",
            "test DWORD PTR [rsp+76], 2",
            "jz " + p + "_size",
            f"movzx eax, WORD PTR [r10+{f['JSFunctionBytecode.arg_count']}]",
            "add r11d, eax",
            p + "_size:",
            "shl r11d, 4",
            "add r11d, 128",
            "mov QWORD PTR [rsp+24], r11",
            "mov rax, rsp",
            *(["sub rax, 128"] if public else []),
            "sub rax, r11",
            "mov r9, QWORD PTR [rsp+8]",
            f"cmp rax, QWORD PTR [r9+{limit}]",
            "jb " + p + "_overflow",
            "pxor xmm0, xmm0",
        ]
        for q in range(96, 272, 16):
            rows += [f"movdqu XMMWORD PTR [rsp+{q}], xmm0"]
        rows += ["mov QWORD PTR [rsp+816], 0", "xor eax, eax"]
        for q in range(304, 816, 32):
            rows += [f"mov QWORD PTR [rsp+{q}], rax"]
        # Initialize the whole SF including Linux tail padding before publication.
        for q in range(832, 912, 16):
            rows += [f"movdqu XMMWORD PTR [rsp+{q}], xmm0"]
        rows += [
            f"mov rax, QWORD PTR [r9+{rt}]",
            "mov QWORD PTR [rsp+832], rax",
            "movdqu xmm1, XMMWORD PTR [rsp+32]",
            "movdqu XMMWORD PTR [rsp+840], xmm1",
            "movdqu xmm1, XMMWORD PTR [rsp+48]",
            "movdqu XMMWORD PTR [rsp+920], xmm1",
            "mov QWORD PTR [rsp+912], r10",
            "mov QWORD PTR [rsp+936], 0",
            "mov rdx, QWORD PTR [rsp+64]",
            "mov QWORD PTR [rsp+856], rdx",
            "lea r8, [rsp+960]",
            f"movzx ecx, WORD PTR [r10+{f['JSFunctionBytecode.arg_count']}]",
            "mov WORD PTR [rsp+890], cx",
            "mov DWORD PTR [rsp+956], 0",
            "test DWORD PTR [rsp+76], 2",
            "jz " + p + "_values_ready",
            "test ecx, ecx",
            "jz " + p + "_values_ready",
            "mov WORD PTR [rsp+956], cx",
            "mov QWORD PTR [rsp+856], r8",
            p + "_copy:",
            "movdqu xmm1, XMMWORD PTR [rdx]",
            "movdqu XMMWORD PTR [r8], xmm1",
            "cmp DWORD PTR [rdx+8], -9",
            "jb " + p + "_immediate",
            "mov rax, QWORD PTR [rdx]",
            "inc DWORD PTR [rax]",
            p + "_immediate:",
            "add rdx, 16",
            "add r8, 16",
            "dec ecx",
            "jnz " + p + "_copy",
            p + "_values_ready:",
            "mov QWORD PTR [rsp+864], r8",
            f"mov al, BYTE PTR [r10+{strict}]",
            "and al, 1",
            "mov BYTE PTR [rsp+892], al",
            "mov BYTE PTR [rsp+894], 1",
            "lea rdx, [rsp+272]",
            "mov QWORD PTR [rsp+944], rdx",
            "mov DWORD PTR [rsp+952], r11d",
            "mov QWORD PTR [rdx], 0",
            "mov QWORD PTR [rdx+8], 4096",
            "mov QWORD PTR [rdx+16], r11",
            "lea rax, [rsp+832]",
            "mov QWORD PTR [rdx+24], rax",
            "mov QWORD PTR [rsp+96], rax",
            "mov QWORD PTR [rsp+104], rdx",
            f"mov rdx, QWORD PTR [r10+{code}]",
            "mov QWORD PTR [rsp+112], rdx",
            "mov QWORD PTR [rsp+120], r8",
            "mov QWORD PTR [rsp+128], r11",
            "mov QWORD PTR [rsp+144], 3",
            "mov QWORD PTR [rsp+152], r9",
            "mov QWORD PTR [rsp+160], r11",
            f"add QWORD PTR [r9+{top}], r11",
            f"mov rdx, QWORD PTR [r9+{limit}]",
            "mov QWORD PTR [rsp+168], rdx",
            "test rdx, rdx",
            "jz " + p + "_unlimited",
            "add rdx, r11",
            f"mov QWORD PTR [r9+{limit}], rdx",
            p + "_unlimited:",
            "mov QWORD PTR [rsp+176], rdx",
            "mov rdx, QWORD PTR [rsp]",
            "mov QWORD PTR [rsp+232], rdx",
            "lea rdx, [rsp+304]",
            "mov QWORD PTR [rsp+240], rdx",
            "lea rdx, [rsp+816]",
            "mov QWORD PTR [rsp+248], rdx",
            f"cmp BYTE PTR [r9+{rt - 4}], 1",
            "sete BYTE PTR [rsp+257]",
            f"mov QWORD PTR [r9+{rt}], rax",
            "lea rdi, [rsp+96]",
            "call JS_LinuxLiteralEnter",
            "mov r9, QWORD PTR [rsp+8]",
            "mov r8, QWORD PTR [rsp+128]",
            "sub r8, QWORD PTR [rsp+160]",
            f"add QWORD PTR [r9+{top}], r8",
            f"cmp QWORD PTR [r9+{limit}], 0",
            "je " + p + "_budget_done",
            f"add QWORD PTR [r9+{limit}], r8",
            p + "_budget_done:",
            "mov rsi, QWORD PTR [rsp+272]",
            "test rsi, rsi",
            "jz " + p + "_done",
            p + "_free:",
            "mov rax, QWORD PTR [rsi]",
            "mov QWORD PTR [rsp+80], rax",
            "mov rdi, QWORD PTR [rsp]",
            "call js_free",
            "mov rsi, QWORD PTR [rsp+80]",
            "test rsi, rsi",
            "jnz " + p + "_free",
            p + "_done:",
            "mov rax, QWORD PTR [rsp+136]",
            "mov rdx, QWORD PTR [rsp+144]",
            "jmp " + p + "_return",
            p + "_overflow:",
            "mov rdi, QWORD PTR [rsp]",
            "call JS_LinuxEntryOverflow",
            "jmp " + p + "_return",
            p + "_exception:",
            "xor eax, eax",
            "mov edx, 6",
            p + "_return:",
            "add rsp, 4936",
            ".cfi_adjust_cfa_offset -4936",
            "ret",
        ]
        return rows

    # Equal-arity zero and1..3 share one native constructor, with distinct
    # symbols for actual admission observations and component controls.
    emit("JS_LinuxNativeRootZero", ["jmp JS_LinuxNativeRootArgs"])
    emit("JS_LinuxNativeRootArgs", root_body(False))
    emit("JS_LinuxPublicRoot", root_body(True))

    # Borrowed native child: state/barrier stay on the native stack, JS cells
    # stay in the parent's nonmoving arena, and the original cursor owns growth.
    child_run = [
        "mov r10, QWORD PTR [rsp-40]",
        "mov r11, QWORD PTR [rsp-32]",
        "mov rax, QWORD PTR [rsp-24]",
        "sub rsp, 312",
        ".cfi_adjust_cfa_offset 312",
        "mov QWORD PTR [rsp], rdi",
        f"mov r9, QWORD PTR [rdi+{ctxrt}]",
        "mov QWORD PTR [rsp+8], r9",
        "mov QWORD PTR [rsp+24], r11",
        "mov QWORD PTR [rsp+32], rsi",
        "mov QWORD PTR [rsp+40], rdx",
        "mov QWORD PTR [rsp+48], rcx",
        "mov QWORD PTR [rsp+56], r8",
        "mov QWORD PTR [rsp+80], r10",
        "mov QWORD PTR [rsp+88], rax",
        "mov rax, QWORD PTR [rsp+336]",
        "mov QWORD PTR [rsp+64], rax",
        "mov DWORD PTR [rsp+72], r9d",  # overwritten below from actual saved input
        f"mov rax, QWORD PTR [rsi+{bc}]",
        "mov QWORD PTR [rsp+16], rax",
        "pxor xmm0, xmm0",
    ]
    # Preserve incoming R9d before loading runtime into R9 above.
    child_run.insert(child_run.index("sub rsp, 312"), "movd xmm4, r9d")
    child_run[child_run.index("mov DWORD PTR [rsp+72], r9d")] = "movd DWORD PTR [rsp+72], xmm4"
    for q in range(96, 272, 16):
        child_run += [f"movdqu XMMWORD PTR [rsp+{q}], xmm0"]
    child_run += [
        f"dec DWORD PTR [rdi+{interrupt}]",
        "mov rdx, QWORD PTR [r10+8]",
        "mov r8, QWORD PTR [rdx+24]",
        "add r8, QWORD PTR [rdx+16]",
        "add QWORD PTR [rdx+16], r11",
        "mov QWORD PTR [rsp+96], r8",
        "mov QWORD PTR [rsp+104], rdx",
        "mov QWORD PTR [r8+112], rdx",
        "mov DWORD PTR [r8+120], r11d",
        "mov DWORD PTR [r8+124], 0",
        f"mov rax, QWORD PTR [r9+{rt}]",
        "mov QWORD PTR [r8], rax",
        "movdqu xmm1, XMMWORD PTR [rsp+32]",
        "movdqu XMMWORD PTR [r8+8], xmm1",
        "movdqu xmm1, XMMWORD PTR [rsp+48]",
        "movdqu XMMWORD PTR [r8+88], xmm1",
        "mov rax, QWORD PTR [rsp+16]",
        "mov QWORD PTR [r8+80], rax",
        "mov QWORD PTR [r8+104], 0",
        "mov rax, QWORD PTR [rsp+64]",
        "mov QWORD PTR [r8+24], rax",
        "lea rax, [r8+128]",
        "mov QWORD PTR [r8+32], rax",
        "mov QWORD PTR [r8+40], 0",
        "mov QWORD PTR [r8+48], 0",
        "mov WORD PTR [r8+56], 0",
        "mov cx, WORD PTR [rsp+72]",
        "mov WORD PTR [r8+58], cx",
        "mov rdx, QWORD PTR [rsp+16]",
        f"mov cl, BYTE PTR [rdx+{strict}]",
        "and cl, 1",
        "mov BYTE PTR [r8+60], cl",
        "mov BYTE PTR [r8+61], 0",
        "mov WORD PTR [r8+62], 1",
        "mov QWORD PTR [r8+64], 0",
        "mov QWORD PTR [r8+72], 0",
        f"movzx ecx, WORD PTR [rdx+{f['JSFunctionBytecode.var_count']}]",
        "test ecx, ecx",
        "jz linux_child_vars_ready",
        "linux_child_vars:",
        "mov QWORD PTR [rax], 0",
        "mov QWORD PTR [rax+8], 3",
        "add rax, 16",
        "dec ecx",
        "jnz linux_child_vars",
        "linux_child_vars_ready:",
        "mov QWORD PTR [rsp+120], rax",
        f"mov rax, QWORD PTR [rdx+{code}]",
        "mov QWORD PTR [rsp+112], rax",
        "mov QWORD PTR [rsp+128], r11",
        "mov QWORD PTR [rsp+144], 3",
        "mov QWORD PTR [rsp+152], r9",
        "mov QWORD PTR [rsp+160], r11",
        f"mov rax, QWORD PTR [r9+{limit}]",
        "mov QWORD PTR [rsp+168], rax",
        f"add QWORD PTR [r9+{top}], r11",
        "test rax, rax",
        "jz linux_child_unlimited",
        "add rax, r11",
        f"mov QWORD PTR [r9+{limit}], rax",
        "linux_child_unlimited:",
        "mov QWORD PTR [rsp+176], rax",
        "mov rax, QWORD PTR [rsp]",
        "mov QWORD PTR [rsp+232], rax",
        "mov rax, QWORD PTR [r10+144]",
        "mov QWORD PTR [rsp+240], rax",
        "mov rax, QWORD PTR [r10+152]",
        "mov QWORD PTR [rsp+248], rax",
        "mov al, BYTE PTR [r10+161]",
        "mov BYTE PTR [rsp+257], al",
        # Both JS frame and all executable state fields are complete now.
        "mov rax, QWORD PTR [rsp+88]",
        "mov rdx, QWORD PTR [rax]",
        "mov QWORD PTR [rsp+272], rdx",
        "lea rdi, [rsp+96]",
        "mov QWORD PTR [rsp+280], rdi",
        "mov DWORD PTR [rsp+288], 2",
        f"mov QWORD PTR [r9+{rt}], r8",
        "lea rdx, [rsp+272]",
        "mov QWORD PTR [rax], rdx",
        "call JS_LinuxLiteralEnter",
        "mov r9, QWORD PTR [rsp+8]",
        "mov r10, QWORD PTR [rsp+128]",
        "sub r10, QWORD PTR [rsp+160]",
        f"add QWORD PTR [r9+{top}], r10",
        f"cmp QWORD PTR [r9+{limit}], 0",
        "je linux_child_charged",
        f"add QWORD PTR [r9+{limit}], r10",
        "linux_child_charged:",
        "mov rax, QWORD PTR [rsp+88]",
        "mov rdx, QWORD PTR [rsp+272]",
        "mov QWORD PTR [rax], rdx",
        "mov rax, QWORD PTR [rsp+136]",
        "mov rdx, QWORD PTR [rsp+144]",
        "add rsp, 312",
        ".cfi_adjust_cfa_offset -312",
        "ret",
    ]
    emit("JS_LinuxNativeChild", child_run)

    from integer_expressions import generate as integer_expressions

    emit("JS_LinuxIntExpressionLeaf", integer_expressions(ids, f))
    emit(
        "JS_LinuxIntExpressionInitChild",
        [*preserve_call("JS_LinuxIntExpressionInit"), "jmp JS_LinuxNativeChildSelect"],
    )

    targets = [
        "JS_FrameCallEntryShared",
        "JS_LinuxCallPublicFallback",
        "JS_LinuxEntryInit",
        "JS_LinuxEntrySlot",
        "JS_LinuxEntryPoll",
        "JS_LinuxEntryOverflow",
        "JS_LinuxLiteralEnter",
        "js_free",
        "JS_LinuxEntryReady",
        "JS_LinuxRootControl",
        "JS_LinuxRootZeroControl",
        "JS_LinuxRootArgsControl",
        "JS_LinuxPublicRootControl",
        "JS_LinuxChildControl",
        "JS_FrameGetterLeafControl",
        "JS_LinuxIntExpressionControl",
        "JS_LinuxIntExpressionInit",
    ]
    asm[1:1] = [".hidden " + name for name in targets]
    asm += [
        *property_note(layout["compiler_features"]["cet"]),
        '.section .note.GNU-stack,"",@progbits',
    ]
    text = "\n".join(asm) + "\n"
    (output / "quickjs-linux-entry.S").write_text(text)
    owners = [
        "root-leaf",
        "child-leaf",
        "native-root",
        "native-root-zero",
        "native-root-args",
        "public-root",
        "child-entry",
    ]
    modules = json.loads((source / "tools/common/modules.json").read_text())
    record = dict(
        status="generated-not-qualified",
        entry_protocol="actual-SysV-aggregate",
        entries=functions,
        local_child_leaf="JS_LinuxChildLeaf",
        leaf_red_zone_bytes=128,
        native_root_stack_bytes=4936,
        native_child_stack_bytes=312,
        initial_arena_bytes=4096,
        functions=functions,
        assembly_sha256=hashlib.sha256(text.encode()).hexdigest(),
        shared_leaf_rows=sum(
            map(len, (root_leaf, child_leaf, fields_leaf, symbol_leaf, captured_leaf))
        ),
        shared_owners={
            (source / "tools" / modules[name]).relative_to(source).as_posix(): hashlib.sha256(
                (source / "tools" / modules[name]).read_bytes()
            ).hexdigest()
            for name in owners
        },
        integer_expression_leaf=dict(
            source_sha256=hashlib.sha256(
                (source / "tools/x86/linux/integer_expressions.py").read_bytes()
            ).hexdigest(),
            configuration_source_sha256=hashlib.sha256(
                (source / "src/x86/linux/integer-expression.c").read_bytes()
            ).hexdigest(),
            maximum_code_bytes=16,
            new_stack_bytes=0,
            new_frame_bytes=0,
            control="QJS_DISABLE_NATIVE_INT_EXPRESSION_LEAF",
        ),
        scope="Native public/zero/equal-arity root and coherent borrowed child entry; shared root/child primitive/getter/capture leaves. Not deferred publication/apply/iterator or release qualification.",
    )
    (output / "ENTRIES.json").write_text(json.dumps(record, indent=2) + "\n")
    return record
