"""Borrow a validated readonly single-.call argument window. MIT.

The owned entry retains compact leaves and checks its master control first.
Only its supported readonly edge enters here. Parent pending operands remain
owners until child return/unwind; borrowed child owns zero argument slots.
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

NAME = "JS_FrameCallForwardBorrowTry"
PUBLISH = "JS_FrameCallForwardBorrowPublish"
COPY = "JS_FrameCallForwardOwnedCopy"
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()


def module(source, name):
    sp = importlib.util.spec_from_file_location(
        "borrow_" + name.replace("-", "_"), _frame_tool_path(name + ".py")
    )
    m = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


def replace(body, old, new):
    hits = [i for i in range(len(body) - len(old) + 1) if body[i : i + len(old)] == old]
    assert len(hits) == 1, (old, hits)
    i = hits[0]
    body[i : i + len(old)] = new


def lines(source, diagnostics, layout_override=None):
    abi = layout_override if layout_override is not None else load_layout(source)
    fields = abi["offsets"]
    text = _frame_source_text(source, "quickjs-interpreter-loop.h")
    assert "#define FRAME_READONLY_ARGS(b) ((FRAME_KIND(b) & 7) == 3)" in text
    own = module(source, "call-forward-owned")
    body = own.lines(source, diagnostics, layout_override=abi)
    start = body.index(COPY + ":") + 1
    body = body[start:]
    replace(
        body,
        [
            "xor eax, eax",
            "test r11d, r11d",
            "jz owned_actual",
            "lea eax, [r11-1]",
            "owned_actual:",
            f"movzx r10d, WORD PTR [rdx+{fields['JSFunctionBytecode.arg_count']}]",
            "cmp eax, r10d",
            "cmovb eax, r10d",
            f"movzx r10d, WORD PTR [rdx+{fields['JSFunctionBytecode.var_count']}]",
            "add eax, r10d",
        ],
        [f"movzx eax, WORD PTR [rdx+{fields['JSFunctionBytecode.var_count']}]"],
    )
    replace(
        body,
        [
            "xor eax, eax",
            "test r11d, r11d",
            "jz owned_count",
            "lea eax, [r11-1]",
            "owned_count:",
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
        ],
        [
            "lea eax, [r11-1]",
            "mov WORD PTR [r9+58], ax",
            "mov DWORD PTR [r9+124], 0",
            "lea r10, [r8+16]",
            "mov QWORD PTR [r9+24], r10",
            "lea rax, [r9+128]",
            "mov QWORD PTR [r9+32], rax",
        ],
    )
    start = body.index("mov r10, QWORD PTR [r9+24]")
    end = body.index("owned_vars_start:")
    body[start:end] = ["mov r10, QWORD PTR [r9+32]"]
    if diagnostics:
        replace(
            body,
            ["add QWORD PTR [rcx+2216], rax"],
            ["add QWORD PTR [rcx+104], rax", "inc QWORD PTR [rcx+112]"],
        )
    body = [line.replace("owned_", "borrow_").replace(own.OLD, COPY) for line in body]
    guards = [
        "lea rax, [rip+JS_FrameCallForwardBorrowControl]",
        "cmp BYTE PTR [rax], 1",
        "je borrow_enabled",
        "cmp BYTE PTR [rax], 2",
        "je " + COPY,
        "jmp JS_FrameCallForwardOwnedCold",
        "borrow_enabled:",
        "cmp r11d, 1",
        "jb JS_FrameCallForwardBorrowMissingTry",
        "lea eax, [r11-1]",
        f"movzx r10d, WORD PTR [rdx+{fields['JSFunctionBytecode.arg_count']}]",
        "cmp eax, r10d",
        "jb JS_FrameCallForwardBorrowMissingTry",
    ]
    # No call, push/pop, RSP or nonvolatile write; no borrowed argument write.
    assert not any(
        x.startswith(
            (
                "call ",
                "push ",
                "pop ",
                f"inc DWORD PTR [rax{abi_constants(abi)['QJS_ABI_REF_COUNT_OFFSET']:+d}]",
            )
        )
        for x in body
    )
    assert "mov QWORD PTR [r9+24], r10" in body and "mov DWORD PTR [r9+124], 0" in body
    return guards + body


def compile_extra(source, build, compiler, msvc, diagnostics):
    body = lines(source, diagnostics)
    if msvc:
        text = [
            "OPTION CASEMAP:NONE",
            "OPTION DOTNAME",
            "EXTERN " + COPY + ":PROC",
            "EXTERN JS_FrameCallForwardBorrowControl:BYTE",
            "EXTERN JS_FrameCallForwardOwnedCold:PROC",
            "EXTERN JS_FrameCallForwardBorrowMissingTry:PROC",
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
            "lea r11, JS_FrameCallForwardBorrowControl",
            "xchg BYTE PTR [r11], cl",
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
        path = _frame_generated_file(build, "quickjs-interpreter-call-forward-borrow.asm")
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
            "lea r11, [rip+JS_FrameCallForwardBorrowControl]",
            "xchg BYTE PTR [r11], cl",
            "ret",
            PUBLISH + "_end:",
            ".p2align 2",
            NAME + "_unwind:",
            ".byte 1,0,0,0",
            '.section .pdata$zzzzzznullfast,"dr"',
            ".rva " + NAME + "," + NAME + "_end," + NAME + "_unwind",
            ".rva " + PUBLISH + "," + PUBLISH + "_end," + NAME + "_unwind",
            '.section .qjslcm$zzforwardownedzborrow,"dw"',
            ".globl JS_FrameCallForwardBorrowControl",
            "JS_FrameCallForwardBorrowControl:",
            ".byte 255",
        ]
        path = _frame_generated_file(build, "quickjs-interpreter-call-forward-borrow.S")
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
                protocol="Readonly adequate-arity VM operand borrow. No child argument ownership, copy, RC increment or argument write; unchanged parent pending cleanup.",
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    module(source, "call-forward-borrow-missing").compile_extra(
        source, build, compiler, msvc, diagnostics
    )


def append_module(source, build, output, msvc, code_group, prefix, owner, merge):
    merge.append(
        output,
        _frame_generated_file(build, "quickjs-interpreter-call-forward-borrow.obj"),
        NAME,
        "forward-borrow-asm",
        keep_all=True,
        code_input=".qjzzva",
        code_output=code_group if msvc else code_group + "$H",
        pdata_output=prefix + "1",
        writable_metadata_inputs=() if msvc else (".qjslcm$zzforwardownedzborrow",),
        base_owner=owner,
        baseline_sections=(),
    )
    module(source, "call-forward-borrow-missing").append_module(
        source, build, output, msvc, code_group, prefix, owner, merge
    )


def append_control(source, build, path, raw):
    return module(source, "call-forward-native").append_control(
        source,
        build,
        path,
        raw,
        name="JS_FrameCallForwardBorrowControl",
        previous="JS_FrameCallForwardOwnedControl",
        original_bytes=62,
    )
