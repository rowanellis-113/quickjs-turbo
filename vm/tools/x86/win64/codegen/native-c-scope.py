"""One coherent host anchor per VM activation, shared by native C calls. MIT.

The canonical C entry borrows the original caller's Win64 incoming home32
without adding a C frame. It eagerly publishes the same kind3 barrier; a
native body publishes kind0 only after its SF/PC/SP/ownership ledger is ready.
No return-address rewriting, cached callee/realm, state growth or JS roots.
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
from native_abi import source_abi, current as current_abi
from pathlib import Path
import argparse
import datetime
import hashlib
import importlib.util
import json
import os
import re
import shutil
import struct
import subprocess
import time

HERE = Path(__file__).resolve().parent
CONTROL = "JS_FrameNativeCScopeControl"
COUNTERS = tuple(
    "JS_FrameNativeCScope" + s + "Hits"
    for s in ("Activation", "Generic", "Numeric", "Argc", "Wide")
)
RAW = "JS_FrameInterpUnscoped"
VM = "JS_FrameNativeCScopeVM"
MARKER = "qjs_native_c_scope_route_marker"
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, _frame_tool_path(filename))
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def route_gas(out):
    # GNU already separates its bounded missing-argument window. Its existing
    # cold fallback can enter arity checks directly; keep exact inherited R11.
    p = out / "quickjs-interpreter-c-invoke-win64.S"
    text = p.read_text(encoding="utf-8")
    for entry, host in (
        ("JS_FrameCInvokeEntry", "interp_host_call"),
        ("JS_FrameCInvokeDirtyEntry", "dirty_interp_host_call"),
    ):
        if entry + ":" in text:
            assert text.count(entry + ":\nlea r11, [rip+" + host + "]\n") == 1
        else:
            assert entry.endswith("DirtyEntry")
    before = "cargc_fallback:\njmp r11"
    assert text.count(before) == 1
    text = text.replace(before, "cargc_fallback:\njmp JS_FrameNativeCScopeArityGuard")
    p.write_text(text, encoding="utf-8")


def route_masm(lines):
    at = lines.index("JS_FrameCInvokeEntry PROC")
    assert lines[at + 1] == "lea r11, interp_host_call"
    assert "JS_FrameCInvokeDirtyEntry PROC" not in lines
    lines[at + 1] = "lea r11, JS_FrameNativeCScopeFallback"
    lines[:0] = ["EXTERN JS_FrameNativeCScopeFallback:PROC"]


def route_numeric(kernels):
    # The full compact numeric implementation remains available in this
    # research source, but ordinary numeric calls deliberately retain F.
    name, stream, kind = kernels[0]
    assert name == "JS_FrameNumericInvokeGuard"
    assert sum("JS_FrameNumericInvokeCommit" in line for line in stream) == 3
    assert not any("JS_FrameNativeCScope" in line for line in stream)


def check_scope(fallback):
    # The canonical entry always owns this home space. Off rejects before
    # reading it; state/kind checks enforce the private activation contract.
    return [
        f"cmp BYTE PTR [rip+{CONTROL}], 1",
        "jne " + fallback,
        "lea r9, [rsp+144]",
        "cmp QWORD PTR [r9+8], rbx",
        "jne " + fallback,
        "cmp DWORD PTR [r9+16], 3",
        "jne " + fallback,
    ]


def publish(anchor, sf):
    fields = current_abi()["offsets"]
    return [
        f"lea r9, {anchor}",
        f"mov al, BYTE PTR [r10+{fields['JSRuntime.current_stack_frame'] - 5}]",
        "and al, 4",
        "mov BYTE PTR [r9+20], al",
        f"lea rax, {sf}",
        f"mov QWORD PTR [r10+{fields['JSRuntime.current_stack_frame']}], rax",
        f"or BYTE PTR [r10+{fields['JSRuntime.current_stack_frame'] - 5}], 4",
        "mov DWORD PTR [r9+16], 0",
    ]


def restore(anchor, sf):
    fields = current_abi()["offsets"]
    return [
        "mov r10, QWORD PTR [rbx+56]",
        f"lea r9, {anchor}",
        "mov DWORD PTR [r9+16], 3",
        f"mov al, BYTE PTR [r10+{fields['JSRuntime.current_stack_frame'] - 5}]",
        "and al, 251",
        "or al, BYTE PTR [r9+20]",
        f"mov BYTE PTR [r10+{fields['JSRuntime.current_stack_frame'] - 5}], al",
        f"mov rax, QWORD PTR {sf}",
        f"mov QWORD PTR [r10+{fields['JSRuntime.current_stack_frame']}], rax",
    ]


def commit(old, suffix, body):
    return [
        s.replace("cinvoke_", "ncs_" + suffix.lower() + "_").replace("JS_FrameCInvokeBody", body)
        for s in old
    ]


def generic_body(old, diag, *, padded=False):
    fields = current_abi()["offsets"]
    suffix = "Argc" if padded else "Generic"
    name = "JS_FrameNativeCScope" + suffix
    size = 208 if padded else 160
    tls = next(i for i, s in enumerate(old) if s.startswith("mov rax, QWORD PTR gs:"))
    prefix = old[:tls]
    prefix.remove("mov DWORD PTR [rsp+156], ecx")
    offsets = {160: 128, 168: 136, 176: 144, 184: 152, 256: size + 48}

    def convert(s):
        s = re.sub(
            r"\[rsp\+(\d+)\]", lambda m: "[rsp+" + str(offsets.get(int(m[1]), int(m[1]))) + "]", s
        )
        return s.replace("cinvoke_", "ncs_" + suffix.lower() + "_")

    prefix = [convert(s).replace("sub rsp, 208", f"sub rsp, {size}") for s in prefix]
    if padded:
        prefix += [
            "mov DWORD PTR [rsp+192], ecx",
            f"movzx eax, BYTE PTR [rdx+{fields['JSObject.u.cfunc.length']}]",
            "cmp ecx, eax",
            "jae ncs_argc_args_ready",
            "mov QWORD PTR [rsp+160], 0",
            "mov QWORD PTR [rsp+168], 3",
            "mov QWORD PTR [rsp+176], 0",
            "mov QWORD PTR [rsp+184], 3",
            "test ecx, ecx",
            "jz ncs_argc_padded",
            "movdqu xmm2, XMMWORD PTR [r8]",
            "movdqa XMMWORD PTR [rsp+160], xmm2",
            "ncs_argc_padded:",
            "lea r8, [rsp+160]",
            "mov QWORD PTR [rsp+72], r8",
            "mov WORD PTR [rsp+106], ax",
            "mov QWORD PTR [rsp+32], r8",
            "ncs_argc_args_ready:",
        ]
    prefix += publish(f"[rsp+{size + 144}]", "[rsp+48]")
    start = old.index(f"mov r11, QWORD PTR [rdx+{fields['JSObject.u.cfunc.c_function']}]")
    stop = old.index("JS_FrameCInvokeCall:")
    setup = [convert(s) for s in old[start:stop]]
    setup = [
        s.replace(
            "mov r9d, DWORD PTR [rsp+156]",
            "mov r9d, DWORD PTR [rsp+192]" if padded else "movzx r9d, WORD PTR [rsp+106]",
        )
        for s in setup
    ]
    if diag:
        setup += ["lock inc QWORD PTR [rip+" + name + "Hits]"]
    tail = old[old.index("mov rax, QWORD PTR [rbx+32]", stop) :]
    tail = [
        convert(s)
        .replace("add rsp, 208", f"add rsp, {size}")
        .replace("je ncs_" + suffix.lower() + "_exception", "je " + name + "Exception")
        for s in tail
    ]
    body = prefix + setup + [name + "Call:", "call r11", name + "AfterCall:"]
    body += restore(f"[rsp+{size + 144}]", "[rsp+48]") + tail
    return [
        (name + "Body", body, ("alloc", size, "ncs_" + suffix.lower() + "_alloc")),
        (name + "Continue", ["jmp JS_FrameCInvokeContinue"], ("leaf",)),
        (
            name + "Exception",
            ["movdqu XMMWORD PTR [rbx+40], xmm0", f"add rsp, {size}"],
            ("out", size),
        ),
        (name + "ExceptionContinue", ["jmp JS_FrameCInvokeExceptionContinue"], ("leaf",)),
    ]


def numeric_body(old, diag):
    fields = current_abi()["offsets"]
    name = "JS_FrameNativeCScopeNumeric"
    tls = next(i for i, s in enumerate(old) if s.startswith("mov rax, QWORD PTR gs:"))
    prefix = [s.replace("sub rsp, 160", "sub rsp, 112") for s in old[:tls]]
    prefix += publish("[rsp+256]", "[rsp+32]") + [
        f"mov r11, QWORD PTR [rdx+{fields['JSObject.u.cfunc.c_function']}]"
    ]
    if diag:
        prefix += [
            "inc QWORD PTR [rbx+2264]",
            "inc QWORD PTR [rbx+2208]",
            "lock inc QWORD PTR [rip+JS_FrameNumericInvokeHits]",
            "lock inc QWORD PTR [rip+" + name + "Hits]",
        ]
    after = old.index("JS_FrameNumericInvokeAfterCall:")
    stop = old.index("mov r10, QWORD PTR [rbx+56]", after)
    boxing = old[after + 1 : stop]
    tail = old[old.index("mov rax, QWORD PTR [rbx+32]", stop) :]
    body = prefix + [name + "Call:", "call r11", name + "AfterCall:"] + boxing
    body += restore("[rsp+256]", "[rsp+32]") + tail
    body = [
        s.replace("ninvoke_", "ncs_numeric_").replace("add rsp, 160", "add rsp, 112") for s in body
    ]
    return [
        (name + "Body", body, ("alloc", 112, "ncs_numeric_alloc")),
        (name + "Continue", ["jmp JS_FrameCInvokeContinue"], ("leaf",)),
    ]


def refresh(diag, prefix):
    fields = current_abi()["offsets"]
    committed, shared, native = (2304, 2320, 2312) if diag else (64, 80, 72)
    return [
        "mov rax, QWORD PTR [rbx+32]",
        f"mov rdx, QWORD PTR [r10+{fields['JSRuntime.stack_limit']}]",
        f"cmp rax, QWORD PTR [rbx+{committed}]",
        "jne " + prefix + "_refresh",
        f"cmp rdx, QWORD PTR [rbx+{shared}]",
        "je " + prefix + "_refreshed",
        prefix + "_refresh:",
        f"mov QWORD PTR [rbx+{committed}], rax",
        f"mov QWORD PTR [rbx+{shared}], rdx",
        "test rdx, rdx",
        "jz " + prefix + "_limit",
        "sub rdx, rax",
        prefix + "_limit:",
        f"mov QWORD PTR [rbx+{native}], rdx",
        prefix + "_refreshed:",
    ]


def wide_body(diag):
    fields = current_abi()["offsets"]
    name = "JS_FrameNativeCScopeWide"
    # Private CALL thunk: fixed128 (SF80, actual4, receiver16, result16),
    # plus dynamic shadow/argv48+formal*16. RBP=base+80 recovers RSP in unwind.
    # VM->native-C low water = VM_RSP-(200+formal*16), inside old +256 guard.
    body = [
        "push rbp",
        "ncs_wide_push:",
        "sub rsp, 128",
        "ncs_wide_alloc:",
        "lea rbp, [rsp+80]",
        "ncs_wide_frame:",
        f"mov rax, QWORD PTR [r10+{fields['JSRuntime.current_stack_frame']}]",
        "mov QWORD PTR [rbp-80], rax",
        "movdqu xmm2, XMMWORD PTR [r8-16]",
        "movdqu XMMWORD PTR [rbp-72], xmm2",
        "mov DWORD PTR [rbp], ecx",
        "mov WORD PTR [rbp-20], 0",
        f"movzx eax, BYTE PTR [rdx+{fields['JSObject.u.cfunc.length']}]",
        "mov WORD PTR [rbp-22], ax",
        "cmp DWORD PTR [rbp+112], 0",
        "je ncs_wide_undefined",
        "movdqu xmm2, XMMWORD PTR [r8-32]",
        "movdqa XMMWORD PTR [rbp+16], xmm2",
        "jmp ncs_wide_this_ready",
        "ncs_wide_undefined:",
        "mov QWORD PTR [rbp+16], 0",
        "mov QWORD PTR [rbp+24], 3",
        "ncs_wide_this_ready:",
        "shl eax, 4",
        "add eax, 48",
        "cmp eax, 4096",
        "jbe ncs_wide_probe_end",
        "test BYTE PTR [rsp-4096], 0",
        "ncs_wide_probe_end:",
        "sub rsp, rax",
        "test BYTE PTR [rsp], 0",
        "lea r9, [rsp+48]",
        "mov QWORD PTR [rbp-56], r9",
        "mov QWORD PTR [rsp+32], r9",
        "test ecx, ecx",
        "jz ncs_wide_missing",
        "ncs_wide_copy:",
        "movdqu xmm2, XMMWORD PTR [r8]",
        "movdqa XMMWORD PTR [r9], xmm2",
        "add r8, 16",
        "add r9, 16",
        "dec ecx",
        "jnz ncs_wide_copy",
        "ncs_wide_missing:",
        "movzx ecx, WORD PTR [rbp-22]",
        "sub ecx, DWORD PTR [rbp]",
        "ncs_wide_fill:",
        "mov QWORD PTR [r9], 0",
        "mov QWORD PTR [r9+8], 3",
        "add r9, 16",
        "dec ecx",
        "jnz ncs_wide_fill",
    ]
    body += publish("[rbp+208]", "[rbp-80]")
    body += [
        "mov rdx, QWORD PTR [rbp-72]",
        f"movsx eax, WORD PTR [rdx+{fields['JSObject.u.cfunc.magic']}]",
        "mov DWORD PTR [rsp+40], eax",
        f"mov r11, QWORD PTR [rdx+{fields['JSObject.u.cfunc.c_function']}]",
    ]
    if diag:
        body += [
            "inc QWORD PTR [rbx+2264]",
            "inc QWORD PTR [rbx+2208]",
            f"cmp BYTE PTR [rdx+{fields['JSObject.u.cfunc.cproto']}], 0",
            "jne ncs_wide_magic_count",
            "inc QWORD PTR [rbx+2392]",
            "jmp ncs_wide_counted",
            "ncs_wide_magic_count:",
            "inc QWORD PTR [rbx+2400]",
            "ncs_wide_counted:",
            "lock inc QWORD PTR [rip+" + name + "Hits]",
        ]
    body += [
        f"mov rdx, QWORD PTR [rdx+{fields['JSObject.u.cfunc.realm']}]",
        "lea rcx, [rbp+32]",
        "lea r8, [rbp+16]",
        "mov r9d, DWORD PTR [rbp]",
        name + "Call:",
        "call r11",
        name + "AfterCall:",
    ]
    body += restore("[rbp+208]", "[rbp-80]") + refresh(diag, "ncs_wide")
    body += [
        "movdqu xmm0, XMMWORD PTR [rbp+32]",
        "cmp QWORD PTR [rbp+40], 6",
        f"sete BYTE PTR [rbx+{2296 if diag else 160}]",
        "lea rsp, [rbp+48]",
        "pop rbp",
        "ret",
    ]
    bridge = [
        "call " + name + "Body",
        f"cmp BYTE PTR [rbx+{2296 if diag else 160}], 0",
        "jne " + name + "Exception",
        "jmp JS_FrameCInvokeContinue",
    ]
    return [
        (name + "Bridge", bridge, ("leaf",)),
        (
            name + "Exception",
            ["movdqu XMMWORD PTR [rbx+40], xmm0", "jmp JS_FrameCInvokeExceptionContinue"],
            ("leaf",),
        ),
        (name + "Body", body, ("wide",)),
    ]


def kernels(diag, msvc, c_invoke, numeric):
    fields = current_abi()["offsets"]
    old = c_invoke._vm_kernel(diag, not msvc)
    result = []
    # Win64 C callers reserve home32 at entry RSP+8. The private anchor is
    # prev/state/kind/saved-active/TLS-slot at +0/+8/+16/+20/+24. Raw VM's
    # eight pushes plus alloc72 put exactly the SAME anchor at raw RSP+144.
    # Preserve eager kind3: lazy TLS would expose a parent native kind0 to a
    # child VM's JS dispatch before that child makes its first native call.
    wrapper = [
        f"cmp BYTE PTR [rip+{CONTROL}], 0",
        "je JS_FrameNativeCScopeConfig",
        f"cmp BYTE PTR [rip+{CONTROL}], 1",
        "jne ncs_vm_off",
        "mov QWORD PTR [rsp+16], rcx",
        "mov rax, QWORD PTR gs:88",
        "mov ecx, DWORD PTR [rip+_tls_index]",
        "mov rax, QWORD PTR [rax+rcx*8]",
    ]
    if msvc:
        wrapper += ["mov ecx, SECTIONREL js_frame_shared_top", "add rax, rcx"]
    else:
        wrapper += [
            "lea rcx, [rip+JS_FrameSharedTop]",
            "lea r9, [rip+_tls_start]",
            "sub rcx, r9",
            "add rax, rcx",
        ]
    wrapper += [
        "mov QWORD PTR [rsp+32], rax",
        "mov r10, QWORD PTR [rax]",
        "mov QWORD PTR [rsp+8], r10",
        "mov DWORD PTR [rsp+24], 3",
        "lea r10, [rsp+8]",
        "mov QWORD PTR [rax], r10",
        "mov rcx, QWORD PTR [rsp+16]",
    ]
    if diag:
        wrapper += ["lock inc QWORD PTR [rip+" + COUNTERS[0] + "]"]
    wrapper += ["jmp " + RAW, "ncs_vm_off:", "mov QWORD PTR [rsp+32], 0", "jmp " + RAW]
    result.append((VM, wrapper, ("entry",)))
    # The first getenv call is cold and returns to the original C stack
    # BEFORE raw VM entry. Split at the restored-RSP boundary: direct E9 is
    # not a standard Win64 epilogue terminator, so its PC needs zero-alloc CFI.
    config = [
        "sub rsp, 72",
        "ncs_config_alloc:",
        "mov QWORD PTR [rsp+32], rcx",
        "lea rcx, [rip+JS_FrameNativeCScopeDisable]",
        "call QWORD PTR [rip+__imp_getenv]",
        "test rax, rax",
        "setne cl",
        "inc cl",
        "xor eax, eax",
        f"lock cmpxchg BYTE PTR [rip+{CONTROL}], cl",
        "mov rcx, QWORD PTR [rsp+32]",
        "add rsp, 72",
    ]
    result.append(("JS_FrameNativeCScopeConfig", config, ("config",)))
    result.append(("JS_FrameNativeCScopeConfigContinue", ["jmp " + VM], ("entry",)))
    # Raw VM has already restored its original entry SP and all NV saves.
    # Incoming home32 is still this activation's property until the real RET.
    # The helper has a standard original-C zero-allocation unwind record.
    leave = [
        "mov r10, QWORD PTR [rsp+32]",
        "test r10, r10",
        "jz ncs_leave_done",
        "mov r11, QWORD PTR [rsp+8]",
        "mov QWORD PTR [r10], r11",
        "ncs_leave_done:",
        "ret",
    ]
    result.append(("JS_FrameNativeCScopeLeave", leave, ("entry",)))
    if msvc:
        result.append(
            (
                "JS_FrameNativeCScopeZeroGuard",
                [
                    f"cmp BYTE PTR [rip+{CONTROL}], 1",
                    "jne JS_FrameDensePopLeafEntry",
                    "lea rax, [rip+JS_FrameDenseArrayPop]",
                    f"cmp QWORD PTR [rdx+{fields['JSObject.u.cfunc.c_function']}], rax",
                    "je JS_FrameDensePopLeafEntry",
                    "jmp JS_FrameNativeCScopeArityGuard",
                ],
                ("leaf",),
            )
        )
    for suffix, inherited in (
        ("Generic", "JS_FrameCInvokeCommit"),
        ("Numeric", "JS_FrameNumericInvokeCommit"),
        ("Argc", "JS_FrameCArgcCommit"),
    ):
        if suffix == "Argc" and msvc:
            continue
        guard = check_scope(inherited) + ["jmp JS_FrameNativeCScope" + suffix + "Commit"]
        result.append(("JS_FrameNativeCScope" + suffix + "Guard", guard, ("leaf",)))
    # GNU bounded arity/builtin controls keep their precedence. This new guard
    # handles wide missing arities there; MS additionally gets zero/small missing.
    guard = [
        "cmp ecx, 65535",
        "ja ncs_arity_fallback",
        f"movzx eax, BYTE PTR [rdx+{fields['JSObject.u.cfunc.length']}]",
        "cmp ecx, eax",
        "jae ncs_arity_fallback",
    ]
    if not msvc:
        guard += [
            "lea rax, [rip+qjs_frame_core_js_number_toString]",
            f"cmp QWORD PTR [rdx+{fields['JSObject.u.cfunc.c_function']}], rax",
            "je ncs_arity_fallback",
            "lea rax, [rip+qjs_frame_core_js_string_slice]",
            f"cmp QWORD PTR [rdx+{fields['JSObject.u.cfunc.c_function']}], rax",
            "je ncs_arity_fallback",
            f"cmp BYTE PTR [rdx+{fields['JSObject.u.cfunc.length']}], 2",
            "jbe ncs_arity_fallback",
        ]
    stream = old[3]
    skip = {
        "test ecx, ecx",
        "jz JS_FrameDensePopLeafEntry",
        f"movzx eax, BYTE PTR [rdx+{fields['JSObject.u.cfunc.length']}]",
        "cmp ecx, eax",
        "jl JS_FrameCArgcGuard",
        "jl cinvoke_fallback",
        "jmp JS_FrameCInvokeCommit",
        "cinvoke_fallback:",
        "jmp r11",
    }
    guard += [s.replace("cinvoke_fallback", "ncs_arity_fallback") for s in stream if s not in skip]
    guard += check_scope("ncs_arity_fallback")
    guard += [
        f"movzx eax, BYTE PTR [rdx+{fields['JSObject.u.cfunc.length']}]",
        "cmp ecx, eax",
        "jae JS_FrameNativeCScopeGenericCommit",
        "cmp eax, 2",
        "jbe JS_FrameNativeCScopeArgcCommit",
        "jmp JS_FrameNativeCScopeWideCommit",
        "ncs_arity_fallback:",
        "jmp r11",
    ]
    # MS restores the original R11 then falls straight into the arity
    # guard under the same leaf unwind entry. GNU arrives directly from
    # its old argc fallback with original clean/dirty R11 already live.
    if msvc:
        guard[:0] = ["JS_FrameNativeCScopeFallback:", "lea r11, [rip+interp_host_call]"]
    result.append(("JS_FrameNativeCScopeArityGuard", guard, ("leaf",)))
    for suffix, body in (
        ("Generic", "GenericBody"),
        ("Numeric", "NumericBody"),
        ("Argc", "ArgcBody"),
        ("Wide", "WideBridge"),
    ):
        result.append(
            (
                "JS_FrameNativeCScope" + suffix + "Commit",
                commit(old[5], suffix, "JS_FrameNativeCScope" + body),
                ("leaf",),
            )
        )
    result += generic_body(old[6], diag)
    numeric_old = next(
        stream
        for name, stream, _ in numeric.blocks(diag, msvc, c_invoke)
        if name == "JS_FrameNumericInvokeBody"
    )
    result += numeric_body(numeric_old, diag)
    result += generic_body(old[6], diag, padded=True)
    result += wide_body(diag)
    return result


def runtime_groups(streams):
    # Contiguous leaf entries all inherit the complete raw-VM stack and the
    # exact same chained unwind. Give their region one owner; keep EVERY
    # logical entry as an independent CFG/unwind test seed. This is metadata
    # ownership, not address/padding selection, and avoids another 4KiB page.
    groups = []
    for name, _, kind in streams:
        if kind[0] == "leaf" and groups and groups[-1]["kind"] == "leaf":
            groups[-1]["end"] = name + "_end"
            groups[-1]["members"].append(name)
        else:
            groups.append(
                dict(
                    begin=name,
                    end=name + "_end",
                    unwind=name + "_unwind",
                    kind=kind[0],
                    members=[name],
                )
            )
    return groups


@source_abi
def compile_backend(source, build, destination=None, *, msvc=False):
    C = module("native_c_scope_coff", "object-adapter.py")
    merge = module("native_c_scope_merge", "extension-merge.py")
    old = module("native_c_scope_old", "c-invoke.py")
    numeric = module("native_c_scope_numeric", "numeric-invoke.py")
    proof = json.loads(
        (
            _frame_generated_file(build, "quickjs-interpreter-dense-array-pop.compile.json")
        ).read_text()
    )
    diag = any("QJS_INTERP_FRAME_DIAGNOSTICS" in arg for arg in proof["compiler_command"])
    compiler = Path(proof["compiler_command"][0])
    streams = kernels(diag, msvc, old, numeric)
    owners = runtime_groups(streams)
    code = ".qjsncs$C" if msvc else ".qjssrf$NCS"
    pdata = ".pdata$zzzzzznullfast" if msvc else ".pdata$zzzzzznativescope"
    externals = [
        RAW,
        "interp_host_call",
        "JS_FrameInterp_end",
        "JS_FrameInterp_unwind",
        "JS_FrameCInvokeContinue",
        "JS_FrameCInvokeCommit",
        "JS_FrameCInvokeControl",
        "JS_FrameCInvokeConfig",
        "JS_FrameNumericInvokeCommit",
        "JS_FrameCInvokeExceptionContinue",
        "_tls_index",
        "__imp_getenv",
        CONTROL,
        *COUNTERS,
        "JS_FrameNumericInvokeHits",
    ]
    if not msvc:
        externals += [
            "JS_FrameCArgcCommit",
            "qjs_frame_core_js_number_toString",
            "qjs_frame_core_js_string_slice",
        ]
    else:
        externals += ["JS_FrameDenseArrayPop", "JS_FrameDensePopLeafEntry"]
    externals += ["js_frame_shared_top"] if msvc else ["JS_FrameSharedTop", "_tls_start"]
    if not msvc and not diag:
        externals += ["dirty_interp_host_call", "JS_FramePublishDirtyTable", "JS_FramePublishTable"]
    lines = (
        [
            "OPTION CASEMAP:NONE",
            "OPTION DOTNAME",
            *["EXTERN " + n + (":PROC" if n == RAW else ":BYTE") for n in externals],
            code + " SEGMENT ALIGN(16) 'CODE'",
        ]
        if msvc
        else [".intel_syntax noprefix", ".section " + code + ',"xr"']
    )
    for name, stream, kind in streams:
        if msvc and name == VM:
            lines += ["PUBLIC JS_FrameInterp", "JS_FrameInterp LABEL NEAR"]
        if not name.endswith("Continue"):
            lines += ["ALIGN 16"] if msvc else [".p2align 4"]
        lines += (
            ["PUBLIC " + name + ", " + name + "_end", name + " PROC"]
            if msvc
            else [
                ".globl " + name + ", " + name + "_end",
                ".def " + name + "; .scl 2; .type 32; .endef",
                name + ":",
            ]
        )
        for s in stream:
            if msvc:
                s = (
                    s.replace("rip+", "")
                    .replace("gs:88", "gs:[88]")
                    .replace("0xc1e0000000000000", "0c1e0000000000000h")
                )
                if s.endswith(":"):
                    lines += ["PUBLIC " + s[:-1], s[:-1] + "::"]
                    continue
                s = re.sub(r"^(j\w+) (\w+)$", r"\1 NEAR PTR \2", s)
            elif s.endswith(":"):
                lines += [".globl " + s[:-1]]
            lines.append(s)
        lines += [name + "_end LABEL BYTE", name + " ENDP"] if msvc else [name + "_end:"]
    lines += ["ALIGN 4"] if msvc else [".p2align 2"]

    def data(values):
        for width, value in values:
            lines.append(
                (
                    {"b": "DB ", "w": "DW ", "r": "DD IMAGEREL "}
                    if msvc
                    else {"b": ".byte ", "w": ".short ", "r": ".rva "}
                )[width]
                + value
            )

    for name, _, kind in streams:
        uw = name + "_unwind"
        lines += [uw + " LABEL BYTE"] if msvc else [uw + ":"]
        mode = kind[0]
        if mode == "entry":
            data([("b", "1,0,0,0")])
        elif mode == "config":
            data(
                [
                    ("b", "1,ncs_config_alloc-" + name + ",1,0"),
                    ("b", "ncs_config_alloc-" + name + ",130"),
                    ("w", "0"),
                ]
            )
        elif mode == "wrapper":
            data(
                [
                    ("b", "1,ncs_vm_alloc-" + VM + ",1,0"),
                    ("b", "ncs_vm_alloc-" + VM + "," + str(0x82)),
                    ("w", "0"),
                ]
            )
        elif mode == "wide":
            data(
                [
                    ("b", "1,ncs_wide_frame-" + name + ",3,85"),
                    ("b", "ncs_wide_frame-" + name + ",3"),
                    ("b", "ncs_wide_alloc-" + name + ",242"),
                    ("b", "ncs_wide_push-" + name + ",80"),
                    ("w", "0"),
                ]
            )
        else:
            if mode == "leaf":
                data([("b", "33,0,0,0")])
            elif mode == "out":
                data([("b", "33,0,2,0"), ("b", "0,1"), ("w", str(kind[1] // 8))])
            else:
                _, size, label = kind
                if size <= 128:
                    data(
                        [
                            ("b", "33," + label + "-" + name + ",1,0"),
                            ("b", label + "-" + name + "," + str(((size - 8) // 8) * 16 + 2)),
                            ("w", "0"),
                        ]
                    )
                else:
                    data(
                        [
                            ("b", "33," + label + "-" + name + ",2,0"),
                            ("b", label + "-" + name + ",1"),
                            ("w", str(size // 8)),
                        ]
                    )
            data([("r", RAW), ("r", "JS_FrameInterp_end"), ("r", "JS_FrameInterp_unwind")])
    if not msvc:
        lines += [
            ".globl JS_FrameNativeCScopeEntryUnwind",
            "JS_FrameNativeCScopeEntryUnwind:",
            ".byte 1,0,0,0",
        ]
    lines += (
        [
            "JS_FrameNativeCScopeDisable LABEL BYTE",
            'DB "QJS_DISABLE_NATIVE_C_SCOPE",0',
            "ALIGN 8",
            "PUBLIC JS_FrameNativeCScopeReturnTarget",
            "JS_FrameNativeCScopeReturnTarget LABEL QWORD",
            "DQ JS_FrameNativeCScopeLeave",
            code + " ENDS",
            pdata + " SEGMENT ALIGN(4) READONLY 'DATA'",
        ]
        if msvc
        else [
            "JS_FrameNativeCScopeDisable:",
            '.asciz "QJS_DISABLE_NATIVE_C_SCOPE"',
            # Keep absolute pointers out of the late expression-sized
            # unwind/code reservation: its final field RVA and GNU PE
            # base-relocation RVA differed by8KiB in the rejected build.
            # Standard readonly data gets normal linker relocation.
            '.section .rdata$zzqjscsret,"dr"',
            ".p2align 3",
            ".globl JS_FrameNativeCScopeReturnTarget",
            "JS_FrameNativeCScopeReturnTarget:",
            ".quad JS_FrameNativeCScopeLeave",
            '.section .pdata$zzzzzznativescope,"dr"',
            ".p2align 2",
        ]
    )
    for owner in owners:
        data([("r", owner["begin"]), ("r", owner["end"]), ("r", owner["unwind"])])
    if msvc:
        lines += [pdata + " ENDS", "END"]
    asm = _frame_build_file(
        build,
        "quickjs-interpreter-native-c-scope.asm"
        if msvc
        else "quickjs-interpreter-native-c-scope.S",
    )
    obj = _frame_build_file(
        build,
        "native-c-scope/implementation.obj" if msvc else "quickjs-interpreter-native-c-scope.obj",
    )
    obj.parent.mkdir(parents=True, exist_ok=True)
    asm.write_text("\n".join(lines) + "\n", encoding="ascii")
    cmd = (
        [str(compiler.with_name("ml64.exe")), "/nologo", "/c", "/Fo" + str(obj), str(asm)]
        if msvc
        else [str(compiler), "-c", "-g0", str(asm), "-o", str(obj)]
    )
    process = subprocess.run(cmd, capture_output=True)
    asm.with_suffix(".log").write_bytes(process.stdout + process.stderr)
    assert process.returncode == 0, (
        cmd,
        (process.stdout + process.stderr).decode(errors="replace"),
    )
    coff = C.Coff(obj.read_bytes())
    corrections = []
    for number, rec in enumerate(coff.section_records, 1):
        for i in range(rec["count"]):
            pos = rec["reloc"] + 10 * i
            off, sym, kind = struct.unpack_from("<IIH", coff.data, pos)
            if 5 <= kind <= 9:
                assert msvc
                at = rec["raw"] + off
                value = struct.unpack_from("<i", coff.data, at)[0]
                struct.pack_into("<i", coff.data, at, value - (kind - 4))
                struct.pack_into("<H", coff.data, pos + 8, 4)
                corrections.append({"offset": off, "kind": kind})
        if merge.section_name(coff, number) == code or (
            msvc and merge.section_name(coff, number) == pdata
        ):
            struct.pack_into("<I", coff.data, rec["pos"] + 36, (rec["flags"] & ~0xE0) | 0x60000040)
    obj.write_bytes(coff.finish())
    record = dict(
        status="passed",
        generator_sha256=sha(__file__),
        diagnostics=diag,
        msvc=msvc,
        asm=str(asm),
        asm_sha256=sha(asm),
        object=str(obj),
        object_sha256=sha(obj),
        standalone_library_member=not msvc,
        blocks=[n for n, _, _ in streams],
        rel32_corrections=corrections,
        control="QJS_DISABLE_NATIVE_C_SCOPE",
        native_stack_bytes={
            "numeric": 112,
            "generic": 160,
            "small_padding": 208,
            "wide_fixed": 128,
            "wide_outgoing": "48+formal*16",
            "activation": 0,
            "borrowed_incoming_home": 32,
            "cold_first_config": 72,
        },
        public_SF_bytes=80,
        state_growth=0,
        public_ABI_changes=0,
        route_required=True,
        no_return_address_rewrite=True,
        cold_entry_aliases=["JS_FrameNativeCScopeFallback"] if msvc else [],
        cold_entry_unwind_owner=next(
            g["begin"] for g in owners if "JS_FrameNativeCScopeArityGuard" in g["members"]
        ),
        runtime_owners=owners,
        all_logical_entries=[n for n, _, _ in streams],
        raw_exit_hook="JS_FrameNativeCScopeRawEpilog",
        raw_exit_terminator="RIP-memory JMP; ModRM mod00; original NV/SP restored",
        raw_return_target="JS_FrameNativeCScopeReturnTarget",
        cleanup_incoming_stack="original-C",
        raw_stack_displacement_vs_F=0,
        eager_blocked_kind3=True,
    )
    entry = None if msvc else compile_entry(source, build, compiler, msvc=False)
    record.update(
        entry_object=str(entry) if entry else None,
        entry_object_sha256=sha(entry) if entry else None,
        pdata_output=pdata,
        canonical_entry=VM if msvc else "JS_FrameNativeCScopeEntry",
    )
    (_frame_generated_file(build, "quickjs-native-c-scope-generation.json")).write_text(
        json.dumps(record, indent=2) + "\n", encoding="utf-8"
    )


def compile_entry(source, build, compiler, *, msvc):
    """Real C-ABI tail entry, owned by the existing register archive member."""
    C = module("native_scope_entry_coff", "object-adapter.py")
    merge = module("native_scope_entry_names", "extension-merge.py")
    code = ".qjsnce$C"
    names = ("JS_FrameInterp", "JS_FrameNativeCScopeEntry", "JS_FrameNativeCScopeEntry_end")
    if msvc:
        lines = [
            "OPTION CASEMAP:NONE",
            "OPTION DOTNAME",
            "EXTERN JS_FrameNativeCScopeVM:PROC",
            "EXTERN JS_FrameNativeCScopeEntryUnwind:BYTE",
            code + " SEGMENT ALIGN(16) 'CODE'",
            "PUBLIC " + ", ".join(names),
            "JS_FrameInterp LABEL NEAR",
            "JS_FrameNativeCScopeEntry PROC",
            "jmp NEAR PTR JS_FrameNativeCScopeVM",
            "JS_FrameNativeCScopeEntry_end LABEL BYTE",
            "JS_FrameNativeCScopeEntry ENDP",
            code + " ENDS",
            ".pdata$zzzzzznullfast SEGMENT ALIGN(4) READONLY 'DATA'",
            "DD IMAGEREL JS_FrameNativeCScopeEntry, IMAGEREL JS_FrameNativeCScopeEntry_end, IMAGEREL JS_FrameNativeCScopeEntryUnwind",
            ".pdata$zzzzzznullfast ENDS",
            "END",
        ]
    else:
        lines = [
            ".intel_syntax noprefix",
            ".section " + code + ',"xr"',
            ".globl " + ", ".join(names),
            ".def JS_FrameInterp; .scl 2; .type 32; .endef",
            ".def JS_FrameNativeCScopeEntry; .scl 2; .type 32; .endef",
            "JS_FrameInterp:",
            "JS_FrameNativeCScopeEntry:",
            "jmp JS_FrameNativeCScopeVM",
            "JS_FrameNativeCScopeEntry_end:",
            '.section .pdata$zzzzzznullfast,"dr"',
            ".rva JS_FrameNativeCScopeEntry, JS_FrameNativeCScopeEntry_end, JS_FrameNativeCScopeEntryUnwind",
        ]
    auxiliary = _frame_generated_file(build, "native-scope-entry")
    auxiliary.mkdir(exist_ok=True)
    asm = auxiliary / ("entry.asm" if msvc else "entry.S")
    obj = auxiliary / "entry.obj"
    asm.write_text("\n".join(lines) + "\n", encoding="ascii")
    cmd = (
        [str(compiler.with_name("ml64.exe")), "/nologo", "/c", "/Fo" + str(obj), str(asm)]
        if msvc
        else [str(compiler), "-c", "-g0", str(asm), "-o", str(obj)]
    )
    p = subprocess.run(cmd, capture_output=True)
    asm.with_suffix(".log").write_bytes(p.stdout + p.stderr)
    assert p.returncode == 0, (cmd, p.stdout, p.stderr)
    coff = C.Coff(obj.read_bytes())
    for number, rec in enumerate(coff.section_records, 1):
        if merge.section_name(coff, number) == code or (
            msvc and merge.section_name(coff, number).startswith(".pdata")
        ):
            struct.pack_into("<I", coff.data, rec["pos"] + 36, (rec["flags"] & ~0xE0) | 0x60000040)
    obj.write_bytes(coff.finish())
    return obj


def objects(build):
    text = (_frame_build_file(build, "build.ninja")).read_text(encoding="utf-8")
    lines = re.findall(r"^build (?:qjs\.lib|libqjs\.a): (.+)$", text, re.M)
    assert len(lines) == 1
    values = lines[0].split(" ||")[0].split(" |")[0].split()[1:]
    assert values and all(s.endswith(".obj") for s in values)
    paths = [_frame_build_file(build, s) for s in values]
    assert all(p.is_file() and p.resolve().is_relative_to(build.resolve()) for p in paths)
    return paths


def merge_msvc_owned_scope(raw, source, build, generation):
    """Keep scope code and native rows in the original late cold archive owner.

    The strict common merger stays unchanged. A private copy first moves the
    allocated post-string directive tail ahead of the symbol table. After
    appending native rows then code, exchange only the source-footer/native
    section identities: old rows, new rows, complete footer, then new code.
    No new allocated output subsection name is introduced.
    """
    C = module("native_scope_carrier_coff", "object-adapter.py")
    M = module("native_scope_carrier_merge", "extension-merge.py")
    original = C.Coff(raw)
    assert original.header == 20 and original.stride == 18
    end = original.string_offset + len(original.strings)
    assert end <= len(raw)
    tail = raw[end:]
    packed = bytearray(raw[: original.table] + tail + raw[original.table : end])
    struct.pack_into("<I", packed, 8, original.table + len(tail))
    moved = []
    for number, rec in enumerate(original.section_records, 1):
        for field in (20, 24, 28):
            value = struct.unpack_from("<I", raw, rec["pos"] + field)[0]
            if not value:
                continue
            span = (
                rec["size"]
                if field == 20
                else struct.unpack_from("<H", raw, rec["pos"] + (32 if field == 24 else 34))[0]
                * (10 if field == 24 else 6)
            )
            if not span and value == original.table:
                continue  # Exact unused end marker; no allocated bytes or relocations.
            assert value < original.table or end <= value < len(raw), (number, field, value)
            if value >= end:
                new = original.table + value - end
                struct.pack_into("<I", packed, rec["pos"] + field, new)
                moved.append(dict(section=number, field=field, old=value, new=new))
    packed = bytes(packed)
    before = C.Coff(packed)
    assert before.sections == original.sections
    assert before.all_symbols == original.all_symbols
    assert before.string_offset + len(before.strings) == len(packed)
    footers = [
        i
        for i, rec in enumerate(before.section_records, 1)
        if packed[rec["raw"] : rec["raw"] + rec["size"]].startswith(b"QJSCW_END_v1!!!!")
    ]
    assert footers == [before.count], footers
    footer = footers[0]
    footer_group = M.section_name(before, footer)
    assert footer_group == ".qjs$zzzzzzzzzzrvV"
    assert before.section_records[footer - 1]["flags"] == 0x60300040
    assert not any(s["section"] == footer and s["type"] & 32 for s in before.all_symbols.values())
    footer_references = []
    for number, rec in enumerate(before.section_records, 1):
        for i in range(rec["count"]):
            off, index, kind = struct.unpack_from("<IIH", packed, rec["reloc"] + 10 * i)
            if before.all_symbols[index]["section"] == footer:
                footer_references.append(dict(section=number, offset=off, kind=kind, symbol=index))
    assert not footer_references, "A retained operand must not depend on the relocated footer"

    implementation = Path(generation["object"])
    incoming = C.Coff(implementation.read_bytes())
    native = [
        i
        for i in range(1, incoming.count + 1)
        if M.section_name(incoming, i) == ".pdata$zzzzzznullfast"
    ]
    code = [i for i in range(1, incoming.count + 1) if M.section_name(incoming, i) == ".qjsncs$C"]
    assert len(native) == len(code) == 1
    assert incoming.section_records[native[0] - 1]["flags"] == 0x60300040
    scratch = _frame_generated_file(build, "native-scope-link") / str(time.time_ns())
    scratch.mkdir(parents=True, exist_ok=False)
    target = scratch / "late-cold-with-scope.obj"
    target.write_bytes(packed)
    # The common merger remains byte-for-byte unchanged and accepts no
    # ADDR64. Stage ONLY this named zero-addend 8-byte pointer as ADDR32NB,
    # retain the strict merge artifact, then promote the exact copied field
    # back to ADDR64 in this private carrier before linking. No other kind,
    # symbol, addend, section or source byte is changed by this adaptation.
    slots = [
        s
        for s in incoming.all_symbols.values()
        if s["name"] == "JS_FrameNativeCScopeReturnTarget" and s["section"] > 0
    ]
    assert len(slots) == 1 and slots[0]["section"] == code[0]
    slot = slots[0]
    sr = incoming.section_records[slot["section"] - 1]
    assert (
        not sr["flags"] & 0x80000000 and slot["value"] % 8 == 0 and slot["value"] + 8 <= sr["size"]
    )
    assert bytes(incoming.data[sr["raw"] + slot["value"] : sr["raw"] + slot["value"] + 8]) == bytes(
        8
    )
    fixups = []
    for i in range(sr["count"]):
        at, index, kind = struct.unpack_from("<IIH", incoming.data, sr["reloc"] + 10 * i)
        if kind == 1:
            symbol = incoming.all_symbols[index]
            assert at == slot["value"] and symbol["name"] == "JS_FrameNativeCScopeLeave"
            assert symbol["section"] == code[0] and symbol["type"] & 32 and symbol["storage"] == 2
            fixups.append(sr["reloc"] + 10 * i)
    assert len(fixups) == 1
    original_implementation = implementation
    staged = bytearray(implementation.read_bytes())
    struct.pack_into("<H", staged, fixups[0] + 8, 3)
    implementation = scratch / "named-return-pointer-rva-stage.obj"
    implementation.write_bytes(staged)
    assert C.Coff(bytes(staged)).all_symbols == incoming.all_symbols
    M.append(
        target,
        implementation,
        VM,
        "native-scope-owned",
        keep_all=True,
        code_input=".qjsncs$C",
        code_output=footer_group,
        pdata_output=footer_group,
        baseline_sections=(footer_group,),
        section_order=[native[0], code[0]],
    )
    strict_bytes = target.read_bytes()
    merged = C.Coff(strict_bytes)
    copied = [
        s
        for s in merged.all_symbols.values()
        if s["name"] == "JS_FrameNativeCScopeReturnTarget" and s["section"] > 0
    ]
    assert len(copied) == 1 and copied[0]["section"] == before.count + 2
    cp = copied[0]
    cr = merged.section_records[cp["section"] - 1]
    promotions = []
    assert bytes(merged.data[cr["raw"] + cp["value"] : cr["raw"] + cp["value"] + 8]) == bytes(8)
    merged_bytes = bytearray(strict_bytes)
    for i in range(cr["count"]):
        at, index, kind = struct.unpack_from("<IIH", strict_bytes, cr["reloc"] + 10 * i)
        if at == cp["value"]:
            symbol = merged.all_symbols[index]
            assert (
                kind == 3
                and symbol["name"] == "JS_FrameNativeCScopeLeave"
                and symbol["section"] == cp["section"]
            )
            struct.pack_into("<H", merged_bytes, cr["reloc"] + 10 * i + 8, 1)
            promotions.append(
                dict(
                    section=cp["section"],
                    offset=at,
                    symbol=symbol["name"],
                    from_kind=3,
                    to_kind=1,
                    width=8,
                )
            )
    assert len(promotions) == 1
    pointer_promotion = dict(
        source=str(original_implementation),
        source_sha256=sha(original_implementation),
        surrogate=str(implementation),
        surrogate_sha256=sha(implementation),
        strict_output_sha256=hashlib.sha256(strict_bytes).hexdigest(),
        promotions=promotions,
        promoted_sha256=hashlib.sha256(merged_bytes).hexdigest(),
        pointer_bytes_unchanged=True,
        common_merger_unchanged=True,
    )
    merged_bytes = bytes(merged_bytes)
    merged = C.Coff(merged_bytes)
    new_native, new_code = before.count + 1, before.count + 2
    assert merged.count == before.count + 2
    assert M.section_name(merged, new_native) == M.section_name(merged, new_code) == footer_group
    new_native_record = dict(merged.section_records[new_native - 1])
    owners = generation["runtime_owners"]
    logical = generation["blocks"]
    covered = [name for owner in owners for name in owner["members"]]
    assert len(logical) == len(set(logical)) and sorted(covered) == sorted(logical)
    assert all(
        owner["begin"] == owner["members"][0] and owner["end"] == owner["members"][-1] + "_end"
        for owner in owners
    )
    assert new_native_record["size"] == len(owners) * 12
    assert new_native_record["count"] == len(owners) * 3
    assert new_native_record["flags"] == before.section_records[footer - 1]["flags"]

    result = bytearray(merged_bytes)
    left, right = (merged.section_records[i - 1]["pos"] for i in (footer, new_native))
    result[left : left + 40], result[right : right + 40] = (
        result[right : right + 40],
        result[left : left + 40],
    )
    swap = {footer: new_native, new_native: footer}
    symbol_changes, associations = [], []
    for index, symbol in merged.all_symbols.items():
        pos = merged.table + index * 18
        if symbol["section"] in swap:
            section = swap[symbol["section"]]
            struct.pack_into("<h", result, pos + 12, section)
            symbol_changes.append(
                dict(index=index, name=symbol["name"], old=symbol["section"], new=section)
            )
        aux = result[pos + 17]
        if aux and symbol["storage"] == 3 and symbol["type"] == 0 and symbol["section"] > 0:
            assert aux == 1
            association = struct.unpack_from("<h", result, pos + 18 + 12)[0]
            if association in swap:
                assert result[pos + 18 + 14] == 5
                struct.pack_into("<h", result, pos + 18 + 12, swap[association])
                associations.append(dict(index=index, old=association, new=swap[association]))
    result = bytes(result)
    after = C.Coff(result)
    for i in range(before.count):
        assert after.sections[new_native - 1 if i + 1 == footer else i] == before.sections[i], i + 1
    assert after.sections[footer - 1] == merged.sections[new_native - 1]
    assert after.sections[new_code - 1] == merged.sections[new_code - 1]
    for index, symbol in merged.all_symbols.items():
        expected = {**symbol, "section": swap.get(symbol["section"], symbol["section"])}
        assert after.all_symbols[index] == expected, index
    definitions = [
        s for s in after.all_symbols.values() if s["name"] == "JS_FrameInterp" and s["section"] > 0
    ]
    assert len(definitions) == 1
    vm = after.symbols[VM]
    assert (definitions[0]["section"], definitions[0]["value"]) == (vm["section"], vm["value"])
    assert vm["section"] == new_code
    report = scratch / "owned-carrier.json"
    report.write_text(
        json.dumps(
            dict(
                status="passed",
                generator_sha256=sha(__file__),
                input_sha256=hashlib.sha256(raw).hexdigest(),
                packed_sha256=hashlib.sha256(packed).hexdigest(),
                output_sha256=hashlib.sha256(result).hexdigest(),
                implementation=str(implementation),
                implementation_sha256=sha(implementation),
                named_return_pointer_promotion=pointer_promotion,
                strict_merge=str(target) + ".native-scope-owned-merge.json",
                post_string_tail_bytes=len(tail),
                rebased_tail_pointers=moved,
                source_footer_old_section=footer,
                source_footer_new_section=new_native,
                added_code_section=new_code,
                added_native_rows=len(owners),
                logical_native_entries=len(logical),
                runtime_owner_members=[g["members"] for g in owners],
                section_symbol_changes=symbol_changes,
                association_changes=associations,
                old_sections_except_footer_identical=True,
                entire_footer_payload_relocated=True,
                old_footer_operand_references=footer_references,
                all_old_symbol_indexes_retained=True,
                existing_input_group=footer_group,
                new_allocated_output_group_names=[],
                canonical_aliases_actual_scope_VM=True,
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return result, str(report)


@source_abi
def route_vm(source, build):
    C = module("native_c_scope_route_coff", "object-adapter.py")
    receipt = _frame_generated_file(build, "quickjs-native-c-scope-route.json")
    assert not receipt.exists()
    generation_path = _frame_generated_file(build, "quickjs-native-c-scope-generation.json")
    generation = json.loads(generation_path.read_text())
    msvc = generation["msvc"]
    assert generation["status"] == "passed" and generation["standalone_library_member"] == (
        not msvc
    )
    assert sha(generation["object"]) == generation["object_sha256"]
    if not msvc:
        assert sha(generation["entry_object"]) == generation["entry_object_sha256"]
    assert sha(__file__) == generation["generator_sha256"]
    rows, definitions, staged = [], [], []
    state = dict(
        status="preparing",
        generator_sha256=sha(__file__),
        records=rows,
        standalone_object=generation["object"],
        generation_sha256=sha(generation_path),
    )
    save = lambda: receipt.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    save()
    try:
        for path in objects(build):
            raw = path.read_bytes()
            coff = C.Coff(raw)
            assert not any(s["name"] == MARKER for s in coff.all_symbols.values()), str(path)
            original = {i: dict(s) for i, s in coff.all_symbols.items()}
            declared = [
                i for i, s in original.items() if s["name"] == "JS_FrameInterp" and s["section"] > 0
            ]
            wrapper = [s for s in original.values() if s["name"] == VM and s["section"] > 0]
            renamed = []
            for index in declared:
                target = original[index]
                if wrapper:
                    assert any(
                        (s["section"], s["value"]) == (target["section"], target["value"])
                        for s in wrapper
                    )
                    continue
                at = len(coff.strings)
                coff.strings += RAW.encode() + b"\0"
                struct.pack_into("<II", coff.data, coff.table + index * coff.stride, 0, at)
                coff.all_symbols[index]["name"] = RAW
                renamed.append(index)
                definitions.append(
                    dict(
                        path=str(path),
                        index=index,
                        section=target["section"],
                        value=target["value"],
                    )
                )
            wrapper_alias = None
            footer_symbols = []
            footer_sections = []
            externals = {}

            def external(name):
                if name not in externals:
                    found = [
                        i
                        for i, s in coff.all_symbols.items()
                        if s["name"] == name and s["section"] == 0 and s["storage"] == 2
                    ]
                    externals[name] = found[0] if found else coff.external(name)
                return externals[name]

            changes = []
            for number, rec in enumerate(coff.section_records, 1):
                for i in range(rec["count"]):
                    pos = rec["reloc"] + 10 * i
                    off, index, kind = struct.unpack_from("<IIH", raw, pos)
                    if original[index]["name"] != "JS_FrameInterp":
                        continue
                    instruction = raw[rec["raw"] + off - 1] if off else -1
                    executable = kind == 4 and instruction in (0xE8, 0xE9)
                    if executable:
                        target = external("JS_FrameInterp") if index in renamed else index
                        role = "call" if instruction == 0xE8 else "tail-jmp"
                    else:
                        assert kind in (3, 10, 11), (path, number, off, kind)
                        target = index if index in renamed else external(RAW)
                        role = "metadata-keeps-raw-VM"
                    if target != index:
                        struct.pack_into("<I", coff.data, pos + 4, target)
                    changes.append(
                        dict(
                            section=number,
                            offset=off,
                            kind=kind,
                            old_symbol=index,
                            target_symbol=target,
                            role=role,
                        )
                    )
            metadata_module = module("native_scope_call_metadata", "call-metadata.py")
            varargs_module = module("native_scope_varargs", "varargs.py")
            varargs_needed = varargs_module.applicable(C.Coff(raw), msvc)
            length_module = module("native_scope_length", "length.py")
            length_tables = length_module.has_tables(C.Coff(raw))
            own_bytecode_tables = module(
                "native_scope_own_table_census", "own-bytecode.py"
            ).has_tables(C.Coff(raw))
            own_bytecode_alloc_needed = (
                path.name == "quickjs.c.obj" and path.parent.name == "qjs-core.dir"
            )
            metadata_carrier = any(
                s["name"] == "JS_FrameCallLinkMProbe" and s["section"] > 0
                for s in original.values()
            )
            metadata_tables = (not msvc) and metadata_module.has_table_refs(C.Coff(raw))
            metadata_definition = (
                metadata_carrier if msvc else path.name == "quickjs-interpreter.c.obj"
            )
            metadata_rw = msvc and path.name == "quickjs-interpreter-register.obj"
            if metadata_definition:
                assert path in objects(build), "Existing authoritative archive input required"
            if (
                not changes
                and not renamed
                and not footer_sections
                and not metadata_carrier
                and not metadata_tables
                and not metadata_definition
                and not varargs_needed
                and not length_tables
                and not own_bytecode_tables
                and not own_bytecode_alloc_needed
            ):
                continue
            marker = bytearray(coff.stride)
            at = len(coff.strings)
            coff.strings += MARKER.encode() + b"\0"
            struct.pack_into("<II", marker, 0, 0, at)
            struct.pack_into("<i" if coff.stride == 20 else "<h", marker, 12, -1)
            marker[coff.class_offset] = 3
            coff.aliases.append(marker)
            assert not coff.extra_relocations
            result = bytearray(coff.finish())
            old_end = coff.string_offset + struct.unpack_from("<I", raw, coff.string_offset)[0]
            tail_shift = len(result) - len(raw)
            tail_pointers = []
            for number, rec in enumerate(coff.section_records, 1):
                for field in (20, 24, 28):
                    value = struct.unpack_from("<I", raw, rec["pos"] + field)[0]
                    if value and value >= old_end:
                        assert struct.unpack_from("<I", result, rec["pos"] + field)[0] == value
                        struct.pack_into("<I", result, rec["pos"] + field, value + tail_shift)
                        tail_pointers.append(
                            dict(section=number, field=field, old=value, new=value + tail_shift)
                        )
            result = bytes(result)
            check = C.Coff(result)
            for index, symbol in original.items():
                expected = dict(symbol)
                if index in renamed:
                    expected["name"] = RAW
                if index in footer_symbols:
                    expected["name"] = ".qjscold$ZSourceUnwind"
                assert check.all_symbols[index] == expected
            for number, (a, b) in enumerate(
                zip(C.Coff(raw).section_records, check.section_records), 1
            ):
                assert (raw[a["raw"] : a["raw"] + a["size"]] if a["raw"] else bytes(a["size"])) == (
                    result[b["raw"] : b["raw"] + b["size"]] if b["raw"] else bytes(b["size"])
                ), (path, number, "old payload changed")
                oldrels = [
                    struct.unpack_from("<IIH", raw, a["reloc"] + 10 * i) for i in range(a["count"])
                ]
                newrels = [
                    list(struct.unpack_from("<IIH", result, b["reloc"] + 10 * i))
                    for i in range(b["count"])
                ]
                for row in changes:
                    if row["section"] == number:
                        hits = [t for t in newrels if t[0] == row["offset"]]
                        assert len(hits) == 1 and hits[0][1:] == [row["target_symbol"], row["kind"]]
                        hits[0][1] = row["old_symbol"]
                assert list(map(tuple, newrels)) == oldrels
            entry_merge = None
            owned_merge = None
            if msvc and path.name == "quickjs-interpreter-null-proto.obj":
                result, owned_merge = merge_msvc_owned_scope(result, source, build, generation)
            if renamed and not msvc:
                assert path.name == "quickjs-interpreter-register.obj"
                # The existing register object has no allocated post-string
                # tail. The generic strict merger therefore applies unchanged.
                before_entry = C.Coff(result)
                string_end = before_entry.string_offset + len(before_entry.strings)
                assert all(
                    not struct.unpack_from("<I", result, r["pos"] + field)[0]
                    or struct.unpack_from("<I", result, r["pos"] + field)[0] < string_end
                    for r in before_entry.section_records
                    for field in (20, 24, 28)
                )
                scratch = _frame_generated_file(build, "native-scope-link") / str(time.time_ns())
                scratch.mkdir(parents=True, exist_ok=False)
                target = scratch / "register-with-entry.obj"
                target.write_bytes(result)
                M = module("native_scope_entry_merge", "extension-merge.py")
                M.append(
                    target,
                    Path(generation["entry_object"]),
                    "JS_FrameNativeCScopeEntry",
                    "native-scope-entry",
                    keep_all=True,
                    code_input=".qjsnce$C",
                    code_output=".qjscold$zzEntry" if msvc else ".qjssrf$NCS",
                    pdata_output=".qjscold$NSU" if msvc else ".pdata$zzzzzznativescope",
                    base_owner=RAW,
                    baseline_sections=(),
                )
                result = target.read_bytes()
                after_entry = C.Coff(result)
                canonical = after_entry.symbols["JS_FrameInterp"]
                actual_entry = after_entry.symbols["JS_FrameNativeCScopeEntry"]
                assert (canonical["section"], canonical["value"]) == (
                    actual_entry["section"],
                    actual_entry["value"],
                )
                end = next(
                    s
                    for s in after_entry.all_symbols.values()
                    if s["name"] == "JS_FrameNativeCScopeEntry_end" and s["section"] > 0
                )
                assert end["value"] - actual_entry["value"] == 5
                entry_merge = str(target.with_name(target.name + ".native-scope-entry-merge.json"))
            metadata_adaptation = metadata_table_routing = metadata_append = metadata_rw_append = (
                forward_native_control
            ) = None
            owned_native_control = borrow_native_control = borrow_missing_native_control = (
                js_captured_control
            ) = None
            if metadata_rw:
                result, metadata_rw_append = metadata_module.append_control(
                    source, build, path, bytes(result)
                )
                result, forward_native_control = module(
                    "native_scope_forward_control", "call-forward-native.py"
                ).append_control(source, build, path, bytes(result))
                result, owned_native_control = module(
                    "native_scope_owned_control", "call-forward-owned.py"
                ).append_control(source, build, path, bytes(result))
                result, borrow_native_control = module(
                    "native_scope_borrow_control", "call-forward-borrow.py"
                ).append_control(source, build, path, bytes(result))
                result, borrow_missing_native_control = module(
                    "native_scope_borrow_missing_control", "call-forward-borrow-missing.py"
                ).append_control(source, build, path, bytes(result))
                result, js_captured_control = module(
                    "native_scope_js_captured_control", "js-captured.py"
                ).append_control(source, build, path, bytes(result))
            if metadata_carrier:
                result, metadata_adaptation = metadata_module.adapt(
                    source, build, path, bytes(result), msvc=msvc
                )
            if metadata_tables:
                result, metadata_table_routing = metadata_module.route_tables(
                    source, build, path, bytes(result)
                )
            if metadata_definition:
                result, metadata_append = metadata_module.append_module(
                    source, build, path, bytes(result), msvc=msvc
                )
            varargs_adaptation = varargs_append = None
            if metadata_definition:
                result, varargs_append = varargs_module.append_module(
                    source, build, path, bytes(result), msvc
                )
            if varargs_needed:
                result, varargs_adaptation = varargs_module.adapt(
                    source, build, path, bytes(result), msvc
                )
            length_route = proto_direct_route = own_bytecode_route = (
                own_bytecode_allocator_route
            ) = None
            if length_tables:
                result, length_route = length_module.route_tables(
                    source, build, path, bytes(result), msvc
                )
                if not msvc:
                    result, proto_direct_route = module(
                        "native_scope_proto_direct", "proto-direct.py"
                    ).route_input(source, build, path, bytes(result), msvc)
            if own_bytecode_tables:
                result, own_bytecode_route = module(
                    "native_scope_own_bytecode", "own-bytecode.py"
                ).route_tables(source, build, path, bytes(result), msvc)
            if own_bytecode_alloc_needed:
                result, own_bytecode_allocator_route = module(
                    "native_scope_own_bytecode_allocator", "own-bytecode.py"
                ).route_core_allocations(source, build, path, bytes(result), msvc)
            backup = path.with_name(path.name + ".before-native-c-scope-route")
            assert not backup.exists()
            rows.append(
                dict(
                    path=str(path),
                    backup=str(backup),
                    before_sha256=hashlib.sha256(raw).hexdigest(),
                    after_sha256=hashlib.sha256(result).hexdigest(),
                    renamed_definitions=renamed,
                    canonical_entry_merge=entry_merge,
                    owned_carrier_merge=owned_merge,
                    call_metadata_adaptation=metadata_adaptation,
                    call_metadata_tables=metadata_table_routing,
                    call_metadata_append=metadata_append,
                    call_metadata_rw=metadata_rw_append,
                    forward_native_control=forward_native_control,
                    owned_native_control=owned_native_control,
                    borrow_native_control=borrow_native_control,
                    borrow_missing_native_control=borrow_missing_native_control,
                    js_captured_control=js_captured_control,
                    varargs_adaptation=varargs_adaptation,
                    varargs_append=varargs_append,
                    length_route=length_route,
                    proto_direct_route=proto_direct_route,
                    own_bytecode_route=own_bytecode_route,
                    own_bytecode_allocator_route=own_bytecode_allocator_route,
                    source_footer_sections=footer_sections,
                    rebased_tail_pointers=tail_pointers,
                    routes=changes,
                )
            )
            staged.append((path, backup, raw, result, path.stat()))
        length_routes = [
            v
            for r in rows
            if r["length_route"]
            for v in json.loads(Path(r["length_route"]).read_text(encoding="utf-8"))["routes"]
        ]
        assert sum(v["role"] == "base table" for v in length_routes) == 1, length_routes
        assert sum(v["role"] == "dirty table initializer" for v in length_routes) == 3 * int(
            not msvc and not generation["diagnostics"]
        ), length_routes
        direct_routes = [
            v
            for r in rows
            if r.get("proto_direct_route")
            for v in json.loads(Path(r["proto_direct_route"]).read_text(encoding="utf-8"))["routes"]
        ]
        expected_direct = 0 if msvc else 1 + int(not generation["diagnostics"])
        assert (
            sum(v["role"] == "validated producer CALL" for v in direct_routes) == expected_direct
        ), direct_routes
        assert sum(v["role"] == "object retry target" for v in direct_routes) == expected_direct, (
            direct_routes
        )
        assert sum(v["role"] == "string retry target" for v in direct_routes) == expected_direct, (
            direct_routes
        )
        own_routes = [
            v
            for r in rows
            if r.get("own_bytecode_route")
            for v in json.loads(Path(r["own_bytecode_route"]).read_text(encoding="utf-8"))["routes"]
        ]
        expected_own_readers = 1 if msvc else 4 if generation["diagnostics"] else 9
        assert (
            sum(v["role"] == "dispatch base reader" for v in own_routes) == expected_own_readers
        ), own_routes
        from x86.common.codegen.property_ic_native import enabled as property_ic_enabled

        own_fields = (16, 24, 2096) if property_ic_enabled(build) else (16, 24)
        dirty_initializers = [v for v in own_routes if v["role"] == "dirty table initializer"]
        assert len(dirty_initializers) == 3 * len(own_fields) * int(
            not msvc and not generation["diagnostics"]
        ), own_routes
        if dirty_initializers:
            assert sorted(v["selected_field_offset"] for v in dirty_initializers) == sorted(
                own_fields * 3
            )
        alloc_records = [r for r in rows if r.get("own_bytecode_allocator_route")]
        assert len(alloc_records) == 1 and Path(alloc_records[0]["path"]).name == "quickjs.c.obj"
        alloc_routes = json.loads(
            Path(alloc_records[0]["own_bytecode_allocator_route"]).read_text(encoding="utf-8")
        )["routes"]
        assert len(alloc_routes) == 2 and len({r["source_line"] for r in alloc_routes}) == 2
        metadata_owners = [r for r in rows if r["call_metadata_append"]]
        assert len(metadata_owners) == 1
        metadata_owner = Path(metadata_owners[0]["path"])
        assert metadata_owner in objects(build) and metadata_owner.name == (
            "quickjs-interpreter-null-proto.obj" if msvc else "quickjs-interpreter.c.obj"
        )
        assert sum(bool(r["call_metadata_rw"]) for r in rows) == (1 if msvc else 0)
        metadata_routes = sum(
            len(json.loads(Path(r["call_metadata_tables"]).read_text())["routes"])
            for r in rows
            if r["call_metadata_tables"]
        )
        assert metadata_routes == (0 if msvc else 8 if generation["diagnostics"] else 40), (
            metadata_routes
        )
        assert len(definitions) == 1 and definitions[0]["path"].endswith(
            "quickjs-interpreter-register.obj"
        ), definitions
        calls = sum(row["role"] in ("call", "tail-jmp") for r in rows for row in r["routes"])
        assert calls == (5 if msvc else 3), calls
        if msvc:
            assert sum(bool(row.get("owned_carrier_merge")) for row in rows) == 1
        # First materialize every exact rollback. No object is routed until
        # the complete reference census and original-payload checks pass.
        for path, backup, raw, result, stamp in staged:
            backup.write_bytes(raw)
        state.update(status="prepared", raw_definitions=definitions, executable_transfers=calls)
        save()
        for path, backup, raw, result, stamp in staged:
            assert sha(path) == hashlib.sha256(raw).hexdigest()
            path.write_bytes(result)
            os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
        for row in rows:
            assert sha(row["path"]) == row["after_sha256"]
        state.update(
            status="passed",
            policy="MSVC scope code/canonical alias and exact native rows belong to the original late cold archive member and existing unqualified output group; complete old footer moves after new native rows. GNU keeps the register-owned five-byte C tail entry. Real CALL/RET activation, no old code edits or extra MS allocated output groups.",
        )
        save()
        print("NATIVE C SCOPE ENTRY ROUTED", calls, "objects", len(rows), flush=True)
    except BaseException as exc:
        state.update(status="failed", error=repr(exc))
        save()
        raise


def restore_vm(source, build):
    receipt = _frame_generated_file(build, "quickjs-native-c-scope-route.json")
    if not receipt.exists():
        return
    C = module("native_c_scope_restore_coff", "object-adapter.py")
    state = json.loads(receipt.read_text())
    assert state["status"] in ("preparing", "prepared", "passed", "failed")
    history = _frame_build_file(build, "native-c-scope-history") / (
        sha(receipt) + "-" + str(time.time_ns())
    )
    history.mkdir(parents=True, exist_ok=False)
    for i, row in enumerate(state["records"]):
        path = Path(row["path"]).resolve()
        assert path.is_relative_to(build.resolve())
        backup = Path(row["backup"])
        if not backup.exists():
            assert state["status"] in ("preparing", "failed") and sha(path) == row["before_sha256"]
            continue
        assert sha(backup) == row["before_sha256"]
        digest = sha(path)
        if digest == row["after_sha256"]:
            stamp = path.stat()
            path.write_bytes(backup.read_bytes())
            os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
        elif digest != row["before_sha256"]:
            assert not any(
                s["name"] == MARKER for s in C.Coff(path.read_bytes()).all_symbols.values()
            ), ("Unknown routed VM epoch", path)
        shutil.copyfile(backup, history / (str(i) + "-" + backup.name))
        backup.unlink()
    shutil.copyfile(receipt, history / receipt.name)
    receipt.unlink()
    print("NATIVE C SCOPE EPOCH RESTORED", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", type=Path, required=True)
    ap.add_argument("--build", type=Path, required=True)
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--compile-module", action="store_true")
    group.add_argument("--route-vm", action="store_true")
    group.add_argument("--restore-vm", action="store_true")
    args = ap.parse_args()
    if args.compile_module:
        proof = json.loads(
            (
                _frame_generated_file(
                    args.build, "quickjs-interpreter-dense-array-pop.compile.json"
                )
            ).read_text()
        )
        compile_backend(
            args.source,
            args.build,
            msvc=Path(proof["compiler_command"][0]).name.lower() == "cl.exe",
        )
    else:
        (route_vm if args.route_vm else restore_vm)(args.source, args.build)
