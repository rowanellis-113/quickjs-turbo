"""Pure-C RegExp owned wrapper extractor."""

import hashlib
import importlib.util
from pathlib import Path
import re
import sys as _frame_sys
from pathlib import Path as _FramePath

_frame_tools_root = str(_FramePath(__file__).resolve().parents[2])
if _frame_tools_root not in _frame_sys.path:
    _frame_sys.path.insert(0, _frame_tools_root)
from common.paths import (
    activate_tools as _frame_activate_tools,
    tool_path as _frame_tool_path,
    source_file as _frame_source_file,
    source_text as _frame_source_text,
    generated_file as _frame_generated_file,
    project_root as _frame_project_root,
    build_file as _frame_build_file,
)

from c_source_match import replace_one

PINNED_UNICODE_BUILTINS = {
    "js_regexp_Symbol_match": (
        "JS_RegExpOwnedMatch",
        "d7dd65674cb64f6e3258bea214de510f31b12b5b15431c9a5ef44fd3138325db",
    ),
    "js_regexp_Symbol_matchAll": (
        "JS_RegExpOwnedMatchAll",
        "08682a7f974929e4dd361697b27beac9f93bde5d65e3014573c5d9c5164bc5ba",
    ),
    "js_regexp_Symbol_split": (
        "JS_RegExpOwnedSplit",
        "2f484d458cedb3e48ac6b3ccde63895651293a6d840b114f9e6f215170885271",
    ),
}


def pinned_unicode_body(name, text):
    """0.17.0 upstream already implements v-mode Unicode progression."""
    return text


def split_body(source, body, native=False):
    common = (source / "src/common/regexp/split.inc").read_text(encoding="utf-8")
    anchor = "    // [Symbol.split](str, limit)"
    assert body.count(anchor) == 1, "Review pinned @@split entry after upstream change"
    entry = """    if (js_regexp_split_guard(ctx, this_val, argv[0], argv[1]))
        return js_regexp_split_search(ctx, this_val, argv[0], argv[1]);

"""
    prefix = "#define QJS_REGEXP_SPLIT_NATIVE 1\n" if native else ""
    suffix = "\n#undef QJS_REGEXP_SPLIT_NATIVE\n" if native else "\n"
    return prefix + common + suffix + body.replace(anchor, entry + anchor, 1)


def module(source, name):
    sp = importlib.util.spec_from_file_location(
        "regexp_" + name.replace("-", "_"),
        _frame_tool_path(name),
    )
    m = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


def section_name(c, index):
    n = c.sections[index - 1]["name"]
    if n.startswith("/"):
        at = int(n[1:])
        n = c.strings[at : c.strings.index(0, at)].decode()
    return n


PINNED_EXEC_SHA256 = "a39e7eaef1d5bea60f96d075d6d182f8fa5f92720f995692b351c45d34a547b4"
PINNED_STANDARD_EXEC_SHA256 = "4e84238f59476b5497c21752f3cb74af41eec2309a5462e168b130e03342054d"


def exec_body(source, text, native=False):
    adapter = module(source, "object-adapter-c")
    original = next(m[0] for m in adapter.FUNCTION.finditer(text) if m[2] == "js_regexp_exec")
    assert hashlib.sha256(original.encode("utf-8")).hexdigest() == PINNED_EXEC_SHA256, (
        "Review pinned RegExp.exec after upstream change"
    )
    assert text.count("js_regexp_exec") == 5, "Review additional exec identity users"
    # The borrowed flag lookup has the same hash/type comparison as this pin.
    for prefix, digest in (
        (
            "static JSAtom __JS_FindAtom(",
            "cd1a1d5d41892236473dfc4ea883580bcfa31a6e8acd898aabe82d728be7025b",
        ),
        (
            "static inline uint32_t hash_string8(",
            "0183f4fa3f8f4669111ac99be76ae9562203e8e7e687f1750fcf70ad21c01186",
        ),
    ):
        start = text.index(prefix)
        function = text[start : text.index("\n}", start) + 2]
        assert hashlib.sha256(function.encode("utf-8")).hexdigest() == digest, (
            "Review borrowed RegExp flag lookup after upstream change"
        )
    body = (source / "src/common/regexp/exec.inc").read_text(encoding="utf-8")
    declaration = "static JSValue js_regexp_exec("
    assert body.count(declaration) == 1
    if native:
        body = body.replace(declaration, "JSValue JS_FrameRegExpExec(", 1)
    return body


