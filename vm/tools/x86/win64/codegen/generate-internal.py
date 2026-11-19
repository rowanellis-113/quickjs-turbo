"""Win64 internal-call selector; leaves the seven-argument value ABI intact."""

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
import argparse
from pathlib import Path
from abi_layout import load as load_layout, assembly_contract


def generate(out, source=None, *, legacy_child=True):
    layout = load_layout(source or _frame_project_root())
    # RCX = hidden result pointer, RDX = ctx, R8 = &func, R9 = &this.
    # new_target/argc/argv/flags remain at incoming RSP+40/+48/+56/+64.
    lines = [
        (
            "JS_FrameDispatchInternal",
            [
                # C-function callees always retain the original interpreter. Test
                # the live value/class before touching native-only mode fields.
                "cmp QWORD PTR [r8+8], -1",
                "jne internal_legacy",
                "mov r11, QWORD PTR [r8]",
                "cmp WORD PTR [r11+QJS_ABI_OFF_JSObject_class_id], 13",
                "jne internal_legacy",
                "mov r10, QWORD PTR [rdx+QJS_ABI_OFF_JSContext_rt]",
                "cmp BYTE PTR [r10+QJS_ABI_OFF_JSRuntime_current_stack_frame-1], 2",
                "je internal_legacy",
                "cmp BYTE PTR [r10+QJS_ABI_OFF_JSRuntime_current_stack_frame-2], 2",
                "je internal_legacy",
                "test DWORD PTR [rsp+64], -3",
                "jnz internal_legacy",
                "mov r11, QWORD PTR [r11+QJS_ABI_OFF_JSObject_u_func_function_bytecode]",
                "cmp BYTE PTR [r11+QJS_ABI_OFF_JSFunctionBytecode_byte_code_buf-1], 2",
                "je internal_legacy",
                "cmp BYTE PTR [r10+QJS_ABI_OFF_JSRuntime_current_stack_frame-1], 1",
                "jne internal_select",
                "cmp BYTE PTR [r10+QJS_ABI_OFF_JSRuntime_current_stack_frame-2], 1",
                "jne internal_select",
                "test BYTE PTR [r11+QJS_ABI_OFF_JSFunctionBytecode_byte_code_buf-1], 1",
                "jz internal_select",
                "jmp QWORD PTR [internal_run_target]",
                "internal_legacy:",
                "jmp QWORD PTR [internal_legacy_target]",
            ],
        ),
        (
            "internal_select",
            [
                "sub rsp, 72",
                "mov QWORD PTR [rsp+32], rcx",
                "mov QWORD PTR [rsp+40], rdx",
                "mov QWORD PTR [rsp+48], r8",
                "mov QWORD PTR [rsp+56], r9",
                "mov rcx, rdx",
                "mov rdx, r8",
                "call JS_FrameResolveInternal",
                "mov rcx, QWORD PTR [rsp+32]",
                "mov rdx, QWORD PTR [rsp+40]",
                "mov r8, QWORD PTR [rsp+48]",
                "mov r9, QWORD PTR [rsp+56]",
                "test eax, eax",
                "jz internal_select_legacy",
                "add rsp, 72",
                "jmp QWORD PTR [internal_run_target]",
                "internal_select_legacy:",
                "add rsp, 72",
                "jmp QWORD PTR [internal_legacy_target]",
            ],
        ),
    ]
    externs = ["JS_FrameRunInternal", "JS_FrameResolveInternal", "qjs_frame_core_JS_CallInternal"]
    if legacy_child:
        externs.append("JS_FrameLegacyChildSelect")
    masm = [
        "; Generated internal selector; no change to the legacy interpreter layout.",
        "OPTION CASEMAP:NONE",
        "OPTION DOTNAME",
    ]
    masm += assembly_contract(layout, "masm").splitlines()
    masm += ["EXTERN " + name + ":PROC" for name in externs]
    masm += [".text$zzqjsinternal SEGMENT ALIGN(16) 'CODE'"]
    gas = [
        "# Generated internal selector; same instructions as the MASM image.",
        ".intel_syntax noprefix",
        '.section .text$zzqjsinternal,"xr"',
    ]
    gas += assembly_contract(layout, "gas").splitlines()
    for name, instructions in lines:
        masm += ["PUBLIC " + name, name + (" PROC FRAME" if name == "internal_select" else " PROC")]
        gas += [
            ".globl " + name,
            ".def " + name + "; .scl 2; .type 32; .endef",
            ".seh_proc " + name,
            name + ":",
        ]
        for index, instruction in enumerate(instructions):
            masm.append(instruction)
            gas.append(
                instruction.replace("[internal_run_target]", "[rip+internal_run_target]").replace(
                    "[internal_legacy_target]", "[rip+internal_legacy_target]"
                )
            )
            if index == 0 and name == "internal_select":
                masm += [".allocstack 72", ".endprolog"]
                gas += [".seh_stackalloc 72", ".seh_endprologue"]
            elif index == 0:
                gas += [".seh_endprologue"]
        masm += [name + " ENDP"]
        gas += [".seh_endproc"]
    run_target = "JS_FrameLegacyChildSelect" if legacy_child else "JS_FrameRunInternal"
    masm += [
        ".text$zzqjsinternal ENDS",
        ".rdata$qjsinternal SEGMENT ALIGN(8) READONLY 'CONST'",
        "internal_run_target DQ " + run_target,
        "internal_legacy_target DQ qjs_frame_core_JS_CallInternal",
        ".rdata$qjsinternal ENDS",
        "END",
    ]
    gas += [
        '.section .rdata$qjsinternal,"dr"',
        ".balign 8",
        "internal_run_target: .quad " + run_target,
        "internal_legacy_target: .quad qjs_frame_core_JS_CallInternal",
    ]
    (out / "quickjs-interpreter-internal-win64.asm").write_text("\n".join(masm) + "\n")
    (out / "quickjs-interpreter-internal-win64.S").write_text("\n".join(gas) + "\n")


