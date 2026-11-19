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
        "e6c35b4c53de9aa37908832e8710a3cf470769c8c6f7f4c8c578f491d7ea91fd",
    ),
    "js_regexp_Symbol_matchAll": (
        "JS_RegExpOwnedMatchAll",
        "0da1dd4b46588f5d96c94961bd04826924ab238f27cee4c2de09c25e4567ce3f",
    ),
    "js_regexp_Symbol_split": (
        "JS_RegExpOwnedSplit",
        "7c9f4d591669e5af88935fca6eff06b398705cb8e10ef15ba5a965f2311d5702",
    ),
}


def pinned_unicode_body(name, text):
    """Keep pinned observable operations; advance v matches by code point."""
    if name in ("js_regexp_Symbol_match", "js_regexp_Symbol_replace"):
        before = """        fullUnicode = JS_ToBoolFree(ctx, JS_GetProperty(ctx, rx, JS_ATOM_unicode));
        if (fullUnicode < 0)
            goto exception;
"""
        after = (
            before
            + """        if (!fullUnicode)
            fullUnicode = string_indexof_char(p, 'v', 0) >= 0;
"""
        )
    else:
        field = "it->unicode" if name.endswith("matchAll") else "unicodeMatching"
        before = f"    {field} = string_indexof_char(strp, 'u', 0) >= 0;"
        after = (
            f"    {field} = (string_indexof_char(strp, 'u', 0) >= 0 ||\n"
            + "                   string_indexof_char(strp, 'v', 0) >= 0);"
        )
    assert text.count(before) == 1, "Pinned Unicode boundary changed: " + name
    if name == "js_regexp_Symbol_replace":
        # The inherited delete kernel advances only u, not v, empty matches.
        # Keep its constructor/exec observation before choosing the v-aware
        # generic loop; native intrinsic dispatch still handles admitted v.
        delete_guard = (
            "    if (rp && rp->len == 0 && is_global && js_is_standard_regexp(ctx, rx)) {"
        )
        generic_v_guard = """    if (rp && rp->len == 0 && is_global && js_is_standard_regexp(ctx, rx) &&
        string_indexof_char(p, 'v', 0) < 0) {"""
        assert text.count(delete_guard) == 1, "Review pinned empty replacement guard"
        text = text.replace(delete_guard, generic_v_guard, 1)
    return text.replace(before, after)


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
        _frame_tool_path((name + "-c" if name == "object-adapter" else name)),
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


PINNED_EXEC_SHA256 = "4462f3d0121b3d5ddc3f8a6714c32ec27ec608676394939e20fd7cb1a5fdb337"
PINNED_STANDARD_EXEC_SHA256 = "4e84238f59476b5497c21752f3cb74af41eec2309a5462e168b130e03342054d"


def exec_body(source, text, native=False):
    adapter = module(source, "object-adapter-c")
    original = next(m[0] for m in adapter.FUNCTION.finditer(text) if m[2] == "js_regexp_exec")
    assert hashlib.sha256(original.encode("utf-8")).hexdigest() == PINNED_EXEC_SHA256, (
        "Review pinned RegExp.exec after upstream change"
    )
    assert text.count("js_regexp_exec") == 4, "Review additional exec identity users"
    # The borrowed flag lookup has the same hash/type comparison as this pin.
    for prefix, digest in (
        (
            "static JSAtom __JS_FindAtom(",
            "2e6024a80e33496d4a4b642ccf53fe5aff837401d57fa5143a450d549f099a88",
        ),
        (
            "static inline uint32_t hash_string8(",
            "aab7446c720ff041572344f347c2fab9ab4f76ec521a89a512f467cc80d45964",
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
    expected = (
        "a9d8353d68ec5640f742e78683983f67ce72c8801ec99868ed62b51f8b94c49b"
        if inline
        else "93f939d05363f19d1b539ab7f53f2c4aacfa23f5ee85fed79147d576d06093fc"
    )
    assert hashlib.sha256(legacy.encode("utf-8")).hexdigest() == expected, (
        "Upstream @@replace changed: review the owned-argv transplant before updating this guard."
    )
    body = _frame_source_text(source, "kernel-regexp-replace.inc")
    builtin_routes = {"js_regexp_Symbol_replace": "JS_RegExpOwnedReplace"}
    if inline:
        # The pinned 0.15.1 algorithm queries rx.unicode, including its getter
        # and abrupt completion. Keep that observable operation while porting
        # the owned callback argv; 0.17 instead derives Unicode from flags.
        old_unicode = """        // 'v' flag implies full Unicode, like 'u'
        fullUnicode = (string_indexof_char(p, 'u', 0) >= 0 || string_indexof_char(p, 'v', 0) >= 0);
"""
        begin = legacy.index(
            "        fullUnicode = JS_ToBoolFree(ctx, JS_GetProperty(ctx, rx, JS_ATOM_unicode));"
        )
        copied_unicode = pinned_unicode_body("js_regexp_Symbol_replace", legacy)[begin:]
        copied_unicode = copied_unicode[
            : copied_unicode.index("        if (JS_SetProperty(ctx, rx, JS_ATOM_lastIndex")
        ]
        body = replace_one(body, old_unicode, copied_unicode)
        # The non-callback fallback must share the v-aware progression rule.
        # Its full pinned algorithm and getter/exception order are retained.
        fallback = pinned_unicode_body("js_regexp_Symbol_replace", legacy)
        fallback = fallback.replace("js_regexp_Symbol_replace(", "JS_RegExpPinnedReplace(", 1)
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
