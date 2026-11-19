"""Source-owned native admission supplements, with the shared 64KiB guard."""

import sys as _x86_sys
from pathlib import Path as _X86Path

if str(_X86Path(__file__).resolve().parents[2]) not in _x86_sys.path:
    _x86_sys.path.insert(0, str(_X86Path(__file__).resolve().parents[2]))
from x86.common.paths_x86 import source_file
import hashlib
import json
from pathlib import Path
from c_workers import module

_source_match = module(Path(__file__).resolve().parents[3], "c_source_match")


def one(text, old, new):
    return _source_match.replace_one(text, old, new)


def function(text, signature):
    return _source_match.extract_function(text, signature)


def generate(source, output, core, layout, *, construct=False):
    loop = (source / "src/common/call/quickjs-interpreter-loop.inc").read_text()
    from js_calls import policy as js_call_policy

    loop = js_call_policy(source, output, loop)
    from forwarding import policy as forwarding_policy

    loop = forwarding_policy(source, output, loop)
    from constructors import loop_policy, validator as constructor_validator

    if construct:
        loop = loop_policy(loop)
    signature = "static FRAME_CODE bool js_frame_validate(JSFunctionBytecode *b)"
    original = function(loop, signature)
    # Keep the inherited short validator, executor, tables and frame format.
    # New native-only cohorts use a derived validator and one real opcode.
    pattern = """        CASE(OP_regexp):
            {
                sp[-2] = js_regexp_constructor_internal(ctx, JS_UNDEFINED,
                                                        sp[-2], sp[-1]);
                sp--;
                if (JS_IsException(sp[-1]))
                    goto exception;
            }
            BREAK;"""
    if core.count(pattern) != 1 or source_file(source, "quickjs.c").read_text().count(pattern) != 1:
        raise ValueError("Review the actual original literal ownership contract")
    loop = one(
        loop,
        "static FRAME_INLINE JSFunctionBytecode *js_frame_target(",
        'static __attribute__((section(".text.qjs_frame_admission"), noipa)) bool js_frame_linux_admit(JSFunctionBytecode *b);\n\n'
        "static FRAME_INLINE JSFunctionBytecode *js_frame_target(",
    )
    loop = one(
        loop,
        "if (!FRAME_KIND(b) && !js_frame_validate(b))",
        "if (!FRAME_KIND(b) && !js_frame_linux_admit(b))",
    )
    (output / "quickjs-linux-loop.h").write_text(loop)

    def clone(name, large):
        text = one(
            original,
            signature,
            "static "
            + ("FRAME_LARGE_CODE" if large else "LINUX_ADMISSION_CODE")
            + " bool "
            + name
            + "(JSFunctionBytecode *b)",
        )
        text = one(
            text, "int pos, size, op, index, target;", "int pos, size, op, index; int64_t target;"
        )
        if text.count("target = pos + 1 +") != 3:
            raise ValueError("Review checked branch-target arithmetic")
        text = text.replace("target = pos + 1 +", "target = (int64_t)pos + 1 +")
        if large:
            text = one(
                text,
                "uint8_t boundaries[(4096 + 7) / 8]",
                "uint8_t boundaries[FRAME_LARGE_BITMAP_BYTES]",
            )
            text = one(text, "b->byte_code_len > 4096", "b->byte_code_len > FRAME_LARGE_CODE_MAX")
        anchor = "#undef FRAME_OP\n            break;\n"
        text = one(
            text,
            anchor,
            anchor
            + """        case OP_regexp:
            if (getenv("QJS_DISABLE_FRAME_REGEXP") != NULL"""
            + (
                ' ||\n                getenv("QJS_DISABLE_FRAME_LONG_REGEXP") != NULL'
                if large
                else ""
            )
            + """)
                return false;
            break;
        case OP_set_name:
            if (getenv("QJS_DISABLE_FRAME_SET_NAME") != NULL)
                return false;
            break;
""",
        )
        return constructor_validator(source, text) if construct else text

    declaration = (
        '#define LINUX_ADMISSION_CODE __attribute__((section(".text.qjs_frame_admission"), noipa))\n'
        '#define QJS_FRAME_LITERAL_CODE __attribute__((section(".text.qjs_frame_opcode"), noipa))\n'
        "#define FRAME_LARGE_CODE_DEFAULT " + str(int(layout["property_ic"])) + "\n"
    )
    supplement = declaration + '#include "src/common/call/large-code-policy.inc"\n\n'
    supplement += clone("JS_FrameLinuxShortValidate", False) + "\n\n"
    supplement += clone("JS_FrameLongValidate", True) + "\n\n"
    from null_proto import admission as null_admission

    supplement += null_admission(source, original) + "\n\n"
    supplement += """static LINUX_ADMISSION_CODE bool js_frame_linux_admit(JSFunctionBytecode *b)
{
    js_frame_linux_js_calls_init();
    if (js_frame_validate(b))
        return true;
    if (!js_frame_register_enabled(b->realm->rt) ||
        getenv("QJS_DISABLE_LINUX_ADMISSION") != NULL)
        return false;
    if (b->byte_code_len <= 4096) {
        if (JS_FrameLinuxShortValidate(b)) return true;
        return JS_LinuxValidateNativeNull(b);
    }
    return js_frame_large_select(b);
}

#include "src/common/regexp/interpreter-literal.inc"
#include "quickjs-linux-set-name.h"
#undef LINUX_ADMISSION_CODE
#undef QJS_FRAME_LITERAL_CODE
"""
    (output / "quickjs-linux-admission.h").write_text(supplement)
    record = dict(
        status="generated-checked-source-admission",
        maximum_code_bytes=65536,
        new_native_opcodes=["regexp", "set_name"],
        shared_large_policy="src/common/call/large-code-policy.inc",
        inherited_short_validator_sha256=hashlib.sha256(original.encode()).hexdigest(),
        generated_loop_sha256=hashlib.sha256(loop.encode()).hexdigest(),
        generated_supplement_sha256=hashlib.sha256(supplement.encode()).hexdigest(),
        default_large_enabled=bool(layout["property_ic"]),
        scope="Base-supported ordinary code plus native regexp; iterator/varargs/literal metadata supplements are separate port items",
    )
    (output / "ADMISSION.json").write_text(json.dumps(record, indent=2) + "\n")


def vm_block():
    # Same event/exception protocol as the existing slow step, with one typed
    # state-only C target. The register activation and its CFA stay alive.
    return [
        "mov QWORD PTR [rbx], rbp",
        "mov QWORD PTR [rbx+16], r12",
        "mov QWORD PTR [rbx+24], r13",
        "mov rcx, rbx",
        "call JS_FrameInterpRegExp",
        "test eax, eax",
        "jz interp_reload",
        "mov rbp, QWORD PTR [rbx]",
        "mov r12, QWORD PTR [rbx+16]",
        "mov r13, QWORD PTR [rbx+24]",
        "jmp interp_exit",
    ]
