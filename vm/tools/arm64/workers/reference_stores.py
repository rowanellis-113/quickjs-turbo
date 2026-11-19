"""Bind original GNU reference-store and writable-own algorithms to ARM types."""

import hashlib, json, re


def generate(source, output, layout, primitives, measured):
    contract = source / "src/arm64/linux/abi/reference-stores.json"
    data = json.loads(contract.read_text())
    for name, expected in data["source_owners"].items():
        if hashlib.sha256((source / name).read_bytes()).hexdigest() != expected:
            raise ValueError("Review complete reference/property store owner: " + name)
    if layout["sizes"]["JSValue"] != 16 or layout["offsets"]["JSGCObjectHeader.ref_count"] != 0:
        raise ValueError("Reference stores require actual inline-header values")
    assembly = (source / "asm/arm64/common/register-reference-stores.inc").read_text()
    calls = re.findall(r"^\s*bl (\w+)\s*$", assembly, re.M)
    if calls != ["JS_FrameInterpFree"]:
        raise ValueError("Last release must use the original typed C/quota owner")
    if re.search(r"\b(?:blr|ret|x18|w18)\b", assembly):
        raise ValueError("Reference-store continuation changed its fixed VM CFA")
    for row in assembly.splitlines():
        code = row.split("//")[0].strip()
        if re.search(r"\bsp\b", code) and code != "ldr w9, [sp, #ARM_VM_POLICY_OFF]":
            raise ValueError("Reference stores cannot reserve or lease physical stack storage")
    shift = primitives["descriptor_flags_shift"]
    flags = layout["constants"]
    mask = (flags["JS_PROP_TMASK"] | flags["JS_PROP_WRITABLE"] | flags["JS_PROP_LENGTH"]) << shift
    writable = flags["JS_PROP_WRITABLE"] << shift
    measured["PROPERTY_DESC_WRITE_MASK"] = mask
    measured["PROPERTY_DESC_WRITABLE"] = writable
    record = dict(
        status="generated-not-qualified",
        source_owners=data["source_owners"],
        source_contract_sha256=hashlib.sha256(contract.read_bytes()).hexdigest(),
        source_generator_sha256=hashlib.sha256(
            (source / "tools/arm64/workers/reference_stores.py").read_bytes()
        ).hexdigest(),
        descriptor_geometry=[shift, mask, writable],
        last_release="Duplicate or transfer incoming;commit slot,next PC/SP and private/public frame view;original typed Free;no slot rewrite after reentry",
        generic_property="Complete accepted GNU live writable/plain/nonlength own hash;referenced old values retain C as in the accepted GNU foundation",
        observing_helper="JS_FrameInterpFree",
        new_C_helpers=0,
        control="Existing QJS_DISABLE_NATIVE_SLOT_STORE process-presence ARM policy,including0;separate QJS_DISABLE_AARCH64_PROPERTY_STORES for generic own put",
        new_frame_bytes=0,
        new_state_bytes=0,
        new_runtime_fields=0,
        new_strong_roots=0,
        instrument_only_tls_bytes=64,
        hardware_performance_qualified=False,
    )
    (output / "REFERENCE-STORES.json").write_text(json.dumps(record, indent=2) + "\n")
    return record
