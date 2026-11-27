"""Reuse the accepted builtin algorithms with actual Linux types and owners."""

import hashlib
import json


def generate(source, output):
    path = source / "src/common/kernel/slice-native.inc"
    raw = path.read_text()
    start = raw.index("static inline JSValueConst frame_slice_argument(")
    end = raw.index("\n_Static_assert", start)
    number = raw.index("NATIVE_SLICE_CODE void JS_FrameNumberToStringNative(")
    stop = raw.find("NATIVE_SLICE_CODE void JS_FrameBuiltinNative(", number)
    number_body = raw[number:] if stop < 0 else raw[number:stop]
    old_int_block = (
        "    if (JS_VALUE_GET_TAG(val) == JS_TAG_INT) {\n"
        "        char buf[70];\n"
        "        int len = i64toa_radix(buf, JS_VALUE_GET_INT(val), 10);\n"
        "        *out = js_new_string8_len(ctx, buf, len);\n"
        "        return;\n"
        "    }"
    )
    new_int_block = (
        "    if (JS_VALUE_GET_TAG(val) == JS_TAG_INT) {\n"
        "#ifdef QJS_INT_TO_STRING_FAST_AVAILABLE\n"
        "        *out = qjs_int_to_string_fast(ctx, JS_VALUE_GET_INT(val));\n"
        "#else\n"
        "        char buf[16];\n"
        "        int len = (int)i32toa(buf, JS_VALUE_GET_INT(val));\n"
        "        *out = js_new_string8_len(ctx, buf, len);\n"
        "#endif\n"
        "        return;\n"
        "    }"
    )
    if old_int_block in number_body:
        number_body = number_body.replace(old_int_block, new_int_block, 1)
    # The foreign ABI wrapper, TLS sequence and compiler-local alias are excluded;
    # both semantic bodies are copied verbatim, not reduced for a fixture.
    text = (
        "/* Accepted builtin semantic bodies; real Linux SF/core types. */\n"
        + raw[start:end]
        + number_body
    )
    target = output / "quickjs-linux-builtin.h"
    target.write_text(text)
    record = dict(
        source=str(path.relative_to(source)),
        source_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        generated_sha256=hashlib.sha256(text.encode()).hexdigest(),
        entries=[
            "JS_FrameStringSliceNative",
            "JS_FrameNumberToStringNative",
            "JS_LinuxBuiltinRun",
            "JS_LinuxBuiltinPrepare",
            "JS_LinuxBuiltinProbe",
            "JS_LinuxNumericTrampoline",
        ],
        view_size=128,
        ownership="caller-window lifetime or transient arena/C stack; typed SF/TLS/GC/quota",
        windows_wrapper_copied=False,
    )
    (output / "BUILTIN-WORKERS.json").write_text(json.dumps(record, indent=2) + "\n")
    return record
