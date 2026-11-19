"""Complete accepted base opcode family bound to actual target types/ISA."""

import hashlib, json

OPS = (
    "or",
    "xor",
    "shl",
    "sar",
    "shr",
    "mod",
    "inc",
    "dec",
    "not",
    "neg",
    "post_inc",
    "post_dec",
    "swap",
    "get_loc0_loc1",
    "push_empty_string",
    "push_atom_value",
    "is_undefined",
    "is_null",
    "is_undefined_or_null",
    "to_propkey",
    "to_propkey2",
    "check_ctor",
)


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def probe_types(text, names, enabled):
    if not enabled:
        return text, names
    names += [
        ("CONST_" + n, n)
        for n in ("JS_ATOM_empty_string", "JS_ATOM_TYPE_STRING", "JS_ATOM_TYPE_SYMBOL")
    ]
    text += """
_Static_assert(JS_TAG_UNDEFINED==JS_TAG_NULL+1,"Original null/undefined interval");
_Static_assert(JS_TAG_INT==0,"Original integer payload guards");
_Static_assert(JS_ATOM_TYPE_SYMBOL==3,"Review original two-bit atom kinds");
__attribute__((used,section(".qjs.arm.scalar_atom"))) const JSString qjs_scalar_atom={.atom_type=JS_ATOM_TYPE_SYMBOL};
"""
    return text, names


def finish(source, output, layout, measured, elf, enabled):
    path = source / "src/arm64/linux/abi/scalar-ops.json"
    data = json.loads(path.read_text())
    for n, h in data["source_owners"].items():
        if sha(source / n) != h:
            raise ValueError("Review complete scalar opcode semantic owner: " + n)
    if enabled:
        byte, mask = layout["bits"]["JSString.atom_type"][0]
        raw = elf.section_data(elf.section(".qjs.arm.scalar_atom"))
        full = raw[byte]
        if full != mask * 3 or any(raw[:byte] + raw[byte + 1 :]):
            raise ValueError("Review complete actual atom type bitfield")
        measured.update(
            SCALAR_ATOM_TYPE_BYTE=byte,
            SCALAR_ATOM_TYPE_MASK=full,
            SCALAR_ATOM_TYPE_SHIFT=(mask & -mask).bit_length() - 1,
        )
    record = dict(
        enabled=enabled,
        opcodes=list(OPS) if enabled else [],
        source_owners=data["source_owners"],
        contract_sha256=sha(path),
        generator_sha256=sha(source / "tools/arm64/vm/scalar_ops.py"),
        asm_sha256=sha(source / "asm/arm64/common/register-scalar-ops.inc"),
        policy_sha256=sha(source / "src/arm64/linux/scalar-policy.c"),
        frame_growth=0,
        state_growth=0,
        runtime_growth=0,
        physical_VM_stack_growth=0,
        release_TLS_bytes=0,
        instrument_TLS_bytes=176 if enabled else 0,
        publication="Incoming token unchanged;all guard failures reach original observing C opcode with original PC/SP/ownership",
        whole_qualification=False,
    )
    (output / "SCALAR-OPS.json").write_text(json.dumps(record, indent=2) + "\n")
    return record
