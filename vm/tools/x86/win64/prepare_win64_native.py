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

from bellard_backports import replace_once
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
        build,
        layout,
        {"aliases": ["M"], "borrowed_field": True},
        fallbacks=None,
        method_learning=False,
    )

    # Expose target labels inside JS_FrameInterp PROC for MASM cross-section jumps.
    exposed_labels = {
        "interp_get_field",
        "interp_get_field2",
        "interp_put_field",
        "interp_call_method",
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
    text_targets = set(orig_for_entry.values()) | {"interp_call_method"}
    pic_exposed_labels = {"property_ic_M2_probe", "property_ic_M2_legacy"}

    def masm_inst(inst):
        out = re.sub(r"\[rip\+([^\]]+)\]", r"[\1]", inst)
        if out.endswith(":") and not out.endswith("::") and out[:-1] in pic_exposed_labels:
            return out[:-1] + "::"
        m = re.match(r"^(j\w+)\s+(\w+)$", out)
        if m and m.group(2) in text_targets:
            return f"{m.group(1)} NEAR PTR {m.group(2)}"
        return out

    for name, body in entries:
        orig = orig_for_entry.get(name)
        if orig is not None:
            # Runtime gate checking JS_FrameOwnBytecodeData.reserved[3] (offset +5).
            masm_gate = [
                "cmp BYTE PTR [JS_FrameOwnBytecodeData+5], 1",
                f"jne NEAR PTR {orig}",
            ]
            gas_gate = [
                "cmp BYTE PTR [rip+JS_FrameOwnBytecodeData+5], 1",
                f"jne {orig}",
            ]
        else:
            # JS_FrameBorrowedField already gates itself via JS_FrameOwnBytecodeData+3.
            masm_gate = []
            gas_gate = []
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


def _wire_win64_inline_properties(text, property_ic):
    text = replace_once(
        text,
        "static no_inline int resize_properties(JSContext *ctx, JSShape **psh,",
        '#include "src/common/property/inline-properties.h"\n'
        "#define QJS_HYBRID_INLINE_PROPERTIES 1\n\n"
        "static no_inline int resize_properties(JSContext *ctx, JSShape **psh,",
        "Win64 property storage helper types",
    )
    if "turbo_obj_flags" not in text:
        text = replace_once(
            text,
            "    uint8_t is_HTMLDDA : 1; /* specific annex B IsHtmlDDA behavior */",
            "    uint8_t is_HTMLDDA : 1; uint8_t turbo_obj_flags : 7; /* specific annex B IsHtmlDDA behavior */",
            "Win64 private object flags",
        )
    text = replace_once(
        text,
        "    js_trigger_gc(ctx->rt, sizeof(JSObject) + sizeof(JSProperty) * sh->prop_size);\n"
        "    p = js_malloc(ctx, sizeof(JSObject));",
        "    size_t inline_bytes = (class_id == JS_CLASS_OBJECT || (props && class_id == JS_CLASS_ARRAY))\n"
        "        ? qjs_inline_property_plan(sh, 0, props ? 4u : 0u) : 0;\n"
        "    size_t object_bytes = inline_bytes ? inline_bytes : sizeof(JSObject);\n"
        "    js_trigger_gc(ctx->rt, object_bytes + (inline_bytes ? 0 : sizeof(JSProperty) * sh->prop_size));\n"
        "    p = js_malloc(ctx, object_bytes);",
        "Win64 plain-object allocation",
    )
    if "p->turbo_obj_flags = 0;" not in text:
        text = replace_once(
            text,
            "    p->is_prototype = 0;\n    p->first_weak_ref = NULL;",
            "    p->is_prototype = 0; p->turbo_obj_flags = 0;\n    p->first_weak_ref = NULL;",
            "Win64 initialize inline bit before installing GC header",
        )
    text = replace_once(
        text,
        "    p->prop = js_malloc(ctx, sizeof(JSProperty) * sh->prop_size);",
        "    p->prop = inline_bytes ? qjs_inline_property_initialize(p, sh, 0, inline_bytes)\n"
        "                           : js_malloc(ctx, sizeof(JSProperty) * sh->prop_size);",
        "Win64 ordinary property storage owner",
    )
    old_realloc = "js_realloc(ctx, p->prop, sizeof(new_prop[0]) * new_size)"
    if text.count(old_realloc) != 2:
        raise ValueError("Review Win64 property growth and compaction anchors")
    text = text.replace(
        old_realloc,
        old_realloc.replace("js_realloc(ctx, p->prop,", "qjs_inline_property_realloc(ctx, p,"),
    )
    text = replace_once(
        text,
        "js_realloc(ctx, p->prop, sizeof(p->prop[0]) *",
        "qjs_inline_property_realloc(ctx, p, sizeof(p->prop[0]) *",
        "Win64 resized hashed property transition",
    )
    text = replace_once(
        text,
        "    js_free_rt(rt, p->prop);",
        "    if (!qjs_inline_property_current(p))\n        js_free_rt(rt, p->prop);",
        "Win64 ordinary destruction property guard",
    )
    text = replace_once(
        text,
        "            s->prop_count += sh->prop_count;",
        "            s->prop_count += sh->prop_count;\n            qjs_inline_property_account(s, p);",
        "Win64 memory usage inline property accounting",
    )
    if property_ic:
        text = replace_once(
            text,
            '#include "src/common/property/property-ic.inc"',
            '#include "src/common/property/inline-property-ic-storage.inc"',
            "Win64 co-allocated property IC resize",
        )
    return text


def _prepare_win64_admission(source, output_dir, layout):
    c_match = _load_module("qjs_win64_c_match", source / "tools/common/backports/c_source_match.py")
    loop = (source / "src/common/call/quickjs-interpreter-loop.inc").read_text(encoding="utf-8")
    signature = "static FRAME_CODE bool js_frame_validate(JSFunctionBytecode *b)"
    original = c_match.extract_function(loop, signature)
    loop = replace_once(
        loop,
        "static FRAME_INLINE JSFunctionBytecode *js_frame_target(",
        "static no_inline bool js_frame_win64_admit(JSFunctionBytecode *b);\n\n"
        "static FRAME_INLINE JSFunctionBytecode *js_frame_target(",
        "Win64 admission forward declaration",
    )
    loop = replace_once(
        loop,
        "if (!FRAME_KIND(b) && !js_frame_validate(b))",
        "if (!FRAME_KIND(b) && !js_frame_win64_admit(b))",
        "Win64 admission dispatch",
    )
    (output_dir / "quickjs-win64-loop.h").write_text(loop, encoding="utf-8", newline="\n")

    extra_cases = """        case OP_regexp:
        case OP_set_name:
        case OP_set_name_computed:
        case OP_set_proto:
        case OP_copy_data_properties:
        case OP_check_object:
        case OP_for_in_start:
        case OP_for_in_next:
            if (getenv("QJS_DISABLE_WIN64_EXTRA_OPS") != NULL)
                return false;
            break;
        case OP_for_of_start:
        case OP_for_of_next:
        case OP_iterator_close:
        case OP_catch:
        case OP_gosub:
        case OP_ret:
        case OP_nip_catch:
            if (getenv("QJS_DISABLE_FRAME_ITERATOR") != NULL ||
                getenv("QJS_DISABLE_WIN64_ITERATOR") != NULL)
                return false;
            break;
        case OP_append:
        case OP_apply:
            if (getenv("QJS_DISABLE_FRAME_VARARGS") != NULL ||
                getenv("QJS_DISABLE_FRAME_ITERATOR") != NULL ||
                getenv("QJS_DISABLE_WIN64_ITERATOR") != NULL)
                return false;
            break;
"""
    anchor = "#undef FRAME_OP\n            break;\n"
    branch_anchor = "        case OP_goto:\n        case OP_if_true:\n        case OP_if_false:"
    branch_repl = "        case OP_catch:\n        case OP_gosub:\n" + branch_anchor

    short_fn = replace_once(
        original,
        signature,
        "static no_inline bool JS_FrameWin64ShortValidate(JSFunctionBytecode *b)",
        "Win64 short validator signature",
    )
    short_fn = replace_once(short_fn, anchor, anchor + extra_cases, "Win64 short extra opcodes")
    short_fn = replace_once(short_fn, branch_anchor, branch_repl, "Win64 short catch/gosub targets")

    long_fn = replace_once(
        original,
        signature,
        "static FRAME_LARGE_CODE bool JS_FrameLongValidate(JSFunctionBytecode *b)",
        "Win64 long validator signature",
    )
    long_fn = replace_once(
        long_fn,
        "int pos, size, op, index, target;",
        "int pos, size, op, index; int64_t target;",
        "Win64 long validator target width",
    )
    if long_fn.count("target = pos + 1 +") != 3:
        raise ValueError("Review Win64 checked branch-target arithmetic")
    long_fn = long_fn.replace("target = pos + 1 +", "target = (int64_t)pos + 1 +")
    long_fn = replace_once(
        long_fn,
        "uint8_t boundaries[(4096 + 7) / 8]",
        "uint8_t boundaries[FRAME_LARGE_BITMAP_BYTES]",
        "Win64 long validator bitmap",
    )
    long_fn = replace_once(
        long_fn,
        "b->byte_code_len > 4096",
        "b->byte_code_len > FRAME_LARGE_CODE_MAX",
        "Win64 long validator limit",
    )
    long_fn = replace_once(long_fn, anchor, anchor + extra_cases, "Win64 long extra opcodes")
    long_fn = replace_once(long_fn, branch_anchor, branch_repl, "Win64 long catch/gosub targets")
    admission_h = (
        "#define FRAME_LARGE_CODE_DEFAULT "
        + str(int(bool(layout.get("property_ic"))))
        + "\n"
        + '#include "src/common/call/large-code-policy.inc"\n\n'
        + short_fn
        + "\n\n"
        + long_fn
        + "\n\nstatic no_inline bool js_frame_win64_admit(JSFunctionBytecode *b)\n"
        "{\n"
        "    if (js_frame_validate(b))\n"
        "        return true;\n"
        "    if (!js_frame_register_enabled(b->realm->rt) ||\n"
        '        getenv("QJS_DISABLE_WIN64_ADMISSION") != NULL)\n'
        "        return false;\n"
        "    if (b->byte_code_len <= 4096)\n"
        "        return JS_FrameWin64ShortValidate(b);\n"
        "    return js_frame_large_select(b);\n"
        "}\n"
    )
    (output_dir / "quickjs-win64-admission.h").write_text(
        admission_h, encoding="utf-8", newline="\n"
    )


def _prepare_win64_json(source, output_dir):
    paths_mod = _load_module("qjs_common_paths", source / "tools/common/paths.py")
    json_mod = _load_module("qjs_linux_json", source / "tools/x86/linux/json_workers.py")
    text = paths_mod.source_text(source, "linux-json.inc")
    text = text.replace('#include "qjs-json-simd.h"', "#include <emmintrin.h>")
    text = text.replace("/* @QJS_MSC_INTRIN@ */", "#include <intrin.h>")
    text = text.replace(
        "#include <stdatomic.h>\n",
        "#include <stdatomic.h>\n"
        "static inline JSAtom frame_json_dup_atom(JSContext *ctx, JSAtom v)\n"
        "{\n"
        "    return JS_DupAtom(ctx, v);\n"
        "}\n",
        1,
    )
    text = re.sub(r"\bqjs_vec128_t\b", "__m128i", text)
    text = re.sub(r"\bqjs_vec_\w+\b", lambda m: json_mod.VEC_REV[m[0]], text)
    text = replace_once(
        text,
        "extern _Atomic unsigned char JS_FrameJSONControl;\n"
        "/* Generated native leaf helpers implement an indivisible byte read and locked\n"
        " * CAS. Their owned late code/unwind entries avoid adding volatile metadata\n"
        " * before the inherited dispatch table or retaining unused CRT COMDAT copies. */\n"
        "extern unsigned char JS_FrameJSONLoad8(const unsigned char *);\n"
        "extern _Bool JS_FrameJSONCAS8(unsigned char *, unsigned char *, unsigned char);",
        "static _Atomic unsigned char JS_FrameJSONControl;\n"
        "static __forceinline unsigned char JS_FrameJSONLoad8(const unsigned char *p)\n"
        "{\n"
        "    return atomic_load_explicit((const _Atomic unsigned char *)p, memory_order_relaxed);\n"
        "}\n"
        "static __forceinline _Bool JS_FrameJSONCAS8(unsigned char *p, unsigned char *expected,\n"
        "                                           unsigned char desired)\n"
        "{\n"
        "    return atomic_compare_exchange_strong_explicit(\n"
        "        (_Atomic unsigned char *)p, expected, desired, memory_order_relaxed,\n"
        "        memory_order_relaxed);\n"
        "}",
        "Win64 local JSON control atomics",
    )
    text = re.sub(
        r"QJS_CONTROL_SLOT_ADDR\(p,\s*(\w+)\);",
        lambda m: f"p = &{m[1]};",
        text,
    )
    text = re.sub(
        r"QJS_JSON_STACK_CHECK\(([^,]+),\s*([^\)]+)\);",
        lambda m: f"return js_check_stack_overflow({m[2].strip()}, 0);",
        text,
    )
    text = text.replace("JS_FrameJSONCallbackStringify(", "JS_LegacyJSONStringify(")
    old_prop = "                prop = js_realloc(p->ctx, o->prop, sizeof(JSProperty) * (size_t)e->to->prop_size);"
    if text.count(old_prop) != 1:
        raise ValueError("Review Win64 JSON property storage growth boundary")
    text = text.replace(
        old_prop,
        "#ifdef QJS_HYBRID_INLINE_PROPERTIES\n"
        "                prop = qjs_inline_property_realloc(\n"
        "                    p->ctx, o, sizeof(JSProperty) * (size_t)e->to->prop_size);\n"
        "#else\n" + old_prop + "\n#endif",
    )
    text = replace_once(
        text,
        "    value = strtod(buf, NULL);",
        "    {\n"
        "        JSATODTempMem atod_mem;\n"
        "        value = js_atod(buf, NULL, 10, 0, &atod_mem);\n"
        "    }",
        "Win64 JSON js_atod parser",
    )
    (output_dir / "quickjs-win64-json.h").write_text(text, encoding="utf-8", newline="\n")


def _prepare_win64_locale(source, output_dir):
    locale = (source / "src/common/string/locale-compare.inc").read_text(encoding="utf-8")
    boundary = "/* Native compound interpreter entry."
    if locale.count(boundary) != 1:
        raise ValueError("Review Win64 locale-compare boundary")
    locale = locale[: locale.index(boundary)]
    locale = replace_once(
        locale,
        "#ifdef _MSC_VER\n"
        "extern unsigned char JS_FrameCallMetaLoadByte(unsigned char *);\n"
        "extern unsigned char JS_FrameCallMetaInitByte(unsigned char *, unsigned char);\n"
        '#pragma section(".qjslfm", read, write)\n'
        '__declspec(allocate(".qjslfm"))\n'
        "#else\n"
        '__attribute__((section(".qjslfm"), aligned(1)))\n'
        "#endif\n"
        "static unsigned char js_frame_locale_compare_control;",
        "#include <stdatomic.h>\nstatic _Atomic unsigned char js_frame_locale_compare_control;",
        "Win64 locale control declaration",
    )
    locale = replace_once(
        locale,
        "#ifdef _MSC_VER\n"
        "    mode = JS_FrameCallMetaLoadByte(&js_frame_locale_compare_control);\n"
        "#else\n"
        "    mode = __atomic_load_n(&js_frame_locale_compare_control, __ATOMIC_RELAXED);\n"
        "#endif\n"
        "    if (unlikely(mode == 0)) {\n"
        '        unsigned char desired = getenv("QJS_DISABLE_LOCALE_COMPARE_LATIN1") ? 2 : 1;\n'
        "#ifdef _MSC_VER\n"
        "        mode = JS_FrameCallMetaInitByte(&js_frame_locale_compare_control, desired);\n"
        "#else\n"
        "        __atomic_compare_exchange_n(&js_frame_locale_compare_control, &mode, desired, false,\n"
        "                                    __ATOMIC_RELAXED, __ATOMIC_RELAXED);\n"
        "#endif\n"
        "        if (!mode)\n"
        "            mode = desired;\n"
        "    }",
        "    mode = atomic_load_explicit(&js_frame_locale_compare_control, memory_order_relaxed);\n"
        "    if (unlikely(mode == 0)) {\n"
        '        unsigned char desired = getenv("QJS_DISABLE_LOCALE_COMPARE_LATIN1") ? 2 : 1;\n'
        "        atomic_compare_exchange_strong_explicit(&js_frame_locale_compare_control, &mode,\n"
        "                                                desired, memory_order_relaxed,\n"
        "                                                memory_order_relaxed);\n"
        "        if (!mode)\n"
        "            mode = desired;\n"
        "    }",
        "Win64 locale control atomics",
    )
    (output_dir / "quickjs-win64-locale.h").write_text(locale, encoding="utf-8", newline="\n")


def _prepare_win64_sort(source, output_dir):
    sort_src = (source / "src/common/array/default-string-sort.inc").read_text(encoding="utf-8")
    boundary = "#ifdef _MSC_VER\nextern void qjs_default_string_sort_original"
    if sort_src.count(boundary) != 1:
        raise ValueError("Review Win64 default-string-sort boundary")
    sort_src = sort_src[: sort_src.index(boundary)]
    sort_src = replace_once(
        sort_src,
        "#ifdef _MSC_VER\n"
        "extern unsigned char JS_FrameCallMetaLoadByte(unsigned char *);\n"
        "extern unsigned char JS_FrameCallMetaInitByte(unsigned char *, unsigned char);\n"
        "#endif\n"
        "static unsigned char js_default_string_sort_mode;",
        "#include <stdatomic.h>\nstatic _Atomic unsigned char js_default_string_sort_mode;",
        "Win64 default-string-sort control declaration",
    )
    sort_src = replace_once(
        sort_src,
        "#ifdef _MSC_VER\n"
        "    mode = JS_FrameCallMetaLoadByte(&js_default_string_sort_mode);\n"
        "#else\n"
        "    mode = __atomic_load_n(&js_default_string_sort_mode, __ATOMIC_RELAXED);\n"
        "#endif\n"
        "    if (unlikely(!mode)) {\n"
        '        unsigned char desired = getenv("QJS_DISABLE_DEFAULT_STRING_RADIX") ? 2 : 1;\n'
        "#ifdef _MSC_VER\n"
        "        mode = JS_FrameCallMetaInitByte(&js_default_string_sort_mode, desired);\n"
        "#else\n"
        "        __atomic_compare_exchange_n(&js_default_string_sort_mode, &mode, desired, false,\n"
        "                                    __ATOMIC_RELAXED, __ATOMIC_RELAXED);\n"
        "#endif\n"
        "        if (!mode)\n"
        "            mode = desired;\n"
        "    }",
        "    mode = atomic_load_explicit(&js_default_string_sort_mode, memory_order_relaxed);\n"
        "    if (unlikely(!mode)) {\n"
        '        unsigned char desired = getenv("QJS_DISABLE_DEFAULT_STRING_RADIX") ? 2 : 1;\n'
        "        atomic_compare_exchange_strong_explicit(&js_default_string_sort_mode, &mode,\n"
        "                                                desired, memory_order_relaxed,\n"
        "                                                memory_order_relaxed);\n"
        "        if (!mode)\n"
        "            mode = desired;\n"
        "    }",
        "Win64 default-string-sort control atomics",
    )
    sort_src += (
        "\nstatic void JS_ArrayDefaultStringSortDispatch(\n"
        "    void *base, size_t count, size_t size, cmp_f compare, void *opaque)\n"
        "{\n"
        "    if (size != sizeof(ValueSlot) || !js_default_string_sort_try(base, count, opaque))\n"
        "        rqsort(base, count, size, compare, opaque);\n"
        "}\n"
    )
    (output_dir / "quickjs-win64-sort.h").write_text(sort_src, encoding="utf-8", newline="\n")


def _prepare_win64_small_char(source, output_dir):
    small = (source / "src/common/kernel/small-char.c").read_text(encoding="utf-8")
    small = replace_once(
        small,
        '#include "src/common/call/interpreter-retained-context.inc"\n',
        "",
        "Win64 small-char retained-context include",
    )
    small = replace_once(
        small,
        "extern JSValue qjs_frame_core_js_new_string_char(JSContext *, uint16_t);\n"
        "extern JSAtom qjs_frame_core___JS_NewAtom(JSRuntime *, JSString *, int);\n",
        "",
        "Win64 small-char same-TU static functions",
    )
    small = re.sub(
        r'\s*__attribute__\(\(section\("\.qjzzpm"\),\s*aligned\(\d+\)\)\)',
        "",
        small,
    )
    small = small.replace("FRAME_INLINE", "WIN64_SC_INLINE")
    small = small.replace("FRAME_CODE", "no_inline")
    small = re.sub(r"\bqjs_frame_core_js_new_string_char\b", "js_new_string_char", small)
    small = re.sub(r"\bqjs_frame_core___JS_NewAtom\b", "__JS_NewAtom", small)
    header = (
        "#if defined(_MSC_VER)\n"
        "#define WIN64_SC_INLINE __forceinline\n"
        "#else\n"
        "#define WIN64_SC_INLINE inline __attribute__((always_inline))\n"
        "#endif\n" + small + "\n#undef WIN64_SC_INLINE\n"
    )
    (output_dir / "quickjs-win64-small-char.h").write_text(header, encoding="utf-8", newline="\n")


def _prepare_win64_slow_host(source, output_dir):
    c_match = _load_module(
        "qjs_win64_host_match", source / "tools/common/backports/c_source_match.py"
    )
    owner = (source / "src/common/call/interpreter-slow-host.inc").read_text(encoding="utf-8")
    template = c_match.extract_function(
        owner, "static QJS_FRAME_SLOW_HOST_CODE JSValue\njs_frame_slow_host_call("
    )
    body = template[template.index("{") :]
    original = "js_frame_legacy_call(ctx, callee, receiver, argc, argv)"
    if body.count(original) != 2:
        raise ValueError("Review Win64 slow-host template consumers")
    common_decl = (
        "struct JSFrameRegisterState *state, struct JSFrame *frame, struct JSFrameSegment *segment, "
        "size_t used, uint8_t *pc, JSValue *sp, JSContext *ctx"
    )
    common = (
        "JSFrameRegisterState *state, JSFrame *frame, JSFrameSegment *segment, "
        "size_t used, uint8_t *pc, JSValue *sp, JSContext *ctx"
    )
    specs = [
        ("start", "int", ", bool async", "js_for_of_start(ctx, sp, async)"),
        ("next", "int", ", int offset", "js_for_of_next(ctx, sp, offset)"),
        (
            "close",
            "int",
            ", JSValueConst object, bool throwing",
            "JS_IteratorClose(ctx, object, throwing)",
        ),
        ("append", "int", "", "js_append_enumerate(ctx, sp)"),
        (
            "apply",
            "JSValue",
            ", int magic",
            "js_function_apply(ctx, sp[-3], 2, vc(&sp[-2]), magic)",
        ),
        (
            "set_name_computed",
            "int",
            "",
            "JS_DefineObjectNameComputed(ctx, sp[-1], sp[-2], JS_PROP_CONFIGURABLE)",
        ),
        (
            "set_proto",
            "int",
            ", JSValueConst proto",
            "JS_SetPrototypeInternal(ctx, sp[-2], proto, true)",
        ),
        (
            "copy_data_properties",
            "int",
            ", int mask",
            "JS_CopyDataProperties(ctx, sp[-1 - (mask & 3)], sp[-1 - ((mask >> 2) & 7)], sp[-1 - ((mask >> 5) & 7)], 0)",
        ),
        ("for_in_start", "int", "", "js_for_in_start(ctx, sp)"),
        ("for_in_next", "int", "", "js_for_in_next(ctx, sp)"),
    ]
    decls, defs = [], []
    for name, result, extra, call in specs:
        decl_sig = f"static {result} js_win64_slow_host_{name}({common_decl}{extra})"
        sig = f"static QJS_FRAME_SLOW_HOST_CODE {result} js_win64_slow_host_{name}({common}{extra})"
        code = body.replace(original, call)
        if result == "int":
            code = replace_once(code, "    JSValue result;", "    int result;", "Win64 host int")
        code = replace_once(
            code,
            "    state->sp = sp;",
            "    state->sp = sp;\n    frame->saved_sp = sp;\n    frame->sf.cur_pc = pc;",
            "Win64 host cursor publication",
        )
        decls.append(decl_sig + ";")
        defs.append(sig + "\n" + code)
    (output_dir / "quickjs-win64-slow-host-declare.h").write_text(
        "\n".join(decls) + "\n", encoding="utf-8", newline="\n"
    )
    (output_dir / "quickjs-win64-slow-host.h").write_text(
        "\n\n".join(defs) + "\n", encoding="utf-8", newline="\n"
    )


def _inject_fast_ops_win64(masm_lines, gas_lines, upstream, layout):
    """Inject Win64 zero-exit native opcodes and fast C-host dispatch routing."""
    opcodes = re.findall(
        r"^DEF\(\s*(\w+)\s*,", (upstream / "quickjs-opcode.h").read_text(encoding="utf-8"), re.M
    )
    atoms = re.findall(
        r"^DEF\(\s*(\w+)\s*,", (upstream / "quickjs-atom.h").read_text(encoding="utf-8"), re.M
    )
    atom_id = {name: i + 1 for i, name in enumerate(atoms)}
    if (
        atom_id["length"] != layout["constants"]["JS_ATOM_length"]
        or atom_id["bigint"] != layout["constants"]["JS_ATOM_bigint"]
    ):
        raise ValueError("Win64 quickjs-atom.h enum mismatch against measured layout constants")

    prefix_rc = layout["reference_count_model"] == "allocator-prefix"
    rc_off = (
        layout["offsets"]["JSMallocBlockHeader.ref_count"]
        - layout["offsets"]["JSMallocBlockHeader.user_data"]
        if prefix_rc
        else layout["offsets"]["JSGCObjectHeader.ref_count"]
    )
    rc_disp = f"{rc_off:+d}" if rc_off else ""
    rt_atom_off = layout["offsets"]["JSRuntime.atom_array"]
    rt_csf_off = layout["offsets"]["JSRuntime.current_stack_frame"]
    obj_class_off = layout["offsets"]["JSObject.class_id"]
    obj_shape_off = layout["offsets"]["JSObject.shape"]
    obj_prop_off = layout["offsets"]["JSObject.prop"]
    bc_code_off = layout["offsets"]["JSFunctionBytecode.byte_code_buf"]
    bc_len_off = layout["offsets"]["JSFunctionBytecode.byte_code_len"]
    gvar_off = layout["offsets"]["JSContext.global_var_obj"]
    gobj_off = layout["offsets"]["JSContext.global_obj"]
    mask_off = layout["offsets"]["JSShape.prop_hash_mask"]
    str_len_byte = layout["bits"]["JSString.len"][0][0]
    html_byte, html_mask = layout["bits"]["JSObject.is_HTMLDDA"][0]
    cproto_off = layout["offsets"]["JSObject.u.cfunc.cproto"]
    cproto_magic = layout["constants"]["JS_CFUNC_generic_magic"]
    cproto_ff = layout["constants"]["JS_CFUNC_f_f"]
    cproto_fff = layout["constants"]["JS_CFUNC_f_f_f"]
    flags_mask = (
        layout["constants"]["JS_PROP_TMASK"]
        | layout["constants"]["JS_PROP_LENGTH"]
        | layout["constants"]["JS_PROP_WRITABLE"]
    )
    flags_writable = layout["constants"]["JS_PROP_WRITABLE"]

    # 1. Wire JS_FrameInterpHostDispatch -> JS_Win64HostDirectFast / JS_Win64HostNumericFast / Shared.
    # Also route OP_add slow boundary -> JS_Win64AddSlow, OP_add_loc string edges -> JS_Win64AddLocalStringCold,
    # OP_get_array_el/el2 string edges -> JS_Win64StringIndexCold, float inc/dec, and caught host exceptions.
    masm_ext_idx = masm_lines.index("EXTERN JS_FrameInterpHostDirectScoped:PROC")
    masm_lines[masm_ext_idx + 1 : masm_ext_idx + 1] = [
        "EXTERN JS_Win64HostDirectFast:PROC",
        "EXTERN JS_Win64HostNumericFast:PROC",
        "EXTERN JS_Win64AddSlow:PROC",
        "EXTERN JS_Win64AddLocalString:PROC",
        "EXTERN JS_Win64StringIndexStep:PROC",
        "EXTERN JS_Win64ForOfNext:PROC",
        "EXTERN JS_Win64ArrayFrom:PROC",
        "EXTERN JS_Win64Object:PROC",
        "EXTERN JS_Win64DefineField:PROC",
        "JS_Win64HostExceptionResume PROTO",
        "JS_Win64AddLocalStringCold PROTO",
        "JS_Win64StringIndexCold PROTO",
        "JS_Win64FloatIncLoc PROTO",
        "JS_Win64FloatDecLoc PROTO",
        "JS_Win64FloatInc PROTO",
        "JS_Win64FloatDec PROTO",
        "JS_Win64FloatPostInc PROTO",
        "JS_Win64FloatPostDec PROTO",
    ]
    masm_text_tmp = "\n".join(masm_lines)
    masm_text_tmp = replace_once(
        masm_text_tmp,
        "call JS_FrameInterpBig_add",
        "call JS_Win64AddSlow",
        "Win64 MASM OP_add fast string/rope route",
    )
    masm_text_tmp = replace_once(
        masm_text_tmp,
        "interp_host_exception::\n"
        "mov rcx, rbx\n"
        "call JS_FrameInterpSlow\n"
        "mov rbp, QWORD PTR [rbx]\n"
        "mov r12, QWORD PTR [rbx+16]\n"
        "mov r13, QWORD PTR [rbx+24]\n"
        "jmp interp_exit",
        "interp_host_exception::\n"
        "mov rcx, rbx\n"
        "call JS_FrameInterpSlow\n"
        "mov rbp, QWORD PTR [rbx]\n"
        "mov r12, QWORD PTR [rbx+16]\n"
        "mov r13, QWORD PTR [rbx+24]\n"
        "jmp NEAR PTR JS_Win64HostExceptionResume",
        "Win64 MASM caught host exception continuation",
    )
    for op_arr in ("interp_get_array_el", "interp_get_array_el2"):
        masm_text_tmp = replace_once(
            masm_text_tmp,
            f"{op_arr}::\ncmp DWORD PTR [r13-8], 0\njne interp_slow\n"
            "cmp DWORD PTR [r13-24], -1\njne interp_slow",
            f"{op_arr}::\ncmp DWORD PTR [r13-8], 0\njne interp_slow\n"
            "cmp DWORD PTR [r13-24], -1\njne NEAR PTR JS_Win64StringIndexCold",
            f"Win64 MASM {op_arr} string-index route",
        )
    masm_text_tmp = replace_once(
        masm_text_tmp,
        f"cmp BYTE PTR [rax+{cproto_off}], {cproto_magic}\n"
        "ja interp_host_dispatch_legacy\n"
        "jmp JS_FrameInterpHostDirectScoped\n"
        "interp_host_dispatch_legacy::\n"
        "jmp JS_FrameInterpHostScoped",
        f"cmp BYTE PTR [rax+{cproto_off}], {cproto_magic}\n"
        "jbe interp_host_dispatch_direct\n"
        f"cmp BYTE PTR [rax+{cproto_off}], {cproto_ff}\n"
        "je interp_host_dispatch_numeric\n"
        f"cmp BYTE PTR [rax+{cproto_off}], {cproto_fff}\n"
        "jne interp_host_dispatch_legacy\n"
        "interp_host_dispatch_numeric::\n"
        "jmp JS_Win64HostNumericFast\n"
        "interp_host_dispatch_direct::\n"
        "jmp JS_Win64HostDirectFast\n"
        "interp_host_dispatch_legacy::\n"
        "jmp JS_FrameInterpHostShared",
        "Win64 MASM fast host dispatch",
    )
    masm_lines = masm_text_tmp.splitlines()

    gas_text_tmp = "\n".join(gas_lines)
    gas_text_tmp = replace_once(
        gas_text_tmp,
        "call JS_FrameInterpBig_add",
        "call JS_Win64AddSlow",
        "Win64 GAS OP_add fast string/rope route",
    )
    gas_text_tmp = replace_once(
        gas_text_tmp,
        "interp_host_exception:\n"
        "mov rcx, rbx\n"
        "call JS_FrameInterpSlow\n"
        "mov rbp, QWORD PTR [rbx]\n"
        "mov r12, QWORD PTR [rbx+16]\n"
        "mov r13, QWORD PTR [rbx+24]\n"
        "jmp interp_exit",
        "interp_host_exception:\n"
        "mov rcx, rbx\n"
        "call JS_FrameInterpSlow\n"
        "mov rbp, QWORD PTR [rbx]\n"
        "mov r12, QWORD PTR [rbx+16]\n"
        "mov r13, QWORD PTR [rbx+24]\n"
        "jmp JS_Win64HostExceptionResume",
        "Win64 GAS caught host exception continuation",
    )
    for op_arr in ("interp_get_array_el", "interp_get_array_el2"):
        gas_text_tmp = replace_once(
            gas_text_tmp,
            f"{op_arr}:\ncmp DWORD PTR [r13-8], 0\njne interp_slow\n"
            "cmp DWORD PTR [r13-24], -1\njne interp_slow",
            f"{op_arr}:\ncmp DWORD PTR [r13-8], 0\njne interp_slow\n"
            "cmp DWORD PTR [r13-24], -1\njne JS_Win64StringIndexCold",
            f"Win64 GAS {op_arr} string-index route",
        )
    gas_text_tmp = replace_once(
        gas_text_tmp,
        f"cmp BYTE PTR [rax+{cproto_off}], {cproto_magic}\n"
        "ja interp_host_dispatch_legacy\n"
        "jmp JS_FrameInterpHostDirectScoped\n"
        "interp_host_dispatch_legacy:\n"
        "jmp JS_FrameInterpHostScoped",
        f"cmp BYTE PTR [rax+{cproto_off}], {cproto_magic}\n"
        "jbe interp_host_dispatch_direct\n"
        f"cmp BYTE PTR [rax+{cproto_off}], {cproto_ff}\n"
        "je interp_host_dispatch_numeric\n"
        f"cmp BYTE PTR [rax+{cproto_off}], {cproto_fff}\n"
        "jne interp_host_dispatch_legacy\n"
        "interp_host_dispatch_numeric:\n"
        "jmp JS_Win64HostNumericFast\n"
        "interp_host_dispatch_direct:\n"
        "jmp JS_Win64HostDirectFast\n"
        "interp_host_dispatch_legacy:\n"
        "jmp JS_FrameInterpHostShared",
        "Win64 GAS fast host dispatch",
    )
    gas_lines = gas_text_tmp.splitlines()

    # Route the two numeric rejection edges in interp_add_loc_mixed -> JS_Win64AddLocalStringCold.
    for lines_ref, lbl, repl in (
        (masm_lines, "interp_add_loc_mixed::", "jne NEAR PTR JS_Win64AddLocalStringCold"),
        (gas_lines, "interp_add_loc_mixed:", "jne JS_Win64AddLocalStringCold"),
    ):
        begin = lines_ref.index(lbl)
        end = lines_ref.index("jmp QWORD PTR [rdi+rax*8]", begin) + 1
        hits = [i for i in range(begin, end) if lines_ref[i].strip() == "jne interp_slow"]
        if len(hits) != 2:
            raise ValueError(f"Review Win64 add_loc rejection edges ({lbl}: {len(hits)})")
        for idx in hits:
            lines_ref[idx] = repl

    # Route cold non-int inc/dec edges -> JS_Win64Float* normalizers.
    for op_lbl, off_cmp, expected_cmp, target in (
        ("interp_inc_loc", 4, "cmp DWORD PTR [r8+8], 0", "JS_Win64FloatIncLoc"),
        ("interp_dec_loc", 4, "cmp DWORD PTR [r8+8], 0", "JS_Win64FloatDecLoc"),
        ("interp_inc", 1, "cmp DWORD PTR [r13-8], 0", "JS_Win64FloatInc"),
        ("interp_dec", 1, "cmp DWORD PTR [r13-8], 0", "JS_Win64FloatDec"),
        ("interp_post_inc", 1, "cmp DWORD PTR [r13-8], 0", "JS_Win64FloatPostInc"),
        ("interp_post_dec", 1, "cmp DWORD PTR [r13-8], 0", "JS_Win64FloatPostDec"),
    ):
        for lines_ref, suffix, jprefix in (
            (masm_lines, "::", "jne NEAR PTR "),
            (gas_lines, ":", "jne "),
        ):
            idx = lines_ref.index(op_lbl + suffix)
            if (
                lines_ref[idx + off_cmp].strip() != expected_cmp
                or lines_ref[idx + off_cmp + 1].strip() != "jne interp_slow"
            ):
                raise ValueError(f"Review Win64 inc/dec handler shape for {op_lbl}{suffix}")
            lines_ref[idx + off_cmp + 1] = jprefix + target

    # Expose interp_slow:: / interp_reload:: / interp_exit:: in MASM so cold handlers can branch.
    masm_expose = {"interp_slow", "interp_reload", "interp_exit"}
    masm_lines = [
        line.strip()[:-1] + "::"
        if line.strip().endswith(":")
        and not line.strip().endswith("::")
        and line.strip()[:-1] in masm_expose
        else line
        for line in masm_lines
    ]

    # 2. Zero-exit native opcode handlers (Win64 ABI safe: only volatile GPRs & xmm0..xmm3).
    dispatch = [
        "inc r12",
        "movzx eax, BYTE PTR [r12]",
        "jmp QWORD PTR [rdi+rax*8]",
    ]
    extra_ops = [
        (
            "push_bigint_i32",
            "JS_Win64PushBigIntI32",
            [
                "mov eax, DWORD PTR [r12+1]",
                "mov QWORD PTR [r13], rax",
                "mov QWORD PTR [r13+8], 7",
                "add r13, 16",
                "add r12, 5",
                "movzx eax, BYTE PTR [r12]",
                "jmp QWORD PTR [rdi+rax*8]",
            ],
        ),
        (
            "check_object",
            "JS_Win64CheckObject",
            [
                "cmp DWORD PTR [r13-8], -1",
                "jne interp_slow",
                *dispatch,
            ],
        ),
        (
            "to_object",
            "JS_Win64ToObject",
            [
                "cmp DWORD PTR [r13-8], -1",
                "jne interp_slow",
                *dispatch,
            ],
        ),
        (
            "plus",
            "JS_Win64Plus",
            [
                "mov eax, DWORD PTR [r13-8]",
                "test eax, eax",
                "jz win64_plus_ok",
                "cmp eax, 8",
                "jne interp_slow",
                "win64_plus_ok:",
                *dispatch,
            ],
        ),
        (
            "nip1",
            "JS_Win64Nip1",
            [
                "cmp DWORD PTR [r13-40], 0",
                "jge win64_nip1_move",
                "mov rax, QWORD PTR [r13-48]",
                f"cmp DWORD PTR [rax{rc_disp}], 1",
                "jle interp_slow",
                f"dec DWORD PTR [rax{rc_disp}]",
                "win64_nip1_move:",
                "movdqu xmm0, XMMWORD PTR [r13-32]",
                "movdqu xmm1, XMMWORD PTR [r13-16]",
                "movdqu XMMWORD PTR [r13-48], xmm0",
                "movdqu XMMWORD PTR [r13-32], xmm1",
                "sub r13, 16",
                *dispatch,
            ],
        ),
        (
            "dup3",
            "JS_Win64Dup3",
            [
                "mov rax, QWORD PTR [r13-48]",
                "mov rdx, QWORD PTR [r13-40]",
                "test edx, edx",
                "jns win64_dup3_1",
                f"inc DWORD PTR [rax{rc_disp}]",
                "win64_dup3_1:",
                "mov QWORD PTR [r13], rax",
                "mov QWORD PTR [r13+8], rdx",
                "mov rax, QWORD PTR [r13-32]",
                "mov rdx, QWORD PTR [r13-24]",
                "test edx, edx",
                "jns win64_dup3_2",
                f"inc DWORD PTR [rax{rc_disp}]",
                "win64_dup3_2:",
                "mov QWORD PTR [r13+16], rax",
                "mov QWORD PTR [r13+24], rdx",
                "mov rax, QWORD PTR [r13-16]",
                "mov rdx, QWORD PTR [r13-8]",
                "test edx, edx",
                "jns win64_dup3_3",
                f"inc DWORD PTR [rax{rc_disp}]",
                "win64_dup3_3:",
                "mov QWORD PTR [r13+32], rax",
                "mov QWORD PTR [r13+40], rdx",
                "add r13, 48",
                *dispatch,
            ],
        ),
        (
            "insert4",
            "JS_Win64Insert4",
            [
                "mov rax, QWORD PTR [r13-16]",
                "mov rdx, QWORD PTR [r13-8]",
                "mov QWORD PTR [r13], rax",
                "mov QWORD PTR [r13+8], rdx",
                "movdqu xmm0, XMMWORD PTR [r13-32]",
                "movdqu XMMWORD PTR [r13-16], xmm0",
                "movdqu xmm0, XMMWORD PTR [r13-48]",
                "movdqu XMMWORD PTR [r13-32], xmm0",
                "movdqu xmm0, XMMWORD PTR [r13-64]",
                "movdqu XMMWORD PTR [r13-48], xmm0",
                "test edx, edx",
                "jns win64_ins4_done",
                f"inc DWORD PTR [rax{rc_disp}]",
                "win64_ins4_done:",
                "mov QWORD PTR [r13-64], rax",
                "mov QWORD PTR [r13-56], rdx",
                "add r13, 16",
                *dispatch,
            ],
        ),
        (
            "perm3",
            "JS_Win64Perm3",
            [
                "movdqu xmm0, XMMWORD PTR [r13-32]",
                "movdqu xmm1, XMMWORD PTR [r13-48]",
                "movdqu XMMWORD PTR [r13-48], xmm0",
                "movdqu XMMWORD PTR [r13-32], xmm1",
                *dispatch,
            ],
        ),
        (
            "perm4",
            "JS_Win64Perm4",
            [
                "movdqu xmm0, XMMWORD PTR [r13-32]",
                "movdqu xmm1, XMMWORD PTR [r13-48]",
                "movdqu xmm2, XMMWORD PTR [r13-64]",
                "movdqu XMMWORD PTR [r13-32], xmm1",
                "movdqu XMMWORD PTR [r13-48], xmm2",
                "movdqu XMMWORD PTR [r13-64], xmm0",
                *dispatch,
            ],
        ),
        (
            "perm5",
            "JS_Win64Perm5",
            [
                "movdqu xmm0, XMMWORD PTR [r13-32]",
                "movdqu xmm1, XMMWORD PTR [r13-48]",
                "movdqu XMMWORD PTR [r13-32], xmm1",
                "movdqu xmm1, XMMWORD PTR [r13-64]",
                "movdqu XMMWORD PTR [r13-48], xmm1",
                "movdqu xmm1, XMMWORD PTR [r13-80]",
                "movdqu XMMWORD PTR [r13-64], xmm1",
                "movdqu XMMWORD PTR [r13-80], xmm0",
                *dispatch,
            ],
        ),
        (
            "swap2",
            "JS_Win64Swap2",
            [
                "movdqu xmm0, XMMWORD PTR [r13-64]",
                "movdqu xmm1, XMMWORD PTR [r13-48]",
                "movdqu xmm2, XMMWORD PTR [r13-32]",
                "movdqu xmm3, XMMWORD PTR [r13-16]",
                "movdqu XMMWORD PTR [r13-64], xmm2",
                "movdqu XMMWORD PTR [r13-48], xmm3",
                "movdqu XMMWORD PTR [r13-32], xmm0",
                "movdqu XMMWORD PTR [r13-16], xmm1",
                *dispatch,
            ],
        ),
        (
            "rot3l",
            "JS_Win64Rot3l",
            [
                "movdqu xmm0, XMMWORD PTR [r13-48]",
                "movdqu xmm1, XMMWORD PTR [r13-32]",
                "movdqu xmm2, XMMWORD PTR [r13-16]",
                "movdqu XMMWORD PTR [r13-48], xmm1",
                "movdqu XMMWORD PTR [r13-32], xmm2",
                "movdqu XMMWORD PTR [r13-16], xmm0",
                *dispatch,
            ],
        ),
        (
            "rot3r",
            "JS_Win64Rot3r",
            [
                "movdqu xmm0, XMMWORD PTR [r13-16]",
                "movdqu xmm1, XMMWORD PTR [r13-32]",
                "movdqu xmm2, XMMWORD PTR [r13-48]",
                "movdqu XMMWORD PTR [r13-16], xmm1",
                "movdqu XMMWORD PTR [r13-32], xmm2",
                "movdqu XMMWORD PTR [r13-48], xmm0",
                *dispatch,
            ],
        ),
        (
            "rot4l",
            "JS_Win64Rot4l",
            [
                "movdqu xmm0, XMMWORD PTR [r13-64]",
                "movdqu xmm1, XMMWORD PTR [r13-48]",
                "movdqu xmm2, XMMWORD PTR [r13-32]",
                "movdqu xmm3, XMMWORD PTR [r13-16]",
                "movdqu XMMWORD PTR [r13-64], xmm1",
                "movdqu XMMWORD PTR [r13-48], xmm2",
                "movdqu XMMWORD PTR [r13-32], xmm3",
                "movdqu XMMWORD PTR [r13-16], xmm0",
                *dispatch,
            ],
        ),
        (
            "rot5l",
            "JS_Win64Rot5l",
            [
                "movdqu xmm0, XMMWORD PTR [r13-80]",
                "movdqu xmm1, XMMWORD PTR [r13-64]",
                "movdqu XMMWORD PTR [r13-80], xmm1",
                "movdqu xmm1, XMMWORD PTR [r13-48]",
                "movdqu XMMWORD PTR [r13-64], xmm1",
                "movdqu xmm1, XMMWORD PTR [r13-32]",
                "movdqu XMMWORD PTR [r13-48], xmm1",
                "movdqu xmm1, XMMWORD PTR [r13-16]",
                "movdqu XMMWORD PTR [r13-32], xmm1",
                "movdqu XMMWORD PTR [r13-16], xmm0",
                *dispatch,
            ],
        ),
        (
            "typeof_is_undefined",
            "JS_Win64TypeofIsUndefined",
            [
                "mov eax, DWORD PTR [r13-8]",
                "cmp eax, -1",
                "je win64_tiu_obj",
                "cmp eax, -6",
                "jg win64_tiu_imm",
                "cmp eax, -9",
                "jl interp_slow",
                "mov r8, QWORD PTR [r13-16]",
                f"cmp DWORD PTR [r8{rc_disp}], 1",
                "jle interp_slow",
                f"dec DWORD PTR [r8{rc_disp}]",
                "jmp win64_tiu_false",
                "win64_tiu_obj:",
                "mov r8, QWORD PTR [r13-16]",
                f"test BYTE PTR [r8+{html_byte}], {html_mask}",
                "jnz interp_slow",
                f"cmp DWORD PTR [r8{rc_disp}], 1",
                "jle interp_slow",
                f"dec DWORD PTR [r8{rc_disp}]",
                "win64_tiu_false:",
                "mov QWORD PTR [r13-16], 0",
                "mov QWORD PTR [r13-8], 1",
                *dispatch,
                "win64_tiu_imm:",
                "cmp eax, 3",
                "je win64_tiu_true",
                "jb win64_tiu_false",
                "cmp eax, 7",
                "je win64_tiu_false",
                "cmp eax, 8",
                "je win64_tiu_false",
                "jmp interp_slow",
                "win64_tiu_true:",
                "mov QWORD PTR [r13-16], 1",
                "mov QWORD PTR [r13-8], 1",
                *dispatch,
            ],
        ),
        (
            "typeof_is_function",
            "JS_Win64TypeofIsFunction",
            [
                "mov eax, DWORD PTR [r13-8]",
                "cmp eax, -1",
                "je win64_tif_obj",
                "cmp eax, -6",
                "jg win64_tif_imm",
                "cmp eax, -9",
                "jl interp_slow",
                "mov r8, QWORD PTR [r13-16]",
                f"cmp DWORD PTR [r8{rc_disp}], 1",
                "jle interp_slow",
                f"dec DWORD PTR [r8{rc_disp}]",
                "win64_tif_false:",
                "mov QWORD PTR [r13-16], 0",
                "mov QWORD PTR [r13-8], 1",
                *dispatch,
                "win64_tif_obj:",
                "mov r8, QWORD PTR [r13-16]",
                f"cmp DWORD PTR [r8{rc_disp}], 1",
                "jle interp_slow",
                f"movzx ecx, WORD PTR [r8+{obj_class_off}]",
                "cmp ecx, 13",
                "je win64_tif_obj_true",
                "cmp ecx, 12",
                "je win64_tif_obj_true",
                "cmp ecx, 1",
                "je win64_tif_obj_false",
                "cmp ecx, 2",
                "je win64_tif_obj_false",
                "cmp ecx, 5",
                "jne interp_slow",
                "win64_tif_obj_false:",
                f"dec DWORD PTR [r8{rc_disp}]",
                "jmp win64_tif_false",
                "win64_tif_obj_true:",
                f"dec DWORD PTR [r8{rc_disp}]",
                "mov QWORD PTR [r13-16], 1",
                "mov QWORD PTR [r13-8], 1",
                *dispatch,
                "win64_tif_imm:",
                "cmp eax, 3",
                "jbe win64_tif_false",
                "cmp eax, 7",
                "je win64_tif_false",
                "cmp eax, 8",
                "je win64_tif_false",
                "jmp interp_slow",
            ],
        ),
        (
            "typeof",
            "JS_Win64Typeof",
            [
                "mov eax, DWORD PTR [r13-8]",
                "cmp eax, -1",
                "je win64_to_obj",
                "cmp eax, -6",
                "jg win64_to_imm",
                "cmp eax, -9",
                "jl interp_slow",
                "mov r8, QWORD PTR [r13-16]",
                f"cmp DWORD PTR [r8{rc_disp}], 1",
                "jle interp_slow",
                f"dec DWORD PTR [r8{rc_disp}]",
                "cmp eax, -7",
                "je win64_to_str",
                "cmp eax, -6",
                "je win64_to_str",
                "cmp eax, -8",
                "je win64_to_sym",
                f"mov ecx, {atom_id['bigint']}",
                "jmp win64_to_ret",
                "win64_to_obj:",
                "mov r8, QWORD PTR [r13-16]",
                f"test BYTE PTR [r8+{html_byte}], {html_mask}",
                "jnz interp_slow",
                f"cmp DWORD PTR [r8{rc_disp}], 1",
                "jle interp_slow",
                f"movzx ecx, WORD PTR [r8+{obj_class_off}]",
                "cmp ecx, 1",
                "je win64_to_obj_ok",
                "cmp ecx, 2",
                "je win64_to_obj_ok",
                "cmp ecx, 13",
                "je win64_to_fn_ok",
                "cmp ecx, 12",
                "jne interp_slow",
                "win64_to_fn_ok:",
                f"dec DWORD PTR [r8{rc_disp}]",
                f"mov ecx, {atom_id['function']}",
                "jmp win64_to_ret",
                "win64_to_obj_ok:",
                f"dec DWORD PTR [r8{rc_disp}]",
                f"mov ecx, {atom_id['object']}",
                "jmp win64_to_ret",
                "win64_to_imm:",
                "test eax, eax",
                "jz win64_to_num",
                "cmp eax, 8",
                "je win64_to_num",
                "cmp eax, 3",
                "je win64_to_undef",
                "cmp eax, 1",
                "je win64_to_bool",
                "cmp eax, 2",
                "je win64_to_null",
                "cmp eax, 7",
                "jne interp_slow",
                f"mov ecx, {atom_id['bigint']}",
                "jmp win64_to_ret",
                "win64_to_str:",
                f"mov ecx, {atom_id['string']}",
                "jmp win64_to_ret",
                "win64_to_sym:",
                f"mov ecx, {atom_id['symbol']}",
                "jmp win64_to_ret",
                "win64_to_num:",
                f"mov ecx, {atom_id['number']}",
                "jmp win64_to_ret",
                "win64_to_bool:",
                f"mov ecx, {atom_id['boolean']}",
                "jmp win64_to_ret",
                "win64_to_null:",
                f"mov ecx, {atom_id['object']}",
                "jmp win64_to_ret",
                "win64_to_undef:",
                f"mov ecx, {atom_id['undefined']}",
                "win64_to_ret:",
                "mov r8, QWORD PTR [rbx+56]",
                f"mov r8, QWORD PTR [r8+{rt_atom_off}]",
                "mov r8, QWORD PTR [r8+rcx*8]",
                f"inc DWORD PTR [r8{rc_disp}]",
                "mov QWORD PTR [r13-16], r8",
                "mov QWORD PTR [r13-8], -7",
                *dispatch,
            ],
        ),
        (
            "catch",
            "JS_Win64Catch",
            [
                "movsxd rdx, DWORD PTR [r12+1]",
                "lea rax, [r12+rdx+1]",
                "mov rcx, QWORD PTR [rbp+80]",
                f"sub rax, QWORD PTR [rcx+{bc_code_off}]",
                "mov QWORD PTR [r13], rax",
                "mov QWORD PTR [r13+8], 5",
                "add r13, 16",
                "add r12, 5",
                "movzx eax, BYTE PTR [r12]",
                "jmp QWORD PTR [rdi+rax*8]",
            ],
        ),
        (
            "nip_catch",
            "JS_Win64NipCatch",
            [
                "cmp DWORD PTR [r13-24], 5",
                "jne interp_slow",
                "movdqu xmm0, XMMWORD PTR [r13-16]",
                "movdqu XMMWORD PTR [r13-32], xmm0",
                "sub r13, 16",
                *dispatch,
            ],
        ),
        (
            "gosub",
            "JS_Win64Gosub",
            [
                "mov rcx, QWORD PTR [rbp+80]",
                f"mov r8, QWORD PTR [rcx+{bc_code_off}]",
                "lea rax, [r12+5]",
                "sub rax, r8",
                "mov QWORD PTR [r13], rax",
                "mov QWORD PTR [r13+8], 0",
                "add r13, 16",
                "movsxd rdx, DWORD PTR [r12+1]",
                "lea r12, [r12+rdx+1]",
                "movzx eax, BYTE PTR [r12]",
                "jmp QWORD PTR [rdi+rax*8]",
            ],
        ),
        (
            "ret",
            "JS_Win64Ret",
            [
                "cmp DWORD PTR [r13-8], 0",
                "jne interp_slow",
                "mov eax, DWORD PTR [r13-16]",
                "mov rcx, QWORD PTR [rbp+80]",
                f"cmp eax, DWORD PTR [rcx+{bc_len_off}]",
                "jae interp_slow",
                "sub r13, 16",
                f"add rax, QWORD PTR [rcx+{bc_code_off}]",
                "mov r12, rax",
                "movzx eax, BYTE PTR [r12]",
                "jmp QWORD PTR [rdi+rax*8]",
            ],
        ),
    ]

    def put_var_hash(obj_off):
        if prefix_rc:
            return [
                f"mov r8, QWORD PTR [rsi+{obj_off}]",
                f"mov r10, QWORD PTR [r8+{obj_shape_off}]",
                "mov eax, r9d",
                "mov rcx, 7046029254386353131",
                "imul rax, rcx",
                "shr rax, 32",
                f"mov ecx, DWORD PTR [r10+{mask_off}]",
                f"lea r11, [r10+rcx*4+{layout['offsets']['JSShape.hash_table'] + 4}]",
                "inc ecx",
                "imul rax, rcx",
                "shr rax, 32",
                "neg rax",
                "mov ecx, DWORD PTR [r11+rax*4-4]",
            ]
        return [
            f"mov r8, QWORD PTR [rsi+{obj_off}]",
            f"mov r10, QWORD PTR [r8+{obj_shape_off}]",
            f"mov ecx, DWORD PTR [r10+{mask_off}]",
            "mov edx, r9d",
            "and edx, ecx",
            "neg rdx",
            "mov ecx, DWORD PTR [r10+rdx*4-4]",
            f"lea r11, [r10+{layout['offsets']['JSShape.prop']}]",
        ]

    def fast_c_op(c_target, tag):
        return [
            "mov QWORD PTR [rbx], rbp",
            "mov QWORD PTR [rbx+16], r12",
            "mov QWORD PTR [rbx+24], r13",
            "mov r10, QWORD PTR [rbx+56]",
            f"mov QWORD PTR [r10+{rt_csf_off}], rbp",
            "mov rcx, rbx",
            f"call {c_target}",
            "cmp eax, 2",
            f"je win64_{tag}_done",
            "test eax, eax",
            "jz interp_reload",
            "mov rbp, QWORD PTR [rbx]",
            "mov r12, QWORD PTR [rbx+16]",
            "mov r13, QWORD PTR [rbx+24]",
            "jmp interp_exit",
            f"win64_{tag}_done:",
            "mov r12, QWORD PTR [rbx+16]",
            "mov r13, QWORD PTR [rbx+24]",
            "movzx eax, BYTE PTR [r12]",
            "jmp QWORD PTR [rdi+rax*8]",
        ]

    extra_ops += [
        (
            "put_var",
            "JS_Win64PutVar",
            [
                "mov r9d, DWORD PTR [r12+1]",
                *put_var_hash(gvar_off),
                "win64_put_var_lex_probe:",
                "test ecx, ecx",
                "jz win64_put_var_global",
                "lea rax, [r11+rcx*8-8]",
                "cmp DWORD PTR [rax+4], r9d",
                "je win64_put_var_lex_found",
                "mov ecx, DWORD PTR [rax]",
                "and ecx, 67108863",
                "jmp win64_put_var_lex_probe",
                "win64_put_var_lex_found:",
                "mov edx, DWORD PTR [rax]",
                "shr edx, 26",
                f"and edx, {flags_mask}",
                f"cmp edx, {flags_writable}",
                "jne interp_slow",
                "dec ecx",
                "shl rcx, 4",
                f"mov r10, QWORD PTR [r8+{obj_prop_off}]",
                "add r10, rcx",
                "mov edx, DWORD PTR [r10+8]",
                "cmp edx, 4",
                "je interp_slow",
                "test edx, edx",
                "js interp_slow",
                "jmp win64_put_var_store",
                "win64_put_var_global:",
                *put_var_hash(gobj_off),
                "win64_put_var_obj_probe:",
                "test ecx, ecx",
                "jz interp_slow",
                "lea rax, [r11+rcx*8-8]",
                "cmp DWORD PTR [rax+4], r9d",
                "je win64_put_var_obj_found",
                "mov ecx, DWORD PTR [rax]",
                "and ecx, 67108863",
                "jmp win64_put_var_obj_probe",
                "win64_put_var_obj_found:",
                "mov edx, DWORD PTR [rax]",
                "shr edx, 26",
                f"and edx, {flags_mask}",
                f"cmp edx, {flags_writable}",
                "jne interp_slow",
                "dec ecx",
                "shl rcx, 4",
                f"mov r10, QWORD PTR [r8+{obj_prop_off}]",
                "add r10, rcx",
                "cmp DWORD PTR [r10+8], 0",
                "jl interp_slow",
                "win64_put_var_store:",
                "mov rax, QWORD PTR [r13-16]",
                "mov rdx, QWORD PTR [r13-8]",
                "mov QWORD PTR [r10], rax",
                "mov QWORD PTR [r10+8], rdx",
                "sub r13, 16",
                "add r12, 5",
                "movzx eax, BYTE PTR [r12]",
                "jmp QWORD PTR [rdi+rax*8]",
            ],
        ),
        ("for_of_next", "JS_Win64ForOfNextEntry", fast_c_op("JS_Win64ForOfNext", "forof")),
        ("array_from", "JS_Win64ArrayFromEntry", fast_c_op("JS_Win64ArrayFrom", "arrfrom")),
        ("object", "JS_Win64ObjectEntry", fast_c_op("JS_Win64Object", "obj")),
        ("define_field", "JS_Win64DefineFieldEntry", fast_c_op("JS_Win64DefineField", "deffield")),
    ]

    masm_tbl = masm_lines.index("interp_table LABEL QWORD") + 1
    gas_tbl = gas_lines.index("interp_table:") + 1
    for op_name, fn_name, _ in extra_ops:
        op_idx = opcodes.index(op_name)
        if masm_lines[masm_tbl + op_idx].strip() != "DQ interp_slow":
            raise ValueError(f"Unexpected MASM {op_name} slot: {masm_lines[masm_tbl + op_idx]}")
        masm_lines[masm_tbl + op_idx] = f"DQ {fn_name}"
        if gas_lines[gas_tbl + op_idx].strip() != ".quad interp_slow":
            raise ValueError(f"Unexpected GAS {op_name} slot: {gas_lines[gas_tbl + op_idx]}")
        gas_lines[gas_tbl + op_idx] = f".quad {fn_name}"

    def masm_inst(inst):
        m = re.match(r"^(j\w+)\s+(interp_slow|interp_exit|interp_reload)$", inst)
        if m:
            return f"{m.group(1)} NEAR PTR {m.group(2)}"
        return inst

    def float_loc_stub(op_instr):
        return [
            "cmp DWORD PTR [r8+8], 8",
            "jne interp_slow",
            "movsd xmm0, QWORD PTR [r8]",
            "cvttsd2si eax, xmm0",
            "cvtsi2sd xmm1, eax",
            "ucomisd xmm0, xmm1",
            "jne interp_slow",
            "jp interp_slow",
            op_instr,
            "jo interp_slow",
            "mov QWORD PTR [r8], rax",
            "mov QWORD PTR [r8+8], 0",
            "add r12, 2",
            "movzx eax, BYTE PTR [r12]",
            "jmp QWORD PTR [rdi+rax*8]",
        ]

    def float_tos_stub(op_instr):
        return [
            "cmp DWORD PTR [r13-8], 8",
            "jne interp_slow",
            "movsd xmm0, QWORD PTR [r13-16]",
            "cvttsd2si eax, xmm0",
            "cvtsi2sd xmm1, eax",
            "ucomisd xmm0, xmm1",
            "jne interp_slow",
            "jp interp_slow",
            op_instr,
            "jo interp_slow",
            "mov QWORD PTR [r13-16], rax",
            "mov QWORD PTR [r13-8], 0",
            "add r12, 1",
            "movzx eax, BYTE PTR [r12]",
            "jmp QWORD PTR [rdi+rax*8]",
        ]

    def float_post_stub(op_instr):
        return [
            "cmp DWORD PTR [r13-8], 8",
            "jne interp_slow",
            "movsd xmm0, QWORD PTR [r13-16]",
            "cvttsd2si eax, xmm0",
            "cvtsi2sd xmm1, eax",
            "ucomisd xmm0, xmm1",
            "jne interp_slow",
            "jp interp_slow",
            op_instr,
            "jo interp_slow",
            "xor edx, edx",
            "inc r12",
            "mov QWORD PTR [r13], rax",
            "mov QWORD PTR [r13+8], rdx",
            "add r13, 16",
            "movzx eax, BYTE PTR [r12]",
            "jmp QWORD PTR [rdi+rax*8]",
        ]

    cold_helpers = [
        (
            "JS_Win64HostExceptionResume",
            [
                "test eax, eax",
                "jz interp_reload",
                "jmp interp_exit",
            ],
        ),
        (
            "JS_Win64AddLocalStringCold",
            [
                "mov eax, DWORD PTR [r8+8]",
                "sub eax, -7",
                "cmp eax, 1",
                "ja interp_slow",
                "mov eax, DWORD PTR [r13-8]",
                "sub eax, -7",
                "cmp eax, 1",
                "ja interp_slow",
                "mov QWORD PTR [rbx], rbp",
                "mov QWORD PTR [rbx+16], r12",
                "mov QWORD PTR [rbx+24], r13",
                "mov rcx, rbx",
                "call JS_Win64AddLocalString",
                "cmp eax, 2",
                "je win64_add_local_done",
                "test eax, eax",
                "jz interp_reload",
                "mov rbp, QWORD PTR [rbx]",
                "mov r12, QWORD PTR [rbx+16]",
                "mov r13, QWORD PTR [rbx+24]",
                "jmp interp_exit",
                "win64_add_local_done:",
                "mov r12, QWORD PTR [rbx+16]",
                "mov r13, QWORD PTR [rbx+24]",
                "movzx eax, BYTE PTR [r12]",
                "jmp QWORD PTR [rdi+rax*8]",
            ],
        ),
        (
            "JS_Win64StringIndexCold",
            [
                "cmp DWORD PTR [r13-24], -7",
                "jne interp_slow",
                "mov r10, QWORD PTR [r13-32]",
                f"mov eax, DWORD PTR [r10+{str_len_byte}]",
                "and eax, 2147483647",
                "cmp DWORD PTR [r13-16], eax",
                "jae interp_slow",
                *fast_c_op("JS_Win64StringIndexStep", "stridx"),
            ],
        ),
        ("JS_Win64FloatIncLoc", float_loc_stub("add eax, 1")),
        ("JS_Win64FloatDecLoc", float_loc_stub("sub eax, 1")),
        ("JS_Win64FloatInc", float_tos_stub("add eax, 1")),
        ("JS_Win64FloatDec", float_tos_stub("sub eax, 1")),
        ("JS_Win64FloatPostInc", float_post_stub("add eax, 1")),
        ("JS_Win64FloatPostDec", float_post_stub("sub eax, 1")),
    ]

    assert masm_lines[-1].strip() == "END", "Unexpected MASM trailer"
    masm_lines.pop()
    masm_code = [".qjscold SEGMENT ALIGN(16) 'CODE'"]
    masm_pdata = [".pdata$zzqjscold SEGMENT ALIGN(4) READONLY 'DATA'"]
    gas_code = ['.section .qjscold,"xr"']
    gas_pdata = ['.section .pdata$zzqjscold,"dr"', ".p2align 2"]
    for fn_name, body in [(fn, b) for _, fn, b in extra_ops] + cold_helpers:
        masm_code += [
            f"PUBLIC {fn_name}",
            f"PUBLIC {fn_name}_end",
            f"{fn_name} PROC",
            *(masm_inst(inst) for inst in body),
            f"{fn_name}_end LABEL BYTE",
            f"{fn_name} ENDP",
        ]
        masm_pdata.append(
            f"DD IMAGEREL {fn_name}, IMAGEREL {fn_name}_end, IMAGEREL JS_FrameInterpPropertyCold_unwind"
        )
        gas_code += [
            f".globl {fn_name}, {fn_name}_end",
            f".def {fn_name}; .scl 2; .type 32; .endef",
            f"{fn_name}:",
            *body,
            f"{fn_name}_end:",
        ]
        gas_pdata.append(f".rva {fn_name}, {fn_name}_end, JS_FrameInterpPropertyCold_unwind")
    masm_code.append(".qjscold ENDS")
    masm_pdata.append(".pdata$zzqjscold ENDS")
    masm_lines += masm_code + masm_pdata + ["END"]
    gas_lines += gas_code + gas_pdata
    return masm_lines, gas_lines


def _build_foundation_c(core_path, output_dir, layout, source):
    c_match = _load_module(
        "qjs_win64_fnd_match", source / "tools/common/backports/c_source_match.py"
    )
    _prepare_win64_admission(source, output_dir, layout)
    _prepare_win64_json(source, output_dir)
    _prepare_win64_locale(source, output_dir)
    _prepare_win64_sort(source, output_dir)
    _prepare_win64_small_char(source, output_dir)
    _prepare_win64_slow_host(source, output_dir)
    original = _wire_win64_inline_properties(
        core_path.read_text(encoding="utf-8"), bool(layout.get("property_ic"))
    )
    orig_char_fn = c_match.extract_function(
        original, "static JSValue js_new_string_char(JSContext *ctx, uint16_t c)"
    )
    char_marker = "/* WIN64_OWNED_ORIGINAL_CHAR_CONSTRUCTOR */"
    original = replace_once(
        original, orig_char_fn, char_marker, "Win64 retain original js_new_string_char"
    )
    if len(re.findall(r"\bjs_new_string_char\(", original)) < 7:
        raise ValueError("Review Win64 single-character call routes")
    original = re.sub(r"\bjs_new_string_char\b", "JS_FrameSmallCharNew", original)
    original = replace_once(
        original,
        char_marker,
        "JSValue JS_FrameSmallCharNew(JSContext *, uint16_t);\n" + orig_char_fn,
        "Win64 small-char declaration and retained constructor",
    )
    free_rt_fn = c_match.extract_function(original, "void JS_FreeRuntime(JSRuntime *rt)")
    free_rt_clean = replace_once(
        free_rt_fn,
        "JS_RunGC(rt);",
        "JS_FrameSmallCharCleanupGC(rt);",
        "Win64 small-char runtime cleanup hook",
    )
    original = replace_once(
        original,
        free_rt_fn,
        "void JS_FrameSmallCharCleanupGC(JSRuntime *);\n" + free_rt_clean,
        "Win64 small-char runtime cleanup declaration",
    )
    original = replace_once(
        original,
        "    rqsort(array, pos, sizeof(*array), js_array_cmp_generic, &asc);",
        "    JS_ArrayDefaultStringSortDispatch(array, pos, sizeof(*array), js_array_cmp_generic, &asc);",
        "Win64 default string radix sort dispatch",
    )
    original = replace_once(
        original,
        "static JSValue js_array_sort(JSContext *ctx, JSValueConst this_val,",
        '#include "quickjs-win64-sort.h"\n'
        "static JSValue js_array_sort(JSContext *ctx, JSValueConst this_val,",
        "Win64 default string radix sort include",
    )
    for old_api, new_api in (
        ("JS_ParseJSON", "JS_LegacyParseJSON"),
        ("JS_JSONStringify", "JS_LegacyJSONStringify"),
    ):
        original = re.sub(r"\b" + old_api + r"\b", new_api, original)
    for old_fn, new_fn in (
        ("js_json_parse", "JS_FrameJSONParse"),
        ("js_json_stringify", "JS_FrameJSONStringify"),
    ):
        pattern = r'(JS_CFUNC_DEF\("(?:parse|stringify)",\s*\d+,\s*)' + old_fn + r"(\s*\))"
        original, count = re.subn(pattern, lambda m: m[1] + new_fn + m[2], original)
        if count != 1:
            raise ValueError("Win64 JSON builtin table route changed: " + old_fn)
    original = replace_once(
        original,
        "static const JSCFunctionListEntry js_json_funcs[] = {",
        "JSValue JS_FrameJSONParse(JSContext *, JSValueConst, int, JSValueConst *);\n"
        "JSValue JS_FrameJSONStringify(JSContext *, JSValueConst, int, JSValueConst *);\n"
        "static const JSCFunctionListEntry js_json_funcs[] = {",
        "Win64 JSON builtin declarations",
    )
    old_locale = 'JS_CFUNC_DEF("localeCompare", 1, js_string_localeCompare )'
    if original.count(old_locale) != 1:
        raise ValueError("Win64 localeCompare builtin table route changed")
    original = original.replace(
        old_locale, old_locale.replace("js_string_localeCompare", "JS_FrameLocaleCompare"), 1
    )
    original = replace_once(
        original,
        "static const JSCFunctionListEntry js_string_proto_funcs[] = {",
        "JSValue JS_FrameLocaleCompare(JSContext *, JSValueConst, int, JSValueConst *);\n"
        "static const JSCFunctionListEntry js_string_proto_funcs[] = {",
        "Win64 localeCompare declaration",
    )

    anchor = "JSValue JS_Call(JSContext *ctx,"
    if original.count(anchor) != 1:
        raise ValueError("Public JS_Call definition anchor changed")
    text = original.replace(anchor, "JSValue JS_LegacyCall(JSContext *ctx,", 1)

    definition = re.compile(r"(^static JSValue )JS_CallInternal(\([^;{}]*\)\s*\{)", re.M | re.S)
    text, count = definition.subn(r"\1JS_LegacyCallInternal\2", text)
    if count != 1:
        raise ValueError("Internal JS_CallInternal definition anchor changed")
    text = (
        "#define QJS_CVM_USE_LEGACY_CALL_INTERNAL 1\n"
        "#define QJS_CVM_FAST_NATIVE 1\n"
        "#if defined(_MSC_VER)\n"
        "#define QJS_FAST_TLS_ARRAY(type, name, count, bytes) \\\n"
        "    static __declspec(thread) type name[count]; \\\n"
        "    static inline type *name##_tls_ptr(void) { return name; }\n"
        "#define QJS_FAST_TLS_VAR(type, name, bytes) \\\n"
        "    static __declspec(thread) type name; \\\n"
        "    static inline type *name##_tls_ptr(void) { return &name; }\n"
        "#else\n"
        "#define QJS_FAST_TLS_ARRAY(type, name, count, bytes) \\\n"
        '    _Static_assert(sizeof(type) * (count) <= (bytes), #name " TLS storage too small"); \\\n'
        '    __asm__(".section .tls$QJSCACHE,\\"dw\\"\\n.p2align 4\\n" \\\n'
        '            "QJS_Win64Tls_" #name ": .space " #bytes "\\n.text\\n"); \\\n'
        "    static inline __attribute__((always_inline)) type *name##_tls_ptr(void) { \\\n"
        "        type *p; \\\n"
        '        __asm__("movq %%gs:88, %0\\n\\t" \\\n'
        '                "movl _tls_index(%%rip), %%ecx\\n\\t" \\\n'
        '                "movq (%0,%%rcx,8), %0\\n\\t" \\\n'
        '                "leaq QJS_Win64Tls_" #name "(%%rip), %%rcx\\n\\t" \\\n'
        '                "leaq _tls_start(%%rip), %%r11\\n\\t" \\\n'
        '                "subq %%r11, %%rcx\\n\\taddq %%rcx, %0" \\\n'
        '                : "=&r"(p) : : "rcx", "r11"); \\\n'
        "        return p; \\\n"
        "    }\n"
        "#define QJS_FAST_TLS_VAR(type, name, bytes) QJS_FAST_TLS_ARRAY(type, name, 1, bytes)\n"
        "#endif\n" + text
    )

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
#include "quickjs-win64-slow-host-declare.h"
#include "src/common/value/arithmetic.inc"
#ifdef QJS_PROPERTY_IC
#define QJS_WIN64_FAST_INSTANCEOF 1
#define QJS_FAST_INSTANCEOF_NO_DIRECT_DATA 1
#define QJS_FAST_INSTANCEOF_CTX_ENTRY 1
#include "src/common/value/instanceof-fast.inc"
#undef QJS_FAST_INSTANCEOF_CTX_ENTRY
#undef QJS_FAST_INSTANCEOF_NO_DIRECT_DATA
#endif
#include "quickjs-win64-loop.h"
#include "quickjs-win64-admission.h"
#include "src/common/call/quickjs-interpreter-shared.inc"
#include "src/common/call/interpreter-slow-host.inc"
#include "quickjs-win64-slow-host.h"

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
        JS_VALUE_GET_OBJ(func_obj)->class_id != JS_CLASS_BYTECODE_FUNCTION ||
        JS_VALUE_GET_OBJ(func_obj)->u.func.function_bytecode->func_kind != JS_FUNC_NORMAL ||
        FRAME_KIND(JS_VALUE_GET_OBJ(func_obj)->u.func.function_bytecode) == 2)
        return JS_LegacyCall(ctx, func_obj, this_obj, argc, argv);
    return JS_FrameCallEntryDispatch(ctx, func_obj, this_obj, JS_UNDEFINED, argc,
                                     argv, JS_CALL_FLAG_COPY_ARGV);
}

