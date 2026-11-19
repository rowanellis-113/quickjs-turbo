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
from native_abi import current as current_abi
from abi_layout import load as load_layout
import shutil, time

"""Synchronous iteration coverage in an appended Win64 semantic island.

Keep the original core and original frame executor compiled unchanged. Extract
the core's opcode bodies and exception-marker loop; use a separate slow step
only while an extended frame is in the activation. No weak iterator cache.
"""
import argparse
import hashlib
import importlib.util
import json
import re
import struct
import subprocess
from pathlib import Path

OPS = (
    "for_of_start",
    "for_of_next",
    "iterator_close",
    "catch",
    "gosub",
    "ret",
    "nip_catch",
    "check_object",
)
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()


def module(source, name):
    spec = importlib.util.spec_from_file_location(
        "iterator_" + name.replace("-", "_"), _frame_tool_path(name + ".py")
    )
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def bodies(source):
    core = _frame_source_file(source, "quickjs.c").read_text(encoding="utf-8")
    answer = {}
    for name in OPS:
        start = core.index("        CASE(OP_" + name + "):")
        end = core.index("\n        CASE(", start + 1)
        answer[name] = core[start:end]
    start = core.index(
        "    if (!JS_IsUncatchableError(rt->current_exception)) {",
        core.index("\n exception:", core.index("        CASE(OP_for_of_start):")),
    )
    end = core.index("\n    ret_val = JS_EXCEPTION;", start)
    loop = core[start:end]
    assert loop.count("goto restart;") == 1
    # The native VM resumes at the recorded bytecode PC, rather than executing
    # a second opcode in C. A caught exception also consumes pending call
    # operands; leaving the old pending ledger would double-free on a new call.
    loop = loop.replace("goto restart;", "frame->pending = 0;\n                    goto dispatch;")
    return answer, loop


def native_instanceof_enabled(build):
    rows = json.loads(_frame_build_file(build, "compile_commands.json").read_text())
    commands = [row["command"] for row in rows if Path(row["file"]).name == "quickjs-interpreter.c"]
    assert len(commands) == 1
    return bool(
        re.search(r"(?:^|\s)(?:-D|/D)JS_IsInstanceOf=JS_FrameInstanceOf(?=\s|$)", commands[0])
    )


