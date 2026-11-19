"""Ordinary constructor policy and ABI metadata;complete executor is shared."""

import hashlib, json
from pathlib import Path


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def prepare(source, output, enabled):
    contract = source / "src/arm64/linux/abi/constructors.json"
    data = json.loads(contract.read_text())
    for name, expected in data["source_owners"].items():
        if sha(source / name) != expected:
            raise ValueError("Review complete constructor/cleanup owner: " + name)
    record = dict(
        status="generated-not-qualified",
        enabled=enabled,
        source_owners=data["source_owners"],
        contract_sha256=sha(contract),
        generator_sha256=sha(source / "tools/arm64/workers/constructors.py"),
        observing_helpers=[
            "JS_FrameInterpProperty_call_constructor",
            "JS_FrameVarargsConstructHeapReturn",
        ]
        if enabled
        else [],
        entries=[
            "JS_FrameInterpProperty_call_constructor",
            "JS_FrameVarargsConstructCall",
            "JS_FrameVarargsConstructHeapReturn",
            "js_linux_construct_host_create",
        ]
        if enabled
        else [],
        new_logical_static_bytes=4 if enabled else 0,
        instrument_only_TLS_bytes=64,
        new_frame_fields=0,
        new_state_fields=0,
        new_runtime_fields=0,
        new_strong_roots=0,
        constructor_root=3,
        full_native_iterator_apply_family=False,
        hardware_performance_qualified=False,
    )
    return record
