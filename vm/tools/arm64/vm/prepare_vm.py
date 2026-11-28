"""Derive an opt-in AArch64 register tier from this build's exact C input.

The target compiler measures core and owned-frame types and opcode numbers.
No target probe executes, no foreign assembly is translated, no archive is patched.
"""

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import struct
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from arm64.paths_arm64 import activate_arm64_tools, source_file

activate_arm64_tools()
from elf64 import Elf64
from layout_input import load_input, requests


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def put(path, value):
    if not path.exists() or path.read_text() != value:
        path.write_text(value)


HOT = {
    "push_i8": "push_i8",
    "push_i16": "push_i16",
    "push_i32": "push_i32",
    "push_minus1": "push_small",
    "undefined": "undefined",
    "null": "null",
    "push_true": "bool",
    "push_false": "bool",
    "get_loc8": "get_loc8",
    "get_loc": "get_loc",
    "get_arg": "get_arg",
    "dup": "dup",
    "drop": "drop",
    "add": "add",
    "sub": "sub",
    "and": "bitand",
    "nop": "nop",
}
for i in range(8):
    HOT["push_" + str(i)] = "push_small"
for family in ("loc", "arg"):
    for i in range(4):
        HOT["get_" + family + str(i)] = "get_" + family + "_short"
for i in range(4):
    HOT["call" + str(i)] = "call_short"
for name in ("call", "call_method", "tail_call", "tail_call_method"):
    HOT[name] = "call_wide"
HOT.update({"return": "return", "return_undef": "return_undef"})
HOT["regexp"] = "regexp"
HOT["special_object"] = "current_function"
for family in ("loc", "arg"):
    for action in ("put", "set"):
        HOT[action + "_" + family] = action + "_" + family
        for i in range(4):
            HOT[action + "_" + family + str(i)] = action + "_" + family + "_short"
for action in ("put", "set"):
    HOT[action + "_loc8"] = action + "_loc8"
for name in (
    "inc_loc",
    "dec_loc",
    "add_loc",
    "lt",
    "lte",
    "gt",
    "gte",
    "eq",
    "neq",
    "goto",
    "goto8",
    "goto16",
    "if_true",
    "if_false",
    "if_true8",
    "if_false8",
):
    HOT[name] = name
HOT.update(strict_eq="eq", strict_neq="neq")
HOT.update(mul="mul", div="div")
for action in ("get", "put", "set"):
    HOT[action + "_var_ref"] = action + "_var_ref"
    for i in range(4):
        HOT[action + "_var_ref" + str(i)] = action + "_var_ref_short"
