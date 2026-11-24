"""Complete GNU numeric/FD owners with actual AAPCS64 and FPCR bindings."""

import hashlib, json, re, shutil
from c_workers import replace_one
from numeric_c import generate as shared_numeric
from compiler_projection_c import generate as shared_projection


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


FD_FIELDS = (
    "vars",
    "var_count",
    "byte_code",
    "label_count",
    "label_slots",
    "home_object_var_idx",
    "this_active_func_var_idx",
    "new_target_var_idx",
    "this_var_idx",
    "arguments_var_idx",
    "arguments_arg_idx",
    "func_var_idx",
    "var_object_idx",
    "arg_var_object_idx",
)


def probe_types(actual, text, names, numeric, projection):
    if numeric:
        names += [
            ("SIZE_JSBigInt", "sizeof(JSBigInt)"),
            (
                "OFF_JSBigInt_header_ref_count",
                "(uint64_t)((int64_t)offsetof(JSMallocBlockHeader,ref_count)-(int64_t)offsetof(JSMallocBlockHeader,user_data))",
            ),
        ]
        names += [
            ("CONST_" + n, "(uint64_t)(int64_t)" + n)
            for n in (
                "JS_SHORT_BIG_INT_MIN",
                "JS_SHORT_BIG_INT_MAX",
                "JS_TAG_BIG_INT",
                "JS_TAG_SHORT_BIG_INT",
            )
        ]
    if projection:
        raw = actual.core.read_text()
        a = raw.index("typedef struct BlockEnv {")
        b = raw.index("} JSFunctionDef;", a) + len("} JSFunctionDef;")
        text += "\n" + raw[a:b] + "\n"
        names += [
            ("SIZE_JSFunctionDef", "sizeof(JSFunctionDef)"),
            ("SIZE_LabelSlot", "sizeof(LabelSlot)"),
            ("OFF_LabelSlot_pos2", "offsetof(LabelSlot,pos2)"),
        ]
        names += [
            ("OFF_JSFunctionDef_" + n, "offsetof(JSFunctionDef," + n + ")") for n in FD_FIELDS
        ]
    return text, names


