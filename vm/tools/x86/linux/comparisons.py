"""Complete accepted GNU comparison kernels,with real SysV C boundaries."""

import sys as _x86_sys
from pathlib import Path as _X86Path

if str(_X86Path(__file__).resolve().parents[2]) not in _x86_sys.path:
    _x86_sys.path.insert(0, str(_X86Path(__file__).resolve().parents[2]))
from x86.common.paths_x86 import source_file
import hashlib
import json
import re
from arguments import asm_body
from c_workers import replace_one

OWNERS = (
    "asm/x86/win64/mingw64/mingw-loose.S",
    "asm/x86/win64/mingw64/mingw-strict.S",
    "asm/x86/win64/common/strict_body.inc",
    "asm/x86/win64/common/strict_reference.inc",
    "asm/x86/win64/common/strict_identity.inc",
    "src/common/value/loose_control.inc",
    "src/common/call/reference-config.inc",
    "tools/x86/win64/coff/retained_routes.py",
)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def contract(source, layout):
    data = json.loads((source / "src/x86/linux/abi/comparisons.json").read_text())
    for name, digest in data["owners"].items():
        if sha(source_file(source, name)) != digest:
            raise ValueError("Review comparison semantic owner: " + name)
    if sha(source_file(source, "quickjs.c")) != data["pinned_core_sha256"]:
        raise ValueError("Review pinned comparison core before native admission")
    if layout["reference_count_model"] != "inline-header":
        raise ValueError("Review comparison reference profile")
    for name, position in data["string_bits"].items():
        if layout["bits"][name] != position:
            raise ValueError("Review comparison string representation: " + name)
    return data


def expanded(source, owner):
    text = (source / owner).read_text()
    text = text.replace('.include "strict_body.inc"', (source / OWNERS[2]).read_text())
    reference = (source / OWNERS[3]).read_text()
    a = reference.index(".macro FRAME_STRICT_REFERENCE prefix")
    a = reference.index("\n", a) + 1
    b = reference.index(".endm", a)
    macro = reference[a:b]
    return re.sub(
        r"(?m)^\s*FRAME_STRICT_REFERENCE (\w+)\s*$",
        lambda m: macro.replace("\\prefix\\()", m[1]),
        text,
    )


def rows(source, owner, name, layout):
    return asm_body(
        source,
        owner,
        name,
        layout,
        extra_values={"QJS_ABI_CONST_JS_TAG_OBJECT": -1},
        expanded=expanded(source, owner),
    )


def stats_bank(body, delta):
    pattern = re.compile(r"\[rip\+(JS_Frame(?:Loose|Strict)EqStats)(?:\+(\d+))?\]")
    return [
        pattern.sub(lambda m: "[rip+" + m[1] + "+" + str(int(m[2] or 0) + delta) + "]", r)
        for r in body
    ]


def source_kernel(source, layout):
    names = [
        "JS_FrameLooseEqEq",
        "JS_FrameLooseEqNeq",
        "JS_FrameLooseEqCommon",
        "JS_FrameStrictEqClean",
    ]
    result = []
    for name in names:
        owner = OWNERS[1] if name.endswith("Clean") else OWNERS[0]
        clean = rows(source, owner, name, layout)
        other = "JS_FrameStrictEqDirty" if name.endswith("Clean") else name + "Dirty"
        dirty = stats_bank(rows(source, owner, other, layout), -64)
        dirty = [
            r.replace("JS_FrameStrictEqDirty", "JS_FrameStrictEqClean")
            .replace("JS_FrameStrictEqOldDirty", "JS_FrameStrictEqOldClean")
            .replace(".Ldirty_loose_", ".Lloose_")
            .replace("JS_FrameLooseEqEqDirty", "JS_FrameLooseEqEq")
            .replace("JS_FrameLooseEqNeqDirty", "JS_FrameLooseEqNeq")
            .replace("JS_FrameLooseEqCommonDirty", "JS_FrameLooseEqCommon")
            .replace("JS_FrameLooseEqOldEqDirty", "JS_FrameLooseEqOldEq")
            .replace("JS_FrameLooseEqOldNeqDirty", "JS_FrameLooseEqOldNeq")
            for r in dirty
        ]
        if dirty != clean:
            raise ValueError("Review complete Clean/Dirty comparison equivalence: " + name)
        aliases = {
            "JS_FrameLooseEqOldEq": "interp_op_slow_eq",
            "JS_FrameLooseEqOldNeq": "interp_op_slow_neq",
            "JS_FrameStrictEqOldCleanEq": "interp_op_slow_strict_eq",
            "JS_FrameStrictEqOldCleanNeq": "interp_op_slow_strict_neq",
        }
        clean = [r.replace(".Lloose_", "linux_cmp_loose_") for r in clean]
        for old, new in aliases.items():
            clean = [r.replace(old, new) for r in clean]
        body = []
        for r in clean:
            if r == "call JS_FrameLooseEqConfigure":
                body += ["mov rcx, rbx", "call JS_LinuxLooseEqInit"]
            else:
                body.append(r)
        if name != "JS_FrameLooseEqCommon":
            mask = 2 | (4 if name.endswith("Clean") else 8)
            off = (
                [
                    "test ecx, ecx",
                    "jnz " + name + "_off_neq",
                    "jmp interp_op_slow_strict_eq",
                    name + "_off_neq:",
                    "jmp interp_op_slow_strict_neq",
                ]
                if name.endswith("Clean")
                else ["jmp interp_op_slow_" + ("eq" if name.endswith("Eq") else "neq")]
            )
            body = [
                "movzx r10d, BYTE PTR [rip+JS_LinuxComparisonControl]",
                "test r10d, r10d",
                "jz " + name + "_init",
                "test r10d, " + str(mask),
                "jnz " + name + "_off",
                *body,
                name + "_init:",
                "mov DWORD PTR [rsp+32], ecx",
                "mov rcx, rbx",
                "call JS_LinuxComparisonInit",
                "mov ecx, DWORD PTR [rsp+32]",
                "jmp " + name,
                name + "_off:",
                *off,
            ]
        result.append((name, body))
    return result


