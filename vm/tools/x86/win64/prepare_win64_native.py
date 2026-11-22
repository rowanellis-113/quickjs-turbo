"""Prepare source-level Windows x86-64 native ASM VM inputs (MSVC & clang-cl).

Zero GNU binutils dependency. Measures actual MSVC/clang-cl struct layout via
COFF probe, generates slow-op host header, generates Win64 ABI register VM
assembly in both MASM (.asm) and GAS/Clang Intel (.S) formats with complete
SEH .pdata/.xdata unwind records, optionally wires native Property IC handlers,
verifies Win64 ABI invariants (32-byte shadow space, callee-saved GPRs, zero
XMM6-XMM15 clobbers), and emits quickjs-win64-foundation.c.
"""

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys

_TOOLS_ROOT = Path(__file__).resolve().parents[2]
if str(_TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(_TOOLS_ROOT))

from x86.common.paths_x86 import activate_tools as _act_x86

_act_x86()

from x86.win64.measure_layout_win64 import measure as measure_win64


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _verify_win64_abi(asm_text, label):
    """Static verification of Win64 x64 ABI invariants."""
    # 1. Callee-saved XMM6-XMM15 must never be modified without save/restore.
    xmm_hi = re.findall(r"\bxmm(?:[6-9]|1[0-5])\b", asm_text, re.I)
    if xmm_hi:
        raise ValueError(f"{label}: Win64 callee-saved XMM register touched: {set(xmm_hi)}")
    # 2. Prologue must save all 8 callee-saved GPRs and allocate >= 32-byte shadow space.
    for reg in ("rbx", "rbp", "rsi", "rdi", "r12", "r13", "r14", "r15"):
        if f"push {reg}" not in asm_text:
            raise ValueError(f"{label}: Missing Win64 callee-saved prologue push {reg}")
    if "sub rsp, 72" not in asm_text:
        raise ValueError(f"{label}: Missing Win64 shadow-space + alignment sub rsp, 72")
    # 3. Complete SEH .pdata + .xdata unwind metadata must exist.
    if (
        "JS_FrameInterp_unwind" not in asm_text
        or "JS_FrameInterpPropertyCold_unwind" not in asm_text
    ):
        raise ValueError(f"{label}: Missing Win64 SEH unwind descriptors")


def _inject_property_ic_win64(masm_lines, gas_lines, build, layout, source):
    """Append native Property IC handlers (JS_FrameOwnBytecodeM1/M2/M3) for Win64."""
    pic_mod = _load_module(
        "qjs_pic_native", source / "tools/x86/common/codegen/property_ic_native.py"
    )
    entries, _external, _gen, _contracts = pic_mod.blocks(
        build, layout, {"aliases": ["M"]}, fallbacks=None, method_learning=False
    )

    # Expose target labels inside JS_FrameInterp PROC for MASM cross-section jumps.
    exposed_labels = {
        "interp_get_field",
        "interp_get_field2",
        "interp_put_field",
        "interp_property_slow_get_field",
        "interp_property_slow_get_field2",
        "interp_property_slow_put_field",
    }
    new_masm = []
    for line in masm_lines:
        stripped = line.strip()
        if (
            stripped.endswith(":")
            and not stripped.endswith("::")
            and stripped[:-1] in exposed_labels
        ):
            new_masm.append(stripped[:-1] + "::")
        else:
            new_masm.append(line)
    masm_lines = new_masm

    # Redirect interp_table slots for get_field / get_field2 / put_field to M1 / M2 / M3.
    slot_map = {
        "interp_get_field": "JS_FrameOwnBytecodeM1",
        "interp_get_field2": "JS_FrameOwnBytecodeM2",
        "interp_put_field": "JS_FrameOwnBytecodeM3",
    }
    masm_lines = [
        f"DQ {slot_map[line.strip()[3:].strip()]}"
        if line.strip().startswith("DQ ") and line.strip()[3:].strip() in slot_map
        else line
        for line in masm_lines
    ]
    gas_lines = [
        f".quad {slot_map[line.strip()[6:].strip()]}"
        if line.strip().startswith(".quad ") and line.strip()[6:].strip() in slot_map
        else line
        for line in gas_lines
    ]

    # Add EXTERN JS_FrameOwnBytecodeData:BYTE in MASM header.
    masm_lines.insert(3, "EXTERN JS_FrameOwnBytecodeData:BYTE")

    assert masm_lines[-1].strip() == "END", "Unexpected MASM trailer"
    masm_lines.pop()

    masm_pic = [".qjscold SEGMENT ALIGN(16) 'CODE'"]
    masm_pdata = [".pdata$zzqjscold SEGMENT ALIGN(4) READONLY 'DATA'"]
    gas_pic = ['.section .qjscold,"xr"']
    gas_pdata = ['.section .pdata$zzqjscold,"dr"', ".p2align 2"]

    orig_for_entry = {
        "JS_FrameOwnBytecodeM1": "interp_get_field",
        "JS_FrameOwnBytecodeM2": "interp_get_field2",
        "JS_FrameOwnBytecodeM3": "interp_put_field",
    }
    text_targets = set(orig_for_entry.values())

    def masm_inst(inst):
        out = re.sub(r"\[rip\+([^\]]+)\]", r"[\1]", inst)
        m = re.match(r"^(j\w+)\s+(\w+)$", out)
        if m and m.group(2) in text_targets:
            return f"{m.group(1)} NEAR PTR {m.group(2)}"
        return out

    for name, body in entries:
        orig = orig_for_entry[name]
        # Runtime gate checking JS_FrameOwnBytecodeData.reserved[3] (offset +5).
        masm_gate = [
            "cmp BYTE PTR [JS_FrameOwnBytecodeData+5], 1",
            f"jne NEAR PTR {orig}",
        ]
        gas_gate = [
            "cmp BYTE PTR [rip+JS_FrameOwnBytecodeData+5], 1",
            f"jne {orig}",
        ]
        masm_body = [masm_inst(inst) for inst in body]
        masm_pic += [
            f"PUBLIC {name}",
            f"PUBLIC {name}_end",
            f"{name} PROC",
            *masm_gate,
            *masm_body,
            f"{name}_end LABEL BYTE",
            f"{name} ENDP",
        ]
        masm_pdata.append(
            f"DD IMAGEREL {name}, IMAGEREL {name}_end, IMAGEREL JS_FrameInterpPropertyCold_unwind"
        )
        gas_pic += [
            f".globl {name}, {name}_end",
            f".def {name}; .scl 2; .type 32; .endef",
            f"{name}:",
            *gas_gate,
            *body,
            f"{name}_end:",
        ]
        gas_pdata.append(f".rva {name}, {name}_end, JS_FrameInterpPropertyCold_unwind")

    masm_pic.append(".qjscold ENDS")
    masm_pdata.append(".pdata$zzqjscold ENDS")
    masm_lines += masm_pic + masm_pdata + ["END"]
    gas_lines += gas_pic + gas_pdata
    return masm_lines, gas_lines


