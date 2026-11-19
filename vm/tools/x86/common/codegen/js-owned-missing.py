"""Own missing-formal argument prefixes in the ordinary prepared JS call ABI.

Append to the existing last register island. Only two already-long admission
JCCs in CallMeta change their operand target; every old instruction keeps its
width/PC. The original callee cleanup/return/unwind code remains in use.
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
from native_abi import current as current_abi
from abi_layout import constants as layout_constants
import re


def frame_body(body, layout, diagnostics=False):
    """Shared x86_64 owned-prefix constructor over the supplied real layout."""
    abi_fields = layout["offsets"]
    abi_rc = layout_constants(layout)["QJS_ABI_REF_COUNT_OFFSET"]
    labels = {
        x[:-1]: "owned_js_" + x[:-1].removeprefix("interp_meta_") for x in body if x.endswith(":")
    }
    rx = re.compile(r"\b(?:" + "|".join(map(re.escape, labels)) + r")\b")
    body = [rx.sub(lambda m: labels[m[0]], x) for x in body]

    def replace(before, after):
        nonlocal body
        text = "\n".join(body)
        assert text.count(before) == 1, before
        body = text.replace(before, after).splitlines()

    replace(
        "mov QWORD PTR [rax+24], r8\nlea r14, [rax+128]",
        f"lea r10, [rax+128]\nmov QWORD PTR [rax+24], r10\nmovzx r10d, BYTE PTR [r9+{abi_fields['JSFunctionBytecode.byte_code_buf'] - 3}]\nshl r10, 4\nlea r14, [rax+r10+128]",
    )
    replace(
        "mov DWORD PTR [rax+124], 0",
        f"movzx r10d, BYTE PTR [r9+{abi_fields['JSFunctionBytecode.byte_code_buf'] - 3}]\nmov WORD PTR [rax+124], r10w\nmov WORD PTR [rax+126], 0",
    )
    # Preserve the caller argv until this has been read from argv[-2]. Copy
    # each provided cell and increment its owner independently, including
    # repeated aliases. No C/GC occurs while the private data frame is partial.
    replace(
        f"mov rbp, rax\nmov r15, r8\nmov r10, QWORD PTR [rbx+56]\nmov QWORD PTR [r10+{abi_fields['JSRuntime.current_stack_frame']}], rbp",
        "\n".join(
            [
                "mov rbp, rax",
                "mov r15, QWORD PTR [rbp+24]",
                "mov r10, r15",
                "mov r11, r8",
                "mov edx, ecx",
                "test edx, edx",
                "jz owned_js_copy_done",
                "owned_js_copy_loop:",
                "movdqu xmm0, XMMWORD PTR [r11]",
                "movdqu XMMWORD PTR [r10], xmm0",
                "cmp DWORD PTR [r11+8], 0",
                "jge owned_js_copy_next",
                "mov rax, QWORD PTR [r11]",
                f"inc DWORD PTR [rax+{abi_rc}]",
                "owned_js_copy_next:",
                "add r10, 16",
                "add r11, 16",
                "dec edx",
                "jnz owned_js_copy_loop",
                "owned_js_copy_done:",
            ]
        ),
    )
    if diagnostics:
        # These original counters already describe arity/copies. Owned frames
        # are not borrowed windows; do not increment the old window counters.
        text = "\n".join(body)
        begin = text.index("inc QWORD PTR [rbx+96]")
        stop = text.index("shl rcx, 4", begin)
        text = (
            text[:begin] + "inc QWORD PTR [rbx+96]\nadd QWORD PTR [rbx+2216], rcx\n" + text[stop:]
        )
        body = text.splitlines()
    # Publish TLS after all owned arguments, locals and capture-table cells are
    # initialized. The register frame commits without any intervening C call.
    replace(
        f"mov r12, QWORD PTR [r9+{abi_fields['JSFunctionBytecode.byte_code_buf']}]",
        f"mov r10, QWORD PTR [rbx+56]\nmov QWORD PTR [r10+{abi_fields['JSRuntime.current_stack_frame']}], rbp\nmov r12, QWORD PTR [r9+{abi_fields['JSFunctionBytecode.byte_code_buf']}]",
    )
    return body


def append(masm, gas, diagnostics, out):
    layout = current_abi()
    abi_fields = layout["offsets"]
    abi_rc = layout_constants(layout)["QJS_ABI_REF_COUNT_OFFSET"]
    original_masm = list(masm)
    original_gas = list(gas)
    guard = "JS_FrameJSOwnedMissingGuard"
    push = "JS_FrameJSOwnedMissingPush"
    wide = "JS_FrameJSWideMissingGuard"
    start = masm.index("interp_meta_call_size_ready::") + 1
    end = masm.index("interp_meta_call_refs_done::") + 5
    body = [
        x.replace(" NEAR PTR ", " ")[:-1] if x.endswith("::") else x.replace(" NEAR PTR ", " ")
        for x in masm[start:end]
    ]
    assert body[-2:] == ["movzx eax, BYTE PTR [r12]", "jmp QWORD PTR [rdi+rax*8]"], body[-3:]
    body = frame_body(body, layout, diagnostics)
    ready = masm.index("interp_meta_ready::")
    stop = masm.index("interp_meta_call_arity_ok::")
    changes = []
    for i in range(ready, stop):
        if masm[i] in ("jne NEAR PTR interp_slow", "jz NEAR PTR interp_slow"):
            changes.append((masm[i], i))
            masm[i] = masm[i].replace("interp_slow", guard)
    assert len(changes) == 2, changes
    # The insufficient caller-window exit already precedes all commits. Its
    # EAX is an address, so the new entry reloads the validated formal count.
    window = [i for i in range(ready, stop) if masm[i] == "ja NEAR PTR interp_slow"]
    assert len(window) == 1, window
    masm[window[0]] = "ja NEAR PTR " + wide
    ready = gas.index("interp_meta_ready:")
    stop = gas.index("interp_meta_call_arity_ok:")
    changed = []
    for i in range(ready, stop):
        if gas[i] in ("jne interp_slow", "jz interp_slow"):
            changed.append(gas[i])
            gas[i] = gas[i].replace("interp_slow", guard)
    assert len(changed) == 2, changed
    window = [i for i in range(ready, stop) if gas[i] == "ja interp_slow"]
    assert len(window) == 1, window
    gas[window[0]] = "ja " + wide
    assert masm.pop() == "END"
    new_masm_at = len(masm)
    new_gas_at = len(gas)
    guard_body = [
        "mov r10, QWORD PTR [rbx+56]",
        f"cmp BYTE PTR [r10+{abi_fields['JSRuntime.module_loader_has_attr'] + 7}], 0",
        "jne interp_slow",
        "cmp eax, 4",
        "ja " + wide,
        "mov r10, rax",
        "shl r10, 4",
        f"movzx eax, WORD PTR [r9+{abi_fields['JSFunctionBytecode.byte_code_buf'] - 6}]",
        "sub eax, 32",
        "add rax, r10",
        "jmp " + push,
    ]
    masm += [".qjscold SEGMENT ALIGN(16) 'CODE'"]
    gas += ['.section .qjsleaf,"xr"']
    for name, lines in ((guard, guard_body), (push, body)):
        masm += ["ALIGN 16", "PUBLIC " + name + ", " + name + "_end", name + " PROC"]
        gas += [
            ".p2align 4",
            ".globl " + name + ", " + name + "_end",
            ".def " + name + "; .scl 2; .type 32; .endef",
            name + ":",
        ]
        for line in lines:
            masm += [
                line[:-1] + "::"
                if line.endswith(":")
                else re.sub(r"^(j\w+) (interp_\w+)$", r"\1 NEAR PTR \2", line)
            ]
            gas += [line]
        masm += [name + "_end LABEL BYTE", name + " ENDP"]
        gas += [name + "_end:"]
    masm += [".qjscold ENDS", ".pdata$zzqjscold SEGMENT ALIGN(4) READONLY 'DATA'"]
    gas += ['.section .pdata$zzqjscold,"dr"', ".p2align 2"]
    for name in (guard, push):
        masm += [
            "DD IMAGEREL "
            + name
            + ", IMAGEREL "
            + name
            + "_end, IMAGEREL JS_FrameInterpPropertyCold_unwind"
        ]
        gas += [".rva " + name + ", " + name + "_end, JS_FrameInterpPropertyCold_unwind"]
    masm += [".pdata$zzqjscold ENDS", "END"]
    # Separate last contribution: inserting into the register object can move
    # the existing later MSVC null-helper code, despite stable original labels.
    externs = [
        "EXTERN interp_slow:PROC",
        "EXTERN JS_FrameInterpPropertyCold_unwind:BYTE",
        "EXTERN " + wide + ":PROC",
    ]
    new_masm = ["OPTION CASEMAP:NONE", "OPTION DOTNAME"] + externs + masm[new_masm_at:]
    new_gas = [".intel_syntax noprefix"] + gas[new_gas_at:]
    del masm[new_masm_at:]
    masm += ["END"]
    del gas[new_gas_at:]
    masm[3:3] = [
        "EXTERN " + guard + ":PROC",
        "PUBLIC interp_slow, JS_FrameInterpPropertyCold_unwind",
    ]
    gas[:0] = [".globl interp_slow, JS_FrameInterpPropertyCold_unwind"]
    # Normalize only the two intended operand-target edits and declarations.
    check = [
        x
        for x in masm
        if x
        not in (
            "EXTERN " + guard + ":PROC",
            "PUBLIC interp_slow, JS_FrameInterpPropertyCold_unwind",
        )
    ]
    check = [
        x.replace(" NEAR PTR " + guard, " NEAR PTR interp_slow").replace(
            " NEAR PTR " + wide, " NEAR PTR interp_slow"
        )
        for x in check
    ]
    assert check == original_masm
    check = [x for x in gas if x != ".globl interp_slow, JS_FrameInterpPropertyCold_unwind"]
    check = [
        x.replace(" " + guard, " interp_slow").replace(" " + wide, " interp_slow") for x in check
    ]
    assert check == original_gas
    (out / "quickjs-interpreter-owned-win64.asm").write_text(
        "\n".join(new_masm) + "\n", encoding="utf-8"
    )
    (out / "quickjs-interpreter-owned-win64.S").write_text(
        "\n".join(new_gas) + "\n", encoding="utf-8"
    )

    # One noncontiguous part of the existing VM activation. Every incoming
    # edge has checked the live callee/class and prepared uncaptured bytecode.
    # The validator admits at most 128 formals. No argument or local is copied
    # until the inherited push has checked arena capacity, quota and polling.
    # The existing owner count frees every copied alias independently.
    lines = [
        "mov r10, QWORD PTR [rbx+56]",
        f"cmp BYTE PTR [r10+{abi_fields['JSRuntime.module_loader_has_attr'] + 7}], 0",
        "jne interp_slow",
        f"movzx eax, BYTE PTR [r9+{abi_fields['JSFunctionBytecode.byte_code_buf'] - 3}]",
        "cmp eax, 128",
        "ja interp_slow",
        "mov r10, rax",
        "shl r10, 4",
        f"movzx eax, WORD PTR [r9+{abi_fields['JSFunctionBytecode.byte_code_buf'] - 6}]",
        "sub eax, 32",
        "add rax, r10",
        "jmp " + push,
    ]
    assert masm.pop() == "END"
    masm[3:3] = ["EXTERN " + push + ":PROC"]
    masm += [
        ".qjszjw SEGMENT ALIGN(16) 'CODE'",
        "ALIGN 16",
        "PUBLIC " + wide + ", " + wide + "_end",
        wide + " PROC",
    ]
    gas += [
        '.section .qjszjw,"xr"',
        ".p2align 4",
        ".globl " + wide + ", " + wide + "_end",
        ".def " + wide + "; .scl 2; .type 32; .endef",
        wide + ":",
    ]
    for line in lines:
        masm += [re.sub(r"^(j\w+) (interp_\w+)$", r"\1 NEAR PTR \2", line)]
        gas += [line]
    masm += [
        wide + "_end LABEL BYTE",
        wide + " ENDP",
        ".qjszjw ENDS",
        ".pdata$zzjswide SEGMENT ALIGN(4) READONLY 'DATA'",
        "DD IMAGEREL "
        + wide
        + ", IMAGEREL "
        + wide
        + "_end, IMAGEREL JS_FrameInterpPropertyCold_unwind",
        ".pdata$zzjswide ENDS",
        "END",
    ]
    gas += [
        wide + "_end:",
        '.section .pdata$zzjswide,"dr"',
        ".p2align 2",
        ".rva " + wide + ", " + wide + "_end, JS_FrameInterpPropertyCold_unwind",
    ]
