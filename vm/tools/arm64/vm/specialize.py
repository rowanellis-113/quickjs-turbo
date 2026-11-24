"""Specialize the AArch64 register VM for Release fast paths (`QJS_AARCH64_FAST_VM`)."""

import hashlib
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from arm64.paths_arm64 import source_file

FAST_VM_MODULES = (
    "vm/specialize.py",
    "vm/register_bias.py",
    "vm/branch_fusion.py",
    "vm/publication_release.py",
    "vm/c_owners.py",
    "workers/property_ic_arm64.py",
    "workers/call_leaves_arm64.py",
    "workers/constructors_arm64.py",
    "workers/indexed_arm64.py",
)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _replace_exact(text, old, new, expected, desc):
    count = text.count(old)
    if count != expected:
        raise ValueError(f"fast_vm {desc}: expected {expected} matches, got {count}")
    return text.replace(old, new)


def _verify_float_typed_array_ids(source):
    core = source_file(source, "quickjs.c").read_text(encoding="utf-8")
    core_nc = re.sub(r"/\*.*?\*/", "", core, flags=re.S)
    m = re.search(r"enum\s*\{\s*JS_CLASS_OBJECT\s*=\s*1\s*,(.*?)JS_CLASS_INIT_COUNT", core_nc, re.S)
    if not m:
        raise ValueError("Unable to locate JSClassID enum in quickjs.c")
    names = ["__UNUSED_0", "JS_CLASS_OBJECT"]
    for tok in m.group(1).split(","):
        tok = re.sub(r"//.*", "", tok).strip()
        if tok:
            if "=" in tok:
                raise ValueError("Unexpected explicit initializer in JSClassID enum: " + tok)
            names.append(tok)
    if names.index("JS_CLASS_UINT32_ARRAY") != 28:
        raise ValueError("JS_CLASS_UINT32_ARRAY enum drift")
    f32 = names.index("JS_CLASS_FLOAT32_ARRAY")
    f64 = names.index("JS_CLASS_FLOAT64_ARRAY")
    arr_iter = names.index("JS_CLASS_ARRAY_ITERATOR")
    if (f32, f64, arr_iter) != (32, 33, 46):
        raise ValueError(f"Unexpected class IDs: {(f32, f64, arr_iter)}")

    qhdr = source_file(source, "quickjs.h").read_text(encoding="utf-8")
    qhdr_nc = re.sub(r"/\*.*?\*/", "", qhdr, flags=re.S)
    mc = re.search(r"typedef\s+enum\s+JSCFunctionEnum\s*\{(.*?)\}\s*JSCFunctionEnum", qhdr_nc, re.S)
    if not mc:
        raise ValueError("Unable to locate JSCFunctionEnum in quickjs.h")
    cfuncs = []
    for tok in mc.group(1).split(","):
        tok = re.sub(r"//.*", "", tok).strip()
        if tok:
            cfuncs.append(tok)
    iter_next_cproto = cfuncs.index("JS_CFUNC_iterator_next")
    if iter_next_cproto != 12:
        raise ValueError(f"Unexpected JS_CFUNC_iterator_next: {iter_next_cproto}")
    return f32, f64, arr_iter, iter_next_cproto


def _verify_atoms(source):
    ah = source_file(source, "quickjs-atom.h").read_text(encoding="utf-8")
    atoms = re.findall(r"(?m)^DEF\(\s*([A-Za-z0-9_$]+)\s*,", ah)
    atom_map = {name: idx + 1 for idx, name in enumerate(atoms)}
    expected_atoms = {
        "function": 27,
        "length": 51,
        "undefined": 73,
        "number": 74,
        "boolean": 75,
        "string": 76,
        "object": 77,
        "symbol": 78,
        "bigint": 149,
    }
    for name, idx in expected_atoms.items():
        if atom_map.get(name) != idx:
            raise ValueError(f"Atom {name} drifted: expected {idx}, got {atom_map.get(name)}")
    return atom_map


