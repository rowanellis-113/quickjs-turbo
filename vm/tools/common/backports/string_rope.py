"""Pinned flat/rope string equality correction shared by native/portable builds."""

import hashlib
import re

FUNCTION_SHA256 = "47814789bd2a2f4914fdadaf76fadd64e866e4dcc004fb8295c9ca8942184f7b"
FUNCTION = re.compile(
    r"^static no_inline __exception int js_eq_slow\([^;{}]*\)\s*\{.*?^\}", re.M | re.S
)


def equality_function(text):
    matches = list(FUNCTION.finditer(text))
    if len(matches) != 1:
        raise ValueError("Need exactly one pinned loose-equality algorithm")
    match = matches[0]
    body = match[0]
    if hashlib.sha256(body.encode()).hexdigest() != FUNCTION_SHA256:
        raise ValueError("Upstream loose equality changed; review the flat/rope correction")
    old = "    } else if (tag1 == tag2) {"
    if body.count(old) != 1:
        raise ValueError("Pinned loose-equality same-type branch changed")
    fixed = body.replace(
        old, "    } else if (tag1 == tag2 || (JS_IsString(op1) && JS_IsString(op2))) {", 1
    )
    return match, fixed


def portable_equality(text):
    match, fixed = equality_function(text)
    return text[: match.start()] + fixed + text[match.end() :]
