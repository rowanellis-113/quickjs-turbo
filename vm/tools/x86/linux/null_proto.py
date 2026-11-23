"""Carry the accepted null-prototype classifier and ordinary allocator to SysV.

The original C allocator algorithm is shared, not reimplemented. The register
VM uses its existing typed, coherent state bridge and unchanged CFA/ownership.
"""

import sys as _x86_sys
from pathlib import Path as _X86Path

if str(_X86Path(__file__).resolve().parents[2]) not in _x86_sys.path:
    _x86_sys.path.insert(0, str(_X86Path(__file__).resolve().parents[2]))
from x86.common.paths_x86 import source_file
import hashlib, json
from c_workers import module, replace_one

OWNERS = (
    "tools/x86/common/codegen/null-proto.py",
    "tools/x86/common/codegen/null-arena.py",
    "asm/x86/win64/mingw64/mingw-arguments_entry.S",
)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def contract(source):
    data = json.loads((source / "src/x86/linux/abi/null-proto.json").read_text())
    for name, value in data["owners"].items():
        if sha(source_file(source, name)) != value:
            raise ValueError("Review null-prototype owner: " + name)
    return data


def admission(source, original, *, retained_captured_classifier=True):
    contract(source)
    signature = "static FRAME_CODE bool js_frame_validate(JSFunctionBytecode *b)"
    text = replace_one(
        original,
        signature,
        "static LINUX_ADMISSION_CODE bool js_linux_validate_null_body(JSFunctionBytecode *b)",
        "null classifier actual original signature",
    )
    text = replace_one(
        text,
        "bool captured_args = false;",
        "bool captured_args = false;\n    bool seen_null = false;",
        "null classifier state",
    )
    anchor = """            break;
        default:
            return false;
"""
    text = replace_one(
        text,
        anchor,
        """            break;
        case OP_special_object:
            if (code[pos + 1] != OP_SPECIAL_OBJECT_NULL_PROTO) return false;
            seen_null = true;
            break;
        default:
            return false;
""",
        "complete inherited null-only opcode extension",
    )
    text = replace_one(
        text,
        "    FRAME_KIND(b) = (captured_args",
        "    if (!seen_null) return false;\n    FRAME_KIND(b) = (captured_args",
        "null cohort admission",
    )
    text = replace_one(
        text,
        "(b->var_ref_count ? 8 : 0);",
        "(b->var_ref_count ? 8 : 0) | 32;",
        "inherited null-only metadata bit",
    )
    # Linux's actual base already calls the common readonly-capture proof.
    # Retain it in the derived classifier, including its original field owner.
    assert text.count("JS_LinuxCapturedReadonlyClassify(b);") == int(retained_captured_classifier)
    text += """
LINUX_ADMISSION_CODE bool JS_LinuxValidateNativeNull(JSFunctionBytecode *b)
{
    JSRuntime *rt=b->realm->rt;
    unsigned char *mode;
    if (FRAME_STATE(rt)!=1 || !js_frame_register_enabled(rt)) return false;
#ifdef ENABLE_DUMPS
    if (check_dump_flag(rt,JS_DUMP_BYTECODE_STEP)) return false;
#endif
    _Static_assert(offsetof(JSRuntime,module_loader_has_attr)+2<offsetof(JSRuntime,u),
                   "null admission uses its original measured padding");
    mode=(unsigned char *)rt+offsetof(JSRuntime,module_loader_has_attr)+2;
    if (!*mode) *mode=getenv("QJS_DISABLE_NATIVE_NULL_PROTO")==NULL ? 1 : 2;
    return *mode==1 && js_linux_validate_null_body(b);
}
"""
    return text


def append(source, output, blocks, layout):
    data = contract(source)
    if layout["reference_count_model"] not in ("inline-header", "allocator-prefix"):
        raise ValueError("Review null-object reference model")
    rows = next(rows for name, rows in blocks if name == "JS_FrameArgumentsOpClean")
    text = "\n".join(rows)
    assert text.count("jne interp_slow") == 2
    rows[:] = text.replace("jne interp_slow", "jne JS_FrameLinuxNullProtoOpcode").splitlines()
    from admission import vm_block

    body = [r.replace("JS_FrameInterpRegExp", "JS_FrameLinuxNullProtoStep") for r in vm_block()]
    record = dict(
        status="generated-not-qualified",
        owners=data["owners"],
        functions=["JS_FrameLinuxNullProtoOpcode"],
        original_argument_decline_edges=2,
        native_C_boundary="existing typed state-only SysV bridge and deferred publication factory",
        frame_growth=0,
        state_growth=0,
        new_strong_roots=0,
        scope="Complete ordinary null-prototype VM entry;argument-owned special objects retain their original worker",
    )
    (output / "NULL-PROTO-VM.json").write_text(json.dumps(record, indent=2) + "\n")
    return [("JS_FrameLinuxNullProtoOpcode", body)], record


