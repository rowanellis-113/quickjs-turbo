"""Activation-owned literal structures and their accepted native VM kernels.

Reuse the strong-root owners, lazy admission and native transition/type/truth
algorithms. Actual Linux types, SysV physical entries and ELF CFAs replace the
old platform adapters. Root/frame/state/public API layouts do not grow.
"""

import sys as _x86_sys
from pathlib import Path as _X86Path

if str(_X86Path(__file__).resolve().parents[2]) not in _x86_sys.path:
    _x86_sys.path.insert(0, str(_X86Path(__file__).resolve().parents[2]))
from x86.common.paths_x86 import source_file
import hashlib
import json
import re
from c_workers import replace_one
from arguments import asm_body
from iterators import literal, scoped

OWNERS = (
    "tools/x86/common/codegen/iterator-literal.py",
    "src/x86/win64/mingw64/mingw-ordinary_literal.c",
    "asm/x86/win64/mingw64/mingw-ordinary_literal_entry.S",
)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def contract(source):
    data = json.loads((source / "src/x86/linux/abi/literals.json").read_text())
    for name, digest in data["owners"].items():
        if sha(source_file(source, name)) != digest:
            raise ValueError("Review accepted literal owner: " + name)
    return data


def append(source, output, stream, blocks, handlers, layout, leaf_contract):
    data = contract(source)
    values = data["state_constants"]
    names = [
        "JS_FrameOrdinaryLiteralOpClean",
        "JS_FrameStackInsert2Clean",
        "JS_FrameTypeofValueClean",
        "JS_FrameTypeofFunctionClean",
        "JS_FrameTypeofUndefinedClean",
        "JS_FramePredicateClassify",
        "JS_FramePredicateValue",
    ]
    names += [
        "JS_FrameTruth" + n + "Clean" for n in ("Lnot", "IfTrue", "IfFalse", "IfTrue8", "IfFalse8")
    ]
    added = []
    aliases = {
        "JS_FrameNativeLifetimeResume": "interp_reload",
        "JS_FramePredicateStore": "leaf_classify_store",
        "JS_FramePredicateLiteral": "leaf_value_boolean_literal",
        "JS_FramePredicateBoolean": "leaf_value_boolean",
    }
    for name in names:
        rows = asm_body(source, OWNERS[2], name, layout, extra_values=values)
        for old, new in aliases.items():
            rows = [r.replace(old, new) for r in rows]
        added.append((name, rows))
    for op, name in (
        ("object", "JS_FrameOrdinaryLiteralOpClean"),
        ("define_field", "JS_FrameOrdinaryLiteralOpClean"),
        ("insert2", "JS_FrameStackInsert2Clean"),
        ("typeof", "JS_FrameTypeofValueClean"),
        ("typeof_is_function", "JS_FrameTypeofFunctionClean"),
        ("typeof_is_undefined", "JS_FrameTypeofUndefinedClean"),
    ):
        if handlers.get(op, "interp_slow") != "interp_slow":
            raise ValueError("Review original literal/scalar dispatch: " + op)
        handlers[op] = name
    code = stream["code"]
    for op, name in (
        ("lnot", "Lnot"),
        ("if_true", "IfTrue"),
        ("if_false", "IfFalse"),
        ("if_true8", "IfTrue8"),
        ("if_false8", "IfFalse8"),
    ):
        at = code.index("interp_" + op + ":")
        end = code.index("ja interp_slow", at)
        if end - at > 18:
            raise ValueError("Review original truthiness guard: " + op)
        code[end] = "ja JS_FrameTruth" + name + "Clean"
    kernel = next(rows for name, rows in blocks if name == "JS_FrameLinuxVMLeaves")
    kernel[:] = replace_one(
        "\n".join(kernel),
        "leaf_classify_reject:\njmp JS_FrameLeafUnready",
        "leaf_classify_reject:\njmp JS_FramePredicateClassify",
        "complete predicate classify edge",
    ).splitlines()
    kernel[:] = replace_one(
        "\n".join(kernel),
        "cmp eax, 7\nje leaf_value_boolean_literal",
        "cmp eax, 7\nje JS_FramePredicateValue",
        "live predicate value edge",
    ).splitlines()
    leaf_contract["before_literal_sha256"] = leaf_contract["assembly_rows_sha256"]
    leaf_contract["assembly_rows_sha256"] = hashlib.sha256(
        ("\n".join(kernel) + "\n").encode()
    ).hexdigest()
    leaf_contract["post_literal_transform"] = (
        "Accepted shared-VM predicate classifier/value;root/child leaves retain their immutable2/4/8/14-byte guards"
    )
    (output / "VM-LEAVES.json").write_text(json.dumps(leaf_contract, indent=2) + "\n")
    record = dict(
        status="generated-not-qualified",
        owners=data["owners"],
        functions=names,
        state_constants=values,
        frame_growth=0,
        state_growth=0,
        source_types="same-TU compiler fields and checked private state/OrdScope",
        scope="Native literal transitions,insert2,typeof,predicate and truth kernels;Dirty variants use the existing publication factory",
    )
    (output / "LITERALS-VM.json").write_text(json.dumps(record, indent=2) + "\n")
    return added, record