def _verify_opcodes(source):
    hdr = source_file(source, "quickjs-opcode.h").read_text(encoding="utf-8")
    ops = re.findall(r"(?m)^DEF\(\s*([A-Za-z0-9_]+)\s*,", hdr)
    op_map = {name: idx for idx, name in enumerate(ops)}
    sanity = {
        "nip": 15,
        "dup1": 18,
        "dup2": 19,
        "rot3r": 21,
        "perm3": 24,
        "put_var": 57,
        "to_object": 112,
        "typeof": 146,
    }
    for name, idx in sanity.items():
        if name not in op_map:
            raise ValueError(f"Missing expected opcode {name}")
        if name in ("nip", "dup1", "dup2", "perm3", "put_var", "to_object") and op_map[name] != idx:
            raise ValueError(f"Opcode {name} drifted: expected {idx}, got {op_map.get(name)}")
    return op_map


def generator_digest(source):
    """Return a deterministic SHA256 digest over the ARM64 fast-VM specialization modules."""
    hasher = hashlib.sha256()
    arm_root = source / "tools/arm64"
    for name in sorted(FAST_VM_MODULES):
        hasher.update((name + "\0").encode("utf-8"))
        hasher.update((arm_root / name).read_bytes())
    return hasher.hexdigest()


def specialize(source, output, enabled, vm_receipt):
    from arm64.vm.branch_fusion import (
        _specialize_compare_branch_and_loops,
        _specialize_equality_comparisons,
        _specialize_float_bitwise_and_neg,
    )
    from arm64.vm.c_owners import _specialize_c_owners
    from arm64.vm.publication_release import _unify_publication_release
    from arm64.vm.register_bias import _reclaim_x26_x27
    from arm64.workers.call_leaves_arm64 import _specialize_call_leaves
    from arm64.workers.constructors_arm64 import _specialize_constructors_and_host
    from arm64.workers.indexed_arm64 import (
        _specialize_indexed_and_borrows,
        _specialize_iterators,
        _specialize_stack_and_globals,
    )
    from arm64.workers.property_ic_arm64 import _specialize_property_ic

    number_record = vm_receipt["number_dataflow"]
    contract_path = source / "src/arm64/linux/abi/fast-vm.json"
    contract = json.loads(contract_path.read_text())
    for name, digest in contract["source_owners"].items():
        if sha(source_file(source, name)) != digest:
            raise ValueError("Review fast-vm source owner: " + name)
    receipt = dict(
        enabled=bool(enabled),
        contract_sha256=sha(contract_path),
        generator_sha256=generator_digest(source),
        source_owners=contract["source_owners"],
        physical_frame_growth=0,
        public_ABI_growth=0,
    )
    if not enabled:
        (output / "FAST-VM.json").write_text(json.dumps(receipt, indent=2) + "\n")
        return receipt
    if not number_record.get("enabled"):
        raise ValueError("QJS_AARCH64_FAST_VM requires QJS_AARCH64_NUMBER_DATAFLOW")

    f32_id, f64_id, arr_iter_id, cfunc_iter_next = _verify_float_typed_array_ids(source)
    _verify_atoms(source)
    op_ids = _verify_opcodes(source)
    target = output / "interpreter-aarch64-number-dataflow.S"
    text = target.read_text()

    text, reg_stats = _reclaim_x26_x27(text)
    text, prop_islands = _specialize_property_ic(text)
    text, ctor_islands = _specialize_constructors_and_host(text)
    text, iter_islands = _specialize_iterators(text, arr_iter_id, cfunc_iter_next)
    text, leaf_islands = _specialize_call_leaves(text)
    text, cmp_islands = _specialize_compare_branch_and_loops(text)
    text, eq_islands = _specialize_equality_comparisons(text)
    text, fbw_islands = _specialize_float_bitwise_and_neg(text)
    text, idx_islands = _specialize_indexed_and_borrows(text, f32_id, f64_id)
    text, glob_islands = _specialize_stack_and_globals(text, output, op_ids)

    c_updates = _specialize_c_owners(source, output)

    env_island = """.Lfast_vm_leaf_env_init:
    mov w21, #0x40000000
#ifdef QJS_AARCH64_SCALAR_OPS
    bl qjs_aarch64_vm_scalar_policy
#else
    bl qjs_aarch64_vm_policy
#endif
    orr w21, w21, w0
    adrp x0, .Lfast_env_s0
    add x0, x0, :lo12:.Lfast_env_s0
    bl getenv
    cbnz x0, .Lfast_env_c1
    orr w21, w21, #0x01000000
.Lfast_env_c1:
    adrp x0, .Lfast_env_s1
    add x0, x0, :lo12:.Lfast_env_s1
    bl getenv
    cbnz x0, .Lfast_env_c2
    orr w21, w21, #0x02000000
.Lfast_env_c2:
    adrp x0, .Lfast_env_s2
    add x0, x0, :lo12:.Lfast_env_s2
    bl getenv
    cbz x0, .Lfast_env_getter_on
    ldrb w2, [x0]
    cmp w2, #48
    b.ne .Lfast_env_chk_lf
.Lfast_env_getter_on:
    orr w21, w21, #0x04000000
.Lfast_env_chk_lf:
    adrp x0, .Lfast_env_s3
    add x0, x0, :lo12:.Lfast_env_s3
    bl getenv
    cbnz x0, .Lfast_env_chk_si
    orr w21, w21, #0x10000000
.Lfast_env_chk_si:
    adrp x0, .Lfast_env_s4
    add x0, x0, :lo12:.Lfast_env_s4
    bl getenv
    cbnz x0, .Lfast_env_chk_ld
    orr w21, w21, #0x00800000
.Lfast_env_chk_ld:
    adrp x0, JS_FrameLengthData
    add x0, x0, :lo12:JS_FrameLengthData
    ldarb w2, [x0]
    cmp w2, #1
    b.ne .Lfast_env_chk_expr
    orr w21, w21, #0x20000000
.Lfast_env_chk_expr:
    adrp x0, .Lfast_env_s5
    add x0, x0, :lo12:.Lfast_env_s5
    bl getenv
    cbnz x0, .Lfast_env_chk_char
    orr w21, w21, #0x00200000
.Lfast_env_chk_char:
    adrp x0, .Lfast_env_s6
    add x0, x0, :lo12:.Lfast_env_s6
    bl getenv
    cbnz x0, .Lfast_env_chk_fwd
    orr w21, w21, #0x00400000
.Lfast_env_chk_fwd:
    adrp x0, .Lfast_env_s7
    add x0, x0, :lo12:.Lfast_env_s7
    bl getenv
    cbnz x0, .Lfast_env_chk_cinv
    adrp x0, .Lfast_env_s8
    add x0, x0, :lo12:.Lfast_env_s8
    bl getenv
    cbnz x0, .Lfast_env_chk_cinv
    adrp x0, .Lfast_env_s9
    add x0, x0, :lo12:.Lfast_env_s9
    bl getenv
    cbnz x0, .Lfast_env_chk_cinv
    orr w21, w21, #0x00080000
.Lfast_env_chk_cinv:
    adrp x0, .Lfast_env_s10
    add x0, x0, :lo12:.Lfast_env_s10
    bl getenv
    cbnz x0, .Lfast_env_chk_own
    adrp x0, .Lfast_env_s11
    add x0, x0, :lo12:.Lfast_env_s11
    bl getenv
    cbnz x0, .Lfast_env_chk_own
    adrp x0, .Lfast_env_s12
    add x0, x0, :lo12:.Lfast_env_s12
    bl getenv
    cbnz x0, .Lfast_env_chk_own
    adrp x0, .Lfast_env_s13
    add x0, x0, :lo12:.Lfast_env_s13
    bl getenv
    cbnz x0, .Lfast_env_chk_own
    orr w21, w21, #0x00100000
.Lfast_env_chk_own:
    adrp x0, JS_FrameOwnBytecodeData
    add x0, x0, :lo12:JS_FrameOwnBytecodeData
    ldrb w2, [x0, #ARM_OFF_JSFrameOwnBytecodeControl_local_field]
    cmp w2, #1
    b.ne .Lfast_env_store
    orr w21, w21, #0x08000000
.Lfast_env_store:
#ifndef QJS_AARCH64_VM_INSTRUMENT
    adrp x4, .Ldispatch_table
    add x4, x4, :lo12:.Ldispatch_table
    adrp x5, .Lfast_orig_ptrs
    add x5, x5, :lo12:.Lfast_orig_ptrs
    mov w8, #0
.Lfast_ptrs_loop0:
    ldrsw x6, [x4, x8, lsl #2]
    add x6, x4, x6
    str x6, [x5, x8, lsl #3]
    add w8, w8, #1
    cmp w8, #256
    b.lo .Lfast_ptrs_loop0

    adrp x4, qjs_aarch64_publish_clean
    add x4, x4, :lo12:qjs_aarch64_publish_clean
    adrp x5, .Lfast_clean_ptrs
    add x5, x5, :lo12:.Lfast_clean_ptrs
    mov w8, #0
.Lfast_ptrs_loop1:
    ldrsw x6, [x4, x8, lsl #2]
    add x6, x4, x6
    str x6, [x5, x8, lsl #3]
    add w8, w8, #1
    cmp w8, #256
    b.lo .Lfast_ptrs_loop1

    adrp x4, qjs_aarch64_publish_dirty
    add x4, x4, :lo12:qjs_aarch64_publish_dirty
    adrp x5, .Lfast_dirty_ptrs
    add x5, x5, :lo12:.Lfast_dirty_ptrs
    mov w8, #0
.Lfast_ptrs_loop2:
    ldrsw x6, [x4, x8, lsl #2]
    add x6, x4, x6
    str x6, [x5, x8, lsl #3]
    add w8, w8, #1
    cmp w8, #256
    b.lo .Lfast_ptrs_loop2
    mov w22, #0
    adrp x0, .Lfast_env_s14
    add x0, x0, :lo12:.Lfast_env_s14
    bl getenv
    cbnz x0, .Lfast_env_ext1
    orr w22, w22, #1
.Lfast_env_ext1:
    adrp x0, .Lfast_env_s15
    add x0, x0, :lo12:.Lfast_env_s15
    bl getenv
    cbnz x0, .Lfast_env_ext_store
    orr w22, w22, #2
.Lfast_env_ext_store:
    adrp x0, .Lfast_vm_ext_env
    str w22, [x0, :lo12:.Lfast_vm_ext_env]
    dmb ish
#endif
    adrp x1, .Lfast_vm_leaf_env
    add x1, x1, :lo12:.Lfast_vm_leaf_env
    stlr w21, [x1]
    mov w0, w21
    b .Lfast_vm_leaf_env_ready
"""
    anchor = ".cfi_endproc\n.size JS_FrameInterp"
    if text.count(anchor) != 1:
        raise ValueError("Review complete borrowed VM CFA before fast_vm island insertion")
    combined_islands = "\n".join(
        [
            env_island,
            prop_islands,
            ctor_islands,
            iter_islands,
            leaf_islands,
            cmp_islands,
            eq_islands,
            fbw_islands,
            idx_islands,
            glob_islands,
        ]
    )
    text = text.replace(anchor, "\n" + combined_islands + "\n" + anchor)

    stack_note = '.section .note.GNU-stack,"",%progbits'
    env_sections = """.section .rodata.str1.1,"aMS",%progbits,1
.Lfast_env_s0:
    .asciz "QJS_DISABLE_FRAME_LEAF_ENTRY"
.Lfast_env_s1:
    .asciz "QJS_DISABLE_NATIVE_CHILD_LEAF"
.Lfast_env_s2:
    .asciz "QJS_DISABLE_THIS_FIELD_LEAF"
.Lfast_env_s3:
    .asciz "QJS_DISABLE_FRAME_INDEXED_OWN"
.Lfast_env_s4:
    .asciz "QJS_DISABLE_FRAME_STACK_INSERT"
.Lfast_env_s5:
    .asciz "QJS_DISABLE_NATIVE_INT_EXPRESSION_LEAF"
.Lfast_env_s6:
    .asciz "QJS_DISABLE_FRAME_CHARACTER_SET_LEAF"
.Lfast_env_s7:
    .asciz "QJS_DISABLE_FRAME_CALL_FORWARD"
.Lfast_env_s8:
    .asciz "QJS_DISABLE_FRAME_CALL_FORWARD_LEAF"
.Lfast_env_s9:
    .asciz "QJS_DISABLE_FRAME_CALL_FORWARD_NATIVE"
.Lfast_env_s10:
    .asciz "QJS_DISABLE_C_INVOKE"
.Lfast_env_s11:
    .asciz "QJS_DISABLE_NATIVE_NUMERIC_INVOKE"
.Lfast_env_s12:
    .asciz "QJS_DISABLE_SHARED_ENTRY"
.Lfast_env_s13:
    .asciz "QJS_RETAIN_SCOPED_HOST"
.Lfast_env_s14:
    .asciz "QJS_DISABLE_LOCALE_COMPARE_LATIN1"
.Lfast_env_s15:
    .asciz "QJS_DISABLE_FRAME_COMPOUND_LEAF"
.section .bss.qjs_aarch64_fast_vm,"aw",%nobits
.p2align 3
.Lfast_array_iter_fn:
    .zero 8
#ifndef QJS_AARCH64_VM_INSTRUMENT
.Lfast_orig_ptrs:
    .zero 2048
.Lfast_clean_ptrs:
    .zero 2048
.Lfast_dirty_ptrs:
    .zero 2048
.p2align 2
.Lfast_vm_ext_env:
    .zero 4
#endif
.p2align 2
.Lfast_vm_leaf_env:
    .zero 4
#ifndef QJS_AARCH64_VM_INSTRUMENT
.section .tbss.qjs_aarch64_fast_vm,"awT",%nobits
.p2align 4
.Lfast_leaf_ic:
    .zero 2048
.Lfast_arr_proto_ic:
    .zero 64
.Lfast_ta_len_ic:
    .zero 128
#endif
"""
    text = _replace_exact(text, stack_note, env_sections + stack_note, 1, "GNU-stack anchor")
    text = _unify_publication_release(text, output, op_ids)
    target.write_text(text)

    number_record["generated_sha256"] = sha(target)
    number_record["fast_vm_enabled"] = True
    (output / "NUMBER-DATAFLOW.json").write_text(json.dumps(number_record, indent=2) + "\n")

    pub_json = output / "PUBLICATION.json"
    pub_rec = json.loads(pub_json.read_text())
    pub_rec["generated"]["interpreter-aarch64-publication-tables.inc"] = sha(
        output / "interpreter-aarch64-publication-tables.inc"
    )
    pub_rec["generated"]["interpreter-aarch64-publication-proxies.inc"] = sha(
        output / "interpreter-aarch64-publication-proxies.inc"
    )
    pub_json.write_text(json.dumps(pub_rec, indent=2) + "\n")
    vm_receipt["deferred_publication"] = pub_rec
    vm_receipt["publication_receipt_sha256"] = sha(pub_json)

    for json_name, rec_key, field_key, upd_key in (
        ("LITERALS.json", "literals", "generated_sha256", "literals"),
        ("ARRAY-WORKERS.json", "array_workers", "header_sha256", "array_workers"),
        ("CALL-LEAVES.json", "call_leaves", "generated_sha256", "call_leaves"),
        ("C-ENTRY.json", "c_entry", "generated_entry_sha256", "c_entry"),
        ("ARGUMENTS.json", "arguments", "generated_sha256", "arguments"),
        ("NULL-PROTO.json", "null_proto", "generated_sha256", "null_proto"),
    ):
        jpath = output / json_name
        jobj = json.loads(jpath.read_text())
        jobj[field_key] = c_updates[upd_key]
        jpath.write_text(json.dumps(jobj, indent=2) + "\n")
        vm_receipt[rec_key] = jobj
        vm_receipt[f"{rec_key}_receipt_sha256"] = sha(jpath)

    jw_path = output / "JSON-WORKERS.json"
    jw_obj = json.loads(jw_path.read_text())
    jw_obj["generated_sha256"] = c_updates["json_workers"]
    jw_path.write_text(json.dumps(jw_obj, indent=2) + "\n")
    vm_receipt["json_workers"] = jw_obj
    vm_receipt["json_worker_sha256"] = c_updates["json_workers"]
    vm_receipt["json_receipt_sha256"] = sha(jw_path)
    vm_receipt["core_sha256"] = c_updates["core"]

    va_jpath = output / "VIRTUAL-ARGUMENTS.json"
    va_jobj = json.loads(va_jpath.read_text())
    va_jobj["worker_sha256"] = c_updates["virtual_arguments"]
    va_jpath.write_text(json.dumps(va_jobj, indent=2) + "\n")

    if "prepared_callbacks" in vm_receipt:
        vm_receipt["prepared_callbacks"]["generated_sha256"] = c_updates["prepared_callbacks"]
    if "dispatch_sha256" in vm_receipt:
        vm_receipt["dispatch_sha256"] = sha(output / "interpreter-aarch64-dispatch.inc")

    receipt.update(
        stats=reg_stats,
        float_typed_arrays=[f32_id, f64_id],
        generated_sha256=number_record["generated_sha256"],
    )
    (output / "FAST-VM.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt
