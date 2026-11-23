"""Complete accepted owned RegExp wrappers with real same-TU Linux types.

The common exec/test algorithms already own their original intrinsic identity.
Reuse them,then compose the shared owned argv,live flag getters and independent
split/empty-search bodies without binary object edits or duplicated core algorithms.
"""

import hashlib
import json
import re
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from common.paths import source_file
from c_workers import module, replace_one

# Default common files;
OWNERS = (
    "tools/common/c_extract/regexp_c.py",
    "tools/common/backports/regexp_test.py",
    "src/common/regexp/exec.inc",
    "src/common/regexp/test.inc",
    "src/common/regexp/split.inc",
    "src/common/regexp/replace-empty.inc",
    "src/common/regexp/flag-atoms.inc",
    "src/common/kernel/regexp-replace.inc",
    "src/common/kernel/regexp-flags.inc",
)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def contract(source, *, contract_rel):
    data = json.loads((source / contract_rel).read_text())
    owners = data.get("owners") or data.get("source_owners") or {}
    for n, h in owners.items():
        if sha(source_file(source, n)) != h:
            raise ValueError("Review accepted RegExp semantic owner: " + n)
    if (
        "pinned_core_sha256" in data
        and sha(source_file(source, "quickjs.c")) != data["pinned_core_sha256"]
    ):
        raise ValueError("Review pinned RegExp getter/flag/hash/observable order")
    return data


def guard_entry(text, name, guard):
    signature = "JSValue " + name + "("
    if text.count(signature) != 1:
        raise ValueError("Review RegExp worker entry: " + name)
    start = text.index("{", text.index(signature)) + 1
    return text[:start] + "\n" + guard + "\n" + text[start:]


