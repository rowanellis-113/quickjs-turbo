"""Native slice reads a published SF view, with actual arguments and direct output.

Exact-span GenericMissingFast/VM-entry transfers, C-Slow JZ operand, host-call operand and one child-init byte change.
Outside decoded patch spans all old PCs/bytes stay fixed; old entries/section pages are unchanged.
The first instruction consumes the original window-mode comparison flags.
Mode1365:1 lifetime-bound window,2 legacy,3 stack view,4 transient,5 live geometry. Unused by f94s; conflicts with held f94z.
Mode1 caller-window extensions join frame_bytes/used/committed and RT charges.
Existing native/slow JS-frame pop reclaims storage; each C return only unpublishes.
Mode4 retains the transient128-byte allocation/charge experiment.
Release cache uses diagnostic-only slots88..127. Diagnostic cache uses appended slots2408..2447.
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
import argparse, hashlib, importlib.util, json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def append(masm, gas, diagnostics, out):
    layout = current_abi()
    abi_fields, abi_bits = layout["offsets"], layout["bits"]
    guard = "JS_FrameNativeSliceGuard"
    config = "JS_FrameNativeSliceConfig"
    native = "JS_FrameNativeSliceTrampoline"
    legacy = "JS_FrameNativeSliceLegacy"
    vm_select = "JS_FrameNativeVMSelect"
    vm_bridge = "JS_FrameNativeVMTrampoline"
    fallback = "JS_FrameInterpHostDirectShared"
    committed = 2304 if diagnostics else 64
    native_limit = 2312 if diagnostics else 72
    shared_limit = 2320 if diagnostics else 80
    exception = 2296 if diagnostics else 160
    stack_native = "JS_FrameNativeSliceStackTrampoline"
    transient = "JS_FrameNativeSliceTransientTrampoline"
    prepare = "JS_FrameNativeSliceReusePrepare"
    view, owner, variables, bytecode, size = (
        (2408, 2416, 2424, 2432, 2440) if diagnostics else (88, 96, 104, 112, 120)
    )
    originals = {"masm": list(masm), "gas": list(gas)}
    bodies = {}
    if not diagnostics:
        for kind, stream in (("masm", masm), ("gas", gas)):
            begin = stream.index(
                "JS_FrameChildTrampoline PROC" if kind == "masm" else "JS_FrameChildTrampoline:"
            )
            end = stream.index(
                "JS_FrameChildTrampoline_end LABEL BYTE"
                if kind == "masm"
                else "JS_FrameChildTrampoline_end:"
            )
            at = stream.index("mov QWORD PTR [r9+40], 0", begin, end)
            assert stream.count("mov QWORD PTR [r9+96], 0") == 0
            stream[at] = "mov QWORD PTR [r9+96], 0"
    for kind, stream in (("masm", masm), ("gas", gas)):
        start = (
            stream.index(
                "JS_FrameInterpGenericTrampoline PROC"
                if kind == "masm"
                else "JS_FrameInterpGenericTrampoline:"
            )
            + 1
        )
        end = stream.index(
            "JS_FrameInterpGenericTrampoline_end LABEL BYTE"
            if kind == "masm"
            else "JS_FrameInterpGenericTrampoline_end:"
        )
        body = [
            x.replace(" NEAR PTR ", " ")
            for x in stream[start:end]
            if not x.startswith(("PUBLIC ", ".globl "))
        ]
        body = [x[:-1] if x.endswith("::") else x for x in body]
        text = "\n".join(body).replace("gen_tramp_", "native_slice_")
        text = text.replace("mov DWORD PTR [rsp+168], r8d", "")
        a = text.index("mov rax, QWORD PTR [rdx-16]", text.index("native_slice_this_ready:"))
        b = text.index("mov rax, QWORD PTR gs:", a)
        text = text[:a] + "lea rax, [rsp+176]\nmov QWORD PTR [rsp+80], rax\n" + text[b:]
        a = text.index("mov rax, QWORD PTR [rsp+56]")
        b = text.index("cmp QWORD PTR [rbx+48], 6", a)
        count = "NATIVE_STACK_COUNT\n" if diagnostics else ""
        text = (
            text[:a]
            + count
            + "lea rcx, [rsp+48]\nlea rdx, [rbx+40]\ncall JS_FrameBuiltinNative\n"
            + text[b:]
        )
        bodies[kind] = [x for x in text.splitlines() if x]
        start = stream.index(
            "JS_FrameInterpGenericMissingFast PROC"
            if kind == "masm"
            else "JS_FrameInterpGenericMissingFast:"
        )
        end = stream.index(
            "JS_FrameInterpGenericMissingFast_end LABEL BYTE"
            if kind == "masm"
            else "JS_FrameInterpGenericMissingFast_end:"
        )
        at = (
            stream.index(
                f"cmp BYTE PTR [rax+{abi_fields['JSRuntime.module_normalize_has_attr'] + 2}], 1",
                start,
                end,
            )
            + 1
        )
        assert stream[at] == "jne " + ("NEAR PTR " if kind == "masm" else "") + fallback
        stream[at : at + 1] = (
            ["jmp NEAR PTR " + guard, "nop", "PUBLIC " + legacy, legacy + " LABEL BYTE"]
            if kind == "masm"
            else ["jmp " + guard, "nop", ".globl " + legacy, legacy + ":"]
        )
    masm[3:3] = ["EXTERN " + guard + ":PROC"]
    for kind, stream in (("masm", masm), ("gas", gas)):
        normalized = []
        declarations = {
            "EXTERN " + guard + ":PROC",
            "PUBLIC " + legacy,
            legacy + " LABEL BYTE",
            ".globl " + legacy,
            legacy + ":",
        }
        for x in stream:
            if not diagnostics and x == "mov QWORD PTR [r9+96], 0":
                normalized.append("mov QWORD PTR [r9+40], 0")
                continue
            if x in declarations:
                continue
            if x == "jmp " + ("NEAR PTR " if kind == "masm" else "") + guard:
                normalized.append("jne " + ("NEAR PTR " if kind == "masm" else "") + fallback)
            elif (
                x == "nop"
                and normalized
                and normalized[-1] == "jne " + ("NEAR PTR " if kind == "masm" else "") + fallback
            ):
                continue
            else:
                normalized.append(x)
        assert normalized == originals[kind], (
            kind,
            "Only the decoded six-byte transfer and child cache-init displacement may change",
        )

    # The original five-byte host call retains its return PC and activation.
    # Only its destination changes; every nonmatching signature follows the
    # same original classification continuation, without repeating the prefix.
    link = "JS_FrameNativeCallLinkDispatch"
    link_config = "JS_FrameNativeCallLinkConfig"
    for kind, stream in (("masm", masm), ("gas", gas)):
        assert stream.count("call JS_FrameInterpHostDispatch") == 1
        stream[stream.index("call JS_FrameInterpHostDispatch")] = "call " + link
    masm[3:3] = ["EXTERN " + link + ":PROC"]

    # Establish cache lifetime at control-flow commits, not at reusable addresses.
    # All C-created roots/slow children enter this VM prologue. The native child
    # root also enters it. Existing fast constructors zero SF padding63 without extra instructions.
    # A matching owner also requires an explicitly prepared marker63. A return to a live parent cannot equal a dead child.
    entry = "JS_FrameNativeLifetimeEntry"
    created = "JS_FrameNativeLifetimeResume"
    for kind, stream in (("masm", masm), ("gas", gas)):
        old = "lea rdi, interp_table" if kind == "masm" else "lea rdi, [rip+interp_table]"
        assert stream.count(old) == 1
        at = stream.index(old)
        stream[at : at + 1] = [
            "jmp " + ("NEAR PTR " if kind == "masm" else "") + entry,
            "nop",
            "nop",
        ]
        # Assert the existing initialization clears padding63 before every
        # fast publication. Keep these constructors byte-for-byte original.
        begin = stream.index("interp_call_size_ready" + ("::" if kind == "masm" else ":"))
        end = stream.index("interp_call_refs_done" + ("::" if kind == "masm" else ":"))
        assert stream[begin:end].count("mov QWORD PTR [rax+56], 0") == 1
        begin = stream.index("interp_meta_call_size_ready" + ("::" if kind == "masm" else ":"))
        end = stream.index("interp_meta_call_refs_done" + ("::" if kind == "masm" else ":"))
        region = "\n".join(stream[begin:end])
        assert (
            region.count(
                "pxor xmm1, xmm1\nmovq QWORD PTR [rax+40], xmm1\nmovdqu XMMWORD PTR [rax+48], xmm1"
            )
            == 1
        )
        # Generic C Slow can allocate a new JSFrame and return event0 directly
        # to interp_reload, bypassing the native VM entry prologue. Invalidate
        # this transition too. Other dedicated opcode success paths retain the
        # live frame; their exception slow step only unwinds existing frames.
        at = stream.index("interp_slow" + ("::" if kind == "masm" else ":"))
        at = stream.index("call JS_FrameInterpSlow", at)
        assert stream[at + 1] == "test eax, eax"
        assert stream[at + 2] in ("jz interp_reload", "jz NEAR PTR interp_reload")
        stream[at + 2] = "jz " + ("NEAR PTR " if kind == "masm" else "") + created
        path = out / (
            "quickjs-interpreter-owned-win64.asm"
            if kind == "masm"
            else "quickjs-interpreter-owned-win64.S"
        )
        text = path.read_text(encoding="utf-8")
        assert (
            text.count(
                "pxor xmm1, xmm1\nmovq QWORD PTR [rax+40], xmm1\nmovdqu XMMWORD PTR [rax+48], xmm1"
            )
            == 1
        )
        # No edit to this contribution, no extra dispatch jump.
    masm[3:3] = ["PUBLIC interp_table", "EXTERN " + entry + ":PROC", "EXTERN " + created + ":PROC"]
    gas[:0] = [".globl interp_table"]

    shape = "native_slice_shape"
    stack_check = "native_slice_stack_check"
    context_check = [
        "mov r11, QWORD PTR [rcx]",
        "mov r11, QWORD PTR [r11+80]",
        f"mov r11, QWORD PTR [r11+{abi_fields['JSFunctionBytecode.realm']}]",
        f"cmp DWORD PTR [r11+{abi_fields['JSContext.interrupt_counter']}], 1",
        "jle " + fallback,
    ]
    stack_admit = [
        "mov r10, rsp",
        "sub r10, 296",
        f"cmp r10, QWORD PTR [rax+{abi_fields['JSRuntime.stack_limit']}]",
        "jb " + fallback,
    ]
    guards = [
        "jne " + fallback,
        shape + ":",
        "mov r10, QWORD PTR [rdx-16]",
        "SLICE_TARGET",
        f"cmp QWORD PTR [r10+{abi_fields['JSObject.u.cfunc.c_function']}], r11",
        "jne " + legacy,
        f"cmp WORD PTR [r10+{abi_fields['JSObject.u.cfunc.length']}], 2",
        "jne " + legacy,
        "native_slice_descriptor_ready:",
        # Preserve live callee R10 until the legacy missing continuation.
        f"movzx r11d, BYTE PTR [rax+{abi_fields['JSRuntime.module_loader_has_attr'] + 5}]",
        "and r11d, 7",
        "cmp r11b, 0",
        "je " + config,
        "cmp r11b, 2",
        "je " + legacy,
        f"movzx r11d, BYTE PTR [rax+{abi_fields['JSRuntime.current_stack_frame'] - 5}]",
        "and r11d, 11",
        "cmp r11d, 1",
        "jne " + fallback,
        "cmp r8d, 65535",
        "ja " + fallback,
        "mov r11, QWORD PTR [rcx+32]",
        f"cmp r11, QWORD PTR [rcx+{committed}]",
        "jne " + fallback,
        f"movzx r10d, BYTE PTR [rax+{abi_fields['JSRuntime.module_loader_has_attr'] + 5}]",
        "and r10d, 7",
        "cmp r10b, 3",
        "je " + stack_check,
        "cmp r10b, 4",
        "je native_slice_transient_check",
        # Owner equality plus byte63 bit0 is sufficient under the entry/Slow
        # invalidation and original fast-constructor-zeroing protocol.
        # Mode5 retains the geometry chain too, with the same marker check.
        "mov r11, QWORD PTR [rcx]",
        f"cmp r11, QWORD PTR [rcx+{owner}]",
        "jne native_slice_reuse_cold",
        "test BYTE PTR [r11+63], 1",
        "jz native_slice_reuse_cold",
        "cmp r10b, 5",
        "jne native_slice_reuse_hot",
        "mov r10, QWORD PTR [r11+32]",
        f"cmp r10, QWORD PTR [rcx+{variables}]",
        "jne native_slice_reuse_cold",
        "mov r10, QWORD PTR [r11+80]",
        f"mov r10, QWORD PTR [r10+{abi_fields['JSFunctionBytecode.var_count']}]",
        f"cmp r10, QWORD PTR [rcx+{bytecode}]",
        "jne native_slice_reuse_cold",
        "mov r10d, DWORD PTR [r11+120]",
        f"cmp r10d, DWORD PTR [rcx+{size}]",
        "jb native_slice_reuse_cold",
        # The C window is already charged. The remaining168 makes the same
        # admission margin as296 before a new128-byte reservation.
        "native_slice_reuse_hot:",
        "mov r10, rsp",
        "sub r10, 168",
        f"cmp r10, QWORD PTR [rax+{abi_fields['JSRuntime.stack_limit']}]",
        "jb " + fallback,
        *context_check,
        "jmp " + vm_select,
        "native_slice_reuse_cold:",
        *stack_admit,
        *context_check,
        "jmp " + prepare,
        "native_slice_transient_check:",
        *stack_admit,
        "mov r10, QWORD PTR [rcx+8]",
        "mov r11, QWORD PTR [r10+8]",
        "sub r11, QWORD PTR [r10+16]",
        "cmp r11, 128",
        "jb " + stack_check,
        *context_check,
        "jmp " + transient,
        stack_check + ":",
        *stack_admit,
        *context_check,
        "jmp " + stack_native,
    ]
    prepares = [
        "movq xmm0, rax",
        "movq xmm1, r9",
        "movd xmm3, r8d",
        "mov r10, QWORD PTR [rcx]",
        "mov r11, QWORD PTR [r10+80]",
        # Last declared local/operand/capture byte, independent of cleanup
        # owned_args (the allocated argument prefix can be larger).
        f"movzx eax, WORD PTR [r11+{abi_fields['JSFunctionBytecode.var_count']}]",
        f"movzx r9d, WORD PTR [r11+{abi_fields['JSFunctionBytecode.stack_size']}]",
        "add rax, r9",
        "shl rax, 4",
        "add rax, QWORD PTR [r10+32]",
        f"movzx r9d, WORD PTR [r11+{abi_fields['JSFunctionBytecode.var_ref_count']}]",
        "shl r9, 3",
        "add r9, 15",
        "and r9, -16",
        "add rax, r9",
        "lea r9, [rax+128]",
        "mov r11d, DWORD PTR [r10+120]",
        "add r11, r10",
        "cmp r11, r9",
        "jae native_slice_reuse_ready",
        "sub r9, r11",
        # Original declared bytes must already be owned. No active following
        # frame may be overwritten; no allocator/callback runs in this leaf.
        "cmp r9, 128",
        "ja native_slice_reuse_fallback",
        "mov r11, QWORD PTR [r10+112]",
        "mov r8, QWORD PTR [r11+24]",
        "add r8, QWORD PTR [r11+16]",
        "sub r8, r10",
        "cmp r8d, DWORD PTR [r10+120]",
        "jne native_slice_reuse_fallback",
        "mov r8, QWORD PTR [r11+8]",
        "sub r8, QWORD PTR [r11+16]",
        "cmp r8, r9",
        "jb native_slice_reuse_fallback",
        "add QWORD PTR [r11+16], r9",
        "add DWORD PTR [r10+120], r9d",
        "add QWORD PTR [rcx+32], r9",
        f"add QWORD PTR [rcx+{committed}], r9",
        "mov r11, QWORD PTR [rcx+56]",
        f"add QWORD PTR [r11+{abi_fields['JSRuntime.stack_top']}], r9",
        f"cmp QWORD PTR [r11+{abi_fields['JSRuntime.stack_limit']}], 0",
        "je native_slice_reuse_budget",
        f"add QWORD PTR [r11+{abi_fields['JSRuntime.stack_limit']}], r9",
        "native_slice_reuse_budget:",
        f"mov r9, QWORD PTR [r11+{abi_fields['JSRuntime.stack_limit']}]",
        f"mov QWORD PTR [rcx+{shared_limit}], r9",
        "test r9, r9",
        "jz native_slice_reuse_limit",
        "sub r9, QWORD PTR [rcx+32]",
        "native_slice_reuse_limit:",
        f"mov QWORD PTR [rcx+{native_limit}], r9",
        "native_slice_reuse_ready:",
        "or BYTE PTR [r10+63], 1",
        f"mov QWORD PTR [rcx+{view}], rax",
        f"mov QWORD PTR [rcx+{owner}], r10",
        "mov r11, QWORD PTR [r10+32]",
        f"mov QWORD PTR [rcx+{variables}], r11",
        "mov r11, QWORD PTR [r10+80]",
        "mov r11, QWORD PTR [r11+58]",
        f"mov QWORD PTR [rcx+{bytecode}], r11",
        "lea r11, [rax+128]",
        "sub r11, r10",
        f"mov QWORD PTR [rcx+{size}], r11",
        "movq rax, xmm0",
        "movq r9, xmm1",
        "movd r8d, xmm3",
        *context_check,
        "jmp " + vm_select,
        "native_slice_reuse_fallback:",
        "movq rax, xmm0",
        "movq r9, xmm1",
        "movd r8d, xmm3",
        *context_check,
        "jmp " + stack_native,
    ]
    configs = [
        "sub rsp, 88",
        "native_slice_config_alloc:",
        "mov QWORD PTR [rsp+32], rcx",
        "mov QWORD PTR [rsp+40], rdx",
        "mov QWORD PTR [rsp+48], r8",
        "mov QWORD PTR [rsp+56], r9",
        "mov QWORD PTR [rsp+64], rax",
        "SLICE_ENV",
        "test rax, rax",
        "jnz native_slice_disabled",
        "ARENA_ENV",
        "test rax, rax",
        "jnz native_slice_stack_disabled",
        "REUSE_ENV",
        "test rax, rax",
        "jnz native_slice_reuse_disabled",
        "LIFETIME_ENV",
        "test rax, rax",
        "setne cl",
        "movzx ecx, cl",
        "lea ecx, [rcx*4+1]",
        "jmp native_slice_mode_ready",
        "native_slice_reuse_disabled:",
        "mov cl, 4",
        "jmp native_slice_mode_ready",
        "native_slice_stack_disabled:",
        "mov cl, 3",
        "jmp native_slice_mode_ready",
        "native_slice_disabled:",
        "mov cl, 2",
        "native_slice_mode_ready:",
        "mov rax, QWORD PTR [rsp+64]",
        f"mov ch, BYTE PTR [rax+{abi_fields['JSRuntime.module_loader_has_attr'] + 5}]",
        "and ch, 248",
        "or cl, ch",
        f"mov BYTE PTR [rax+{abi_fields['JSRuntime.module_loader_has_attr'] + 5}], cl",
        "mov rcx, QWORD PTR [rsp+32]",
        "mov rdx, QWORD PTR [rsp+40]",
        "mov r8, QWORD PTR [rsp+48]",
        "mov r9, QWORD PTR [rsp+56]",
        "add rsp, 88",
        "jmp " + shape,
    ]
    arena = [
        "push rbx",
        "native_slice_push_rbx:",
        "push rbp",
        "native_slice_push_rbp:",
        "push rsi",
        "native_slice_push_rsi:",
        "sub rsp, 32",
        "native_slice_alloc:",
        "mov rbx, rcx",
        "mov rbp, rax",
        f"dec DWORD PTR [r11+{abi_fields['JSContext.interrupt_counter']}]",
        # The record is not a JSFrame; state.frame and the caller's ownership
        # remain untouched. Shared reentry starts after the reserved C record.
        "mov r10, QWORD PTR [rbx+8]",
        "mov rsi, QWORD PTR [r10+24]",
        "add rsi, QWORD PTR [r10+16]",
        "add QWORD PTR [r10+16], 128",
        f"add QWORD PTR [rbp+{abi_fields['JSRuntime.stack_top']}], 128",
        f"cmp QWORD PTR [rbp+{abi_fields['JSRuntime.stack_limit']}], 0",
        "je native_slice_charged",
        f"add QWORD PTR [rbp+{abi_fields['JSRuntime.stack_limit']}], 128",
        "native_slice_charged:",
        f"mov rax, QWORD PTR [rbp+{abi_fields['JSRuntime.current_stack_frame']}]",
        "mov QWORD PTR [rsi], rax",
        "movdqu xmm2, XMMWORD PTR [rdx-16]",
        "movdqu XMMWORD PTR [rsi+8], xmm2",
        "mov QWORD PTR [rsi+24], rdx",
        "xorps xmm2, xmm2",
        "movdqu XMMWORD PTR [rsi+32], xmm2",
        "movdqu XMMWORD PTR [rsi+48], xmm2",
        "movdqu XMMWORD PTR [rsi+64], xmm2",
        "mov WORD PTR [rsi+58], r8w",
        "UNDEFINED_CELL",
        "test r9b, r9b",
        "jz native_slice_this_ready",
        "lea rax, [rdx-32]",
        "native_slice_this_ready:",
        "mov QWORD PTR [rsi+32], rax",
        "ARENA_TLS",
        "mov QWORD PTR [rsi+104], r10",
        "mov rax, QWORD PTR [r10]",
        "mov QWORD PTR [rsi+80], rax",
        "mov QWORD PTR [rsi+88], rbx",
        "mov DWORD PTR [rsi+96], 0",
        f"mov al, BYTE PTR [rbp+{abi_fields['JSRuntime.current_stack_frame'] - 5}]",
        "and al, 4",
        "mov BYTE PTR [rsi+112], al",
        f"mov QWORD PTR [rbp+{abi_fields['JSRuntime.current_stack_frame']}], rsi",
        "lea rax, [rsi+80]",
        f"or BYTE PTR [rbp+{abi_fields['JSRuntime.current_stack_frame'] - 5}], 4",
        "mov QWORD PTR [r10], rax",
        *(["NATIVE_ARENA_COUNT"] if diagnostics else []),
        "mov rcx, rsi",
        "lea rdx, [rbx+40]",
        "call JS_FrameBuiltinNative",
        "cmp QWORD PTR [rbx+48], 6",
        f"sete BYTE PTR [rbx+{exception}]",
        "mov r10, QWORD PTR [rsi+104]",
        "mov rax, QWORD PTR [rsi+80]",
        "mov QWORD PTR [r10], rax",
        f"mov al, BYTE PTR [rbp+{abi_fields['JSRuntime.current_stack_frame'] - 5}]",
        "and al, 251",
        "or al, BYTE PTR [rsi+112]",
        f"mov BYTE PTR [rbp+{abi_fields['JSRuntime.current_stack_frame'] - 5}], al",
        "mov rax, QWORD PTR [rsi]",
        f"mov QWORD PTR [rbp+{abi_fields['JSRuntime.current_stack_frame']}], rax",
        "mov r10, QWORD PTR [rbx+8]",
        "sub QWORD PTR [r10+16], 128",
        f"sub QWORD PTR [rbp+{abi_fields['JSRuntime.stack_top']}], 128",
        f"cmp QWORD PTR [rbp+{abi_fields['JSRuntime.stack_limit']}], 0",
        "je native_slice_released",
        f"sub QWORD PTR [rbp+{abi_fields['JSRuntime.stack_limit']}], 128",
        "native_slice_released:",
        "mov rax, QWORD PTR [rbx+32]",
        f"mov rdx, QWORD PTR [rbp+{abi_fields['JSRuntime.stack_limit']}]",
        f"cmp rax, QWORD PTR [rbx+{committed}]",
        "jne native_slice_refresh",
        f"cmp rdx, QWORD PTR [rbx+{shared_limit}]",
        "je native_slice_done",
        "native_slice_refresh:",
        f"mov QWORD PTR [rbx+{committed}], rax",
        f"mov QWORD PTR [rbx+{shared_limit}], rdx",
        "test rdx, rdx",
        "jz native_slice_limit",
        "sub rdx, rax",
        "native_slice_limit:",
        f"mov QWORD PTR [rbx+{native_limit}], rdx",
        "native_slice_done:",
        f"movzx eax, BYTE PTR [rbx+{exception}]",
        "native_slice_epilogue:",
        "add rsp, 32",
        "pop rsi",
        "pop rbp",
        "pop rbx",
        "ret",
    ]
    # Same56-byte bridge; the owned caller window is popped by existing JS
    # native/slow/tail-return cleanup. Its contents are live only during C.
    # Reinitialize SF null fields because other argument windows can reuse it.
    reusable = list(arena)
    a = reusable.index("mov r10, QWORD PTR [rbx+8]")
    b = reusable.index(f"mov rax, QWORD PTR [rbp+{abi_fields['JSRuntime.current_stack_frame']}]", a)
    reusable[a:b] = [f"mov rsi, QWORD PTR [rbx+{view}]"]
    a = reusable.index("mov r10, QWORD PTR [rbx+8]")
    b = reusable.index("mov rax, QWORD PTR [rbx+32]", a)
    reusable[a:b] = []
    transient_body = [x.replace("native_slice_", "native_slice_transient_") for x in arena]
    # A code-address/signature descriptor has no weak object-address cache.
    # The callee remains rooted in original operands; its live realm is loaded
    # by the builtin. JS cannot mutate the private cfunc signature fields.
    direct_host = 2297 if diagnostics else 161
    link_body = [
        "mov rax, QWORD PTR [rcx+56]",
        f"test BYTE PTR [rax+{abi_fields['JSRuntime.module_loader_has_attr'] + 5}], 128",
        "jz native_call_link_control",
        f"test BYTE PTR [rax+{abi_fields['JSRuntime.module_loader_has_attr'] + 5}], 16",
        "jnz native_call_link_control",
        f"cmp BYTE PTR [rcx+{direct_host}], 0",
        "je native_call_link_legacy",
        "cmp QWORD PTR [rdx-8], -1",
        "jne native_call_link_legacy",
        "mov r10, QWORD PTR [rdx-16]",
        f"cmp WORD PTR [r10+{abi_fields['JSObject.class_id']}], 12",
        "jne native_call_link_legacy",
        f"cmp WORD PTR [r10+{abi_fields['JSObject.u.cfunc.length']}], 2",
        "jne native_call_link_number",
        "SLICE_TARGET",
        f"cmp QWORD PTR [r10+{abi_fields['JSObject.u.cfunc.c_function']}], r11",
        "jne native_call_link_ordinary",
        # First descriptor covers the existing argc0/1 native-view ABI only.
        "cmp r8d, 1",
        "ja native_call_link_ordinary",
        "jmp native_call_link_eligible",
        # Only actual argc0: native-off resumes the original missing-argument
        # continuation, which requires actual < formal (Number formal=1).
        "native_call_link_number:",
        f"cmp WORD PTR [r10+{abi_fields['JSObject.u.cfunc.length']}], 257",
        "jne native_call_link_ordinary",
        f"cmp WORD PTR [r10+{abi_fields['JSObject.u.cfunc.magic']}], 0",
        "jne native_call_link_ordinary",
        "test r8d, r8d",
        "jnz native_call_link_ordinary",
        f"test BYTE PTR [rax+{abi_fields['JSRuntime.module_loader_has_attr'] + 5}], 32",
        "jnz native_call_link_ordinary",
        "NUMBER_TARGET",
        f"cmp QWORD PTR [r10+{abi_fields['JSObject.u.cfunc.c_function']}], r11",
        "jne native_call_link_ordinary",
        "native_call_link_eligible:",
        # Guard's mode2 legacy transfer inherits this eligibility too. A
        # direct/unshared runtime must resume HostDirectGate classification,
        # never jump into the missing-window continuation out of context.
        f"movzx r11d, BYTE PTR [rax+{abi_fields['JSRuntime.current_stack_frame'] - 5}]",
        "and r11d, 11",
        "cmp r11d, 1",
        "jne native_call_link_ordinary",
        # Preserve generic/window controls and their original lazy bootstrap.
        f"cmp BYTE PTR [rax+{abi_fields['JSRuntime.module_normalize_has_attr'] + 1}], 1",
        "jne native_call_link_ordinary",
        f"cmp BYTE PTR [rax+{abi_fields['JSRuntime.module_normalize_has_attr'] + 2}], 1",
        "jne native_call_link_ordinary",
        "jmp native_slice_descriptor_ready",
        "native_call_link_ordinary:",
        "mov rax, r10",
        f"cmp BYTE PTR [r10+{abi_fields['JSObject.u.cfunc.cproto']}], 1",
        "ja JS_FrameInterpNumericEntry",
        "jmp JS_FrameInterpHostDirectGate",
        "native_call_link_legacy:",
        "jmp JS_FrameInterpHostGate",
        "native_call_link_control:",
        f"test BYTE PTR [rax+{abi_fields['JSRuntime.module_loader_has_attr'] + 5}], 128",
        "jz " + link_config,
        "jmp JS_FrameInterpHostDispatch",
    ]
    # Only byte1365 belongs to this native family. Bits0..2 are the window
    # mode, bit3 VM-off, bit4 link-off, bit5 Number-off, bit7 initialized.
    # Bytes1362/1363/1364 already belong to null validation/add_loc/slot free.
    link_config_body = [
        "sub rsp, 88",
        "native_call_link_config_alloc:",
        "mov QWORD PTR [rsp+32], rcx",
        "mov QWORD PTR [rsp+40], rdx",
        "mov QWORD PTR [rsp+48], r8",
        "mov QWORD PTR [rsp+56], r9",
        "mov QWORD PTR [rsp+64], rax",
        "mov BYTE PTR [rsp+72], 128",
        "LINK_ENV",
        "test rax, rax",
        "setne cl",
        "shl cl, 4",
        "or BYTE PTR [rsp+72], cl",
        "VM_ENV",
        "test rax, rax",
        "setne cl",
        "shl cl, 3",
        "or BYTE PTR [rsp+72], cl",
        "NUMBER_ENV",
        "test rax, rax",
        "setne cl",
        "shl cl, 5",
        "or BYTE PTR [rsp+72], cl",
        "mov rax, QWORD PTR [rsp+64]",
        f"mov cl, BYTE PTR [rax+{abi_fields['JSRuntime.module_loader_has_attr'] + 5}]",
        "and cl, 7",
        "or cl, BYTE PTR [rsp+72]",
        f"mov BYTE PTR [rax+{abi_fields['JSRuntime.module_loader_has_attr'] + 5}], cl",
        "mov rcx, QWORD PTR [rsp+32]",
        "mov rdx, QWORD PTR [rsp+40]",
        "mov r8, QWORD PTR [rsp+48]",
        "mov r9, QWORD PTR [rsp+56]",
        "add rsp, 88",
        "jmp " + link,
    ]
    # RBX is already the VM state. Compiled C preserves all nonvolatile VM
    # registers; the bridge itself writes none. A mismatch keeps the old ABI.
    vm_select_body = [
        f"test BYTE PTR [rax+{abi_fields['JSRuntime.module_loader_has_attr'] + 5}], 8",
        "jz " + vm_bridge,
        "jmp " + native,
    ]
    vm_body = [
        "cmp rbx, rcx",
        "jne " + native,
        "sub rsp, 40",
        "native_vm_alloc:",
        f"dec DWORD PTR [r11+{abi_fields['JSContext.interrupt_counter']}]",
        f"mov r10, QWORD PTR [rbx+{view}]",
        f"mov r11, QWORD PTR [rax+{abi_fields['JSRuntime.current_stack_frame']}]",
        "mov QWORD PTR [r10], r11",
        "movdqu xmm2, XMMWORD PTR [rdx-16]",
        "movdqu XMMWORD PTR [r10+8], xmm2",
        "mov QWORD PTR [r10+24], rdx",
        "xorps xmm2, xmm2",
        "movdqu XMMWORD PTR [r10+32], xmm2",
        "movdqu XMMWORD PTR [r10+48], xmm2",
        "movdqu XMMWORD PTR [r10+64], xmm2",
        "mov WORD PTR [r10+58], r8w",
        "VM_UNDEFINED",
        "test r9b, r9b",
        "jz native_vm_this_ready",
        "lea r11, [rdx-32]",
        "native_vm_this_ready:",
        "mov QWORD PTR [r10+32], r11",
        "VM_TLS",
        "mov QWORD PTR [r10+104], r11",
        "mov rcx, QWORD PTR [r11]",
        "mov QWORD PTR [r10+80], rcx",
        "mov QWORD PTR [r10+88], rbx",
        "mov DWORD PTR [r10+96], 0",
        f"mov cl, BYTE PTR [rax+{abi_fields['JSRuntime.current_stack_frame'] - 5}]",
        "and cl, 4",
        "mov BYTE PTR [r10+112], cl",
        f"mov QWORD PTR [rax+{abi_fields['JSRuntime.current_stack_frame']}], r10",
        "lea rcx, [r10+80]",
        f"or BYTE PTR [rax+{abi_fields['JSRuntime.current_stack_frame'] - 5}], 4",
        "mov QWORD PTR [r11], rcx",
        *(["NATIVE_VM_COUNT"] if diagnostics else []),
        "mov rcx, r10",
        "lea rdx, [rbx+40]",
        "call JS_FrameBuiltinNative",
        # Reentry has its own register state (shared C and native child paths).
        # The active parent's window is owned/charged and cache.view is stable.
        f"mov r10, QWORD PTR [rbx+{view}]",
        "mov r11, QWORD PTR [rbx+56]",
        "cmp QWORD PTR [rbx+48], 6",
        f"sete BYTE PTR [rbx+{exception}]",
        "mov rdx, QWORD PTR [r10+104]",
        "mov rax, QWORD PTR [r10+80]",
        "mov QWORD PTR [rdx], rax",
        f"mov al, BYTE PTR [r11+{abi_fields['JSRuntime.current_stack_frame'] - 5}]",
        "and al, 251",
        "or al, BYTE PTR [r10+112]",
        f"mov BYTE PTR [r11+{abi_fields['JSRuntime.current_stack_frame'] - 5}], al",
        "mov rax, QWORD PTR [r10]",
        f"mov QWORD PTR [r11+{abi_fields['JSRuntime.current_stack_frame']}], rax",
        "mov rax, QWORD PTR [rbx+32]",
        f"mov rdx, QWORD PTR [r11+{abi_fields['JSRuntime.stack_limit']}]",
        f"cmp rax, QWORD PTR [rbx+{committed}]",
        "jne native_vm_refresh",
        f"cmp rdx, QWORD PTR [rbx+{shared_limit}]",
        "je native_vm_done",
        "native_vm_refresh:",
        f"mov QWORD PTR [rbx+{committed}], rax",
        f"mov QWORD PTR [rbx+{shared_limit}], rdx",
        "test rdx, rdx",
        "jz native_vm_limit",
        "sub rdx, rax",
        "native_vm_limit:",
        f"mov QWORD PTR [rbx+{native_limit}], rdx",
        "native_vm_done:",
        f"movzx eax, BYTE PTR [rbx+{exception}]",
        "add rsp, 40",
        "ret",
    ]
    m = [
        "OPTION CASEMAP:NONE",
        "OPTION DOTNAME",
        "EXTERN " + fallback + ":PROC",
        "EXTERN " + legacy + ":BYTE",
        "EXTERN JS_FrameInterpHostDispatch:PROC",
        "EXTERN JS_FrameInterpHostGate:PROC",
        "EXTERN JS_FrameInterpHostDirectGate:PROC",
        "EXTERN JS_FrameInterpNumericEntry:PROC",
        "EXTERN qjs_frame_core_js_string_slice:PROC",
        "EXTERN qjs_frame_core_js_number_toString:PROC",
        "EXTERN JS_FrameBuiltinNative:PROC",
        "EXTERN _tls_index:DWORD",
        "EXTERN js_frame_shared_top:BYTE",
        "EXTERN __imp_getenv:QWORD",
        "EXTERN interp_reload:BYTE",
        "EXTERN interp_table:QWORD",
        "EXTERN JS_FrameInterpPropertyCold_unwind:BYTE",
        ".qjsprop SEGMENT ALIGN(4) 'CODE'",
    ]
    g = [".intel_syntax noprefix", '.section .qjsprop,"xr"']
    roots = (
        guard,
        native,
        transient,
        stack_native,
        config,
        prepare,
        link,
        link_config,
        vm_select,
        vm_bridge,
    )
    entry_body = [f"mov QWORD PTR [rbx+{owner}], 0", "ENTRY_TABLE", "jmp interp_reload"]
    created_body = [f"mov QWORD PTR [rbx+{owner}], 0", "jmp interp_reload"]
    for name, lines in (
        (guard, guards),
        (native, reusable),
        (transient, transient_body),
        (stack_native, None),
        (config, configs),
        (prepare, prepares),
        (entry, entry_body),
        (created, created_body),
        (link, link_body),
        (link_config, link_config_body),
        (vm_select, vm_select_body),
        (vm_bridge, vm_body),
    ):
        m += ["ALIGN 4", "PUBLIC " + name + ", " + name + "_end", name + " PROC"]
        g += [
            ".p2align 2",
            ".globl " + name + ", " + name + "_end",
            ".def " + name + "; .scl 2; .type 32; .endef",
            name + ":",
        ]
        for kind, stream in (("masm", m), ("gas", g)):
            body = (
                lines
                if lines is not None
                else [x.replace("native_slice_", "native_slice_stack_") for x in bodies[kind]]
            )
            for x in body:
                if x == "SLICE_TARGET":
                    stream += [
                        "lea r11, "
                        + (
                            "qjs_frame_core_js_string_slice"
                            if kind == "masm"
                            else "[rip+qjs_frame_core_js_string_slice]"
                        )
                    ]
                elif x == "NUMBER_TARGET":
                    stream += [
                        "lea r11, "
                        + (
                            "qjs_frame_core_js_number_toString"
                            if kind == "masm"
                            else "[rip+qjs_frame_core_js_number_toString]"
                        )
                    ]
                elif x == "ENTRY_TABLE":
                    stream += [
                        "lea rdi, interp_table" if kind == "masm" else "lea rdi, [rip+interp_table]"
                    ]
                elif x in (
                    "SLICE_ENV",
                    "ARENA_ENV",
                    "REUSE_ENV",
                    "LIFETIME_ENV",
                    "LINK_ENV",
                    "VM_ENV",
                    "NUMBER_ENV",
                ):
                    target = {
                        "SLICE_ENV": "JS_FrameNativeSliceDisable",
                        "ARENA_ENV": "JS_FrameNativeArenaDisable",
                        "REUSE_ENV": "JS_FrameNativeReuseDisable",
                        "LIFETIME_ENV": "JS_FrameNativeLifetimeDisable",
                        "LINK_ENV": "JS_FrameNativeCallLinkDisable",
                        "VM_ENV": "JS_FrameNativeVMDisable",
                        "NUMBER_ENV": "JS_FrameNativeNumberDisable",
                    }[x]
                    stream += (
                        ["lea rcx, " + target, "call QWORD PTR [__imp_getenv]"]
                        if kind == "masm"
                        else ["lea rcx, [rip+" + target + "]", "call getenv"]
                    )
                elif x == "VM_UNDEFINED":
                    stream += [
                        "lea r11, "
                        + (
                            "JS_FrameNativeUndefined"
                            if kind == "masm"
                            else "[rip+JS_FrameNativeUndefined]"
                        )
                    ]
                elif x == "VM_TLS":
                    stream += (
                        [
                            "mov r11, QWORD PTR gs:[88]",
                            "mov ecx, DWORD PTR [_tls_index]",
                            "mov r11, QWORD PTR [r11+rcx*8]",
                            "mov ecx, SECTIONREL js_frame_shared_top",
                            "add r11, rcx",
                        ]
                        if kind == "masm"
                        else [
                            "mov r11, QWORD PTR gs:88",
                            "mov ecx, DWORD PTR [rip+_tls_index]",
                            "mov r11, QWORD PTR [r11+rcx*8]",
                            "lea rcx, [rip+JS_FrameSharedTop]",
                            "lea rdx, [rip+_tls_start]",
                            "sub rcx, rdx",
                            "add r11, rcx",
                        ]
                    )
                elif x in ("NATIVE_STACK_COUNT", "NATIVE_ARENA_COUNT", "NATIVE_VM_COUNT"):
                    cell = {
                        "NATIVE_STACK_COUNT": "rsp+56",
                        "NATIVE_ARENA_COUNT": "rsi+8",
                        "NATIVE_VM_COUNT": "r10+8",
                    }[x]
                    magic = name + "_count_magic"
                    done = name + "_count_done"
                    stream += [
                        "inc QWORD PTR [rbx+2208]",
                        f"mov rax, QWORD PTR [{cell}]",
                        f"cmp BYTE PTR [rax+{abi_fields['JSObject.u.cfunc.cproto']}], 1",
                        "je " + magic,
                        "inc QWORD PTR [rbx+2392]",
                        "jmp " + done,
                        magic + ":",
                        "inc QWORD PTR [rbx+2400]",
                        done + ":",
                    ]
                elif x == "UNDEFINED_CELL":
                    stream += [
                        "lea rax, "
                        + (
                            "JS_FrameNativeUndefined"
                            if kind == "masm"
                            else "[rip+JS_FrameNativeUndefined]"
                        )
                    ]
                elif x == "ARENA_TLS":
                    stream += (
                        [
                            "mov rax, QWORD PTR gs:[88]",
                            "mov ecx, DWORD PTR [_tls_index]",
                            "mov rax, QWORD PTR [rax+rcx*8]",
                            "mov ecx, SECTIONREL js_frame_shared_top",
                            "lea r10, [rax+rcx]",
                        ]
                        if kind == "masm"
                        else [
                            "mov rax, QWORD PTR gs:88",
                            "mov ecx, DWORD PTR [rip+_tls_index]",
                            "mov rax, QWORD PTR [rax+rcx*8]",
                            "lea rcx, [rip+JS_FrameSharedTop]",
                            "lea r11, [rip+_tls_start]",
                            "sub rcx, r11",
                            "lea r10, [rax+rcx]",
                        ]
                    )
                elif x.endswith(":"):
                    label = x[:-1]
                    stream += (
                        ["PUBLIC " + label, label + "::"]
                        if kind == "masm"
                        else [".globl " + label, label + ":"]
                    )
                else:
                    if kind == "masm":
                        for target in (fallback, legacy):
                            x = x.replace(" " + target, " NEAR PTR " + target)
                    stream.append(x)
        m += [name + "_end LABEL BYTE", name + " ENDP"]
        g += [name + "_end:"]
    m += ["ALIGN 4", guard + "_unwind LABEL BYTE", "DB 1, 0, 0, 0"]
    g += [".p2align 2", guard + "_unwind:", ".byte 1, 0, 0, 0"]
    for name, prefix, allocation in (
        (native, "native_slice_", 32),
        (transient, "native_slice_transient_", 32),
        (stack_native, "native_slice_stack_", 208),
    ):
        m += [
            name + "_unwind LABEL BYTE",
            "DB 1, "
            + prefix
            + "alloc - "
            + name
            + ", "
            + ("4" if allocation == 32 else "5")
            + ", 0",
        ]
        g += [
            name + "_unwind:",
            ".byte 1, "
            + prefix
            + "alloc - "
            + name
            + ", "
            + ("4" if allocation == 32 else "5")
            + ", 0",
        ]
        if allocation == 32:
            m += ["DB " + prefix + "alloc - " + name + ", 50"]
            g += [".byte " + prefix + "alloc - " + name + ", 50"]
        else:
            m += ["DB " + prefix + "alloc - " + name + ", 1", "DW 26"]
            g += [".byte " + prefix + "alloc - " + name + ", 1", ".short 26"]
        for reg, op in (("rsi", 96), ("rbp", 80), ("rbx", 48)):
            m += ["DB " + prefix + "push_" + reg + " - " + name + ", " + str(op)]
            g += [".byte " + prefix + "push_" + reg + " - " + name + ", " + str(op)]
        if allocation == 208:
            m += ["DB 0, 0"]
            g += [".short 0"]
    m += [
        config + "_unwind LABEL BYTE",
        "DB 1, native_slice_config_alloc - " + config + ", 1, 0",
        "DB native_slice_config_alloc - " + config + ", 162",
        "DB 0, 0",
    ]
    g += [
        config + "_unwind:",
        ".byte 1, native_slice_config_alloc - " + config + ", 1, 0",
        ".byte native_slice_config_alloc - " + config + ", 162",
        ".short 0",
    ]
    m += [prepare + "_unwind LABEL BYTE", "DB 1, 0, 0, 0"]
    g += [prepare + "_unwind:", ".byte 1, 0, 0, 0"]
    m += [
        "ALIGN 4",
        link + "_unwind LABEL BYTE",
        "DB 1, 0, 0, 0",
        link_config + "_unwind LABEL BYTE",
        "DB 1, native_call_link_config_alloc - " + link_config + ", 1, 0",
        "DB native_call_link_config_alloc - " + link_config + ", 162",
        "DB 0, 0",
    ]
    g += [
        ".p2align 2",
        link + "_unwind:",
        ".byte 1, 0, 0, 0",
        link_config + "_unwind:",
        ".byte 1, native_call_link_config_alloc - " + link_config + ", 1, 0",
        ".byte native_call_link_config_alloc - " + link_config + ", 162",
        ".short 0",
    ]
    m += [
        "ALIGN 4",
        vm_select + "_unwind LABEL BYTE",
        "DB 1, 0, 0, 0",
        vm_bridge + "_unwind LABEL BYTE",
        "DB 1, native_vm_alloc - " + vm_bridge + ", 1, 0",
        "DB native_vm_alloc - " + vm_bridge + ", 66",
        "DB 0, 0",
    ]
    g += [
        ".p2align 2",
        vm_select + "_unwind:",
        ".byte 1, 0, 0, 0",
        vm_bridge + "_unwind:",
        ".byte 1, native_vm_alloc - " + vm_bridge + ", 1, 0",
        ".byte native_vm_alloc - " + vm_bridge + ", 66",
        ".short 0",
    ]
    for name, value in (
        ("JS_FrameNativeNumberDisable", "QJS_DISABLE_NATIVE_NUMBER_FRAME"),
        ("JS_FrameNativeVMDisable", "QJS_DISABLE_NATIVE_VM_BRIDGE"),
        ("JS_FrameNativeCallLinkDisable", "QJS_DISABLE_NATIVE_CALL_LINK"),
        ("JS_FrameNativeSliceDisable", "QJS_DISABLE_NATIVE_SLICE"),
        ("JS_FrameNativeArenaDisable", "QJS_DISABLE_NATIVE_FRAME_ARENA"),
        ("JS_FrameNativeReuseDisable", "QJS_DISABLE_NATIVE_FRAME_REUSE"),
        ("JS_FrameNativeLifetimeDisable", "QJS_DISABLE_NATIVE_FRAME_LIFETIME"),
    ):
        m += ["PUBLIC " + name, name + " LABEL BYTE", 'DB "' + value + '", 0']
        g += [".globl " + name, name + ":", '.asciz "' + value + '"']
    m += [
        "ALIGN 16",
        "PUBLIC JS_FrameNativeUndefined",
        "JS_FrameNativeUndefined LABEL BYTE",
        "DQ 0, 3",
        ".qjsprop ENDS",
        ".pdata$zzzzzznativeslice SEGMENT ALIGN(4) READONLY 'DATA'",
    ]
    g += [
        ".p2align 4",
        ".globl JS_FrameNativeUndefined",
        "JS_FrameNativeUndefined:",
        ".quad 0, 3",
        '.section .pdata$zzzzzznativeslice,"dr"',
        ".p2align 2",
    ]
    for name in roots:
        m += ["DD IMAGEREL " + name + ", IMAGEREL " + name + "_end, IMAGEREL " + name + "_unwind"]
        g += [".rva " + name + ", " + name + "_end, " + name + "_unwind"]
    for name in (entry, created):
        m += [
            "DD IMAGEREL "
            + name
            + ", IMAGEREL "
            + name
            + "_end, IMAGEREL JS_FrameInterpPropertyCold_unwind"
        ]
        g += [".rva " + name + ", " + name + "_end, JS_FrameInterpPropertyCold_unwind"]
    m += [".pdata$zzzzzznativeslice ENDS", "END"]
    (out / "quickjs-interpreter-native-slice-win64.asm").write_text(
        "\n".join(m) + "\n", encoding="utf-8"
    )
    # Matched native slots isolate the context ABI from entry placement.
    # Padding follows the actual _end, so no dead PC is added to unwind.
    capacities = {
        False: {
            "JS_FrameNativeSliceGuard": 444,
            "JS_FrameNativeSliceTrampoline": 320,
            "JS_FrameNativeSliceTransientTrampoline": 412,
            "JS_FrameNativeSliceStackTrampoline": 384,
            "JS_FrameNativeSliceConfig": 172,
            "JS_FrameNativeSliceReusePrepare": 348,
            "JS_FrameNativeLifetimeEntry": 20,
            "JS_FrameNativeLifetimeResume": 16,
            "JS_FrameNativeCallLinkDispatch": 224,
            "JS_FrameNativeCallLinkConfig": 164,
            "JS_FrameNativeVMSelect": 16,
            "JS_FrameNativeVMTrampoline": 332,
        },
        True: {
            "JS_FrameNativeSliceGuard": 456,
            "JS_FrameNativeSliceTrampoline": 372,
            "JS_FrameNativeSliceTransientTrampoline": 460,
            "JS_FrameNativeSliceStackTrampoline": 440,
            "JS_FrameNativeSliceConfig": 172,
            "JS_FrameNativeSliceReusePrepare": 376,
            "JS_FrameNativeLifetimeEntry": 24,
            "JS_FrameNativeLifetimeResume": 16,
            "JS_FrameNativeCallLinkDispatch": 224,
            "JS_FrameNativeCallLinkConfig": 164,
            "JS_FrameNativeVMSelect": 16,
            "JS_FrameNativeVMTrampoline": 388,
        },
    }
    fixed = []
    for line in g:
        fixed.append(line)
        if line.endswith("_end:") and line[:-5] in capacities[diagnostics]:
            name = line[:-5]
            fixed.append(".org " + name + "+" + str(capacities[diagnostics][name]) + ", 0x90")
    g = fixed
    # Restore established lifetime/control entries without moving AZ Link/VM.
    # The stack fallback is cold in production; all of its instructions stay.
    restore_delta = {False: 40, True: 44}[diagnostics]
    stack = "JS_FrameNativeSliceStackTrampoline"
    block_start = g.index(stack + ":") - 3
    assert g[block_start : block_start + 3] == [
        ".p2align 2",
        ".globl " + stack + ", " + stack + "_end",
        ".def " + stack + "; .scl 2; .type 32; .endef",
    ]
    block_end = g.index(".org " + stack + "+" + str(capacities[diagnostics][stack]) + ", 0x90") + 1
    cold_stack = g[block_start:block_end]
    g[block_start:block_end] = [
        ".fill " + str(capacities[diagnostics][stack] - restore_delta) + ", 1, 0x90"
    ]
    resume = "JS_FrameNativeLifetimeResume"
    at = g.index(".org " + resume + "+" + str(capacities[diagnostics][resume]) + ", 0x90") + 1
    g[at:at] = [".fill " + str(restore_delta) + ", 1, 0x90"]
    vm = "JS_FrameNativeVMTrampoline"
    at = g.index(".org " + vm + "+" + str(capacities[diagnostics][vm]) + ", 0x90") + 1
    g[at:at] = (
        ['.section .qjsvm$zzzzzznativefallback,"xr"'] + cold_stack + ['.section .qjsprop,"xr"']
    )
    # Private sort entry owns admission; ordinary C->JS uses the original CMP.
    # Retain the old islands and labels for an isolated five-byte ablation.
    begin = gas.index("JS_FrameChildFast:")
    end = gas.index("JS_FrameChildFast_end:")
    at = gas.index("cmp DWORD PTR [r8+8], -1", begin, end)
    gas[at : at + 1] = [
        "cmp DWORD PTR [r8+8], -1",
        ".globl JS_FrameCachedChildClassifyContinue",
        "JS_FrameCachedChildClassifyContinue:",
    ]
    at = gas.index("mov r10, QWORD PTR [rsp+16]", at, end + 3)
    gas[at:at] = [".globl JS_FrameCachedChildGeometryReady", "JS_FrameCachedChildGeometryReady:"]
    owner = 2416 if diagnostics else 96
    g += [
        '.section .qjsvm$zzzzzzsortguard,"xr"',
        ".p2align 4",
        ".globl JS_FrameCachedChildAdmission, JS_FrameCachedChildAdmission_end",
        ".def JS_FrameCachedChildAdmission; .scl 2; .type 32; .endef",
        "JS_FrameCachedChildAdmission:",
        f"mov r11, QWORD PTR [r10+{owner}]",
        "test r11b, 1",
        "jz cached_child_classify",
        "and r11, -4",
        "cmp QWORD PTR [r11], rdx",
        "jne cached_child_classify",
        "cmp DWORD PTR [rsp+48], 2",
        "jne cached_child_classify",
        "cmp DWORD PTR [r8+8], -1",
        "jne cached_child_classify",
        "mov r10, QWORD PTR [r8]",
        "cmp QWORD PTR [r11+8], r10",
        "jne cached_child_classify",
        "mov r10, QWORD PTR [rsp+16]",
        f"test BYTE PTR [r10+{owner}], 2",
        "jnz JS_FramePreparedChildGuard",
        ".globl JS_FrameCachedChildMetadata",
        "JS_FrameCachedChildMetadata:",
        "mov r10, QWORD PTR [r11+24]",
        "mov QWORD PTR [rsp+24], r10",
        "mov r11, QWORD PTR [r11+32]",
        "mov QWORD PTR [rsp+32], r11",
        ".globl JS_FrameCachedChildHit",
        "JS_FrameCachedChildHit:",
        "jmp JS_FrameCachedChildGeometryReady",
        "cached_child_classify:",
        "cmp DWORD PTR [r8+8], -1",
        "jmp JS_FrameCachedChildClassifyContinue",
        "JS_FrameCachedChildAdmission_end:",
        '.section .xdata$zzzzzzsortguard,"dr"',
        ".p2align 2",
        "JS_FrameCachedChildAdmission_unwind:",
        ".byte 1,0,0,0",
        '.section .pdata$zzzzzzzsortguard,"dr"',
        ".p2align 2",
        ".rva JS_FrameCachedChildAdmission, JS_FrameCachedChildAdmission_end, JS_FrameCachedChildAdmission_unwind",
    ]

    # The fixed ChildFast prefix already checked mode/TLS/RT/coherence/argc.
    # A matching tag3 owns a private prepared arena; repeat physical quota/poll
    # admission, retaining the same conservative 4344-byte helper allowance.
    state = 96
    data = 2544 if diagnostics else 272
    commit = 2304 if diagnostics else 64
    limit = 2312 if diagnostics else 72
    shared = 2320 if diagnostics else 80
    exception = 2296 if diagnostics else 160
    g += [
        '.section .qjscall$prepare,"xr"',
        ".p2align 4",
        ".globl JS_FramePreparedChildGuard, JS_FramePreparedChildGuard_end",
        ".def JS_FramePreparedChildGuard; .scl 2; .type 32; .endef",
        "JS_FramePreparedChildGuard:",
        "cmp QWORD PTR [r11+80], 0",
        "jne JS_FrameCachedChildMetadata",
        f"cmp QWORD PTR [r11+{state}], 0",
        "jne JS_FrameCachedChildMetadata",
        "mov rax, rsp",
        "sub rax, 4344",
        "sub rax, QWORD PTR [r11+32]",
        "mov r10, QWORD PTR [rsp+8]",
        f"cmp rax, QWORD PTR [r10+{abi_fields['JSRuntime.stack_limit']}]",
        "jb JS_FrameCachedChildMetadata",
        f"cmp DWORD PTR [rdx+{abi_fields['JSContext.interrupt_counter']}], 1",
        "jle JS_FrameCachedChildMetadata",
        "mov QWORD PTR [rsp+24], r11",
        "jmp JS_FramePreparedChildTrampoline",
        "JS_FramePreparedChildGuard_end:",
        ".p2align 4",
        ".globl JS_FramePreparedChildTrampoline, JS_FramePreparedChildTrampoline_end",
        ".def JS_FramePreparedChildTrampoline; .scl 2; .type 32; .endef",
        "JS_FramePreparedChildTrampoline:",
        "sub rsp, 56",
        ".globl prepared_sort_alloc",
        "prepared_sort_alloc:",
        "mov QWORD PTR [rsp+32], rcx",
        "mov r11, QWORD PTR [rsp+80]",
        "mov QWORD PTR [rsp+40], r11",
        f"dec DWORD PTR [rdx+{abi_fields['JSContext.interrupt_counter']}]",
        f"lea r8, [r11+{data}]",
        f"lea r10, [r11+{state}]",
        "movdqu xmm1, XMMWORD PTR [r9]",
        "movdqu XMMWORD PTR [r8+88], xmm1",
        "mov rax, QWORD PTR [rsp+112]",
        "mov QWORD PTR [r8+24], rax",
        "mov rax, QWORD PTR [r10+56]",
        f"mov rax, QWORD PTR [rax+{abi_fields['JSRuntime.current_stack_frame']}]",
        "mov QWORD PTR [r8], rax",
        "mov QWORD PTR [r8+48], 0",
        "mov QWORD PTR [r8+64], 0",
        "mov QWORD PTR [r8+72], 0",
        "mov BYTE PTR [r8+63], 0",
        "mov QWORD PTR [r8+104], 0",
        "mov DWORD PTR [r8+124], 0",
        "mov QWORD PTR [r8+40], 0",
        "mov WORD PTR [r8+56], 0",
        "mov rax, QWORD PTR [r11+24]",
        f"movzx ecx, WORD PTR [rax+{abi_fields['JSFunctionBytecode.var_count']}]",
        "lea r9, [r8+128]",
        "test ecx, ecx",
        "jz prepared_sort_vars_ready",
        "prepared_sort_init_vars:",
        "mov QWORD PTR [r9], 0",
        "mov QWORD PTR [r9+8], 3",
        "add r9, 16",
        "dec ecx",
        "jnz prepared_sort_init_vars",
        ".globl prepared_sort_vars_ready",
        "prepared_sort_vars_ready:",
        "mov QWORD PTR [r10], r8",
        "lea rdx, [r11+64]",
        "mov QWORD PTR [r10+8], rdx",
        "mov QWORD PTR [r10+24], r9",
        f"mov rax, QWORD PTR [rax+{abi_fields['JSFunctionBytecode.byte_code_buf']}]",
        "mov QWORD PTR [r10+16], rax",
        "mov QWORD PTR [r10+48], 3",
        f"mov BYTE PTR [r10+{exception}], 0",
        "mov r9, QWORD PTR [r11+32]",
        "mov DWORD PTR [r8+120], r9d",
        "mov QWORD PTR [rdx+16], r9",
        "mov QWORD PTR [r10+32], r9",
        f"mov QWORD PTR [r10+{commit}], r9",
    ]
    if diagnostics:
        g += ["mov DWORD PTR [r10+128], 1"]
    g += [
        "mov rdx, QWORD PTR [r10+56]",
        f"add QWORD PTR [rdx+{abi_fields['JSRuntime.stack_top']}], r9",
        f"mov rax, QWORD PTR [rdx+{abi_fields['JSRuntime.stack_limit']}]",
        "test rax, rax",
        "jz prepared_sort_unlimited",
        "add rax, r9",
        f"mov QWORD PTR [rdx+{abi_fields['JSRuntime.stack_limit']}], rax",
        "prepared_sort_unlimited:",
        f"mov QWORD PTR [r10+{shared}], rax",
        "test rax, rax",
        "jz prepared_sort_limit_ready",
        "sub rax, r9",
        "prepared_sort_limit_ready:",
        f"mov QWORD PTR [r10+{limit}], rax",
        f"mov QWORD PTR [rdx+{abi_fields['JSRuntime.current_stack_frame']}], r8",
        "mov rdx, QWORD PTR gs:[88]",
        "mov eax, DWORD PTR [rip+_tls_index]",
        "mov rdx, QWORD PTR [rdx+rax*8]",
        "lea rax, [rip+JS_FrameSharedTop]",
        "lea r8, [rip+_tls_start]",
        "sub rax, r8",
        "add rdx, rax",
        "mov QWORD PTR [rsp+48], rdx",
        "mov rax, QWORD PTR [rdx]",
        "mov QWORD PTR [r11+40], rax",
        "lea rax, [r11+40]",
        "mov QWORD PTR [rdx], rax",
        "mov rcx, r10",
        ".globl prepared_sort_enter",
        "prepared_sort_enter:",
        "call JS_FrameInterp",
        "mov r11, QWORD PTR [rsp+40]",
        f"lea r10, [r11+{state}]",
        "mov rdx, QWORD PTR [r10+56]",
        "mov r9, QWORD PTR [r10+32]",
        f"sub r9, QWORD PTR [r10+{commit}]",
        "jz prepared_sort_charged",
        f"add QWORD PTR [rdx+{abi_fields['JSRuntime.stack_top']}], r9",
        f"cmp QWORD PTR [rdx+{abi_fields['JSRuntime.stack_limit']}], 0",
        "je prepared_sort_charged",
        f"add QWORD PTR [rdx+{abi_fields['JSRuntime.stack_limit']}], r9",
        ".globl prepared_sort_charged",
        "prepared_sort_charged:",
        "mov rax, QWORD PTR [rsp+48]",
        "mov rdx, QWORD PTR [r11+40]",
        "mov QWORD PTR [rax], rdx",
        "mov rax, QWORD PTR [rsp+32]",
        "movdqu xmm0, XMMWORD PTR [r10+40]",
        "movdqu XMMWORD PTR [rax], xmm0",
        ".globl prepared_sort_epilogue",
        "prepared_sort_epilogue:",
        "add rsp, 56",
        "ret",
        "JS_FramePreparedChildTrampoline_end:",
        '.section .xdata$zzzzzzsortprepare,"dr"',
        ".p2align 2",
        "JS_FramePreparedChildGuard_unwind:",
        ".byte 1,0,0,0",
        "JS_FramePreparedChildTrampoline_unwind:",
        ".byte 1, prepared_sort_alloc - JS_FramePreparedChildTrampoline, 1, 0",
        ".byte prepared_sort_alloc - JS_FramePreparedChildTrampoline, 0x62",
        ".short 0",
        '.section .pdata$zzzzzzzsortprepare,"dr"',
        ".p2align 2",
        ".rva JS_FramePreparedChildGuard, JS_FramePreparedChildGuard_end, JS_FramePreparedChildGuard_unwind",
        ".rva JS_FramePreparedChildTrampoline, JS_FramePreparedChildTrampoline_end, JS_FramePreparedChildTrampoline_unwind",
    ]

    # Private sret/capsule/argv/paused-host ABI: RCX/RDX/R8/R9.
    # Home slots preserve the two input pointers. No inherited primary VM
    # prologue is involved; each entry has its own real unwind description.
    g += [
        '.section .qjscall$zzentry,"xr"',
        ".p2align 4",
        ".globl JS_FramePreparedSortInvoke, JS_FramePreparedSortInvoke_end",
        ".def JS_FramePreparedSortInvoke; .scl 2; .type 32; .endef",
        "JS_FramePreparedSortInvoke:",
        "mov QWORD PTR [rsp+8], rdx",
        "mov QWORD PTR [rsp+16], r8",
        "mov rdx, QWORD PTR [rdx]",
        "mov rax, QWORD PTR [rdx+16]",
        "mov QWORD PTR [rsp+24], rax",
        f"cmp BYTE PTR [rax+{abi_fields['JSRuntime.module_normalize_has_attr'] + 3}], 1",
        "jne prepared_entry_fallback",
        f"movzx r10d, BYTE PTR [rax+{abi_fields['JSRuntime.current_stack_frame'] - 5}]",
        "and r10d, 3",
        "cmp r10d, 1",
        "jne prepared_entry_fallback",
        f"cmp BYTE PTR [rax+{abi_fields['JSRuntime.current_stack_frame'] - 1}], 1",
        "jne prepared_entry_fallback",
        f"cmp BYTE PTR [rax+{abi_fields['JSRuntime.current_stack_frame'] - 3}], 1",
        "jne prepared_entry_fallback",
        f"test BYTE PTR [rax+{abi_bits['JSRuntime.dump_flags'][0][0]}], 128",
        "jnz prepared_entry_fallback",
        "mov r10, QWORD PTR gs:[88]",
        "mov r11d, DWORD PTR [rip+_tls_index]",
        "mov r10, QWORD PTR [r10+r11*8]",
        "lea r11, [rip+JS_FrameSharedTop]",
        "lea r8, [rip+_tls_start]",
        "sub r11, r8",
        "add r10, r11",
        "cmp QWORD PTR [r10], r9",
        "jne prepared_entry_fallback",
        "cmp DWORD PTR [r9+16], 0",
        "jne prepared_entry_fallback",
        "mov r10, QWORD PTR [r9+8]",
        "cmp QWORD PTR [r10+56], rax",
        "jne prepared_entry_fallback",
        "mov r11, QWORD PTR [r10+32]",
        f"cmp r11, QWORD PTR [r10+{commit}]",
        "jne prepared_entry_fallback",
        "mov r11, QWORD PTR [rsp+8]",
        "lea r8, [r11+3]",
        f"cmp QWORD PTR [r10+{owner}], r8",
        "jne prepared_entry_fallback",
        "cmp QWORD PTR [r11+80], 0",
        "jne prepared_entry_fallback",
        f"cmp QWORD PTR [r11+{state}], 0",
        "jne prepared_entry_fallback",
        "mov r8, rsp",
        "sub r8, 4344",
        "sub r8, QWORD PTR [r11+32]",
        f"cmp r8, QWORD PTR [rax+{abi_fields['JSRuntime.stack_limit']}]",
        "jb prepared_entry_fallback",
        f"cmp DWORD PTR [rdx+{abi_fields['JSContext.interrupt_counter']}], 1",
        "jle prepared_entry_fallback",
        "jmp JS_FramePreparedSortTrampoline",
        ".globl prepared_entry_fallback",
        "prepared_entry_fallback:",
        "mov rdx, QWORD PTR [rsp+8]",
        "mov r8, QWORD PTR [rsp+16]",
        "jmp JS_FramePreparedSortFallback",
        "JS_FramePreparedSortInvoke_end:",
        ".p2align 4",
        ".globl JS_FramePreparedSortTrampoline, JS_FramePreparedSortTrampoline_end",
        ".def JS_FramePreparedSortTrampoline; .scl 2; .type 32; .endef",
        "JS_FramePreparedSortTrampoline:",
        "sub rsp, 56",
        ".globl prepared_entry_alloc",
        "prepared_entry_alloc:",
        "mov QWORD PTR [rsp+32], rcx",
        "mov r11, QWORD PTR [rsp+64]",
        "mov QWORD PTR [rsp+40], r11",
        "mov rdx, QWORD PTR [r11]",
        f"dec DWORD PTR [rdx+{abi_fields['JSContext.interrupt_counter']}]",
        f"lea r8, [r11+{data}]",
        f"lea r10, [r11+{state}]",
        "mov QWORD PTR [r8+88], 0",
        "mov QWORD PTR [r8+96], 3",
        "mov rax, QWORD PTR [rsp+72]",
        "mov QWORD PTR [r8+24], rax",
        "mov rax, QWORD PTR [r10+56]",
        f"mov rax, QWORD PTR [rax+{abi_fields['JSRuntime.current_stack_frame']}]",
        "mov QWORD PTR [r8], rax",
        "mov QWORD PTR [r8+48], 0",
        "mov QWORD PTR [r8+64], 0",
        "mov QWORD PTR [r8+72], 0",
        "mov BYTE PTR [r8+63], 0",
        "mov QWORD PTR [r8+104], 0",
        "mov DWORD PTR [r8+124], 0",
        "mov QWORD PTR [r8+40], 0",
        "mov WORD PTR [r8+56], 0",
        "mov rax, QWORD PTR [r11+24]",
        f"movzx ecx, WORD PTR [rax+{abi_fields['JSFunctionBytecode.var_count']}]",
        "lea r9, [r8+128]",
        "test ecx, ecx",
        "jz prepared_entry_vars_ready",
        "prepared_entry_init_vars:",
        "mov QWORD PTR [r9], 0",
        "mov QWORD PTR [r9+8], 3",
        "add r9, 16",
        "dec ecx",
        "jnz prepared_entry_init_vars",
        ".globl prepared_entry_vars_ready",
        "prepared_entry_vars_ready:",
        "mov QWORD PTR [r10], r8",
        "lea rdx, [r11+64]",
        "mov QWORD PTR [r10+8], rdx",
        "mov QWORD PTR [r10+24], r9",
        f"mov rax, QWORD PTR [rax+{abi_fields['JSFunctionBytecode.byte_code_buf']}]",
        "mov QWORD PTR [r10+16], rax",
        "mov QWORD PTR [r10+48], 3",
        f"mov BYTE PTR [r10+{exception}], 0",
        "mov r9, QWORD PTR [r11+32]",
        "mov DWORD PTR [r8+120], r9d",
        "mov QWORD PTR [rdx+16], r9",
        "mov QWORD PTR [r10+32], r9",
        f"mov QWORD PTR [r10+{commit}], r9",
    ]
    if diagnostics:
        g += ["mov DWORD PTR [r10+128], 1"]
    # Root publication, quota reconciliation, TLS restoration and owned result
    # transfer are the already tested prepared-scope protocol, duplicated in a
    # separate late island without editing any established opcode handler.
    begin = g.index("mov rdx, QWORD PTR [r10+56]", g.index("prepared_sort_vars_ready:"))
    end = g.index("JS_FramePreparedChildTrampoline_end:", begin)
    tail = [x.replace("prepared_sort_", "prepared_entry_") for x in g[begin:end]]
    g += tail + [
        "JS_FramePreparedSortTrampoline_end:",
        '.section .xdata$zzzzzzzzsortentry,"dr"',
        ".p2align 2",
        "JS_FramePreparedSortInvoke_unwind:",
        ".byte 1,0,0,0",
        "JS_FramePreparedSortTrampoline_unwind:",
        ".byte 1, prepared_entry_alloc - JS_FramePreparedSortTrampoline, 1, 0",
        ".byte prepared_entry_alloc - JS_FramePreparedSortTrampoline, 0x62",
        ".short 0",
        '.section .pdata$zzzzzzzzsortentry,"dr"',
        ".p2align 2",
        ".rva JS_FramePreparedSortInvoke, JS_FramePreparedSortInvoke_end, JS_FramePreparedSortInvoke_unwind",
        ".rva JS_FramePreparedSortTrampoline, JS_FramePreparedSortTrampoline_end, JS_FramePreparedSortTrampoline_unwind",
    ]

    (out / "quickjs-interpreter-native-slice-win64.S").write_text(
        "\n".join(g) + "\n", encoding="utf-8"
    )


def generate(source, out):
    out.write_text(
        '#include "quickjs-native-slice-private.h"\n'
        '#define NATIVE_SLICE_CODE __attribute__((section(".qjsvm$zzzzznative"), noipa))\n'
        '#include "'
        + str(_frame_source_file(source, "quickjs-interpreter-slice-native.h")).replace("\\", "/")
        + '"\n',
        encoding="utf-8",
    )


def adapt(source, object_path, header):
    spec = importlib.util.spec_from_file_location(
        "native_core_alias", _frame_tool_path("object-adapter")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    raw = object_path.read_bytes()
    coff = module.Coff(raw)
    body = _frame_source_text(source, "quickjs-interpreter-slice-native.h")
    body += _frame_source_text(source, "quickjs-interpreter-cached-sort.h")
    # Public JS_Call is defined by the frame wrapper, not the renamed core.
    # Keep dependency discovery from copying the original public wrapper.
    body += _frame_source_text(source, "quickjs-interpreter-prepared-entry.h").replace(
        "JS_Call(", "QJS_SORT_PUBLIC_CALL("
    )
    # These exact core bodies used to be inlined into js_string_slice. Do not
    # create additional by-value JSValue ABI crossings in the interpreter-view body.
    import re

    local_helpers = {
        "JS_ToString",
        "JS_ToInt32SatFree",
        "JS_FreeValue",
        "JS_FreeValueRT",
        "js_thisNumberValue",
        "JS_ToFloat64Free",
    }
    module.HOT_LOCAL_HELPERS |= local_helpers
    core_text = _frame_source_file(source, "quickjs.c").read_text(encoding="utf-8")
    text, exports, copies = module.generate(core_text, coff, body)
    assert local_helpers <= set(copies)
    helper_definitions = {m[2]: m for m in module.FUNCTION.finditer(core_text)}
    inline_bodies = {
        name: hashlib.sha256(helper_definitions[name][0].encode()).hexdigest()
        for name in sorted(local_helpers)
    }
    # Insert names after the public header; retain its public declarations.
    marker = "#ifdef _MSC_VER\n#define FRAME_BIGINT_LOCAL"
    assert text.count(marker) == 1
    private_names = "\n".join(
        "#define " + name + " qjs_slice_inline_" + name for name in sorted(local_helpers)
    )
    numeric_hint_type = re.search(
        r"^typedef enum JSToNumberHintEnum \{.*?^\} JSToNumberHintEnum;", core_text, re.M | re.S
    ).group(0)
    text = text.replace(marker, private_names + "\n" + numeric_hint_type + "\n" + marker)
    names = "|".join(sorted(local_helpers))
    pattern = r"^(?:static\s+)?(?:inline\s+)?(void|int|JSValue)\s+(" + names + r")(?=\s*\()"
    text, count = re.subn(
        pattern, r"static inline __attribute__((always_inline)) \1 \2", text, flags=re.M
    )
    assert count == 2 * len(local_helpers), count

    names = {s["name"] for s in coff.all_symbols.values()}
    added = []
    for name in exports:
        if "qjs_frame_core_" + name in names:
            continue
        coff.expose(name)
        added.append(name)
    # Internal/atod routing appends relocation payloads beyond the old string
    # table. Coff.finish() alone would omit those bytes. Preserve the tail and
    # adjust only file pointers, keeping payloads and symbol indices unchanged.
    import struct

    original = module.Coff(raw)
    old_end = original.string_offset + len(original.strings)
    result = bytearray(coff.finish())
    shift = len(result) - old_end
    result.extend(raw[old_end:])
    for record in original.section_records:
        for field in (20, 24, 28):
            at = record["pos"] + field
            value = struct.unpack_from("<I", raw, at)[0]
            if value and value >= old_end:
                struct.pack_into("<I", result, at, value + shift)
    # Only the existing Array.prototype.sort function-table pointer is routed.
    # GCC records it as .text+addend; debug address references are untouched.
    routed = module.Coff(bytes(result))
    target = routed.external("JS_FrameCachedArraySort")
    f = routed.symbols["js_array_sort"]
    sort_routes = []
    for si, rec in enumerate(routed.section_records):
        if routed.sections[si]["name"] != ".rdata":
            continue
        for i in range(rec["count"]):
            q = rec["reloc"] + i * 10
            off, sym, kind = struct.unpack_from("<IIH", routed.data, q)
            symbol = routed.all_symbols[sym]
            if kind != 1 or symbol["section"] != f["section"]:
                continue
            addend = struct.unpack_from("<Q", routed.data, rec["raw"] + off)[0]
            if addend + symbol["value"] != f["value"]:
                continue
            struct.pack_into("<Q", routed.data, rec["raw"] + off, 0)
            struct.pack_into("<I", routed.data, q + 4, target)
            sort_routes.append(
                dict(
                    section=si + 1,
                    offset=off,
                    old_symbol=symbol["name"],
                    old_addend=addend,
                    new_symbol="JS_FrameCachedArraySort",
                    kind=kind,
                )
            )
    assert len(sort_routes) == 1, sort_routes
    # Coff.finish preserves the tail bytes; new aliases move their file
    # offsets. Internal/atod routing stored relocation arrays in this tail.
    old_end = routed.string_offset + struct.unpack_from("<I", routed.data, routed.string_offset)[0]
    result = bytearray(routed.finish())
    shift = len(result) - len(routed.data)
    for rec in routed.section_records:
        for field in (20, 24, 28):
            q = rec["pos"] + field
            value = struct.unpack_from("<I", routed.data, q)[0]
            if value and value >= old_end:
                struct.pack_into("<I", result, q, value + shift)
    result = bytes(result)
    verified = module.Coff(result)
    for si, (before, after) in enumerate(zip(original.sections, verified.sections), 1):
        if si not in {r["section"] for r in sort_routes}:
            assert before == after
        else:
            x = bytearray(
                original.data[
                    original.section_records[si - 1]["raw"] : original.section_records[si - 1][
                        "raw"
                    ]
                    + before["size"]
                ]
            )
            y = bytearray(
                verified.data[
                    verified.section_records[si - 1]["raw"] : verified.section_records[si - 1][
                        "raw"
                    ]
                    + after["size"]
                ]
            )
            for r in sort_routes:
                if r["section"] == si:
                    x[r["offset"] : r["offset"] + 8] = y[r["offset"] : r["offset"] + 8] = bytes(8)
            assert x == y and before["size"] == after["size"] and before["flags"] == after["flags"]

    for i, symbol in original.all_symbols.items():
        assert verified.all_symbols[i] == symbol

    backup = object_path.with_name(object_path.name + ".before-native-slice")
    assert not backup.exists()
    backup.write_bytes(raw)
    object_path.write_bytes(result)
    header.write_text(text, encoding="utf-8")
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    header.with_suffix(".json").write_text(
        json.dumps(
            dict(
                status="passed",
                before_sha256=sha(backup),
                after_sha256=sha(object_path),
                header_sha256=sha(header),
                added_aliases=added,
                copied_helpers=copies,
                local_inline_helpers=sorted(local_helpers),
                original_helper_definitions_sha256=inline_bodies,
                numeric_hint_type_sha256=hashlib.sha256(numeric_hint_type.encode()).hexdigest(),
                sort_routes=sort_routes,
                policy="External aliases plus one audited old sort function-table ADDR64 relocation/addend; all RX and old symbols fixed. Main private header stays f94s.",
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--compile", action="store_true")
    ap.add_argument("--adapt", action="store_true")
    ap.add_argument("--source", type=Path, required=True)
    for name in ("build", "out", "object", "header"):
        ap.add_argument("--" + name, type=Path)
    a = ap.parse_args()
    assert a.compile != a.adapt
    if a.adapt:
        assert a.object and a.header
        adapt(a.source, a.object, a.header)
    else:
        assert a.build and a.out
        spec = importlib.util.spec_from_file_location("slice_compiler", _frame_tool_path("atod"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        original_argv = module.win_argv
        module.win_argv = lambda command: [
            x for x in original_argv(command) if not x.startswith("-g")
        ] + ["-g0"]
        module.compile_extra(
            a.source,
            a.build,
            a.out,
            generator=generate,
            filename="quickjs-interpreter-native-slice.c",
            late_name=".qjsvm$zzzzznative",
        )

        def generate_sort(source, out):
            out.write_text(
                '#include "quickjs-native-slice-private.h"\n'
                '#define NATIVE_SORT_CODE __attribute__((section(".qjsvm$zzzzzzsortcache"), noipa))\n'
                '#include "'
                + str(_frame_source_file(source, "quickjs-interpreter-cached-sort.h")).replace(
                    "\\", "/"
                )
                + '"\n',
                encoding="utf-8",
            )

        module.compile_extra(
            a.source,
            a.build,
            a.out.with_name("quickjs-interpreter-cached-sort.obj"),
            generator=generate_sort,
            filename="quickjs-interpreter-cached-sort.c",
            late_name=".qjsvm$zzzzzzsortcache",
        )

        def generate_prepared(source, out):
            out.write_text(
                '#include "quickjs-native-slice-private.h"\n'
                "#define QJS_PREPARED_SCOPE_ONLY 1\n"
                '#define NATIVE_SORT_CODE __attribute__((section(".qjscall$preparec"), noipa))\n'
                '#include "'
                + str(_frame_source_file(source, "quickjs-interpreter-cached-sort.h")).replace(
                    "\\", "/"
                )
                + '"\n'
                '#include "'
                + str(_frame_source_file(source, "quickjs-interpreter-prepared-entry.h")).replace(
                    "\\", "/"
                )
                + '"\n',
                encoding="utf-8",
            )

        module.compile_extra(
            a.source,
            a.build,
            a.out.with_name("quickjs-interpreter-prepared-sort.obj"),
            generator=generate_prepared,
            filename="quickjs-interpreter-prepared-sort.c",
            late_name=".qjscall$preparec",
        )

        def generate_number_property(source, out):
            out.write_text(
                '#include "quickjs-native-slice-private.h"\n'
                '#define NUMBER_PROPERTY_CODE __attribute__((section(".qjscall$zznumberpropertyc"), noipa))\n'
                '#include "'
                + str(_frame_source_file(source, "quickjs-interpreter-number-property.h")).replace(
                    "\\", "/"
                )
                + '"\n',
                encoding="utf-8",
            )

        module.compile_extra(
            a.source,
            a.build,
            a.out.with_name("quickjs-interpreter-number-property.obj"),
            generator=generate_number_property,
            filename="quickjs-interpreter-number-property.c",
            late_name=".qjscall$zznumberpropertyc",
        )

        def generate_proto_load(source, out):
            out.write_text(
                '#include "quickjs-native-slice-private.h"\n'
                '#define PROTO_LOAD_CODE __attribute__((section(".qjscall$zzzzprotoloadc"), noipa))\n'
                '#include "'
                + str(_frame_source_file(source, "quickjs-interpreter-proto-load.h")).replace(
                    "\\", "/"
                )
                + '"\n',
                encoding="utf-8",
            )

        module.compile_extra(
            a.source,
            a.build,
            a.out.with_name("quickjs-interpreter-proto-load.obj"),
            generator=generate_proto_load,
            filename="quickjs-interpreter-proto-load.c",
            late_name=".qjscall$zzzzprotoloadc",
        )

        def generate_proto_persistent(source, out):
            out.write_text(
                '#include "quickjs-native-slice-private.h"\n'
                '#define PROTO_PERSIST_CODE __attribute__((section(".qjscall$zzzzzzzpersistfill"), noipa))\n'
                '#include "'
                + str(_frame_source_file(source, "quickjs-interpreter-proto-persistent.h")).replace(
                    "\\", "/"
                )
                + '"\n',
                encoding="utf-8",
            )

        module.compile_extra(
            a.source,
            a.build,
            a.out.with_name("quickjs-interpreter-proto-persistent.obj"),
            generator=generate_proto_persistent,
            filename="quickjs-interpreter-proto-persistent.c",
            late_name=".qjscall$zzzzzzzpersistfill",
        )

        def generate_root(source, out):
            out.write_text(
                '#include "quickjs-interpreter-private.h"\n'
                '#define ROOT_CODE __attribute__((section(".qjsroot$c"), noipa, target("general-regs-only")))\n'
                '#include "'
                + str(_frame_source_file(source, "quickjs-interpreter-native-root.h")).replace(
                    "\\", "/"
                )
                + '"\n',
                encoding="utf-8",
            )

        module.compile_extra(
            a.source,
            a.build,
            a.out.with_name("quickjs-interpreter-native-root.obj"),
            generator=generate_root,
            filename="quickjs-interpreter-native-root.c",
            late_name=".qjsroot$c",
        )

        # Absolute pointer COMDAT data is unsafe when renamed into executable
        # islands by this linker. All native targets use explicit RIP-relative
        # addresses; require zero ADDR64 relocations in this entire new object.
        spec = importlib.util.spec_from_file_location(
            "native_reloc_guard", _frame_tool_path("object-adapter")
        )
        c = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(c)
        import struct

        for path in (
            a.out,
            a.out.with_name("quickjs-interpreter-proto-persistent.obj"),
            a.out.with_name("quickjs-interpreter-native-root.obj"),
        ):
            obj = c.Coff(path.read_bytes())
            for rec in obj.section_records:
                for i in range(rec["count"]):
                    off, sym, kind = struct.unpack_from("<IIH", obj.data, rec["reloc"] + i * 10)
                    assert kind != 1, (
                        "Native island must have no ADDR64 relocation",
                        path.name,
                        off,
                        obj.all_symbols[sym],
                    )