def append(source, output, stream, blocks, layout):
    data = contract(source, layout)
    added = source_kernel(source, layout)
    eq = next(r for n, r in blocks if n == "JS_FrameInterpPrimitiveEq")
    original = hashlib.sha256(json.dumps([stream["code"], eq]).encode()).hexdigest()
    numeric = "interp_number_compare_eq:" in eq
    routes = {}
    for op in ("eq", "neq"):
        # The optional numeric tier contributes two JNE misses. Without it,
        # the original integer opcode contributes one JNZ tag miss instead.
        condition = "jne" if numeric else "jnz"
        before = condition + " interp_op_slow_" + op
        after = condition + " JS_FrameLooseEq" + op.capitalize()
        count = sum(r.count(before) for r in (stream["code"], eq))
        if count != (2 if numeric else 1):
            raise ValueError("Review original loose guard edges: " + op + " " + str(count))
        for body in (stream["code"], eq):
            body[:] = [after if row == before else row for row in body]
        routes[op] = count
    label = "interp_primitive_eq_original_fallback:" if numeric else "interp_primitive_eq_fallback:"
    a = eq.index(label)
    old = ["test ecx, ecx", "jnz interp_op_slow_strict_neq", "jmp interp_op_slow_strict_eq"]
    if eq[a + 1 : a + 4] != old:
        raise ValueError("Review original strict fallback selector")
    eq[a + 1 : a + 4] = ["jmp JS_FrameStrictEqClean"]
    record = dict(
        status="generated-not-qualified",
        owners=data["owners"],
        functions=[n for n, _ in added],
        dirty_stats_banks={"JS_FrameLooseEqStats": 64, "JS_FrameStrictEqStats": 64},
        helpers=["JS_LinuxComparisonInit", "JS_LinuxLooseEqInit"],
        globals=[
            "JS_LinuxComparisonControl",
            "JS_FrameLooseEqMode",
            "JS_FrameLooseEqStats",
            "JS_FrameStrictEqMode",
            "JS_FrameStrictEqStats",
            "JS_FrameReferenceMode",
            "JS_FrameLargeGlobalMode",
        ],
        sysv_leaf="JS_LinuxStrictIdentityLeaf",
        numeric_compare=numeric,
        routes=routes,
        original_assembly_rows_sha256=original,
        derived_dirty="Exact source Dirty rows equal normalized Clean plus64-byte statistics bank",
        frame_growth=0,
        state_growth=0,
        new_strong_roots=0,
    )
    (output / "COMPARISONS-VM.json").write_text(json.dumps(record, indent=2) + "\n")
    return added, record


def render_native(source, layout):
    leaf = "JS_LinuxStrictIdentityLeaf"
    body = rows(source, OWNERS[4], "JS_FrameStrictIdentitySlow", layout)
    body = [
        re.sub(r"\brdx\b", "rsi", r)
        .replace("r8b", "dl")
        .replace("JS_FrameStrictIdentitySlow", leaf)
        .replace("qjs_frame_core_js_strict_eq_slow", "JS_LinuxStrictIdentityFallback")
        for r in body
    ]
    lines = [
        '.section .text.qjs_linux_comparison_leaf,"ax",@progbits',
        ".p2align 4",
        ".globl " + leaf,
        ".hidden " + leaf,
        ".type " + leaf + ",@function",
        leaf + ":",
        ".cfi_startproc",
        "endbr64",
        *body,
        ".cfi_endproc",
        ".size " + leaf + ",.-" + leaf,
        ".hidden JS_LinuxStrictIdentityFallback",
    ]
    for n, size, value in [
        ("JS_FrameLooseEqStats", 128, 0),
        ("JS_FrameStrictEqStats", 128, 0),
        ("JS_FrameReferenceMode", 4, 0),
        ("JS_FrameLargeGlobalMode", 4, 0),
        ("JS_FrameStrictEqMode", 4, 3),
    ]:
        section = (
            ".rodata.qjs_linux_comparison"
            if n == "JS_FrameStrictEqMode"
            else ".data.qjs_linux_comparison"
        )
        lines += [
            ".section "
            + section
            + (',"a",@progbits' if n == "JS_FrameStrictEqMode" else ',"aw",@progbits'),
            ".p2align " + ("3" if size == 128 else "2"),
            ".globl " + n,
            ".hidden " + n,
            ".type " + n + ",@object",
            n + ":",
            ".zero " + str(size) if size == 128 else ".long " + str(value),
            ".size " + n + ",.-" + n,
        ]
    return lines