def generate(
    source,
    output,
    core,
    layout,
    *,
    unified_slow=False,
    platform_binding="src/x86/linux/interpreter-literals.inc",
):
    data = contract(source)
    iterator = literal(source, "iterator-literal", "body")
    for name in ("qjs_literal_core_js_free_shape0", "qjs_literal_core_JS_NewObjectFromShape"):
        iterator = re.sub(r"extern [^;]*\b" + name + r"\([^;]*;\n", "", iterator)
    iterator = iterator.replace("qjs_literal_core_js_free_shape0", "js_free_shape0")
    iterator = iterator.replace("qjs_literal_core_JS_NewObjectFromShape", "JS_NewObjectFromShape")
    slow_selector = "JS_LinuxUnifiedSlowSelect" if unified_slow else "JS_LinuxLiteralBaseSlow"
    iterator = iterator.replace("JS_FrameIteratorSlowSelect", slow_selector)
    iterator = iterator.replace("JS_FrameInterp(", "JS_LinuxLiteralRunVM(")
    iterator = iterator.replace('".qjslmet"', '".data.qjs_linux_literals"')
    iterator = replace_one(
        iterator,
        "FRAME_CODE int JS_FrameIteratorLiteralSelect(JSFrameRegisterState *state)",
        "static FRAME_CODE int js_linux_iterator_literal_body(JSFrameRegisterState *state)",
        "coherent checkpoint literal boundary",
    )
    # Use the later ordinary owner's consumed-RHS publication rule for the
    # shared checkpoint prefix too. The core consumes this value on failure.
    iterator = replace_one(
        iterator,
        "            JS_REF_COUNT(old)--;\n",
        "            JS_REF_COUNT(old)--;\n            --sp;*sp=JS_UNDEFINED;\n",
        "checkpoint literal hit moves its only operand owner",
    )
    old = "            ret=JS_DefinePropertyValue(ctx,sp[-2],atom,sp[-1],JS_PROP_C_W_E|JS_PROP_THROW);"
    new = """            JSValue value=sp[-1];
            --sp;*sp=JS_UNDEFINED;
            state->sp=sp;frame->saved_sp=sp;frame->sf.cur_sp=sp;
            ret=JS_DefinePropertyValue(ctx,sp[-1],atom,value,JS_PROP_C_W_E|JS_PROP_THROW);"""
    iterator = replace_one(
        iterator, old, new, "checkpoint literal core call consumes before reentry"
    )
    iterator = replace_one(
        iterator, "        sp--;pc+=5;", "        pc+=5;", "one literal RHS consumption"
    )
    iterator += "\n" + scoped(
        source, "js_linux_iterator_literal_body", "JS_FrameIteratorLiteralSelect"
    )
    ordinary = (source / OWNERS[1]).read_text()
    start = ordinary.index("extern void qjs_literal_core_js_free_shape0(")
    end = ordinary.index("#define ORD_ACTIVE(s)", start)
    ordinary = ordinary[:start] + ordinary[end:]
    ordinary = ordinary.replace("qjs_literal_core_js_free_shape0", "js_free_shape0")
    ordinary = ordinary.replace("qjs_literal_core_JS_NewObjectFromShape", "JS_NewObjectFromShape")
    ordinary = ordinary.replace("JS_FrameSlowDirectSelect", "JS_FrameIteratorLiteralSelect")
    ordinary = ordinary.replace("JS_FrameInterp(", "JS_LinuxLiteralRunVM(")
    ordinary = ordinary.replace('".qjzzpm"', '".data.qjs_linux_literals"')
    # Both prefixes are the same activation-owned object representation.
    # Sharing actual typedefs avoids incompatible-struct aliasing in one TU.
    start = ordinary.index("typedef struct {")
    end = ordinary.index("typedef struct OrdRecord {", start)
    ordinary = (
        ordinary[:start]
        + "typedef JSFrameLiteralSite OrdSite;\ntypedef JSFrameLiteralScope OrdLegacy;\n"
        + ordinary[end:]
    )
    ordinary = replace_one(
        ordinary,
        "FRAME_CODE int JS_FrameOrdinaryLiteralStep(JSFrameRegisterState *s)",
        "static FRAME_CODE int js_linux_ordinary_literal_body(JSFrameRegisterState *s)",
        "coherent ordinary literal boundary",
    )
    ordinary += "\n" + scoped(
        source, "js_linux_ordinary_literal_body", "JS_FrameOrdinaryLiteralStep"
    )
    facade = """
FRAME_CODE int JS_LinuxLiteralEnter(JSFrameRegisterState *state)
{
    unsigned char previous_active=ORD_ACTIVE(state),previous_lazy=ORD_LAZY(state);
    /* Every physical VM entry owns a fresh scope, including SysV assembly
       roots and coherent C reentry. Caller flags/counter pointers survive. */
    ORD_ACTIVE(state)=0;ORD_LAZY(state)=0;
    JSFunctionBytecode *b=state->frame->bytecode;
    bool extended=(FRAME_ITERATOR_KIND(b)&1)!=0 ||
        (FRAME_KIND(b)==2 && (((unsigned char *)b)[FRAME_CALL_AUX_OFFSET]&1));
    int event=extended?JS_FrameOrdinaryLiteralEnter(state):JS_FrameOrdinaryLiteralLazyEnter(state);
    ORD_ACTIVE(state)=previous_active;ORD_LAZY(state)=previous_lazy;
    return event;
}
FRAME_CODE int JS_FrameInterpSlow(JSFrameRegisterState *state)
{
    if (!state->exception_pending && state->frame &&
        (*state->pc==OP_object || *state->pc==OP_define_field))
        return JS_FrameOrdinaryLiteralStep(state);
    return JS_LinuxLiteralBaseSlow(state);
}
"""
    facade = facade.replace(
        "return JS_LinuxLiteralBaseSlow(state);", "return " + slow_selector + "(state);"
    )
    text = '#include "' + platform_binding + '"\n' + iterator + "\n" + ordinary + "\n" + facade
    text += "\n#undef FRAME_CODE\n#undef FRAME_INLINE\n"
    header = output / "quickjs-linux-literals.h"
    header.write_text(text)
    core += '\n#include "quickjs-linux-literals.h"\n'
    record = dict(
        status="generated-not-qualified",
        owners=data["owners"],
        source_files={
            n: sha(source_file(source, n))
            for n in (
                "tools/x86/linux/literal_shapes.py",
                "src/x86/linux/interpreter-literals.inc",
                "src/common/call/interpreter-slow-host.inc",
            )
        },
        generated_sha256=sha(header),
        frame_growth=0,
        state_growth=0,
        lazy_owner_bytes=24,
        full_scope_bytes=864,
        legacy_prefix_bytes=336,
        slow_selector=slow_selector,
        entries=[
            "JS_LinuxLiteralEnter",
            "JS_LinuxLiteralRunVM",
            "JS_FrameIteratorLiteralEnter",
            "JS_FrameIteratorLiteralSelect",
            "JS_FrameOrdinaryLiteralEnter",
            "JS_FrameOrdinaryLiteralLazyEnter",
            "JS_FrameOrdinaryLiteralStep",
            "JS_LinuxLiteralBaseSlow",
        ]
        + (["JS_LinuxUnifiedSlowSelect"] if unified_slow else []),
        scope="Complete accepted activation-owned literal owners and native cohorts;not whole port or speed",
    )
    (output / "LITERALS.json").write_text(json.dumps(record, indent=2) + "\n")
    return core