def generate(source, build, out, native_instanceof=False):
    original = _frame_source_text(source, "quickjs-interpreter-loop.h")
    opcode_bodies, exception_loop = bodies(source)
    extra_cases = "".join("        case OP_" + name + ":\n" for name in OPS)
    validator = original[
        : original.index(
            '\n#ifdef QJS_INTERP_FRAME_REGISTER_ABI\n#include "quickjs-interpreter-slow.h"'
        )
    ]
    # Byte22 is the remaining original padding between the two flag bytes and
    # byte_code_buf. Byte18..21 and byte23 retain their existing contracts.
    validator = replace_one(
        validator,
        "static FRAME_CODE bool js_frame_validate(",
        "FRAME_CODE bool JS_FrameIteratorValidate(",
    )
    validator = replace_one(validator, "js_frame_validate(b)", "JS_FrameIteratorValidate(b)")
    validator = replace_one(
        validator, "!JS_FrameIteratorValidate(b)", "!JS_FrameIteratorValidateSelect(b)"
    )
    # FRAME_CODE is defined by the extracted prefix, so put its declaration
    # immediately before the first function that needs the selector.
    validator = replace_one(
        validator,
        "static FRAME_INLINE JSFunctionBytecode *js_frame_target(",
        "FRAME_CODE bool JS_FrameIteratorValidateSelect(JSFunctionBytecode *b);\n\n"
        "static FRAME_INLINE JSFunctionBytecode *js_frame_target(",
    )
    validator = replace_one(
        validator,
        "    bool captured_args = false;",
        "    bool captured_args = false;\n    bool extended = false;\n    FRAME_ITERATOR_KIND(b) = 0;",
    )
    validator = replace_one(
        validator,
        "        default:\n            return false;\n        }",
        extra_cases
        + "            extended = true;\n            break;\n        default:\n            return false;\n        }",
    )
    goto_cases = re.compile(r"(?m)^([ \t]*)case OP_goto:\s*case OP_if_true:\s*case OP_if_false:")
    validator, count = goto_cases.subn(
        lambda m: m[1]
        + "case OP_catch: case OP_gosub:\n"
        + m[1]
        + "case OP_goto: case OP_if_true: case OP_if_false:",
        validator,
    )
    if count != 1:
        raise ValueError("Iterator validator branch anchor missing or ambiguous")
    validator = replace_one(
        validator,
        "    FRAME_KIND(b) = (captured_args",
        '    if (extended && (getenv("QJS_DISABLE_FRAME_ITERATOR") != NULL ||\n'
        "                     !js_frame_register_enabled(b->realm->rt))) return false;\n"
        "    FRAME_ITERATOR_KIND(b) = extended;\n    FRAME_KIND(b) = (captured_args",
    )
    # The common contract may already be included by the private core header.
    # Iterator/varargs metadata belongs to this TU, outside that header guard.
    marker = "#ifndef QJS_FRAME_BYTECODE_METADATA"
    at = validator.index(marker)
    validator = (
        validator[:at]
        + (
            "#define FRAME_ITERATOR_KIND(b) (((unsigned char *)(b))[offsetof(JSFunctionBytecode,byte_code_buf)-2])\n"
            "_Static_assert(sizeof(JSGCObjectHeader) == QJS_ABI_SIZE_JSGCObjectHeader &&\n"
            "               offsetof(JSFunctionBytecode, byte_code_buf) == QJS_ABI_OFF_JSFunctionBytecode_byte_code_buf,\n"
            '               "iterator kind uses measured bytecode padding");\n'
        )
        + validator[at:]
    )
    # All generated functions/constants are new. The inherited TU never
    # includes this modified prefix and retains its original object bytes.
    validator = replace_one(validator, 'section(".qjsvm$z")', 'section(".qjsiter")')
    validator = replace_one(validator, 'section(".qjsvm$zw")', 'section(".qjsiter")')
    nop_case = re.compile(r"(?m)^[ \t]*CASE\(OP_nop\)\s*:")
    insertion = (
        "\n".join(opcode_bodies.values()).replace("        CASE(", "    CASE(")
        + "\n    CASE(OP_nop):"
    )
    expanded, count = nop_case.subn(lambda _: insertion, original)
    if count != 1:
        raise ValueError("Iterator dispatch insertion anchor missing or ambiguous")
    anchor = "    ret_val = JS_EXCEPTION;\nreturn_frame:"
    assert expanded.count(anchor) == 1
    expanded = expanded.replace(anchor, exception_loop + "\n" + anchor)
    dispatch = _frame_source_text(source, "quickjs-interpreter-dispatch.h")
    for name in OPS:
        assert dispatch.count("FRAME_TARGET(" + name + ", invalid)") == 1
        dispatch = dispatch.replace(
            "FRAME_TARGET(" + name + ", invalid)", "FRAME_TARGET(" + name + ", OP_" + name + ")"
        )
    (_frame_generated_file(build, "quickjs-interpreter-iterator-dispatch.h")).write_text(
        dispatch, encoding="utf-8"
    )
    slow_file = _frame_generated_file(build, "quickjs-interpreter-iterator-slow.h")
    module(source, "generate-slow").generate(source, slow_file, interpreter_text=expanded)
    slow = slow_file.read_text(encoding="utf-8").split("\nFRAME_OPCODE_CODE", 1)[0]
    slow = slow.replace("JS_FrameInterpSlow(", "JS_FrameIteratorSlow(")
    slow = slow.replace(
        '#include "src/common/call/quickjs-interpreter-dispatch.inc"',
        '#include "quickjs-interpreter-iterator-dispatch.h"',
    )
    slow_file.write_text(slow, encoding="utf-8")
    wrapper = """
extern int JS_FrameInterpSlow(JSFrameRegisterState *state);
extern bool JS_FrameValidateNativeNull(JSFunctionBytecode *b);
extern void JS_FrameCapturedReadonlyClassify(JSFunctionBytecode *b);
FRAME_CODE bool JS_FrameIteratorValidateSelect(JSFunctionBytecode *b)
{
    if (JS_FrameValidateNativeNull(b)) return true;
    if (!JS_FrameIteratorValidate(b)) return false;
    JS_FrameCapturedReadonlyClassify(b);
    return true;
}
FRAME_CODE int JS_FrameIteratorSlowSelect(JSFrameRegisterState *state)
{
    JSFrame *frame;
    for (frame = state->frame; frame; frame = js_frame_parent(frame))
        if (FRAME_ITERATOR_KIND(frame->bytecode))
            return JS_FrameIteratorSlow(state);
    return JS_FrameInterpSlow(state);
}
"""
    boundaries = []
    for name in OPS:
        body = opcode_bodies[name].split(":", 1)[1]
        body = body.replace("BREAK;", "goto iterator_done;")
        boundary = """
FRAME_CODE int JS_FrameIteratorOp_%s(JSFrameRegisterState *state)
{
    JSFrame *frame = state->frame;
    JSFunctionBytecode *b = frame->bytecode;
    JSStackFrame *sf = &frame->sf;
    JSContext *ctx = b->realm;
    JSValue *sp = state->sp, *stack_buf = sf->var_buf + b->var_count;
    uint8_t *pc = state->pc + 1;
    (void)stack_buf; (void)ctx;
    js_frame_begin_c(state);
    sf->cur_pc = pc;
    frame->saved_sp = sp;
%s
iterator_done:
    state->pc = pc;
    state->sp = sp;
    frame->saved_sp = sp;
    sf->cur_pc = pc;
    js_frame_finish_c(state);
    return 0;
exception:
    state->pc = pc;
    state->sp = sp;
    frame->saved_sp = sp;
    sf->cur_pc = pc;
    state->exception_pending = true;
    js_frame_finish_c(state);
    return JS_FrameIteratorSlow(state);
}
""" % (name, body)
        if "goto exception;" not in body:
            boundary = boundary[: boundary.index("\nexception:")] + "\n}\n"
        boundaries.append(boundary)
    backend = validator + slow + wrapper + "\n".join(boundaries)
    # Discover original helpers without changing the inherited private header.
    adapter = module(source, "object-adapter")
    core_path = _frame_build_file(build, "CMakeFiles/qjs-core.dir/quickjs.c.obj")
    raw = core_path.read_bytes()
    coff = adapter.Coff(raw)
    # This symbol now belongs to the frame wrapper. Its original core name was
    # renamed by the inherited adapter; discovery must not copy that wrapper.
    coff.symbols["JS_Call"] = dict(storage=2)
    discovery = backend + _frame_source_text(source, "quickjs-interpreter-ops.h")
    # Preserve the inherited frame TU's intrinsic selection even when a new
    # core caller makes the compiler emit its original out-of-line operator.
    # Its core provider was compiled without the frame-only replacement.
    if native_instanceof:
        adapter.HOT_LOCAL_HELPERS.add("js_operator_instanceof")
    header, exports, copies = adapter.generate(
        _frame_source_file(source, "quickjs.c").read_text(encoding="utf-8"), coff, discovery
    )
    if native_instanceof:
        assert "js_operator_instanceof" in copies and "js_operator_instanceof" not in exports
    names = {x["name"] for x in coff.all_symbols.values()}
    added = []
    for name in exports:
        if "qjs_frame_core_" + name not in names:
            coff.expose(name)
            added.append(name)
    finish_preserving_tail(coff, raw, core_path)
    (_frame_generated_file(build, "quickjs-iterator-private.h")).write_text(
        header, encoding="utf-8"
    )
    out.write_text(
        '#include "quickjs-iterator-private.h"\n'
        "#undef DIRECT_DISPATCH\n#define DIRECT_DISPATCH 0\n" + backend,
        encoding="utf-8",
    )
    (_frame_generated_file(build, "quickjs-interpreter-iterator-source.json")).write_text(
        json.dumps(
            dict(
                core_sha256=sha(_frame_source_file(source, "quickjs.c")),
                inherited_header_sha256=sha(
                    _frame_source_file(source, "quickjs-interpreter-loop.h")
                ),
                added_aliases=added,
                copied_helpers=copies,
                native_instanceof=dict(
                    inherited_compiler_definition=native_instanceof,
                    operator_copied="js_operator_instanceof" in copies,
                ),
                opcode_bodies_sha256={
                    n: hashlib.sha256(v.encode()).hexdigest() for n, v in opcode_bodies.items()
                },
                adapted_exception_loop_sha256=hashlib.sha256(exception_loop.encode()).hexdigest(),
                generated_sha256=sha(out),
                kind_offset=load_layout(source)["offsets"]["JSFunctionBytecode.byte_code_buf"] - 2,
                physical_frame_bytes=128,
            ),
            indent=2,
        )
        + "\n"
    )


