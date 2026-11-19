"""Accepted GNU iterator/checkpoint algorithm with actual AAPCS64 boundaries."""

import hashlib, json
from pathlib import Path
from c_workers import module, replace_one
from iterators_c import contract as shared_contract, generate as shared_generate
from admission_c import function


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def event(index):
    return (
        "#ifdef QJS_AARCH64_VM_INSTRUMENT\n    ++qjs_aarch64_iterator_counters["
        + str(index)
        + "];\n#endif\n"
    )


def prepare(source, output, enabled):
    contract = source / "src/arm64/linux/abi/iterators.json"
    data = json.loads(contract.read_text())
    shared = shared_contract(source)
    for name, expected in data["source_owners"].items():
        if sha(source / name) != expected:
            raise ValueError("Review ARM iterator owner: " + name)
    ops = list(module(source, "iterator-c").OPS)
    helpers = ["JS_LinuxIterator_" + n for n in ops]
    record = dict(
        status="generated-not-qualified",
        enabled=enabled,
        opcodes=ops,
        source_owners=data["source_owners"],
        contract_sha256=sha(contract),
        generator_sha256=sha(source / "tools/arm64/workers/iterators.py"),
        observing_helpers=helpers if enabled else [],
        entries=(
            helpers
            + ["js_linux_iterator_" + n + "_body" for n in ops]
            + [
                "JS_FrameIteratorCheckpointPush",
                "JS_FrameIteratorCheckpointValue",
                "JS_FrameIteratorCheckpointOp",
                "JS_FrameIteratorCheckpointAdmit",
                "JS_FrameIteratorCheckpointSelect",
                "JS_FrameIteratorOp_for_of_next",
                "JS_FrameIteratorArrayNext",
                "JS_FrameIteratorSlowNext",
            ]
        )
        if enabled
        else [],
        metadata_bits=shared["metadata_bits"],
        new_frame_fields=0,
        new_state_fields=0,
        new_runtime_fields=0,
        new_strong_roots=0,
        instrument_only_TLS_bytes=128,
        native_apply_spread_literal_parity=False,
        hardware_performance_qualified=False,
    )
    return record


def extend_stage(source, stage, layout, record):
    if not record["enabled"]:
        return
    shared_generate(source, stage, layout)
    record["shared_factory_record"] = json.loads((stage / "ITERATORS.json").read_text())


def observe_stage(text, record):
    if not record["enabled"]:
        return text
    signature = "FRAME_CODE int JS_FrameIteratorCheckpointPush(JSFrameRegisterState *state)\n{"
    text = replace_one(
        text, signature, signature + "\n" + event(8), "natural admitted next push attempts"
    )
    signature = "FRAME_CODE int JS_FrameIteratorCheckpointOp(JSFrameRegisterState *state)\n{"
    part = function(text, signature)
    replacement = replace_one(
        part,
        "    if(FRAME_CHECKPOINT(frame)) {",
        "    if(FRAME_CHECKPOINT(frame)) {\n" + event(9),
        "actual paused result consumption",
    )
    text = replace_one(text, part, replacement, "actual checkpoint continuation owner")
    for name, index in [("JS_FrameIteratorArrayNext", 10), ("JS_FrameIteratorSlowNext", 11)]:
        args = (
            "JSFrameRegisterState *state"
            if index == 10
            else "JSContext *ctx,JSValue *sp,int offset"
        )
        part = function(text, "FRAME_CODE int " + name + "(" + args + ")\n{")
        replacement = replace_one(
            part,
            "    return 0;",
            "    " + event(index).lstrip() + "    return 0;",
            "natural dense-array success",
        )
        text = replace_one(text, part, replacement, "accepted dense-array owner observation")
    text += "\n" + "".join(
        "_Static_assert(__builtin_types_compatible_p(__typeof__(&"
        + name
        + '),int (*)(JSFrameRegisterState *)),"Actual typed iterator opcode ABI");\n'
        for name in record["observing_helpers"]
    )
    return text


def observe_host(text, record):
    if not record["enabled"]:
        return text
    for i, name in enumerate(record["observing_helpers"]):
        part = function(
            text, "QJS_FRAME_SLOW_HOST_CODE int " + name + "(JSFrameRegisterState *state)\n{"
        )
        start = part.index("{")
        text = replace_one(
            text,
            part,
            part[: start + 1] + "\n" + event(i) + part[start + 1 :],
            "typed iterator observing boundary " + name,
        )
    return text
