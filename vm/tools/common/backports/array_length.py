"""Use the common sparse-length correction in portable declared source overlays."""

import hashlib

PINNED_FUNCTION_SHA256 = "abc7c79ef2cc727c1f5f4c54974fbe35eac78ddbb0a8485c565d96569f4e4b6c"


def portable_core(text, source, build):
    start = text.index("static int set_array_length(")
    end = text.index("\n/* return -1 if exception */", start)
    original = text[start:end]
    assert hashlib.sha256(original.encode("utf-8")).hexdigest() == PINNED_FUNCTION_SHA256, (
        "Review sparse-length semantics after upstream change"
    )
    common = source / "src/common/array/length.inc"
    body = common.read_text(encoding="utf-8")
    declaration = "int JS_FrameSetArrayLength("
    assert body.count(declaration) == 1
    body = body.replace(declaration, "static int set_array_length(", 1)
    output = build.resolve() / "generated/backports"
    output.mkdir(parents=True, exist_ok=True)
    header = output / "quickjs-array-length-portable.h"
    content = body.encode("utf-8")
    if not header.exists() or header.read_bytes() != content:
        header.write_bytes(content)
    # An include returns to the original logical line after preprocessing.
    # Preserve the complete old function's line count and all surrounding code.
    replacement = '#include "quickjs-array-length-portable.h"' + "\n" * original.count("\n")
    patched = text[:start] + replacement + text[end:]
    assert patched.count("\n") == text.count("\n")
    return patched, dict(
        mechanism="Restart sparse Array.length property scan after compaction",
        summary="Same common C function as native worker; static original name in portable compiler input",
        source=str(common),
        source_sha256=hashlib.sha256(common.read_bytes()).hexdigest(),
        compiler_include=str(header),
        compiler_include_sha256=hashlib.sha256(content).hexdigest(),
        pinned_function_sha256=PINNED_FUNCTION_SHA256,
        line_count_preserved=True,
    )
