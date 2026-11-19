"""Complete source-owned activation literal lifetime with measured ARM fields."""

import hashlib, json, re
from c_workers import replace_one
from literal_shapes_c import generate as shared_generate
from iterators_c import literal


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def original_types(source):
    iterator = literal(source, "iterator-literal", "body")
    iterator = iterator[: iterator.index("static _Atomic unsigned literal_control")]
    ordinary = (source / "src/common/kernel/ordinary-literal.c").read_text()
    text = (
        iterator + "\ntypedef JSFrameLiteralSite OrdSite;\ntypedef JSFrameLiteralScope OrdLegacy;\n"
    )
    for typ in ("OrdRecord", "OrdChunk", "OrdScope", "OrdLazy"):
        matches = re.findall(r"typedef struct(?: \w+)? \{[^{}]*\} " + typ + r";", ordinary)
        if len(matches) != 1:
            raise ValueError("Review actual source literal type: " + typ)
        text += matches[0] + "\n"
    return text


def probe_types(source, text, names):
    text += original_types(source)
    for typ, fields in [
        ("JSFrameLiteralSite", ("site", "bytecode", "old_shape", "new_shape", "atom", "slot")),
        ("JSFrameLiteralScope", ("cache_next", "literals", "next")),
        ("OrdRecord", ("site", "next")),
        ("OrdScope", ("legacy", "bucket", "chunks", "count")),
        ("OrdLazy", ("cache_next", "scope", "seen")),
    ]:
        names += [("SIZE_" + typ, "sizeof(" + typ + ")")]
        names += [("OFF_" + typ + "_" + f, "offsetof(" + typ + "," + f + ")") for f in fields]
    names += [
        (
            "OFF_JSFrameRegisterState_exception_pending",
            "offsetof(JSFrameRegisterState,exception_pending)",
        )
    ]
    names += [
        ("LITERAL_ACTIVE_OFFSET", "offsetof(JSFrameRegisterState,direct_host_calls)+sizeof(bool)"),
        ("LITERAL_LAZY_OFFSET", "offsetof(JSFrameRegisterState,direct_host_calls)+sizeof(bool)+1"),
    ]
    names += [
        ("CONST_JS_ATOM_" + n, "JS_ATOM_" + n)
        for n in ("undefined", "number", "boolean", "string", "object", "symbol", "bigint")
    ]
    names += [
        ("CONST_" + n, "(uint64_t)(int64_t)" + n)
        for n in ("JS_TAG_SYMBOL", "JS_TAG_BIG_INT", "JS_TAG_SHORT_BIG_INT")
    ]
    return text, names


