"""Match one C token sequence while tolerating formatting-only whitespace.

This is for source-derived generators, not a C parser. Comments and literals
remain part of the anchor; replacements spanning preprocessor directives or
line splices must match their text exactly.
"""

import importlib.util
from pathlib import Path
import re

_spec = importlib.util.spec_from_file_location(
    "native_format_tokens", Path(__file__).resolve().parents[1] / "format/native.py"
)
_formatter = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_formatter)


def _significant(text):
    return [
        (match.lastgroup, match.group(), match.start(), match.end())
        for match in _formatter.TOKEN.finditer(text)
        if match.lastgroup != "space"
    ]


def _match_one(text, before):
    if not before:
        raise ValueError("Empty C source anchor")
    needle_tokens = _significant(before)
    needle = [(kind, value) for kind, value, _, _ in needle_tokens]
    if not needle:
        raise ValueError("C source anchor has no tokens")
    source = _significant(text)
    width = len(needle)
    hits = [
        index
        for index in range(len(source) - width + 1)
        if (source[index][0], source[index][1]) == needle[0]
        and [(kind, value) for kind, value, _, _ in source[index : index + width]] == needle
    ]
    if len(hits) != 1:
        raise ValueError(
            "C source anchor missing or ambiguous (%d matches): %s" % (len(hits), before)
        )
    start = source[hits[0]][2]
    end = source[hits[0] + width - 1][3]
    return needle_tokens, start, end


def extract_function(text, signature):
    """Extract one source-owned C definition across whitespace-only changes."""
    _, start, _ = _match_one(text, signature)
    line_start = text.rfind("\n", 0, start) + 1
    if text[line_start:start].lstrip().startswith("#"):
        raise ValueError("Function signature is inside a preprocessor directive")
    depth = 0
    for token in _formatter.TOKEN.finditer(text, start):
        if token.lastgroup != "punct":
            continue
        value = token.group()
        if value == ";" and depth == 0:
            raise ValueError("Expected a function definition, found a prototype")
        if value == "{":
            depth += 1
        elif value == "}" and depth:
            depth -= 1
            if not depth:
                return text[start : token.end()]
    raise ValueError("Missing or unbalanced function body: " + signature)


def find_one(text, before):
    """Locate one exact C token sequence, retaining literal/comment identity."""
    _, start, end = _match_one(text, before)
    return start, end


def replace_one(text, before, after):
    """Replace exactly one anchor or reject missing/ambiguous C token matches."""
    needle_tokens, start, end = _match_one(text, before)
    exact = text.find(before)
    if (
        exact >= 0
        and text.find(before, exact + 1) < 0
        and exact + needle_tokens[0][2] == start
        and exact + needle_tokens[-1][3] == end
    ):
        return text[:exact] + after + text[exact + len(before) :]

    line_start = text.rfind("\n", 0, start) + 1
    line_end = text.find("\n", end)
    if line_end == -1:
        line_end = len(text)
    context = text[line_start:line_end]
    if re.search(r"(?m)^[ \t]*#", context) or "\\\n" in context or "\\\n" in before:
        raise ValueError("C source anchor requires an exact preprocessor match: " + before)

    prefix = before[: needle_tokens[0][2]]
    suffix = before[needle_tokens[-1][3] :]
    if prefix and not text[line_start:start].strip():
        start = line_start
        if "\n" in prefix and start:
            start -= 1
    if "\n" in suffix:
        tail = text[end:line_end]
        if not tail.strip() and line_end < len(text):
            end = line_end + 1
    return text[:start] + after + text[end:]