def finish_preserving_tail(coff, raw, path):
    end = coff.string_offset + struct.unpack_from("<I", raw, coff.string_offset)[0]
    result = bytearray(coff.finish())
    shift = len(result) - len(raw)
    for rec in coff.section_records:
        for field in (20, 24, 28):
            at = rec["pos"] + field
            value = struct.unpack_from("<I", raw, at)[0]
            if value and value >= end:
                struct.pack_into("<I", result, at, value + shift)
    path.write_bytes(result)


def compile_extra(source, build, out):
    compiler = module(source, "atod")
    old_argv = compiler.win_argv
    compiler.win_argv = lambda command: [x for x in old_argv(command) if not x.startswith("-g")] + [
        "-g0"
    ]
    native_instanceof = native_instanceof_enabled(build)
    compiler.compile_extra(
        source,
        build,
        out,
        generator=lambda src, target: generate(
            src, build, target, native_instanceof=native_instanceof
        ),
        filename="quickjs-interpreter-iterator.c",
        late_name=".qjsiter",
    )


def append(gas, diagnostics, out):
    # The old VM has fixed 256-entry opcode storage. Redirect only the eight
    # previous invalid slots; derived Clean/Dirty tables copy these entries.
    abi_layout = current_abi()
    abi_fields = abi_layout["offsets"]
    source = Path(__file__).resolve().parents[4]
    # DEF definitions form the final bytecode table; def are temporary parser
    # opcodes and are excluded by the shared register generator.
    names = [
        m[1]
        for m in re.finditer(
            r"^DEF\(\s*(\w+)\s*,", _frame_source_file(source, "quickjs-opcode.h").read_text(), re.M
        )
    ]
    begin = gas.index("interp_table:") + 1
    replacements = []
    for name in OPS:
        at = begin + names.index(name)
        assert gas[at] == ".quad interp_slow", (name, gas[at])
        gas[at] = ".quad JS_FrameIteratorEntry_" + name
        replacements.append(dict(opcode=name, slot=names.index(name)))
    code = [".intel_syntax noprefix", '.section .qjsiter,"xr"']
    ranges = []
    for name in OPS:
        label = "JS_FrameIteratorEntry_" + name
        code += [
            ".p2align 4",
            ".globl " + label + ", " + label + "_end",
            ".def " + label + "; .scl 2; .type 32; .endef",
            label + ":",
        ]
        if not diagnostics:
            code += [
                "lea r10, [rip+JS_FramePublishDirtyTable]",
                "cmp rdi, r10",
                "jne " + label + "_published",
                "lea rdi, [rip+JS_FramePublishTable]",
            ]
        code += [
            "mov r10, QWORD PTR [rbx+56]",
            f"mov QWORD PTR [r10+{abi_fields['JSRuntime.current_stack_frame']}], rbp",
        ]
        if not diagnostics:
            code += [label + "_published:"]
        if diagnostics:
            code += ["inc QWORD PTR [rbx+144+" + str(names.index(name) * 8) + "]"]
        code += [
            "mov QWORD PTR [rbx], rbp",
            "mov QWORD PTR [rbx+16], r12",
            "mov QWORD PTR [rbx+24], r13",
            "mov rcx, rbx",
            "call JS_FrameIteratorOp_" + name,
            "test eax, eax",
            "jz JS_FrameNativeLifetimeResume",
            "mov rbp, QWORD PTR [rbx]",
            "mov r12, QWORD PTR [rbx+16]",
            "mov r13, QWORD PTR [rbx+24]",
            "jmp interp_exit",
            label + "_end:",
        ]
        ranges.append(label)
    resume = "JS_FrameIteratorHostResume"
    code += [
        ".p2align 4",
        ".globl " + resume + ", " + resume + "_end",
        resume + ":",
        "test eax, eax",
        "jnz interp_exit",
        "jmp JS_FrameNativeLifetimeResume",
        resume + "_end:",
        ".p2align 2",
        "JS_FrameIteratorEntry_unwind:",
        ".byte 33, 0, 0, 0",
        ".rva JS_FrameInterp, JS_FrameInterp_end, JS_FrameInterp_unwind",
        '.section .pdata$zzzzzzzzzzzzzziterator,"dr"',
        ".p2align 2",
    ]
    for label in ranges + [resume]:
        code += [".rva " + label + ", " + label + "_end, JS_FrameIteratorEntry_unwind"]
    (out / "quickjs-interpreter-iterator-win64.S").write_text(
        "\n".join(code) + "\n", encoding="utf-8"
    )
    # Host exceptions can now be caught inside this activation. Keep the old
    # return PC/shape, redirect the final near JMP to inspect the slow event.
    for stream, label in ((gas, "interp_host_exception"),):
        at = stream.index(label + ":")
        end = stream.index("jmp interp_exit", at)
        assert end - at in (5, 6, 7)
        stream[end] = "jmp " + resume
    publish = out / "quickjs-interpreter-publish-win64.S"
    if not diagnostics:
        text = publish.read_text(encoding="utf-8")
        needle = "dirty_interp_host_exception:\nmov rcx, rbx\ncall JS_FramePublishBefore_FrameInterpSlow\nmov rbp, QWORD PTR [rbx]\nmov r12, QWORD PTR [rbx+16]\nmov r13, QWORD PTR [rbx+24]\njmp interp_exit"
        assert text.count(needle) == 1
        text = text.replace(needle, needle.rsplit("\n", 1)[0] + "\njmp " + resume)
        publish.write_text(text, encoding="utf-8")
    (out / "quickjs-interpreter-iterator-asm.json").write_text(
        json.dumps(
            dict(
                opcode_slots=replacements,
                host_exception_resume=True,
                frame_bytes=128,
                no_old_instruction_size_change=True,
            ),
            indent=2,
        )
        + "\n"
    )
    module(source, "iterator-fast").append(out, diagnostics)


