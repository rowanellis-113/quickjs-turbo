"""Expand original native VM streams for owned source adapters."""

import hashlib, re


def expand_vm(source, output):
    original = (source / "asm/arm64/linux/interpreter.S").read_text()
    expanded = {}

    def expand(match):
        name = match[1]
        if name.startswith("asm/arm64/common/"):
            text = (source / name).read_text()
        elif name in {"interpreter-aarch64-publication.inc", "interpreter-aarch64-leaf-bridge.inc"}:
            text = (output / name).read_text()
        else:
            return match[0]
        expanded[name] = hashlib.sha256(text.encode()).hexdigest()
        return re.sub(r'^#include "([^"]+)"$', expand, text, flags=re.M)

    text = re.sub(r'^#include "([^"]+)"$', expand, original, flags=re.M)
    if len([n for n in expanded if n.startswith("asm/arm64/common/")]) != 28:
        raise ValueError("Review complete28 fragment VM input")
    return text, expanded
