"""Specialize complete number operators and local addition in the native VM."""

import hashlib
import json
import re
from arm64.paths_arm64 import source_file
from arm64.vm.vm_source import expand_vm
from arm64.vm.value_flow import specialize, cold_operator_modes


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def arithmetic(text):
    """Specialize operators without returning to distant shared warm blocks."""
    entries = re.findall(r"(?m)^(\.L(?:pub_)?)(add|sub|mul|div):$", text)
    expected = {(p, op) for p in (".L", ".Lpub_") for op in ("add", "sub", "mul", "div")}
    if set(entries) != expected or len(entries) != len(expected):
        raise ValueError("Review every original/publication number operator")
    blocks = [
        """
#if ARM_CONST_JS_TAG_INT != 0
#error Review original zero integer tag
#endif
#if ARM_CONST_JS_TAG_FLOAT64 <= 0 || (ARM_CONST_JS_TAG_FLOAT64 & (ARM_CONST_JS_TAG_FLOAT64 - 1)) != 0
#error Review original single-bit positive float tag
#endif
"""
    ]
    sites = []
    for prefix, op in entries:
        label, renamed = prefix + op, prefix + "dataflow_original_" + op
        if text.count(label + ":\n") != 1:
            raise ValueError("Review exact original arithmetic entry")
        stem = prefix + "dataflow_" + op
        mode = {"add": 0, "sub": 1, "mul": 2, "div": 3}[op]
        known, integer, store = stem + "_known", stem + "_integers", stem + "_store"
        # Copy the full accepted division classifier, including -0, NaN,
        # infinities and INT_MIN; labels become local to this operator.
        canonical_start = text.index(prefix + "number_canonical:\n")
        canonical_end = text.index(prefix + "number_float_result:\n", canonical_start)
        canonical = text[canonical_start:canonical_end]
        canonical = canonical.replace(prefix + "number_", stem + "_")
        text = text.replace(label + ":\n", renamed + ":\n")
        first = known if op == "div" else integer
        block = f"""{label}:
    mov w17, #{mode}
    ldp x10, x11, [x21, #-32]
    ldp x12, x13, [x21, #-16]
    orr x14, x11, x13
    cbz x14, {first}
    cmp x14, #ARM_CONST_JS_TAG_FLOAT64
    b.ne {prefix}binary_float
{known}:
    fmov d0, x10
    cbnz x11, {stem}_lhs_ready
    scvtf d0, w10
{stem}_lhs_ready:
    fmov d1, x12
    cbnz x13, {stem}_rhs_ready
    scvtf d1, w12
{stem}_rhs_ready:
    f{op} d0, d0, d1
"""
        if op == "div":
            block += canonical
        else:
            block += f"    b {stem}_float_result\n{integer}:\n"
            if op in ("add", "sub"):
                instruction = "adds" if op == "add" else "subs"
                block += f"    {instruction} w14, w10, w12\n    b.vs {known}\n"
            else:
                block += f"""    smull x14, w10, w12
    cmp x14, w14, sxtw
    b.ne {known}
    cbnz x14, {stem}_int_result
    orr w15, w10, w12
    tbnz w15, #31, {known}
"""
            block += f"""{stem}_int_result:
    mov w10, w14
    mov x11, #ARM_CONST_JS_TAG_INT
    b {store}
"""
        block += f"""{stem}_float_result:
    fmov x10, d0
    mov x11, #ARM_CONST_JS_TAG_FLOAT64
{store}:
    stp x10, x11, [x21, #-32]
    sub x21, x21, #16
    add x20, x20, #1
    ARM_DISPATCH_NEXT 1
"""
        blocks.append(block)
        sites.append(
            dict(
                entry=label,
                original_entry_preserved=renamed,
                nonnumber_owner=prefix + "binary_float",
                warm_continuations="operator-local int/float/classifier/store/dispatch",
            )
        )
    return text, "\n".join(blocks), sites


