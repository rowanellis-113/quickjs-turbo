"""One common RegExp.test ordering correction for native and source-overlay builds."""

import hashlib

PINNED_FUNCTION_SHA256 = "ada5df91778e445b83ce625b41014280628e40087fa7a7170f700e1b04fd41b8"


def original_body(text):
    start = text.index("static JSValue js_regexp_test(")
    end = text.index("\nstatic JSValue js_regexp_Symbol_match(", start)
    original = text[start:end]
    assert hashlib.sha256(original.encode("utf-8")).hexdigest() == PINNED_FUNCTION_SHA256, (
        "Review RegExp.test receiver/coercion/exec semantics after upstream change"
    )
    assert text.count("js_regexp_test") == 2, "Review additional RegExp.test references"
    return start, end, original


def native_body(text, source):
    original_body(text)
    return (source / "src/common/regexp/test.inc").read_text(encoding="utf-8")


def portable_core(text, source, build):
    start, end, original = original_body(text)
    common = source / "src/common/regexp/test.inc"
    body = common.read_text(encoding="utf-8")
    declaration = "JSValue JS_FrameRegExpTest("
    assert body.count(declaration) == 1
    body = body.replace(declaration, "static JSValue js_regexp_test(", 1)
    output = build.resolve() / "generated/backports"
    output.mkdir(parents=True, exist_ok=True)
    header = output / "quickjs-regexp-test-portable.h"
    content = body.encode("utf-8")
    if not header.exists() or header.read_bytes() != content:
        header.write_bytes(content)
    replacement = '#include "quickjs-regexp-test-portable.h"' + "\n" * original.count("\n")
    patched = text[:start] + replacement + text[end:]
    assert patched.count("\n") == text.count("\n")
    return patched, dict(
        mechanism="Validate RegExp.test receiver and own ToString input before observable exec lookup",
        source=str(common),
        source_sha256=hashlib.sha256(common.read_bytes()).hexdigest(),
        compiler_include=str(header),
        compiler_include_sha256=hashlib.sha256(content).hexdigest(),
        pinned_function_sha256=PINNED_FUNCTION_SHA256,
        line_count_preserved=True,
    )