def generate(
    source,
    output,
    core,
    layout,
    *,
    contract_rel,
    platform_binding="src/common/linux/interpreter-regexp.inc",
    abi_label="native",
    arch_adapt=None,
):
    data = contract(source, contract_rel=contract_rel)
    ref_model = layout["reference_count_model"]
    if ref_model == "allocator-prefix":
        if (
            layout["offsets"]["JSMallocBlockHeader.ref_count"]
            - layout["offsets"]["JSMallocBlockHeader.user_data"]
            != -4
        ):
            raise ValueError("Review GNU RegExp source profile")
    elif ref_model != "inline-header":
        raise ValueError("Review GNU RegExp source profile")
    owner = module(source, "regexp-c")
    raw = source_file(source, "quickjs.c").read_text()
    body, routes = owner.semantic_source(source, inline=True, include_independent=False)
    # Actual C-overlay exec/test are byte-identical to the shared semantic
    # bodies. Preserve their original builtin pointer and standard-exec proof.
    directory = Path(layout["compiler_input"]).parent
    exec_path = directory / "quickjs-portable-regexp-exec.h"
    if exec_path.read_text() != owner.exec_body(source, raw):
        raise ValueError("The actual Linux exec body is not the shared owner")
    test_path = directory / "quickjs-regexp-test-portable.h"
    expected = (
        module(source, "regexp_test")
        .native_body(raw, source)
        .replace("JSValue JS_FrameRegExpTest(", "static JSValue js_regexp_test(", 1)
    )
    if test_path.read_text() != expected:
        raise ValueError("The actual Linux test body is not the shared owner")
    declaration = """
__attribute__((visibility("hidden"))) JSValue JS_RegExpOwnedReplace(JSContext *,JSValueConst,int,JSValueConst *);
__attribute__((visibility("hidden"))) JSValue JS_RegExpOwnedMatch(JSContext *,JSValueConst,int,JSValueConst *);
__attribute__((visibility("hidden"))) JSValue JS_RegExpOwnedMatchAll(JSContext *,JSValueConst,int,JSValueConst *);
__attribute__((visibility("hidden"))) JSValue JS_RegExpOwnedSplit(JSContext *,JSValueConst,int,JSValueConst *);
__attribute__((visibility("hidden"))) JSValue JS_RegExpOwnedFlags(JSContext *,JSValueConst);
__attribute__((visibility("hidden"))) JSValue JS_LinuxRegExpSplitDispatch(JSContext *,JSValueConst,int,JSValueConst *);
__attribute__((visibility("hidden"))) JSValue JS_LinuxRegExpReplaceDispatch(JSContext *,JSValueConst,int,JSValueConst *);
"""
    anchor = "static const JSCFunctionListEntry js_regexp_proto_funcs[]"
    a = core.index(anchor)
    b = core.index("\n};", a) + 3
    table = core[a:b]
    routes["js_regexp_Symbol_replace"] = "JS_LinuxRegExpReplaceDispatch"
    routes["js_regexp_Symbol_split"] = "JS_LinuxRegExpSplitDispatch"
    for old, new in routes.items():
        table, count = re.subn(r"\b" + re.escape(old) + r"\b", new, table)
        if count != 1:
            raise ValueError("Review actual RegExp builtin table target: " + old)
    core = core[:a] + declaration + table + core[b:]
    # The accepted owned argv worker has the original seven-argument call
    # contract. The Linux selector is source-defined in this complete core TU.
    external = """#ifdef QJS_INTERP_FRAME_INTERNAL_ENTRY
extern JSValue JS_FrameDispatchInternal(JSContext *, JSValueConst, JSValueConst, JSValueConst, int,
                                        JSValueConst *, int);
#endif
"""
    body = replace_one(body, external, "", "same-TU real Linux internal selector")
    if body.count("JS_FrameDispatchInternal(") != 1:
        raise ValueError("Review original owned callback call boundary")
    body = body.replace("JS_FrameDispatchInternal(", "JS_CallInternal(")
    body = body.replace('".qjsrfm"', '".data.qjs_linux_regexp"')
    for old, new in routes.items():
        name = {
            "js_regexp_Symbol_replace": "JS_RegExpOwnedReplace",
            "js_regexp_Symbol_match": "JS_RegExpOwnedMatch",
            "js_regexp_Symbol_matchAll": "JS_RegExpOwnedMatchAll",
            "js_regexp_Symbol_split": "JS_RegExpOwnedSplit",
            "js_regexp_get_flags": "JS_RegExpOwnedFlags",
        }[old]
        if old == "js_regexp_get_flags":
            guard = "    if ((js_linux_regexp_mode() & 3) != 1) return js_regexp_get_flags(ctx,this_val);"
        elif old == "js_regexp_Symbol_replace":
            guard = "    if ((js_linux_regexp_mode() & 7) != 1) return js_regexp_Symbol_replace(ctx,this_val,argc,argv);"
        else:
            guard = (
                "    if ((js_linux_regexp_mode() & 3) != 1) return "
                + old
                + "(ctx,this_val,argc,argv);"
            )
        body = guard_entry(body, name, guard)
    # These helper families already exist in the portable core. Give the
    # native identity-aware consumers their own names,not conflicting copies.
    split = (source / "src/common/regexp/split.inc").read_text()
    empty = (source / "src/common/regexp/replace-empty.inc").read_text()
    split_names = sorted(set(re.findall(r"\bjs_regexp_split_\w+", split)))
    empty_names = sorted(set(re.findall(r"\bjs_regexp_empty_\w+", empty)))
    for n in split_names:
        split = re.sub(r"\b" + n + r"\b", n.replace("js_regexp_", "js_linux_regexp_"), split)
    for n in empty_names:
        empty = re.sub(r"\b" + n + r"\b", n.replace("js_regexp_", "js_linux_regexp_"), empty)
    native = (
        """
#define JS_FrameRegExpExec js_regexp_exec
#define QJS_REGEXP_SPLIT_NATIVE 1
"""
        + split
        + """
#undef QJS_REGEXP_SPLIT_NATIVE
#define QJS_REGEXP_EMPTY_NATIVE 1
"""
        + empty
        + """
#undef QJS_REGEXP_EMPTY_NATIVE
#undef JS_FrameRegExpExec
JSValue JS_LinuxRegExpSplitDispatch(JSContext *ctx,JSValueConst receiver,int argc,JSValueConst *argv)
{
    if ((js_linux_regexp_mode() & 3) != 1)
        return js_regexp_Symbol_split(ctx,receiver,argc,argv);
    if (js_linux_regexp_split_guard(ctx,receiver,argv[0],argv[1]))
        return js_linux_regexp_split_search(ctx,receiver,argv[0],argv[1]);
    return JS_RegExpOwnedSplit(ctx,receiver,argc,argv);
}
JSValue JS_LinuxRegExpReplaceDispatch(JSContext *ctx,JSValueConst receiver,int argc,JSValueConst *argv)
{
    if ((js_linux_regexp_mode() & 3) != 1)
        return js_regexp_Symbol_replace(ctx,receiver,argc,argv);
    int flags;JSProperty *last_index;
    if (js_linux_regexp_empty_guard(ctx,receiver,argv[0],argv[1],&flags,&last_index))
        return js_linux_regexp_empty_search(ctx,receiver,argv[0],flags,last_index);
    return JS_RegExpOwnedReplace(ctx,receiver,argc,argv);
}
"""
    )
    text = body + "\n" + native
    text = text.replace('".qjsrem"', '".data.qjs_linux_regexp"')
    text = replace_one(
        text,
        "    static _Atomic unsigned char control;",
        '    static _Atomic unsigned char control __attribute__((section(".data.qjs_linux_regexp")));',
        "new empty-search control belongs to its late Linux data family",
    )
    # Outline only new non-inline workers. Shared helpers retain their actual
    # core types;normal original executable code is not replaced or patched.
    text = re.sub(
        r"^(static )?(JSValue|bool) (\w+)\(",
        lambda m: (m[1] or "") + "QJS_LINUX_REGEXP_CODE " + m[2] + " " + m[3] + "(",
        text,
        flags=re.M,
    )
    text = f'#include "{platform_binding}"\n' + text + "\n#undef QJS_LINUX_REGEXP_CODE\n"
    target = output / "quickjs-linux-regexp.h"
    target.write_text(text)
    core += '\n#include "quickjs-linux-regexp.h"\n'
    record = dict(
        status="generated-not-qualified",
        owners=data.get("owners") or data.get("source_owners", {}),
        source_files={
            n: sha(source / n) for n in ("tools/common/elf/regexp_workers.py", platform_binding)
        },
        generated_sha256=sha(target),
        builtin_routes=routes,
        shared_original_exec=dict(
            path=str(exec_path), sha256=sha(exec_path), identity="js_regexp_exec"
        ),
        shared_original_test=dict(
            path=str(test_path), sha256=sha(test_path), identity="js_regexp_test"
        ),
        entries=[
            "JS_RegExpOwnedReplace",
            "JS_RegExpOwnedMatch",
            "JS_RegExpOwnedMatchAll",
            "JS_RegExpOwnedSplit",
            "JS_RegExpOwnedFlags",
            "JS_LinuxRegExpSplitDispatch",
            "JS_LinuxRegExpReplaceDispatch",
        ],
        private_helpers=[
            n.replace("js_regexp_", "js_linux_regexp_") for n in split_names + empty_names
        ],
        callback=f"Actual JS_CallInternal(ctx,rep,undefined,undefined,argc,owned_argv,COPY_ARGV);existing coherent builtin C/{abi_label} boundary",
        controls=[
            "QJS_DISABLE_LINUX_REGEXP_WORKERS",
            "QJS_DISABLE_LINUX_REGEXP_OWNED_ARGV",
            "QJS_DISABLE_REGEXP_FLAGS_LEAF",
            "QJS_DISABLE_REGEXP_FLAGS_BATCH",
            "QJS_DISABLE_REGEXP_SPLIT",
            "QJS_DISABLE_REGEXP_REPLACE_EMPTY",
        ],
        frame_growth=0,
        state_growth=0,
        new_strong_roots=0,
        heap="Original owned callback argv,stack6 then transient allocation;no persistent new cache",
    )
    if arch_adapt is not None:
        text, extra = arch_adapt(source, text)
        target.write_text(text)
        record.update(extra, generated_sha256=sha(target))
    (output / "REGEXP-WORKERS.json").write_text(json.dumps(record, indent=2) + "\n")
    return core, record
