"""Complete original null-prototype cohort and allocator over actual ARM types."""

import hashlib, json
from admission_c import one
from null_proto_c import admission as shared_admission, generate as shared_generate


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def check(source):
    path = source / "src/arm64/linux/abi/null-proto.json"
    data = json.loads(path.read_text())
    for name, expected in data["source_owners"].items():
        if sha(source / name) != expected:
            raise ValueError("Review complete null-prototype owner: " + name)
    return path, data


def classifier(source, output, original):
    check(source)
    # Remove only the independently added ARM THIS_FUNC case, then derive the
    # original GNU NULL_PROTO-only cohort using its complete shared factory.
    # The old THIS_FUNC classifier remains the first path, unchanged.
    special = """        case OP_special_object:
            if (code[pos+1]!=OP_SPECIAL_OBJECT_THIS_FUNC) return false;
            break;
"""
    base = one(original, special, "")
    retained = base.count("JS_AArch64CapturedReadonlyClassify(b);")
    if retained not in (0, 1):
        raise ValueError("Review original optional captured classifier")
    base = base.replace("JS_AArch64CapturedReadonlyClassify", "JS_LinuxCapturedReadonlyClassify")
    text = shared_admission(source, base, retained_captured_classifier=bool(retained))
    return text.replace("LINUX_ADMISSION_CODE", "AARCH64_ADMISSION_CODE").replace(
        "JS_LinuxCapturedReadonlyClassify", "JS_AArch64CapturedReadonlyClassify"
    )


def generate(source, output, core, layout, enabled):
    path, data = check(source)
    if enabled:
        if (
            layout["offsets"]["JSMallocBlockHeader.ref_count"]
            - layout["offsets"]["JSMallocBlockHeader.user_data"]
        ) != -4:
            raise ValueError("Review actual ARM allocator-prefix reference-count header")
        actual_layout = dict(layout, reference_count_model="allocator-prefix")
        core = shared_generate(
            source, output, core, actual_layout, admission_header="interpreter-aarch64-admission.h"
        )
        record = json.loads((output / "NULL-PROTO.json").read_text())
        record["enabled"] = True
        record["architecture"] = (
            "AAPCS64;actual JSValue aggregate,typed state-only C opcode boundary"
        )
    else:
        (output / "quickjs-linux-null-proto.h").write_text(
            "/* Native null-prototype cohort compiled OFF. */\n"
        )
        record = dict(enabled=False, entries=[], frame_growth=0, state_growth=0, new_strong_roots=0)
    record.update(
        source_owners=data["source_owners"],
        source_contract_sha256=sha(path),
        generator_sha256=sha(source / "tools/arm64/workers/null_proto.py"),
        generated_sha256=sha(output / "quickjs-linux-null-proto.h"),
        whole_qualification=False,
        hardware_performance_qualified=False,
    )
    (output / "NULL-PROTO.json").write_text(json.dumps(record, indent=2) + "\n")
    return core, record