def generate(source, output, core, layout, enabled):
    path = source / "src/arm64/linux/abi/literals.json"
    contract = json.loads(path.read_text())
    for n, h in contract["source_owners"].items():
        if sha(source / n) != h:
            raise ValueError("Review full literal lifetime/native source owner: " + n)
    if enabled:
        core = shared_generate(
            source,
            output,
            core,
            layout,
            platform_binding="src/arm64/linux/interpreter-literals.inc",
        )
        p = output / "quickjs-linux-literals.h"
        text = p.read_text()
        text = replace_one(
            text,
            '#include "src/arm64/linux/interpreter-literals.inc"',
            '#pragma push_macro("FRAME_CODE")\n#pragma push_macro("FRAME_INLINE")\n#include "src/arm64/linux/interpreter-literals.inc"',
            "preserve actual surrounding target macro scope",
        )
        text = replace_one(
            text,
            "FRAME_CODE int JS_FrameInterpSlow(JSFrameRegisterState *state)\n{",
            '__attribute__((noipa,section(".text.qjs_frame"))) int JS_FrameInterpSlow(JSFrameRegisterState *state)\n{',
            "retain the original declared semantic entry section",
        )
        text += '\n#include "interpreter-aarch64-values.h"\n'
        for typ, fields in [
            ("JSFrameLiteralSite", ("site", "bytecode", "old_shape", "new_shape", "atom", "slot")),
            ("JSFrameLiteralScope", ("cache_next", "literals", "next")),
            ("OrdRecord", ("site", "next")),
            ("OrdScope", ("legacy", "bucket", "chunks", "count")),
            ("OrdLazy", ("cache_next", "scope", "seen")),
        ]:
            text += (
                "_Static_assert(sizeof("
                + typ
                + ")==ARM_SIZE_"
                + typ
                + ',"actual source target literal type");\n'
            )
            for f in fields:
                text += (
                    "_Static_assert(offsetof("
                    + typ
                    + ","
                    + f
                    + ")==ARM_OFF_"
                    + typ
                    + "_"
                    + f
                    + ',"actual source target literal field");\n'
                )
        text += """
_Static_assert(offsetof(JSFrameRegisterState,direct_host_calls)+sizeof(bool)==ARM_LITERAL_ACTIVE_OFFSET,"actual active padding");
_Static_assert(offsetof(JSFrameRegisterState,direct_host_calls)+sizeof(bool)+1==ARM_LITERAL_LAZY_OFFSET,"actual lazy padding");
_Static_assert(sizeof(JS_FrameOrdinaryLiteralStats)==34*sizeof(uint64_t),"original counter extent");
_Static_assert(__builtin_types_compatible_p(__typeof__(&JS_LinuxLiteralEnter),int (*)(JSFrameRegisterState*)),"actual AAPCS64 literal physical owner");
#ifdef QJS_AARCH64_VM_INSTRUMENT
__attribute__((visibility("hidden"),noipa)) void qjs_aarch64_vm_literal_counts(uint64_t out[34])
{for(unsigned i=0;i<34;i++)out[i]=__atomic_load_n(&JS_FrameOrdinaryLiteralStats[i],__ATOMIC_RELAXED);}
#endif
#pragma pop_macro("FRAME_INLINE")
#pragma pop_macro("FRAME_CODE")
"""
        p.write_text(text)
        record = json.loads((output / "LITERALS.json").read_text())
        record.update(
            enabled=True,
            generated_sha256=sha(p),
            physical_owner="Existing kind3 blocked TLS -> complete literal lifetime -> raw AAPCS64 VM",
            native=[
                "object/define_field transition",
                "insert2",
                "typeof value/function/undefined",
                "string/rope/object/number truth",
            ],
            remaining="Specialized fused predicate call classify/value and other scalar leaf admission are separately open",
        )
    else:
        p = output / "quickjs-linux-literals.h"
        p.write_text("/* Literal mechanisms compiled OFF. */\n")
        record = dict(enabled=False, entries=[], generated_sha256=sha(p))
    record.update(
        source_owners=contract["source_owners"],
        contract_sha256=sha(path),
        generator_sha256=sha(source / "tools/arm64/workers/literals.py"),
        geometry=dict(
            frame_growth=0,
            state_growth=0,
            runtime_growth=0,
            new_release_TLS=0,
            new_instrument_TLS=0,
        ),
        whole_qualification=False,
        physical_ARM_performance_qualified=False,
    )
    (output / "LITERALS.json").write_text(json.dumps(record, indent=2) + "\n")
    return core, record


def finish(output, record):
    if record["enabled"]:
        p = output / "quickjs-linux-indexed.h"
        t = p.read_text()
        t = replace_one(
            t,
            "FRAME_CODE int JS_FrameInterpSlow(JSFrameRegisterState *state)\n{",
            "FRAME_CODE int JS_LinuxLiteralBaseSlow(JSFrameRegisterState *state)\n{",
            "retain complete indexed/extended/argument exception owner",
        )
        p.write_text(t)
        ip = output / "INDEXED.json"
        d = json.loads(ip.read_text())
        d["generated_sha256"] = sha(p)
        d["entries"].append("JS_LinuxLiteralBaseSlow")
        ip.write_text(json.dumps(d, indent=2) + "\n")
        record["base_selector_sha256"] = sha(p)
    (output / "LITERALS.json").write_text(json.dumps(record, indent=2) + "\n")
    return record
