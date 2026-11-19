"""Rebuild the retained serializer from this checkout's original engine."""

import argparse
import hashlib
import importlib.util
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from common.paths import activate_tools, source_file, tool_path

activate_tools()
spec = importlib.util.spec_from_file_location("wire_source_parser", tool_path("object-adapter-c"))
adapter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)


def replace_once(text, before, after):
    if text.count(before) != 1:
        raise ValueError("Review upstream wire change near: " + before[:100])
    return text.replace(before, after, 1)


def generate(source):
    core = source_file(source, "quickjs.c").read_text(encoding="utf-8")
    legacy_regexp = (
        hashlib.sha256(core.encode()).hexdigest()
        == "ddab054455e43cfafbe5c0671fa38acd9f3a1eac4ce2a49a97dfec6437701ebe"
    )
    functions = {match[2]: match for match in adapter.FUNCTION.finditer(core)}
    first = core.index("/* object list */")
    first = core.rfind(
        "/*******************************************************************/", 0, first
    )
    body = core[first : functions["JS_ReadObject"].end()] + "\n\n"
    body += re.search(r"^#define MAGIC_SET[^\n]*", core, re.M)[0] + "\n"
    body += (
        "\n\n".join(
            functions[name][0]
            for name in (
                "js_map_read",
                "js_map_write",
                "JS_ReadMap",
                "JS_ReadSet",
                "JS_WriteMap",
                "JS_WriteSet",
            )
        )
        + "\n"
    )
    body = replace_once(
        body,
        "    bool allow_debug;\n",
        "    bool allow_debug;\n#ifdef QJS_FRAME_REGEXP_LEGACY_WIRE\n    bool extended_regexp;\n#endif\n",
    )

    def edit(name, changes):
        nonlocal body
        original = functions[name][0]
        modified = original
        for before, after in changes:
            modified = replace_once(modified, before, after)
        body = replace_once(body, original, modified)

    edit(
        "bc_put_atom",
        [
            (
                "        if (bc_atom_to_idx(s, &v, atom))\n            return -1;",
                "        if (bc_atom_to_idx(s, &v, atom)) {\n"
                "            /* Some writer callers only observe the sticky buffer error. */\n"
                "            dbuf_set_error(&s->dbuf);\n            return -1;\n        }",
            )
        ],
    )
    edit(
        "JS_WriteFunctionTag",
        [
            (
                "    int idx, i;\n",
                "    int idx, i;\n    FrameRegExpConstant *regexp_cpool = NULL;\n",
            ),
            (
                "    for(i = 0; i < b->cpool_count; i++) {\n        if (JS_WriteObjectRec(s, b->cpool[i]))\n            goto fail;\n    }",
                "    if (JS_RegExpConstantMask(s->ctx, b, &regexp_cpool))\n        goto fail;\n"
                "    for(i = 0; i < b->cpool_count; i++) {\n"
                "#ifdef QJS_FRAME_REGEXP_LEGACY_WIRE\n"
                "        if (regexp_cpool && regexp_cpool[i]) {\n"
                "            bc_put_u8(s, BC_TAG_STRING);\n"
                "            if (JS_WritePortableRegExpBytecode(s,\n"
                "                JS_VALUE_GET_STRING(b->cpool[regexp_cpool[i] - 1]),\n"
                "                JS_VALUE_GET_STRING(b->cpool[i])))\n                goto fail;\n"
                "        } else\n#endif\n        {\n"
                "            if (JS_WriteObjectRec(s, b->cpool[i]))\n                goto fail;\n"
                "#ifndef QJS_FRAME_REGEXP_LEGACY_WIRE\n"
                "            if (regexp_cpool && regexp_cpool[i] &&\n"
                "                JS_FinishWriteRegExpBytecode(s, JS_VALUE_GET_STRING(b->cpool[i])))\n                goto fail;\n"
                "#endif\n        }\n    }",
            ),
            (
                "    return 0;\n fail:\n    return -1;",
                "    js_free(s->ctx, regexp_cpool);\n    return 0;\n fail:\n    js_free(s->ctx, regexp_cpool);\n    return -1;",
            ),
        ],
    )
    edit(
        "JS_WriteRegExp",
        [
            (
                "    JS_WriteString(s, bc);\n    return 0;",
                "#ifdef QJS_FRAME_REGEXP_LEGACY_WIRE\n"
                "    return JS_WritePortableRegExpBytecode(s, regexp.pattern, bc);\n"
                "#else\n    JS_WriteString(s, bc);\n"
                "    /* Canonicalize the output copy, never the shared live RegExp string. */\n"
                "    return JS_FinishWriteRegExpBytecode(s, bc);\n#endif",
            )
        ],
    )
    edit(
        "JS_WriteObjectAtoms",
        [
            (
                "    dbuf1 = s->dbuf;",
                "    if (dbuf_error(&s->dbuf))\n        return -1;\n    dbuf1 = s->dbuf;",
            ),
            (
                "    /* XXX: should check for OOM in above phase */",
                "    if (dbuf_error(&s->dbuf))\n        goto fail;",
            ),
            (
                "    bc_put_u8(s, BC_VERSION);",
                "#ifdef QJS_FRAME_REGEXP_LEGACY_WIRE\n"
                "    bc_put_u8(s, s->extended_regexp ? FRAME_REGEXP_WIRE_VERSION : BC_VERSION);\n"
                "#else\n    bc_put_u8(s, BC_VERSION);\n#endif",
            ),
        ],
    )
    edit(
        "JS_ReadFunctionTag",
        [
            (
                "    b = js_mallocz(ctx, function_size);",
                "    b = JS_FrameOwnBytecodeAllocateContext(ctx, function_size);",
            ),
            (
                "        if (JS_ReadFunctionBytecode(s, b, byte_code_offset, b->byte_code_len))\n            goto fail;",
                "        if (JS_ReadFunctionBytecode(s, b, byte_code_offset, b->byte_code_len))\n            goto fail;\n"
                "        if (JS_PrepareFunctionRegExp(ctx, b))\n            goto fail;",
            ),
        ],
    )
    edit(
        "JS_ReadRegExp",
        [
            (
                "    if (bc->is_wide_char) {",
                "#ifdef QJS_FRAME_REGEXP_LEGACY_WIRE\n"
                "    {\n        JSString *runtime = JS_CompileImportedRegExp(ctx, pattern, bc);\n"
                "        if (!runtime) {\n            js_free_string(ctx->rt, pattern);\n"
                "            js_free_string(ctx->rt, bc);\n            return JS_EXCEPTION;\n        }\n"
                "        JS_FreeValue(ctx, JS_MKPTR(JS_TAG_STRING, bc));\n        bc = runtime;\n    }\n"
                "#else\n    /* Restore runtime opcodes only on this private imported copy. */\n"
                "    if (bc->is_wide_char ||\n        lre_prepare_bytecode(str8(bc), bc->len, true) != 0) {",
            ),
            (
                "    return js_regexp_constructor_internal(",
                "#endif\n    return js_regexp_constructor_internal(",
            ),
        ],
    )
    edit(
        "JS_ReadObjectAtoms",
        [
            (
                "    if (v8 != BC_VERSION) {",
                "    if (v8 != BC_VERSION\n"
                "#ifdef QJS_FRAME_REGEXP_LEGACY_WIRE\n        && v8 != FRAME_REGEXP_WIRE_VERSION\n"
                "#endif\n       ) {",
            )
        ],
    )
    at = body.index("static int JS_WriteFunctionTag(")
    body = body[:at] + '#include "src/common/wire/regexp_wire.inc"\n\n' + body[at:]
    return (
        "/* Generated from quickjs.c SHA256 "
        + hashlib.sha256(core.encode()).hexdigest()
        + "; do not edit. */\n"
        + ("#define QJS_FRAME_REGEXP_LEGACY_WIRE 1\n" if legacy_regexp else "")
        + '#include "src/common/regexp/libregexp.h"\n#include "interpreter-wire-private.h"\n'
        "extern void *JS_FrameOwnBytecodeAllocateContext(JSContext *,size_t);\n" + body
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    body = generate(args.source.resolve())
    if args.check:
        if not args.output.is_file() or args.output.read_text(encoding="utf-8") != body:
            raise SystemExit(
                "Wire source is stale; regenerate it and review the upstream serializer changes"
            )
    else:
        args.output.write_text(body, encoding="utf-8", newline="\n")
    print("Wire: current upstream format plus retained RegExp/ownership/OOM behavior verified")


if __name__ == "__main__":
    main()
