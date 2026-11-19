"""Generate a compiler-executed ABI probe from the selected upstream source.

Private types always come from quickjs.c in --source. No frozen type view or
historical binary supplies a field offset. The probe also measures bitfields,
which cannot be inspected with offsetof and can differ between cl and GCC.
"""

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from paths import source_file

MARKER = "static inline bool double_is_int32"
SIZES = (
    "JSValue",
    "JSGCObjectHeader",
    "JSRuntime",
    "JSContext",
    "JSObject",
    "JSFunctionBytecode",
    "JSStackFrame",
    "JSVarRef",
    "JSString",
    "JSStringRope",
    "JSShape",
    "JSShapeProperty",
    "JSProperty",
    "JSBigInt",
    "JSCFunctionType",
    "JSArrayBuffer",
    "JSTypedArray",
)
FIELDS = {
    "JSValue": ("tag",),
    "JSRuntime": (
        "malloc_state",
        "rt_info",
        "atom_hash_size",
        "atom_array",
        "current_exception",
        "in_free",
        "current_stack_frame",
        "stack_size",
        "stack_top",
        "stack_limit",
        "interrupt_handler",
        "interrupt_opaque",
        "module_normalize_has_attr",
        "normalize_u",
        "module_loader_has_attr",
        "u",
        "gc_obj_list",
        "gc_phase",
        "can_block",
        "shape_hash_bits",
    ),
    "JSContext": ("rt", "class_proto", "global_obj", "global_var_obj", "interrupt_counter"),
    "JSObject": (
        "header",
        "class_id",
        "shape",
        "prop",
        "first_weak_ref",
        "u.func.function_bytecode",
        "u.func.var_refs",
        "u.func.home_object",
        "u.cfunc.realm",
        "u.cfunc.c_function",
        "u.cfunc.length",
        "u.cfunc.cproto",
        "u.cfunc.magic",
        "u.array.u1",
        "u.array.u",
        "u.array.count",
        "u.regexp",
        "u.array.u.values",
        "u.typed_array",
        "u.array_buffer",
        "u.array.u.int32_ptr",
    ),
    "JSFunctionBytecode": (
        "header",
        "byte_code_buf",
        "byte_code_len",
        "func_name",
        "vardefs",
        "closure_var",
        "arg_count",
        "var_count",
        "defined_arg_count",
        "stack_size",
        "var_ref_count",
        "closure_var_count",
        "cpool_count",
        "cpool",
        "realm",
        "pc2line_len",
        "pc2line_buf",
    ),
    "JSStackFrame": (
        "prev_frame",
        "cur_func",
        "arg_buf",
        "var_buf",
        "var_refs",
        "cur_pc",
        "var_ref_count",
        "arg_count",
        "is_strict_mode",
        "cur_sp",
    ),
    "JSVarRef": ("header", "pvalue", "value"),
    "JSString": ("hash_next", "first_weak_ref"),
    "JSStringRope": ("len",),
    "JSShape": (
        "header",
        "prop_count",
        "prop_size",
        "proto",
        "prop",
        "prop_hash_mask",
        "hash",
        "is_hashed",
        "deleted_prop_count",
    ),
    "JSShapeProperty": ("atom",),
    "JSArrayBuffer": ("immutable",),
    "JSTypedArray": ("buffer",),
    "JSBigInt": ("len", "tab"),
}
BITS = {
    "JSRuntime": ("dump_flags",),
    "JSContext": ("std_array_prototype",),
    "JSObject": (
        "is_prototype",
        "extensible",
        "free_mark",
        "is_exotic",
        "fast_array",
        "is_constructor",
        "is_HTMLDDA",
    ),
    "JSString": ("len", "is_wide_char", "hash", "kind", "atom_type"),
    "JSFunctionBytecode": ("is_strict_mode", "func_kind", "is_derived_class_constructor"),
    "JSShapeProperty": ("flags",),
}
CONSTANTS = (
    "JS_TAG_STRING",
    "JS_TAG_STRING_ROPE",
    "JS_TAG_OBJECT",
    "JS_TAG_EXCEPTION",
    "JS_CLASS_OBJECT",
    "JS_CLASS_ARRAY",
    "JS_CLASS_BYTECODE_FUNCTION",
    "JS_CLASS_C_FUNCTION",
    "JS_CLASS_STRING",
    "JS_PROP_TMASK",
    "JS_ATOM_length",
    "OP_COUNT",
    "JS_PROP_INITIAL_SIZE",
)


def printf(format_string, *arguments):
    return (
        "    printf("
        + json.dumps(format_string)
        + (", " + ", ".join(arguments) if arguments else "")
        + ");"
    )


