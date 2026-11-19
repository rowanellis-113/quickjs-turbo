"""Complete shared array copy/sort C owners over actual AAPCS64 types."""

import hashlib, json
from c_workers import module


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def generate(source, output, core, enabled):
    path = source / "src/arm64/linux/abi/array-workers.json"
    contract = json.loads(path.read_text())
    for name, expected in contract["source_owners"].items():
        if sha(source / name) != expected:
            raise ValueError("Review complete array/sort source owner: " + name)
    if enabled:
        from array_workers import generate as shared

        core, record = shared(
            source,
            output,
            core,
            module(source, "object-adapter-c"),
            include_dense=False,
            include_append=False,
            stack_pointer_stmt='__asm__ volatile("mov %0, sp" : "=r"(sp));',
        )
        record["entries"].append("JS_FrameLinuxPreparedSortProbe")
        record["architecture"] = "aarch64"
        record["enabled"] = True
        record["private_core_type_mirrors"] = False
        record["public_abi"] = "actual GCC AAPCS64 aggregate and five-argument rqsort C"
    else:
        (output / "quickjs-linux-arrays.h").write_text(
            "/* Array copy/sort compiled OFF;inherited pop retained. */\n"
        )
        record = dict(status="compiled-off", enabled=False, entries=[])
    record.update(
        source_owners=contract["source_owners"],
        source_contract_sha256=sha(path),
        generator_sha256=sha(source / "tools/arm64/workers/array_workers.py"),
        header_sha256=sha(output / "quickjs-linux-arrays.h"),
        new_frame_fields=0,
        new_state_fields=0,
        new_runtime_fields=0,
        native_append_complete=False,
        whole_qualification=False,
    )
    (output / "ARRAY-WORKERS.json").write_text(json.dumps(record, indent=2) + "\n")
    return core, record