def route(
    path,
    source,
    objdump,
    targets=None,
    label="iterator",
    excluded_sections=(),
    caller=None,
    conditional=False,
):
    adapter = module(source, "object-adapter")
    raw = path.read_bytes()
    coff = adapter.Coff(raw)
    routes = []
    if caller:
        entry = coff.symbols[caller]
        end = min(
            x["value"]
            for x in coff.all_symbols.values()
            if x["section"] == entry["section"] and x["type"] == 32 and x["value"] > entry["value"]
        )

        def accepted(section, pc):
            return section == entry["section"] and entry["value"] <= pc < end
    else:

        def accepted(section, pc):
            return True

    targets = targets or {
        "JS_FrameValidateNativeNull": "JS_FrameIteratorValidateSelect",
        "JS_FrameInterpSlow": "JS_FrameIteratorSlowSelect",
    }
    external = {n: coff.external(t) for n, t in targets.items()}
    section_names = []
    for section in coff.sections:
        name = section["name"]
        if name.startswith("/"):
            start = int(name[1:])
            name = coff.strings[start : coff.strings.index(0, start)].decode()
        section_names.append(name)
    executable = [
        n
        for n, r in zip(section_names, coff.section_records)
        if r["flags"] & 0x20000000 and n not in excluded_sections
    ]
    listing = subprocess.check_output(
        [
            str(objdump),
            "-D",
            "-w",
            "-Mintel",
            *[a for n in dict.fromkeys(executable) for a in ("-j", n)],
            str(path),
        ],
        text=True,
    )
    # COFF contributions can share a name after island merging. objdump emits
    # them separately in object order; a name.index() would decode later text
    # against the first contribution's relocation offsets.
    occurrences = {}
    section_order = []
    for line in listing.splitlines():
        m = re.match(r"Disassembly of section (.+):", line)
        if not m:
            continue
        name = m[1]
        occurrence = occurrences.get(name, 0)
        matches = [i + 1 for i, n in enumerate(section_names) if n == name]
        assert occurrence < len(matches), (name, occurrence, matches)
        section_order.append(matches[occurrence])
        occurrences[name] = occurrence + 1
    decoded = {}
    current_section = None
    section_cursor = 0
    for line in listing.splitlines():
        m = re.match(r"Disassembly of section (.+):", line)
        if m:
            current_section = section_order[section_cursor]
            section_cursor += 1
            continue
        m = re.match(r"^\s*([0-9a-f]+):\s+((?:[0-9a-f]{2}\s+)+)\s*(.*?)\s*$", line)
        if not m or not current_section:
            continue
        pc, data = int(m[1], 16), bytes.fromhex(m[2])
        branch = (len(data) == 5 and data[0] in (0xE8, 0xE9)) or (
            conditional and len(data) == 6 and data[0] == 0x0F and 0x80 <= data[1] <= 0x8F
        )
        if branch and accepted(current_section, pc):
            decoded[current_section, pc + len(data) - 4] = data
    # External calls have existing relocation operands. Do not rename the
    # inherited Slow definition: the selector's ordinary path still uses it.
    relocated = set()
    for sn, rec in enumerate(coff.section_records, 1):
        if not rec["flags"] & 0x20000000 or section_names[sn - 1] in excluded_sections:
            continue
        assert rec["count"] < 65535
        for i in range(rec["count"]):
            at = rec["reloc"] + i * 10
            off, sym, kind = struct.unpack_from("<IIH", raw, at)
            target_symbol = coff.all_symbols[sym]
            name = target_symbol["name"]
            if kind != 4 or (sn, off) not in decoded:
                continue
            addend = struct.unpack_from("<i", raw, rec["raw"] + off)[0]
            if name not in targets:
                # MinGW commonly relocates a call to a section symbol plus a
                # function addend, including calls within .qjsvm$z itself.
                matches = [
                    n
                    for n in targets
                    if n in coff.symbols
                    and coff.symbols[n]["section"] == target_symbol["section"]
                    and coff.symbols[n]["value"] == target_symbol["value"] + addend
                ]
                if not matches:
                    continue
                assert len(matches) == 1
                name = matches[0]
            if name in targets:
                struct.pack_into("<I", coff.data, at + 4, external[name])
                coff.data[rec["raw"] + off : rec["raw"] + off + 4] = bytes(4)
                relocated.add((sn, off))
                routes.append(
                    dict(
                        section=sn,
                        offset=off,
                        target=targets[name],
                        old=name,
                        kind="existing-rel32",
                        old_symbol=target_symbol["name"],
                        old_addend=addend,
                    )
                )
    # GCC has already resolved same-section local calls. Decode instructions;
    # an E8/E9 inside an immediate or data is never a call operand.
    current_section = None
    section_cursor = 0
    for line in listing.splitlines():
        m = re.match(r"Disassembly of section (.+):", line)
        if m:
            current_section = section_order[section_cursor]
            section_cursor += 1
            continue
        m = re.match(r"^\s*([0-9a-f]+):\s+((?:[0-9a-f]{2}\s+)+)\s*(.*?)\s*$", line)
        if not m or not current_section:
            continue
        pc, data = int(m[1], 16), bytes.fromhex(m[2])
        branch = (len(data) == 5 and data[0] in (0xE8, 0xE9)) or (
            conditional and len(data) == 6 and data[0] == 0x0F and 0x80 <= data[1] <= 0x8F
        )
        if not branch or not accepted(current_section, pc):
            continue
        operand = pc + len(data) - 4
        if (current_section, operand) in relocated:
            continue
        destination = pc + len(data) + struct.unpack_from("<i", data, len(data) - 4)[0]
        for name in targets:
            symbol = coff.symbols.get(name)
            if symbol and symbol["section"] == current_section and symbol["value"] == destination:
                rec = coff.section_records[current_section - 1]
                coff.data[rec["raw"] + operand : rec["raw"] + operand + 4] = bytes(4)
                coff.extra_relocations.setdefault(current_section, []).append(
                    struct.pack("<IIH", operand, external[name], 4)
                )
                routes.append(
                    dict(
                        section=current_section,
                        offset=operand,
                        target=targets[name],
                        old=name,
                        kind="decoded-rel32",
                    )
                )
    if not routes:
        return
    # finish() appends decoded relocation arrays; move old post-string arrays
    # by just the symbol/string growth, rather than the complete new tail size.
    end = coff.string_offset + struct.unpack_from("<I", raw, coff.string_offset)[0]
    result = bytearray(coff.finish())
    shift = (
        len(coff.aliases) * coff.stride
        + len(coff.strings)
        - struct.unpack_from("<I", raw, coff.string_offset)[0]
    )
    for rec in coff.section_records:
        for field in (20, 24, 28):
            at = rec["pos"] + field
            value = struct.unpack_from("<I", raw, at)[0]
            if (
                value
                and value >= end
                and (
                    field != 24
                    or rec not in [coff.section_records[n - 1] for n in coff.extra_relocations]
                )
            ):
                struct.pack_into("<I", result, at, value + shift)
    backup = path.with_name(path.name + ".before-" + label)
    if backup.exists():
        # A fresh generated object can contain routable calls while snapshots
        # of the previous compiler epoch remain. Preserve the prior evidence
        # before replacing this stage's input snapshot; never reuse its hash.
        evidence = path.with_name(path.name + "." + label + ".json")
        previous = json.loads(evidence.read_text())
        assert previous["status"] == "passed" and sha(backup) == previous["before_sha256"]
        history = path.with_name(path.name + ".route-history") / (
            label + "-" + previous["after_sha256"] + "-" + str(time.time_ns())
        )
        history.mkdir(parents=True, exist_ok=False)
        for item in (backup, evidence):
            assert item.resolve().parent == path.resolve().parent
            shutil.copyfile(item, history / item.name)
            assert sha(item) == sha(history / item.name)
    backup.write_bytes(raw)
    path.write_bytes(result)
    path.with_name(path.name + "." + label + ".json").write_text(
        json.dumps(
            dict(
                status="passed",
                before_sha256=sha(backup),
                after_sha256=sha(path),
                routes=routes,
                excluded_sections=list(excluded_sections),
                caller=caller,
                policy="Only decoded CALL/JMP destination operands and their COFF relocation targets.",
            ),
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", type=Path, required=True)
    ap.add_argument("--build", type=Path)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--compile", action="store_true")
    ap.add_argument("--route", nargs="*", type=Path)
    ap.add_argument("--objdump", type=Path)
    args = ap.parse_args()
    if args.compile:
        compile_extra(args.source, args.build, args.out)
    else:
        assert args.route and args.objdump
        for path in args.route:
            route(path, args.source, args.objdump)
