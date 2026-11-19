"""Reuse the accepted C RegExp/wire semantics without the native frame ABI."""

import hashlib
import importlib.util
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from paths import source_file


def _module(source, name, path):
    spec = importlib.util.spec_from_file_location(name, source / path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def portable_core(text, source, build):
    source, build = Path(source), Path(build)
    adapter = _module(
        source, "portable_regexp_adapter", "tools/common/c_extract/object_adapter_c.py"
    )
    regexp = _module(source, "portable_regexp_builtins", "tools/common/c_extract/regexp_c.py")
    wire = _module(source, "portable_regexp_wire", "tools/common/backports/generate-wire.py")
    original = source_file(source, "quickjs.c").read_text(encoding="utf-8")
    generated_wire = wire.generate(source)
    common_wire = source / "src/common/wire/wire.c"
    assert generated_wire == common_wire.read_text(encoding="utf-8"), (
        "Regenerate/review common wire source"
    )
    directory = build.resolve() / "generated/backports"
    directory.mkdir(parents=True, exist_ok=True)
    records = []

    def include(before, body, filename):
        nonlocal text
        assert text.count(before) == 1, "Portable RegExp source anchor changed: " + filename
        path = directory / filename
        content = body.encode("utf-8")
        if not path.exists() or path.read_bytes() != content:
            path.write_bytes(content)
        text = text.replace(before, '#include "' + filename + '"' + "\n" * before.count("\n"), 1)
        records.append(dict(path=str(path), sha256=hashlib.sha256(content).hexdigest()))

    # The common exec retains its original static identity on the C backend.
    functions_for_exec = {m[2]: m[0] for m in adapter.FUNCTION.finditer(original)}
    include(
        functions_for_exec["js_regexp_exec"],
        regexp.exec_body(source, original),
        "quickjs-portable-regexp-exec.h",
    )

    # Share the exact accepted Unicode progress correction. Preserve the
    # original portable callback argv/ownership algorithm and observable gets.
    functions = {m[2]: m[0] for m in adapter.FUNCTION.finditer(original)}
    for name in (
        "js_regexp_Symbol_match",
        "js_regexp_Symbol_replace",
        "js_regexp_Symbol_matchAll",
        "js_regexp_Symbol_split",
    ):
        before = functions[name]
        after = regexp.pinned_unicode_body(name, before)
        if name == "js_regexp_Symbol_split":
            after = regexp.split_body(source, after)
        if name == "js_regexp_Symbol_replace":
            common = (source / "src/common/regexp/replace-empty.inc").read_text(encoding="utf-8")
            anchor = "    // [Symbol.replace](str, rep)"
            assert after.count(anchor) == 1, "Review pinned @@replace entry"
            entry = """    int empty_flags;
    JSProperty *empty_index;
    if (js_regexp_empty_guard(ctx, this_val, argv[0], argv[1], &empty_flags, &empty_index))
        return js_regexp_empty_search(ctx, this_val, argv[0], empty_flags, empty_index);

"""
            after = common + "\n" + after.replace(anchor, entry + anchor, 1)
        include(before, after, "quickjs-portable-" + name + ".h")

    # Reuse the whole maintained serializer instead of allowing new RegExp
    # bytecode to escape through the old 0.15.1 wire format. Keep its existing
    # old-format compiler/import translation and malformed-bytecode checks.
    # Portable has no native frame allocator: the original reader uses calloc.
    wire_functions = {m[2]: m for m in adapter.FUNCTION.finditer(generated_wire)}
    old_functions = {m[2]: m for m in adapter.FUNCTION.finditer(original)}
    first = original.rfind(
        "/*******************************************************************/",
        0,
        original.index("/* object list */"),
    )
    old_body = original[first : old_functions["JS_ReadObject"].end()]
    new_first = generated_wire.index(
        "/*******************************************************************/"
    )
    new_body = generated_wire[new_first : wire_functions["JS_ReadObject"].end()]
    allocation = "JS_FrameOwnBytecodeAllocateContext(ctx, function_size)"
    assert new_body.count(allocation) == 1
    new_body = new_body.replace(allocation, "js_mallocz(ctx, function_size)")
    include(
        old_body,
        "#define QJS_FRAME_REGEXP_LEGACY_WIRE 1\n" + new_body,
        "quickjs-portable-regexp-wire.h",
    )
    for name in (
        "js_map_read",
        "js_map_write",
        "JS_ReadMap",
        "JS_ReadSet",
        "JS_WriteMap",
        "JS_WriteSet",
    ):
        include(functions[name], wire_functions[name][0], "quickjs-portable-" + name + ".h")
    before = '#include "libregexp.h"'
    assert text.count(before) == 1
    # The new RegExp header expects its own inline Unicode helpers. The pinned
    # core instead calls the retained external bool wrapper. Preserve its exact
    # prototype: an implicit int return reads undefined upper bits on some targets.
    declaration = "bool lre_is_space(int c);"
    assert source_file(source, "libregexp.h").read_text(encoding="utf-8").count(declaration) == 1
    include(
        before,
        '#include "src/common/regexp/libregexp.h"\n' + declaration + "\n",
        "quickjs-portable-regexp-api.h",
    )
    return text, dict(
        mechanism="Accepted common RegExp/Unicode builtin progress and wire compatibility on C backend",
        common_wire_sha256=hashlib.sha256(common_wire.read_bytes()).hexdigest(),
        includes=records,
        line_count_preserved=True,
        native_frame_allocator=False,
        core_whitespace_bool_abi_preserved=True,
        scope="No native frame/object adapter or duplicated serializer; original portable allocation/argv paths retained",
    )
