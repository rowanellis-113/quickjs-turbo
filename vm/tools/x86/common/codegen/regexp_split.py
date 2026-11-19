"""Compile the shared split search independently of existing builtin workers."""

import hashlib
import importlib.util
import json
import re
from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from x86.common.paths_x86 import activate_tools, tool_path, generated_file, source_file

activate_tools()


def module(name):
    spec = importlib.util.spec_from_file_location("split_" + name, tool_path(name))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def section_name(coff, index):
    name = coff.sections[index - 1]["name"]
    if name.startswith("/"):
        at = int(name[1:])
        name = coff.strings[at : coff.strings.index(0, at)].decode()
    return name


def compile_extra(source, build, out):
    adapter, compiler = module("object-adapter"), module("atod")
    original_argv = compiler.win_argv
    compiler.win_argv = lambda text: (
        [x for x in original_argv(text) if not x.startswith("-g")] + ["-g0"]
        if "gcc.exe" in original_argv(text)[0].lower()
        else original_argv(text)
    )
    generated = {}

    def generate(src, target):
        text = source_file(src, "quickjs.c").read_text(encoding="utf-8")
        coff = adapter.Coff(generated_file(build, "quickjs-core-original.obj").read_bytes())
        body = (
            """JSValue JS_FrameRegExpExec(JSContext *, JSValueConst, int, JSValueConst *);
JSValue JS_RegExpOwnedFlags(JSContext *, JSValueConst);
JSValue JS_RegExpOwnedSplit(JSContext *, JSValueConst, int, JSValueConst *);
JSValue JS_RegExpOwnedReplace(JSContext *, JSValueConst, int, JSValueConst *);
#define QJS_REGEXP_SPLIT_NATIVE 1
"""
            + (src / "src/common/regexp/split.inc").read_text(encoding="utf-8")
            + """
#undef QJS_REGEXP_SPLIT_NATIVE
JSValue JS_RegExpSplitDispatch(JSContext *ctx, JSValueConst receiver, int argc, JSValueConst *argv)
{
    if (js_regexp_split_guard(ctx, receiver, argv[0], argv[1]))
        return js_regexp_split_search(ctx, receiver, argv[0], argv[1]);
    return JS_RegExpOwnedSplit(ctx, receiver, argc, argv);
}
"""
        )
        body += (
            "\n#define QJS_REGEXP_EMPTY_NATIVE 1\n"
            + (src / "src/common/regexp/replace-empty.inc").read_text(encoding="utf-8")
            + "\n#undef QJS_REGEXP_EMPTY_NATIVE\nJSValue JS_RegExpReplaceDispatch(JSContext *ctx, JSValueConst receiver, int argc, JSValueConst *argv)\n{\n    int flags;\n    JSProperty *last_index;\n    if (js_regexp_empty_guard(ctx, receiver, argv[0], argv[1], &flags, &last_index))\n        return js_regexp_empty_search(ctx, receiver, argv[0], flags, last_index);\n    return JS_RegExpOwnedReplace(ctx, receiver, argc, argv);\n}\n"
        )
        match = re.search(r"typedef struct StringBuffer\s*\{.*?\}\s*StringBuffer;", text, re.S)
        assert match, "Pinned StringBuffer type changed"
        text = text.replace(
            "static inline bool double_is_int32",
            match[0] + "\nstatic inline bool double_is_int32",
            1,
        )
        header, exports, copies = adapter.generate(text, coff, body)
        private = generated_file(build, "quickjs-regexp-split-private.h")
        private.write_text(header, encoding="utf-8", newline="\n")
        target.write_text(
            '#include "quickjs-regexp-split-private.h"\n' + body, encoding="utf-8", newline="\n"
        )
        generated.update(
            exports=exports,
            copies=copies,
            private=str(private),
            private_sha256=hashlib.sha256(private.read_bytes()).hexdigest(),
        )

    commands = json.loads((build / "compile_commands.json").read_text())
    msvc = any(
        "/nologo" in item["command"].lower()
        for item in commands
        if Path(item["file"]).name == "quickjs-interpreter.c"
    )
    # Reuse the existing late executable output groups. A new PE section can
    # expand headers across the first mapped page; independent TUs do not
    # require independent loader sections.
    late = ".qjzzlc$zzsplit" if msvc else ".qjsex$zzsplit"
    compiler.compile_extra(
        source, build, out, generator=generate, filename="quickjs-regexp-split.c", late_name=late
    )
    coff = adapter.Coff(out.read_bytes())
    mingw = any(
        "gcc.exe" in x.lower()
        for x in json.loads(out.with_suffix(".compile.json").read_text())["compiler_command"]
    )
    allowed = {
        "qjs_frame_core_js_regexp_exec",
        "qjs_frame_core_js_regexp_get_flag",
        "qjs_frame_core_js_regexp_get_flags",
        "qjs_frame_core_js_get_this",
        "JS_RegExpOwnedFlags",
        "JS_RegExpOwnedSplit",
        "JS_RegExpOwnedReplace",
        "JS_FrameRegExpExec",
    }
    original_core = adapter.Coff(generated_file(build, "quickjs-core-original.obj").read_bytes())
    original_worker = adapter.Coff(generated_file(build, "quickjs-regexp-replace.obj").read_bytes())
    refs = []
    for index, record in enumerate(coff.section_records, 1):
        if section_name(coff, index).startswith(".debug"):
            continue
        for i in range(record["count"]):
            offset, symbol, kind = struct.unpack_from("<IIH", coff.data, record["reloc"] + 10 * i)
            if kind != 1:
                continue
            target = coff.all_symbols[symbol]
            cells = [
                s
                for s in coff.all_symbols.values()
                if s["name"] == ".refptr." + target["name"]
                and s["section"] == index
                and s["value"] == 0
                and s["type"] == 0
                and s["storage"] == 2
            ]
            owner, name = (
                (original_core, target["name"][len("qjs_frame_core_") :])
                if target["name"].startswith("qjs_frame_core_")
                else (original_worker, target["name"])
            )
            definition = next(
                (s for s in owner.all_symbols.values() if s["name"] == name and s["section"] > 0),
                None,
            )
            # GCC may mark an address-only undefined symbol NOTYPE. Verify
            # the defining object's actual function symbol as well as its
            # single readonly, zero-filled compiler import cell.
            assert (
                mingw
                and target["name"] in allowed
                and target["section"] == 0
                and target["value"] == 0
                and target["type"] in (0, 32)
                and target["storage"] == 2
                and definition
                and definition["section"] > 0
                and definition["type"] & 32
                and len(cells) == 1
                and record["count"] == 1
                and offset == 0
                and record["size"] in (8, 16)
                and record["flags"] & 0x40
                and not record["flags"] & 0xA0000020
                and section_name(coff, index) == ".rdata$.refptr." + target["name"]
                and not any(coff.data[record["raw"] : record["raw"] + record["size"]])
            ), ("Unexpected absolute split pointer", offset, target)
            refs.append(dict(section=index, target=target["name"], size=record["size"]))
    path = out.with_suffix(".compile.json")
    receipt = json.loads(path.read_text())
    receipt.update(
        generated=generated,
        compiler_refptrs=refs,
        contract="Independent native split TU; ordinary compiler unwind and bounded readonly refptr cells; existing builtin worker source is unchanged.",
    )
    path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8", newline="\n")
    return dict(
        exports=generated["exports"],
        object=str(out),
        object_sha256=hashlib.sha256(out.read_bytes()).hexdigest(),
        receipt=str(path),
    )