def generate(source, output, core, layout, actual, numeric, projection, measured):
    path = source / "src/arm64/linux/abi/numeric-workers.json"
    contract = json.loads(path.read_text())
    for n, h in contract["source_owners"].items():
        if sha(source / n) != h:
            raise ValueError("Review complete numeric/compiler semantic owner: " + n)
    records = {}
    if numeric:
        stage = output / "numeric-source"
        stage.mkdir(exist_ok=True)
        loop = output / "interpreter-aarch64-loop.h"
        before = loop.read_text()
        (stage / "quickjs-linux-loop.h").write_text(before)
        (stage / "ADMISSION.json").write_text(
            json.dumps(dict(generated_loop_sha256=sha(loop))) + "\n"
        )
        core = shared_numeric(
            source, stage, core, dict(layout, reference_count_model="allocator-prefix")
        )
        text = (stage / "quickjs-linux-numeric.h").read_text()
        binding = "        QJS_CONTROL_SLOT_ADDR(flag, JS_FrameAddLocalDisable);"
        text = replace_one(
            text,
            binding,
            "        flag=JS_FrameAddLocalDisable;",
            "actual target C address expression",
        )
        text += '\n#include "interpreter-aarch64-values.h"\n'
        text += """
_Static_assert((int64_t)offsetof(JSMallocBlockHeader,ref_count)-(int64_t)offsetof(JSMallocBlockHeader,user_data)==ARM_OFF_JSBigInt_header_ref_count && offsetof(JSBigInt,tab)==ARM_OFF_JSBigInt_tab,"actual target BigInt reference header");
_Static_assert(JS_SHORT_BIG_INT_MIN==INT32_MIN && JS_SHORT_BIG_INT_MAX==INT32_MAX,"actual target short BigInt range");
_Static_assert(__builtin_types_compatible_p(__typeof__(&JS_FrameBigIntRelease),void (*)(JSContext*,JSValue)),"actual AAPCS64 value argument");
#ifdef QJS_AARCH64_VM_INSTRUMENT
__thread uint64_t qjs_aarch64_numeric_counters[12] __attribute__((visibility("hidden"),tls_model("local-exec")));
__attribute__((visibility("hidden"),noipa)) void qjs_aarch64_vm_numeric_counts(uint64_t out[12])
{memcpy(out,qjs_aarch64_numeric_counters,sizeof(qjs_aarch64_numeric_counters));}
#endif
"""
        # The complete source arithmetic remains unchanged;passive entry counts
        # do not force admission,hold values or exist in the Release image.
        sig = "FRAME_NULL_CODE int JS_FrameAddLocalBig(JSFrameRegisterState *state)\n{"
        # Shared numeric factory already spells FRAME_NULL_CODE explicitly.
        sig = '__attribute__((section(".text.qjs_linux_add_local"),noipa,visibility("hidden"))) int JS_FrameAddLocalBig(JSFrameRegisterState *state)\n{'
        text = replace_one(
            text,
            sig,
            sig
            + "\n#ifdef QJS_AARCH64_VM_INSTRUMENT\n    ++qjs_aarch64_numeric_counters[5];\n#endif",
            "actual C local-add entry observer",
        )
        text = (
            '#ifdef QJS_AARCH64_VM_INSTRUMENT\nextern __thread uint64_t qjs_aarch64_numeric_counters[12] __attribute__((visibility("hidden"),tls_model("local-exec")));\n#endif\n'
            + text
        )
        (output / "quickjs-linux-numeric.h").write_text(text)
        primitive = (stage / "quickjs-linux-bigint.h").read_text()
        for n, i in [("add", 6), ("mul", 7)]:
            sig = (
                "FRAME_PROPERTY_CODE int JS_FrameInterpPrimitive_"
                + n
                + "(JSFrameRegisterState *state)\n{"
            )
            primitive = replace_one(
                primitive,
                sig,
                sig
                + "\n#ifdef QJS_AARCH64_VM_INSTRUMENT\n    ++qjs_aarch64_numeric_counters["
                + str(i)
                + "];\n#endif",
                "actual C primitive entry " + n,
            )
        primitive = (
            '#ifdef QJS_AARCH64_VM_INSTRUMENT\nextern __thread uint64_t qjs_aarch64_numeric_counters[12] __attribute__((visibility("hidden"),tls_model("local-exec")));\n#endif\n'
            + primitive
        )
        (output / "quickjs-linux-bigint.h").write_text(primitive)
        loop.write_text((stage / "quickjs-linux-loop.h").read_text())
        decimal = (stage / "quickjs-linux-atod.c").read_text()
        decimal = replace_one(
            decimal,
            '#include "qjs-number-rounding.h"',
            '#include "src/arm64/common/number-rounding.h"',
            "target FPCR rounding binding",
        )
        decimal = replace_one(
            decimal,
            "!qjs_number_atod_nearest()",
            "!qjs_aarch64_atod_nearest()",
            "original nondefault-rounding fallback",
        )
        decimal = replace_one(
            decimal,
            "    if (pnext)\n",
            "#ifdef QJS_AARCH64_VM_INSTRUMENT\n    ++qjs_aarch64_numeric_counters[8];\n#endif\n    if (pnext)\n",
            "actual exact decimal success",
        )
        decimal = replace_one(
            decimal,
            "slow:\n",
            "slow:\n#ifdef QJS_AARCH64_VM_INSTRUMENT\n    ++qjs_aarch64_numeric_counters[9];\n#endif\n",
            "actual original decimal fallback",
        )
        decimal = (
            '#ifdef QJS_AARCH64_VM_INSTRUMENT\n#include <stdint.h>\nextern __thread uint64_t qjs_aarch64_numeric_counters[12] __attribute__((visibility("hidden"),tls_model("local-exec")));\n#endif\n'
            + decimal
        )
        (output / "quickjs-linux-atod.c").write_text(decimal)
        rec = json.loads((stage / "NUMERIC.json").read_text())
        rec.update(
            enabled=True,
            generated_sha256=sha(output / "quickjs-linux-numeric.h"),
            primitive_sha256=sha(output / "quickjs-linux-bigint.h"),
            decimal_sha256=sha(output / "quickjs-linux-atod.c"),
            loop_after_sha256=sha(loop),
            ABI="actual AAPCS64 void(ctx,JSValue),int(state),double C converter",
            rounding="actual glibc FPCR Rmode constants,no foreign SIMD intrinsic",
            frame_growth=0,
            state_growth=0,
        )
        records["numeric"] = rec
    else:
        for n in ("quickjs-linux-numeric.h", "quickjs-linux-bigint.h", "quickjs-linux-atod.c"):
            (output / n).write_text("/* Native numeric workers compiled OFF. */\n")
        records["numeric"] = dict(enabled=False, entries=[])
    if projection:
        core = shared_projection(source, output, core, actual.core.read_text(), layout)
        p = output / "quickjs-linux-compiler-private.h"
        t = p.read_text() + '\n#include "interpreter-aarch64-values.h"\n'
        for typ in ("JSFunctionDef", "LabelSlot"):
            t += (
                "_Static_assert(sizeof("
                + typ
                + ")==ARM_SIZE_"
                + typ
                + ',"actual target compiler type");\n'
            )
        for n in FD_FIELDS:
            t += (
                "_Static_assert(offsetof(JSFunctionDef,"
                + n
                + ")==ARM_OFF_JSFunctionDef_"
                + n
                + ',"actual target FD field");\n'
            )
        t += '_Static_assert(offsetof(LabelSlot,pos2)==ARM_OFF_LabelSlot_pos2,"actual label field");\n'
        p.write_text(t)
        p = output / "quickjs-linux-compiler-projection.c"
        t = p.read_text()
        sig = "    JSFunctionDef *fd=opaque;"
        t = replace_one(
            t,
            sig,
            sig
            + "\n#ifdef QJS_AARCH64_VM_INSTRUMENT\n    ++qjs_aarch64_numeric_counters[10];\n#endif",
            "actual original compiler projection entry",
        )
        t = replace_one(
            t,
            "    JS_CompilerBytecodePlan(&view);",
            "#ifdef QJS_AARCH64_VM_INSTRUMENT\n    ++qjs_aarch64_numeric_counters[11];\n#endif\n    JS_CompilerBytecodePlan(&view);",
            "actual bounded source planner call",
        )
        t = (
            '#ifdef QJS_AARCH64_VM_INSTRUMENT\n#include <stdint.h>\nextern __thread uint64_t qjs_aarch64_numeric_counters[12] __attribute__((visibility("hidden"),tls_model("local-exec")));\n#endif\n'
            + t
        )
        p.write_text(t)
        rec = json.loads((output / "COMPILER-PROJECTION.json").read_text())
        rec.update(
            enabled=True,
            generated_sha256=sha(p),
            private_sha256=sha(output / "quickjs-linux-compiler-private.h"),
            actual_target="AArch64 GCC;independent original typed FD projection;no runtime retained metadata",
        )
        records["projection"] = rec
    else:
        (output / "quickjs-linux-compiler-private.h").write_text(
            "/* Compiler projection compiled OFF. */\n"
        )
        (output / "quickjs-linux-compiler-projection.c").write_text(
            "/* Compiler projection compiled OFF. */\n"
        )
        records["projection"] = dict(enabled=False, entries=[])
    if projection and not numeric:
        core += """
#ifdef QJS_AARCH64_VM_INSTRUMENT
__thread uint64_t qjs_aarch64_numeric_counters[12] __attribute__((visibility("hidden"),tls_model("local-exec")));
__attribute__((visibility("hidden"),noipa)) void qjs_aarch64_vm_numeric_counts(uint64_t out[12])
{memcpy(out,qjs_aarch64_numeric_counters,sizeof(qjs_aarch64_numeric_counters));}
#endif
"""
    record = dict(
        status="generated-not-qualified",
        numeric=records["numeric"],
        projection=records["projection"],
        source_owners=contract["source_owners"],
        contract_sha256=sha(path),
        generator_sha256=sha(source / "tools/arm64/workers/numeric_workers.py"),
        frame_growth=0,
        state_growth=0,
        runtime_growth=0,
        physical_ARM_performance_qualified=False,
    )
    (output / "NUMERIC-WORKERS.json").write_text(json.dumps(record, indent=2) + "\n")
    return core, record
