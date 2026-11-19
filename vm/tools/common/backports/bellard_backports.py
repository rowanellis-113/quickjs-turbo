"""Small, source-guarded adaptations of Bellard's 2026-06-04 optimizations.

The checked-in upstream inputs and public ABI stay intact. This module is
consumed by the existing compiler launcher, not by the engine at runtime.
"""

import hashlib

HEADER_SHA256 = "8011dd97fbeb1cc551020f90dde4b4f21f83a6145b6254b5e815f6d885ed3874"
VALUE_COMMIT = "10c81b1989de2d2e8d482d252b160a34f215d3e2"
MIXED_COMMIT = "8e97f24044102b5793524ab22b037ca75f536319"
ARRAY_APPEND_RELEASE = "3d5e064e9dd67c70f7962836505a7fa067bf0a4e"
MAP_HASH_COMMIT = "a151ce19e5aa684c4c70346fd45f27cc9cdbef93"


def replace_once(text, before, after, label):
    if text.count(before) != 1:
        raise ValueError("review Bellard backport anchor: " + label)
    return text.replace(before, after, 1)


def writable_array_append(block):
    """Apply the release's length-writability guard to the pinned append lane.

    Growing the dense count inside an existing length is legal. Growing a
    readonly length must instead enter the complete original property setter.
    Keep the physical line count for source-bound creator/call proofs.
    """
    block = replace_once(
        block,
        "if (likely(new_len <= p->u.array.u1.size)) {",
        "if (likely(new_len <= p->u.array.u1.size)) { if (unlikely(new_len > array_len && !(p->shape->prop[0].flags & JS_PROP_WRITABLE))) goto bellard_array_append_slow;",
        "array append readonly length",
    )
    return replace_once(
        block,
        "                sf->cur_pc = pc;",
        "                bellard_array_append_slow: sf->cur_pc = pc;",
        "array append complete setter",
    )


def map_pointer_hash(text):
    """Adapt Bellard's pointer multiply/high-word mixing to NG's uint32 hash.

    NG keeps its original power-of-two mask, table layout and equality rules.
    Mix before narrowing so aligned pointers do not retain empty low bits.
    uint64 arithmetic also has defined behavior for 32-bit pointer inputs.
    """
    return replace_once(
        text,
        "        h = (uintptr_t)JS_VALUE_GET_PTR(key) * 3163;",
        "        return (uint32_t)(((uint64_t)((uintptr_t)JS_VALUE_GET_PTR(key) ^ tag) * UINT64_C(0x61C8864680B583EB)) >> 32);",
        "Map/Set object and symbol pointer hash",
    )


def value_header(original, narrow_readers=False):
    text = original.read_text(encoding="utf-8")
    if hashlib.sha256(text.encode()).hexdigest() != HEADER_SHA256:
        raise ValueError("review Bellard value initialization against changed quickjs.h")
    # Retain .int32 for source compatibility. CMake selects narrow readers only
    # for GNU C when requested; other compilers keep the exact qualified B3 header.
    text = replace_once(
        text,
        "typedef union JSValueUnion {\n    int32_t int32;",
        "typedef union JSValueUnion {\n    uint64_t uint64;\n    int32_t int32;",
        "value union",
    )
    for before, after in [
        (
            "#define JS_VALUE_GET_INT(v) ((v).u.int32)",
            "#define JS_VALUE_GET_INT(v) ((int32_t)(v).u.uint64)",
        ),
        (
            "#define JS_VALUE_GET_BOOL(v) ((v).u.int32)",
            "#define JS_VALUE_GET_BOOL(v) ((int32_t)(v).u.uint64)",
        ),
    ]:
        if not narrow_readers:
            text = replace_once(text, before, after, before)
    for before, after in [
        ("    v.u.int32 = int32;", "    v.u.uint64 = (uint32_t)int32;"),
        (
            "#define JS_MKVAL(tag, val) (JSValue){ (JSValueUnion){ .int32 = val }, tag }",
            "#define JS_MKVAL(tag, val) (JSValue){ (JSValueUnion){ .uint64 = (uint32_t)(val) }, tag }",
        ),
    ]:
        text = replace_once(text, before, after, before)
    # The old public representation stays authoritative on big-endian hosts.
    # Identical layout is insufficient for mixing old/new big-endian int words.
    old = original.read_text(encoding="utf-8")
    return (
        "#if defined(__BYTE_ORDER__) && __BYTE_ORDER__ == __ORDER_BIG_ENDIAN__\n"
        + old
        + "\n#else\n"
        + text
        + "\n#endif\n"
    )


def mixed_numbers(text):
    """Keep numeric pairs in C's existing float path, including x87 guards.

    The implementation deliberately preserves all physical/logical source lines:
    creator-call and native operand proofs bind to the original line tables.
    The long replacement line is generated, never hand-maintained C source.
    """
    for op in ("add", "sub", "mul"):
        begin = text.index("        CASE(OP_" + op + "):")
        end = text.index("\n        CASE(", begin + 1)
        block = text[begin:end]
        before = "} else if (JS_VALUE_IS_BOTH_FLOAT(op1, op2)) {"
        slow = "bellard_add_slow_case" if op == "add" else "binary_arith_slow"
        after = (
            "} else if (JS_TAG_IS_FLOAT64(JS_VALUE_GET_TAG(op1)) || "
            "JS_TAG_IS_FLOAT64(JS_VALUE_GET_TAG(op2))) { double d1, d2; "
        )
        for number in (1, 2):
            value = "op" + str(number)
            after += (
                "if (JS_TAG_IS_FLOAT64(JS_VALUE_GET_TAG(" + value + "))) "
                "d" + str(number) + " = JS_VALUE_GET_FLOAT64(" + value + "); "
                "else if (JS_VALUE_GET_TAG(" + value + ") == JS_TAG_INT) "
                "d" + str(number) + " = JS_VALUE_GET_INT(" + value + "); "
                "else goto " + slow + "; "
            )
        block = replace_once(block, before, after, op + " numeric guard")
        for number in (1, 2):
            before = "JS_VALUE_GET_FLOAT64(op" + str(number) + ")"
            # The conversion prelude itself contains this spelling too.
            at = block.index("JS_X87_FPCW_SAVE_AND_ADJUST")
            tail = replace_once(block[at:], before, "d" + str(number), op + " numeric operand")
            block = block[:at] + tail
        if op == "add":
            before = "                    sf->cur_pc = pc;"
            block = replace_once(
                block, before, before.replace("sf->", slow + ": sf->"), "add slow label"
            )
        text = text[:begin] + block + text[end:]
    return text