def _build_foundation_c(core_path, output_dir, layout):
    original = core_path.read_text(encoding="utf-8")
    anchor = "JSValue JS_Call(JSContext *ctx,"
    if original.count(anchor) != 1:
        raise ValueError("Public JS_Call definition anchor changed")
    text = original.replace(anchor, "JSValue JS_LegacyCall(JSContext *ctx,", 1)

    definition = re.compile(r"(^static JSValue )JS_CallInternal(\([^;{}]*\)\s*\{)", re.M | re.S)
    text, count = definition.subn(r"\1JS_LegacyCallInternal\2", text)
    if count != 1:
        raise ValueError("Internal JS_CallInternal definition anchor changed")

    public = re.compile(r"(^JSValue JS_LegacyCall\([^;{}]*\)\s*\{)(.*?^\})", re.M | re.S)
    match = public.search(text)
    if not match or match[2].count("JS_CallInternal(") != 1:
        raise ValueError("Original public JS_Call fallback body changed")
    text = (
        text[: match.start(2)]
        + match[2].replace("JS_CallInternal(", "JS_LegacyCallInternal(")
        + text[match.end(2) :]
    )

    text += """
#define JS_CallInternal JS_LegacyCallInternal

/* Windows x86-64 source-level native ASM VM foundation: exact core types in this TU. */
#include "interpreter-private-abi.h"
#include "src/common/call/interpreter-bytecode-metadata.inc"
#include "src/x86/win64/internal/win64-native-compat.inc"
#include "src/common/call/interpreter-slow-host-declare.inc"
#include "src/common/value/arithmetic.inc"
#include "src/common/call/quickjs-interpreter-loop.inc"
#include "src/common/call/quickjs-interpreter-shared.inc"
#include "src/common/call/interpreter-slow-host.inc"

#undef JS_CallInternal
static JSValue JS_CallInternal(JSContext *ctx, JSValueConst func_obj,
                               JSValueConst this_obj, JSValueConst new_target,
                               int argc, JSValueConst *argv, int flags)
{
    if ((flags & ~JS_CALL_FLAG_COPY_ARGV) || FRAME_STATE(ctx->rt) == 2 ||
        JS_VALUE_GET_TAG(func_obj) != JS_TAG_OBJECT ||
        JS_VALUE_GET_OBJ(func_obj)->class_id != JS_CLASS_BYTECODE_FUNCTION ||
        JS_VALUE_GET_OBJ(func_obj)->u.func.function_bytecode->func_kind != JS_FUNC_NORMAL)
        return JS_LegacyCallInternal(ctx, func_obj, this_obj, new_target, argc, argv, flags);
    if (unlikely(!FRAME_INTERNAL_STATE(ctx->rt)))
        FRAME_INTERNAL_STATE(ctx->rt) = qjs_internal_interp_internal_disabled() ? 2 : 1;
    if (FRAME_INTERNAL_STATE(ctx->rt) != 1 ||
        FRAME_KIND(JS_VALUE_GET_OBJ(func_obj)->u.func.function_bytecode) == 2)
        return JS_LegacyCallInternal(ctx, func_obj, this_obj, new_target, argc, argv, flags);
    return JS_FrameCallEntryDispatch(ctx, func_obj, this_obj, new_target, argc, argv, flags);
}

JSValue JS_Call(JSContext *ctx, JSValueConst func_obj, JSValueConst this_obj,
                int argc, JSValueConst *argv)
{
    if (FRAME_STATE(ctx->rt) == 2 || JS_VALUE_GET_TAG(func_obj) != JS_TAG_OBJECT ||
        JS_VALUE_GET_OBJ(func_obj)->class_id != JS_CLASS_BYTECODE_FUNCTION)
        return JS_LegacyCall(ctx, func_obj, this_obj, argc, argv);
    return JS_FrameCallEntryDispatch(ctx, func_obj, this_obj, JS_UNDEFINED, argc,
                                     argv, JS_CALL_FLAG_COPY_ARGV);
}
"""
    out_c = output_dir / "quickjs-win64-foundation.c"
    out_c.write_text(text, encoding="utf-8", newline="\n")
    return out_c


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", type=Path, required=True)
    ap.add_argument("--upstream", type=Path, required=True)
    ap.add_argument("--build", type=Path, required=True)
    ap.add_argument("--compiler", required=True)
    ap.add_argument("--clang-cl", action="store_true")
    ap.add_argument("--define", action="append", default=[])
    args = ap.parse_args()

    source = args.source.resolve()
    upstream = args.upstream.resolve()
    build = args.build.resolve()
    abi_dir = build / "generated/win64-abi"
    native_dir = build / "generated/win64-native"
    native_dir.mkdir(parents=True, exist_ok=True)

    # 1. Measure actual compiler layout via COFF probe
    layout = measure_win64(
        source,
        upstream,
        build,
        abi_dir,
        args.compiler,
        defines=args.define,
        is_clang_cl=args.clang_cl,
    )

    # 2. Generate quickjs-interpreter-slow.h
    slow_mod = _load_module("qjs_win64_slow", source / "tools/x86/win64/codegen/generate-slow.py")
    slow_mod.generate(source, native_dir / "quickjs-interpreter-slow.h")

    # 3. Generate Win64 register VM assembly (MASM + GAS/Clang Intel syntax)
    reg_mod = _load_module(
        "qjs_win64_register", source / "tools/x86/common/codegen/generate-register.py"
    )
    reg_mod.generate(
        source,
        native_dir,
        diagnostics=False,
        internal_entry=True,
        foundation_only=True,
        layout_override=layout,
    )

    masm_in = native_dir / "quickjs-interpreter-register-win64.asm"
    gas_in = native_dir / "quickjs-interpreter-register-win64.S"
    masm_lines = masm_in.read_text(encoding="utf-8").splitlines()
    gas_lines = gas_in.read_text(encoding="utf-8").splitlines()

    # Replace CRT-import-dependent __imp_getenv with our portable JS_FrameGetenv bridge
    masm_lines = [
        "EXTERN JS_FrameGetenv:PROC"
        if line.strip() == "EXTERN __imp_getenv:QWORD"
        else line.replace("call QWORD PTR [__imp_getenv]", "call JS_FrameGetenv")
        for line in masm_lines
    ]
    gas_lines = [
        line.replace("call QWORD PTR [rip+__imp_getenv]", "call JS_FrameGetenv")
        for line in gas_lines
    ]

    # 4. Wire native Property IC handlers if QJS_PROPERTY_IC is enabled
    if layout.get("property_ic"):
        masm_lines, gas_lines = _inject_property_ic_win64(
            masm_lines, gas_lines, build, layout, source
        )

    masm_text = "\n".join(masm_lines) + "\n"
    gas_text = "\n".join(gas_lines) + "\n"
    _verify_win64_abi(masm_text, "quickjs-win64-vm.asm")
    _verify_win64_abi(gas_text, "quickjs-win64-vm.S")

    masm_out = native_dir / "quickjs-win64-vm.asm"
    gas_out = native_dir / "quickjs-win64-vm.S"
    masm_out.write_text(masm_text, encoding="utf-8", newline="\n")
    gas_out.write_text(gas_text, encoding="utf-8", newline="\n")

    # 5. Generate quickjs-win64-foundation.c
    core_path = Path(layout["compiler_input"])
    foundation_c = _build_foundation_c(core_path, native_dir, layout)

    receipt = dict(
        schema=1,
        backend="WIN_X86_64",
        property_ic=bool(layout.get("property_ic")),
        masm_sha256=_sha(masm_out),
        gas_sha256=_sha(gas_out),
        foundation_c_sha256=_sha(foundation_c),
        layout_sha256=_sha(abi_dir / "layout.json"),
    )
    (native_dir / "PREPARE.json").write_text(
        json.dumps(receipt, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print(
        f"WIN_X86_64 NATIVE PREPARED: property_ic={receipt['property_ic']}, "
        f"masm={masm_out.name}, gas={gas_out.name}"
    )


if __name__ == "__main__":
    main()
