"""Reference slot stores in the existing native activation.

The old non-reference handlers and every instruction offset stay intact.
Only their existing negative-tag branch destinations change. Last releases
retain the original C free/quota protocol; value capture/duplication happens
before a finalizer, matching set_value(ctx, slot, value) argument evaluation.
"""

# Shared source/tool/artifact addressing for the x86 backend package.
import sys as _frame_sys
from pathlib import Path as _FramePath

_frame_tools_root = str(_FramePath(__file__).resolve().parents[3])
if _frame_tools_root not in _frame_sys.path:
    _frame_sys.path.insert(0, _frame_tools_root)
from x86.common.paths_x86 import (
    activate_tools as _frame_activate_tools,
    tool_path as _frame_tool_path,
    source_file as _frame_source_file,
    source_text as _frame_source_text,
    generated_file as _frame_generated_file,
    project_root as _frame_project_root,
    build_file as _frame_build_file,
)

_frame_activate_tools()
from abi_layout import load as load_layout, constants as layout_constants


def append(masm, gas, entries, diagnostics, source=None):
    layout = load_layout(source or _frame_project_root())
    rc = layout_constants(layout)["QJS_ABI_REF_COUNT_OFFSET"]
    mode = layout["offsets"]["JSRuntime.module_normalize_has_attr"] + 5
    assert masm.pop() == "END"
    name = "JS_FrameInterpSlotCold"
    body = []
    for target, action, size in entries:
        body += [
            target + ":",
            f"mov r9d, {size | (128 if action == 'set' else 0)}",
            "jmp slot_store_common",
        ]
    body += [
        "slot_store_common:",
        "mov r10, QWORD PTR [rbx+56]",
        f"cmp BYTE PTR [r10+{mode}], 0",
        "je slot_store_config",
        f"cmp BYTE PTR [r10+{mode}], 1",
        "jne interp_slow",
        "mov rax, QWORD PTR [r8]",
        f"cmp DWORD PTR [rax{rc:+d}], 1",
        "jle slot_store_last",
        f"dec DWORD PTR [rax{rc:+d}]",
        # No user code can run after a non-last decref. The already-owned
        # operand protects aliases of the slot being overwritten.
        "mov rax, QWORD PTR [r13-16]",
        "mov rdx, QWORD PTR [r13-8]",
        "test r9b, 128",
        "jz slot_store_pop",
        "test edx, edx",
        "jns slot_store_write",
        f"inc DWORD PTR [rax{rc:+d}]",
        "jmp slot_store_write",
        "slot_store_pop:",
        "sub r13, 16",
        "slot_store_write:",
        "mov QWORD PTR [r8], rax",
        "mov QWORD PTR [r8+8], rdx",
        "and r9d, 127",
        "add r12, r9",
        "movzx eax, BYTE PTR [r12]",
        "jmp QWORD PTR [rdi+rax*8]",
        "slot_store_last:",
        # Capture the incoming value BEFORE calling a possibly reentrant
        # finalizer. A set owns an extra dup; a put transfers the popped value.
        "mov rax, QWORD PTR [r13-16]",
        "mov rdx, QWORD PTR [r13-8]",
        "test r9b, 128",
        "jz slot_store_last_pop",
        "test edx, edx",
        "jns slot_store_last_ready",
        f"inc DWORD PTR [rax{rc:+d}]",
        "jmp slot_store_last_ready",
        "slot_store_last_pop:",
        "sub r13, 16",
        "slot_store_last_ready:",
        "and r9d, 127",
        "add r12, r9",
        "movdqu xmm0, XMMWORD PTR [r8]",
        # Original set_value publishes BEFORE the old value's finalizer.
        # A finalizer may observe or modify this live slot. Never rewrite it
        # after the callback. Only the old owned value crosses the C boundary.
        "mov QWORD PTR [r8], rax",
        "mov QWORD PTR [r8+8], rdx",
        "movdqa XMMWORD PTR [rsp+32], xmm0",
        "lea r8, [rsp+32]",
        "mov QWORD PTR [rbx], rbp",
        "mov QWORD PTR [rbx+16], r12",
        "mov QWORD PTR [rbx+24], r13",
        "mov rcx, rbx",
        "mov rdx, rsi",
        "jmp JS_FrameSlotFreeBorrowed",
        "movzx eax, BYTE PTR [r12]",
        "jmp QWORD PTR [rdi+rax*8]",
        "slot_store_config:",
        "mov QWORD PTR [rsp+32], r8",
        "mov QWORD PTR [rsp+40], r9",
        "mov QWORD PTR [rsp+48], r10",
        "lea rcx, JS_FrameSlotDisable",
        "call QWORD PTR [__imp_getenv]",
        "test rax, rax",
        "setne r11b",
        "inc r11b",
        "mov r10, QWORD PTR [rsp+48]",
        f"mov BYTE PTR [r10+{mode}], r11b",
        "mov r8, QWORD PTR [rsp+32]",
        "mov r9, QWORD PTR [rsp+40]",
        "jmp slot_store_common",
    ]
    # Reuse the old MS section names: adding a POGO debug group changes .rdata
    # placement. GNU islands are after .reloc; all tails remain PC-relative.
    masm += [
        ".qjscold SEGMENT ALIGN(16) 'CODE'",
        "ALIGN 16",
        "PUBLIC " + name + ", " + name + "_end",
        name + " PROC",
    ]
    gas += [
        '.section .qjsleaf,"xr"',
        ".p2align 4",
        ".globl " + name + ", " + name + "_end",
        ".def " + name + "; .scl 2; .type 32; .endef",
        name + ":",
    ]
    for line in body:
        masm += [
            line[:-1] + "::"
            if line.endswith(":")
            else line.replace("jne interp_slow", "jne NEAR PTR interp_slow").replace(
                "jmp JS_FrameSlotFreeBorrowed", "jmp NEAR PTR JS_FrameSlotFreeBorrowed"
            )
        ]
        gas += [
            line.replace(
                "lea rcx, JS_FrameSlotDisable", "lea rcx, [rip+JS_FrameSlotDisable]"
            ).replace("[__imp_getenv]", "[rip+__imp_getenv]")
        ]
    # Preserve the old section envelope. These bytes follow an unconditional
    # tail jump and are never executed; subsequent helpers keep their RVAs.
    masm += ["DB 30 DUP (090h)"]
    gas += [".fill 30,1,0x90"]
    masm += [
        name + "_end LABEL BYTE",
        name + " ENDP",
        "ALIGN 4",
        "JS_FrameSlotDisable LABEL BYTE",
        'DB "QJS_DISABLE_NATIVE_SLOT_STORE", 0',
        ".qjscold ENDS",
        ".pdata$zzqjscold SEGMENT ALIGN(4) READONLY 'DATA'",
        "DD IMAGEREL "
        + name
        + ", IMAGEREL "
        + name
        + "_end, IMAGEREL JS_FrameInterpPropertyCold_unwind",
        ".pdata$zzqjscold ENDS",
        "END",
    ]
    gas += [
        name + "_end:",
        ".p2align 2",
        "JS_FrameSlotDisable:",
        '.asciz "QJS_DISABLE_NATIVE_SLOT_STORE"',
        '.section .pdata$zzqjscold,"dr"',
        ".p2align 2",
        ".rva " + name + ", " + name + "_end, JS_FrameInterpPropertyCold_unwind",
    ]
