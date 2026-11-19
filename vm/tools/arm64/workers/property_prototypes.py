"""Complete accepted prototype fill/snapshots over actual AAPCS64 types."""

import hashlib, json, re
from c_workers import module, replace_one


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def prepare(source, output, layout):
    contract = source / "src/arm64/linux/abi/property-prototypes.json"
    data = json.loads(contract.read_text())
    for name, expected in data["source_owners"].items():
        if sha(source / name) != expected:
            raise ValueError("Review prototype cache semantic owner: " + name)
    assembly = (source / "asm/arm64/common/register-property-prototypes.inc").read_text()
    calls = []
    for row in assembly.splitlines():
        code = row.split("//")[0].strip()
        if re.match(r"bl\s+", code):
            calls.append(code)
        if re.match(r"(?:blr|br|ret)\b", code) or re.search(r"\b(?:x18|w18)\b", code):
            raise ValueError("Prototype kernel must retain its direct fixed-CFA transfers: " + code)
        if re.search(r"\bsp\b", code) and code != "ldr w9, [sp, #ARM_VM_POLICY_OFF]":
            raise ValueError("Prototype kernel may only read its existing policy slot: " + code)
    if calls != ["bl JS_FrameAArch64ProtoFill"]:
        raise ValueError("Review pure prototype C boundary: " + repr(calls))
    load = (source / "src/common/kernel/proto-load.inc").read_text()
    persistent = (source / "src/common/kernel/proto-persistent.inc").read_text()
    direct = module(source, "proto-direct-c").BODY
    types = []
    for text, name in (
        (load, "JSFrameProtoHint"),
        (persistent, "JSFrameProtoPersistentHint"),
        (direct, "JSFrameProtoDirectData"),
    ):
        m = re.search(r"typedef struct " + name + r" \{.*?\} " + name + ";", text, re.S)
        if not m:
            raise ValueError("Review complete original prototype type: " + name)
        types.append(m[0])
    header = (
        "#ifndef QJS_AARCH64_PROTO_TYPES_H\n#define QJS_AARCH64_PROTO_TYPES_H\n#include <stdatomic.h>\n"
        + "\n".join(types)
        + """
extern volatile unsigned char JS_FrameProtoLoadControl,JS_FrameProtoPersistControl;
extern JSFrameProtoPersistentHint JS_FrameProtoPersistentHints[128];
extern JSFrameProtoDirectData JS_FrameProtoDirectData;
#endif
"""
    )
    (output / "interpreter-aarch64-proto-types.h").write_text(header)
    load = replace_one(
        load, types[0], '#include "interpreter-aarch64-proto-types.h"', "actual shared hint type"
    )
    persistent = replace_one(persistent, types[1], "", "actual shared persistent type")
    direct = replace_one(direct, types[2], "", "actual shared direct type")
    load = replace_one(load, "    unsigned char *state = opaque;\n", "", "typed state projection")
    load = replace_one(
        load,
        "    memcpy(&frame, state, sizeof(frame));",
        "    frame=((JSFrameRegisterState *)opaque)->frame;",
        "typed frame projection",
    )
    for textname in ("load", "persistent"):
        text = load if textname == "load" else persistent
        text = replace_one(
            text,
            "    memcpy(&pc, state + 16, sizeof(pc));",
            "    pc=((JSFrameRegisterState *)opaque)->pc;",
            "typed PC projection",
        )
        text = replace_one(
            text,
            "    memcpy(&sp, state + 24, sizeof(sp));",
            "    sp=((JSFrameRegisterState *)opaque)->sp;",
            "typed SP projection",
        )
        text = replace_one(
            text,
            "        memcpy(&b, (unsigned char *)frame + 80, sizeof(b));",
            "        b=((JSFrame *)frame)->bytecode;",
            "typed current bytecode projection",
        )
        text = text.replace(
            "native live prototype hint ABI", "actual target live prototype hint ABI"
        )
        if textname == "load":
            load = text
        else:
            persistent = text
    old = """#ifdef QJS_INTERP_FRAME_DIAGNOSTICS
    memcpy(&sites, state + 2280, sizeof(sites));
    memcpy(&next, state + 2288, sizeof(next));
#else
    memcpy(&sites, state + 144, sizeof(sites));
    memcpy(&next, state + 152, sizeof(next));
#endif"""
    load = replace_one(
        load,
        old,
        """    sites=(unsigned char *)((JSFrameRegisterState *)opaque)->sites;
    next=((JSFrameRegisterState *)opaque)->cache_next;""",
        "typed activation owner and replacement bytes",
    )
    old = """#ifdef QJS_INTERP_FRAME_DIAGNOSTICS
    memcpy(&sites, state + 2280, sizeof(sites));
#else
    memcpy(&sites, state + 144, sizeof(sites));
#endif"""
    persistent = replace_one(
        persistent,
        old,
        "    sites=(unsigned char *)((JSFrameRegisterState *)opaque)->sites;",
        "typed persistent activation projection",
    )
    persistent = replace_one(
        persistent,
        "    unsigned char *state = opaque, *sites;",
        "    unsigned char *sites;",
        "no raw opaque arithmetic",
    )
    persistent = replace_one(
        persistent,
        "        memcpy(&frame, state, sizeof(frame));",
        "        frame=((JSFrameRegisterState *)opaque)->frame;",
        "typed persistent frame projection",
    )
    persistent = replace_one(
        persistent,
        "    QJS_PROTO_LOAD_PRIMARY(primary);",
        "    primary=__atomic_load_n(&JS_FrameProtoLoadControl,__ATOMIC_ACQUIRE);",
        "actual target atomic acquire",
    )
    bodies = []
    for text in (direct, load, persistent):
        text = re.sub(
            r'__attribute__\(\(section\("[^\"]+"\)(, (?:used,)?aligned\(8\))?\)\)',
            '__attribute__((section(".data.qjs_arm_proto"),aligned(8)))',
            text,
        )
        # Direct's declaration also carries used,aligned;retain full attributes
        # while translating only the source-owned section string.
        for name in (
            ".qjzzdm$C",
            ".data$zzzzzzzzzzprotoload",
            ".qjspmet$hints",
            ".qjspmet$next",
            ".qjspmet$control",
        ):
            text = text.replace('"' + name + '"', '".data.qjs_arm_proto"')
        for decl in (
            "JSFrameProtoDirectData JS_FrameProtoDirectData=",
            "volatile unsigned char JS_FrameProtoLoadControl\n",
            "JSFrameProtoPersistentHint JS_FrameProtoPersistentHints[128]\n",
            "unsigned char JS_FrameProtoPersistentNext[64] ",
            "volatile unsigned char JS_FrameProtoPersistControl ",
        ):
            if decl in text:
                text = replace_one(
                    text,
                    decl,
                    '__attribute__((visibility("hidden"))) ' + decl,
                    "hidden same-image prototype data",
                )
        bodies.append(text)
    text = (
        """/* Complete original source algorithms;typed AAPCS64 projections. */
#include "interpreter-aarch64-proto-types.h"
#undef FRAME_CODE
#define FRAME_CODE __attribute__((visibility("hidden"),section(".text.qjs_arm_proto_cold"),noipa))
#define PROTO_LOAD_CODE FRAME_CODE
#define PROTO_PERSIST_CODE FRAME_CODE
"""
        + "\n".join(bodies)
        + """
FRAME_CODE int JS_FrameAArch64ProtoFill(JSFrameRegisterState *state)
{
#ifdef QJS_AARCH64_VM_INSTRUMENT
 ++qjs_aarch64_proto_counters[5];
#endif
 return JS_FrameProtoPersistentFill(state);
}
static __attribute__((constructor,noipa)) void js_arm_proto_startup(void)
{JS_FrameProtoDirectConfigure();}
#undef PROTO_LOAD_CODE
#undef PROTO_PERSIST_CODE
#undef FRAME_CODE
"""
    )
    if re.search(r"\b(?:JS_RunGC|JS_Call|JS_FreeValue|js_malloc|js_realloc|js_free)\s*\(", text):
        raise ValueError("Pure prototype fill must not observe JS/GC or allocate/free")
    if re.search(r"\bstate\s*\+|\b(?:2280|2288|QJS_PROTO_LOAD_PRIMARY)\b", text):
        raise ValueError("Opaque foreign state/ISA projection escaped typed conversion")
    (output / "interpreter-aarch64-proto.h").write_text(text)
    return dict(
        status="generated-not-qualified",
        source_owners=data["source_owners"],
        worker_sha256=hashlib.sha256(text.encode()).hexdigest(),
        types_sha256=hashlib.sha256(header.encode()).hexdigest(),
        pure_nonobserving_helpers=["JS_FrameAArch64ProtoFill"],
        entries=[
            "JS_FrameProtoLoadFill",
            "JS_FrameProtoPersistentFill",
            "JS_FrameProtoDirectConfigure",
            "JS_FrameAArch64ProtoFill",
            "js_arm_proto_startup",
        ],
        atomic="Complete original atomic fields/pc-release writer;ARM native acquire readers validate one captured slot+atom against current live holder",
        activation_owner="Original16x32byte JSFrameCallSite array and8replacement bytes,marker-1 disjoint from real argc",
        weak_persistent_bytes=128 * 32 + 64,
        frame_growth=0,
        state_growth=0,
        extra_strong_roots=0,
        hardware_performance_qualified=False,
    )


