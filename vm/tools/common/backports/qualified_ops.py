"""Reproduce the already-qualified R9 C opcode backports on pinned NG bodies.
No engine behavior changes here; fail closed on an upstream opcode diff.
"""

import hashlib

PATCHES = {
    "get_array_el": (
        "f03a072409b5eb76fa6626de9b13743860c0d14f6b8eb3b5caf06f219b557eea",
        [
            (
                4,
                4,
                "",
                r"""                /* fast path: regular/typed array element by int index */
                if (likely(JS_VALUE_GET_TAG(sp[-2]) == JS_TAG_OBJECT &&
                           JS_VALUE_GET_TAG(sp[-1]) == JS_TAG_INT)) {
                    JSObject *p = JS_VALUE_GET_OBJ(sp[-2]);
                    uint32_t idx = JS_VALUE_GET_INT(sp[-1]);
                    if (likely(p->class_id == JS_CLASS_ARRAY &&
                               idx < p->u.array.count)) {
                        val = js_dup(p->u.array.u.values[idx]);
                        JS_FreeValue(ctx, sp[-2]);
                        sp[-2] = val;
                        sp--;
                        BREAK;
                    }
                    if (js_get_fast_array_element(ctx, p, idx, &val)) {
                        JS_FreeValue(ctx, sp[-2]);
                        sp[-2] = val;
                        sp--;
                        BREAK;
                    }
                }
""",
            ),
        ],
    ),
    "get_array_el2": (
        "85c376dd4cf09e0dc0d7ebbcea5c129b4f40457169a9b440f187994d3842d08c",
        [
            (
                4,
                4,
                "",
                r"""                /* fast path: regular/typed array element by int index */
                if (likely(JS_VALUE_GET_TAG(sp[-2]) == JS_TAG_OBJECT &&
                           JS_VALUE_GET_TAG(sp[-1]) == JS_TAG_INT)) {
                    JSObject *p = JS_VALUE_GET_OBJ(sp[-2]);
                    uint32_t idx = JS_VALUE_GET_INT(sp[-1]);
                    if (likely(p->class_id == JS_CLASS_ARRAY &&
                               idx < p->u.array.count)) {
                        sp[-1] = js_dup(p->u.array.u.values[idx]);
                        BREAK;
                    }
                    if (js_get_fast_array_element(ctx, p, idx, &val)) {
                        sp[-1] = val;
                        BREAK;
                    }
                }
""",
            ),
        ],
    ),
    "add": (
        "0329859e54eba5e409dd7c1c38ea5f06a665e01adeef0b44e51548fc2a74286b",
        [
            (
                19,
                19,
                "",
                r"""                } else if (JS_TAG_IS_FLOAT64(JS_VALUE_GET_TAG(op1)) ||
                           JS_TAG_IS_FLOAT64(JS_VALUE_GET_TAG(op2))) {
                    /* mixed int/float; the BOTH_FLOAT fast path above is unchanged */
                    double d1, d2;
                    if (!js_arith_to_float64(op1, &d1) ||
                        !js_arith_to_float64(op2, &d2))
                        goto add_slow_case;
                    JS_X87_FPCW_SAVE_AND_ADJUST(fpcw);
                    sp[-2] = js_float64(d1 + d2);
                    JS_X87_FPCW_RESTORE(fpcw);
                    sp--;
""",
            ),
            (
                20,
                20,
                "",
                r"""                add_slow_case:
""",
            ),
        ],
    ),
    "sub": (
        "37fd758c30b1e9632dfb5681291a10362e8d5a6de8ac06865060a1fd55320850",
        [
            (
                19,
                19,
                "",
                r"""                } else if (JS_TAG_IS_FLOAT64(JS_VALUE_GET_TAG(op1)) ||
                           JS_TAG_IS_FLOAT64(JS_VALUE_GET_TAG(op2))) {
                    /* mixed int/float; the BOTH_FLOAT fast path above is unchanged */
                    double d1, d2;
                    if (!js_arith_to_float64(op1, &d1) ||
                        !js_arith_to_float64(op2, &d2))
                        goto binary_arith_slow;
                    JS_X87_FPCW_SAVE_AND_ADJUST(fpcw);
                    sp[-2] = js_float64(d1 - d2);
                    JS_X87_FPCW_RESTORE(fpcw);
                    sp--;
""",
            ),
        ],
    ),
    "mul": (
        "3d3f91b40853a2682f386ee999d973a9e7ea8a6cc35331e61b769f33ceedbd9a",
        [
            (
                30,
                30,
                "",
                r"""                } else if (JS_TAG_IS_FLOAT64(JS_VALUE_GET_TAG(op1)) ||
                           JS_TAG_IS_FLOAT64(JS_VALUE_GET_TAG(op2))) {
                    /* mixed int/float; the BOTH_FLOAT fast path above is unchanged */
                    double d1, d2;
                    if (!js_arith_to_float64(op1, &d1) ||
                        !js_arith_to_float64(op2, &d2))
                        goto binary_arith_slow;
                    JS_X87_FPCW_SAVE_AND_ADJUST(fpcw);
                    d = d1 * d2;
                    JS_X87_FPCW_RESTORE(fpcw);
                    goto mul_fp_res;
""",
            ),
        ],
    ),
    "div": (
        "d54cf40261b1afc0f134a4d2cf83d2dff1160199a20849bbf4fcba08ce202c7a",
        [
            (
                11,
                11,
                "",
                r"""                } else if (JS_VALUE_IS_BOTH_FLOAT(op1, op2)) {
                    JS_X87_FPCW_SAVE_AND_ADJUST(fpcw);
                    sp[-2] = js_number(JS_VALUE_GET_FLOAT64(op1) /
                                       JS_VALUE_GET_FLOAT64(op2));
                    JS_X87_FPCW_RESTORE(fpcw);
                    sp--;
                } else if (JS_TAG_IS_FLOAT64(JS_VALUE_GET_TAG(op1)) ||
                           JS_TAG_IS_FLOAT64(JS_VALUE_GET_TAG(op2))) {
                    /* mixed int/float; the BOTH_FLOAT fast path above is unchanged */
                    double d1, d2;
                    if (!js_arith_to_float64(op1, &d1) ||
                        !js_arith_to_float64(op2, &d2))
                        goto binary_arith_slow;
                    JS_X87_FPCW_SAVE_AND_ADJUST(fpcw);
                    sp[-2] = js_number(d1 / d2);
                    JS_X87_FPCW_RESTORE(fpcw);
                    sp--;
""",
            ),
        ],
    ),
}


def apply(text):
    for name, (digest, edits) in PATCHES.items():
        start = text.index("        CASE(OP_" + name + "):")
        end = text.index("        CASE(", start + 1)
        block = text[start:end]
        if hashlib.sha256(block.encode()).hexdigest() != digest:
            raise ValueError("Review qualified R9 opcode backport after upstream change: " + name)
        lines = block.splitlines(True)
        for first, last, before, after in reversed(edits):
            assert "".join(lines[first:last]) == before
            lines[first:last] = [after]
        text = text[:start] + "".join(lines) + text[end:]
    return text
