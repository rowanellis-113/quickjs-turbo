"""Own complete shared string kernels in actual Linux core types and SysV C."""

import hashlib
import json
import re
from c_workers import module, replace_one


def generate(
    source,
    output,
    core,
    adapter,
    layout,
    *,
    compat_header="src/common/linux/interpreter-linux-compat.inc",
):
    from common.paths import source_text, source_file
    from string_rope import equality_function

    raw = source_file(source, "quickjs.c").read_text()
    _, equality = equality_function(raw)
    if core.count(equality) != 1:
        raise ValueError("Review existing complete common rope-equality algorithm")
    local_source = module(source, "local-string-c").generate(source, None, source_owned=True)
    matches = [
        m[0] for m in adapter.FUNCTION.finditer(local_source) if m[2] == "JS_FrameAddLocalString"
    ]
    if len(matches) != 1:
        raise ValueError("Review complete add_loc string source")
    local = matches[0]
    local = replace_one(
        local,
        "    unsigned char *mode=(unsigned char *)state->rt+offsetof(JSRuntime,module_loader_has_attr)+3;\n",
        "",
        "replace native add_loc policy location",
    )
    begin = local.index("    const char *flag;")
    end = local.index("    assert(tag_is_string", begin)
    local = (
        local[:begin]
        + """    if (linux_string_policy(&qjs_linux_string_local_add_mode, "QJS_DISABLE_NATIVE_ADD_LOCAL") != 1)
        return JS_FrameInterpSlow(state);
"""
        + local[end:]
    )
    local = local.replace("LOCAL_STRING_CODE", "LINUX_STRING_CODE")
    old_concat = "    result=JS_ConcatString(ctx,js_dup(*pv),sp[-1]);"
    new_concat = """    if (JS_VALUE_GET_TAG(*pv) == JS_TAG_STRING && JS_VALUE_GET_TAG(sp[-1]) == JS_TAG_STRING) {
        JSString *p1 = JS_VALUE_GET_STRING(*pv);
        JSString *p2 = JS_VALUE_GET_STRING(sp[-1]);
        if (p2->len == 0) {
            JS_FreeValue(ctx, sp[-1]);
            js_frame_finish_c(state);
            return 2;
        }
        if (JS_REF_COUNT(p1) == 1 && !p1->atom_type && p1->kind == JS_STRING_KIND_NORMAL &&
            p1->is_wide_char == p2->is_wide_char &&
            js_malloc_usable_size(ctx, p1) >=
                sizeof(*p1) + (((size_t)p1->len + (size_t)p2->len) << p1->is_wide_char) + 1 -
                    p1->is_wide_char) {
            if (p1->is_wide_char) {
                memcpy(str16(p1) + p1->len, str16(p2), (size_t)p2->len << 1);
                p1->len += p2->len;
            } else {
                memcpy(str8(p1) + p1->len, str8(p2), p2->len);
                p1->len += p2->len;
                str8(p1)[p1->len] = '\\0';
            }
            if (unlikely(p1->hash))
                p1->hash = 0;
            JS_FreeValue(ctx, sp[-1]);
            js_frame_finish_c(state);
            return 2;
        }
    } else if (JS_VALUE_GET_TAG(*pv) == JS_TAG_STRING_ROPE &&
               JS_VALUE_GET_TAG(sp[-1]) == JS_TAG_STRING) {
        JSStringRope *rope = JS_VALUE_GET_STRING_ROPE(*pv);
        JSString *part = JS_VALUE_GET_STRING(sp[-1]);
        uint32_t added = part->len;
        if (!added) {
            JS_FreeValue(ctx, sp[-1]);
            js_frame_finish_c(state);
            return 2;
        }
        if (JS_REF_COUNT(rope) == 1 && JS_VALUE_GET_TAG(rope->right) == JS_TAG_STRING &&
            added <= JS_STRING_ROPE_SHORT_LEN && rope->len <= JS_STRING_LEN_MAX - added &&
            JS_VALUE_GET_STRING(rope->right)->len <= JS_STRING_ROPE_SHORT_LEN) {
            JSString *tail = JS_VALUE_GET_STRING(rope->right);
            unsigned wide = part->is_wide_char;
            size_t length = (size_t)tail->len + added;
            if (JS_REF_COUNT(tail) == 1 && !tail->atom_type && tail->kind == JS_STRING_KIND_NORMAL &&
                tail->is_wide_char == wide &&
                js_malloc_usable_size(ctx, tail) >= sizeof(*tail) + (length << wide) + !wide) {
                if (wide) {
                    memcpy(str16(tail) + tail->len, str16(part), (size_t)added << 1);
                } else {
                    memcpy(str8(tail) + tail->len, str8(part), added);
                    str8(tail)[length] = 0;
                }
                tail->len = (uint32_t)length;
                if (unlikely(tail->hash))
                    tail->hash = 0;
                rope->len += added;
                rope->is_wide_char |= wide;
                JS_FreeValue(ctx, sp[-1]);
                js_frame_finish_c(state);
                return 2;
            }
            JSValue joined = JS_ConcatString2(ctx, js_dup(rope->right), sp[-1]);
            if (JS_IsException(joined)) {
                sp[-1] = JS_UNDEFINED;
                state->exception_pending = true;
                js_frame_finish_c(state);
                return JS_FrameInterpSlow(state);
            }
            set_value(ctx, &rope->right, joined);
            rope->len += added;
            rope->is_wide_char |= wide;
            js_frame_finish_c(state);
            return 2;
        }
    }
    result=JS_ConcatString(ctx,js_dup(*pv),sp[-1]);"""
    local = replace_one(local, old_concat, new_concat, "in-place add_loc string append")
    control = source_text(source, "string-concat-control.inc")
    control = control.replace(".qjsem$strings", ".bss.qjs_strings")
    control = control.replace(
        "unsigned char JS_FrameLocalRopeModeGet(void)",
        '__attribute__((section(".text.qjs_strings"), noipa))\nunsigned char JS_FrameLocalRopeModeGet(void)',
    )
    concat = source_text(source, "string-concat-rope.inc")
    concat = concat.replace(
        "JSValue JS_FrameSharedConcatRope(",
        '__attribute__((section(".text.qjs_strings"), noipa))\nJSValue JS_FrameSharedConcatRope(',
        1,
    )
    append = source_text(source, "string-local-rope-append.inc")
    append = append.replace("LOCAL_STRING_CODE", "LINUX_STRING_CODE")
    append = append.replace("FRAME_INLINE", "inline __attribute__((always_inline))")
    append = re.sub(r"\bJS_FrameInterpAddTrampoline\b", "JS_FrameLinuxStringConcat", append)
    append = re.sub(r"\bqjs_frame_core_js_new_string_rope\b", "js_new_string_rope", append)
    locale = (source / "src/common/string/locale-compare.inc").read_text()
    boundary = "/* Native compound interpreter entry."
    if locale.count(boundary) != 1:
        raise ValueError("Review ordinary locale kernel and compound-entry dependency")
    if layout["property_ic"]:
        locale = replace_one(
            locale,
            "#if defined(_WIN64) && (defined(__GNUC__) || defined(_MSC_VER)) && defined(QJS_PROPERTY_IC)",
            "#if defined(QJS_PROPERTY_IC)",
            "actual-type Linux compound owner",
        )
        locale = replace_one(
            locale,
            "#define COMPOUND_NOINLINE __attribute__((noipa))",
            "#define COMPOUND_NOINLINE LINUX_STRING_CODE",
            "isolated Linux compound helper",
        )
        for token, label in (
            (
                "sizeof(JSFunctionBytecode) == QJS_ABI_SIZE_JSFunctionBytecode",
                "compound measured bytecode size",
            ),
            (
                "offsetof(JSFunctionBytecode, property_ic) ==\n                       QJS_ABI_OFF_JSFunctionBytecode_property_ic",
                "compound measured IC field",
            ),
            (
                "sizeof(JSPropertyICSite) == QJS_ABI_SIZE_JSPropertyICSite",
                "compound measured IC site",
            ),
            ("sizeof(JSPropertyICWay) == QJS_ABI_SIZE_JSPropertyICWay", "compound measured IC way"),
        ):
            if " ".join(token.split()) not in " ".join(locale.split()):
                raise ValueError("Source-owned C worker boundary changed: " + label)
    else:
        locale = locale[: locale.index(boundary)]
    locale = locale.replace(".qjslfm", ".bss.qjs_strings")
    locale = locale.replace(
        "JSValue JS_FrameLocaleCompare(", "LINUX_STRING_CODE JSValue JS_FrameLocaleCompare(", 1
    )
    policy = source_text(source, "string-linux-boundaries.inc")
    policy = replace_one(
        policy,
        "    result = JS_FrameLinuxSharedConcatSelect(ctx, sp[-2], sp[-1]);",
        """    if (JS_VALUE_GET_TAG(sp[-2]) == JS_TAG_STRING && JS_VALUE_GET_STRING(sp[-2])->len == 0) {
        JSString *pe = JS_VALUE_GET_STRING(sp[-2]);
        uint32_t rtag = JS_VALUE_GET_TAG(sp[-1]);
        if (rtag == JS_TAG_INT) {
            result = qjs_int_to_string_fast(ctx, JS_VALUE_GET_INT(sp[-1]));
            if (likely(JS_REF_COUNT(pe) > 1))
                --JS_REF_COUNT(pe);
            else
                JS_FreeValue(ctx, sp[-2]);
        } else if (JS_TAG_IS_FLOAT64(rtag)) {
            result = js_dtoa2(ctx, JS_VALUE_GET_FLOAT64(sp[-1]), 10, 0, JS_DTOA_FORMAT_FREE);
            if (likely(JS_REF_COUNT(pe) > 1))
                --JS_REF_COUNT(pe);
            else
                JS_FreeValue(ctx, sp[-2]);
        } else {
            result = JS_FrameLinuxSharedConcatSelect(ctx, sp[-2], sp[-1]);
        }
    } else if (JS_VALUE_GET_TAG(sp[-1]) == JS_TAG_STRING && JS_VALUE_GET_STRING(sp[-1])->len == 0) {
        JSString *pe = JS_VALUE_GET_STRING(sp[-1]);
        uint32_t ltag = JS_VALUE_GET_TAG(sp[-2]);
        if (ltag == JS_TAG_INT) {
            result = qjs_int_to_string_fast(ctx, JS_VALUE_GET_INT(sp[-2]));
            if (likely(JS_REF_COUNT(pe) > 1))
                --JS_REF_COUNT(pe);
            else
                JS_FreeValue(ctx, sp[-1]);
        } else if (JS_TAG_IS_FLOAT64(ltag)) {
            result = js_dtoa2(ctx, JS_VALUE_GET_FLOAT64(sp[-2]), 10, 0, JS_DTOA_FORMAT_FREE);
            if (likely(JS_REF_COUNT(pe) > 1))
                --JS_REF_COUNT(pe);
            else
                JS_FreeValue(ctx, sp[-1]);
        } else {
            result = JS_FrameLinuxSharedConcatSelect(ctx, sp[-2], sp[-1]);
        }
    } else {
        result = JS_FrameLinuxSharedConcatSelect(ctx, sp[-2], sp[-1]);
    }""",
        "fast empty-string + int/float64 concat",
    )
    small_path = source_file(source, "string-small-char.c")
    small = small_path.read_text()
    small = replace_one(
        small,
        '#include "src/common/call/interpreter-retained-context.inc"',
        "",
        "actual-type small character owner",
    )
    small = small.replace("FRAME_INLINE", "inline __attribute__((always_inline))")
    small = small.replace("FRAME_CODE", "LINUX_STRING_CODE").replace(
        ".qjzzpm", ".bss.qjs_small_chars"
    )
    small = re.sub(r"\bqjs_frame_core_js_new_string_char\b", "js_new_string_char", small)
    small = re.sub(r"\bqjs_frame_core___JS_NewAtom\b", "__JS_NewAtom", small)
    functions = {m[2]: m[0] for m in adapter.FUNCTION.finditer(core)}
    original_char = functions["js_new_string_char"]
    marker = "/* LINUX_OWNED_ORIGINAL_CHAR_CONSTRUCTOR */"
    core = replace_one(
        core, original_char, marker, "retain consuming original character constructor"
    )
    character_routes = len(re.findall(r"\bjs_new_string_char\(", core))
    if character_routes < 7:
        raise ValueError("Review every original single-character call route")
    core = re.sub(r"\bjs_new_string_char\b", "JS_FrameSmallCharNew", core)
    core = replace_one(
        core,
        marker,
        "JSValue JS_FrameSmallCharNew(JSContext *, uint16_t);\n" + original_char,
        "original constructor and cached-call declaration",
    )
    free_runtime = functions["JS_FreeRuntime"]
    cleanup = replace_one(
        free_runtime,
        "JS_RunGC(rt);",
        "JS_FrameSmallCharCleanupGC(rt);",
        "exact shutdown cache ownership boundary",
    )
    core = replace_one(
        core,
        free_runtime,
        "void JS_FrameSmallCharCleanupGC(JSRuntime *);\n" + cleanup,
        "runtime shutdown cache cleanup owner",
    )
    index_path = source_file(source, "string-index.c")
    index = index_path.read_text()
    boundary = "#include <stdatomic.h>"
    if index.count(boundary) != 1:
        raise ValueError("Review shared string data accessors and index kernel")
    index = index[index.index(boundary) :]
    index = index.replace("FRAME_CODE", "LINUX_STRING_CODE").replace(
        ".qjzzpm", ".bss.qjs_string_index"
    )
    index = re.sub(r"\bJS_FrameSlowDirectSelect\b", "JS_FrameInterpSlow", index)
    forward = """
int JS_FrameLocalRopeAppendStep(JSFrameRegisterState *);
int JS_FrameLinuxStringConcat(JSFrameRegisterState *);
"""
    text = (
        control
        + "\n"
        + concat
        + "\n"
        + forward
        + "\n"
        + policy
        + "\n"
        + local
        + "\n"
        + append
        + "\n"
        + locale
        + "\n"
        + small
        + "\n"
        + index
    )
    path = output / "quickjs-linux-strings.h"
    path.write_text(text)
    old = 'JS_CFUNC_DEF("localeCompare", 1, js_string_localeCompare )'
    if core.count(old) != 1:
        raise ValueError("Review exact localeCompare method route")
    core = replace_one(
        core,
        old,
        old.replace("js_string_localeCompare", "JS_FrameLocaleCompare"),
        "localeCompare method",
    )
    table = "static const JSCFunctionListEntry js_string_proto_funcs[] = {"
    core = replace_one(
        core,
        table,
        "JSValue JS_FrameLocaleCompare(JSContext *, JSValueConst, int, JSValueConst *);\n" + table,
        "locale method prototype",
    )
    record = dict(
        status="generated-shared-string-kernels-not-qualified",
        generated_sha256=hashlib.sha256(text.encode()).hexdigest(),
        entries=[
            "JS_FrameSharedConcatRope",
            "JS_FrameLocalRopeModeGet",
            "JS_FrameLinuxSharedConcatSelect",
            "JS_FrameLinuxStringConcat",
            "JS_FrameLinuxStringAdd",
            "JS_FrameAddLocalString",
            "JS_FrameLocalRopeAppendStep",
            "JS_FrameLocaleCompare",
            "JS_FrameSmallCharNew",
            "JS_FrameSmallCharCleanupGC",
            "JS_FrameStringIndexStep",
            "JS_FrameLinuxStringSlow",
        ]
        + (["JS_FrameLocaleCompareCompound"] if layout["property_ic"] else []),
        equality=dict(
            route="existing common js_eq_slow body",
            body_sha256=hashlib.sha256(equality.encode()).hexdigest(),
        ),
        small_char=dict(
            source_sha256=hashlib.sha256(small_path.read_bytes()).hexdigest(),
            original_call_routes=character_routes,
            cleanup_routes=1,
            owner_slots=16,
            characters_per_slot=256,
        ),
        string_index=dict(
            source_sha256=hashlib.sha256(index_path.read_bytes()).hexdigest(),
            opcodes=["get_array_el", "get_array_el2"],
            fallback="original typed C step",
        ),
        method_routes=[
            dict(method="String.prototype.localeCompare", target="JS_FrameLocaleCompare")
        ],
        private_types="actual core/frame types;no private compiler clones or guessed runtime bytes",
        compound=dict(
            enabled=bool(layout["property_ic"]),
            source_sha256=hashlib.sha256(
                (source / "src/common/string/locale-compare.inc").read_bytes()
            ).hexdigest(),
            ownership="Same actual core/method owner;nonobserving cold proof and live PIC/hash/builtin/string proof",
        ),
        remaining_dependencies="Other string/call/constructor/publication supplements remain separate groups",
    )
    (output / "STRING-WORKERS.json").write_text(json.dumps(record, indent=2) + "\n")
    return core + '\n#include "quickjs-linux-strings.h"\n', record
