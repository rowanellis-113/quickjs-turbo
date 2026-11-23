"""Keep pinned libc inputs intact and isolate its bounded file-buffer growth."""

import hashlib
import json
from pathlib import Path

SOURCE_SHA256 = "60b8af33a1404a842f00de2ccf70d97ebc9a789bdcbe075a6c01b4df47c081a6"


def compiler_input(root, build):
    root, build = Path(root), Path(build)
    original = root / "quickjs-libc.c"
    if not original.is_file() and (root.parent / "quickjs-libc.c").is_file():
        original = root.parent / "quickjs-libc.c"
    raw = original.read_bytes()
    data = raw.replace(b"\r\n", b"\n")
    if hashlib.sha256(data).hexdigest() != SOURCE_SHA256:
        raise ValueError("upstream libc changed: review the file-loading overlay")
    text = data.decode("utf-8")
    signature = "uint8_t *js_load_file(JSContext *ctx, size_t *pbuf_len, const char *filename)\n"
    if text.count(signature) != 1:
        raise ValueError("review upstream file-loading function boundary")
    start = text.index(signature)
    end = text.index("/* load and evaluate a file */", start)
    legacy = text[start:end].replace(
        "uint8_t *js_load_file(", "static uint8_t *js_load_file_legacy(", 1
    )
    if legacy.count("static uint8_t *js_load_file_legacy(") != 1 or "js_load_file_legacy" in text:
        raise ValueError("review legacy file-loader identity")
    shared = root / "src/common/io/file-load.inc"
    content = (
        '#line 1 "'
        + original.as_posix()
        + '"\n'
        + text[:start]
        + legacy
        + '#include "src/common/io/file-load.inc"\n'
        + "#line "
        + str(text[:end].count("\n") + 1)
        + ' "'
        + original.as_posix()
        + '"\n'
        + text[end:]
    ).encode("utf-8")
    # Keep this separate from the private core's value64 quickjs.h overlay.
    directory = build.resolve() / "generated/libc"
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / "quickjs-libc.c"
    if not target.exists() or target.read_bytes() != content:
        target.write_bytes(content)
    receipt = dict(
        schema=1,
        upstream_source=str(original),
        upstream_source_sha256=SOURCE_SHA256,
        upstream_checkout_sha256=hashlib.sha256(raw).hexdigest(),
        original_file_modified=False,
        shared_source=str(shared),
        shared_source_sha256=hashlib.sha256(shared.read_bytes()).hexdigest(),
        compiler_input=str(target),
        compiler_input_sha256=hashlib.sha256(content).hexdigest(),
        mechanism="Geometric streaming reads, then exact-size input handoff before parsing",
        ablation="QJS_DISABLE_FILE_LOAD_GROWTH presence, checked per load; original body and allocation policy",
        compaction_ablation="QJS_DISABLE_FILE_LOAD_COMPACT presence retains geometric spare capacity",
        scope="Declared libc overlay only; original loader when source overlays are disabled",
    )
    (directory / "FILE-LOADER.json").write_text(
        json.dumps(receipt, indent=2) + "\n", encoding="utf-8"
    )
    return target
