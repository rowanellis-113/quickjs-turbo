"""Accepted length/Number controls and live method proofs over target types."""

import hashlib, json, re
from c_workers import module, replace_one


def prepare(source, output, layout):
    contract = source / "src/arm64/linux/abi/property-primitives.json"
    data = json.loads(contract.read_text())
    for name, expected in data["source_owners"].items():
        if hashlib.sha256((source / name).read_bytes()).hexdigest() != expected:
            raise ValueError("Review native primitive-property semantic owner: " + name)
    length = module(source, "length-c").BODY
    kind = re.search(r"typedef struct JSFrameLengthData \{.*?\} JSFrameLengthData;", length, re.S)
    if not kind:
        raise ValueError("Review complete shared length control type")
    types = (
        "#include <stdatomic.h>\n"
        + kind[0]
        + """
extern volatile unsigned char JS_FrameNumberPropertyControl;
void JS_FrameLengthConfigure(void);
void JS_FrameNumberPropertyConfigure(void);
"""
    )
    (output / "interpreter-aarch64-property-types.h").write_text(types)
    length = replace_one(
        length,
        kind[0],
        '#include "interpreter-aarch64-property-types.h"',
        "actual length type owner",
    )
    length = length.replace('".qjzzlm$C"', '".data.qjs_arm_properties"')
    length = replace_one(
        length,
        "JSFrameLengthData JS_FrameLengthData=",
        '__attribute__((visibility("hidden"))) JSFrameLengthData JS_FrameLengthData=',
        "owned length data",
    )
    number = (source / "src/common/kernel/number-property.inc").read_text()
    number = number.replace('".data$zzzzzzzzzznumberproperty"', '".data.qjs_arm_properties"')
    number = replace_one(
        number,
        "volatile unsigned char JS_FrameNumberPropertyControl",
        '__attribute__((visibility("hidden"))) volatile unsigned char JS_FrameNumberPropertyControl',
        "owned Number control",
    )
    text = (
        """/* Full shared control algorithms;actual AAPCS64 C,not foreign ABI. */
#undef FRAME_CODE
#define ARM_PROPERTY_CODE __attribute__((visibility("hidden"),section(".text.qjs_arm_property_cold"),noipa))
#define FRAME_CODE ARM_PROPERTY_CODE
#define NUMBER_PROPERTY_CODE ARM_PROPERTY_CODE
"""
        + length
        + "\n"
        + number
        + """
static __attribute__((constructor,noipa)) void js_arm_property_startup(void)
{JS_FrameLengthConfigure();}
#undef NUMBER_PROPERTY_CODE
#undef FRAME_CODE
#undef ARM_PROPERTY_CODE
"""
    )
    if re.search(r"\b(?:JS_RunGC|JS_Call|JS_FreeValue|js_malloc|js_realloc)\s*\(", text):
        raise ValueError("Cold property controls must not observe or mutate a JS runtime")
    (output / "interpreter-aarch64-property-primitives.h").write_text(text)
    byte, mask = layout["bits"]["JSShapeProperty.flags"][0]
    shift = byte * 8 + mask.bit_length() - 1
    if (
        mask & (mask - 1)
        or shift + 6 != 32
        or layout["sizes"]["JSShapeProperty"] != 8
        or layout["offsets"]["JSShapeProperty.atom"] != 4
    ):
        raise ValueError("Review actual source shape descriptor bit packing")
    record = dict(
        status="generated-not-qualified",
        source_owners=data["source_owners"],
        worker_sha256=hashlib.sha256(text.encode()).hexdigest(),
        types_sha256=hashlib.sha256(types.encode()).hexdigest(),
        descriptor_flags_shift=shift,
        descriptor_tmask=layout["constants"]["JS_PROP_TMASK"] << shift,
        descriptor_next_mask=(1 << shift) - 1,
        entries=[
            "JS_FrameLengthConfigure",
            "JS_FrameNumberPropertyConfigure",
            "js_arm_property_startup",
        ],
        data=["JS_FrameLengthData", "JS_FrameNumberPropertyControl"],
        pure_nonobserving_helpers=["JS_FrameNumberPropertyConfigure"],
        native="Exact flat-string/fast-array logical length and original live own/prototype data lookup with no C on hot hit",
        frame_growth=0,
        state_growth=0,
        extra_strong_roots=0,
        hardware_performance_qualified=False,
    )
    return record


def finish(output, record, measured):
    record["length_control_geometry"] = [
        measured[n]
        for n in (
            "SIZE_JSFrameLengthData",
            "OFF_JSFrameLengthData_mode",
            "NUMBER_PROPERTY_CONTROL_BYTES",
        )
    ]
    if record["length_control_geometry"] != [40, 0, 1]:
        raise ValueError("Review actual target cold property data")
    (output / "PROPERTY-PRIMITIVES.json").write_text(json.dumps(record, indent=2) + "\n")
    return record
