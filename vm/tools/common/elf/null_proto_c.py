"""Shared C null-prototype classifier and arena allocator generator."""

import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from common.paths import source_file
from c_workers import module, replace_one


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def contract(source, *, contract_rel=None):
    if contract_rel is None:
        return {"owners": {}}
    data = json.loads((source / contract_rel).read_text())
    owners = data.get("owners") or data.get("source_owners") or {}
    for name, value in owners.items():
        if sha(source_file(source, name)) != value:
            raise ValueError("Review null-prototype owner: " + name)
    return data


def admission(source, original, *, retained_captured_classifier=True, contract_rel=None):
    contract(source, contract_rel=contract_rel)
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


def generate(
    source,
    output,
    core,
    layout,
    *,
    admission_header="quickjs-linux-admission.h",
    platform_binding="src/common/linux/interpreter-null-proto.inc",
    contract_rel=None,
):
    data = contract(source, contract_rel=contract_rel)
    ref_model = layout["reference_count_model"]
    if ref_model == "inline-header":
        if layout["offsets"]["JSGCObjectHeader.ref_count"] != 0:
            raise ValueError("Review null-object inline-header ownership")
    elif ref_model == "allocator-prefix":
        if (
            layout["offsets"]["JSMallocBlockHeader.ref_count"]
            - layout["offsets"]["JSMallocBlockHeader.user_data"]
            != -4
        ):
            raise ValueError("Review null-object allocator-prefix ownership")
    else:
        raise ValueError("Review null-object reference-count model")
    common = module(source, "null-arena-c")
    body = common.generate_body(source, reference_count_model=ref_model)
    assert body.count("FRAME_NULL_CODE JSValue JS_FrameNewNullObject(") == 1
    if ref_model == "inline-header":
        assert body.count("extern void qjs_frame_core_js_free_shape0(JSRuntime *, JSShape *);") == 1
        body = body.replace(
            "extern void qjs_frame_core_js_free_shape0(JSRuntime *, JSShape *);", ""
        )
        body = body.replace("qjs_frame_core_js_free_shape0", "js_free_shape0")
        body = replace_one(
            body,
            "QJS_ABI_HAS_PREFIX_RC == 0 && QJS_ABI_REF_COUNT_OFFSET == 0",
            "offsetof(JSObject,header.ref_count)==0 && offsetof(JSShape,header.ref_count)==0",
            "actual same-TU inline ownership assertion",
        )
    body = body.replace("JS_FrameNewNullObject", "JS_LinuxNewNullObject")
    assert "QJS_ABI_" not in body
    platform = source / platform_binding
    from arguments_c import scoped

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
               __typeof__(&JS_NewObjectProtoClass)),"actual native JSValue allocation ABI");
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
            n: sha(source / n)
            for n in (
                "tools/common/elf/null_proto_c.py",
                "tools/common/elf/admission_c.py",
                platform_binding,
                "src/common/call/interpreter-slow-host.inc",
            )
        },
        generated_sha256=sha(path),
        common_allocator_sha256=hashlib.sha256(
            common.generate_body(source, reference_count_model=ref_model).encode()
        ).hexdigest(),
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
        scope="Original warm shape/GC/malloc/initialization/failure ownership;native C aggregates and coherent VM scope",
    )
    (output / "NULL-PROTO.json").write_text(json.dumps(record, indent=2) + "\n")
    return core + '\n#include "quickjs-linux-null-proto.h"\n'
