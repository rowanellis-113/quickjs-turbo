"""Shared assembly text boundary utilities."""

import re


def assembly_line_start(text, line):
    """Locate one complete directive/label independently of indentation."""
    if "\n" in line or not line:
        raise ValueError("Expected one assembly line")
    matches = list(re.finditer(r"(?m)^[ \t]*" + re.escape(line) + r"[ \t]*$", text))
    if len(matches) != 1:
        raise ValueError("Review unique publication assembly line: " + line)
    return matches[0].start()
