"""Pure C regex definitions and identifier discovery for source adapters."""

import re


FUNCTION = re.compile(
    r"^((?:(?:static|inline|no_inline|__maybe_unused)\s+)*"
    r"(?:[\w]+\s+|\*\s*)+?)(\w+)\s*\(([^;{}]*)\)\s*\{(.*?)^\}",
    re.M | re.S,
)
MACRO = re.compile(r"^#define\s+(\w+)(?:[^\n]*\\\n)*[^\n]*", re.M)

# These helpers were inlined into the original interpreter's hot paths.
# Keeping them local avoids adding an ABI boundary per value or global load.
# Cold semantic helpers stay shared with the unchanged core.
HOT_LOCAL_HELPERS = {
    "js_dup",
    "js_bool",
    "js_int32",
    "js_uint32",
    "js_float64",
    "js_number",
    "__JS_NewShortBigInt",
    "hash_atom",
    "JS_GetGlobalVar",
    "JS_SetPropertyInternal",
    "needs_backtrace",
    # These retained argument builders were already local/inlined. Copy this
    # upstream's implementation, including its VarRef ownership protocol.
    "js_dup_shape",
    "add_gc_object",
    "js_create_var_ref",
    "js_build_arguments",
    "js_build_mapped_arguments",
}

# These small helpers are newly needed by the primitive BigInt boundary. Any
# compiler-emitted out-of-line copy belongs beside that boundary, so introducing
# it cannot shift existing .text helpers. The core's definitions are untouched.
BIGINT_ISLAND_HELPERS = {"JS_CompactBigInt", "js_bigint_set_si", "js_bigint_set_short"}


def identifiers(text):
    text = re.sub(
        r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'', " ", text, flags=re.S
    )
    return set(re.findall(r"\b\w+\b", text))