def finish(output, record, measured):
    keys = (
        "SIZE_JSFrameProtoHint",
        "SIZE_JSFrameProtoPersistentHint",
        "SIZE_JSFrameProtoDirectData",
        "SIZE_JSFrameCallSite",
        "CONST_FRAME_CACHE_SLOTS",
        "OFF_JSFrameRegisterState_sites",
        "OFF_JSFrameRegisterState_cache_next",
        "OFF_JSFrameProtoHint_pc",
        "OFF_JSFrameProtoHint_holder",
        "OFF_JSFrameProtoHint_atom_slot",
        "OFF_JSFrameProtoHint_marker",
    )
    record["actual_geometry"] = [measured[k] for k in keys]
    if record["actual_geometry"] != [32, 32, 48, 32, 16, 144, 152, 0, 8, 16, 24]:
        raise ValueError("Review actual prototype/shared-call-site target geometry")
    for field in ("pc", "holder", "atom_slot", "marker"):
        if (
            measured["OFF_JSFrameProtoPersistentHint_" + field]
            != measured["OFF_JSFrameProtoHint_" + field]
        ):
            raise ValueError("Persistent/activation field projection differs: " + field)
    if measured["OFF_JSFrameProtoDirectData_mode"] != 0:
        raise ValueError("Review actual direct policy mode")
    (output / "PROPERTY-PROTOTYPES.json").write_text(json.dumps(record, indent=2) + "\n")
    return record