for name in (
    "get_var_ref_check",
    "put_var_ref_check",
    "put_var_ref_check_init",
    "get_loc_check",
    "put_loc_check",
    "put_loc_check_init",
    "set_loc_uninitialized",
    "push_const",
    "push_const8",
    "push_this",
):
    HOT[name] = name


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--number-dataflow", action="store_true")
    ap.add_argument("--linear-return", action="store_true")
    ap.add_argument("--fast-vm", action="store_true")
    for name in ("source", "build", "output"):
        ap.add_argument("--" + name, type=Path, required=True)
    a = ap.parse_args()
    source, build, out = (p.resolve() for p in (a.source, a.build, a.output))
    out.mkdir(parents=True, exist_ok=True)
    core_path = out / "quickjs-aarch64.c"
    actual = load_input(source, build, core_path)
    from c_workers import module as actual_module

    source_match = actual_module(source, "c_source_match")
    HOT.update({name: name for name in ("get_field", "get_field2", "get_length", "put_field")})
    if actual.receipt["property_ic"]:
        HOT.update({name: name for name in ("get_field", "get_field2", "put_field")})
    publication_contract = source / "src/arm64/linux/abi/publication.json"
    for path, expected in json.loads(publication_contract.read_text())["source_owners"].items():
        if sha(source_file(source, path)) != expected:
            raise ValueError("Review complete publication semantic owner: " + path)
    admission_contract = source / "src/arm64/linux/abi/admission.json"
    for path, expected in json.loads(admission_contract.read_text())["source_owners"].items():
        if sha(source_file(source, path)) != expected:
            raise ValueError("Review native regexp/admission owner: " + path)
    regexp_contract = source / "src/arm64/linux/abi/regexp.json"
    for path, expected in json.loads(regexp_contract.read_text())["source_owners"].items():
        if sha(source_file(source, path)) != expected:
            raise ValueError("Review RegExp source/typed boundary owner: " + path)
    json_contract = source / "src/arm64/linux/abi/json.json"
    for path, expected in json.loads(json_contract.read_text())["source_owners"].items():
        if sha(source_file(source, path)) != expected:
            raise ValueError("Review complete JSON semantic/architecture owner: " + path)
    callback_contract = source / "src/arm64/linux/abi/prepared-callbacks.json"
    for path, expected in json.loads(callback_contract.read_text())["source_owners"].items():
        if sha(source_file(source, path)) != expected:
            raise ValueError("Review prepared callback loop/activation semantics: " + path)
    shared_contract = source / "src/arm64/linux/abi/shared.json"
    for path, expected in json.loads(shared_contract.read_text())["source_owners"].items():
        if sha(source_file(source, path)) != expected:
            raise ValueError("Review shared activation/ownership semantics: " + path)
    capture_path = source / "src/arm64/linux/abi/captures.json"
    for path, expected in json.loads(capture_path.read_text())["source_owners"].items():
        if sha(source_file(source, path)) != expected:
            raise ValueError("Review original capture/owned argument semantics: " + path)
    window_path = source / "src/arm64/linux/abi/window.json"
    for path, expected in json.loads(window_path.read_text())["source_owners"].items():
        if sha(source_file(source, path)) != expected:
            raise ValueError(
                "Review original argument window semantics before native execution: " + path
            )
    numeric_path = source / "src/arm64/linux/abi/numeric.json"
    numeric = json.loads(numeric_path.read_text())
    for name, expected in numeric["core_functions"].items():
        definitions = re.findall(
            r"^static (?:inline )?(?:bool|JSValue) " + name + r"\([^;{}]*\)\s*\{.*?^\}",
            actual.core.read_text(),
            re.M | re.S,
        )
        if len(definitions) != 1 or hashlib.sha256(definitions[0].encode()).hexdigest() != expected:
            raise ValueError("Review original numeric semantics before native execution: " + name)
    for path, expected in numeric["source_owners"].items():
        if sha(source_file(source, path)) != expected:
            raise ValueError("Review numeric source owner before native execution: " + path)
    special = re.findall(r"typedef enum \{[^{}]+\} OPSpecialObjectEnum;", actual.core.read_text())
    if len(special) != 1:
        raise ValueError("Review actual special-object enum owner")
    special_enum = special[0] if "OPSpecialObjectEnum" not in actual.prelude else ""
    owner = re.findall(
        r"case OP_SPECIAL_OBJECT_THIS_FUNC:\s*(\*sp\+\+ = js_dup\(sf->cur_func\);)\s*break;",
        actual.core.read_text(),
    )
    fragment = source / "src/common/call/interpreter-current-function.inc"
    if len(owner) != 1:
        raise ValueError("Review original THIS_FUNC semantics before extending frame admission")
    source_match.find_one(fragment.read_text(), owner[0])
    if "-DQJS_AARCH64_NULL_PROTO" in actual.flags:
        fallback = (source / "src/common/call/interpreter-current-function-null.inc").read_text()
        for subopcode in ("THIS_FUNC", "NULL_PROTO"):
            semantic = re.findall(
                r"^                case OP_SPECIAL_OBJECT_"
                + subopcode
                + r":\n.*?^                    break;\n",
                actual.core.read_text(),
                re.M | re.S,
            )
            if len(semantic) != 1:
                raise ValueError("Review exact original " + subopcode + " fallback semantics")
            source_match.find_one(fallback, semantic[0])
    name_fragment = source / "src/common/call/interpreter-set-name.inc"
    name_owner = re.findall(
        r"^        CASE\(OP_set_name\):.*?(?=^        CASE\(OP_set_name_computed\):)",
        actual.core.read_text(),
        re.M | re.S,
    )
    if len(name_owner) != 1:
        raise ValueError("Review exact original set_name opcode semantics")
    source_match.find_one(name_fragment.read_text(), name_owner[0].rstrip())
    flags = actual.flags
    iterator_enabled = "-DQJS_AARCH64_ITERATORS" in flags
    constructor_enabled = "-DQJS_AARCH64_CONSTRUCTORS" in flags
    forwarding_enabled = "-DQJS_AARCH64_FORWARDING" in flags
    if constructor_enabled:
        HOT["call_constructor"] = "construct_call"
    if iterator_enabled:
        for op in actual_module(source, "iterator-c").OPS:
            HOT[op] = "iterator_" + op
    comparison_enabled = "-DQJS_AARCH64_COMPARISONS" in flags
    varargs_enabled = "-DQJS_AARCH64_VARARGS" in flags
    strings_enabled = "-DQJS_AARCH64_STRING_WORKERS" in flags
    scalar_enabled = "-DQJS_AARCH64_SCALAR_OPS" in flags
    from arm64.vm.scalar_ops import OPS as SCALAR_OPS

    if scalar_enabled:
        HOT.update({n: "scalar_" + n for n in SCALAR_OPS})
    call_leaves_enabled = "-DQJS_AARCH64_CALL_LEAVES" in flags
    stack_insert_enabled = "-DQJS_AARCH64_STACK_INSERT" in flags
    if stack_insert_enabled:
        HOT["insert3"] = "stack_insert3"
    numeric_workers_enabled = "-DQJS_AARCH64_NUMERIC_WORKERS" in flags
    projection_enabled = "-DQJS_AARCH64_COMPILER_PROJECTION" in flags
    literals_enabled = "-DQJS_AARCH64_LITERALS" in flags
    indexed_enabled = "-DQJS_AARCH64_INDEXED" in flags
    arguments_enabled = "-DQJS_AARCH64_ARGUMENTS" in flags
    if arguments_enabled:
        HOT.update({n: n for n in ("get_array_el", "get_array_el2", "put_array_el")})
    if indexed_enabled:
        HOT.update(
            {
                n: "indexed_" + n
                for n in ("get_array_el", "get_array_el2", "put_array_el", "instanceof")
            }
        )
    if literals_enabled:
        HOT.update(
            {
                n: "literal_" + n
                for n in (
                    "object",
                    "define_field",
                    "insert2",
                    "typeof",
                    "typeof_is_function",
                    "typeof_is_undefined",
                    "lnot",
                )
            }
        )
    null_enabled = "-DQJS_AARCH64_NULL_PROTO" in flags
    global_enabled = "-DQJS_AARCH64_GLOBAL_BINDING" in flags
    if global_enabled:
        HOT.update(get_var="get_var", get_var_undef="get_var")
    triple = subprocess.check_output([actual.compiler, "-dumpmachine"], text=True).strip()
    if not triple.startswith("aarch64"):
        raise ValueError("An actual AArch64 compiler target is required")
    if any(f.startswith(("-flto", "-fsanitize")) for f in flags):
        raise ValueError("AArch64 VM is not qualified with LTO/sanitizers")
    unsafe = (
        "-Ofast",
        "-ffast-math",
        "-ffinite-math-only",
        "-funsafe-math-optimizations",
        "-fno-signed-zeros",
        "-freciprocal-math",
        "-fassociative-math",
        "-fno-trapping-math",
        "-fsingle-precision-constant",
    )
    if any(f.startswith(unsafe) for f in flags):
        raise ValueError("Native numeric semantics require reviewed IEEE compiler flags")
    commands = []

    def probe(name, text, section):
        src, obj = out / (name + ".c"), out / (name + ".o")
        put(src, text)
        argv = [
            actual.compiler,
            "-I" + str(actual.core.parent),
            "-I" + str(out),
            *flags,
            "-Wno-unused-function",
            "-Wno-unused-const-variable",
            "-Wno-unused-variable",
            "-c",
            str(src),
            "-o",
            str(obj),
        ]
        commands.append(argv)
        (out / "COMMANDS.json").write_text(json.dumps(commands, indent=2) + "\n")
        with (
            (out / (name + ".stdout")).open("wb") as so,
            (out / (name + ".stderr")).open("wb") as se,
        ):
            proc = subprocess.run(argv, cwd=actual.command["directory"], stdout=so, stderr=se)
        if proc.returncode != 0:
            err = (out / (name + ".stderr")).read_text(encoding="utf-8", errors="replace")
            if err:
                sys.stderr.write(err)
            raise subprocess.CalledProcessError(proc.returncode, argv)
        elf = Elf64.read(obj, expected_machine=183)
        if elf.kind != 1:
            raise ValueError("Probe must be AArch64 ET_REL")
        raw = elf.section_data(elf.section(section))
        return elf, list(struct.unpack("<" + "Q" * (len(raw) // 8), raw))

    checks = """
#if !defined(__aarch64__) || !defined(__linux__) || !defined(__LP64__) || __BYTE_ORDER__ != __ORDER_LITTLE_ENDIAN__
#error Linux AArch64 LE LP64 required
#endif
#if defined(__ARM_FEATURE_BTI_DEFAULT) || defined(__ARM_FEATURE_PAC_DEFAULT)
#error BTI/PAC register executor is not qualified yet
#endif
_Static_assert(sizeof(JSValue)==16 && offsetof(JSValue,tag)==8, "AArch64 value representation");
_Static_assert(sizeof(JSVarRef *)==8, "Actual AArch64 capture pointer size");
#include <float.h>
#if defined(__FAST_MATH__) || (defined(__FINITE_MATH_ONLY__) && __FINITE_MATH_ONLY__ > 0)
#error IEEE double semantics required by native numeric handlers
#endif
_Static_assert(sizeof(double)==8 && FLT_RADIX==2 && DBL_MANT_DIG==53 && DBL_MAX_EXP==1024,
               "Native arithmetic requires IEEE binary64");
"""
    keys, expr = requests(actual.catalogue, actual.receipt["property_ic"])
    bits = actual.catalogue["bits"]
    text = actual.prelude + "\n#include <stddef.h>\n" + checks
    text += (
        '__attribute__((used,section(".qjs.vm.core"),aligned(8))) const uint64_t qjs_core[] = {\n'
    )
    text += ",\n".join(expr) + "\n};\n"
    for i, name in enumerate(bits):
        owner, field = name.split(".", 1)
        text += f'__attribute__((used,section(".qjs.vm.bit{i}"))) const {owner} qjs_bit{i} = {{.{field}=1}};\n'
    elf, values = probe("core-probe", text, ".qjs.vm.core")
    if len(values) != len(keys):
        raise ValueError("Core constant extent changed")
    contract = ["/* Actual target constants, generated; no foreign numeric import. */"]
    layout = dict(
        reference_count_model="allocator-prefix", sizes={}, offsets={}, constants={}, bits={}
    )
    for (group, name), value in zip(keys, values):
        if group == "constants" and value >= 1 << 63:
            value -= 1 << 64
        layout[group][name] = value
        prefix = dict(sizes="SIZE_", offsets="OFF_", constants="CONST_")[group]
        contract.append(
            "#define QJS_ABI_" + prefix + name.replace(".", "_") + " (" + str(value) + ")"
        )
    for i, name in enumerate(bits):
        raw = elf.section_data(elf.section(".qjs.vm.bit" + str(i)))
        active = [(j, b) for j, b in enumerate(raw) if b]
        if len(active) != 1:
            raise ValueError("Split or missing bitfield: " + name)
        byte, mask = active[0]
        layout["bits"][name] = active
        contract += [
            f"#define QJS_ABI_BIT_{name.replace('.', '_')}_BYTE {byte}",
            f"#define QJS_ABI_BIT_{name.replace('.', '_')}_MASK {mask}",
        ]
    contract += [
        "#define QJS_ABI_HAS_CORO_OWNER 1",
        "#define QJS_ABI_HAS_PREFIX_RC 1",
        "#define QJS_ABI_REF_COUNT_OFFSET (-4)",
        "#define QJS_ABI_INTERRUPT_TAKES_CTX 1",
    ]
    for (group, name), expression in zip(keys, expr):
        if group in ("sizes", "offsets"):
            contract.append(
                "_Static_assert("
                + expression
                + " == QJS_ABI_"
                + dict(sizes="SIZE_", offsets="OFF_")[group]
                + name.replace(".", "_")
                + ', "AArch64 actual core: '
                + name
                + '");'
            )
    put(out / "interpreter-private-abi.h", "\n".join(contract) + "\n")
    # The shared register header also asserts the measured original core types.
    preamble = (
        "\nstatic void close_var_ref(JSRuntime *rt, JSVarRef *var_ref);\n"
        '#include "interpreter-private-abi.h"\n'
        '#include "src/arm64/linux/interpreter-compat.inc"\n'
    )
    preamble += '#ifdef QJS_AARCH64_VM_INSTRUMENT\n#include "src/arm64/linux/interpreter-observe.h"\n#endif\n'
    from arm64.workers.property_primitives import (
        prepare as prepare_primitives,
        finish as finish_primitives,
    )

    primitive_record = prepare_primitives(source, out, layout)
    from arm64.workers.property_hints import prepare as prepare_hints, finish as finish_hints

    own_record = prepare_hints(
        source, out, layout, reference_controls=global_enabled or comparison_enabled
    )
    from arm64.workers.global_bindings import prepare as prepare_globals, finish as finish_globals

    global_record = prepare_globals(
        source, out, layout, actual, global_enabled, reference_controls=comparison_enabled
    )
    from arm64.workers.comparisons import (
        prepare as prepare_comparisons,
        finish as finish_comparisons,
    )

    comparison_record = prepare_comparisons(source, out, layout, comparison_enabled, global_enabled)
    from arm64.workers.constructors import prepare as prepare_constructors
    from arm64.workers.iterators import prepare as prepare_iterators
    from arm64.workers.extended_calls import (
        prepare as prepare_extended,
        prepare_loop as extended_loop,
        finish as finish_extended,
    )

    constructor_record = prepare_constructors(source, out, constructor_enabled)
    iterator_record = prepare_iterators(source, out, iterator_enabled)
    from arm64.workers.forwarding import (
        prepare as prepare_forwarding,
        policy as forwarding_policy,
        finish as finish_forwarding,
    )

    forwarding_record = prepare_forwarding(source, out, forwarding_enabled)
    extended_record = prepare_extended(
        source, out, constructor_record, iterator_record, forwarding=forwarding_enabled
    )
    from arm64.workers.property_prototypes import (
        prepare as prepare_prototypes,
        finish as finish_prototypes,
    )

    proto_record = prepare_prototypes(source, out, layout)
    owned = ["JSFrame", "JSFrameRegisterState", "JSFrameSegment", "JSFrameSharedAnchor"]
    offsets = [
        "JSFrameRegisterState." + n
        for n in (
            "frame",
            "segment",
            "pc",
            "sp",
            "result",
            "rt",
            "used_bytes",
            "native_stack_limit",
            "direct_host_calls",
            "sites",
            "cache_next",
            "iterator_checkpoint_depth",
        )
    ]
    offsets += [
        "JSFrame." + n
        for n in (
            "bytecode",
            "this_value",
            "saved_sp",
            "segment",
            "frame_bytes",
            "owned_args",
            "pending",
        )
    ]
    offsets += ["JSFrameSegment." + n for n in ("used", "capacity", "data")]
    offsets += ["JSFrameSharedAnchor." + n for n in ("prev", "state", "kind")]
    names = [("SIZE_" + t, "sizeof(" + t + ")") for t in owned]
    names += [
        ("OFF_" + n.replace(".", "_"), "offsetof(" + n.replace(".", ",") + ")") for n in offsets
    ]
    names += [
        ("CONST_" + n, "(uint64_t)(int64_t)(" + n + ")")
        for n in (
            "JS_TAG_INT",
            "JS_TAG_BOOL",
            "JS_TAG_NULL",
            "JS_TAG_UNDEFINED",
            "JS_TAG_UNINITIALIZED",
        )
    ]
    opnames = list(HOT)
    opnames += [
        name
        for name in ("get_var", "get_var_undef", "call_constructor", *iterator_record["opcodes"])
        if name not in HOT
    ]
    names += [("OP_" + n, "OP_" + n) for n in opnames]
    names += [
        ("FRAME_HEADER_BYTES", "FRAME_HEADER_BYTES"),
        ("FRAME_KIND_OFFSET", "offsetof(JSFunctionBytecode,byte_code_buf)-1"),
        ("FRAME_ROOT_OFFSET", "FRAME_ROOT_OFFSET"),
        ("FRAME_FLAGS_OFFSET", "FRAME_FLAGS_OFFSET"),
        (
            "REF_COUNT_OFFSET",
            "(uint64_t)((int64_t)offsetof(JSMallocBlockHeader,ref_count)-(int64_t)offsetof(JSMallocBlockHeader,user_data))",
        ),
    ]
    names += [
        ("CONST_OP_SPECIAL_OBJECT_NULL_PROTO", "OP_SPECIAL_OBJECT_NULL_PROTO"),
        ("CONST_OP_SPECIAL_OBJECT_THIS_FUNC", "OP_SPECIAL_OBJECT_THIS_FUNC"),
        ("VAR_REF_POINTER_BYTES", "sizeof(JSVarRef *)"),
    ]
    names += [
        ("OFF_JSProperty_u_value", "offsetof(JSProperty,u.value)"),
        ("SIZE_JSFrameLengthData", "sizeof(JSFrameLengthData)"),
        ("OFF_JSFrameLengthData_mode", "offsetof(JSFrameLengthData,mode)"),
        ("NUMBER_PROPERTY_CONTROL_BYTES", "sizeof(JS_FrameNumberPropertyControl)"),
        ("CONST_JS_CLASS_NUMBER", "JS_CLASS_NUMBER"),
    ]
    if actual.receipt["property_ic"]:
        names += [("OFF_JSPropertyICWay_shape", "offsetof(JSPropertyICWay,shape)")]
        names += [
            ("CONST_" + name, "(uint64_t)(" + name + ")")
            for name in (
                "JS_IC_OWN",
                "JS_IC_PROTO",
                "JS_IC_UNSET",
                "JS_IC_REPLACE",
                "JS_IC_TRANSITION",
                "JS_IC_PROTO_WEAK",
                "JS_IC_RETAIN_ORPHANS",
            )
        ]
    names += [
        ("SIZE_JSFrameOwnBytecodeControl", "sizeof(JSFrameOwnBytecodeControl)"),
        ("OFF_JSFrameOwnBytecodeControl_mode", "offsetof(JSFrameOwnBytecodeControl,mode)"),
        (
            "OFF_JSFrameOwnBytecodeControl_local_field",
            "offsetof(JSFrameOwnBytecodeControl,reserved)+1",
        ),
    ]
    names += [
        ("COMPARE_SLICE_PARENT", "offsetof(JSStringSlice,parent)"),
        ("COMPARE_SLICE_START", "offsetof(JSStringSlice,start)"),
        ("CONST_JS_TAG_SHORT_BIG_INT", "(uint64_t)(int64_t)JS_TAG_SHORT_BIG_INT"),
        ("CONST_JS_TAG_BIG_INT", "(uint64_t)(int64_t)JS_TAG_BIG_INT"),
    ]
    names += [("SIZE_JSFrameGlobalHint", "sizeof(JSFrameGlobalHint)")]
    names += [
        ("OFF_JSFrameGlobalHint_" + f, "offsetof(JSFrameGlobalHint," + f + ")")
        for f in ("pc", "arithmetic", "atom_slot", "marker")
    ]
    names += [
        (
            "OFF_JSFrameOwnBytecodeControl_symbol_case",
            "offsetof(JSFrameOwnBytecodeControl,reserved)+4",
        ),
        ("CONST_JS_ATOM_undefined", "JS_ATOM_undefined"),
        ("CONST_JS_TAG_SYMBOL", "(uint64_t)(int64_t)JS_TAG_SYMBOL"),
    ]
    names += [
        ("SIZE_" + t, "sizeof(" + t + ")")
        for t in (
            "JSFrameProtoHint",
            "JSFrameProtoPersistentHint",
            "JSFrameProtoDirectData",
            "JSFrameCallSite",
        )
    ]
    names += [
        ("OFF_" + t + "_" + f, "offsetof(" + t + "," + f + ")")
        for t in ("JSFrameProtoHint", "JSFrameProtoPersistentHint")
        for f in ("pc", "holder", "atom_slot", "marker")
    ]
    names += [
        ("OFF_JSFrameProtoDirectData_mode", "offsetof(JSFrameProtoDirectData,mode)"),
        ("CONST_FRAME_CACHE_SLOTS", "FRAME_CACHE_SLOTS"),
    ]
    text = (
        actual.prelude
        + special_enum
        + preamble
        + '#include "src/common/call/interpreter-context-types.inc"\n#include "src/common/call/interpreter-shared-types.inc"\n#include "interpreter-aarch64-property-types.h"\n#include "interpreter-aarch64-own-types.h"\n#include "interpreter-aarch64-proto-types.h"\n#include "interpreter-aarch64-global-types.h"\n'
        + checks
    )
    if arguments_enabled:
        raw_arguments = (source / "src/common/kernel/ordinary-arguments.c").read_text()
        declarations = re.findall(
            r"typedef struct JSFrameArgumentsRecord \{.*?\} JSFrameArgumentsRecord;",
            raw_arguments,
            re.S,
        )
        signatures = re.findall(r"^#define ARGUMENTS_SIGNATURE .+$", raw_arguments, re.M)
        if len(declarations) != 1 or len(signatures) != 1:
            raise ValueError("Review actual complete argument-record declaration")
        text += "\n" + declarations[0] + "\n" + signatures[0] + "\n"
        names += [("SIZE_JSFrameArgumentsRecord", "sizeof(JSFrameArgumentsRecord)")]
        names += [
            ("OFF_JSFrameArgumentsRecord_" + n, "offsetof(JSFrameArgumentsRecord," + n + ")")
            for n in ("argv", "argc", "signature")
        ]
        names += [
            (n, n)
            for n in (
                "FRAME_CALL_META_OFFSET",
                "FRAME_CALL_LOCALS_OFFSET",
                "FRAME_CALL_FORMALS_OFFSET",
            )
        ]
        names += [("CONST_ARGUMENTS_SIGNATURE", "ARGUMENTS_SIGNATURE")]
        names += [("CONST_" + n, n) for n in ("JS_CLASS_ARGUMENTS", "JS_CLASS_MAPPED_ARGUMENTS")]
    if varargs_enabled:
        raw_apply = (source / "src/common/kernel/apply-forward.c").read_text()
        declarations = re.findall(
            r"typedef struct \{\s*JSValueConst \*argv;\s*uint32_t argc, signature;\s*\} JSFrameApplyArgumentRecord;",
            raw_apply,
        )
        if len(declarations) != 1:
            raise ValueError("Review actual source apply-record type")
        text += "\n" + declarations[0] + "\n"
        names += [("SIZE_JSFrameApplyArgumentRecord", "sizeof(JSFrameApplyArgumentRecord)")]
        names += [
            (
                "OFF_JSFrameApplyArgumentRecord_" + n,
                "offsetof(JSFrameApplyArgumentRecord," + n + ")",
            )
            for n in ("argv", "argc", "signature")
        ]
    if indexed_enabled:
        from arm64.workers.indexed import probe_types

        text, names = probe_types(source, text, names)
    if literals_enabled:
        from arm64.workers.literals import probe_types as probe_literal_types

        text, names = probe_literal_types(source, text, names)
    from arm64.workers.numeric_workers import probe_types as probe_numeric_types

    text, names = probe_numeric_types(
        actual, text, names, numeric_workers_enabled, projection_enabled
    )
    if strings_enabled:
        from arm64.workers.strings import probe_types as probe_string_types

        text, names = probe_string_types(source, text, names)
    from arm64.vm.scalar_ops import probe_types as probe_scalar_types

    text, names = probe_scalar_types(text, names, scalar_enabled)
    text += (
        '__attribute__((used,section(".qjs.vm.owned"),aligned(8))) const uint64_t qjs_owned[]={\n'
    )
    text += ",\n".join(e for _, e in names) + "\n};\n"
    owned_elf, values = probe("owned-probe", text, ".qjs.vm.owned")
    if len(values) != len(names):
        raise ValueError("Owned-frame constant extent changed")
    measured = {}
    for group, prefix in (("sizes", "SIZE_"), ("offsets", "OFF_"), ("constants", "CONST_")):
        measured.update((prefix + n.replace(".", "_"), v) for n, v in layout[group].items())
    measured.update(zip((n for n, _ in names), values))
    for signed_key in ("REF_COUNT_OFFSET", "OFF_JSBigInt_header_ref_count"):
        if signed_key in measured and measured[signed_key] >= 1 << 63:
            measured[signed_key] -= 1 << 64
    strict_byte, strict_mask = layout["bits"]["JSFunctionBytecode.is_strict_mode"][0]
    measured.update(
        STRICT_BYTE=strict_byte,
        STRICT_MASK=strict_mask,
        STRICT_SHIFT=(strict_mask & -strict_mask).bit_length() - 1,
    )
    primitive_record = finish_primitives(out, primitive_record, measured)
    own_record = finish_hints(out, own_record, measured)
    proto_record = finish_prototypes(out, proto_record, measured)
    global_record = finish_globals(out, global_record, measured)
    comparison_record = finish_comparisons(out, comparison_record, measured)
    measured["PROPERTY_DESC_TMASK"] = primitive_record["descriptor_tmask"]
    measured["PROPERTY_DESC_NEXT_MASK"] = primitive_record["descriptor_next_mask"]
    measured["HAS_CONSTRUCTORS"] = int(constructor_enabled)
    measured["HAS_ITERATORS"] = int(iterator_enabled)
    measured["HAS_PROPERTY_IC"] = int(actual.receipt["property_ic"])
    array_own_enabled = "-DQJS_AARCH64_ARRAY_OWN" in flags
    measured["HAS_ARRAY_OWN"] = int(array_own_enabled)
    from arm64.vm.scalar_ops import finish as finish_scalar

    scalar_record = finish_scalar(source, out, layout, measured, owned_elf, scalar_enabled)
    measured["HAS_SCALAR_OPS"] = int(scalar_enabled)
    measured["HAS_STACK_INSERT"] = int(stack_insert_enabled)
    measured["HAS_STRING_WORKERS"] = int(strings_enabled)
    measured["HAS_NATIVE_STRING_APPEND"] = int(strings_enabled)
    if strings_enabled:
        for name, key, off in [
            ("len", "STRING_LEN_MASK", layout["bits"]["JSString.len"][0][0]),
            ("kind", "STRING_KIND_MASK", measured["STRING_FLAGS_OFFSET"]),
            ("nonnormal", "STRING_NONNORMAL_MASK", measured["STRING_FLAGS_OFFSET"]),
        ]:
            raw = owned_elf.section_data(owned_elf.section(".qjs.arm.string_" + name))
            mask = int.from_bytes(raw[off : off + 4], "little")
            if not mask or any(raw[:off] + raw[off + 4 :]):
                raise ValueError("Review actual full string bitfield mask")
            measured[key] = mask

    measured["HAS_NUMERIC_WORKERS"] = int(numeric_workers_enabled)
    measured["NUMERIC_LOCAL_MODE_OFFSET"] = (
        layout["offsets"]["JSRuntime.module_loader_has_attr"] + 3
    )
    measured["HAS_LITERALS"] = int(literals_enabled)
    measured["HAS_INDEXED"] = int(indexed_enabled)
    measured["HAS_VARARGS"] = int(varargs_enabled)
    measured["HAS_ARGUMENTS"] = int(arguments_enabled)
    measured["HAS_NULL_PROTO"] = int(null_enabled)
    measured["HAS_FORWARDING"] = int(forwarding_enabled)
    measured["FORWARD_MODE_OFFSET"] = layout["offsets"]["JSFunctionBytecode.pc2line_len"] + 7
    for name, active in layout["bits"].items():
        byte, mask = active[0]
        measured["BIT_" + name.replace(".", "_") + "_BYTE"] = byte
        measured["BIT_" + name.replace(".", "_") + "_MASK"] = mask
    from arm64.workers.properties import generate as generate_properties

    property_record = generate_properties(source, out, layout, actual.receipt["property_ic"])
    from arm64.workers.reference_stores import generate as generate_reference_stores

    reference_record = generate_reference_stores(source, out, layout, primitive_record, measured)
    from arm64.vm.c_return import generate as generate_c_return

    c_return_record = generate_c_return(source, out, actual, probe, preamble, checks)
    put(
        out / "interpreter-aarch64-values.h",
        "\n".join("#define ARM_" + n + " (" + str(v) + ")" for n, v in measured.items()) + "\n",
    )
    table = [".Lslow"] * 256
    for name, handler in HOT.items():
        number = measured["OP_" + name]
        if not 0 <= number < 256 or table[number] != ".Lslow":
            raise ValueError("Duplicate or invalid measured opcode")
        table[number] = ".L" + handler
    put(
        out / "interpreter-aarch64-dispatch.inc",
        "\n".join(".word " + label + " - .Ldispatch_table" for label in table) + "\n",
    )
    from arm64.vm.publication import generate as generate_publication

    publication_record = generate_publication(
        source,
        out,
        table,
        global_bindings=global_enabled,
        comparisons=comparison_enabled,
        constructors=constructor_enabled,
        iterators=iterator_enabled,
        forwarding=forwarding_enabled,
        null_proto=null_enabled,
        arguments=arguments_enabled,
        varargs=varargs_enabled,
        indexed=indexed_enabled,
        literals=literals_enabled,
        numeric=numeric_workers_enabled,
        strings=strings_enabled,
        stack_insert=stack_insert_enabled,
        call_leaves=call_leaves_enabled,
        scalar=scalar_enabled,
    )
    original = actual.core.read_text()
    anchor = "JSValue JS_Call(JSContext *ctx,"
    if original.count(anchor) != 1:
        raise ValueError("Original public call definition changed")
    text = original.replace(anchor, "JSValue JS_LegacyCall(JSContext *ctx,", 1)
    pattern = re.compile(r"(^static JSValue )JS_CallInternal(\([^;{}]*\)\s*\{)", re.M | re.S)
    text, count = pattern.subn(r"\1JS_LegacyCallInternal\2", text)
    if count != 1:
        raise ValueError("Original internal call definition changed")
    cvm_defs = "#define QJS_CVM_USE_LEGACY_CALL_INTERNAL 1\n"
    if a.fast_vm:
        cvm_defs += "#define QJS_CVM_FAST_NATIVE 1\n"
    text = cvm_defs + text
    public = re.search(r"(^JSValue JS_LegacyCall\([^;{}]*\)\s*\{)(.*?^\})", text, re.M | re.S)
    if not public or public[2].count("JS_CallInternal(") != 1:
        raise ValueError("Original public fallback body changed")
    text = (
        text[: public.start(2)]
        + public[2].replace("JS_CallInternal(", "JS_LegacyCallInternal(")
        + text[public.end(2) :]
    )
    from arm64.workers.array_own import generate as generate_array_own

    text, array_own_record = generate_array_own(source, out, text, layout, array_own_enabled)
    loop = (source / "src/common/call/quickjs-interpreter-loop.inc").read_text()
    whitelist = "#define FRAME_OP(id) case OP_##id:"
    ops = '#include "src/common/call/quickjs-interpreter-ops.inc"'
    if loop.count(whitelist) != 1 or loop.count(ops) != 1:
        raise ValueError("Review current-function classifier/semantic boundary")
    loop = loop.replace(
        whitelist,
        """        case OP_special_object:
            if (code[pos+1]!=OP_SPECIAL_OBJECT_THIS_FUNC) return false;
            break;
        case OP_set_name:
            if (getenv("QJS_DISABLE_FRAME_SET_NAME")) return false;
            break;
"""
        + whitelist,
        1,
    )
    loop = loop.replace(
        ops,
        ops
        + '\n#include "src/common/call/interpreter-current-function.inc"\n#include "src/common/call/interpreter-set-name.inc"',
        1,
    )
    if null_enabled:
        loop = loop.replace(
            "src/common/call/interpreter-current-function.inc",
            "src/common/call/interpreter-current-function-null.inc",
        )
    from arm64.workers.arguments import prepare_loop as prepare_argument_loop

    loop = prepare_argument_loop(source, out, loop, arguments_enabled)
    loop = extended_loop(loop, extended_record["enabled"])
    loop = forwarding_policy(source, out, loop, forwarding_record)
    from arm64.vm.admission import generate as generate_admission

    loop, admission_record = generate_admission(
        source,
        out,
        original,
        loop,
        large_default=actual.receipt["property_ic"],
        complete_calls=extended_record["enabled"],
        null_proto=null_enabled,
    )
    dispatch = (source / "src/common/call/quickjs-interpreter-dispatch.inc").read_text()
    old = "FRAME_TARGET(special_object, invalid)"
    if dispatch.count(old) != 1:
        raise ValueError("Review current-function C dispatch owner")
    dispatch = dispatch.replace(old, "FRAME_TARGET(special_object, OP_special_object)", 1)
    old = "FRAME_TARGET(set_name, invalid)"
    if dispatch.count(old) != 1:
        raise ValueError("Review original set_name C dispatch owner")
    dispatch = dispatch.replace(old, "FRAME_TARGET(set_name, OP_set_name)", 1)
    put(out / "interpreter-aarch64-dispatch-c.inc", dispatch)
    loop = loop.replace(
        '#include "src/common/call/quickjs-interpreter-dispatch.inc"',
        '#include "interpreter-aarch64-dispatch-c.inc"',
    )
    host = "        host_frame.prev_frame = state->rt->current_stack_frame;"
    if loop.count(host) != 1:
        raise ValueError("Review typed shared host-frame owner")
    loop = loop.replace(
        host,
        """        host_frame.var_buf = NULL;
        host_frame.var_refs = NULL;
        host_frame.var_ref_count = 0;
        host_frame.is_constructor = false;
        host_frame.cur_gc_obj = NULL;
        host_frame.cur_pc = NULL;
        host_frame.cur_sp = NULL;
"""
        + host,
        1,
    )
    for name, magic in (("generic", 0), ("generic_magic", 1)):
        invoke = "            state->result = object->u.cfunc.c_function." + name + "("
        if loop.count(invoke) != 1:
            raise ValueError("Review actual typed host invocation: " + name)
        loop = loop.replace(
            invoke,
            "#ifdef QJS_AARCH64_VM_INSTRUMENT\n"
            + "            qjs_aarch64_vm_direct_host("
            + str(magic)
            + ");\n#endif\n"
            + invoke,
            1,
        )
    invoke = "    state->result = js_frame_legacy_call(ctx, argv[-1], this_value, argc, vc(argv));"
    if loop.count(invoke) != 1:
        raise ValueError("Review original typed class-host bridge owner")
    loop = loop.replace(
        invoke,
        "#ifdef QJS_AARCH64_VM_INSTRUMENT\n"
        + "    qjs_aarch64_vm_direct_host(2);\n#endif\n"
        + invoke,
        1,
    )
    run_vm = "        event = JS_FrameInterp(&registers);"
    if loop.count(run_vm) != 1:
        raise ValueError("Review root register-VM activation owner")
    loop = loop.replace(run_vm, "        event = JS_FrameAArch64Run(&registers);", 1)
    shared_generator = source / "tools/common/c_extract/generate_shared_host.py"
    shared_spec = importlib.util.spec_from_file_location(
        "qjs_arm_shared_generator", shared_generator
    )
    shared_module = importlib.util.module_from_spec(shared_spec)
    shared_spec.loader.exec_module(shared_module)
    shared_host = shared_module.generate(source, interpreter_text=loop)
    # AArch64 has no foreign native C-invoke prologue committing this snapshot.
    # Charge once,then cache that exact charge before publishing a host scope.
    begin_c = "    js_frame_begin_c(state);"
    if shared_host.count(begin_c) != 2:
        raise ValueError("Review both shared host quota boundaries")
    shared_host = shared_host.replace(begin_c, begin_c + "\n    js_frame_finish_c(state);")
    for target in ("JS_FrameInterpHostDirectShared", "JS_FrameInterpHostShared"):
        signature = "SHARED_CODE int " + target + "("
        if shared_host.count(signature) != 1:
            raise ValueError("Review original native C fallback: " + target)
        shared_host = shared_host.replace(signature, "SHARED_CODE int " + target + "Original(", 1)
    shared_host = (
        "int JS_FrameInterpHostDirectShared(JSFrameRegisterState *,JSValue *,int,bool);\nint JS_FrameInterpHostShared(JSFrameRegisterState *,JSValue *,int,bool);\n"
        + shared_host
    )
    put(out / "interpreter-aarch64-shared-host.h", shared_host)
    shared = (source / "src/common/call/quickjs-interpreter-shared.inc").read_text()
    host_include = '#include "src/common/call/quickjs-interpreter-shared-host.inc"'
    shared_run = "    JS_FrameInterp(&state);"
    if shared.count(host_include) != 1 or shared.count(shared_run) != 1:
        raise ValueError("Review shared host/child source boundaries")
    shared = shared.replace(host_include, '#include "interpreter-aarch64-shared-host.h"', 1)
    shared = shared.replace(shared_run, "    JS_FrameAArch64Run(&state);", 1)
    scoped_slot = "        slot = js_frame_shared_slot();"
    if shared.count(scoped_slot) != 1:
        raise ValueError("Review retained scoped-host macro boundary")
    shared = shared.replace(
        scoped_slot,
        "        js_frame_begin_c(state); "
        + chr(92)
        + "\n"
        + "        js_frame_finish_c(state); "
        + chr(92)
        + "\n"
        + scoped_slot,
        1,
    )
    put(out / "interpreter-aarch64-shared.h", shared)
    put(out / "interpreter-aarch64-loop.h", loop)
    text += (
        "\n#define JS_CallInternal JS_LegacyCallInternal\n"
        + preamble
        + """
#include "src/common/value/arithmetic.inc"
#include "src/common/call/interpreter-slow-host-declare.inc"
static int JS_FrameAArch64Run(struct JSFrameRegisterState *);
#include "interpreter-aarch64-loop.h"
#include "interpreter-aarch64-admission.h"
#include "interpreter-aarch64-shared.h"
#include "src/common/call/interpreter-slow-host.inc"
#ifdef QJS_AARCH64_EXTENDED_CALLS
#include "interpreter-aarch64-construct-host.h"
#endif
#undef JS_CallInternal
static JSValue JS_CallInternal(JSContext *ctx, JSValueConst func_obj,
                               JSValueConst this_obj, JSValueConst new_target,
                               int argc, JSValueConst *argv, int flags)
{
    if ((flags & ~JS_CALL_FLAG_COPY_ARGV) || FRAME_STATE(ctx->rt)==2 ||
        JS_VALUE_GET_TAG(func_obj)!=JS_TAG_OBJECT ||
        JS_VALUE_GET_OBJ(func_obj)->class_id!=JS_CLASS_BYTECODE_FUNCTION)
        return JS_LegacyCallInternal(ctx,func_obj,this_obj,new_target,argc,argv,flags);
    if (unlikely(!FRAME_INTERNAL_STATE(ctx->rt)))
        FRAME_INTERNAL_STATE(ctx->rt)=qjs_internal_interp_internal_disabled()?2:1;
    if (FRAME_INTERNAL_STATE(ctx->rt)!=1)
        return JS_LegacyCallInternal(ctx,func_obj,this_obj,new_target,argc,argv,flags);
    return JS_FrameCallEntryDispatch(ctx,func_obj,this_obj,new_target,argc,argv,flags);
}
JSValue JS_Call(JSContext *ctx, JSValueConst func_obj, JSValueConst this_obj,
                int argc, JSValueConst *argv)
{
    return JS_FrameCallEntryDispatch(ctx,func_obj,this_obj,JS_UNDEFINED,argc,argv,JS_CALL_FLAG_COPY_ARGV);
}
"""
    )
    text += """
#ifdef QJS_AARCH64_VM_INSTRUMENT
/* Passive typed metadata observation. Never classify or mutate admission. */
__attribute__((visibility("hidden"),noipa))
void qjs_aarch64_vm_quota(JSRuntime *rt,uintptr_t words[2])
{
    words[0]=rt->stack_top;words[1]=rt->stack_limit;
}
__attribute__((visibility("hidden"),noipa))
int qjs_aarch64_vm_function_info(JSValueConst function, uintptr_t *words)
{
    JSFunctionBytecode *b;
    if (JS_VALUE_GET_TAG(function)!=JS_TAG_OBJECT ||
        JS_VALUE_GET_OBJ(function)->class_id!=JS_CLASS_BYTECODE_FUNCTION) return 0;
    b=JS_VALUE_GET_OBJ(function)->u.func.function_bytecode;
    words[0]=FRAME_KIND(b);words[1]=b->arg_count;words[2]=b->var_count;
    words[3]=b->var_ref_count;words[4]=b->byte_code_len;words[5]=b->stack_size;
    return 1;
}
__attribute__((visibility("hidden"),noipa))
size_t qjs_aarch64_vm_function_code(JSValueConst function,const uint8_t **code)
{
    if (JS_VALUE_GET_TAG(function)!=JS_TAG_OBJECT ||
        JS_VALUE_GET_OBJ(function)->class_id!=JS_CLASS_BYTECODE_FUNCTION) return 0;
    JSFunctionBytecode *b=JS_VALUE_GET_OBJ(function)->u.func.function_bytecode;
    *code=b->byte_code_buf;return b->byte_code_len;
}
#endif
"""
    for name, expression in names[: len(owned) + len(offsets)]:
        text += (
            "_Static_assert("
            + expression
            + " == "
            + str(measured[name])
            + ', "AArch64 owned frame: '
            + name
            + '");\n'
        )
    text += '_Static_assert(__builtin_types_compatible_p(__typeof__(JS_FrameInterpHostDirect), int(JSFrameRegisterState *, JSValue *, int, bool)), "Actual typed host bridge ABI");\n'
    text += '_Static_assert(__builtin_types_compatible_p(__typeof__(JS_FrameInterpHost), int(JSFrameRegisterState *, JSValue *, int, bool)), "Actual typed class-host bridge ABI");\n'
    for target in ("JS_FrameInterpHostDirectShared", "JS_FrameInterpHostShared"):
        text += (
            "_Static_assert(__builtin_types_compatible_p(__typeof__("
            + target
            + '), int(JSFrameRegisterState *, JSValue *, int, bool)), "Actual AAPCS64 shared host ABI");\n'
        )
    from c_workers import module as worker_module
    from arm64.workers.prepared_callbacks_arm64 import generate as generate_callbacks

    text, callback_record = generate_callbacks(
        source, out, text, worker_module(source, "object-adapter-c")
    )
    from c_workers import generate_async_generator

    text, async_record = generate_async_generator(
        source,
        out,
        text,
        contract_rel="src/arm64/linux/abi/async-generator.json",
        public_abi="actual GCC AAPCS64 C",
        write_receipt=True,
    )
    if measured["REF_COUNT_OFFSET"] != -4:
        raise ValueError(
            "JSON requires the actual reviewed allocator-prefix reference-count header"
        )
    from json_workers import generate as generate_json
    from arm64.workers.json_worker import arch_adapt as adapt_arm_json

    text, json_record = generate_json(
        source,
        out,
        text,
        worker_module(source, "object-adapter-c"),
        dict(
            reference_count_model="allocator-prefix",
            offsets=layout["offsets"],
            compiler_input=str(actual.core),
            property_ic=actual.receipt["property_ic"],
        ),
        arch_adapt=adapt_arm_json,
    )
    from arm64.workers.regexp_workers_arm64 import generate as generate_regexp

    text, regexp_record = generate_regexp(
        source,
        out,
        text,
        dict(
            reference_count_model="allocator-prefix",
            offsets=layout["offsets"],
            compiler_input=str(actual.core),
        ),
    )
    from arm64.vm.c_entry import generate as generate_c_entry

    text, c_entry_record = generate_c_entry(source, out, text)
    from arm64.workers.array_workers import generate as generate_array_workers

    text, array_workers_record = generate_array_workers(
        source, out, text, "-DQJS_AARCH64_ARRAY_WORKERS" in flags
    )
    from arm64.workers.null_proto import generate as generate_null

    text, null_record = generate_null(source, out, text, layout, null_enabled)
    for target in ("JS_FrameAArch64HostDirectValue", "JS_FrameAArch64HostValue"):
        text += (
            "_Static_assert(__builtin_types_compatible_p(__typeof__("
            + target
            + '), JSValue(JSFrameRegisterState *,JSValue *,int,bool)),"Actual target aggregate host return");\n'
        )
    text += '\n#include "interpreter-aarch64-property-primitives.h"\n'
    from arm64.workers.property_hints import generate as generate_hints

    text, own_record = generate_hints(
        source, out, text, dict(compiler_input=str(actual.core)), own_record
    )
    text += '\n#include "interpreter-aarch64-proto.h"\n#include "interpreter-aarch64-globals.h"\n'
    from arm64.workers.comparisons import generate_core, finish_slow as finish_comparison_slow

    text = generate_core(out, text, comparison_record)
    from arm64.workers.arguments import generate as generate_arguments

    text, arguments_record = generate_arguments(
        source, out, text, layout, original, arguments_enabled
    )
    from arm64.workers.varargs import generate as generate_varargs

    text, varargs_record = generate_varargs(source, out, text, layout, varargs_enabled)
    from arm64.workers.indexed import generate as generate_indexed

    text, indexed_record = generate_indexed(source, out, text, layout, indexed_enabled)
    from arm64.workers.literals import generate as generate_literals

    text, literals_record = generate_literals(source, out, text, layout, literals_enabled)
    from arm64.workers.numeric_workers import generate as generate_numeric_workers

    text, numeric_workers_record = generate_numeric_workers(
        source, out, text, layout, actual, numeric_workers_enabled, projection_enabled, measured
    )
    from arm64.workers.strings import generate as generate_strings

    text, strings_record = generate_strings(
        source,
        out,
        text,
        dict(
            layout,
            property_ic=actual.receipt["property_ic"],
            native_string_append=bool(measured["HAS_NATIVE_STRING_APPEND"]),
        ),
        strings_enabled,
    )
    from arm64.workers.stack_insert import generate as generate_stack_insert

    text, stack_insert_record = generate_stack_insert(source, out, text, stack_insert_enabled)
    from arm64.workers.call_leaves import generate as generate_call_leaves

    text, call_leaves_record = generate_call_leaves(source, out, text, actual, call_leaves_enabled)
    put(core_path, text)
    generator = source / "tools/common/c_extract/generate_slow_c.py"
    spec = importlib.util.spec_from_file_location("qjs_arm_slow_generator", generator)
    slow = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(slow)
    slow.generate(source, out / "quickjs-interpreter-slow.h", interpreter_text=loop)
    slow_path = out / "quickjs-interpreter-slow.h"
    text = slow_path.read_text()
    if arguments_enabled:
        condition = "#if defined(QJS_FRAME_ARGUMENTS_CONSTRUCT_GUARD)"
        if text.count(condition) != 1:
            raise ValueError("Review argument constructor decline boundary")
        text = text.replace(condition, "#if defined(QJS_AARCH64_ARGUMENTS)", 1)
    legacy_call = (
        "ret_val = js_frame_legacy_call(ctx, callee, call_this, call_argc, vc(call_argv));"
    )
    if text.count(legacy_call) != 1:
        raise ValueError("Review coherent C-step host-call owner")
    text = text.replace(
        legacy_call,
        "ret_val = js_frame_slow_host_call(state, frame, segment, used_bytes, pc, sp, ctx, callee, call_this, call_argc, vc(call_argv));",
        1,
    )
    text = text.replace(
        '#include "src/common/call/quickjs-interpreter-dispatch.inc"',
        '#include "interpreter-aarch64-dispatch-c.inc"',
    )
    signature = "FRAME_CODE int JS_FrameInterpSlow(JSFrameRegisterState *state)"
    entry = "    goto execute_opcode;\n"
    end = "    return event;\n}\n#undef CASE"
    if text.count(signature) != 1 or text.count(entry) != 1 or text.count(end) != 1:
        raise ValueError("Review source-derived ARM return continuation boundary")
    text = text.replace(
        signature,
        "static FRAME_CODE int JS_AArch64Step(JSFrameRegisterState *state, unsigned resume)",
        1,
    )
    text = text.replace(
        entry,
        "    if (resume==1) { ret_val=state->result; goto return_frame; }\n"
        + "    if (resume==2) { ret_val=state->result; goto finish_call; }\n"
        + entry,
        1,
    )
    wrappers = """    return event;
}
FRAME_CODE int JS_FrameInterpSlow(JSFrameRegisterState *state)
{
    /* A general C opcode can retire/reuse frames or pad dormant window bytes.
     * Invalidate its activation-owned builtin geometry before the real step. */
    state->arities=0;
#ifdef QJS_AARCH64_VM_INSTRUMENT
    qjs_aarch64_vm_slow_entry(*state->pc);
#endif
    return JS_AArch64Step(state, 0);
}
FRAME_CODE int JS_FrameAArch64Return(JSFrameRegisterState *state)
{
#ifdef QJS_AARCH64_VM_INSTRUMENT
    qjs_aarch64_vm_return_resume();
#endif
    return JS_AArch64Step(state, 1);
}
FRAME_CODE int JS_FrameAArch64FinishCall(JSFrameRegisterState *state)
{
    return JS_AArch64Step(state, 2);
}
#undef CASE"""
    text = text.replace(end, wrappers, 1)
    put(slow_path, text)
    finish_comparison_slow(out, comparison_record)
    extended_record = finish_extended(
        source,
        out,
        layout,
        loop,
        extended_record,
        constructor_record,
        iterator_record,
        varargs=varargs_enabled,
    )
    from arm64.workers.varargs import finish as finish_varargs

    varargs_record = finish_varargs(out)
    forwarding_record = finish_forwarding(
        source, out, forwarding_record, extended_record, constructor_record, iterator_record
    )
    from arm64.workers.indexed import finish as finish_indexed

    indexed_record = finish_indexed(out, indexed_record)
    if indexed_enabled:
        constructor_record = json.loads((out / "CONSTRUCTORS.json").read_text())
        iterator_record = json.loads((out / "ITERATORS.json").read_text())
        extended_record = json.loads((out / "EXTENDED-CALLS.json").read_text())
    from arm64.workers.literals import finish as finish_literals

    literals_record = finish_literals(out, literals_record)
    if literals_enabled:
        indexed_record = json.loads((out / "INDEXED.json").read_text())
    if varargs_enabled:
        varargs_record = finish_varargs(out)
    receipt = dict(
        schema=1,
        platform="linux-aarch64-aapcs64",
        qualification="experimental functional tier",
        target=triple,
        probe_executed=False,
        native_vm=True,
        native_call_return=dict(
            child="prepared readonly provided/missing window or owned writable/captured formals,including missing arity and local capture tables",
            captures="align16 actual pointer table after operand capacity;all pointers NULL before publication;original C closure/close owners",
            captured_control="QJS_DISABLE_AARCH64_CAPTURED_ENTRY",
            owned_missing_control="QJS_DISABLE_AARCH64_OWNED_MISSING",
            missing_window="original owner-segment last-frame/capture-table guards, padding and combined quota",
            missing_window_control="QJS_DISABLE_AARCH64_MISSING_WINDOW",
            returns="guarded cleanup retaining every heap owner; root and tail continuations",
            observing_cleanup="source-derived C return resume",
            frame_size=measured["SIZE_JSFrame"],
            state_size=measured["SIZE_JSFrameRegisterState"],
        ),
        native_host=dict(
            bridge="JS_FrameInterpHostDirectShared",
            semantic_bridge="JS_FrameInterpHostDirect",
            signatures=["generic", "generic_magic"],
            class_bridge="JS_FrameInterpHostShared",
            class_semantic_bridge="JS_FrameInterpHost",
            class_dispatch="original typed JSClassCall and C prototype owners",
            consumer="source-derived C finish_call",
            control="QJS_DISABLE_DIRECT_HOST_CALL",
            class_control="QJS_DISABLE_AARCH64_CLASS_HOST",
        ),
        shared_entry=dict(
            tls="Compiler-managed ELF TLS; actual common anchor type",
            host_bridges=["JS_FrameInterpHostDirectShared", "JS_FrameInterpHostShared"],
            vm_owner="JS_FrameAArch64Run with kind3 blocked activation",
            child="Original synchronous arena/ownership/quota/capture owner",
            control="QJS_DISABLE_SHARED_ENTRY; QJS_RETAIN_SCOPED_HOST",
            c_step="Original guarded coherent slow-host publisher",
        ),
        constructors=constructor_record,
        constructors_receipt_sha256=sha(out / "CONSTRUCTORS.json"),
        iterators=iterator_record,
        iterators_receipt_sha256=sha(out / "ITERATORS.json"),
        extended_calls=extended_record,
        extended_calls_receipt_sha256=sha(out / "EXTENDED-CALLS.json"),
        comparisons=comparison_record,
        comparisons_receipt_sha256=sha(out / "COMPARISONS.json"),
        forwarding=forwarding_record,
        forwarding_receipt_sha256=sha(out / "FORWARDING.json"),
        scalar_ops=scalar_record,
        scalar_receipt_sha256=sha(out / "SCALAR-OPS.json"),
        call_leaves=call_leaves_record,
        call_leaves_receipt_sha256=sha(out / "CALL-LEAVES.json"),
        stack_insert=stack_insert_record,
        stack_insert_receipt_sha256=sha(out / "STACK-INSERT.json"),
        strings=strings_record,
        strings_receipt_sha256=sha(out / "STRING-WORKERS.json"),
        numeric_workers=numeric_workers_record,
        numeric_workers_receipt_sha256=sha(out / "NUMERIC-WORKERS.json"),
        literals=literals_record,
        literals_receipt_sha256=sha(out / "LITERALS.json"),
        indexed=indexed_record,
        indexed_receipt_sha256=sha(out / "INDEXED.json"),
        varargs=varargs_record,
        varargs_receipt_sha256=sha(out / "VARARGS.json"),
        arguments=arguments_record,
        arguments_receipt_sha256=sha(out / "ARGUMENTS.json"),
        null_proto=null_record,
        null_proto_receipt_sha256=sha(out / "NULL-PROTO.json"),
        array_workers=array_workers_record,
        array_workers_receipt_sha256=sha(out / "ARRAY-WORKERS.json"),
        array_own=array_own_record,
        array_own_receipt_sha256=sha(out / "ARRAY-OWN.json"),
        core=layout,
        owned=measured,
        native_opcodes=sorted(HOT),
        call_return_owner="native prepared readonly/owned/captured children and guarded non-finalizing returns; original C observing cleanup",
        unsupported_instruction="C one-step",
        unsupported_function="legacy interpreter",
        compiler_input_sha256=sha(actual.core),
        core_sha256=sha(core_path),
        slow_sha256=sha(out / "quickjs-interpreter-slow.h"),
        assembly_sha256=sha(source / "asm/arm64/linux/interpreter.S"),
        common_ops_sha256=sha(source / "asm/arm64/common/register-ops.inc"),
        common_calls_sha256=sha(source / "asm/arm64/common/register-call.inc"),
        slots_sha256=sha(source / "asm/arm64/common/register-slots.inc"),
        references_sha256=sha(source / "asm/arm64/common/register-references.inc"),
        window_contract_sha256=sha(window_path),
        capture_contract_sha256=sha(capture_path),
        set_name_sha256=sha(name_fragment),
        shared_sha256=sha(out / "interpreter-aarch64-shared.h"),
        shared_host_sha256=sha(out / "interpreter-aarch64-shared-host.h"),
        shared_source_sha256=sha(source / "src/common/call/quickjs-interpreter-shared.inc"),
        shared_types_sha256=sha(source / "src/common/call/interpreter-shared-types.inc"),
        shared_tls_sha256=sha(source / "src/common/linux/interpreter-linux-shared-tls.inc"),
        shared_supplements_sha256=sha(
            source / "src/arm64/linux/interpreter-shared-supplements.inc"
        ),
        slow_host_sha256=sha(source / "src/common/call/interpreter-slow-host.inc"),
        shared_generator_sha256=sha(shared_generator),
        shared_contract_sha256=sha(shared_contract),
        prepared_callbacks=callback_record,
        callback_contract_sha256=sha(callback_contract),
        callback_generator_sha256=sha(source / "tools/arm64/workers/prepared_callbacks_arm64.py"),
        callback_selector_sha256=sha(
            source / "src/common/linux/interpreter-linux-prepared-callback.inc"
        ),
        async_generator=async_record,
        async_worker_sha256=sha(out / "quickjs-linux-c-workers.h"),
        async_receipt_sha256=sha(out / "ASYNC-GENERATOR.json"),
        async_contract_sha256=sha(source / "src/arm64/linux/abi/async-generator.json"),
        c_workers_generator_sha256=sha(source / "tools/common/elf/c_workers.py"),
        json_workers=json_record,
        json_worker_sha256=sha(out / "quickjs-linux-json.h"),
        json_receipt_sha256=sha(out / "JSON-WORKERS.json"),
        json_contract_sha256=sha(json_contract),
        json_generator_sha256=sha(source / "tools/common/elf/json_workers.py"),
        json_arm_generator_sha256=sha(source / "tools/arm64/workers/json_worker.py"),
        json_vector_sha256=sha(source / "src/arm64/common/json-vector.h"),
        regexp_workers=regexp_record,
        regexp_worker_sha256=sha(out / "quickjs-linux-regexp.h"),
        regexp_receipt_sha256=sha(out / "REGEXP-WORKERS.json"),
        regexp_contract_sha256=sha(regexp_contract),
        regexp_generator_sha256=sha(source / "tools/arm64/workers/regexp_workers_arm64.py"),
        native_admission=admission_record,
        deferred_publication=publication_record,
        c_entry=c_entry_record,
        c_return=c_return_record,
        properties=property_record,
        global_bindings=global_record,
        global_bindings_receipt_sha256=sha(out / "GLOBAL-BINDINGS.json"),
        reference_stores=reference_record,
        reference_stores_receipt_sha256=sha(out / "REFERENCE-STORES.json"),
        property_prototypes=proto_record,
        property_prototypes_receipt_sha256=sha(out / "PROPERTY-PROTOTYPES.json"),
        property_hints=own_record,
        property_hints_receipt_sha256=sha(out / "PROPERTY-HINTS.json"),
        property_primitives=primitive_record,
        property_primitives_receipt_sha256=sha(out / "PROPERTY-PRIMITIVES.json"),
        property_primitives_generator_sha256=sha(
            source / "tools/arm64/workers/property_primitives.py"
        ),
        property_primitives_contract_sha256=sha(
            source / "src/arm64/linux/abi/property-primitives.json"
        ),
        property_primitives_source_sha256=sha(
            source / "asm/arm64/common/register-property-primitives.inc"
        ),
        properties_receipt_sha256=sha(out / "PROPERTIES.json"),
        properties_generator_sha256=sha(source / "tools/arm64/workers/properties.py"),
        properties_contract_sha256=sha(source / "src/arm64/linux/abi/properties.json"),
        properties_source_sha256=sha(source / "asm/arm64/common/register-property-ic.inc"),
        c_return_receipt_sha256=sha(out / "C-RETURN.json"),
        c_return_generator_sha256=sha(source / "tools/arm64/vm/c_return.py"),
        c_return_contract_sha256=sha(source / "src/arm64/linux/abi/c-return.json"),
        host_return_source_sha256=sha(source / "asm/arm64/common/register-host-return.inc"),
        c_entry_receipt_sha256=sha(out / "C-ENTRY.json"),
        c_entry_generator_sha256=sha(source / "tools/arm64/vm/c_entry.py"),
        c_entry_source_sha256=sha(source / "src/arm64/linux/interpreter-c-entry.inc"),
        c_entry_contract_sha256=sha(source / "src/arm64/linux/abi/c-entry.json"),
        publication_receipt_sha256=sha(out / "PUBLICATION.json"),
        publication_contract_sha256=sha(source / "src/arm64/linux/abi/publication.json"),
        publication_generator_sha256=sha(source / "tools/arm64/vm/publication.py"),
        admission_contract_sha256=sha(admission_contract),
        admission_generator_sha256=sha(source / "tools/arm64/vm/admission.py"),
        regexp_opcode_sha256=sha(source / "asm/arm64/common/register-regexp.inc"),
        branches_sha256=sha(source / "asm/arm64/common/register-branch.inc"),
        numeric_sha256=sha(source / "asm/arm64/common/register-numeric.inc"),
        numeric_contract_sha256=sha(numeric_path),
        policy_sha256=sha(source / "src/arm64/linux/interpreter-policy.c"),
        policy_header_sha256=sha(source / "src/arm64/linux/interpreter-policy.h"),
        observer_sha256=sha(source / "src/arm64/linux/interpreter-observe.c"),
        observer_header_sha256=sha(source / "src/arm64/linux/interpreter-observe.h"),
        current_function_sha256=sha(fragment),
        loop_sha256=sha(out / "interpreter-aarch64-loop.h"),
        c_dispatch_sha256=sha(out / "interpreter-aarch64-dispatch-c.inc"),
        generator_sha256=sha(Path(__file__)),
        flags=flags,
    )
    from arm64.vm.number_dataflow import generate as generate_numbers

    receipt["number_dataflow"] = generate_numbers(
        source, out, a.number_dataflow, linear_return=a.linear_return
    )
    if a.fast_vm:
        from arm64.vm.specialize import specialize as specialize_fast_vm

        receipt["fast_vm"] = specialize_fast_vm(source, out, True, receipt)
    put(out / "VM.json", json.dumps(receipt, indent=2) + "\n")
    print(
        "AARCH64_REGISTER_TIER_GENERATED",
        len(HOT),
        "native handlers; guarded JS calls/returns and typed host boundaries",
    )


if __name__ == "__main__":
    main()