def generate(source, output, enabled, linear_return=False):
    if linear_return and not enabled:
        raise ValueError("Linear return requires the complete owned VM flow")
    path = source / "src/arm64/linux/abi/number-dataflow.json"
    contract = json.loads(path.read_text())
    for name, digest in contract["source_owners"].items():
        if sha(source_file(source, name)) != digest:
            raise ValueError("Review number-local source owner: " + name)
    target = output / "interpreter-aarch64-number-dataflow.S"
    record = dict(
        enabled=enabled, contract_sha256=sha(path), source_owners=contract["source_owners"]
    )
    if not enabled:
        target.write_text("/* Number dataflow compiled OFF; inherited VM selected. */\n")
    else:
        text = expand_vm(source, output)[0]
        template = (source / "asm/arm64/common/register-number-local.inc").read_text()
        dispatch = (
            r"(?:    ARM_DISPATCH_NEXT 1\n|"
            r"    ldrb w9, \[x20\]\n"
            r"    ldrsw x10, \[x25, x9, lsl #2\]\n"
            r"    add x10, x25, x10\n    br x10\n)"
        )
        producers = re.findall(r"(?m)^(\.L(?:pub_)?add_loc):\n", text)
        pattern = re.compile(r"(?m)^(\.L(?:pub_)?add_loc):\n(.*?" + dispatch + ")", re.S)
        islands, sites = [], []

        def adapt(match):
            body = match[2]
            stem = f".Lnumber_local_{len(islands)}"
            routes = re.findall(r"(?m)^    cbnz x16, (\.L\w+)$", body)
            if len(routes) != 3 or body.count("    adds w10, w10, w14\n") != 1:
                raise ValueError("Review exact original number-local operands/CPP routes")
            overflows = re.findall(r"(?m)^    b\.vs (\.L\w+)$", body)
            if len(overflows) != 1 or overflows[0] != routes[-1]:
                raise ValueError("Review original integer overflow ownership")
            for route in routes:
                body = body.replace(
                    "    cbnz x16, " + route + "\n", "    cbnz x16, " + stem + "_number\n"
                )
            body = body.replace(
                "    b.vs " + overflows[0] + "\n", "    b.vs " + stem + "_overflow\n"
            )
            fallback = (
                "#if ARM_HAS_NUMERIC_WORKERS\n    b "
                + routes[0]
                + "\n#elif ARM_HAS_STRING_WORKERS\n    b "
                + routes[1]
                + "\n#else\n    b "
                + routes[2]
                + "\n#endif"
            )
            islands.append(template.replace("@STEM@", stem).replace("@FALLBACK@", fallback))
            sites.append(
                dict(
                    entry=match[1],
                    original_fallbacks=routes,
                    overflow_original=overflows[0],
                    number=stem,
                )
            )
            return match[1] + ":\n" + body

        text, count = pattern.subn(adapt, text)
        if count not in (1, 2) or count != len(producers):
            raise ValueError("Review complete original/publication number-local producers")
        text, operators, operator_sites = arithmetic(text)
        fusion_sites = []  # No producer-side fusion probes in the opcode-owned path.
        text, value_flow, value_flow_sites = specialize(text)
        operators = cold_operator_modes(operators)
        return_code = ""
        return_receipt = dict(enabled=False)
        if linear_return:
            from arm64.vm.linear_return import specialize as specialize_return

            text, return_code, return_receipt = specialize_return(source, text)
        anchor = ".cfi_endproc\n.size JS_FrameInterp"
        if text.count(anchor) != 1:
            raise ValueError("Review complete borrowed VM CFA")
        text = text.replace(
            anchor,
            "\n" + "\n".join(islands) + "\n" + operators + "\n" + value_flow + return_code + anchor,
        )
        if "@STEM@" in text or "@FALLBACK@" in text:
            raise ValueError("Unbound number-local producer")
        target.write_text(text)
        record.update(
            sites=sites,
            arithmetic_sites=operator_sites,
            fusion_sites=fusion_sites,
            value_flow_sites=value_flow_sites,
            linear_return=return_receipt,
            semantics="Opcode-owned value reads, reference ownership, slot commits and self-contained number operators; no producer-side fusion probes; boxed double add_loc; nonnumbers retain exact original owners and unchanged PC/SP/values",
            publication="Incoming x25 and original Clean/Dirty stream retained. Optional linear return uses inherited typed Free bridges, expanded pop transitions and existing owning result spill; no new fields or frame growth",
            physical_frame_growth=0,
            public_ABI_growth=0,
        )
    record["generated_sha256"] = sha(target)
    (output / "NUMBER-DATAFLOW.json").write_text(json.dumps(record, indent=2) + "\n")
    return record