def append_legacy_child(masm, gas):
    """Avoid an independent arena activation for small legacy callbacks.

    An active shared native parent still uses the established child entry.
    Root public API calls and normal JS-origin calls retain their native path.
    A small callback under a legacy C or synchronous-generator frame uses
    the original C interpreter, including its poll, quota, ownership, realm
    and exception protocols. The existing size and stack bounds also apply
    to generator callbacks; normal JS parents retain their native entry.
    """
    fields = current_abi()["offsets"]
    native = "legacy_child_native"
    name = "JS_FrameLegacyChildSelect"
    select = [
        f"mov r10, QWORD PTR [rdx+{fields['JSContext.rt']}]",
        f"test BYTE PTR [r10+{fields['JSRuntime.current_stack_frame'] - 5}], 4",
        "jnz " + native,
        f"mov r11, QWORD PTR [r10+{fields['JSRuntime.current_stack_frame']}]",
        "test r11, r11",
        "jz " + native,
        "cmp QWORD PTR [r11+16], -1",
        "jne " + native,
        "mov r11, QWORD PTR [r11+8]",
        f"cmp WORD PTR [r11+{fields['JSObject.class_id']}], 12",
        "je legacy_child_shape",
        f"cmp WORD PTR [r11+{fields['JSObject.class_id']}], 17",
        "jne " + native,
        "legacy_child_shape:",
        "mov r11, QWORD PTR [r8]",
        f"mov r11, QWORD PTR [r11+{fields['JSObject.u.func.function_bytecode']}]",
        f"cmp DWORD PTR [r11+{fields['JSFunctionBytecode.byte_code_len']}], 16",
        "ja " + native,
        f"cmp WORD PTR [r11+{fields['JSFunctionBytecode.var_count']}], 0",
        "jne " + native,
        f"cmp WORD PTR [r11+{fields['JSFunctionBytecode.var_ref_count']}], 0",
        "jne " + native,
        f"cmp WORD PTR [r11+{fields['JSFunctionBytecode.stack_size']}], 2",
        "ja " + native,
        f"cmp BYTE PTR [r10+{fields['JSRuntime.module_normalize_has_attr'] + 4}], 0",
        "je JS_FrameLegacyChildConfig",
        f"cmp BYTE PTR [r10+{fields['JSRuntime.module_normalize_has_attr'] + 4}], 1",
        "jne " + native,
        # Direct rel32 tails stay valid under ASLR. GNU ld's INSERT-after-reloc
        # islands must not rely on new absolute-pointer base relocations.
        "jmp JS_FrameLegacyChildLeaf",
        native + ":",
        "jmp JS_FrameRunInternal",
    ]
    config = [
        "sub rsp, 72",
        "legacy_child_config_alloc:",
        "mov QWORD PTR [rsp+32], rcx",
        "mov QWORD PTR [rsp+40], rdx",
        "mov QWORD PTR [rsp+48], r8",
        "mov QWORD PTR [rsp+56], r9",
        "mov QWORD PTR [rsp+64], r10",
        "lea rcx, JS_FrameLegacyChildDisable",
        "call QWORD PTR [__imp_getenv]",
        "test rax, rax",
        "setne r11b",
        "inc r11b",
        "mov r10, QWORD PTR [rsp+64]",
        f"mov BYTE PTR [r10+{fields['JSRuntime.module_normalize_has_attr'] + 4}], r11b",
        "mov rcx, QWORD PTR [rsp+32]",
        "mov rdx, QWORD PTR [rsp+40]",
        "mov r8, QWORD PTR [rsp+48]",
        "mov r9, QWORD PTR [rsp+56]",
        "add rsp, 72",
        "jmp JS_FrameLegacyChildSelect",
    ]
    assert masm.pop() == "END"
    # Called by the register generator AFTER every old cold contribution.
    # Reuse the exact old MS group names: adding even a subgroup creates POGO
    # debug records and pushes framebench's .data over a page boundary.
    masm[3:3] = ["EXTERN JS_FrameRunInternal:PROC", "EXTERN qjs_frame_core_JS_CallInternal:PROC"]
    masm += [".qjscold SEGMENT ALIGN(16) 'CODE'"]
    gas += ['.section .qjsleaf,"xr"', ".p2align 4"]
    for function, body in ((name, select), ("JS_FrameLegacyChildConfig", config)):
        masm += ["ALIGN 16", "PUBLIC " + function + ", " + function + "_end", function + " PROC"]
        gas += [
            ".p2align 4",
            ".globl " + function + ", " + function + "_end",
            ".def " + function + "; .scl 2; .type 32; .endef",
            function + ":",
        ]
        for line in body:
            masm += (
                ["PUBLIC legacy_child_config_alloc", "legacy_child_config_alloc::"]
                if line == "legacy_child_config_alloc:"
                else [
                    line.replace(
                        "jmp JS_FrameLegacyChildLeaf", "jmp NEAR PTR JS_FrameLegacyChildLeaf"
                    ).replace("jmp JS_FrameRunInternal", "jmp NEAR PTR JS_FrameRunInternal")
                ]
            )
            gas += [
                line.replace(
                    "lea rcx, JS_FrameLegacyChildDisable",
                    "lea rcx, [rip+JS_FrameLegacyChildDisable]",
                ).replace("[__imp_getenv]", "[rip+__imp_getenv]")
            ]
        masm += [function + "_end LABEL BYTE", function + " ENDP"]
        gas += [function + "_end:"]
    masm += [
        "ALIGN 4",
        name + "_unwind LABEL BYTE",
        "DB 1, 0, 0, 0",
        "JS_FrameLegacyChildConfig_unwind LABEL BYTE",
        "DB 1, legacy_child_config_alloc - JS_FrameLegacyChildConfig, 1, 0",
        "DB legacy_child_config_alloc - JS_FrameLegacyChildConfig, 082h",
        "DB 0, 0",
        'JS_FrameLegacyChildDisable DB "QJS_DISABLE_LEGACY_CHILD_GUARD", 0',
        ".qjscold ENDS",
        ".pdata$zzqjscold SEGMENT ALIGN(4) READONLY 'DATA'",
    ]
    gas += [
        ".p2align 2",
        name + "_unwind:",
        ".byte 1, 0, 0, 0",
        "JS_FrameLegacyChildConfig_unwind:",
        ".byte 1, legacy_child_config_alloc - JS_FrameLegacyChildConfig, 1, 0",
        ".byte legacy_child_config_alloc - JS_FrameLegacyChildConfig, 0x82",
        ".short 0",
        'JS_FrameLegacyChildDisable: .asciz "QJS_DISABLE_LEGACY_CHILD_GUARD"',
        '.section .pdata$zzqjsleaf,"dr"',
        ".p2align 2",
    ]
    for function in (name, "JS_FrameLegacyChildConfig"):
        masm += [
            "DD IMAGEREL "
            + function
            + ", IMAGEREL "
            + function
            + "_end, IMAGEREL "
            + function
            + "_unwind"
        ]
        gas += [".rva " + function + ", " + function + "_end, " + function + "_unwind"]
    masm += [".pdata$zzqjscold ENDS", "END"]


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--source", type=Path, default=_frame_project_root())
    ap.add_argument(
        "--standalone",
        action="store_true",
        help="development C-interpreter stage without the register child selector",
    )
    args = ap.parse_args()
    generate(args.out, args.source, legacy_child=not args.standalone)