#include "quickjs-win64-json.h"
#include "quickjs-win64-locale.h"
#include "quickjs-win64-small-char.h"
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
    ap.add_argument("--gnu", action="store_true")
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
        is_gnu=args.gnu,
    )

    # 2. Generate quickjs-interpreter-slow.h (with Win64 fast instanceof, iterators, varargs, and exception walk)
    slow_mod = _load_module("qjs_win64_slow", source / "tools/x86/win64/codegen/generate-slow.py")
    iter_mod = _load_module("qjs_win64_iter", source / "tools/x86/common/codegen/iterator.py")
    varargs_mod = _load_module("qjs_win64_varargs", source / "tools/x86/common/codegen/varargs.py")
    iter_bodies, exception_loop = iter_mod.bodies(source)
    iter_bodies.pop("check_object", None)
    varargs_bodies = varargs_mod.core_bodies(source)

    loop_src = (source / "src/common/call/quickjs-interpreter-loop.inc").read_text(encoding="utf-8")
    exc_anchor = "    ret_val = JS_EXCEPTION;\nreturn_frame:"
    expanded_loop = replace_once(
        loop_src,
        exc_anchor,
        exception_loop + "\n" + exc_anchor,
        "Win64 catch/iterator-close exception marker walk",
    )
    slow_path = native_dir / "quickjs-interpreter-slow.h"
    slow_mod.generate(source, slow_path, interpreter_text=expanded_loop)
    ops_text = (source / "src/common/call/quickjs-interpreter-ops.inc").read_text(encoding="utf-8")
    ops_anchor = "        CASE(OP_instanceof):\n            sf->cur_pc = pc;"
    ops_text = replace_once(
        ops_text,
        ops_anchor,
        "        CASE(OP_instanceof):\n"
        "#if defined(QJS_WIN64_FAST_INSTANCEOF) && defined(QJS_PROPERTY_IC)\n"
        "            if (JS_FastInstanceOfContext(ctx, sp)) {\n"
        "                sp--;\n"
        "                BREAK;\n"
        "            }\n"
        "#endif\n"
        "            sf->cur_pc = pc;",
        "Win64 OP_instanceof fast path",
    )
    add_loc_old = (
        "#ifdef QJS_FRAME_LOCAL_ROPE_APPEND\n"
        "                } else if (JS_VALUE_GET_TAG(*pv) == JS_TAG_STRING_ROPE &&\n"
        "                           JS_VALUE_GET_TAG(sp[-1]) == JS_TAG_STRING) {\n"
        "                    sf->cur_pc = pc;\n"
        "                    if (js_frame_append_local_rope(ctx, pv, *--sp) < 0)\n"
        "                        goto exception;\n"
        "#endif\n"
        "                } else if (JS_VALUE_GET_TAG(*pv) == JS_TAG_STRING) {\n"
        "                    JSValue op1;\n"
        "                    op1 = sp[-1];\n"
        "                    sp--;\n"
        "                    sf->cur_pc = pc;\n"
        "                    op1 = JS_ToPrimitiveFree(ctx, op1, HINT_NONE);\n"
        "                    if (JS_IsException(op1))\n"
        "                        goto exception;\n"
        "                    op1 = JS_ConcatString(ctx, js_dup(*pv), op1);\n"
        "                    if (JS_IsException(op1))\n"
        "                        goto exception;\n"
        "                    set_value(ctx, pv, op1);"
    )
    add_loc_new = (
        "#ifdef QJS_FRAME_LOCAL_ROPE_APPEND\n"
        "                } else if (JS_VALUE_GET_TAG(*pv) == JS_TAG_STRING_ROPE &&\n"
        "                           JS_VALUE_GET_TAG(sp[-1]) == JS_TAG_STRING) {\n"
        "                    JSValue op1 = *--sp;\n"
        "                    if (JS_VALUE_GET_STRING(op1)->len == 0) {\n"
        "                        JS_FreeValue(ctx, op1);\n"
        "                    } else {\n"
        "                        sf->cur_pc = pc;\n"
        "                        if (js_frame_append_local_rope(ctx, pv, op1) < 0)\n"
        "                            goto exception;\n"
        "                    }\n"
        "#endif\n"
        "                } else if (JS_VALUE_GET_TAG(*pv) == JS_TAG_STRING) {\n"
        "                    JSValue op1;\n"
        "                    op1 = sp[-1];\n"
        "                    sp--;\n"
        "                    if (JS_VALUE_GET_TAG(op1) == JS_TAG_STRING) {\n"
        "                        JSString *p1 = JS_VALUE_GET_STRING(*pv);\n"
        "                        JSString *p2 = JS_VALUE_GET_STRING(op1);\n"
        "                        if (p2->len == 0) {\n"
        "                            JS_FreeValue(ctx, op1);\n"
        "                            BREAK;\n"
        "                        }\n"
        "                        if (JS_REF_COUNT(p1) == 1 && !p1->atom_type &&\n"
        "                            p1->kind == JS_STRING_KIND_NORMAL &&\n"
        "                            p1->is_wide_char == p2->is_wide_char &&\n"
        "                            js_malloc_usable_size(ctx, p1) >=\n"
        "                                sizeof(*p1) +\n"
        "                                    (((size_t)p1->len + (size_t)p2->len) << p1->is_wide_char) +\n"
        "                                    1 - p1->is_wide_char) {\n"
        "                            if (p1->is_wide_char) {\n"
        "                                memcpy(str16(p1) + p1->len, str16(p2),\n"
        "                                       (size_t)p2->len << 1);\n"
        "                                p1->len += p2->len;\n"
        "                            } else {\n"
        "                                memcpy(str8(p1) + p1->len, str8(p2), p2->len);\n"
        "                                p1->len += p2->len;\n"
        "                                str8(p1)[p1->len] = '\\0';\n"
        "                            }\n"
        "                            if (unlikely(p1->hash))\n"
        "                                p1->hash = 0;\n"
        "                            JS_FreeValue(ctx, op1);\n"
        "                            BREAK;\n"
        "                        }\n"
        "                        sf->cur_pc = pc;\n"
        "                        op1 = JS_ConcatString(ctx, js_dup(*pv), op1);\n"
        "                        if (JS_IsException(op1))\n"
        "                            goto exception;\n"
        "                        set_value(ctx, pv, op1);\n"
        "                        BREAK;\n"
        "                    }\n"
        "                    sf->cur_pc = pc;\n"
        "                    op1 = JS_ToPrimitiveFree(ctx, op1, HINT_NONE);\n"
        "                    if (JS_IsException(op1))\n"
        "                        goto exception;\n"
        "                    op1 = JS_ConcatString(ctx, js_dup(*pv), op1);\n"
        "                    if (JS_IsException(op1))\n"
        "                        goto exception;\n"
        "                    set_value(ctx, pv, op1);"
    )
    ops_text = replace_once(
        ops_text, add_loc_old, add_loc_new, "Win64 OP_add_loc fast string append"
    )
    extra_ops = """
        CASE(OP_regexp):
            {
                sf->cur_pc = pc;
                sp[-2] = js_regexp_constructor_internal(ctx, JS_UNDEFINED, sp[-2], sp[-1]);
                sp--;
                if (JS_IsException(sp[-1]))
                    goto exception;
            }
            BREAK;
        CASE(OP_set_name):
            {
                int ret;
                JSAtom atom;
                atom = get_u32(pc);
                pc += 4;
                sf->cur_pc = pc;
                ret = JS_DefineObjectName(ctx, sp[-1], atom, JS_PROP_CONFIGURABLE);
                if (unlikely(ret < 0))
                    goto exception;
            }
            BREAK;
        CASE(OP_set_name_computed):
            {
                int ret;
                sf->cur_pc = pc;
                ret = JS_DefineObjectNameComputed(ctx, sp[-1], sp[-2], JS_PROP_CONFIGURABLE);
                if (unlikely(ret < 0))
                    goto exception;
            }
            BREAK;
        CASE(OP_set_proto):
            {
                JSValue proto;
                proto = sp[-1];
                if (JS_IsObject(proto) || JS_IsNull(proto)) {
                    sf->cur_pc = pc;
                    if (JS_SetPrototypeInternal(ctx, sp[-2], proto, true) < 0)
                        goto exception;
                }
                sp--;
                *sp = JS_UNDEFINED;
                state->sp = sp;
                frame->saved_sp = sp;
                sf->cur_sp = sp;
                JS_FreeValue(ctx, proto);
            }
            BREAK;
        CASE(OP_copy_data_properties):
            {
                int mask;
                mask = *pc++;
                sf->cur_pc = pc;
                if (JS_CopyDataProperties(ctx, sp[-1 - (mask & 3)],
                                          sp[-1 - ((mask >> 2) & 7)],
                                          sp[-1 - ((mask >> 5) & 7)], 0))
                    goto exception;
            }
            BREAK;
        CASE(OP_check_object):
            if (unlikely(!JS_IsObject(sp[-1]))) {
                sf->cur_pc = pc;
                JS_ThrowTypeErrorNotAnObject(ctx);
                goto exception;
            }
            BREAK;
        CASE(OP_for_in_start):
            sf->cur_pc = pc;
            if (js_for_in_start(ctx, sp))
                goto exception;
            BREAK;
        CASE(OP_for_in_next):
            sf->cur_pc = pc;
            if (js_for_in_next(ctx, sp))
                goto exception;
            sp += 2;
            BREAK;
"""
    ops_text = (
        ops_text
        + extra_ops
        + "\n"
        + "\n".join(iter_bodies.values())
        + "\n"
        + "\n".join(varargs_bodies.values())
        + "\n"
    )
    for old_call, new_call in (
        (
            "js_for_of_start(ctx, sp, false)",
            "js_win64_slow_host_start(state,frame,segment,used_bytes,pc,sp,ctx,false)",
        ),
        (
            "js_for_of_next(ctx, sp, offset)",
            "js_win64_slow_host_next(state,frame,segment,used_bytes,pc,sp,ctx,offset)",
        ),
        (
            "JS_IteratorClose(ctx, sp[-1], false)",
            "js_win64_slow_host_close(state,frame,segment,used_bytes,pc,sp,ctx,sp[-1],false)",
        ),
        (
            "js_append_enumerate(ctx, sp)",
            "js_win64_slow_host_append(state,frame,segment,used_bytes,pc,sp,ctx)",
        ),
        (
            "js_function_apply(ctx, sp[-3], 2, vc(&sp[-2]), magic)",
            "js_win64_slow_host_apply(state,frame,segment,used_bytes,pc,sp,ctx,magic)",
        ),
        (
            "JS_DefineObjectNameComputed(ctx, sp[-1], sp[-2], JS_PROP_CONFIGURABLE)",
            "js_win64_slow_host_set_name_computed(state,frame,segment,used_bytes,pc,sp,ctx)",
        ),
        (
            "JS_SetPrototypeInternal(ctx, sp[-2], proto, true)",
            "js_win64_slow_host_set_proto(state,frame,segment,used_bytes,pc,sp,ctx,proto)",
        ),
        (
            "JS_CopyDataProperties(ctx, sp[-1 - (mask & 3)],\n"
            "                                          sp[-1 - ((mask >> 2) & 7)],\n"
            "                                          sp[-1 - ((mask >> 5) & 7)], 0)",
            "js_win64_slow_host_copy_data_properties(state,frame,segment,used_bytes,pc,sp,ctx,mask)",
        ),
        (
            "js_for_in_start(ctx, sp)",
            "js_win64_slow_host_for_in_start(state,frame,segment,used_bytes,pc,sp,ctx)",
        ),
        (
            "js_for_in_next(ctx, sp)",
            "js_win64_slow_host_for_in_next(state,frame,segment,used_bytes,pc,sp,ctx)",
        ),
    ):
        ops_text = replace_once(ops_text, old_call, new_call, f"Win64 coherent slow op {old_call}")
    (native_dir / "quickjs-win64-ops.inc").write_text(ops_text, encoding="utf-8", newline="\n")

    dispatch_text = (source / "src/common/call/quickjs-interpreter-dispatch.inc").read_text(
        encoding="utf-8"
    )
    for op in (
        "regexp",
        "set_name",
        "set_name_computed",
        "set_proto",
        "copy_data_properties",
        "check_object",
        "for_in_start",
        "for_in_next",
        "for_of_start",
        "for_of_next",
        "iterator_close",
        "catch",
        "gosub",
        "ret",
        "nip_catch",
        "append",
        "apply",
    ):
        dispatch_text = replace_once(
            dispatch_text,
            f"FRAME_TARGET({op}, invalid)",
            f"FRAME_TARGET({op}, OP_{op})",
            f"Win64 dispatch {op}",
        )
    (native_dir / "quickjs-win64-dispatch.inc").write_text(
        dispatch_text, encoding="utf-8", newline="\n"
    )

    slow_text = slow_path.read_text(encoding="utf-8")
    slow_text = replace_once(
        slow_text,
        '#include "src/common/call/quickjs-interpreter-dispatch.inc"',
        '#include "quickjs-win64-dispatch.inc"',
        "Win64 slow dispatch include",
    )
    slow_text = replace_once(
        slow_text,
        '#include "src/common/call/quickjs-interpreter-ops.inc"',
        '#include "quickjs-win64-ops.inc"',
        "Win64 slow ops include",
    )
    slow_text = replace_once(
        slow_text,
        "ret_val = js_frame_legacy_call(ctx, callee, call_this, call_argc, vc(call_argv));",
        "ret_val = js_frame_slow_host_call(state, frame, segment, used_bytes, pc, sp, ctx, "
        "callee, call_this, call_argc, vc(call_argv));",
        "Win64 slow host call TLS bridge",
    )
    slow_text = replace_once(
        slow_text,
        "JS_IteratorClose(ctx, sp[-1], true)",
        "js_win64_slow_host_close(state,frame,segment,used_bytes,pc,sp,ctx,sp[-1],true)",
        "Win64 exception iterator close TLS bridge",
    )
    for old_rep, new_rep, lbl_rep in (
        (
            "            JSValue val = *--sp;\n            JS_FreeValue(ctx, val);",
            "            JSValue val = *--sp;\n"
            "            *sp = JS_UNDEFINED;\n"
            "            state->sp = sp; frame->saved_sp = sp; sf->cur_sp = sp;\n"
            "            JS_FreeValue(ctx, val);",
            "Win64 exception unwind pop publication",
        ),
        (
            "                    JS_FreeValue(ctx, sp[-1]); /* drop the next method */\n"
            "                    sp--;",
            "                    JSValue consumed = *--sp;\n"
            "                    *sp = JS_UNDEFINED;\n"
            "                    state->sp = sp; frame->saved_sp = sp; sf->cur_sp = sp;\n"
            "                    JS_FreeValue(ctx, consumed);",
            "Win64 exception iterator drop publication",
        ),
        (
            "                    rt->current_exception = JS_UNINITIALIZED;\n"
            "                    JS_FreeValueRT(rt, ctx->error_back_trace);",
            "                    rt->current_exception = JS_UNINITIALIZED;\n"
            "                    state->sp = sp; frame->saved_sp = sp; sf->cur_sp = sp;\n"
            "                    JS_FreeValueRT(rt, ctx->error_back_trace);",
            "Win64 exception backtrace publication",
        ),
        (
            "    for (pval = local_buf; pval < sp; pval++)\n        JS_FreeValue(ctx, *pval);",
            "    for (pval = local_buf; pval < sp; pval++) {\n"
            "        JSValue consumed = *pval;\n"
            "        *pval = JS_UNDEFINED;\n"
            "        JS_FreeValue(ctx, consumed);\n"
            "    }",
            "Win64 return_frame consumed-slot publication",
        ),
    ):
        slow_text = replace_once(slow_text, old_rep, new_rep, lbl_rep)
    slow_path.write_text(slow_text, encoding="utf-8", newline="\n")

    # 3. Generate Win64 register VM assembly (MASM + GAS/Clang Intel syntax)
    reg_mod = _load_module(
        "qjs_win64_register", source / "tools/x86/common/codegen/generate-register.py"
    )
    append_mod = _load_module(
        "qjs_win64_append", source / "tools/x86/common/codegen/array-append.py"
    )
    reg_mod.generate(
        source,
        native_dir,
        diagnostics=False,
        internal_entry=True,
        foundation_only=True,
        numeric_compare=("QJS_FRAME_EXPERIMENTAL_COMPARE" in args.define),
        win64_native=True,
        layout_override=layout,
        array_append_body=append_mod.body,
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
    masm_lines, gas_lines = _inject_fast_ops_win64(masm_lines, gas_lines, upstream, layout)

    # 4b. Append native x86-64 coroutine fast-segment executor (JS_CVMRunFastSegment)
    cvm_mod = _load_module(
        "qjs_cvm_fast_native", source / "tools/x86/common/codegen/cvm_fast_native.py"
    )
    cvm_masm, cvm_gas, _cvm_ops = cvm_mod.emit_win64(
        source, layout, bool(layout.get("property_ic"))
    )
    if masm_lines and masm_lines[-1].strip() == "END":
        masm_lines = masm_lines[:-1] + cvm_masm + ["END"]
    else:
        masm_lines += cvm_masm
    gas_lines += cvm_gas

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
    foundation_c = _build_foundation_c(core_path, native_dir, layout, source)

    receipt = dict(
        schema=1,
        backend="WIN_X86_64",
        toolchain="gnu" if args.gnu else ("clang-cl" if args.clang_cl else "msvc"),
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