def finish_slow(source, output):
    contract(source)
    path = output / "quickjs-linux-construct.h"
    text = replace_one(
        path.read_text(),
        "FRAME_CODE int JS_FrameInterpSlow(JSFrameRegisterState *state)\n{",
        "FRAME_CODE int JS_LinuxLiteralBaseSlow(JSFrameRegisterState *state)\n{",
        "preserve complete original selector behind literal cohorts",
    )
    path.write_text(text)
    for name in ("CONSTRUCT.json", "ITERATORS.json"):
        p = output / name
        data = json.loads(p.read_text())
        data["before_literal_sha256"] = data["generated_sha256"]
        data["generated_sha256"] = sha(path)
        data["post_literal_transform"] = (
            "Complete base selector retained behind activation-owned literal cohorts"
        )
        p.write_text(json.dumps(data, indent=2) + "\n")
    p = output / "VARARGS.json"
    data = json.loads(p.read_text())
    data["before_literal_slow_sha256"] = data["slow_sha256"]
    data["slow_sha256"] = sha(path)
    p.write_text(json.dumps(data, indent=2) + "\n")
    p = output / "LITERALS.json"
    data = json.loads(p.read_text())
    data["slow_sha256"] = sha(path)
    p.write_text(json.dumps(data, indent=2) + "\n")
