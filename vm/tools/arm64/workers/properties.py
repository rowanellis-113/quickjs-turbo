"""Bind native AArch64 by-id PICs to the actual common cache/type owners."""

import hashlib, json, re


def generate(source, output, layout, enabled):
    path = source / "src/arm64/linux/abi/properties.json"
    contract = json.loads(path.read_text())
    for name, expected in contract["source_owners"].items():
        if hashlib.sha256((source / name).read_bytes()).hexdigest() != expected:
            raise ValueError("Review actual native property/cache owner: " + name)
    assembly = (source / "asm/arm64/common/register-property-ic.inc").read_text()
    labels = set(re.findall(r"^(\.L\w+):", assembly, re.M)) | {
        ".Lslow",
        ".Lfast",
        ".Lproperty_method_legacy",
        ".Lproperty_method_live",
        ".Lproperty_pic_slow",
        ".Lproperty_own_try",
        ".Lproperty_own_put",
    }
    for row in assembly.splitlines():
        code = row.split("//")[0].strip()
        if re.match(r"(?:bl|blr|br|ret)\b", code):
            raise ValueError("Native PIC must not call or grow the VM stack: " + code)
        if re.search(r"\bsp\b", code) and code != "ldr w9, [sp, #ARM_VM_POLICY_OFF]":
            raise ValueError("Native PIC may only read its existing policy stack slot: " + code)
        branch = re.fullmatch(r"(?:b(?:\.\w+)?|cbz|cbnz|tbz|tbnz)\s+(.+)", code)
        if branch and branch[1].split(",")[-1].strip() not in labels:
            raise ValueError("Native PIC transfer escapes its original VM continuation: " + code)
    if "ARM_PROPERTY_COUNTER_" in assembly:
        raise ValueError("Unexpanded source counter marker")
    record = dict(
        status="generated-not-qualified",
        enabled=enabled,
        source_contract_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        source_owners=contract["source_owners"],
        architecture="aarch64",
        handlers=["get_field", "get_field2", "put_field"] if enabled else [],
        native_ways=4,
        callee_abi="No call;actual VM cached registers and inherited FDE",
        ownership="Duplicate before receiver release;replace declines any last owner;activate successor prototype before weakening predecessor",
        misses="Original unchanged PC/SP and all owners;typed original C learner/publication",
        exclusions="Growth requiring allocation,more than4 ways,exotics,accessors,dictionary shapes and last release retain original owners",
        frame_growth=0,
        state_growth=0,
        extra_strong_roots=0,
        hardware_performance_qualified=False,
    )
    if enabled:
        for name, size in (
            ("JSValue", 16),
            ("JSProperty", 16),
            ("JSPropertyICWay", 40),
            ("JSPropertyICSite", 64),
        ):
            if layout["sizes"][name] != size:
                raise ValueError("Review actual property stride: " + name)
        record["actual_types"] = {
            name: layout["sizes"][name]
            for name in (
                "JSValue",
                "JSProperty",
                "JSPropertyICWay",
                "JSPropertyICSite",
                "JSPropertyIC",
            )
        }
        record["actual_offsets"] = {
            name: value
            for name, value in layout["offsets"].items()
            if name.startswith(("JSPropertyIC", "JSShape.", "JSObject."))
        }
        record["actual_bits"] = {
            name: layout["bits"][name]
            for name in ("JSObject.is_exotic", "JSObject.is_prototype", "JSObject.extensible")
        }
    (output / "PROPERTIES.json").write_text(json.dumps(record, indent=2) + "\n")
    return record