def generate(source, output, core, layout):
    data = contract(source, layout)
    declaration = """
__attribute__((visibility("hidden"))) int JS_LinuxStrictIdentitySlow(JSContext *,JSValue *,bool);
"""
    core = replace_one(
        core,
        '#include "quickjs.h"',
        '#include "quickjs.h"\n' + declaration,
        "actual public strict helper declaration",
    )
    a = core.index("static no_inline int js_strict_eq_slow(")
    b = core.index("\n}", a) + 2
    retained = core[a:b]
    if hashlib.sha256(retained.encode()).hexdigest() != data["retained_strict_slow_sha256"]:
        raise ValueError("Review actual strict C fallback ownership/signature")
    core = core[:a] + "/* LINUX_ORIGINAL_STRICT_EQ_BODY */" + core[b:]
    before = core.count("js_strict_eq_slow(")
    if before != 2:
        raise ValueError("Review original strict core callers: " + str(before))
    core = core.replace("js_strict_eq_slow(", "JS_LinuxStrictIdentitySlow(").replace(
        "/* LINUX_ORIGINAL_STRICT_EQ_BODY */", retained
    )
    text = '#include "src/common/linux/interpreter-comparisons.inc"\n'
    text += "FRAME_CODE\n" + (source / "src/common/value/loose_control.inc").read_text() + "\n"
    text += """
FRAME_CODE int JS_LinuxLooseEqInit(JSFrameRegisterState *state)
{
    (void)state;JS_FrameLooseEqConfigure();return 1;
}
#undef FRAME_CODE
"""
    path = output / "quickjs-linux-comparisons.h"
    path.write_text(text)
    core += '\n#include "quickjs-linux-comparisons.h"\n'
    record = dict(
        status="generated-not-qualified",
        owners=data["owners"],
        source_files={
            n: sha(source_file(source, n))
            for n in (
                "tools/x86/linux/comparisons.py",
                "src/common/linux/interpreter-comparisons.inc",
            )
        },
        generated_sha256=sha(path),
        core_callers=before,
        retained_original_sha256=hashlib.sha256(retained.encode()).hexdigest(),
        entries=[
            "JS_LinuxComparisonInit",
            "JS_LinuxLooseEqInit",
            "JS_LinuxStrictIdentitySlow",
            "JS_LinuxStrictIdentityFallback",
            "JS_FrameLooseEqConfigure",
        ],
        pure_helpers=["JS_LinuxComparisonInit", "JS_LinuxLooseEqInit"],
        leaf="int(ctx=RDI,sp=RSI,is_neq=DL),no frame;complete original C fallback has same actual signature",
        frame_growth=0,
        state_growth=0,
        new_strong_roots=0,
    )
    (output / "COMPARISONS.json").write_text(json.dumps(record, indent=2) + "\n")
    return core


def finish_slow(output):
    path = output / "quickjs-interpreter-slow.h"
    text = path.read_text()
    before = sha(path)
    if text.count("js_strict_eq_slow(") != 2:
        raise ValueError("Review typed strict opcode C callers")
    path.write_text(text.replace("js_strict_eq_slow(", "JS_LinuxStrictIdentitySlow("))
    for name, key in (
        ("ARGUMENTS.json", "slow_sha256"),
        ("CONSTRUCT.json", "base_slow_after_sha256"),
    ):
        receipt = output / name
        prior = json.loads(receipt.read_text())
        if prior[key] != before:
            raise ValueError("Review pre-comparison C-step producer chain: " + name)
        prior["before_comparison_" + key] = prior[key]
        prior[key] = sha(path)
        prior["post_comparison_transform"] = (
            "Exactly two actual-signature strict helper calls;all argument/constructor/cleanup code unchanged"
        )
        receipt.write_text(json.dumps(prior, indent=2) + "\n")
    receipt = output / "COMPARISONS.json"
    record = json.loads(receipt.read_text())
    record.update(slow_callers=2, slow_before_sha256=before, slow_sha256=sha(path))
    receipt.write_text(json.dumps(record, indent=2) + "\n")
