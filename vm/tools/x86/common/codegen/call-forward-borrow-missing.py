"""Pad a readonly single-.call window inside the caller's declared stack. MIT.

Provided arguments stay owned by the paused caller. Only missing slots are
written, after every failing/observable check and before child publication.
The declared stack end excludes the caller's captured-variable table.
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
import hashlib, importlib.util, json, re, subprocess

NAME = "JS_FrameCallForwardBorrowMissingTry"
PUBLISH = "JS_FrameCallForwardBorrowMissingPublish"
COPY = "JS_FrameCallForwardOwnedCopy"
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()


def module(source, name):
    sp = importlib.util.spec_from_file_location(
        "borrow_missing_" + name.replace("-", "_"), _frame_tool_path(name + ".py")
    )
    m = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


def lines(source, diagnostics, layout_override=None):
    abi = layout_override if layout_override is not None else load_layout(source)
    fields = abi["offsets"]
    borrow = module(source, "call-forward-borrow")
    body = borrow.lines(source, diagnostics, layout_override=abi)
    body = body[body.index("mov QWORD PTR [rsp+8], r8") :]
    borrow.replace(
        body,
        ["lea eax, [r11-1]", "mov WORD PTR [r9+58], ax", "mov DWORD PTR [r9+124], 0"],
        [
            f"movzx eax, WORD PTR [rdx+{fields['JSFunctionBytecode.arg_count']}]",
            "mov WORD PTR [r9+58], ax",
            "mov DWORD PTR [r9+124], 0",
        ],
    )
    # The inherited child arg_buf is original argv+16, including zero-native-
    # argc calls. In that case an unused slot is skipped; the bound includes it.
    borrow.replace(
        body,
        ["mov r10, QWORD PTR [r9+32]", "borrow_vars_start:"],
        [
            "mov r10, QWORD PTR [r9+24]",
            "mov eax, DWORD PTR [rsp+16]",
            "test eax, eax",
            "jz borrow_pad_begin",
            "dec eax",
            "shl rax, 4",
            "add r10, rax",
            "borrow_pad_begin:",
            f"movzx eax, WORD PTR [rdx+{fields['JSFunctionBytecode.arg_count']}]",
            "shl rax, 4",
            "add rax, QWORD PTR [r9+24]",
            "borrow_pad_missing:",
            "mov QWORD PTR [r10], 0",
            "mov QWORD PTR [r10+8], 3",
            "add r10, 16",
            "cmp r10, rax",
            "jb borrow_pad_missing",
            "mov r10, QWORD PTR [r9+32]",
            "borrow_vars_start:",
        ],
    )
    body = [s.replace("borrow_", "borrow_missing_") for s in body]
    guards = [
        "lea rax, [rip+JS_FrameCallForwardBorrowMissingControl]",
        "cmp BYTE PTR [rax], 1",
        "je borrow_missing_enabled",
        "cmp BYTE PTR [rax], 2",
        "je " + COPY,
        "jmp JS_FrameCallForwardOwnedCold",
        "borrow_missing_enabled:",
        "xor eax, eax",
        "test r11d, r11d",
        "jz borrow_missing_actual",
        "lea eax, [r11-1]",
        "borrow_missing_actual:",
        f"movzx r10d, WORD PTR [rdx+{fields['JSFunctionBytecode.arg_count']}]",
        "cmp eax, r10d",
        "jae " + COPY,
        # End = arg_buf + formal*16. Check against declared operand-stack end,
        # NOT allocated frame_bytes, which may include var_refs or extensions.
        "shl r10, 4",
        "lea r10, [r8+r10+16]",
        "mov r9, QWORD PTR [rcx]",
        "mov rax, QWORD PTR [r9+80]",
        f"movzx eax, WORD PTR [rax+{fields['JSFunctionBytecode.var_count']}]",
        "shl rax, 4",
        "add rax, QWORD PTR [r9+32]",
        "mov QWORD PTR [rsp+8], rax",
        "mov rax, QWORD PTR [r9+80]",
        f"movzx eax, WORD PTR [rax+{fields['JSFunctionBytecode.stack_size']}]",
        "shl rax, 4",
        "add rax, QWORD PTR [rsp+8]",
        "cmp r10, rax",
        "ja " + COPY,
        # Also bind the declared stack span to this actual frame allocation.
        "mov eax, DWORD PTR [r9+120]",
        "add rax, r9",
        "cmp r10, rax",
        "ja " + COPY,
    ]
    assert not any(
        s.startswith(
            (
                "call ",
                "push ",
                "pop ",
                f"inc DWORD PTR [rax{abi_constants(abi)['QJS_ABI_REF_COUNT_OFFSET']:+d}]",
            )
        )
        for s in guards + body
    )
    assert "mov DWORD PTR [r9+124], 0" in body
    return guards + body


def compile_extra(source, build, compiler, msvc, diagnostics):
    body = lines(source, diagnostics)
    if msvc:
        text = [
            "OPTION CASEMAP:NONE",
            "OPTION DOTNAME",
            "EXTERN " + COPY + ":PROC",
            "EXTERN JS_FrameCallForwardBorrowMissingControl:BYTE",
            "EXTERN JS_FrameCallForwardOwnedCold:PROC",
            ".qjzzva SEGMENT ALIGN(16) READONLY 'CODE'",
            "PUBLIC " + NAME + ", " + NAME + "_end",
            NAME + " PROC",
        ]
        for line in body:
            line = re.sub(r"\[rip\+([^\]]+)\]", r"\1", line)
            if re.fullmatch(r"j\w+ \w+", line):
                op, target = line.split()
                line = op + " NEAR PTR " + target
            text.append(line)
        text += [
            NAME + "_end LABEL BYTE",
            NAME + " ENDP",
            "ALIGN 16",
            "PUBLIC " + PUBLISH + ", " + PUBLISH + "_end",
            PUBLISH + " PROC",
            "lea r10, JS_FrameCallForwardBorrowMissingControl",
            "xchg BYTE PTR [r10], cl",
            "ret",
            PUBLISH + "_end LABEL BYTE",
            PUBLISH + " ENDP",
            "ALIGN 4",
            NAME + "_unwind LABEL BYTE",
            "DB 1,0,0,0",
            ".qjzzva ENDS",
            ".pdata$zzzzzznullfast SEGMENT ALIGN(4) READONLY 'DATA'",
            "DD IMAGEREL " + NAME + ", IMAGEREL " + NAME + "_end, IMAGEREL " + NAME + "_unwind",
            "DD IMAGEREL "
            + PUBLISH
            + ", IMAGEREL "
            + PUBLISH
            + "_end, IMAGEREL "
            + NAME
            + "_unwind",
            ".pdata$zzzzzznullfast ENDS",
            "END",
        ]
        path = _frame_generated_file(build, "quickjs-interpreter-call-forward-borrow-missing.asm")
        obj = path.with_suffix(".obj")
        command = [compiler.with_name("ml64.exe"), "/nologo", "/c", "/Fo" + str(obj), path]
    else:
        text = [
            ".intel_syntax noprefix",
            '.section .qjzzva,"xr"',
            ".p2align 4",
            ".globl " + NAME + ", " + NAME + "_end",
            ".def " + NAME + "; .scl 2; .type 32; .endef",
            NAME + ":",
            *body,
            NAME + "_end:",
            ".p2align 4",
            ".globl " + PUBLISH + ", " + PUBLISH + "_end",
            ".def " + PUBLISH + "; .scl 2; .type 32; .endef",
            PUBLISH + ":",
            "lea r10, [rip+JS_FrameCallForwardBorrowMissingControl]",
            "xchg BYTE PTR [r10], cl",
            "ret",
            PUBLISH + "_end:",
            ".p2align 2",
            NAME + "_unwind:",
            ".byte 1,0,0,0",
            '.section .pdata$zzzzzznullfast,"dr"',
            ".rva " + NAME + "," + NAME + "_end," + NAME + "_unwind",
            ".rva " + PUBLISH + "," + PUBLISH + "_end," + NAME + "_unwind",
            '.section .qjslcm$zzforwardownedzborrowzmissing,"dw"',
            ".globl JS_FrameCallForwardBorrowMissingControl",
            "JS_FrameCallForwardBorrowMissingControl:",
            ".byte 255",
        ]
        path = _frame_generated_file(build, "quickjs-interpreter-call-forward-borrow-missing.S")
        obj = path.with_suffix(".obj")
        command = [compiler, "-c", "-g0", path, "-o", obj]
    path.write_text("\n".join(text) + "\n", encoding="ascii")
    command = list(map(str, command))
    p = subprocess.run(command, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
    obj.with_suffix(".log").write_bytes(p.stdout + p.stderr)
    assert p.returncode == 0, (command, p.stdout, p.stderr)
    obj.with_suffix(".compile.json").write_text(
        json.dumps(
            dict(
                status="passed",
                command=command,
                object_sha256=sha(obj),
                source_sha256=sha(path),
                diagnostics=diagnostics,
                protocol="Readonly missing-arity VM operand borrow within declared caller stack; only missing slots padded, zero argument ownership, original parent cleanup.",
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def append_module(source, build, output, msvc, code_group, prefix, owner, merge):
    merge.append(
        output,
        _frame_generated_file(build, "quickjs-interpreter-call-forward-borrow-missing.obj"),
        NAME,
        "forward-borrow-missing-asm",
        keep_all=True,
        code_input=".qjzzva",
        code_output=code_group if msvc else code_group + "$I",
        pdata_output=prefix + "1",
        writable_metadata_inputs=() if msvc else (".qjslcm$zzforwardownedzborrowzmissing",),
        base_owner=owner,
        baseline_sections=(),
    )


def append_control(source, build, path, raw):
    return module(source, "call-forward-native").append_control(
        source,
        build,
        path,
        raw,
        name="JS_FrameCallForwardBorrowMissingControl",
        previous="JS_FrameCallForwardBorrowControl",
        original_bytes=63,
    )