def native_standard_exec(text, source):
    adapter = module(source, "object-adapter-c")
    original = next(
        m[0] for m in adapter.FUNCTION.finditer(text) if m[2] == "js_is_standard_regexp"
    )
    assert hashlib.sha256(original.encode("utf-8")).hexdigest() == PINNED_STANDARD_EXEC_SHA256, (
        "Review standard RegExp observation order"
    )
    return original.replace("js_is_standard_regexp(", "js_frame_regexp_standard(", 1).replace(
        "val, js_regexp_exec, 0", "val, JS_FrameRegExpExec, 0"
    )


def semantic_source(source, inline=None, include_independent=True):
    """Shared owned RegExp algorithms,without a platform object/ABI adapter.

    The default uses kernel includes over core types. Source-overlay backends may
    retain their already-shared exec/test/locale definitions and intrinsic
    identities by excluding those independent entries.
    """
    source = Path(source)
    adapter = module(source, "object-adapter-c")
    text = _frame_source_file(source, "quickjs.c").read_text(encoding="utf-8")
    if inline is None:
        inline = True
    legacy = next(
        m[0] for m in adapter.FUNCTION.finditer(text) if m[2] == "js_regexp_Symbol_replace"
    )
    expected = "93f939d05363f19d1b539ab7f53f2c4aacfa23f5ee85fed79147d576d06093fc"
    assert hashlib.sha256(legacy.encode("utf-8")).hexdigest() == expected, (
        "Upstream @@replace changed: review the owned-argv transplant before updating this guard."
    )
    body = _frame_source_text(source, "kernel-regexp-replace.inc")
    builtin_routes = {"js_regexp_Symbol_replace": "JS_RegExpOwnedReplace"}
    if inline:
        # 0.17.0 already derives fullUnicode from flags and handles v progression.
        fallback = legacy.replace("js_regexp_Symbol_replace(", "JS_RegExpPinnedReplace(", 1)
        body = body.replace(
            "return js_regexp_Symbol_replace(ctx, this_val, argc, argv);",
            "return JS_RegExpPinnedReplace(ctx, this_val, argc, argv);",
        )
        additional = []
        for old_name, (new_name, digest) in PINNED_UNICODE_BUILTINS.items():
            original = next(m[0] for m in adapter.FUNCTION.finditer(text) if m[2] == old_name)
            assert hashlib.sha256(original.encode("utf-8")).hexdigest() == digest, (
                old_name + " changed: review Unicode adapter"
            )
            owned = pinned_unicode_body(old_name, original)
            assert owned.startswith("static JSValue " + old_name + "(")
            owned = owned.replace(
                "static JSValue " + old_name + "(", "JSValue " + new_name + "(", 1
            )
            additional.append(owned)
            builtin_routes[old_name] = new_name
        body = "\n\n".join([fallback, *additional, body])
        # Preserve the pinned flags algorithm and all eight observable reads.
        # Only an actually resolved native flag getter may skip C dispatch.
        flag_bodies = {
            name: next(m[0] for m in adapter.FUNCTION.finditer(text) if m[2] == name)
            for name in ("js_regexp_get_flag", "js_regexp_get_flags")
        }
        for name, digest in {
            "js_regexp_get_flag": "7a8b232d13c8e849872c9c943ec73c33fdd860c94cf8568efa64d75b4a3be735",
            "js_regexp_get_flags": "904490619cf8c10e97f3513c4ba449e9323186ec5f5954374425b21dcdc265eb",
        }.items():
            assert hashlib.sha256(flag_bodies[name].encode()).hexdigest() == digest, (
                name + " changed: review native getter recognition"
            )
        proto = text[text.index("static const JSCFunctionListEntry js_regexp_proto_funcs[]") :]
        proto = proto[: proto.index("\n};") + 3]
        entries = re.findall(r'JS_CGETSET(?:_MAGIC)?_DEF\("(\w+)"', proto)
        assert entries == [
            "flags",
            "source",
            "global",
            "ignoreCase",
            "multiline",
            "dotAll",
            "unicode",
            "unicodeSets",
            "sticky",
            "hasIndices",
        ], "Review live RegExp flag descriptor layout"
        flags = flag_bodies["js_regexp_get_flags"]
        flags = flags.replace(
            "static JSValue js_regexp_get_flags(", "JSValue JS_RegExpOwnedFlags(", 1
        )
        flags = flags.replace("JS_GetPropertyStr(", "js_frame_regexp_flag_property_str(")
        flags = flags.replace("JS_GetProperty(", "js_frame_regexp_flag_property(")
        flags = flags.replace(
            "    char str[8], *p = str;",
            """    unsigned char flags_mode = js_frame_regexp_flags_mode();
    if ((flags_mode & 3) != 1 ||
        JS_VALUE_GET_TAG(this_val) != JS_TAG_OBJECT ||
        JS_VALUE_GET_OBJ(this_val)->class_id != JS_CLASS_REGEXP)
        return js_regexp_get_flags(ctx, this_val);
    char str[8], *p = str;
    int flag_bits;
    if (!(flags_mode & 4) && js_frame_regexp_flags_batch(ctx, this_val, &flag_bits)) {
        if (flag_bits & LRE_FLAG_INDICES) *p++ = 'd';
        if (flag_bits & LRE_FLAG_GLOBAL) *p++ = 'g';
        if (flag_bits & LRE_FLAG_IGNORECASE) *p++ = 'i';
        if (flag_bits & LRE_FLAG_MULTILINE) *p++ = 'm';
        if (flag_bits & LRE_FLAG_DOTALL) *p++ = 's';
        if (flag_bits & LRE_FLAG_UNICODE) *p++ = 'u';
        if (flag_bits & LRE_FLAG_UNICODE_SETS) *p++ = 'v';
        if (flag_bits & LRE_FLAG_STICKY) *p++ = 'y';
        if (p == str) return js_empty_string(ctx->rt);
        return js_new_string8_len(ctx, str, p - str);
    }""",
            1,
        )
        body += "\n" + _frame_source_text(source, "quickjs-regexp-flags.inc") + "\n" + flags + "\n"
        builtin_routes["js_regexp_get_flags"] = "JS_RegExpOwnedFlags"
    if include_independent:
        # On the newer core, keep the original fallback's exact static compiler ABI.
        # Share the existing isolated builtin TU/unwind pipeline with common string kernels.
        locale = next(
            m[0] for m in adapter.FUNCTION.finditer(text) if m[2] == "js_string_localeCompare"
        )
        assert (
            hashlib.sha256(locale.encode()).hexdigest()
            == "0859a5e397dfb485b007e00f8a74794cc64edd294346898083727aeb2fd8140f"
        ), "Review localeCompare semantics after upstream change"
        body += "\n" + _frame_source_text(source, "src/common/string/locale-compare.inc")
        builtin_routes["js_string_localeCompare"] = "JS_FrameLocaleCompare"
        from regexp_test import native_body

        body += "\n" + native_body(text, source)
        builtin_routes["js_regexp_test"] = "JS_FrameRegExpTest"
    if inline and include_independent:
        body = body.replace("js_is_standard_regexp(", "js_frame_regexp_standard(")
        body = (
            exec_body(source, text, native=True)
            + "\n"
            + native_standard_exec(text, source)
            + "\n"
            + body
        )
        builtin_routes["js_regexp_exec"] = "JS_FrameRegExpExec"
    return body, builtin_routes
