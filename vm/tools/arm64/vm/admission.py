"""Complete source-derived ARM regexp and bounded long-code admission."""

import hashlib
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from arm64.paths_arm64 import source_file
from admission_c import function, one


def generate(source, output, core, loop, *, large_default, complete_calls=False, null_proto=False):
    signature = "static FRAME_CODE bool js_frame_validate(JSFunctionBytecode *b)"
    original = function(loop, signature)
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
        raise ValueError("Review original consumed regexp literal operands")
    prototype = 'static __attribute__((section(".text.qjs_arm_admission"),noipa)) bool js_frame_aarch64_admit(JSFunctionBytecode *);\n'
    loop = one(
        loop,
        "static FRAME_INLINE JSFunctionBytecode *js_frame_target(",
        prototype + "\nstatic FRAME_INLINE JSFunctionBytecode *js_frame_target(",
    )
    loop = one(
        loop,
        "if (!FRAME_KIND(b) && !js_frame_validate(b))",
        "if (!FRAME_KIND(b) && !js_frame_aarch64_admit(b))",
    )

    def clone(name, large):
        text = one(
            original,
            signature,
            "static "
            + ("FRAME_LARGE_CODE" if large else "AARCH64_ADMISSION_CODE")
            + " bool "
            + name
            + "(JSFunctionBytecode *b)",
        )
        text = one(
            text, "int pos, size, op, index, target;", "int pos, size, op, index; int64_t target;"
        )
        if text.count("target = pos + 1 +") != 3:
            raise ValueError("Review all checked branch target additions")
        text = text.replace("target = pos + 1 +", "target = (int64_t)pos + 1 +")
        if large:
            text = one(
                text,
                "uint8_t boundaries[(4096 + 7) / 8]",
                "uint8_t boundaries[FRAME_LARGE_BITMAP_BYTES]",
            )
            text = one(text, "b->byte_code_len > 4096", "b->byte_code_len > FRAME_LARGE_CODE_MAX")
        anchor = "#define FRAME_OP(id) case OP_##id:"
        extra = (
            """        case OP_regexp:
            if (getenv("QJS_DISABLE_FRAME_REGEXP") != NULL"""
            + (
                ' ||\n                getenv("QJS_DISABLE_FRAME_LONG_REGEXP") != NULL'
                if large
                else ""
            )
            + """)
                return false;
            break;
"""
        )
        text = one(text, anchor, extra + anchor)
        if complete_calls:
            from constructors_c import validator

            text = validator(source, text)
        return text

    text = (
        """/* Source-owned native regexp/long admission over actual ARM C types. */
#define AARCH64_ADMISSION_CODE __attribute__((section(".text.qjs_arm_admission"),noipa))
#define QJS_FRAME_LITERAL_CODE __attribute__((section(".text.qjs_frame_regexp"),noipa))
#define FRAME_LARGE_CODE_DEFAULT """
        + str(int(large_default))
        + """
#include "src/common/call/large-code-policy.inc"
"""
    )
    if null_proto:
        from arm64.workers.null_proto import classifier

        text += classifier(source, output, original) + "\n"
    text += (
        clone("JS_FrameAArch64ShortValidate", False)
        + "\n"
        + clone("JS_FrameLongValidate", True)
        + "\n"
    )
    text += """static AARCH64_ADMISSION_CODE bool js_frame_aarch64_admit(JSFunctionBytecode *b)
{
    if(js_frame_validate(b))return true;
    if(!js_frame_register_enabled(b->realm->rt) || getenv("QJS_DISABLE_LINUX_ADMISSION"))return false;
    if(b->byte_code_len<=4096)return JS_FrameAArch64ShortValidate(b);
    return js_frame_large_select(b);
}
#include "interpreter-aarch64-regexp.h"
#undef AARCH64_ADMISSION_CODE
#undef QJS_FRAME_LITERAL_CODE
#undef FRAME_LARGE_CODE_DEFAULT
#undef FRAME_LARGE_CODE
"""
    if null_proto:
        text = one(
            text,
            "    if(b->byte_code_len<=4096)return JS_FrameAArch64ShortValidate(b);",
            "    if(JS_LinuxValidateNativeNull(b))return true;\n    if(b->byte_code_len<=4096)return JS_FrameAArch64ShortValidate(b);",
        )
    (output / "interpreter-aarch64-admission.h").write_text(text)
    literal = (source / "src/common/regexp/interpreter-literal.inc").read_text()
    marker = "QJS_FRAME_LITERAL_CODE int JS_FrameInterpRegExp(JSFrameRegisterState *state)\n{"
    literal = one(
        literal,
        marker,
        marker
        + """
#ifdef QJS_AARCH64_VM_INSTRUMENT
    qjs_aarch64_vm_regexp_started();
#endif""",
    )
    (output / "interpreter-aarch64-regexp.h").write_text(literal)
    record = dict(
        status="generated-not-qualified",
        native_opcode="regexp",
        maximum_code_bytes=65536,
        bitmap_bytes=8192,
        stack_guard=12288,
        default_large=bool(large_default),
        original_validator_sha256=hashlib.sha256(original.encode()).hexdigest(),
        generated_sha256=hashlib.sha256(text.encode()).hexdigest(),
        literal_sha256=hashlib.sha256(literal.encode()).hexdigest(),
        ownership="Exact original consumed-operand constructor,cleared slots,PC/SP publication,quota and exception continuation",
        register_abi="Typed state-only AAPCS64 call;actual common state/frame types",
        retained="Original short validator,THIS_FUNC,set_name,argument/capture bounds and metadata",
    )
    return loop, record