def generate(source, output, core, layout, *, admission_header="quickjs-linux-admission.h"):
    data = contract(source)
    prefix_rc = layout["reference_count_model"] == "allocator-prefix"
    if layout["reference_count_model"] not in ("inline-header", "allocator-prefix") or (
        not prefix_rc and layout["offsets"]["JSGCObjectHeader.ref_count"] != 0
    ):
        raise ValueError("Review null-object inline-header ownership")
    common = module(source, "null-arena")
    body = common.generate_body(source)
    assert body.count("FRAME_NULL_CODE JSValue JS_FrameNewNullObject(") == 1
    if not prefix_rc:
        assert body.count("extern void qjs_frame_core_js_free_shape0(JSRuntime *, JSShape *);") == 1
        body = body.replace(
            "extern void qjs_frame_core_js_free_shape0(JSRuntime *, JSShape *);", ""
        )
        body = body.replace("qjs_frame_core_js_free_shape0", "js_free_shape0")
    body = body.replace("JS_FrameNewNullObject", "JS_LinuxNewNullObject")
    if not prefix_rc:
        body = replace_one(
            body,
            "    p->is_prototype = 0;",
            "    p->__gc_mark = 0;\n    p->is_prototype = 0;",
            "null-object birth initializes the inline storage bit to zero",
        )
        body = replace_one(
            body,
            "QJS_ABI_HAS_PREFIX_RC == 0 && QJS_ABI_REF_COUNT_OFFSET == 0",
            "offsetof(JSObject,header.ref_count)==0 && offsetof(JSShape,header.ref_count)==0",
            "actual same-TU inline ownership assertion",
        )
    assert "QJS_ABI_" not in body
    platform = source / "src/common/linux/interpreter-null-proto.inc"
    from arguments import scoped

    wrapper = scoped(source, "js_linux_null_proto_body", "JS_FrameLinuxNullProtoStep")
    wrapper = wrapper.replace("FRAME_CODE", "QJS_LINUX_NULL_CODE")
    header = (
        """/* Generated from the accepted null allocator and actual Linux types. */
#define FRAME_NULL_CODE __attribute__((section(".text.qjs_linux_null_proto"),noipa))
#define FRAME_NULL_INLINE __attribute__((always_inline)) inline
#define QJS_LINUX_NULL_CODE FRAME_NULL_CODE
"""
        + body
        + """
_Static_assert(__builtin_types_compatible_p(__typeof__(&JS_LinuxNewNullObject),
               __typeof__(&JS_NewObjectProtoClass)),"actual SysV JSValue allocation ABI");
#include "src/common/linux/interpreter-null-proto.inc"
"""
        + wrapper
        + """
#undef QJS_LINUX_NULL_CODE
#undef FRAME_NULL_CODE
#undef FRAME_NULL_INLINE
"""
    )
    path = output / "quickjs-linux-null-proto.h"
    path.write_text(header)
    record = dict(
        status="generated-not-qualified",
        owners=data["owners"],
        source_files={
            n: sha(source_file(source, n))
            for n in (
                "tools/x86/linux/null_proto.py",
                "tools/x86/linux/admission.py",
                "src/common/linux/interpreter-null-proto.inc",
                "src/common/call/interpreter-slow-host.inc",
            )
        },
        generated_sha256=sha(path),
        common_allocator_sha256=hashlib.sha256(common.generate_body(source).encode()).hexdigest(),
        adapted_allocator_sha256=hashlib.sha256(body.encode()).hexdigest(),
        admission_sha256=sha(output / admission_header),
        entries=[
            "JS_LinuxNewNullObject",
            "JS_FrameLinuxNullProtoStep",
            "js_linux_null_proto_body",
            "JS_LinuxValidateNativeNull",
            "js_linux_validate_null_body",
        ],
        frame_growth=0,
        state_growth=0,
        new_strong_roots=0,
        per_runtime_heap_growth=0,
        mode_padding=layout["offsets"]["JSRuntime.module_loader_has_attr"] + 2,
        allocator_control_padding=layout["offsets"]["JSRuntime.module_loader_has_attr"] + 6,
        scope="Original warm shape/GC/malloc/initialization/failure ownership;SysV C aggregates and coherent VM scope",
    )
    (output / "NULL-PROTO.json").write_text(json.dumps(record, indent=2) + "\n")
    return core + '\n#include "quickjs-linux-null-proto.h"\n'
