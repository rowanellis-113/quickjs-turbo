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
