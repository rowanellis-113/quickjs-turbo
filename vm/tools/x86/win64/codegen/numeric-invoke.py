"""VM numeric-native invocation with the original Win64/SF/TLS contract. MIT.

The VM already owns the nonvolatile registers. Primitive f_f/f_f_f arguments
need neither coercion nor a second Win64 callee register frame. Every failure
is precommit and returns to the exact inherited clean/dirty host entry.
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
from native_abi import current as current_abi, source_abi
from pathlib import Path
import hashlib, importlib.util, json, re, struct, subprocess

sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()


def scope_module():
    spec = importlib.util.spec_from_file_location(
        "numeric_native_scope", _frame_tool_path("native-c-scope")
    )
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def route_gas(out, diagnostics):
    # Keep the original exact clean/dirty R11 fallback. Only class12 with
    # positive actual argc reaches the original special-signature branch.
    abi_layout = current_abi()
    abi_fields = abi_layout["offsets"]
    p = out / "quickjs-interpreter-c-invoke-win64.S"
    text = p.read_text(encoding="utf-8")
    for name, target in [
        ("JS_FrameCInvokeEntry", "interp_host_call"),
        ("JS_FrameCInvokeDirtyEntry", "dirty_interp_host_call"),
    ]:
        if diagnostics and name.endswith("DirtyEntry"):
            assert name + ":" not in text
        else:
            assert text.count(name + ":\nlea r11, [rip+" + target + "]\n") == 1
    before = f"cmp BYTE PTR [rdx+{abi_fields['JSObject.u.cfunc.cproto']}], 1\nja cinvoke_fallback"
    assert text.count(before) == 1
    text = text.replace(
        before,
        f"cmp BYTE PTR [rdx+{abi_fields['JSObject.u.cfunc.cproto']}], 1\nja JS_FrameNumericInvokeGuard",
    )
    p.write_text(text, encoding="utf-8")


def route_masm(lines):
    abi_layout = current_abi()
    abi_fields = abi_layout["offsets"]
    at = lines.index("JS_FrameCInvokeEntry PROC")
    assert lines[at + 1] == "lea r11, interp_host_call"
    at = lines.index("JS_FrameCInvokeGuard PROC")
    branch = lines.index(f"cmp BYTE PTR [rdx+{abi_fields['JSObject.u.cfunc.cproto']}], 1", at) + 1
    assert lines[branch] == "ja cinvoke_fallback"
    # The old MS release branch is rel8. This is an explicit source-level
    # cold-guard change; never reinterpret its operand as a rel32 or steal
    # padding. Keep the original large interpreter and JS PIC spans gated.
    lines[branch] = "ja NEAR PTR JS_FrameNumericInvokeGuard"
    lines[:0] = [
        "EXTERN JS_FrameNumericInvokeGuard:PROC",
        "PUBLIC interp_host_call, JS_FrameInterp_end, JS_FrameInterp_unwind",
    ]


def blocks(diagnostics, msvc, c_invoke):
    abi_layout = current_abi()
    abi_fields = abi_layout["offsets"]
    committed = 2304 if diagnostics else 64
    shared_limit = 2320 if diagnostics else 80
    native_limit = 2312 if diagnostics else 72
    direct = 2297 if diagnostics else 161
    exception = 2296 if diagnostics else 160
    result = []
    fallback = "ninvoke_fallback"
    # Original CInvokeGuard established class12 and positive argc. Config
    # saves/restores every incoming volatile and getenv cannot reenter JS.
    # Exact numeric signature, formal arity, primitive argument tags and all
    # original poll/shared/quota/stack controls are still checked here.
    guard = [
        f"movzx eax, BYTE PTR [rdx+{abi_fields['JSObject.u.cfunc.cproto']}]",
        "sub eax, 6",
        "cmp eax, 1",
        "ja " + fallback,
        f"movzx eax, BYTE PTR [rdx+{abi_fields['JSObject.u.cfunc.length']}]",
        "cmp ecx, eax",
        "jl " + fallback,
        f"cmp BYTE PTR [rbx+{direct}], 0",
        "je " + fallback,
        "mov rax, QWORD PTR [rbx+56]",
        f"test BYTE PTR [rax+{abi_fields['JSRuntime.current_stack_frame'] - 5}], 32",
        "jnz " + fallback,
        f"test BYTE PTR [rax+{abi_fields['JSRuntime.current_stack_frame'] - 5}], 64",
        "jz " + fallback,
        f"movzx r10d, BYTE PTR [rax+{abi_fields['JSRuntime.current_stack_frame'] - 5}]",
        "and r10d, 3",
        "cmp r10d, 1",
        "jne " + fallback,
        "mov r10, QWORD PTR [rbx+32]",
        f"cmp r10, QWORD PTR [rbx+{committed}]",
        "jne " + fallback,
        # Original NumericFast's formal*16+200 guard starts at a CALL entry
        # eight bytes below this VM-JMP entry. Preserve that lower bound.
        f"movzx r10d, BYTE PTR [rdx+{abi_fields['JSObject.u.cfunc.length']}]",
        "shl r10, 4",
        "add r10, 208",
        "neg r10",
        "add r10, rsp",
        f"cmp r10, QWORD PTR [rax+{abi_fields['JSRuntime.stack_limit']}]",
        "jb " + fallback,
        f"cmp DWORD PTR [rsi+{abi_fields['JSContext.interrupt_counter']}], 1",
        "jle " + fallback,
        "cmp BYTE PTR [rip+JS_FrameNumericInvokeControl], 0",
        "je JS_FrameNumericInvokeConfig",
        "cmp BYTE PTR [rip+JS_FrameNumericInvokeControl], 1",
        "jne " + fallback,
        "cmp QWORD PTR [r8+8], 8",
        "je ninvoke_double0",
        "cmp QWORD PTR [r8+8], 0",
        "jne " + fallback,
        "cvtsi2sd xmm0, DWORD PTR [r8]",
        "jmp ninvoke_arg0",
        "ninvoke_double0:",
        "movsd xmm0, QWORD PTR [r8]",
        "ninvoke_arg0:",
        f"cmp BYTE PTR [rdx+{abi_fields['JSObject.u.cfunc.cproto']}], 6",
        "je JS_FrameNumericInvokeCommit",
        "cmp ecx, 2",
        "jl " + fallback,
        "cmp QWORD PTR [r8+24], 8",
        "je ninvoke_double1",
        "cmp QWORD PTR [r8+24], 0",
        "jne " + fallback,
        "cvtsi2sd xmm1, DWORD PTR [r8+16]",
        "jmp JS_FrameNumericInvokeCommit",
        "ninvoke_double1:",
        "movsd xmm1, QWORD PTR [r8+16]",
        "jmp JS_FrameNumericInvokeCommit",
        fallback + ":",
        "jmp r11",
    ]
    result.append(("JS_FrameNumericInvokeGuard", guard, "leaf"))
    kernel = c_invoke._vm_kernel(diagnostics, not msvc)
    commit = [
        line.replace("JS_FrameCInvokeBody", "JS_FrameNumericInvokeBody").replace(
            "cinvoke_", "ninvoke_commit_"
        )
        for line in kernel[5]
    ]
    result.append(("JS_FrameNumericInvokeCommit", commit, "leaf"))
    # Shadow0..31; original SF32..111; shared anchor112..135; old active136;
    # TLS slot144..151. 160 bytes includes alignment, no hidden JSValue result
    # or by-value-this slot is needed by the exact typed native prototypes.
    body = [
        "sub rsp, 160",
        "ninvoke_alloc:",
        f"mov rax, QWORD PTR [r10+{abi_fields['JSRuntime.current_stack_frame']}]",
        "mov QWORD PTR [rsp+32], rax",
        "movdqu xmm2, XMMWORD PTR [r8-16]",
        "movdqu XMMWORD PTR [rsp+40], xmm2",
        "mov QWORD PTR [rsp+56], r8",
        "mov WORD PTR [rsp+90], cx",
        "mov WORD PTR [rsp+92], 0",
        "mov rax, QWORD PTR gs:88",
        "mov ecx, DWORD PTR [rip+_tls_index]",
        "mov rax, QWORD PTR [rax+rcx*8]",
        "lea rcx, [rip+JS_FrameSharedTop]",
        "lea r9, [rip+_tls_start]",
        "sub rcx, r9",
        "add rax, rcx",
        "mov QWORD PTR [rsp+144], rax",
        "mov rcx, QWORD PTR [rax]",
        "mov QWORD PTR [rsp+112], rcx",
        "mov QWORD PTR [rsp+120], rbx",
        "mov DWORD PTR [rsp+128], 0",
        f"mov cl, BYTE PTR [r10+{abi_fields['JSRuntime.current_stack_frame'] - 5}]",
        "and cl, 4",
        "mov BYTE PTR [rsp+136], cl",
        "lea rcx, [rsp+32]",
        f"mov QWORD PTR [r10+{abi_fields['JSRuntime.current_stack_frame']}], rcx",
        "lea rcx, [rsp+112]",
        f"or BYTE PTR [r10+{abi_fields['JSRuntime.current_stack_frame'] - 5}], 4",
        "mov QWORD PTR [rax], rcx",
        f"mov r11, QWORD PTR [rdx+{abi_fields['JSObject.u.cfunc.c_function']}]",
    ]
    if diagnostics:
        body += [
            "inc QWORD PTR [rbx+2264]",
            "inc QWORD PTR [rbx+2208]",
            "lock inc QWORD PTR [rip+JS_FrameNumericInvokeHits]",
        ]
    body += [
        "JS_FrameNumericInvokeCall:",
        "call r11",
        "JS_FrameNumericInvokeAfterCall:",
        # Exact inherited double_is_int32 boxing, including -0 and INT32_MIN.
        "movq rax, xmm0",
        "mov rdx, rax",
        "shr rdx, 52",
        "and edx, 2047",
        "sub edx, 1023",
        "cmp edx, 30",
        "ja ninvoke_special",
        "mov ecx, edx",
        "mov rdx, rax",
        "shl rdx, 12",
        "shl rdx, cl",
        "test rdx, rdx",
        "jne ninvoke_float",
        "jmp ninvoke_int",
        "ninvoke_special:",
        "test rax, rax",
        "jz ninvoke_int",
        "mov rdx, 0xc1e0000000000000",
        "cmp rax, rdx",
        "je ninvoke_int",
        "ninvoke_float:",
        "mov edx, 8",
        "jmp ninvoke_boxed",
        "ninvoke_int:",
        "cvttsd2si eax, xmm0",
        "xor edx, edx",
        "ninvoke_boxed:",
        "movq xmm0, rax",
        "movq xmm1, rdx",
        "punpcklqdq xmm0, xmm1",
        "mov r10, QWORD PTR [rbx+56]",
        "mov r11, QWORD PTR [rsp+144]",
        "mov rax, QWORD PTR [rsp+112]",
        "mov QWORD PTR [r11], rax",
        f"mov al, BYTE PTR [r10+{abi_fields['JSRuntime.current_stack_frame'] - 5}]",
        "and al, 251",
        "or al, BYTE PTR [rsp+136]",
        f"mov BYTE PTR [r10+{abi_fields['JSRuntime.current_stack_frame'] - 5}], al",
        "mov rax, QWORD PTR [rsp+32]",
        f"mov QWORD PTR [r10+{abi_fields['JSRuntime.current_stack_frame']}], rax",
        "mov rax, QWORD PTR [rbx+32]",
        f"mov rdx, QWORD PTR [r10+{abi_fields['JSRuntime.stack_limit']}]",
        f"cmp rax, QWORD PTR [rbx+{committed}]",
        "jne ninvoke_refresh",
        f"cmp rdx, QWORD PTR [rbx+{shared_limit}]",
        "je ninvoke_refreshed",
        "ninvoke_refresh:",
        f"mov QWORD PTR [rbx+{committed}], rax",
        f"mov QWORD PTR [rbx+{shared_limit}], rdx",
        "test rdx, rdx",
        "jz ninvoke_limit",
        "sub rdx, rax",
        "ninvoke_limit:",
        f"mov QWORD PTR [rbx+{native_limit}], rdx",
        "ninvoke_refreshed:",
        f"mov BYTE PTR [rbx+{exception}], 0",
        "add rsp, 160",
    ]
    if msvc:
        old = body[
            body.index("mov rax, QWORD PTR gs:88") : body.index("mov QWORD PTR [rsp+144], rax")
        ]
        at = body.index(old[0])
        body[at : at + len(old)] = [
            "mov rax, QWORD PTR gs:[88]",
            "mov ecx, DWORD PTR [_tls_index]",
            "mov rax, QWORD PTR [rax+rcx*8]",
            "mov ecx, SECTIONREL js_frame_shared_top",
            "add rax, rcx",
        ]
    result.append(("JS_FrameNumericInvokeBody", body, "body"))
    result.append(("JS_FrameNumericInvokeContinue", ["jmp JS_FrameCInvokeContinue"], "leaf"))
    regs = ("rcx", "rdx", "r8", "r9", "r10", "r11", "rax")
    config = ["sub rsp, 96", "ninvoke_config_alloc:"]
    config += [f"mov QWORD PTR [rsp+{32 + i * 8}], {reg}" for i, reg in enumerate(regs)]
    config += [
        "lea rcx, [rip+JS_FrameNumericInvokeDisable]",
        "call QWORD PTR [rip+__imp_getenv]",
        "test rax, rax",
        "setne cl",
        "inc cl",
        "xor eax, eax",
        "lock cmpxchg BYTE PTR [rip+JS_FrameNumericInvokeControl], cl",
    ]
    config += [f"mov {reg}, QWORD PTR [rsp+{32 + i * 8}]" for i, reg in enumerate(regs)]
    config += ["add rsp, 96"]
    result += [
        ("JS_FrameNumericInvokeConfig", config, "config"),
        ("JS_FrameNumericInvokeConfigContinue", ["jmp JS_FrameNumericInvokeGuard"], "leaf"),
    ]
    scope_module().route_numeric(result)
    return result


@source_abi
def compile_backend(source, build, destination, *, msvc=False):
    def module(name, filename):
        sp = importlib.util.spec_from_file_location(name, _frame_tool_path(filename))
        value = importlib.util.module_from_spec(sp)
        sp.loader.exec_module(value)
        return value

    C = module("numeric_invoke_coff", "object-adapter.py")
    merge = module("numeric_invoke_merge", "extension-merge.py")
    old = module("numeric_invoke_inherited", "c-invoke.py")
    proof = json.loads(
        (
            _frame_generated_file(build, "quickjs-interpreter-dense-array-pop.compile.json")
        ).read_text()
    )
    diag = any("QJS_INTERP_FRAME_DIAGNOSTICS" in arg for arg in proof["compiler_command"])
    compiler = Path(proof["compiler_command"][0])
    kernels = blocks(diag, msvc, old)
    obj = _frame_generated_file(build, "quickjs-interpreter-numeric-invoke.obj")
    asm = _frame_build_file(
        build,
        "quickjs-interpreter-numeric-invoke.asm"
        if msvc
        else "quickjs-interpreter-numeric-invoke.S",
    )
    external = [
        "JS_FrameNativeCScopeNumericGuard",
        "interp_host_call",
        "JS_FrameCInvokeContinue",
        "JS_FrameInterp",
        "JS_FrameInterp_end",
        "JS_FrameInterp_unwind",
        "_tls_index",
        "__imp_getenv",
    ]
    if msvc:
        external += [
            "js_frame_shared_top",
            "JS_FrameNumericInvokeControl",
            "JS_FrameNumericInvokeHits",
        ]
    else:
        external += ["JS_FrameSharedTop", "_tls_start"]
        if not diag:
            external += [
                "dirty_interp_host_call",
                "JS_FramePublishDirtyTable",
                "JS_FramePublishTable",
            ]
    lines = (
        [
            "OPTION CASEMAP:NONE",
            "OPTION DOTNAME",
            *["EXTERN " + name + ":BYTE" for name in external],
            ".qjssrc$C SEGMENT ALIGN(16) 'CODE'",
        ]
        if msvc
        else [".intel_syntax noprefix", '.section .qjssrc$C,"xr"']
    )
    for name, stream, kind in kernels:
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
        for instruction in stream:
            if msvc:
                instruction = instruction.replace("rip+", "").replace(
                    "0xc1e0000000000000", "0c1e0000000000000h"
                )
                if instruction.endswith(":"):
                    lines += ["PUBLIC " + instruction[:-1], instruction[:-1] + "::"]
                    continue
                instruction = re.sub(r"^(j\w+) (\w+)$", r"\1 NEAR PTR \2", instruction)
            elif instruction.endswith(":"):
                lines += [".globl " + instruction[:-1]]
            lines.append(instruction)
        lines += [name + "_end LABEL BYTE", name + " ENDP"] if msvc else [name + "_end:"]
    lines += ["ALIGN 4"] if msvc else [".p2align 2"]
    for kind in ("leaf", "body", "config"):
        name = "ninvoke_" + kind + "_unwind"
        if msvc:
            lines += [name + " LABEL BYTE"]
            if kind == "leaf":
                lines += ["DB 021h,0,0,0"]
            elif kind == "body":
                lines += [
                    "DB 021h,ninvoke_alloc-JS_FrameNumericInvokeBody,2,0",
                    "DB ninvoke_alloc-JS_FrameNumericInvokeBody,1",
                    "DW 20",
                ]
            else:
                lines += [
                    "DB 021h,ninvoke_config_alloc-JS_FrameNumericInvokeConfig,1,0",
                    "DB ninvoke_config_alloc-JS_FrameNumericInvokeConfig,0b2h",
                    "DW 0",
                ]
            lines += [
                "DD IMAGEREL JS_FrameInterp, IMAGEREL JS_FrameInterp_end, IMAGEREL JS_FrameInterp_unwind"
            ]
        else:
            lines += [name + ":"]
            if kind == "leaf":
                lines += [".byte 33,0,0,0"]
            elif kind == "body":
                lines += [
                    ".byte 33,ninvoke_alloc-JS_FrameNumericInvokeBody,2,0",
                    ".byte ninvoke_alloc-JS_FrameNumericInvokeBody,1",
                    ".short 20",
                ]
            else:
                lines += [
                    ".byte 33,ninvoke_config_alloc-JS_FrameNumericInvokeConfig,1,0",
                    ".byte ninvoke_config_alloc-JS_FrameNumericInvokeConfig,0xb2",
                    ".short 0",
                ]
            lines += [".rva JS_FrameInterp, JS_FrameInterp_end, JS_FrameInterp_unwind"]
    if msvc:
        lines += [
            "JS_FrameNumericInvokeDisable LABEL BYTE",
            'DB "QJS_DISABLE_NATIVE_NUMERIC_INVOKE",0',
            ".qjssrc$C ENDS",
            ".pdata$zzzzzznullfast SEGMENT ALIGN(4) READONLY 'DATA'",
        ]
        for name, _, kind in kernels:
            lines += [
                "DD IMAGEREL "
                + name
                + ", IMAGEREL "
                + name
                + "_end, IMAGEREL ninvoke_"
                + kind
                + "_unwind"
            ]
        lines += [".pdata$zzzzzznullfast ENDS", "END"]
        command = [str(compiler.with_name("ml64.exe")), "/nologo", "/c", "/Fo" + str(obj), str(asm)]
    else:
        lines += [
            "JS_FrameNumericInvokeDisable:",
            '.asciz "QJS_DISABLE_NATIVE_NUMERIC_INVOKE"',
            '.section .pdata$zzzzzznullfast,"dr"',
            ".p2align 2",
        ]
        for name, _, kind in kernels:
            lines += [".rva " + name + ", " + name + "_end, ninvoke_" + kind + "_unwind"]
        lines += [
            '.section .qjssrm,"dw"',
            ".p2align 3",
            ".globl JS_FrameNumericInvokeControl, JS_FrameNumericInvokeHits",
            "JS_FrameNumericInvokeControl:",
            ".byte 0",
            ".globl JS_FrameNativeCScopeControl",
            "JS_FrameNativeCScopeControl:",
            ".byte 0",
            ".p2align 3",
            "JS_FrameNumericInvokeHits:",
            ".quad 0",
        ]
        for counter in scope_module().COUNTERS:
            lines += [".globl " + counter, counter + ":", ".quad 0"]
        command = [str(compiler), "-c", "-g0", str(asm), "-o", str(obj)]
    asm.write_text("\n".join(lines) + "\n", encoding="ascii")
    process = subprocess.run(command, capture_output=True)
    asm.with_suffix(".log").write_bytes(process.stdout + process.stderr)
    assert process.returncode == 0, (
        command,
        (process.stdout + process.stderr).decode(errors="replace"),
    )
    coff = C.Coff(obj.read_bytes())
    corrections = []
    for number, rec in enumerate(coff.section_records, 1):
        for i in range(rec["count"]):
            pos = rec["reloc"] + i * 10
            offset, symbol, kind = struct.unpack_from("<IIH", coff.data, pos)
            if 5 <= kind <= 9:
                assert msvc
                at = rec["raw"] + offset
                value = struct.unpack_from("<i", coff.data, at)[0]
                struct.pack_into("<i", coff.data, at, value - (kind - 4))
                struct.pack_into("<H", coff.data, pos + 8, 4)
                corrections.append(dict(offset=offset, kind=kind))
        name = merge.section_name(coff, number)
        if name == ".qjssrc$C" or name.startswith(".pdata"):
            struct.pack_into("<I", coff.data, rec["pos"] + 36, (rec["flags"] & ~0xE0) | 0x60000040)
    obj.write_bytes(coff.finish())
    merge.append(
        destination,
        obj,
        "JS_FrameNumericInvokeGuard",
        "numeric-invoke",
        keep_all=True,
        code_input=".qjssrc$C",
        code_output=".qjssrc$C" if msvc else ".qjssrc$Z",
        pdata_output=".pdata$zzzzzznullfast",
        writable_metadata_inputs=() if msvc else (".qjssrm",),
        base_owner="JS_FrameCallLinkM_call0",
        baseline_sections=(),
    )
    record = dict(
        status="passed",
        diagnostics=diag,
        msvc=msvc,
        generator_sha256=sha(__file__),
        asm=str(asm),
        asm_sha256=sha(asm),
        object=str(obj),
        object_sha256=sha(obj),
        destination_sha256=sha(destination),
        blocks=[name for name, _, _ in kernels],
        rel32_corrections=corrections,
        native_stack_bytes=160,
        nonvolatile_resaves=0,
        owned_root_or_js_allocation_changes=0,
        control="QJS_DISABLE_NATIVE_NUMERIC_INVOKE",
        scope="Primitive exact f_f/f_f_f, live callee; original caller poll, numeric/shared/direct modes, arity, quota and conservative stack guard; original SF/TLS and writable source metadata carrier. Original clean/dirty fallback LEAs restored. Source-level special-signature JA routes only class12/positive-argc to typed numeric guard; MS release rel8 widens to near JA. All other numeric instructions/unwind follow existing VM and cold native contribution.",
    )
    (_frame_generated_file(build, "quickjs-interpreter-numeric-invoke-generation.json")).write_text(
        json.dumps(record, indent=2) + "\n", encoding="utf-8"
    )
