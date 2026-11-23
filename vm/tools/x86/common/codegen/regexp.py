"""Build separate builtin and array-copy workers without recompiling the core.

Types/inline helpers come from this build's source. The first stage redirects
only the listed regexp/locale builtin-table pointers. The separate array-copy
stage then routes exactly one decoded call operand in the original splice
builtin, retaining its entry, size, tables and all other instruction bytes.
Each stage emits its own checked object-level equivalence receipt.
"""

# Shared source/tool/artifact addressing for the x86 backend package.
import sys as _frame_sys
from pathlib import Path as _FramePath

_frame_tools_root = str(_FramePath(__file__).resolve().parents[3])
if _frame_tools_root not in _frame_sys.path:
    _frame_sys.path.insert(0, _frame_tools_root)
from x86.common.paths_x86 import (
    activate_tools as _frame_activate_tools,
    tool_path as _frame_tool_path,
    source_file as _frame_source_file,
    source_text as _frame_source_text,
    generated_file as _frame_generated_file,
    project_root as _frame_project_root,
    build_file as _frame_build_file,
)

_frame_activate_tools()
from c_source_match import replace_one
from pathlib import Path
import argparse, hashlib, importlib.util, json, re, struct
from native_abi import current_or_load as load_layout

sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
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
        "regexp_" + name.replace("-", "_"), _frame_tool_path(name + ".py")
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
    adapter = module(source, "object-adapter")
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
    adapter = module(source, "object-adapter")
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

    The default is the existing Win worker text. Source-overlay backends may
    retain their already-shared exec/test/locale definitions and intrinsic
    identities by excluding those independent entries.
    """
    source = Path(source)
    adapter = module(source, "object-adapter")
    text = _frame_source_file(source, "quickjs.c").read_text(encoding="utf-8")
    if inline is None:
        inline = load_layout(source)["reference_count_model"] == "inline-header"
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
    body = _frame_source_text(source, "quickjs-regexp-replace.h")
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


def generate(source, build, target):
    adapter = module(source, "object-adapter")
    text = _frame_source_file(source, "quickjs.c").read_text(encoding="utf-8")
    inline = load_layout(source)["reference_count_model"] == "inline-header"
    types = []
    for name in ("StringBuffer", "ValueBuffer") + (
        ("JSRegExpStringIteratorData",) if inline else ()
    ):
        m = re.search(r"typedef struct " + name + r"\s*\{.*?\}\s*" + name + r";", text, re.S)
        assert m, name
        types.append(m[0])
    expanded = text.replace(
        "static inline bool double_is_int32",
        "\n".join(types) + "\n\nstatic inline bool double_is_int32",
        1,
    )
    # Source-private tentative objects are unused by this builtin; avoid duplicate MSVC BSS.
    expanded = re.sub(r"^static const \w+ \w+(?:\[[^]\n]*\])?;\n", "", expanded, flags=re.M)
    original = _frame_generated_file(build, "quickjs-core-original.obj")
    core = adapter.Coff(original.read_bytes())
    body, builtin_routes = semantic_source(source, inline=inline)
    header, exports, copies = adapter.generate(
        expanded, core, body + ("" if inline else "\njs_regexp_Symbol_replace\n")
    )
    private = _frame_generated_file(build, "quickjs-regexp-private.h")
    private.write_text(header, encoding="utf-8", newline="\n")
    target.write_text(
        '#include "quickjs-regexp-private.h"\n' + body, encoding="utf-8", newline="\n"
    )
    return exports, copies, private, builtin_routes


def adapt_core(source, build, exports, builtin_routes):
    adapter = module(source, "object-adapter")
    path = _frame_build_file(build, "CMakeFiles/qjs-core.dir/quickjs.c.obj")
    raw = path.read_bytes()
    c = adapter.Coff(raw)
    existing = {s["name"] for s in c.all_symbols.values()}
    for name in exports:
        if "qjs_frame_core_" + name not in existing:
            c.expose(name)
    legacy = {name: c.symbols[name] for name in builtin_routes}
    routes = []
    new_symbols = {name: c.external(target) for name, target in builtin_routes.items()}
    for sn, r in enumerate(c.section_records, 1):
        name = section_name(c, sn)
        if r["flags"] & 0x20000000 or not name.startswith((".rdata", ".data")):
            continue
        assert r["count"] < 65535
        for i in range(r["count"]):
            at = r["reloc"] + 10 * i
            offset, symbol, kind = struct.unpack_from("<IIH", c.data, at)
            if kind != 1:
                continue  # IMAGE_REL_AMD64_ADDR64 builtin function pointer
            old = c.all_symbols[symbol]
            value = struct.unpack_from("<Q", c.data, r["raw"] + offset)[0]
            targets = [
                key
                for key, symbol in legacy.items()
                if (old["name"] == key and value == 0)
                or (
                    old["section"] == symbol["section"]
                    and old["type"] == 0
                    and old["value"] + value == symbol["value"]
                )
            ]
            if not targets:
                continue
            assert len(targets) == 1, ("Ambiguous regexp builtin pointer", targets)
            target = targets[0]
            routes.append(
                dict(
                    section=sn,
                    name=name,
                    offset=offset,
                    old_symbol=old,
                    old_addend=value,
                    kind=kind,
                    builtin=target,
                    destination=builtin_routes[target],
                )
            )
            struct.pack_into("<I", c.data, at + 4, new_symbols[target])
            struct.pack_into("<Q", c.data, r["raw"] + offset, 0)
    assert sorted(r["builtin"] for r in routes) == sorted(builtin_routes), (
        "Expected one pointer per owned regexp builtin",
        routes,
    )
    end = c.string_offset + struct.unpack_from("<I", raw, c.string_offset)[0]
    result = bytearray(c.finish())
    shift = len(result) - len(raw)
    # The inherited GCC adapter appends decoded relocations after the string table.
    for rec in c.section_records:
        for field in (20, 24, 28):
            at = rec["pos"] + field
            value = struct.unpack_from("<I", raw, at)[0]
            if value and value >= end:
                struct.pack_into("<I", result, at, value + shift)
    result = bytes(result)
    verified = adapter.Coff(result)
    for i, (old, new) in enumerate(zip(adapter.Coff(raw).sections, verified.sections), 1):
        if i not in {r["section"] for r in routes}:
            assert old == new, (i, old, new)
    for old in adapter.Coff(raw).all_symbols.values():
        if old["type"] & 32 and old["section"] > 0:
            new = verified.symbols[old["name"]]
            assert (old["value"], old["section"], old["storage"]) == (
                new["value"],
                new["section"],
                new["storage"],
            )
    backup = path.with_name(path.name + ".before-regexp")
    assert not backup.exists()
    backup.write_bytes(raw)
    path.write_bytes(result)
    return dict(
        before_sha256=sha(backup),
        after_sha256=sha(path),
        routes=routes,
        executable_sections_identical=True,
        original_function_symbols_unchanged=True,
        additional_helper_aliases=exports,
    )


def compile_extra(source, build, out):
    compiler = module(source, "atod")
    generated = {}
    old_argv = compiler.win_argv

    def island_argv(command):
        args = old_argv(command)
        if "gcc.exe" in args[0].lower():
            args = [x for x in args if not x.startswith("-g")] + ["-g0"]
        return args

    compiler.win_argv = island_argv

    def generator(src, target):
        exports, copies, private, builtin_routes = generate(src, build, target)
        generated.update(
            exports=exports,
            copies=copies,
            private=str(private),
            private_sha256=sha(private),
            builtin_routes=builtin_routes,
            exec_source_sha256=sha(src / "src/common/regexp/exec.inc"),
        )

    commands = json.loads((_frame_build_file(build, "compile_commands.json")).read_text())
    msvc = any(
        "/nologo" in r["command"].lower()
        for r in commands
        if Path(r["file"]).name == "quickjs-interpreter.c"
    )
    compiler.compile_extra(
        source,
        build,
        out,
        generator=generator,
        filename="quickjs-regexp-replace.c",
        late_name=".qjscold$zznullfast" if msvc else ".qjszre$C",
    )
    adapter = module(source, "object-adapter")
    c = adapter.Coff(out.read_bytes())
    mingw = any(
        "gcc.exe" in x.lower()
        for x in json.loads(out.with_suffix(".compile.json").read_text())["compiler_command"]
    )
    if mingw:
        for sn, r in enumerate(c.section_records, 1):
            name = section_name(c, sn)
            if not name.startswith(".pdata"):
                continue
            renamed = ".qjsrfn$C"
            at = len(c.strings)
            c.strings += renamed.encode() + b"\0"
            c.data[r["pos"] : r["pos"] + 8] = ("/" + str(at)).encode().ljust(8, b"\0")
            for index, sym in c.all_symbols.items():
                if (
                    sym["section"] == sn
                    and sym["name"] == name
                    and sym["storage"] == 3
                    and sym["type"] == 0
                ):
                    struct.pack_into("<II", c.data, c.table + index * c.stride, 0, at)
        out.write_bytes(c.finish())
    # GCC uses a standard readonly .refptr cell for the original exec fallback.
    # It is a PE base-relocated data pointer, never an absolute code operand.
    # Preserve its compiler COMDAT section/key and validate its exact
    # zero-filled, single-pointer shape.
    compiler_refptrs = []
    for sn, r in enumerate(c.section_records, 1):
        if section_name(c, sn).startswith(".debug"):
            continue
        for i in range(r["count"]):
            off, sym, kind = struct.unpack_from("<IIH", c.data, r["reloc"] + 10 * i)
            if kind != 1:
                continue
            target = c.all_symbols[sym]
            refptr = [
                s
                for s in c.all_symbols.values()
                if s["name"] == ".refptr." + target["name"]
                and s["section"] == sn
                and s["value"] == 0
                and s["type"] == 0
                and s["storage"] == 2
            ]
            assert (
                mingw
                and target["name"]
                in (
                    "qjs_frame_core_js_regexp_exec",
                    "qjs_frame_core_js_regexp_get_flag",
                    "qjs_frame_core_js_regexp_get_flags",
                    "qjs_frame_core_js_get_this",
                    "qjs_frame_core_js_string_localeCompare",
                )
                and target["section"] == 0
                and target["value"] == 0
                and target["type"] == 32
                and target["storage"] == 2
                and len(refptr) == 1
                and r["count"] == 1
                and off == 0
                and r["size"] in (8, 16)
                and r["flags"] & 0x40
                and section_name(c, sn) == ".rdata$.refptr." + target["name"]
                and not r["flags"] & 0xA0000020
                and r["raw"]
                and not any(c.data[r["raw"] : r["raw"] + r["size"]])
            ), ("Unexpected absolute pointer in new regexp island", off, target)
            compiler_refptrs.append(
                dict(
                    section=sn,
                    target=target["name"],
                    size=r["size"],
                    offset=off,
                    kind=kind,
                    standard_pe_base_relocation=True,
                )
            )
    if msvc:
        merger = module(source, "extension-merge")
        # This separate edge appends to an already completed Ninja input.
        # Preserve its producer timestamp so it does not perpetually dirty this edge.
        import os

        destination = _frame_generated_file(build, "quickjs-interpreter-null-proto.obj")
        stamp = destination.stat()
        controls = [
            r for sn, r in enumerate(c.section_records, 1) if section_name(c, sn) == ".qjsrfm"
        ]
        if generated["builtin_routes"].get("js_regexp_get_flags"):
            assert len(controls) == 1 and controls[0]["size"] == 1 and controls[0]["count"] == 0
            assert c.data[controls[0]["raw"]] == 0
        else:
            assert not controls
        locale_controls = [
            r for sn, r in enumerate(c.section_records, 1) if section_name(c, sn) == ".qjslfm"
        ]
        assert (
            len(locale_controls) == 1
            and locale_controls[0]["size"] == 1
            and locale_controls[0]["count"] == 0
        )
        assert c.data[locale_controls[0]["raw"]] == 0
        merger.append(
            destination,
            out,
            "JS_RegExpOwnedReplace",
            "regexp",
            keep_all=True,
            writable_metadata_inputs=((".qjsrfm",) if controls else ()) + (".qjslfm",),
        )
        os.utime(destination, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
    array = module(source, "array-copy").compile_extra(
        source, build, _frame_generated_file(build, "quickjs-array-copy.obj")
    )
    generated["array_copy"] = array
    default_sort = module(source, "default-sort").compile_extra(
        source, build, _frame_generated_file(build, "quickjs-default-sort.obj")
    )
    generated["default_sort"] = default_sort
    generator_capability = module(source, "generator-capability").compile_extra(
        source, build, _frame_generated_file(build, "quickjs-generator-capability.obj")
    )
    generated["generator_capability"] = generator_capability
    strings = module(source, "string").compile_extra(
        source, build, _frame_generated_file(build, "quickjs-string.obj")
    )
    generated["strings"] = strings
    from regexp_split import compile_extra as compile_split

    split = compile_split(source, build, _frame_generated_file(build, "quickjs-regexp-split.obj"))
    generated["split"] = split
    generated["exports"] = sorted(set(generated["exports"]) | set(split["exports"]))
    generated["builtin_routes"]["js_regexp_Symbol_split"] = "JS_RegExpSplitDispatch"
    generated["builtin_routes"]["js_regexp_Symbol_replace"] = "JS_RegExpReplaceDispatch"
    generated["exports"] = sorted(
        set(generated["exports"])
        | set(array["exports"])
        | set(strings["exports"])
        | set(default_sort["exports"])
        | set(generator_capability["exports"])
    )
    core = adapt_core(source, build, generated["exports"], generated["builtin_routes"])
    generated["array_copy_route"] = module(source, "array-copy").route_core(source, build)
    generated["default_sort_route"] = module(source, "default-sort").route_core(source, build)
    generated["generator_capability_route"] = module(source, "generator-capability").route_core(
        source, build
    )
    record = out.with_suffix(".compile.json")
    receipt = json.loads(record.read_text())
    receipt.update(
        object_sha256=sha(out),
        generator_sha256=sha(Path(__file__)),
        generated=generated,
        core=core,
        compiler_refptrs=compiler_refptrs,
        contract="Independent builtin and array-copy TUs. Core source unchanged. First-stage core receipt covers listed regexp/locale table pointers and helper aliases; generated.array_copy_route covers the single allowed splice call operand and relocation. Array builtin table pointers and original symbols stay unchanged.",
        unwind="New MinGW records and merged directory follow inherited islands; MSVC compiler .pdata retained.",
    )
    record.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(
        "BUILTIN WORKERS COMPILED;",
        len(generated["builtin_routes"]),
        "prototype pointers and one audited splice call routed",
        flush=True,
    )


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", type=Path, required=True)
    ap.add_argument("--build", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    compile_extra(a.source, a.build, a.out)
