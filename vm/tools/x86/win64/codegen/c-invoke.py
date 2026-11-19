"""Interp-style private VM C prepare/invoke; retain the public Win64 ABI.

Live class/signature/realm and all shared/quota/interrupt guards remain.
The VM already owns its nonvolatile registers: there is no second GPR save.
The C result remains in XMM0 until the original ownership consumer needs it.
The native SF/TLS boundary and the by-value-this copy are retained exactly.
No target/object cache, new JS allocation, frame field or core rewrite. MIT.
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
from abi_layout import constants as abi_constants
import json


def _vm_kernel(diagnostics, publish):
    abi_layout = current_abi()
    abi_fields = abi_layout["offsets"]
    committed = 2304 if diagnostics else 64
    native_limit = 2312 if diagnostics else 72
    shared_limit = 2320 if diagnostics else 80
    exception = 2296 if diagnostics else 160
    direct = 2297 if diagnostics else 161
    regs = ("rcx", "rdx", "r8", "r9", "r10", "r11", "rax")
    entry = ["lea r11, [rip+interp_host_call]", "jmp JS_FrameCInvokeGuard"]
    dirty = ["lea r11, [rip+dirty_interp_host_call]", "jmp JS_FrameCInvokeGuard"]
    guard = [
        # R11 is exclusively the exact inherited fallback PC until commit.
        f"cmp WORD PTR [rdx+{abi_fields['JSObject.class_id']}], 12",
        "jne cinvoke_fallback",
        "test ecx, ecx",
        "jz cinvoke_fallback",
        f"cmp BYTE PTR [rdx+{abi_fields['JSObject.u.cfunc.cproto']}], 1",
        "ja cinvoke_fallback",
        f"movzx eax, BYTE PTR [rdx+{abi_fields['JSObject.u.cfunc.length']}]",
        "cmp ecx, eax",
        "jl cinvoke_fallback",
        f"cmp BYTE PTR [rbx+{direct}], 0",
        "je cinvoke_fallback",
        "mov rax, QWORD PTR [rbx+56]",
        f"test BYTE PTR [rax+{abi_fields['JSRuntime.module_loader_has_attr'] + 5}], 128",
        "jz cinvoke_fallback",
        f"test BYTE PTR [rax+{abi_fields['JSRuntime.module_loader_has_attr'] + 5}], 16",
        "jnz cinvoke_fallback",
        f"cmp BYTE PTR [rax+{abi_fields['JSRuntime.module_normalize_has_attr'] + 1}], 1",
        "jne cinvoke_fallback",
        f"movzx r10d, BYTE PTR [rax+{abi_fields['JSRuntime.current_stack_frame'] - 5}]",
        "and r10d, 11",
        "cmp r10d, 1",
        "jne cinvoke_fallback",
        "mov r10, QWORD PTR [rbx+32]",
        f"cmp r10, QWORD PTR [rbx+{committed}]",
        "jne cinvoke_fallback",
        # Match the original GenericFast's conservative formal*16+248 check
        # at its CALL entry, which is eight bytes below this VM-JMP entry.
        f"movzx r10d, BYTE PTR [rdx+{abi_fields['JSObject.u.cfunc.length']}]",
        "shl r10, 4",
        "add r10, 256",
        "neg r10",
        "add r10, rsp",
        f"cmp r10, QWORD PTR [rax+{abi_fields['JSRuntime.stack_limit']}]",
        "jb cinvoke_fallback",
        f"cmp DWORD PTR [rsi+{abi_fields['JSContext.interrupt_counter']}], 1",
        "jle cinvoke_fallback",
        "cmp BYTE PTR [rip+JS_FrameCInvokeControl], 0",
        "je JS_FrameCInvokeConfig",
        "cmp BYTE PTR [rip+JS_FrameCInvokeControl], 1",
        "jne cinvoke_fallback",
        "jmp JS_FrameCInvokeCommit",
        "cinvoke_fallback:",
        "jmp r11",
    ]
    # Redirect two existing near branches; keep all positive-argc code PCs.
    argc_guard = guard[:]
    if publish:
        guard[guard.index("test ecx, ecx") + 1] = "jz JS_FrameDensePopLeafEntry"
        guard[guard.index("cmp ecx, eax") + 1] = "jl JS_FrameCArgcGuard"
    else:
        # Packed native-view/builtin controls belong to the MinGW islands.
        at = guard.index(
            f"test BYTE PTR [rax+{abi_fields['JSRuntime.module_loader_has_attr'] + 5}], 128"
        )
        assert guard[at : at + 4] == [
            f"test BYTE PTR [rax+{abi_fields['JSRuntime.module_loader_has_attr'] + 5}], 128",
            "jz cinvoke_fallback",
            f"test BYTE PTR [rax+{abi_fields['JSRuntime.module_loader_has_attr'] + 5}], 16",
            "jnz cinvoke_fallback",
        ]
        del guard[at : at + 4]
        guard[guard.index("test ecx, ecx") + 1] = "jz JS_FrameDensePopLeafEntry"
    commit = [
        # The original host opcode's publication and pending-value ledger.
        "mov eax, DWORD PTR [rsp+56]",
        "add r12, rax",
        "mov QWORD PTR [rbp+48], r12",
        "mov QWORD PTR [rbp+104], r13",
        "mov eax, DWORD PTR [rsp+48]",
        "lea eax, [rax+rcx+1]",
        "or eax, DWORD PTR [rsp+52]",
        "mov WORD PTR [rbp+126], ax",
        "mov QWORD PTR [rbx], rbp",
        "mov QWORD PTR [rbx+16], r12",
        "mov QWORD PTR [rbx+24], r13",
    ]
    if publish and not diagnostics:
        commit += [
            "lea r10, [rip+JS_FramePublishDirtyTable]",
            "cmp rdi, r10",
            "jne cinvoke_publish_ready",
            "lea rdi, [rip+JS_FramePublishTable]",
            "cinvoke_publish_ready:",
        ]
    commit += [
        "mov r10, QWORD PTR [rbx+56]",
        f"mov QWORD PTR [r10+{abi_fields['JSRuntime.current_stack_frame']}], rbp",
        f"dec DWORD PTR [rsi+{abi_fields['JSContext.interrupt_counter']}]",
        "jmp JS_FrameCInvokeBody",
    ]
    body = [
        "sub rsp, 208",
        "cinvoke_alloc:",
        # Shadow/stack args0..47, original SF48..127, shared anchor128..159,
        # writable by-value receiver160..175, hidden result176..191, TLS192.
        f"mov rax, QWORD PTR [r10+{abi_fields['JSRuntime.current_stack_frame']}]",
        "mov QWORD PTR [rsp+48], rax",
        "movdqu xmm2, XMMWORD PTR [r8-16]",
        "movdqu XMMWORD PTR [rsp+56], xmm2",
        "mov QWORD PTR [rsp+72], r8",
        "mov WORD PTR [rsp+106], cx",
        "mov WORD PTR [rsp+108], 0",
        "mov DWORD PTR [rsp+156], ecx",
        "mov QWORD PTR [rsp+32], r8",
        f"movsx eax, WORD PTR [rdx+{abi_fields['JSObject.u.cfunc.magic']}]",
        "mov DWORD PTR [rsp+40], eax",
        "cmp DWORD PTR [rsp+256], 0",
        "je cinvoke_undefined",
        "movdqu xmm2, XMMWORD PTR [r8-32]",
        "movdqa XMMWORD PTR [rsp+160], xmm2",
        "jmp cinvoke_this_ready",
        "cinvoke_undefined:",
        "mov QWORD PTR [rsp+160], 0",
        "mov QWORD PTR [rsp+168], 3",
        "cinvoke_this_ready:",
        "mov rax, QWORD PTR gs:88",
        "mov ecx, DWORD PTR [rip+_tls_index]",
        "mov rax, QWORD PTR [rax+rcx*8]",
        "lea rcx, [rip+JS_FrameSharedTop]",
        "lea r9, [rip+_tls_start]",
        "sub rcx, r9",
        "add rax, rcx",
        "mov QWORD PTR [rsp+192], rax",
        "mov rcx, QWORD PTR [rax]",
        "mov QWORD PTR [rsp+128], rcx",
        "mov QWORD PTR [rsp+136], rbx",
        "mov DWORD PTR [rsp+144], 0",
        f"mov cl, BYTE PTR [r10+{abi_fields['JSRuntime.current_stack_frame'] - 5}]",
        "and cl, 4",
        "mov BYTE PTR [rsp+152], cl",
        "lea rcx, [rsp+48]",
        f"mov QWORD PTR [r10+{abi_fields['JSRuntime.current_stack_frame']}], rcx",
        "lea rcx, [rsp+128]",
        f"or BYTE PTR [r10+{abi_fields['JSRuntime.current_stack_frame'] - 5}], 4",
        "mov QWORD PTR [rax], rcx",
        f"mov r11, QWORD PTR [rdx+{abi_fields['JSObject.u.cfunc.c_function']}]",
        f"mov rdx, QWORD PTR [rdx+{abi_fields['JSObject.u.cfunc.realm']}]",
        "lea rcx, [rsp+176]",
        "lea r8, [rsp+160]",
        "mov r9d, DWORD PTR [rsp+156]",
    ]
    if diagnostics:
        body += [
            "inc QWORD PTR [rbx+2264]",
            "inc QWORD PTR [rbx+2208]",
            "mov rax, QWORD PTR [rsp+56]",
            f"cmp BYTE PTR [rax+{abi_fields['JSObject.u.cfunc.cproto']}], 0",
            "jne cinvoke_magic_count",
            "inc QWORD PTR [rbx+2392]",
            "jmp cinvoke_counted",
            "cinvoke_magic_count:",
            "inc QWORD PTR [rbx+2400]",
            "cinvoke_counted:",
        ]
    body += [
        "JS_FrameCInvokeCall:",
        "call r11",
        "JS_FrameCInvokeAfterCall:",
        # Restore exactly the old native SF/TLS/shared mode/limit protocol.
        "mov r10, QWORD PTR [rbx+56]",
        "mov r11, QWORD PTR [rsp+192]",
        "mov rax, QWORD PTR [rsp+128]",
        "mov QWORD PTR [r11], rax",
        f"mov al, BYTE PTR [r10+{abi_fields['JSRuntime.current_stack_frame'] - 5}]",
        "and al, 251",
        "or al, BYTE PTR [rsp+152]",
        f"mov BYTE PTR [r10+{abi_fields['JSRuntime.current_stack_frame'] - 5}], al",
        "mov rax, QWORD PTR [rsp+48]",
        f"mov QWORD PTR [r10+{abi_fields['JSRuntime.current_stack_frame']}], rax",
        "mov rax, QWORD PTR [rbx+32]",
        f"mov rdx, QWORD PTR [r10+{abi_fields['JSRuntime.stack_limit']}]",
        f"cmp rax, QWORD PTR [rbx+{committed}]",
        "jne cinvoke_refresh",
        f"cmp rdx, QWORD PTR [rbx+{shared_limit}]",
        "je cinvoke_refreshed",
        "cinvoke_refresh:",
        f"mov QWORD PTR [rbx+{committed}], rax",
        f"mov QWORD PTR [rbx+{shared_limit}], rdx",
        "test rdx, rdx",
        "jz cinvoke_limit",
        "sub rdx, rax",
        "cinvoke_limit:",
        f"mov QWORD PTR [rbx+{native_limit}], rdx",
        "cinvoke_refreshed:",
        "movdqu xmm0, XMMWORD PTR [rsp+176]",
        "cmp QWORD PTR [rsp+184], 6",
        f"sete BYTE PTR [rbx+{exception}]",
        "je cinvoke_exception",
        "add rsp, 208",
        "JS_FrameCInvokeContinue:",
        "mov r11, QWORD PTR [rbp+104]",
        "movzx r10d, WORD PTR [rbp+126]",
        "and r10d, 32767",
        "shl r10, 4",
        "neg r10",
        "add r10, r11",
        "mov r13, r10",
        "mov DWORD PTR [rsp+60], 1",
    ]
    if diagnostics:
        body += ["inc QWORD PTR [rbx+2360]"]
    if publish and not diagnostics:
        body += [
            "lea rax, [rip+JS_FramePublishTable]",
            "cmp rdi, rax",
            "je publish_interp_release_values",
        ]
    body += [
        "jmp interp_release_values",
        "cinvoke_exception:",
        "movdqu XMMWORD PTR [rbx+40], xmm0",
        "add rsp, 208",
        "jmp interp_host_exception",
    ]
    # RSP-restored PCs have a distinct leaf range. Do not rely on Windows
    # recognizing an add-rsp followed by a private cross-kernel continuation
    # as a conventional function epilogue.
    at = body.index("JS_FrameCInvokeContinue:")
    ex = body.index("cinvoke_exception:")
    continuation = body[at + 1 : ex]
    exception_body = body[ex:-1]
    exception_continuation = body[-1:]
    body = body[:at]
    config = ["sub rsp, 96", "cinvoke_config_alloc:"]
    config += [f"mov QWORD PTR [rsp+{32 + i * 8}], {r}" for i, r in enumerate(regs)]
    config += [
        "lea rcx, [rip+JS_FrameCInvokeDisable]",
        "call getenv",
        "test rax, rax",
        "setne cl",
        "inc cl",
        "xor eax, eax",
        "lock cmpxchg BYTE PTR [rip+JS_FrameCInvokeControl], cl",
    ]
    config += [f"mov {r}, QWORD PTR [rsp+{32 + i * 8}]" for i, r in enumerate(regs)]
    config += ["add rsp, 96", "jmp JS_FrameCInvokeGuard"]
    config_continuation = config[-1:]
    config = config[:-1]

    return (
        regs,
        entry,
        dirty,
        guard,
        argc_guard,
        commit,
        body,
        continuation,
        exception_body,
        exception_continuation,
        config,
        config_continuation,
    )


def append(g, diagnostics, out):
    abi_layout = current_abi()
    abi_fields = abi_layout["offsets"]
    changes = []
    declaration = ".globl JS_FrameInterp"
    assert g.count(declaration) == 1
    g[g.index(declaration)] = (
        declaration
        + ", interp_host_call, interp_release_values, interp_host_exception, JS_FrameInterp_end, JS_FrameInterp_unwind"
    )
    # Both the retained call kernel and the CallMeta kernel have this branch.
    needle = "jne interp_host_call"
    assert g.count(needle) == 2
    for i, x in enumerate(g):
        if x == needle:
            assert g[i - 1] == f"cmp WORD PTR [rdx+{abi_fields['JSObject.class_id']}], 13"
            g[i] = "jne JS_FrameCInvokeEntry"
            changes.append(dict(path="register", index=i))
    if not diagnostics:
        p = out / "quickjs-interpreter-publish-win64.S"
        t = p.read_text(encoding="utf-8")
        needle = (
            f"cmp WORD PTR [rdx+{abi_fields['JSObject.class_id']}], 13\njne dirty_interp_host_call"
        )
        assert t.count(needle) == 2
        t = t.replace(
            needle,
            f"cmp WORD PTR [rdx+{abi_fields['JSObject.class_id']}], 13\njne JS_FrameCInvokeDirtyEntry",
        )
        t = ".globl dirty_interp_host_call, publish_interp_release_values\n" + t
        p.write_text(t, encoding="utf-8")
        changes.extend([dict(path="publish", branch=i) for i in range(2)])
    (
        regs,
        entry,
        dirty,
        guard,
        argc_guard,
        commit,
        body,
        continuation,
        exception_body,
        exception_continuation,
        config,
        config_continuation,
    ) = _vm_kernel(diagnostics, True)
    import importlib.util

    spec = importlib.util.spec_from_file_location("frame_iterator", _frame_tool_path("iterator"))
    iterator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(iterator)
    iterator.append(g, diagnostics, out)

    g = [".intel_syntax noprefix", '.section .qjsinv,"xr"']
    blocks = [("JS_FrameCInvokeEntry", entry, "leaf")]
    if not diagnostics:
        blocks.append(("JS_FrameCInvokeDirtyEntry", dirty, "leaf"))
    blocks += [
        ("JS_FrameCInvokeGuard", guard, "leaf"),
        ("JS_FrameCInvokeCommit", commit, "leaf"),
        ("JS_FrameCInvokeBody", body, "body"),
        ("JS_FrameCInvokeContinue", continuation, "leaf"),
        ("JS_FrameCInvokeException", exception_body, "outbody"),
        ("JS_FrameCInvokeExceptionContinue", exception_continuation, "leaf"),
        ("JS_FrameCInvokeConfig", config, "config"),
        ("JS_FrameCInvokeConfigContinue", config_continuation, "leaf"),
    ]
    for name, stream, kind in blocks:
        if not name.endswith("Continue"):
            g += [".p2align 4"]
        g += [
            ".globl " + name + ", " + name + "_end",
            ".def " + name + "; .scl 2; .type 32; .endef",
            name + ":",
        ]
        for x in stream:
            if x.endswith(":"):
                g += [".globl " + x[:-1]]
            g.append(x)
        g += [name + "_end:"]
    g += [
        ".p2align 2",
        "cinvoke_leaf_unwind:",
        ".byte 33, 0, 0, 0",
        ".rva JS_FrameInterp, JS_FrameInterp_end, JS_FrameInterp_unwind",
        "cinvoke_body_unwind:",
        ".byte 33, cinvoke_alloc-JS_FrameCInvokeBody, 2, 0",
        ".byte cinvoke_alloc-JS_FrameCInvokeBody, 1",
        ".short 26",
        ".rva JS_FrameInterp, JS_FrameInterp_end, JS_FrameInterp_unwind",
        "cinvoke_outbody_unwind:",
        ".byte 33, 0, 2, 0",
        ".byte 0, 1",
        ".short 26",
        ".rva JS_FrameInterp, JS_FrameInterp_end, JS_FrameInterp_unwind",
        "cinvoke_config_unwind:",
        ".byte 33, cinvoke_config_alloc-JS_FrameCInvokeConfig, 1, 0",
        ".byte cinvoke_config_alloc-JS_FrameCInvokeConfig, 0xb2",
        ".short 0",
        ".rva JS_FrameInterp, JS_FrameInterp_end, JS_FrameInterp_unwind",
        "JS_FrameCInvokeDisable:",
        '.asciz "QJS_DISABLE_NATIVE_C_INVOKE"',
        '.section .qjsimet,"dw"',
        ".globl JS_FrameCInvokeControl",
        "JS_FrameCInvokeControl:",
        ".byte 0",
        '.section .pdata$zzzzzzzzzzzzcinvoke,"dr"',
        ".p2align 2",
    ]
    for name, _, kind in blocks:
        g += [
            ".rva "
            + name
            + ", "
            + name
            + "_end, cinvoke_"
            + ("leaf" if kind == "leaf" else kind)
            + "_unwind"
        ]
    _append_argv_window(
        g,
        diagnostics,
        argc_guard,
        commit,
        body,
        continuation,
        exception_body,
        exception_continuation,
        config,
        config_continuation,
        out,
    )
    _append_builtin_entry(g, diagnostics, argc_guard, commit, continuation, config, out)
    (out / "quickjs-interpreter-c-invoke-win64.S").write_text("\n".join(g) + "\n", encoding="utf-8")
    _numeric_invoke_module().route_gas(out, diagnostics)
    _numeric_invoke_module().scope_module().route_gas(out)
    (out / "quickjs-interpreter-c-invoke-proof.json").write_text(
        json.dumps(
            dict(
                variant="f94dp",
                parent="f94do",
                changed_branches=changes,
                physical_frame_bytes=128,
                mode="process-wide atomic byte in a separate writable semantic island",
                eligibility="live C class12, generic/magic, positive actual>=formal, original direct/shared/link/generic controls, committed quota, stack and interrupt guards",
                fallback="exact inherited Clean/Dirty host entry; bounded zero/missing arities enter CArgc, special signatures and failed guards retain old host entry",
                success="actual Win64 SRET/by-value-this call; original SF/TLS/GC/quota restoration; XMM0 directly to old owned-value consumer",
                exception="spill to state.result and inherited exception entry",
                old_rx="vs f94do: only two JE displacements in CArgc; positive-argc body and ordinary window unchanged",
                new_code="after qjsknown, no existing GPR/XMM/frame offsets or core machine code change",
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _append_argv_window(
    g,
    diagnostics,
    old_guard,
    old_commit,
    old_body,
    old_continue,
    old_exception,
    old_exception_continue,
    old_config,
    old_config_continue,
    out,
):
    """Bounded arity fixup, before the same native SF/TLS/ownership protocol.

    Only actual0/formal0..2 or actual1/formal2 reaches this island. A borrowed
    argument is copied without Dup/Free, as in js_call_c_function. Missing
    slots are undefined. The native SF counts readable slots; the C callback
    and the caller's pending-value ledger retain the actual argument count.
    The 240-byte body fits the inherited formal*16+256 stack guard, including
    the native return address. Larger arities retain the old checked path.
    """
    abi_layout = current_abi()
    abi_fields = abi_layout["offsets"]
    rename = lambda s: s.replace("cinvoke_", "cargc_").replace("JS_FrameCInvoke", "JS_FrameCArgc")
    tail = old_guard[
        old_guard.index(next(s for s in old_guard if s.startswith("cmp BYTE PTR [rbx+"))) :
    ]
    # Keep the shared positive-argc control/configuration. A separate switch
    # permits a same-image ablation without disabling the existing C kernel.
    # Call preparation chooses the retained signature-specific adapters first.
    # DN preempted these with generic ABI calls, losing their native SF view.
    # Compare the live target each time; this does not cache a callee/realm or
    # public length. Nonmatching descriptors still reach the checked legacy
    # dispatcher, including when a signature-specific adapter is disabled.
    guard = [
        "lea rax, [rip+qjs_frame_core_js_number_toString]",
        f"cmp QWORD PTR [rdx+{abi_fields['JSObject.u.cfunc.c_function']}], rax",
        "je cargc_fallback",
        "lea rax, [rip+qjs_frame_core_js_string_slice]",
        f"cmp QWORD PTR [rdx+{abi_fields['JSObject.u.cfunc.c_function']}], rax",
        "je cargc_fallback",
        f"cmp BYTE PTR [rdx+{abi_fields['JSObject.u.cfunc.cproto']}], 1",
        "ja cargc_fallback",
        f"cmp BYTE PTR [rdx+{abi_fields['JSObject.u.cfunc.length']}], 2",
        "ja cargc_fallback",
        "cmp ecx, 1",
        "ja cargc_fallback",
    ]
    for s in tail:
        if s == "jmp JS_FrameCInvokeCommit":
            guard += [
                "cmp BYTE PTR [rip+JS_FrameCArgcControl], 0",
                "je JS_FrameCArgcConfig",
                "cmp BYTE PTR [rip+JS_FrameCArgcControl], 1",
                "jne cargc_fallback",
                "jmp JS_FrameCArgcCommit",
            ]
        else:
            guard.append(s.replace("cinvoke_", "cargc_"))
    commit = [rename(s) for s in old_commit]
    body = [
        rename(s)
        .replace("sub rsp, 208", "sub rsp, 240")
        .replace("add rsp, 208", "add rsp, 240")
        .replace("[rsp+256]", "[rsp+288]")
        for s in old_body
    ]
    at = body.index("cargc_this_ready:") + 1
    body[at:at] = [
        f"movzx eax, BYTE PTR [rdx+{abi_fields['JSObject.u.cfunc.length']}]",
        "cmp ecx, eax",
        "jae cargc_args_ready",
        "mov QWORD PTR [rsp+208], 0",
        "mov QWORD PTR [rsp+216], 3",
        "mov QWORD PTR [rsp+224], 0",
        "mov QWORD PTR [rsp+232], 3",
        "test ecx, ecx",
        "jz cargc_padded",
        "movdqu xmm2, XMMWORD PTR [r8]",
        "movdqa XMMWORD PTR [rsp+208], xmm2",
        "cargc_padded:",
        "lea r8, [rsp+208]",
        "mov QWORD PTR [rsp+72], r8",
        "mov WORD PTR [rsp+106], ax",
        "mov QWORD PTR [rsp+32], r8",
        "cargc_args_ready:",
    ]
    continuation = [rename(s) for s in old_continue]
    exception_body = [rename(s).replace("add rsp, 208", "add rsp, 240") for s in old_exception]
    exception_continue = [rename(s) for s in old_exception_continue]
    config = [rename(s) for s in old_config]
    config_continue = [rename(s) for s in old_config_continue]
    blocks = [
        ("JS_FrameCArgcGuard", guard, "leaf"),
        ("JS_FrameCArgcCommit", commit, "leaf"),
        ("JS_FrameCArgcBody", body, "body"),
        ("JS_FrameCArgcContinue", continuation, "leaf"),
        ("JS_FrameCArgcException", exception_body, "outbody"),
        ("JS_FrameCArgcExceptionContinue", exception_continue, "leaf"),
        ("JS_FrameCArgcConfig", config, "config"),
        ("JS_FrameCArgcConfigContinue", config_continue, "leaf"),
    ]
    g += ['.section .qjsargc,"xr"']
    for name, stream, kind in blocks:
        if not name.endswith("Continue"):
            g += [".p2align 4"]
        g += [
            ".globl " + name + ", " + name + "_end",
            ".def " + name + "; .scl 2; .type 32; .endef",
            name + ":",
        ]
        for s in stream:
            if s.endswith(":"):
                g += [".globl " + s[:-1]]
            g.append(s)
        g += [name + "_end:"]
    g += [
        ".p2align 2",
        "cargc_leaf_unwind:",
        ".byte 33, 0, 0, 0",
        ".rva JS_FrameInterp, JS_FrameInterp_end, JS_FrameInterp_unwind",
        "cargc_body_unwind:",
        ".byte 33, cargc_alloc-JS_FrameCArgcBody, 2, 0",
        ".byte cargc_alloc-JS_FrameCArgcBody, 1",
        ".short 30",
        ".rva JS_FrameInterp, JS_FrameInterp_end, JS_FrameInterp_unwind",
        "cargc_outbody_unwind:",
        ".byte 33, 0, 2, 0",
        ".byte 0, 1",
        ".short 30",
        ".rva JS_FrameInterp, JS_FrameInterp_end, JS_FrameInterp_unwind",
        "cargc_config_unwind:",
        ".byte 33, cargc_config_alloc-JS_FrameCArgcConfig, 1, 0",
        ".byte cargc_config_alloc-JS_FrameCArgcConfig, 0xb2",
        ".short 0",
        ".rva JS_FrameInterp, JS_FrameInterp_end, JS_FrameInterp_unwind",
        "JS_FrameCArgcDisable:",
        '.asciz "QJS_DISABLE_NATIVE_C_ARG_WINDOW"',
        '.section .qjsargm,"dw"',
        ".globl JS_FrameCArgcControl",
        "JS_FrameCArgcControl:",
        ".byte 0",
        '.section .pdata$zzzzzzzzzzzzcargc,"dr"',
        ".p2align 2",
    ]
    for name, _, kind in blocks:
        g += [".rva " + name + ", " + name + "_end, cargc_" + kind + "_unwind"]
    (out / "quickjs-interpreter-c-argc-proof.json").write_text(
        json.dumps(
            dict(
                variant="f94dp",
                parent="f94do",
                eligibility="generic/magic actual0/formal0..2 or actual1/formal2; retained number-toString/string-slice adapters take priority",
                caller_ownership="actual pending count unchanged; borrowed padded window has no Dup/Free",
                native_sf="arg_count=max(actual,formal), argv=original unless padded, actual argc passed to C",
                allocation="240-byte fixed native stack body; two 16-byte slots at208..239; no heap allocation",
                guard="inherited formal*16+256 and all runtime/direct/shared/interrupt controls",
                ablation="QJS_DISABLE_NATIVE_C_ARG_WINDOW; existing C invoke control also respected",
                layout="two existing near-Jcc displacements; new RX/RW islands follow qjsimet",
                fallback="formal>2, actual>1, special C signatures and every failed guard",
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _append_builtin_entry(g, diagnostics, old_guard, old_commit, old_continue, old_config, out):
    """Select the native-view entry once, then prepare/invoke that ABI.

    The preceding live code-pointer comparisons are the static descriptor
    keys. Validate the private signature and actual arity before selecting
    its entry. No weak object, context, shape or mutable guard is cached.
    The stack view is borrowed for this activation only. Reentry retains
    the original shared SF/TLS protocol and the caller's ownership ledger.
    """
    abi_layout = current_abi()
    abi_fields = abi_layout["offsets"]
    # Change only two near-JE operands in the retained CArgc guard. Its size,
    # every old PC, the ordinary arity window and positive C invoke stay fixed.
    lo = g.index("JS_FrameCArgcGuard:")
    hi = g.index("JS_FrameCArgcGuard_end:")
    for target, entry in (
        ("qjs_frame_core_js_number_toString", "JS_FrameBuiltinNumberEntry"),
        ("qjs_frame_core_js_string_slice", "JS_FrameBuiltinSliceEntry"),
    ):
        at = g.index("lea rax, [rip+" + target + "]", lo, hi) + 2
        assert g[at] == "je cargc_fallback"
        g[at] = "je " + entry
    rename = lambda s: s.replace("cinvoke_", "builtin_").replace(
        "JS_FrameCInvoke", "JS_FrameBuiltin"
    )
    number = [
        f"cmp WORD PTR [rdx+{abi_fields['JSObject.u.cfunc.length']}], 257",
        "jne builtin_fallback",
        f"cmp WORD PTR [rdx+{abi_fields['JSObject.u.cfunc.magic']}], 0",
        "jne builtin_fallback",
        "test ecx, ecx",
        "jnz builtin_fallback",
        "mov rax, QWORD PTR [rbx+56]",
        f"test BYTE PTR [rax+{abi_fields['JSRuntime.module_loader_has_attr'] + 5}], 32",
        "jnz builtin_fallback",
        "lea r9, [rip+JS_FrameNumberToStringNative]",
        "jmp JS_FrameBuiltinGuard",
    ]
    slice_entry = [
        f"cmp WORD PTR [rdx+{abi_fields['JSObject.u.cfunc.length']}], 2",
        "jne builtin_fallback",
        "cmp ecx, 1",
        "ja builtin_fallback",
        "lea r9, [rip+JS_FrameStringSliceNative]",
        "jmp JS_FrameBuiltinGuard",
    ]
    tail = old_guard[
        old_guard.index(next(s for s in old_guard if s.startswith("cmp BYTE PTR [rbx+"))) :
    ]
    guard = []
    for s in tail:
        if s == "jmp JS_FrameCInvokeCommit":
            guard += [
                # Retain all native-view/window and VM adapter controls.
                f"cmp BYTE PTR [rax+{abi_fields['JSRuntime.module_normalize_has_attr'] + 2}], 1",
                "jne builtin_fallback",
                f"movzx r10d, BYTE PTR [rax+{abi_fields['JSRuntime.module_loader_has_attr'] + 5}]",
                "and r10d, 15",
                "cmp r10d, 1",
                "jne builtin_fallback",
                "cmp BYTE PTR [rip+JS_FrameBuiltinControl], 0",
                "je JS_FrameBuiltinConfig",
                "cmp BYTE PTR [rip+JS_FrameBuiltinControl], 1",
                "jne builtin_fallback",
                "jmp JS_FrameBuiltinCommit",
            ]
        else:
            guard.append(s.replace("cinvoke_", "builtin_"))
    commit = [rename(s) for s in old_commit]
    committed = 2304 if diagnostics else 64
    native_limit = 2312 if diagnostics else 72
    shared_limit = 2320 if diagnostics else 80
    exception = 2296 if diagnostics else 160
    # Shadow32, original JSNativeFrameView128 at32, result16 at160,
    # selected immutable entry pointer8 at176, alignment padding8 at184.
    body = [
        "sub rsp, 192",
        "builtin_alloc:",
        "mov QWORD PTR [rsp+176], r9",
        f"mov rax, QWORD PTR [r10+{abi_fields['JSRuntime.current_stack_frame']}]",
        "mov QWORD PTR [rsp+32], rax",
        "movdqu xmm2, XMMWORD PTR [r8-16]",
        "movdqu XMMWORD PTR [rsp+40], xmm2",
        "mov QWORD PTR [rsp+56], r8",
        "pxor xmm2, xmm2",
        "movdqu XMMWORD PTR [rsp+64], xmm2",
        "movdqu XMMWORD PTR [rsp+80], xmm2",
        "movdqu XMMWORD PTR [rsp+96], xmm2",
        "mov WORD PTR [rsp+90], cx",
        "lea rax, [rdi+2048]",
        "cmp DWORD PTR [rsp+240], 0",
        "je builtin_this_ready",
        "lea rax, [r8-32]",
        "builtin_this_ready:",
        "mov QWORD PTR [rsp+64], rax",
        "mov rax, QWORD PTR gs:88",
        "mov ecx, DWORD PTR [rip+_tls_index]",
        "mov rax, QWORD PTR [rax+rcx*8]",
        "lea rcx, [rip+JS_FrameSharedTop]",
        "lea r9, [rip+_tls_start]",
        "sub rcx, r9",
        "add rax, rcx",
        "mov QWORD PTR [rsp+136], rax",
        "mov rcx, QWORD PTR [rax]",
        "mov QWORD PTR [rsp+112], rcx",
        "mov QWORD PTR [rsp+120], rbx",
        "mov DWORD PTR [rsp+128], 0",
        f"mov cl, BYTE PTR [r10+{abi_fields['JSRuntime.current_stack_frame'] - 5}]",
        "and cl, 4",
        "mov BYTE PTR [rsp+144], cl",
        "lea rcx, [rsp+32]",
        f"mov QWORD PTR [r10+{abi_fields['JSRuntime.current_stack_frame']}], rcx",
        "lea rcx, [rsp+112]",
        f"or BYTE PTR [r10+{abi_fields['JSRuntime.current_stack_frame'] - 5}], 4",
        "mov QWORD PTR [rax], rcx",
        "mov r11, QWORD PTR [rsp+176]",
        "lea rcx, [rsp+32]",
        "lea rdx, [rsp+160]",
    ]
    if diagnostics:
        body += ["inc QWORD PTR [rbx+2264]", "inc QWORD PTR [rbx+2208]"]
    body += [
        "JS_FrameBuiltinCall:",
        "call r11",
        "JS_FrameBuiltinAfterCall:",
        "mov r10, QWORD PTR [rbx+56]",
        "mov r11, QWORD PTR [rsp+136]",
        "mov rax, QWORD PTR [rsp+112]",
        "mov QWORD PTR [r11], rax",
        f"mov al, BYTE PTR [r10+{abi_fields['JSRuntime.current_stack_frame'] - 5}]",
        "and al, 251",
        "or al, BYTE PTR [rsp+144]",
        f"mov BYTE PTR [r10+{abi_fields['JSRuntime.current_stack_frame'] - 5}], al",
        "mov rax, QWORD PTR [rsp+32]",
        f"mov QWORD PTR [r10+{abi_fields['JSRuntime.current_stack_frame']}], rax",
        "mov rax, QWORD PTR [rbx+32]",
        f"mov rdx, QWORD PTR [r10+{abi_fields['JSRuntime.stack_limit']}]",
        f"cmp rax, QWORD PTR [rbx+{committed}]",
        "jne builtin_refresh",
        f"cmp rdx, QWORD PTR [rbx+{shared_limit}]",
        "je builtin_refreshed",
        "builtin_refresh:",
        f"mov QWORD PTR [rbx+{committed}], rax",
        f"mov QWORD PTR [rbx+{shared_limit}], rdx",
        "test rdx, rdx",
        "jz builtin_limit",
        "sub rdx, rax",
        "builtin_limit:",
        f"mov QWORD PTR [rbx+{native_limit}], rdx",
        "builtin_refreshed:",
        "movdqu xmm0, XMMWORD PTR [rsp+160]",
        "cmp QWORD PTR [rsp+168], 6",
        f"sete BYTE PTR [rbx+{exception}]",
        "je JS_FrameBuiltinException",
        "add rsp, 192",
    ]
    continuation = [rename(s) for s in old_continue]
    exception_body = ["movdqu XMMWORD PTR [rbx+40], xmm0", "add rsp, 192"]
    config = [rename(s) for s in old_config]
    config[-1] = "add rsp, 96"
    blocks = [
        ("JS_FrameBuiltinNumberEntry", number, "leaf"),
        ("JS_FrameBuiltinSliceEntry", slice_entry, "leaf"),
        ("JS_FrameBuiltinGuard", guard, "leaf"),
        ("JS_FrameBuiltinCommit", commit, "leaf"),
        ("JS_FrameBuiltinBody", body, "body"),
        ("JS_FrameBuiltinContinue", continuation, "leaf"),
        ("JS_FrameBuiltinException", exception_body, "outbody"),
        ("JS_FrameBuiltinExceptionContinue", ["jmp interp_host_exception"], "leaf"),
        ("JS_FrameBuiltinConfig", config, "config"),
        ("JS_FrameBuiltinConfigContinue", ["jmp JS_FrameBuiltinGuard"], "leaf"),
    ]
    g += ['.section .qjsbent,"xr"']
    for name, stream, kind in blocks:
        if not name.endswith("Continue"):
            g += [".p2align 4"]
        g += [
            ".globl " + name + ", " + name + "_end",
            ".def " + name + "; .scl 2; .type 32; .endef",
            name + ":",
        ]
        for s in stream:
            if s.endswith(":"):
                g += [".globl " + s[:-1]]
            g.append(s)
        g += [name + "_end:"]
    g += [
        ".p2align 2",
        "builtin_leaf_unwind:",
        ".byte 33, 0, 0, 0",
        ".rva JS_FrameInterp, JS_FrameInterp_end, JS_FrameInterp_unwind",
        "builtin_body_unwind:",
        ".byte 33, builtin_alloc-JS_FrameBuiltinBody, 2, 0",
        ".byte builtin_alloc-JS_FrameBuiltinBody, 1",
        ".short 24",
        ".rva JS_FrameInterp, JS_FrameInterp_end, JS_FrameInterp_unwind",
        "builtin_outbody_unwind:",
        ".byte 33, 0, 2, 0",
        ".byte 0, 1",
        ".short 24",
        ".rva JS_FrameInterp, JS_FrameInterp_end, JS_FrameInterp_unwind",
        "builtin_config_unwind:",
        ".byte 33, builtin_config_alloc-JS_FrameBuiltinConfig, 1, 0",
        ".byte builtin_config_alloc-JS_FrameBuiltinConfig, 0xb2",
        ".short 0",
        ".rva JS_FrameInterp, JS_FrameInterp_end, JS_FrameInterp_unwind",
        "JS_FrameBuiltinDisable:",
        '.asciz "QJS_DISABLE_NATIVE_BUILTIN_ENTRY"',
        '.section .qjsbenm,"dw"',
        ".globl JS_FrameBuiltinControl",
        "JS_FrameBuiltinControl:",
        ".byte 0",
        '.section .pdata$zzzzzzzzzzzzcbuiltin,"dr"',
        ".p2align 2",
    ]
    for name, _, kind in blocks:
        g += [".rva " + name + ", " + name + "_end, builtin_" + kind + "_unwind"]
    (out / "quickjs-interpreter-builtin-entry-proof.json").write_text(
        json.dumps(
            dict(
                variant="f94dp",
                parent="f94do",
                descriptor="live target + exact private signature and actual arity selects a static native-view entry",
                eligibility="Number.toString magic0/formal1/actual0; String.slice generic/formal2/actual0..1; original shared/direct/link/generic/window/VM/Number controls",
                preparation="caller PC/SP and actual pending ownership; nonowning 128-byte native view on the C stack",
                invocation="selected helper(view,out) exactly once; no generic dispatch or repeated builtin classification",
                native_stack_bytes=192,
                physical_frame_bytes=128,
                object_cache=False,
                ablation="QJS_DISABLE_NATIVE_BUILTIN_ENTRY; QJS_DISABLE_NATIVE_C_INVOKE also disables this fusion",
                layout="only two JE operands in old CArgc; all other old RX pinned; appended qjsbent/qjsbenm",
                limitation="static signature-specific descriptors; no callsite PIC or GC weak-target cache",
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def append_masm(masm, diagnostics, out):
    """Private VM JMP entry, one Win64 C call, original owned-value return.

    The VM already saved all nonvolatile GPRs. Every precommit failure jumps
    to its exact old host entry. Positive actual >= formal generic/magic only;
    zero/missing, numeric, bound/proxy and disabled shared modes stay there.
    """
    abi_layout = current_abi()
    abi_fields = abi_layout["offsets"]
    import re

    (
        regs,
        entry,
        dirty,
        guard,
        argc_guard,
        commit,
        body,
        continuation,
        exception_body,
        exception_continuation,
        config,
        config_continuation,
    ) = _vm_kernel(diagnostics, False)
    before = ("jne interp_host_call", "jne NEAR PTR interp_host_call")
    assert sum(masm.count(x) for x in before) == 2
    for i, line in enumerate(masm):
        if line in before:
            assert masm[i - 1] == f"cmp WORD PTR [rdx+{abi_fields['JSObject.class_id']}], 13"
            masm[i] = "jne NEAR PTR JS_FrameCInvokeEntry"
    assert masm.pop() == "END"
    masm.insert(0, "EXTERN JS_FrameDensePopLeafEntry:PROC")
    # Copy the already ABI-bound own-property probe. Route only the old
    # five-byte C call in the separate cold block; hot interpreter is intact.
    first = masm.index("mov r9d, DWORD PTR [r12+1]", masm.index("interp_get_field2::"))
    last = masm.index("interp_get_field2_noref::", first)
    own_probe = masm[first:last]
    call = masm.index("call JS_FrameInterpProperty_get_field2")
    assert masm[call - 1] == "mov rcx, rbx"
    masm[call] = "jmp NEAR PTR JS_FrameStringProtoEntry"
    masm[call + 1 : call + 1] = ["PUBLIC JS_FrameStringProtoReturn", "JS_FrameStringProtoReturn::"]
    masm.insert(0, "EXTERN JS_FrameStringProtoEntry:PROC")
    (out / "msvc-string-proto-template.json").write_text(
        json.dumps(
            dict(
                status="passed",
                diagnostics=diagnostics,
                own_probe=own_probe,
                policy="Only one existing cold CALL becomes equal-width near JMP; zero-byte return alias. Full old hot VM and native guards preserved.",
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    blocks = [
        ("JS_FrameCInvokeEntry", entry, "leaf"),
        ("JS_FrameCInvokeGuard", guard, "leaf"),
        ("JS_FrameCInvokeCommit", commit, "leaf"),
        ("JS_FrameCInvokeBody", body, "body"),
        ("JS_FrameCInvokeContinue", continuation, "leaf"),
        ("JS_FrameCInvokeException", exception_body, "outbody"),
        ("JS_FrameCInvokeExceptionContinue", exception_continuation, "leaf"),
        ("JS_FrameCInvokeConfig", config, "config"),
        ("JS_FrameCInvokeConfigContinue", config_continuation, "leaf"),
    ]
    # MSVC's compiler-owned native TLS uses SECREL; unlike the MinGW GAS
    # contribution this has no erroneous HIGHLOW base relocation.
    tls_g = [
        "mov rax, QWORD PTR gs:88",
        "mov ecx, DWORD PTR [rip+_tls_index]",
        "mov rax, QWORD PTR [rax+rcx*8]",
        "lea rcx, [rip+JS_FrameSharedTop]",
        "lea r9, [rip+_tls_start]",
        "sub rcx, r9",
        "add rax, rcx",
    ]
    tls_m = [
        "mov rax, QWORD PTR gs:[88]",
        "mov ecx, DWORD PTR [_tls_index]",
        "mov rax, QWORD PTR [rax+rcx*8]",
        "mov ecx, SECTIONREL js_frame_shared_top",
        "add rax, rcx",
    ]
    joined = "\n".join(body)
    assert joined.count("\n".join(tls_g)) == 1
    body[:] = joined.replace("\n".join(tls_g), "\n".join(tls_m)).splitlines()
    # Preserve all fields, stack arguments, SRET/this temporaries and restore
    # lists. Only RIP operand spelling, external JMP encoding and TLS differ.
    # These existing groups contain the primitive entry and its control.
    # Append once; never search padding, image bases or section placements.
    assert any(x.startswith(".qjszlf SEGMENT") for x in masm)
    assert any(x.startswith(".qjszlm SEGMENT") for x in masm)
    section = ".qjszlf"
    masm += [section + " SEGMENT ALIGN(16) 'CODE'"]
    for name, lines, kind in blocks:
        if not name.endswith("Continue"):
            masm += ["ALIGN 16"]
        masm += ["PUBLIC " + name + ", " + name + "_end", name + " PROC"]
        for line in lines:
            line = re.sub(r"\[rip\+([^]]+)\]", r"[\1]", line)
            if line == "lea r11, [interp_host_call]":
                line = "lea r11, interp_host_call"
            if line == "lea rcx, [JS_FrameCInvokeDisable]":
                line = "lea rcx, JS_FrameCInvokeDisable"
            if line == "call getenv":
                line = "call QWORD PTR [__imp_getenv]"
            if line.endswith(":"):
                masm += ["PUBLIC " + line[:-1], line[:-1] + "::"]
            else:
                line = re.sub(r"^(j\w+) (JS_Frame\w+|interp_\w+)$", r"\1 NEAR PTR \2", line)
                masm += [line]
        masm += [name + "_end LABEL BYTE", name + " ENDP"]
    masm += [
        "ALIGN 4",
        "cinvoke_leaf_unwind LABEL BYTE",
        "DB 021h,0,0,0",
        "DD IMAGEREL JS_FrameInterp, IMAGEREL JS_FrameInterp_end, IMAGEREL JS_FrameInterp_unwind",
        "cinvoke_body_unwind LABEL BYTE",
        "DB 021h,cinvoke_alloc-JS_FrameCInvokeBody,2,0",
        "DB cinvoke_alloc-JS_FrameCInvokeBody,1",
        "DW 26",
        "DD IMAGEREL JS_FrameInterp, IMAGEREL JS_FrameInterp_end, IMAGEREL JS_FrameInterp_unwind",
        "cinvoke_outbody_unwind LABEL BYTE",
        "DB 021h,0,2,0",
        "DB 0,1",
        "DW 26",
        "DD IMAGEREL JS_FrameInterp, IMAGEREL JS_FrameInterp_end, IMAGEREL JS_FrameInterp_unwind",
        "cinvoke_config_unwind LABEL BYTE",
        "DB 021h,cinvoke_config_alloc-JS_FrameCInvokeConfig,1,0",
        "DB cinvoke_config_alloc-JS_FrameCInvokeConfig,0b2h",
        "DW 0",
        "DD IMAGEREL JS_FrameInterp, IMAGEREL JS_FrameInterp_end, IMAGEREL JS_FrameInterp_unwind",
        section + " ENDS",
        ".pdata$zzqjsinvoke SEGMENT ALIGN(4) READONLY 'DATA'",
    ]
    for name, _, kind in blocks:
        masm += [
            "DD IMAGEREL "
            + name
            + ", IMAGEREL "
            + name
            + "_end, IMAGEREL cinvoke_"
            + kind
            + "_unwind"
        ]
    masm += [
        ".pdata$zzqjsinvoke ENDS",
        ".qjszlm SEGMENT ALIGN(1) 'DATA'",
        "PUBLIC JS_FrameCInvokeControl",
        "JS_FrameCInvokeControl DB 0",
        'JS_FrameCInvokeDisable DB "QJS_DISABLE_NATIVE_C_INVOKE",0',
        ".qjszlm ENDS",
        "END",
    ]
    _numeric_invoke_module().route_masm(masm)
    _numeric_invoke_module().scope_module().route_masm(masm)
    (out / "msvc-c-invoke-generation.json").write_text(
        json.dumps(
            dict(
                status="passed",
                toolchain="msvc",
                diagnostics=diagnostics,
                shared_instruction_kernel=True,
                physical_frame_bytes=128,
                c_stack_bytes=208,
                nonvolatile_resaves=0,
                new_gc_roots=0,
                new_cache_or_js_allocations=0,
                changed_branches=2,
                eligibility="live class12 generic/magic, positive actual>=formal, direct/shared/generic enabled, committed quota, conservative stack and interrupt guards",
                fallback="original interp_host_call before any call-state, ownership or poll commit",
                native_abi="real Win64 hidden result, writable aligned this temporary, actual argc, argv and signed magic; live callee realm",
                boundary="original SF/TLS shared anchor and active flag; synchronous C-to-JS reentry; exact restore and quota-limit refresh",
                success="owned XMM0 directly to inherited argument/function/receiver consumer",
                exception="complete JSValue to state.result, inherited host exception path",
                control="QJS_DISABLE_NATIVE_C_INVOKE",
                limits=[
                    "Zero/missing arities and special signatures use the retained host route.",
                    "No persistent callee links or compact physical frame added.",
                ],
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def dense_pop_leaf_kernel(diagnostics, publish, layout):
    """No native frame or call after guards; original owned return handles GC.

    Init/configuration and every rejection remain precommit. Only the live
    code pointer + length0/generic_magic/magic0 and actual0 match. Successful
    empty/dense pops do not allocate, coerce, throw or call user/native code.
    Caller PC/SP and actual pending ledger are published before moving a
    value; the retained release path spills it before reentrant last-ref free.
    """
    abi_layout = current_abi()
    abi_fields = abi_layout["offsets"]
    (_, _, _, old_guard, _, commit, _, _, _, _, _, _) = _vm_kernel(diagnostics, publish)
    fallback = "denseleaf_fallback"
    entry = [
        "lea rax, [rip+JS_FrameDenseArrayPop]",
        f"cmp QWORD PTR [rdx+{abi_fields['JSObject.u.cfunc.c_function']}], rax",
        "jne " + fallback,
        f"cmp WORD PTR [rdx+{abi_fields['JSObject.u.cfunc.length']}], 256",
        "jne " + fallback,
        f"cmp WORD PTR [rdx+{abi_fields['JSObject.u.cfunc.magic']}], 0",
        "jne " + fallback,
        "test ecx, ecx",
        "jnz " + fallback,
    ]
    tail = old_guard[
        old_guard.index(next(x for x in old_guard if x.startswith("cmp BYTE PTR [rbx+"))) :
    ]
    for x in tail:
        if x == "jmp JS_FrameCInvokeCommit":
            if publish:
                entry += [
                    "cmp BYTE PTR [rip+JS_FrameCArgcControl], 0",
                    "je JS_FrameCArgcConfig",
                    "cmp BYTE PTR [rip+JS_FrameCArgcControl], 1",
                    "jne " + fallback,
                ]
            entry += [
                "cmp BYTE PTR [rip+JS_FrameDenseArrayPopControl], 1",
                "jne " + fallback,
                "cmp BYTE PTR [rip+JS_FrameDensePopLeafControl], 1",
                "jne " + fallback,
                "jmp JS_FrameDensePopLeafGuard",
            ]
        elif x == "cinvoke_fallback:":
            entry += [fallback + ":"]
        elif x == "jmp r11":
            entry += ["jmp JS_FrameCArgcGuard" if publish else "jmp r11"]
        else:
            entry.append(x.replace("cinvoke_fallback", fallback))
    # Actual build's types and bitfields, independently probed in C.
    (
        sz,
        tag,
        cls,
        flags,
        flagmask,
        shape,
        prop,
        vals,
        count,
        mask,
        ptable,
        patom,
        shift,
        atom,
        ctxrt,
    ) = layout
    assert sz == 16 and flagmask and shift == 26
    properties = (
        [f"lea r10, [rax+{ptable}]"]
        if abi_layout["reference_count_model"] == "inline-header"
        else [f"mov r10d, DWORD PTR [rax+{mask}]", f"lea r10, [rax+r10*4+{ptable + 4}]"]
    )
    guard = [
        "cmp DWORD PTR [rsp+48], 0",
        "je " + fallback,
        f"cmp QWORD PTR [r8-32+{tag}], -1",
        "jne " + fallback,
        "mov r9, QWORD PTR [r8-32]",
        f"cmp WORD PTR [r9+{cls}], 2",
        "jne " + fallback,
        f"movzx eax, BYTE PTR [r9+{flags}]",
        f"and eax, {flagmask}",
        f"cmp eax, {flagmask}",
        "jne " + fallback,
        f"mov rax, QWORD PTR [rdx+{abi_fields['JSObject.u.cfunc.realm']}]",
        "test rax, rax",
        "jz " + fallback,
        f"mov rax, QWORD PTR [rax+{ctxrt}]",
        "cmp rax, QWORD PTR [rbx+56]",
        "jne " + fallback,
        f"mov rax, QWORD PTR [r9+{shape}]",
        *properties,
        f"cmp DWORD PTR [r10+{patom}], {atom}",
        "jne " + fallback,
        "mov eax, DWORD PTR [r10]",
        f"shr eax, {shift}",
        "cmp eax, 10",
        "jne " + fallback,
        f"mov rax, QWORD PTR [r9+{prop}]",
        f"cmp QWORD PTR [rax+{tag}], 0",
        "jne " + fallback,
        f"mov r10d, DWORD PTR [r9+{count}]",
        "cmp DWORD PTR [rax], r10d",
        "jne " + fallback,
        "cmp r10d, 2147483647",
        "ja " + fallback,
        "jmp JS_FrameDensePopLeafCommit",
    ]
    commit = [
        x.replace("cinvoke_publish_ready", "denseleaf_publish_ready").replace(
            "JS_FrameCInvokeBody", "JS_FrameDensePopLeafBody"
        )
        for x in commit
    ]
    exception = 2296 if diagnostics else 160
    body = [
        f"mov ecx, DWORD PTR [r9+{count}]",
        "test ecx, ecx",
        "jz denseleaf_empty",
        "dec ecx",
        f"mov rax, QWORD PTR [r9+{vals}]",
        "mov r10, rcx",
        "shl r10, 4",
        "movdqu xmm0, XMMWORD PTR [rax+r10]",
        f"mov DWORD PTR [r9+{count}], ecx",
        f"mov rax, QWORD PTR [r9+{prop}]",
        "mov QWORD PTR [rax], rcx",
        "jmp denseleaf_value_ready",
        "denseleaf_empty:",
        "mov eax, 3",
        "movq xmm0, rax",
        "pslldq xmm0, 8",
        "denseleaf_value_ready:",
        f"mov BYTE PTR [rbx+{exception}], 0",
    ]
    if diagnostics:
        body += ["lock inc QWORD PTR [rip+JS_FrameDensePopLeafHits]"]
    body += ["jmp JS_FrameCInvokeContinue"]
    return [
        ("JS_FrameDensePopLeafEntry", entry),
        ("JS_FrameDensePopLeafGuard", guard),
        ("JS_FrameDensePopLeafCommit", commit),
        ("JS_FrameDensePopLeafBody", body),
    ]


def _prototype_layout(abi):
    fields = abi["offsets"]
    constants = abi["constants"]
    ((exotic_byte, exotic_mask),) = abi["bits"]["JSObject.is_exotic"]
    assert abi["bits"]["JSShapeProperty.flags"] == [[3, 4]]
    table = fields[
        "JSShape.prop" if abi["reference_count_model"] == "inline-header" else "JSShape.hash_table"
    ]
    return (
        fields["JSContext.class_proto"],
        constants["JS_CLASS_STRING"],
        constants["JS_CLASS_OBJECT"],
        abi["sizes"]["JSValue"],
        fields["JSValue.tag"],
        fields["JSObject.class_id"],
        fields["JSObject.shape"],
        fields["JSObject.prop"],
        fields["JSShape.prop_hash_mask"],
        table,
        fields["JSShapeProperty.atom"],
        26,
        constants["JS_PROP_TMASK"],
        exotic_byte,
        exotic_mask,
    )


def string_proto_data_kernel(diagnostics, layout, own_probe):
    """Live flat-string prototype own data read, no object/slot/value cache.

    Enter through the already-published get_field2 cold boundary by JMP.
    All durable inputs reside in the VM's nonvolatile registers. Success
    allocates/calls nothing, retains the receiver, duplicates the current
    value exactly once and performs the inherited opcode's stack effect.
    """
    (
        length,
        proto,
        string_cls,
        object_cls,
        size,
        tag,
        cls,
        shape,
        prop,
        mask,
        table,
        atom,
        shift,
        tmask,
        exo,
        exobit,
    ) = layout
    assert tuple(layout[1:]) == _prototype_layout(current_abi())
    assert own_probe[0] == "mov r9d, DWORD PTR [r12+1]"
    probe = []
    for line in own_probe:
        line = line.replace("interp_get_field2_obj_", "stringproto_obj_")
        line = line.replace("interp_property_slow_get_field2", "JS_FrameStringProtoFallback")
        line = line.replace("interp_get_field2_noref", "JS_FrameStringProtoFinish")
        probe.append(line[:-1] if line.endswith("::") else line)
    finish = []
    if diagnostics:
        finish += ["lock inc DWORD PTR [JS_FrameStringProtoHits]"]
    finish += [
        "mov QWORD PTR [r13], rax",
        "mov QWORD PTR [r13+8], rdx",
        "add r13, 16",
        "add r12, 5",
        "movzx eax, BYTE PTR [r12]",
        "jmp QWORD PTR [rdi+rax*8]",
    ]
    return [
        (
            "JS_FrameStringProtoEntry",
            [
                "cmp DWORD PTR [r13-8], -7",
                "jne JS_FrameObjectProtoEntry",
                "mov r9d, DWORD PTR [r12+1]",
                "test r9d, r9d",
                "js JS_FrameStringProtoFallback",
                f"cmp r9d, {length}",
                "je JS_FrameStringProtoFallback",
                "cmp BYTE PTR [JS_FrameStringProtoControl], 0",
                "je JS_FrameStringProtoConfig",
                "cmp BYTE PTR [JS_FrameStringProtoControl], 1",
                "jne JS_FrameStringProtoFallback",
                "jmp JS_FrameStringProtoHolder",
            ],
        ),
        (
            "JS_FrameStringProtoHolder",
            [
                f"mov r8, QWORD PTR [rsi+{proto}]",
                f"cmp DWORD PTR [r8+{string_cls * size + tag}], -1",
                "jne JS_FrameStringProtoFallback",
                f"mov r8, QWORD PTR [r8+{string_cls * size}]",
                f"cmp WORD PTR [r8+{cls}], {string_cls}",
                "je JS_FrameStringProtoLookup",
                f"cmp WORD PTR [r8+{cls}], {object_cls}",
                "jne JS_FrameStringProtoFallback",
                f"test BYTE PTR [r8+{exo}], {exobit}",
                "jnz JS_FrameStringProtoFallback",
                "jmp JS_FrameStringProtoLookup",
            ],
        ),
        ("JS_FrameStringProtoLookup", probe + ["jmp JS_FrameStringProtoFinish"]),
        ("JS_FrameStringProtoFinish", finish),
        (
            "JS_FrameStringProtoFallback",
            [
                "mov rcx, rbx",
                "call JS_FrameInterpProperty_get_field2",
                "jmp JS_FrameStringProtoReturn",
            ],
        ),
        (
            "JS_FrameStringProtoConfig",
            [
                # The original VM activation already supplies aligned Win64
                # shadow space. getenv has no JS hook; nonvolatile VM registers
                # survive. Reread every scratch input at Entry after configuration.
                "lea rcx, JS_FrameStringProtoDisable",
                "call QWORD PTR [__imp_getenv]",
                "test rax, rax",
                "setne cl",
                "inc cl",
                "xor eax, eax",
                "lock cmpxchg BYTE PTR [JS_FrameStringProtoControl], cl",
                "jmp JS_FrameStringProtoEntry",
            ],
        ),
        ("JS_FrameStringProtoState", ["movzx eax, BYTE PTR [JS_FrameStringProtoControl]", "ret"]),
        (
            "JS_FrameStringProtoCount",
            (["mov eax, DWORD PTR [JS_FrameStringProtoHits]"] if diagnostics else ["xor eax, eax"])
            + ["ret"],
        ),
    ]


def object_proto_data_kernel(diagnostics, layout, own_probe):
    """Live ordinary receiver -> immediate ordinary prototype data property.

    Prove receiver own-absence afresh, then probe the current shape's live
    prototype. No retained identities, slots or targets, no new stack or root.
    The existing control payload's unused byte19 holds mode + diagnostic hit.
    """
    (
        length,
        proto,
        string_cls,
        object_cls,
        size,
        tag,
        cls,
        shape,
        prop,
        mask,
        table,
        atom,
        shift,
        tmask,
        exo,
        exobit,
    ) = layout
    assert tuple(layout[1:]) == _prototype_layout(current_abi())
    proto_offset = current_abi()["offsets"]["JSShape.proto"]
    # The selected JSShape.proto is independently asserted by the C probe.
    found = own_probe.index("interp_get_field2_obj_found::")
    absence = []
    for line in own_probe[:found]:
        line = line.replace("interp_get_field2_obj_probe", "objectproto_own_probe")
        line = line.replace("interp_get_field2_obj_found", "JS_FrameObjectProtoFallback")
        line = line.replace("interp_property_slow_get_field2", "JS_FrameObjectProtoHolder")
        absence.append(line[:-1] if line.endswith("::") else line)
    probe = []
    for line in own_probe:
        line = line.replace("interp_get_field2_obj_", "objectproto_holder_")
        line = line.replace("interp_property_slow_get_field2", "JS_FrameObjectProtoFallback")
        line = line.replace("interp_get_field2_noref", "JS_FrameObjectProtoFinish")
        probe.append(line[:-1] if line.endswith("::") else line)
    finish = ["lock or BYTE PTR [JS_FrameObjectProtoControl], 128"] if diagnostics else []
    finish += [
        "mov QWORD PTR [r13], rax",
        "mov QWORD PTR [r13+8], rdx",
        "add r13, 16",
        "add r12, 5",
        "movzx eax, BYTE PTR [r12]",
        "jmp QWORD PTR [rdi+rax*8]",
    ]
    return [
        (
            "JS_FrameObjectProtoEntry",
            [
                "cmp DWORD PTR [r13-8], -1",
                "jne JS_FrameObjectProtoFallback",
                "mov r8, QWORD PTR [r13-16]",
                f"cmp WORD PTR [r8+{cls}], {object_cls}",
                "jne JS_FrameObjectProtoFallback",
                f"test BYTE PTR [r8+{exo}], {exobit}",
                "jnz JS_FrameObjectProtoFallback",
                "mov r9d, DWORD PTR [r12+1]",
                "test r9d, r9d",
                "js JS_FrameObjectProtoFallback",
                "cmp BYTE PTR [JS_FrameObjectProtoControl], 0",
                "je JS_FrameObjectProtoConfig",
                "test BYTE PTR [JS_FrameObjectProtoControl], 1",
                "jz JS_FrameObjectProtoFallback",
                "jmp JS_FrameObjectProtoOwn",
            ],
        ),
        ("JS_FrameObjectProtoOwn", absence),
        (
            "JS_FrameObjectProtoHolder",
            [
                f"mov r8, QWORD PTR [r10+{proto_offset}]",
                "test r8, r8",
                "jz JS_FrameObjectProtoFallback",
                f"cmp WORD PTR [r8+{cls}], {object_cls}",
                "jne JS_FrameObjectProtoFallback",
                f"test BYTE PTR [r8+{exo}], {exobit}",
                "jnz JS_FrameObjectProtoFallback",
                "jmp JS_FrameObjectProtoHintEntry",
            ],
        ),
        ("JS_FrameObjectProtoLookup", probe + ["jmp JS_FrameObjectProtoHintFill"]),
        ("JS_FrameObjectProtoFinish", finish),
        ("JS_FrameObjectProtoFallback", ["jmp JS_FrameStringProtoFallback"]),
        (
            "JS_FrameObjectProtoConfig",
            [
                "lea rcx, JS_FrameObjectProtoDisable",
                "call QWORD PTR [__imp_getenv]",
                "test rax, rax",
                "setne cl",
                "inc cl",
                "xor eax, eax",
                "lock cmpxchg BYTE PTR [JS_FrameObjectProtoControl], cl",
                "jmp JS_FrameObjectProtoEntry",
            ],
        ),
        (
            "JS_FrameObjectProtoState",
            ["movzx eax, BYTE PTR [JS_FrameObjectProtoControl]", "and eax, 3", "ret"],
        ),
        (
            "JS_FrameObjectProtoHit",
            (
                ["movzx eax, BYTE PTR [JS_FrameObjectProtoControl]", "shr eax, 7"]
                if diagnostics
                else ["xor eax, eax"]
            )
            + ["ret"],
        ),
    ]


def object_proto_hint_kernel(diagnostics):
    """Scalar-only hints, always checked against the current holder descriptor.

    Each aligned 32-bit cell contains slot+1, with zero meaning empty. Cells
    are independent, have no identity/key publication protocol and contain no
    pointers. A racing/recycled/colliding value is just another candidate index:
    bounds, current atom and normal-data flags must all pass before use.
    """
    abi = current_abi()
    fields = abi["offsets"]
    assert abi["bits"]["JSShapeProperty.flags"] == [[3, 4]]
    properties = (
        [f"lea r11, [r10+{fields['JSShape.prop']}]"]
        if abi["reference_count_model"] == "inline-header"
        else [
            f"mov eax, DWORD PTR [r10+{fields['JSShape.prop_hash_mask']}]",
            f"lea r11, [r10+rax*4+{fields['JSShape.hash_table'] + 4}]",
        ]
    )
    entry = [
        "cmp BYTE PTR [JS_FrameObjectProtoHintControl], 0",
        "je JS_FrameObjectProtoHintConfig",
        "cmp BYTE PTR [JS_FrameObjectProtoHintControl], 1",
        "jne JS_FrameObjectProtoLookup",
        "mov eax, r9d",
        "and eax, 15",
        "lea r11, JS_FrameObjectProtoHints",
        "mov ecx, DWORD PTR [r11+rax*4]",
        "test ecx, ecx",
        "jz JS_FrameObjectProtoLookup",
        "dec ecx",
        f"mov r10, QWORD PTR [r8+{fields['JSObject.shape']}]",
        f"cmp ecx, DWORD PTR [r10+{fields['JSShape.prop_count']}]",
        "jae JS_FrameObjectProtoLookup",
        *properties,
        "lea rax, [r11+rcx*8]",
        "cmp DWORD PTR [rax+4], r9d",
        "jne JS_FrameObjectProtoLookup",
        "test DWORD PTR [rax], 3221225472",
        "jnz JS_FrameObjectProtoLookup",
        "shl rcx, 4",
        f"mov r10, QWORD PTR [r8+{fields['JSObject.prop']}]",
        "add r10, rcx",
        "mov rax, QWORD PTR [r10]",
        "mov rdx, QWORD PTR [r10+8]",
        "test edx, edx",
        "jns objecthint_value_ready",
        f"inc DWORD PTR [rax{abi_constants(abi)['QJS_ABI_REF_COUNT_OFFSET']:+d}]",
        "objecthint_value_ready:",
    ]
    if diagnostics:
        entry += ["lock inc QWORD PTR [JS_FrameObjectProtoHintHits]"]
    entry += ["jmp JS_FrameObjectProtoFinish"]
    return [
        ("JS_FrameObjectProtoHintEntry", entry),
        (
            "JS_FrameObjectProtoHintFill",
            [
                "cmp BYTE PTR [JS_FrameObjectProtoHintControl], 1",
                "jne JS_FrameObjectProtoFinish",
                "shr ecx, 4",
                "inc ecx",
                "and r9d, 15",
                "lea r11, JS_FrameObjectProtoHints",
                "mov DWORD PTR [r11+r9*4], ecx",
                "jmp JS_FrameObjectProtoFinish",
            ],
        ),
        (
            "JS_FrameObjectProtoHintConfig",
            [
                "lea rcx, JS_FrameObjectProtoHintDisable",
                "call QWORD PTR [__imp_getenv]",
                "test rax, rax",
                "setne cl",
                "inc cl",
                "xor eax, eax",
                "lock cmpxchg BYTE PTR [JS_FrameObjectProtoHintControl], cl",
                "jmp JS_FrameObjectProtoEntry",
            ],
        ),
        (
            "JS_FrameObjectProtoHintState",
            ["movzx eax, BYTE PTR [JS_FrameObjectProtoHintControl]", "ret"],
        ),
        (
            "JS_FrameObjectProtoHintCount",
            (
                ["mov rax, QWORD PTR [JS_FrameObjectProtoHintHits]"]
                if diagnostics
                else ["xor eax, eax"]
            )
            + ["ret"],
        ),
    ]


def _numeric_invoke_module():
    from pathlib import Path
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "frame_numeric_invoke", _frame_tool_path("numeric-invoke")
    )
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result
