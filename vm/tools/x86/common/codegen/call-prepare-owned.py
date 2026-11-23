"""Native owned-child and logical-wrapper commit from the shared descriptor.

Incoming home: target bytecode +8, packed depth/argc +16, original argv +24.
Only the fourth home slot (+32..39) is added as scratch for regular frame bytes.
No call, native RSP change, or nonvolatile mutation. Near-poll failures refund
the exact prefix before the prepared-C fallback sees the original descriptor.
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
from abi_layout import constants as abi_constants
from native_abi import current_or_load as load_layout
from pathlib import Path
import importlib.util

OLD = "JS_FrameVarargsForwardTry"
DATA = "JS_FrameCallPrepareData"
OWN = "JS_FrameCallPrepareOwned"
FALL = "JS_FrameCallPrepareFallback"


def module(source, name):
    sp = importlib.util.spec_from_file_location(
        "prepared_owned_" + name.replace("-", "_"), _frame_tool_path(name + ".py")
    )
    m = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


def extend_blocks(source, base, diagnostics, layout_override=None):
    abi = layout_override if layout_override is not None else load_layout(source)
    fields = abi["offsets"]
    ((strict_byte, strict_mask),) = abi["bits"]["JSFunctionBytecode.is_strict_mode"]
    assert strict_mask == 1
    ids = module(source, "leaf-entry").checked_opcodes(source)
    names = [name for name, _ in base]
    assert names == [
        "JS_FrameCallPrepareOne",
        "JS_FrameCallPrepareDeep",
        "JS_FrameCallPrepareExecute",
    ]
    run = list(base[2][1])
    c = run.index("prepare_c_commit:")
    refund = run.index("prepare_refund_polls:")
    observed = run.index("prepare_c_unobserved:", c)
    # Keep one observed attempt/depth event at general admission, irrespective
    # of native/C completion. depth[0] separately counts successful native owns.
    fallback = run[observed + 1 : refund]
    assert fallback[-1] == "jmp JS_FrameCallPrepareCommit"
    patched = run[: observed + 1] + ["jmp " + OWN] + run[refund:]
    limit = 2312 if diagnostics else 72
    quota_end = run.index(f"cmp r10, QWORD PTR [rcx+{limit}]", run.index("prepare_leaf_quota:")) + 2
    poll_end = run.index("prepare_polls_ready:")
    poll = run[quota_end : poll_end + 1]
    assert poll[:3] == [
        "mov r10, QWORD PTR [rcx]",
        "mov r10, QWORD PTR [r10+80]",
        f"mov r10, QWORD PTR [r10+{fields['JSFunctionBytecode.realm']}]",
    ]

    def copied_poll(lines):
        return [
            line.replace("prepare_", "prepare_owned_").replace(" " + OLD, " " + FALL)
            for line in lines
        ]

    # Reuse precisely the qualified single-pass poll/refund instructions.
    poll = copied_poll(poll)
    refund_body = copied_poll(run[refund:])
    own = (
        [
            "lea rax, [rip+" + DATA + "]",
            "cmp BYTE PTR [rax+1], 1",
            "jne " + FALL,
            "mov rdx, QWORD PTR [rsp+8]",
            "mov r8, QWORD PTR [rsp+24]",
            "mov r11d, DWORD PTR [rsp+16]",
            "mov r9d, r11d",
            "shr r9d, 16",
            "and r11d, 65535",
            # Actual target argc is max(original argc-depth,0). Own all actuals,
            # including extras, then pad through the declared formal count.
            "mov eax, r11d",
            "sub eax, r9d",
            "jae prepare_owned_actual",
            "xor eax, eax",
            "prepare_owned_actual:",
            f"movzx r10d, WORD PTR [rdx+{fields['JSFunctionBytecode.arg_count']}]",
            "cmp eax, r10d",
            "cmovb eax, r10d",
            f"movzx r10d, WORD PTR [rdx+{fields['JSFunctionBytecode.var_count']}]",
            "add eax, r10d",
            f"movzx r10d, WORD PTR [rdx+{fields['JSFunctionBytecode.stack_size']}]",
            "add eax, r10d",
            "shl rax, 4",
            "add rax, 128",
            f"movzx r10d, WORD PTR [rdx+{fields['JSFunctionBytecode.var_ref_count']}]",
            "shl r10, 3",
            "add r10, 15",
            "and r10, -16",
            "add rax, r10",
            "mov QWORD PTR [rsp+32], rax",
            "imul r10, r9, 80",
            "add rax, r10",
            "mov r10, QWORD PTR [rcx+8]",
            "mov rdx, QWORD PTR [r10+8]",
            "sub rdx, QWORD PTR [r10+16]",
            "cmp rax, rdx",
            "ja " + FALL,
            "add rax, QWORD PTR [rcx+32]",
            "jc " + FALL,
            "add rax, 5280",
            "jc " + FALL,
            "mov r10, rsp",
            "sub r10, rax",
            "jc " + FALL,
            f"cmp r10, QWORD PTR [rcx+{limit}]",
            "jb " + FALL,
        ]
        + poll
        + [
            # No fallback/observer/failing operation from here through publication.
            # The entire child, capture slots, arguments and logical C chain are
            # complete before making the activation visible to VM/GC/API entries.
            "mov rdx, QWORD PTR [rsp+8]",
            "mov r10, QWORD PTR [rcx+8]",
            "mov r9, QWORD PTR [r10+24]",
            "add r9, QWORD PTR [r10+16]",
            "mov QWORD PTR [r9+112], r10",
            "mov QWORD PTR [r9+80], rdx",
            "mov rax, QWORD PTR [rsp+32]",
            "mov DWORD PTR [r9+120], eax",
            "mov eax, DWORD PTR [rsp+16]",
            "shr eax, 16",
            "cmp eax, 1",
            "jne prepare_owned_target_later",
            "lea r10, [r8-32]",
            "jmp prepare_owned_target_slot",
            "prepare_owned_target_later:",
            "sub eax, 2",
            "shl rax, 4",
            "lea r10, [r8+rax]",
            "prepare_owned_target_slot:",
            "movdqu xmm0, XMMWORD PTR [r10]",
            "movdqu XMMWORD PTR [r9+8], xmm0",
            "mov eax, DWORD PTR [rsp+16]",
            "mov r10d, eax",
            "shr r10d, 16",
            "and eax, 65535",
            "sub eax, r10d",
            "jae prepare_owned_count",
            "xor eax, eax",
            "prepare_owned_count:",
            f"movzx r10d, WORD PTR [rdx+{fields['JSFunctionBytecode.arg_count']}]",
            "cmp eax, r10d",
            "cmovb eax, r10d",
            "mov WORD PTR [r9+58], ax",
            "mov WORD PTR [r9+124], ax",
            "mov WORD PTR [r9+126], 0",
            "shl rax, 4",
            "lea r10, [r9+128]",
            "mov QWORD PTR [r9+24], r10",
            "add rax, r10",
            "mov QWORD PTR [r9+32], rax",
            f"movzx r10d, WORD PTR [rdx+{fields['JSFunctionBytecode.var_count']}]",
            "shl r10, 4",
            "add r10, rax",
            "mov QWORD PTR [r9+64], r10",
            "mov QWORD PTR [r9+104], r10",
            f"movzx eax, WORD PTR [rdx+{fields['JSFunctionBytecode.var_ref_count']}]",
            "mov WORD PTR [r9+56], ax",
            "mov QWORD PTR [r9+40], 0",
            "test eax, eax",
            "jz prepare_owned_refs_done",
            f"movzx r11d, WORD PTR [rdx+{fields['JSFunctionBytecode.stack_size']}]",
            "shl r11, 4",
            "add r10, r11",
            "mov QWORD PTR [r9+40], r10",
            "prepare_owned_zero_refs:",
            "mov QWORD PTR [r10], 0",
            "add r10, 8",
            "dec eax",
            "jnz prepare_owned_zero_refs",
            "prepare_owned_refs_done:",
            "mov QWORD PTR [r9+48], 0",
            "mov QWORD PTR [r9+72], 0",
            f"movzx eax, BYTE PTR [rdx+{strict_byte}]",
            "and eax, 1",
            "mov BYTE PTR [r9+60], al",
            "mov BYTE PTR [r9+61], 0",
            "mov WORD PTR [r9+62], 2",
            # Final receiver is argv[depth-1] when present, otherwise undefined.
            "mov r11d, DWORD PTR [rsp+16]",
            "mov eax, r11d",
            "shr eax, 16",
            "and r11d, 65535",
            "cmp r11d, eax",
            "jb prepare_owned_undefined_this",
            "dec eax",
            "shl rax, 4",
            "movdqu xmm0, XMMWORD PTR [r8+rax]",
            "movdqu XMMWORD PTR [r9+88], xmm0",
            "jmp prepare_owned_this_done",
            "prepare_owned_undefined_this:",
            "mov QWORD PTR [r9+88], 0",
            "mov QWORD PTR [r9+96], 3",
            "prepare_owned_this_done:",
            "mov eax, DWORD PTR [rsp+16]",
            "shr eax, 16",
            "sub r11d, eax",
            "jae prepare_owned_copy_count",
            "xor r11d, r11d",
            "prepare_owned_copy_count:",
            "mov eax, DWORD PTR [rsp+16]",
            "and eax, 65535",
            "sub eax, r11d",
            "shl rax, 4",
            "add r8, rax",
            "mov r10, QWORD PTR [r9+24]",
            "test r11d, r11d",
            "jz prepare_owned_pad_start",
            "prepare_owned_copy_args:",
            "movdqu xmm0, XMMWORD PTR [r8]",
            "movdqu XMMWORD PTR [r10], xmm0",
            "cmp DWORD PTR [r8+8], -9",
            "jb prepare_owned_no_dup",
            "mov rax, QWORD PTR [r8]",
            f"inc DWORD PTR [rax{abi_constants(abi)['QJS_ABI_REF_COUNT_OFFSET']:+d}]",
            "prepare_owned_no_dup:",
            "add r8, 16",
            "add r10, 16",
            "dec r11d",
            "jnz prepare_owned_copy_args",
            "prepare_owned_pad_start:",
            "cmp r10, QWORD PTR [r9+32]",
            "je prepare_owned_vars_start",
            "prepare_owned_pad_args:",
            "mov QWORD PTR [r10], 0",
            "mov QWORD PTR [r10+8], 3",
            "add r10, 16",
            "cmp r10, QWORD PTR [r9+32]",
            "jne prepare_owned_pad_args",
            "prepare_owned_vars_start:",
            "cmp r10, QWORD PTR [r9+64]",
            "je prepare_owned_vars_done",
            "prepare_owned_zero_vars:",
            "mov QWORD PTR [r10], 0",
            "mov QWORD PTR [r10+8], 3",
            "add r10, 16",
            "cmp r10, QWORD PTR [r9+64]",
            "jne prepare_owned_zero_vars",
            "prepare_owned_vars_done:",
            # Previous-link accumulator lives only in the unpublished child.
            # A non-final wrapper necessarily has an original argument remaining.
            "mov rax, QWORD PTR [rcx]",
            "mov QWORD PTR [r9], rax",
            "mov r8, QWORD PTR [rsp+24]",
            "mov r11d, DWORD PTR [rsp+16]",
            "mov edx, r11d",
            "shr edx, 16",
            "and r11d, 65535",
            "movdqu xmm1, XMMWORD PTR [r8-16]",
            "movdqu xmm0, XMMWORD PTR [r8-32]",
            "mov r10, QWORD PTR [rsp+32]",
            "add r10, r9",
            "prepare_owned_logical_loop:",
            "mov rax, QWORD PTR [r9]",
            "mov QWORD PTR [r10], rax",
            "mov QWORD PTR [r9], r10",
            "movdqu XMMWORD PTR [r10+8], xmm1",
            "mov QWORD PTR [r10+24], r8",
            "mov eax, r11d",
            "test eax, eax",
            "jnz prepare_owned_logical_count",
            "lea rax, [r9+88]",
            "mov QWORD PTR [r10+24], rax",
            "mov eax, 1",
            "prepare_owned_logical_count:",
            "mov WORD PTR [r10+58], ax",
            "mov WORD PTR [r10+56], 0",
            "mov WORD PTR [r10+60], 0",
            "mov WORD PTR [r10+62], 50944",
            "mov QWORD PTR [r10+32], 0",
            "mov QWORD PTR [r10+40], 0",
            "mov QWORD PTR [r10+48], 0",
            "mov QWORD PTR [r10+64], 0",
            "mov QWORD PTR [r10+72], 0",
            "add r10, 80",
            "dec edx",
            "jz prepare_owned_logical_done",
            "movdqu xmm1, xmm0",
            "movdqu xmm0, XMMWORD PTR [r8]",
            "add r8, 16",
            "dec r11d",
            "jmp prepare_owned_logical_loop",
            "prepare_owned_logical_done:",
            "mov rdx, QWORD PTR [rsp+8]",
            "mov r10, QWORD PTR [rcx]",
            "mov r8, QWORD PTR [rcx+24]",
            "mov QWORD PTR [r10+64], r8",
            "mov QWORD PTR [r10+104], r8",
            "mov r8, QWORD PTR [rcx+16]",
            "mov eax, DWORD PTR [rsp+16]",
            "and eax, 65535",
            "add eax, 2",
            f"cmp BYTE PTR [r8], {ids['tail_call_method']}",
            "jne prepare_owned_not_tail",
            "or eax, 32768",
            "prepare_owned_not_tail:",
            "mov WORD PTR [r10+126], ax",
            "add r8, 3",
            "mov QWORD PTR [r10+48], r8",
            "mov eax, DWORD PTR [rsp+16]",
            "shr eax, 16",
            "imul rax, rax, 80",
            "add rax, QWORD PTR [rsp+32]",
            "mov r10, QWORD PTR [rcx+8]",
            "add QWORD PTR [r10+16], rax",
            "add QWORD PTR [rcx+32], rax",
        ]
    )
    if diagnostics:
        own += [
            "inc QWORD PTR [rcx+88]",
            "mov eax, DWORD PTR [rsp+16]",
            "mov r10d, eax",
            "shr r10d, 16",
            "and eax, 65535",
            "sub eax, r10d",
            "jae prepare_owned_diag_count",
            "xor eax, eax",
            "prepare_owned_diag_count:",
            "add QWORD PTR [rcx+2216], rax",
            f"cmp ax, WORD PTR [rdx+{fields['JSFunctionBytecode.arg_count']}]",
            "jae prepare_owned_diag_arity",
            "inc QWORD PTR [rcx+96]",
            "prepare_owned_diag_arity:",
            "inc DWORD PTR [rcx+128]",
            "mov eax, DWORD PTR [rcx+128]",
            "cmp eax, DWORD PTR [rcx+132]",
            "jbe prepare_owned_diag_depth",
            "mov DWORD PTR [rcx+132], eax",
            "prepare_owned_diag_depth:",
            "mov rax, QWORD PTR [rcx+32]",
            "cmp rax, QWORD PTR [rcx+120]",
            "jbe prepare_owned_diag_peak",
            "mov QWORD PTR [rcx+120], rax",
            "prepare_owned_diag_peak:",
        ]
    own += [
        "lea rax, [rip+" + DATA + "]",
        "test BYTE PTR [rax], 4",
        "jz prepare_owned_unobserved",
        "lock inc QWORD PTR [rax+24]",
        "prepare_owned_unobserved:",
        "mov QWORD PTR [rcx], r9",
        f"mov rax, QWORD PTR [rdx+{fields['JSFunctionBytecode.byte_code_buf']}]",
        "mov QWORD PTR [rcx+16], rax",
        "mov rax, QWORD PTR [r9+64]",
        "mov QWORD PTR [rcx+24], rax",
        "mov r10, QWORD PTR [rcx+56]",
        f"mov QWORD PTR [r10+{fields['JSRuntime.current_stack_frame']}], r9",
        "mov eax, 1",
        "ret",
    ] + refund_body
    return [base[0], base[1], (base[2][0], patched), (OWN, own), (FALL, fallback)]
