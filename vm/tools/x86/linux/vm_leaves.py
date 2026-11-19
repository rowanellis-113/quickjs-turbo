"""Use the complete shared VM primitive/compound/character leaf factories."""

import hashlib
import json
from c_workers import module


def append(source, output, stream, layout, property_ic):
    generator = module(source, "leaf-entry")
    ids = generator.checked_opcodes(source)
    rows = stream["call_code"]
    original = "jne interp_meta_unready"
    if rows.count(original) != 1:
        raise ValueError("Review the original prepared-metadata readiness edge")
    rows[rows.index(original)] = "jne JS_FrameLeafGuard"
    kernel = generator.leaf_kernel(ids, False, "interp_meta_unready")
    if property_ic:
        kernel = generator.character_set_kernel(ids, generator.compound_kernel(ids, kernel))
    # There is one real Linux dispatch table. Deferred publish-table selection
    # is its own migration group; preserve the current owned value consumer.
    kernel += [
        "jmp interp_release_values",
        "JS_FrameLeafReject:",
        "mov rdx, QWORD PTR [r8-16]",
        "jmp interp_meta_ready",
        "JS_FrameLeafUnready:",
        f"movzx eax, BYTE PTR [r9+{layout['offsets']['JSFunctionBytecode.byte_code_buf'] - 1}]",
        "and eax, 21",
        "jmp interp_meta_unready",
    ]
    # The returning forward probe is separate. These are direct JMP blocks
    # inside the existing VM activation and use that activation's CFA144.
    record = dict(
        status="generated-not-qualified",
        source="tools/x86/common/codegen/leaf-entry.py",
        source_sha256=hashlib.sha256(
            (source / "tools/x86/common/codegen/leaf-entry.py").read_bytes()
        ).hexdigest(),
        policy_sha256=hashlib.sha256(
            (source / "src/x86/linux/interpreter-vm-leaf.inc").read_bytes()
        ).hexdigest(),
        assembly_rows_sha256=hashlib.sha256(("\n".join(kernel) + "\n").encode()).hexdigest(),
        primitive=True,
        compound=bool(property_ic),
        character_set=bool(property_ic),
        entry="JS_FrameLeafGuard",
        result="XMM0/original finalizer-safe caller consumer",
        positive_metadata="Existing three unused flag bits;bit16 intentionally clear",
        frame_growth=0,
        extra_GC_roots=0,
        qualification="Exact immutable bytecode patterns,live arity/type/realm/arena/quota/poll guards;original metadata fallback and ownership",
        scope="Full shared primitive/compound/character kernels;constructor and deferred dispatch remain separate",
    )
    (output / "VM-LEAVES.json").write_text(json.dumps(record, indent=2) + "\n")
    controls = ["JS_FrameLeafControl"]
    if property_ic:
        controls += ["JS_FrameCompoundControl", "JS_FrameCharacterSetControl"]
    return [("JS_FrameLinuxVMLeaves", kernel)], controls, record