def prelude(text):
    if text.count(MARKER) != 1:
        raise ValueError("Upstream private-type boundary changed; review the probe")
    body = text[: text.index(MARKER)]
    # A type-only header must not define an otherwise unrelated public API.
    body = re.sub(r"^const char\* JS_GetVersion\(void\) \{.*?^\}", "", body, flags=re.M | re.S)
    return body


def struct_body(text, name):
    match = re.search(r"\bstruct\s+" + re.escape(name) + r"\s*\{", text)
    if not match:
        raise ValueError("Missing original type " + name)
    start = match.end()
    depth = 1
    # These definitions have no brace-containing strings; strip comments so
    # comments about layouts cannot affect the balanced type boundary.
    tail = re.sub(r"/\*.*?\*/|//[^\n]*", "", text[start:], flags=re.S)
    for index, char in enumerate(tail):
        depth += (char == "{") - (char == "}")
        if not depth:
            return tail[:index]
    raise ValueError("Unclosed original type " + name)


def generate(source, output):
    text = source_file(source, "quickjs.c").read_text(encoding="utf-8")
    types = prelude(text)
    prefix_model = "JSMallocBlockHeader" in types and "js_rc(" in types
    fields = {name: list(values) for name, values in FIELDS.items()}
    bits = {name: list(values) for name, values in BITS.items()}
    sizes = list(SIZES)
    if "is_constructor" in struct_body(types, "JSStackFrame"):
        fields["JSStackFrame"] += ["is_constructor", "cur_gc_obj"]
    varref = struct_body(types, "JSVarRef")
    fields["JSVarRef"] += [
        name
        for name in ("is_detached", "is_lexical", "is_const", "is_coro")
        if re.search(r"\b" + name + r"\s*;", varref)
    ]
    if not re.search(r"\bprop\s*\[", struct_body(types, "JSShape")):
        fields["JSShape"].remove("prop")
        fields["JSShape"].append("hash_table")
    if prefix_model:
        sizes += ["JSMallocBlockHeader", "JSArenaState"]
        fields["JSMallocBlockHeader"] = ["ref_count", "user_data"]
        bits["JSMallocBlockHeader"] = ["gc_obj_type", "mark"]
    else:
        fields["JSGCObjectHeader"] = ["ref_count", "link"]
        fields["JSString"] += ["header"]
        bits["JSGCObjectHeader"] = ["gc_obj_type", "mark"]
    # gc_phase is itself a bitfield on both supported upstream bases.
    fields["JSRuntime"].remove("gc_phase")
    lines = [
        "/* Generated ABI measurement; compile with the engine's own toolchain flags. */",
        '#include "interpreter-layout-types.h"',
        "#include <stddef.h>",
        "static void abi_bits(const unsigned char *bytes, size_t count) {",
        '    int first = 1; printf("[");',
        "    for (size_t i = 0; i < count; ++i) if (bytes[i]) {",
        '        printf("%s[%zu,%u]", first ? "" : ",", i, (unsigned)bytes[i]); first = 0;',
        "    }",
        '    printf("]");',
        "}",
        "int main(void) {",
    ]
    identity = hashlib.sha256(text.encode("utf-8")).hexdigest()
    header = {
        "schema": 1,
        "source_sha256": identity,
        "reference_count_model": "allocator-prefix" if prefix_model else "inline-header",
    }
    lines += [printf(json.dumps(header)[:-1] + ',"sizes":{')]
    for index, name in enumerate(sizes):
        lines.append(printf(("," if index else "") + '"' + name + '":%zu', "sizeof(" + name + ")"))
    lines += [printf('},"offsets":{')]
    index = 0
    for name, members in fields.items():
        for member in members:
            lines.append(
                printf(
                    ("," if index else "") + '"' + name + "." + member + '":%zu',
                    "offsetof(" + name + ", " + member + ")",
                )
            )
            index += 1
    lines += [printf('},"bits":{')]
    index = 0
    for name, members in bits.items():
        for member in members:
            lines += [
                "    { " + name + " value = {0}; value." + member + " = 1;",
                printf(("," if index else "") + '"' + name + "." + member + '":'),
                "      abi_bits((const unsigned char *)&value, sizeof(value)); }",
            ]
            index += 1
    lines += [printf('},"constants":{')]
    for index, name in enumerate(CONSTANTS):
        lines.append(printf(("," if index else "") + '"' + name + '":%lld', "(long long)" + name))
    lines += [printf("}}\n"), "    return 0;", "}"]
    output.parent.mkdir(parents=True, exist_ok=True)
    (output.parent / "interpreter-layout-types.h").write_text(types, encoding="utf-8", newline="\n")
    output.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    generate(args.source.resolve(), args.output.resolve())


if __name__ == "__main__":
    main()
