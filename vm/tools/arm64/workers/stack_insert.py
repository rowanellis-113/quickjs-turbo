"""Bind the complete accepted insert3 owner to actual AAPCS64 fields."""

import hashlib, json, re


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def generate(source, output, core, enabled):
    path = source / "src/arm64/linux/abi/stack-insert.json"
    contract = json.loads(path.read_text())
    for n, h in contract["source_owners"].items():
        if sha(source / n) != h:
            raise ValueError("Review complete stack-insert source owner: " + n)
    original = (source / "src/common/call/quickjs-interpreter-ops.inc").read_text()
    blocks = re.findall(
        r"        CASE\(OP_insert3\):.*?(?=        CASE\(OP_insert4\):)", original, re.S
    )
    if len(blocks) != 1:
        raise ValueError("Review exact original insert3 ownership")
    if enabled:
        core += '\n_Static_assert(offsetof(JSFrameSlowDirectData,mode)==ARM_OFF_JSFrameSlowDirectData_mode,"actual existing policy mode");\n'
        core += """
#ifdef QJS_AARCH64_VM_INSTRUMENT
__thread uint64_t qjs_aarch64_stack_insert_counter __attribute__((visibility("hidden"),tls_model("local-exec")));
__attribute__((visibility("hidden"),noipa)) uint64_t qjs_aarch64_vm_stack_insert_count(void){return qjs_aarch64_stack_insert_counter;}
#endif
"""
    record = dict(
        enabled=enabled,
        source_owners=contract["source_owners"],
        contract_sha256=sha(path),
        generator_sha256=sha(source / "tools/arm64/workers/stack_insert.py"),
        original_opcode_sha256=hashlib.sha256(blocks[0].encode()).hexdigest(),
        frame_growth=0,
        state_growth=0,
        runtime_growth=0,
        release_TLS_bytes=0,
        instrument_TLS_bytes=8 if enabled else 0,
        heap_owners="One original duplicate,zero allocation or final release",
        publication="Incoming original/Clean/Dirty token unchanged;disabled route reaches its original C owner",
        whole_qualification=False,
    )
    (output / "STACK-INSERT.json").write_text(json.dumps(record, indent=2) + "\n")
    return core, record