def append_shared_bypass(masm, gas, diagnostics, native_slice):
    """Tail-forward an identical internal ABI over a coherent shared parent.

    No callee metadata is cached and no publication, quota or ownership guard
    is removed. The old C bridge remains the same-image control and root path.
    This is appended after all inherited code; no address/padding search.
    """
    abi_layout = current_abi()
    abi_fields = abi_layout["offsets"]
    name = "JS_FrameSharedCallBypass"
    config = name + "Config"
    control = name + "Control"
    disable = name + "Disable"

    def redirect(lines, old):
        begin = (
            lines.index("JS_FrameLegacyChildSelect PROC")
            if old.startswith("jmp NEAR")
            else lines.index("JS_FrameLegacyChildSelect:")
        )
        end = (
            lines.index("JS_FrameLegacyChildSelect ENDP", begin)
            if old.startswith("jmp NEAR")
            else lines.index("JS_FrameLegacyChildSelect_end:", begin)
        )
        hits = [i for i in range(begin, end) if lines[i] == old]
        assert len(hits) == 1, hits
        lines[hits[0]] = old.replace("JS_FrameRunInternal", name)

    redirect(masm, "jmp NEAR PTR JS_FrameRunInternal")
    redirect(gas, "jmp JS_FrameRunInternal")
    guard = [
        f"mov r10, QWORD PTR [rdx+{abi_fields['JSContext.rt']}]",
        f"test BYTE PTR [r10+{abi_fields['JSRuntime.current_stack_frame'] - 5}], 4",
        "jz JS_FrameRunInternal",
        "cmp BYTE PTR [" + control + "], 0",
        "je " + config,
        "cmp BYTE PTR [" + control + "], 1",
        "jne JS_FrameRunInternal",
        "jmp JS_FrameCallEntryDispatch",
    ]
    cold = [
        "sub rsp, 72",
        "shared_bypass_alloc:",
        "mov QWORD PTR [rsp+32], rcx",
        "mov QWORD PTR [rsp+40], rdx",
        "mov QWORD PTR [rsp+48], r8",
        "mov QWORD PTR [rsp+56], r9",
        "lea rcx, " + disable,
        "call QWORD PTR [__imp_getenv]",
        "test rax, rax",
        "setne r11b",
        "inc r11b",
    ]
    if diagnostics:
        cold += [
            "mov BYTE PTR [rsp+64], r11b",
            "lea rcx, " + name + "Trace",
            "call QWORD PTR [__imp_getenv]",
            "test rax, rax",
            "jnz shared_bypass_trace_checked",
            "lea rcx, " + name + "TracePrevious",
            "call QWORD PTR [__imp_getenv]",
            "test rax, rax",
            "shared_bypass_trace_checked:",
            "mov r11b, BYTE PTR [rsp+64]",
            "jz shared_bypass_config_ready",
            "mov r11b, 2",
            "shared_bypass_config_ready:",
        ]
    # An aligned byte load/store is atomic on x64. Racing first entries all
    # publish the same process-environment policy; there is no mutable target.
    cold += [
        "mov BYTE PTR [" + control + "], r11b",
        "mov rcx, QWORD PTR [rsp+32]",
        "mov rdx, QWORD PTR [rsp+40]",
        "mov r8, QWORD PTR [rsp+48]",
        "mov r9, QWORD PTR [rsp+56]",
        "add rsp, 72",
        "jmp " + name,
    ]
    assert masm.pop() == "END"
    assert any(x.startswith(".qjszlf SEGMENT") for x in masm) or native_slice
    # The MASM stream is unbuilt on MinGW, which uses the matching GAS kernel.
    mssection = ".qjszlf" if not native_slice else ".qjscold"
    masm += [mssection + " SEGMENT ALIGN(16) 'CODE'"]
    gas += ['.section .qjsundf$zzbypass,"xr"', ".p2align 4"]
    for function, stream in ((name, guard), (config, cold)):
        masm += ["ALIGN 16", "PUBLIC " + function + ", " + function + "_end", function + " PROC"]
        gas += [
            ".p2align 4",
            ".globl " + function + ", " + function + "_end",
            ".def " + function + "; .scl 2; .type 32; .endef",
            function + ":",
        ]
        for line in stream:
            if line.endswith(":"):
                masm += ["PUBLIC " + line[:-1], line[:-1] + "::"]
                gas += [".globl " + line[:-1], line]
            else:
                m = line
                for target in (config, name, "JS_FrameRunInternal", "JS_FrameCallEntryDispatch"):
                    if (
                        m.split(" ", 1)[0] in ("jmp", "jz", "je", "jne")
                        and m.split(" ", 1)[1] == target
                    ):
                        m = m.split(" ", 1)[0] + " NEAR PTR " + target
                masm += [m]
                g = line.replace("[" + control + "]", "[rip+" + control + "]").replace(
                    "[__imp_getenv]", "[rip+__imp_getenv]"
                )
                if g.startswith("lea rcx, "):
                    g = "lea rcx, [rip+" + g.split(", ", 1)[1] + "]"
                gas += [g]
        masm += [function + "_end LABEL BYTE", function + " ENDP"]
        gas += [function + "_end:"]
    masm += [
        "ALIGN 4",
        name + "_unwind LABEL BYTE",
        "DB 1,0,0,0",
        config + "_unwind LABEL BYTE",
        "DB 1,shared_bypass_alloc-" + config + ",1,0",
        "DB shared_bypass_alloc-" + config + ",082h",
        "DB 0,0",
        disable + ' DB "QJS_DISABLE_SHARED_CALL_BYPASS",0',
    ]
    gas += [
        ".p2align 2",
        name + "_unwind:",
        ".byte 1,0,0,0",
        config + "_unwind:",
        ".byte 1,shared_bypass_alloc-" + config + ",1,0",
        ".byte shared_bypass_alloc-" + config + ",0x82",
        ".short 0",
        disable + ":",
        '.asciz "QJS_DISABLE_SHARED_CALL_BYPASS"',
    ]
    if diagnostics:
        masm += [name + 'Trace DB "QJS_INTERP_FRAME_TRACE",0']
        gas += [name + "Trace:", '.asciz "QJS_INTERP_FRAME_TRACE"']
        masm += [name + 'TracePrevious DB "QJS_",76,76,73,78,84,"_FRAME_TRACE",0']
        gas += [
            name + "TracePrevious:",
            '.ascii "QJS_"',
            ".byte 76,76,73,78,84",
            '.asciz "_FRAME_TRACE"',
        ]
    masm += [mssection + " ENDS", ".pdata$zzqjsbypass SEGMENT ALIGN(4) READONLY 'DATA'"]
    gas += ['.section .pdata$zzqjsbypass,"dr"', ".p2align 2"]
    for function in (name, config):
        masm += [
            "DD IMAGEREL "
            + function
            + ",IMAGEREL "
            + function
            + "_end,IMAGEREL "
            + function
            + "_unwind"
        ]
        gas += [".rva " + function + "," + function + "_end," + function + "_unwind"]
    masm += [
        ".pdata$zzqjsbypass ENDS",
        ".qjszlm SEGMENT ALIGN(1) 'DATA'",
        "PUBLIC " + control,
        control + " DB 0",
        ".qjszlm ENDS",
        "END",
    ]
    gas += ['.section .qjsundm$zzbypass,"dw"', ".globl " + control, control + ":", ".byte 0"]
