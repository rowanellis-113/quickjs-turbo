import sys as _x86_sys
from pathlib import Path as _X86Path

_x86_sys.path.insert(0, str(_X86Path(__file__).resolve().parents[2]))
from x86.common.paths_x86 import activate_tools as _act_x86, source_file

_act_x86()

"""Build a development Linux owned-frame executor from qualified input.

Public boundaries use SysV. The optional register VM explicitly retains typed
private ms_abi bridges at this stage; complete feature migration is separate.
The original portable archive is not modified.
"""

import argparse
import hashlib
import json
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
from control_flow import property_note


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", type=Path, required=True)
    ap.add_argument("--build", type=Path, required=True)
    ap.add_argument("--layout", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--internal-quota", action="store_true")
    ap.add_argument("--route-internal", action="store_true")
    ap.add_argument("--register-vm", type=Path)
    ap.add_argument(
        "--prepare-only",
        action="store_true",
        help="Generate C/headers/bridge assembly before the normal CMake compilation edge",
    )
    ap.add_argument("--command-source", type=Path)
    a = ap.parse_args()
    source, build, layout_dir, output = [
        p.resolve() for p in (a.source, a.build, a.layout, a.output)
    ]
    output.mkdir(parents=True, exist_ok=a.prepare_only)
    layout = json.loads((layout_dir / "layout.json").read_text())
    vm = None
    if a.register_vm:
        if not a.internal_quota or not a.route_internal:
            raise ValueError("Register VM requires internal routing and stack quota")
        a.register_vm = a.register_vm.resolve()
        vm = json.loads((a.register_vm / "VM.json").read_text())
        if (
            sha(a.register_vm / "quickjs-linux-vm.S") != vm["assembly_sha256"]
            or sha(layout_dir / "layout.json") != vm["layout_sha256"]
        ):
            raise ValueError("Register assembly/layout binding changed")
        if (
            vm.get("native_entries")
            and sha(a.register_vm / "quickjs-linux-entry.S")
            != vm["native_entries"]["assembly_sha256"]
        ):
            raise ValueError("Native SysV entry assembly changed")
    receipt = json.loads((build / "generated/backports/BACKPORTS.json").read_text())
    core = Path(receipt["compiler_input"])
    if (
        sha(core) != layout["compiler_input_sha256"]
        or sha(source_file(source, "quickjs.c")) != layout["source_sha256"]
    ):
        raise ValueError("Layout and compiler input must match")
    original = core.read_text()
    anchor = "JSValue JS_Call(JSContext *ctx,"
    if original.count(anchor) != 1:
        raise ValueError("Public call definition anchor changed")
    if a.route_internal and not a.internal_quota:
        raise ValueError("Internal routing requires the owned-frame stack quota")
    text = original.replace(anchor, "JSValue JS_LegacyCall(JSContext *ctx,", 1)
    if a.route_internal:
        definition = re.compile(r"(^static JSValue )JS_CallInternal(\([^;{}]*\)\s*\{)", re.M | re.S)
        text, count = definition.subn(r"\1JS_LegacyCallInternal\2", text)
        if count != 1:
            raise ValueError("Internal call definition anchor changed")
        public = re.compile(r"(^JSValue JS_LegacyCall\([^;{}]*\)\s*\{)(.*?^\})", re.M | re.S)
        match = public.search(text)
        if not match or match[2].count("JS_CallInternal(") != 1:
            raise ValueError("Original public fallback body changed")
        text = (
            text[: match.start(2)]
            + match[2].replace("JS_CallInternal(", "JS_LegacyCallInternal(")
            + text[match.end(2) :]
        )
        # Only fallback calls within the owned executor bypass the new selector.
        # All original core calls keep JS_CallInternal and reach the selector.
        text += "\n#define JS_CallInternal JS_LegacyCallInternal\n"
    if vm and vm.get("native_entries"):
        text += "\n#define QJS_LINUX_NATIVE_ENTRIES 1\n"
    if vm and vm.get("native_construct"):
        text += "\n#define QJS_LINUX_CONSTRUCT_CONTINUATION 1\n"
    if vm and vm.get("native_admission"):
        from admission import generate as generate_admission

        generate_admission(
            source, output, original, layout, construct=bool(vm.get("native_construct"))
        )
    text += """
/* Linux development foundation: exact core types and helpers in this TU. */
#include "interpreter-private-abi.h"
#include "src/common/call/interpreter-bytecode-metadata.inc"
#include "src/x86/linux/interpreter-private-compat.inc"
#if defined(QJS_INTERP_FRAME_LINUX_SHARED)
#include "src/common/call/interpreter-slow-host-declare.inc"
#endif
#include "src/common/value/arithmetic.inc"
#include "src/common/call/quickjs-interpreter-loop.inc"
#if defined(QJS_INTERP_FRAME_LINUX_SHARED)
#include "src/common/call/quickjs-interpreter-shared.inc"
#include "src/common/call/interpreter-slow-host.inc"
#elif defined(QJS_LINUX_REGISTER_FOUNDATION)
/* Shared/native-host supplements are separate port items. This stage retains
 * the original C entry semantics instead of compiling PE TLS/host gates. */
#define JS_FrameCallEntryDispatch js_frame_call_entry
#else
#include "src/common/call/quickjs-interpreter-shared.inc"
#endif
"""
    if vm and vm.get("native_admission"):
        text = text.replace(
            '#include "src/common/call/quickjs-interpreter-loop.inc"',
            '#include "quickjs-linux-loop.h"\n#include "quickjs-linux-admission.h"',
            1,
        )
    if vm and vm.get("native_construct"):
        text = text.replace(
            '#include "src/common/call/interpreter-slow-host.inc"',
            '#include "src/common/call/interpreter-slow-host.inc"\n#include "quickjs-linux-construct-host.h"',
            1,
        )
    if vm and vm.get("native_c_invoke"):
        text += '#include "src/x86/linux/interpreter-c-invoke.inc"\n'
    if vm and vm.get("native_publication"):
        text += '#include "src/common/linux/interpreter-publish.inc"\n'
    if a.route_internal:
        text += """
#undef JS_CallInternal
static JSValue JS_CallInternal(JSContext *ctx, JSValueConst func_obj,
                               JSValueConst this_obj, JSValueConst new_target,
                               int argc, JSValueConst *argv, int flags)
{
    /* Retain the original entry before any shared-TLS/C-frame setup when
     * this call cannot use the owned bytecode executor. These are the same
     * flag/class/control boundaries checked by the Win64 leaf selectors. */
    if ((flags & ~JS_CALL_FLAG_COPY_ARGV) || FRAME_STATE(ctx->rt) == 2 ||
        JS_VALUE_GET_TAG(func_obj) != JS_TAG_OBJECT ||
        JS_VALUE_GET_OBJ(func_obj)->class_id != JS_CLASS_BYTECODE_FUNCTION)
        return JS_LegacyCallInternal(ctx, func_obj, this_obj, new_target, argc, argv, flags);
    if (unlikely(!FRAME_INTERNAL_STATE(ctx->rt)))
        FRAME_INTERNAL_STATE(ctx->rt) = qjs_internal_interp_internal_disabled() ? 2 : 1;
    if (FRAME_INTERNAL_STATE(ctx->rt) != 1 ||
        FRAME_KIND(JS_VALUE_GET_OBJ(func_obj)->u.func.function_bytecode) == 2)
        return JS_LegacyCallInternal(ctx, func_obj, this_obj, new_target, argc, argv, flags);
    return JS_FrameCallEntryDispatch(ctx, func_obj, this_obj, new_target, argc, argv, flags);
}
"""
    text += """
JSValue JS_LinuxCallPublicFallback(JSContext *ctx, JSValueConst func_obj, JSValueConst this_obj,
                int argc, JSValueConst *argv)
{
    if (FRAME_STATE(ctx->rt) == 2 || JS_VALUE_GET_TAG(func_obj) != JS_TAG_OBJECT ||
        JS_VALUE_GET_OBJ(func_obj)->class_id != JS_CLASS_BYTECODE_FUNCTION)
        return JS_LegacyCall(ctx, func_obj, this_obj, argc, argv);
    return JS_FrameCallEntryDispatch(ctx, func_obj, this_obj, JS_UNDEFINED, argc,
                                    argv, JS_CALL_FLAG_COPY_ARGV);
}
"""
    if not (vm and vm.get("native_entries")):
        text = text.replace("JSValue JS_LinuxCallPublicFallback(", "JSValue JS_Call(", 1)
    if vm and vm.get("helper_protocol") == "audited-sysv-assembly":
        from c_workers import generate as generate_c_workers

        text = generate_c_workers(source, output, text, layout)
    if vm and vm.get("native_arguments"):
        from arguments import generate as generate_arguments

        text = generate_arguments(source, output, text, layout, original)
    if vm and vm.get("native_varargs"):
        from varargs_native import generate as generate_varargs

        text = generate_varargs(source, output, text, layout)
    if vm and vm.get("native_literals"):
        from literal_shapes import generate as generate_literals

        text = generate_literals(
            source,
            output,
            text,
            layout,
            unified_slow=bool(vm.get("native_indexed") and vm.get("native_iterators")),
        )
    if vm and vm.get("native_indexed"):
        from indexed_ops import generate as generate_indexed

        text = generate_indexed(source, output, text, layout)
    if vm and vm.get("native_properties"):
        from property_family import generate as generate_properties

        text = generate_properties(
            source, output, text, layout, reference_controls=bool(vm.get("native_global_bindings"))
        )
    if vm and vm.get("native_comparisons"):
        from comparisons import generate as generate_comparisons

        text = generate_comparisons(source, output, text, layout)
    if vm and vm.get("native_numeric"):
        from numeric import generate as generate_numeric
        from compiler_projection import generate as generate_compiler_projection

        text = generate_numeric(source, output, text, layout)
        text = generate_compiler_projection(source, output, text, original, layout)
    if vm and vm.get("native_global_bindings"):
        from global_bindings import generate as generate_global_bindings

        text = generate_global_bindings(source, output, text, layout)
    if vm and vm.get("native_null_proto"):
        from null_proto import generate as generate_null_proto

        text = generate_null_proto(source, output, text, layout)
    if vm and vm.get("native_c_invoke"):
        from inline_objects import core_storage

        text = core_storage(text, property_ic=layout["property_ic"])
    generated = output / "quickjs-linux-foundation.c"
    generated.write_text(text)
    commands = json.loads((build / "compile_commands.json").read_text())
    command_source = (
        a.command_source.resolve() if a.command_source else source_file(source, "quickjs.c")
    )
    original_command = next(c for c in commands if Path(c["file"]).resolve() == command_source)
    argv = shlex.split(original_command["command"])
    compiler, flags = argv[0], []
    i = 1
    while i < len(argv):
        if argv[i] in ("-o", "-c"):
            i += 2
        else:
            flags.append(argv[i])
            i += 1
    flags.append("-DQJS_INTERP_FRAME_LINUX")
    if a.internal_quota:
        flags.append("-DQJS_INTERP_FRAME_INTERNAL_ENTRY")
    if vm:
        flags += ["-DQJS_INTERP_FRAME_REGISTER_ABI", "-DQJS_LINUX_REGISTER_FOUNDATION"]
        if vm.get("shared_entry"):
            flags.append("-DQJS_INTERP_FRAME_LINUX_SHARED")
    executed_commands = []

    def run(label, args, cwd=build):
        executed_commands.append(dict(label=label, cwd=str(cwd), command=list(map(str, args))))
        (output / "COMMANDS.json").write_text(json.dumps(executed_commands, indent=2) + "\n")
        with (
            (output / (label + ".stdout")).open("wb") as so,
            (output / (label + ".stderr")).open("wb") as se,
        ):
            subprocess.run(list(map(str, args)), cwd=cwd, stdout=so, stderr=se, check=True)

    # Overlay quickjs.h must win include search exactly as for the real core.
    include_flags = ["-I" + str(core.parent), "-I" + str(layout_dir), "-I" + str(output)]
    asm_obj = None
    entry_obj = None
    if vm:
        run(
            "generate-slow-c",
            [
                sys.executable,
                "-B",
                source / "tools/common/c_extract/generate_slow_c.py",
                "--source",
                source,
                "--output",
                output / "quickjs-interpreter-slow.h",
            ],
        )
        if vm.get("shared_entry"):
            slow = output / "quickjs-interpreter-slow.h"
            before = slow.read_text()
            original_call = (
                "ret_val = js_frame_legacy_call(ctx, callee, call_this, call_argc, vc(call_argv));"
            )
            if before.count(original_call) != 1:
                raise ValueError("The retained C-step legacy call boundary changed")
            after = before.replace(
                original_call,
                "ret_val = js_frame_slow_host_call(state, frame, segment, used_bytes, pc, sp, "
                "ctx, callee, call_this, call_argc, vc(call_argv));",
            )
            slow.write_text(after)
            (output / "SLOW-HOST.json").write_text(
                json.dumps(
                    dict(
                        status="one-retained-call-boundary-routed",
                        before_sha256=hashlib.sha256(before.encode()).hexdigest(),
                        after_sha256=sha(slow),
                        protocol="typed coherent paused-state publication; original call ownership",
                        scope="Only the original generic legacy call in the C step; other helpers are separate coverage",
                    ),
                    indent=2,
                )
                + "\n"
            )
        if vm.get("native_forwarding"):
            from forwarding import release as release_forwarding

            slow = output / "quickjs-interpreter-slow.h"
            slow.write_text(release_forwarding(slow.read_text()))
            host_receipt = output / "SLOW-HOST.json"
            if host_receipt.exists():
                host = json.loads(host_receipt.read_text())
                host["host_routed_sha256"] = host["after_sha256"]
                host["after_sha256"] = sha(slow)
                host["post_host_transform"] = (
                    "Source-owned logical wrapper release after observable child cleanup"
                )
                host_receipt.write_text(json.dumps(host, indent=2) + "\n")
        if vm.get("native_construct"):
            from constructors import generate as generate_constructors

            generate_constructors(source, output, layout)
        if vm.get("native_arguments"):
            from arguments import finish_slow as finish_argument_slow

            finish_argument_slow(output)
        if vm.get("native_iterators"):
            from iterators import generate as generate_iterators

            generate_iterators(source, output, layout)
        if vm.get("native_varargs"):
            from varargs_native import finish_slow as finish_varargs_slow

            finish_varargs_slow(source, output, layout)
        if vm.get("native_literals"):
            from literal_shapes import finish_slow as finish_literal_slow

            finish_literal_slow(source, output)
        if vm.get("native_indexed"):
            from indexed_ops import finish_slow as finish_indexed_slow

            finish_indexed_slow(source, output)
        if vm.get("native_comparisons"):
            from comparisons import finish_slow as finish_comparison_slow

            finish_comparison_slow(output)
        preprocessed = output / "core-with-frame.i"
        run(
            "preprocess",
            [compiler, *include_flags, *flags, "-E", "-P", generated, "-o", preprocessed],
        )
        expanded = preprocessed.read_text()
        bridges, assembly_bridges, helper_profiles = [], [], []
        sysv = vm.get("helper_protocol") == "audited-sysv-assembly"
        if sysv and vm.get("entry_protocol") != "SysV":
            raise ValueError("SysV bridge mode requires a SysV VM entry")
        for helper, bridge in vm["helper_mapping"].items():
            target = (
                helper + "Shared"
                if vm.get("shared_entry")
                and helper in ("JS_FrameInterpHost", "JS_FrameInterpHostDirect")
                else helper
            )
            if vm.get("native_strings") and helper == "JS_FrameInterpBig_add":
                target = "JS_FrameLinuxStringAdd"
            if vm.get("native_strings") and helper == "JS_FrameInterpSlow":
                target = "JS_FrameLinuxStringSlow"
            if vm.get("native_arrays") and helper == "JS_FrameInterpSlow":
                target = "JS_FrameLinuxArraySlow"
            pattern = re.compile(
                r"\b(int|void\s*\*|void|_Bool|JSValue|uint64_t)\s*"
                + re.escape(target)
                + r"\s*\(([^;{}]*)\)\s*\{",
                re.S,
            )
            matches = list(pattern.finditer(expanded))
            if len(matches) != 1:
                raise ValueError("No unique actual C helper definition: " + helper)
            result, params = matches[0][1], matches[0][2].strip()
            names = []
            for param in params.split(",") if params and params != "void" else []:
                match = re.search(r"(\w+)\s*$", param)
                if not match:
                    raise ValueError("Review complex helper parameter: " + param)
                names.append(match[1])
            if sysv:
                signature = re.sub(r"\s+", "", params)
                state_only = "JSFrameRegisterState*state"
                host = state_only + ",JSValue*argv,intargc,_Boolmethod"
                free = state_only + ",JSContext*ctx,JSValuevalue"
                profile = (
                    "state"
                    if signature == state_only
                    else "host"
                    if signature == host
                    else "free"
                    if signature == free
                    else None
                )
                if helper == "JS_FrameCallPrepareCommit":
                    # The pinned public JSValueConst macro expands to JSValue.
                    prepared = (
                        state_only
                        + ",JSValue*prepared_target,JSValue*prepared_argv,unsignedgeometry"
                    )
                    if signature != prepared or result != "int":
                        raise ValueError(
                            "Review actual prepared forward ABI: " + result + "(" + params + ")"
                        )
                    profile = "forward-prepared"
                if helper == "JS_FrameLocaleCompareCompound":
                    compound = (
                        "JSContext*ctx,JSFunctionBytecode*b,constJSValue*args,constJSValue*thisp"
                    )
                    if signature != compound or result != "uint64_t":
                        raise ValueError(
                            "Review actual compound proof ABI: " + result + "(" + params + ")"
                        )
                    profile = "leaf-compound"
                if helper == "JS_FrameSlowDirectTryInstanceOfLeaf":
                    if signature != "JSContext*ctx,JSValue*sp" or result != "int":
                        raise ValueError("Review actual pure instanceof SysV signature")
                    profile = "leaf-instanceof"
                if helper == "JS_LinuxCInvokeInit":
                    if signature != state_only or re.sub(r"\s+", "", result) != "void*":
                        raise ValueError("The native C TLS initializer signature changed")
                    profile = "tls-slot"
                if profile is None or (
                    result not in ("int", "void") and profile not in ("tls-slot", "leaf-compound")
                ):
                    raise ValueError(
                        "Unreviewed actual SysV helper profile: "
                        + helper
                        + " "
                        + result
                        + "("
                        + params
                        + ")"
                    )
                if (profile == "host") != (
                    helper in ("JS_FrameInterpHost", "JS_FrameInterpHostDirect")
                ) or (profile == "free") != (helper == "JS_FrameInterpFree"):
                    raise ValueError("Helper identity/signature boundary changed: " + helper)
                helper_profiles.append(
                    dict(
                        helper=helper,
                        target=target,
                        bridge=bridge,
                        result=result,
                        params=params,
                        profile=profile,
                    )
                )
                body = ["mov rdi, rcx"]
                if profile == "host":
                    body += ["mov rsi, rdx", "mov edx, r8d", "mov ecx, r9d"]
                elif profile == "free":
                    body += ["mov rsi, rdx", "mov rdx, QWORD PTR [r8]", "mov rcx, QWORD PTR [r8+8]"]
                elif profile == "forward-prepared":
                    body += ["mov rsi, rdx", "mov rdx, r8", "mov ecx, r9d"]
                elif profile == "leaf-instanceof":
                    body += ["mov rsi, rdx"]
                elif profile == "leaf-compound":
                    body += ["mov rsi, rdx", "mov rdx, r8", "mov rcx, r9"]
                private_result = (
                    ["movdqu xmm0, XMMWORD PTR [rbx+40]"]
                    if profile == "host" and vm.get("native_c_invoke")
                    else []
                )
                assembly_bridges += [
                    ".p2align 4",
                    ".globl " + bridge,
                    ".hidden " + bridge,
                    ".hidden " + target,
                    ".type " + bridge + ",@function",
                    bridge + ":",
                    ".cfi_startproc",
                    "endbr64",
                    "push rdi",
                    ".cfi_adjust_cfa_offset 8",
                    ".cfi_offset rdi,-16",
                    "push rsi",
                    ".cfi_adjust_cfa_offset 8",
                    ".cfi_offset rsi,-24",
                    "sub rsp,8",
                    ".cfi_adjust_cfa_offset 8",
                    *body,
                    "call " + target,
                    *private_result,
                    "add rsp,8",
                    ".cfi_adjust_cfa_offset -8",
                    "pop rsi",
                    ".cfi_restore rsi",
                    ".cfi_adjust_cfa_offset -8",
                    "pop rdi",
                    ".cfi_restore rdi",
                    ".cfi_adjust_cfa_offset -8",
                    "ret",
                    ".cfi_endproc",
                    ".size " + bridge + ",.-" + bridge,
                ]
            else:
                bridges += [
                    '__attribute__((ms_abi,noinline,visibility("hidden")))',
                    result
                    + " "
                    + bridge
                    + "("
                    + params
                    + ") { "
                    + ("" if result == "void" else "return ")
                    + target
                    + "("
                    + ", ".join(names)
                    + "); }",
                ]
        attributes = 'visibility("hidden")' if sysv else 'ms_abi,visibility("hidden")'
        bridges += [
            "extern int "
            + vm["private_entry"]
            + "(JSFrameRegisterState *) __attribute__(("
            + attributes
            + "));"
        ]
        if vm.get("native_literals"):
            if not sysv:
                raise ValueError("Literal physical entry requires the actual SysV VM")
            bridges += [
                "int JS_LinuxLiteralRunVM(JSFrameRegisterState *state) { return "
                + vm["private_entry"]
                + "(state); }",
                "int JS_FrameInterp(JSFrameRegisterState *state) { return JS_LinuxLiteralEnter(state); }",
            ]
        else:
            bridges += [
                "int JS_FrameInterp(JSFrameRegisterState *state) { return "
                + vm["private_entry"]
                + "(state); }"
            ]
        generated.write_text(
            text
            + "\n/* Typed development private-VM bridges; no guessed clones. */\n"
            + "\n".join(bridges)
            + "\n"
        )
        (output / "BRIDGES.json").write_text(
            json.dumps(
                dict(
                    status="generated-typed-C-private-VM-bridges",
                    helper_count=len(vm["helper_mapping"]),
                    private_protocol="audited private-GPR to SysV assembly"
                    if sysv
                    else "compiler-checked ms_abi development bridge",
                    helper_profiles=helper_profiles,
                    public_protocol="SysV",
                    shared_entry=bool(vm.get("shared_entry")),
                    native_shared_supplements=False,
                ),
                indent=2,
            )
            + "\n"
        )
        asm_obj = output / "quickjs-linux-vm.o"
        if not a.prepare_only:
            run("assemble", [compiler, "-c", a.register_vm / "quickjs-linux-vm.S", "-o", asm_obj])
            if vm.get("native_entries"):
                entry_obj = output / "quickjs-linux-entry.o"
                run(
                    "assemble-entries",
                    [compiler, "-c", a.register_vm / "quickjs-linux-entry.S", "-o", entry_obj],
                )
        if sysv:
            bridge_source = output / "quickjs-linux-bridges.S"
            bridge_source.write_text(
                "\n".join(
                    [
                        ".intel_syntax noprefix",
                        '.section .text.qjs_linux_bridges,"ax",@progbits',
                        *assembly_bridges,
                        *property_note(vm["compiler_cet"]),
                        '.section .note.GNU-stack,"",@progbits',
                    ]
                )
                + "\n"
            )
            if not a.prepare_only:
                run(
                    "assemble-bridges",
                    [compiler, "-c", bridge_source, "-o", output / "quickjs-linux-bridges.o"],
                )
    if a.prepare_only:
        if not vm:
            raise ValueError("Normal native source generation requires a register VM")
        (output / "PREPARE.json").write_text(
            json.dumps(
                dict(
                    status="generated-not-compiled",
                    compiler_input_sha256=sha(core),
                    generated_source_sha256=sha(generated),
                    layout_sha256=sha(layout_dir / "layout.json"),
                    vm_assembly_sha256=vm["assembly_sha256"],
                    bridges_assembly_sha256=sha(output / "quickjs-linux-bridges.S"),
                    slow_header_sha256=sha(output / "quickjs-interpreter-slow.h"),
                    c_workers={
                        name: sha(output / name)
                        for name in (
                            "C-WORKERS.json",
                            "quickjs-linux-c-workers.h",
                            "quickjs-linux-prepared-callback.h",
                            "JSON-WORKERS.json",
                            "quickjs-linux-json.h",
                            "STRING-WORKERS.json",
                            "quickjs-linux-strings.h",
                            "ARRAY-WORKERS.json",
                            "quickjs-linux-arrays.h",
                            "BUILTIN-WORKERS.json",
                            "quickjs-linux-builtin.h",
                            "REGEXP-WORKERS.json",
                            "quickjs-linux-regexp.h",
                            "JS-CALLS.json",
                            "quickjs-linux-captured-proof.h",
                            "quickjs-linux-set-name.h",
                            "FORWARDING.json",
                            "quickjs-linux-forward.h",
                            "VM-LEAVES.json",
                        )
                        + (
                            (
                                "CONSTRUCT.json",
                                "quickjs-linux-construct.h",
                                "quickjs-linux-construct-dispatch.h",
                                "quickjs-linux-construct-host.h",
                            )
                            if vm.get("native_construct")
                            else ()
                        )
                        + (("PUBLICATION.json",) if vm.get("native_publication") else ())
                        + (
                            (
                                "GLOBAL-BINDINGS.json",
                                "GLOBAL-BINDINGS-VM.json",
                                "quickjs-linux-global-bindings.h",
                            )
                            if vm.get("native_global_bindings")
                            else ()
                        )
                        + (
                            (
                                "ARGUMENTS.json",
                                "ARGUMENTS-VM.json",
                                "quickjs-linux-arguments.h",
                                "VIRTUAL-ARGUMENTS.json",
                                "quickjs-linux-virtual-arguments-private.h",
                                "quickjs-linux-virtual-arguments.c",
                            )
                            if vm.get("native_arguments")
                            else ()
                        )
                        + (
                            ("ITERATORS.json", "ITERATORS-VM.json")
                            if vm.get("native_iterators")
                            else ()
                        )
                        + (
                            ("VARARGS.json", "VARARGS-VM.json", "quickjs-linux-varargs.h")
                            if vm.get("native_varargs")
                            else ()
                        )
                        + (
                            ("LITERALS.json", "LITERALS-VM.json", "quickjs-linux-literals.h")
                            if vm.get("native_literals")
                            else ()
                        )
                        + (
                            (
                                "COMPARISONS.json",
                                "COMPARISONS-VM.json",
                                "quickjs-linux-comparisons.h",
                            )
                            if vm.get("native_comparisons")
                            else ()
                        )
                        + (
                            (
                                "NUMERIC.json",
                                "NUMERIC-VM.json",
                                "quickjs-linux-numeric.h",
                                "quickjs-linux-bigint.h",
                                "quickjs-linux-atod.c",
                                "COMPILER-PROJECTION.json",
                                "quickjs-linux-compiler-private.h",
                                "quickjs-linux-compiler-projection.c",
                            )
                            if vm.get("native_numeric")
                            else ()
                        )
                        + (
                            ("ENTRIES.json", "quickjs-linux-entry.S")
                            if vm.get("native_entries")
                            else ()
                        )
                    }
                    if vm.get("helper_protocol") == "audited-sysv-assembly"
                    else {},
                    command_source=str(command_source),
                ),
                indent=2,
            )
            + "\n"
        )
        print("LINUX NATIVE SOURCES PREPARED", generated)
        return
    obj = output / "quickjs.c.o"
    run(
        "compile",
        [
            compiler,
            *include_flags,
            *flags,
            "-Werror=attributes",
            "-MD",
            "-MF",
            output / "core.d",
            "-c",
            generated,
            "-o",
            obj,
        ],
    )
    env_obj = output / "interpreter-env.c.o"
    run(
        "env",
        [
            compiler,
            *flags,
            "-MD",
            "-MF",
            output / "env.d",
            "-c",
            source / "src/common/internal/interpreter-env.c",
            "-o",
            env_obj,
        ],
    )
    numeric_objects = []
    if vm and vm.get("native_numeric"):
        for kind in ("atod", "compiler-projection"):
            extra_source = output / ("quickjs-linux-" + kind + ".c")
            extra_object = output / ("quickjs-linux-" + kind + ".o")
            run(
                "numeric-" + kind,
                [
                    compiler,
                    *include_flags,
                    *flags,
                    "-Werror=attributes",
                    "-c",
                    extra_source,
                    "-o",
                    extra_object,
                ],
            )
            numeric_objects.append(extra_object)
    if vm and vm.get("native_arguments"):
        extra_source = output / "quickjs-linux-virtual-arguments.c"
        extra_object = output / "quickjs-linux-virtual-arguments.o"
        run(
            "virtual-arguments",
            [
                compiler,
                *include_flags,
                *flags,
                "-Werror=attributes",
                "-c",
                extra_source,
                "-o",
                extra_object,
            ],
        )
        numeric_objects.append(extra_object)
    original_archive = build / "libqjs.a"
    original_digest = sha(original_archive)
    archive = output / "libqjs.a"
    shutil.copy2(original_archive, archive)
    members = subprocess.check_output(["ar", "t", archive], text=True).splitlines()
    if members.count("quickjs.c.o") != 1:
        raise ValueError("Expected one original core archive member")
    run(
        "archive",
        [
            "ar",
            "r",
            archive,
            obj,
            env_obj,
            *numeric_objects,
            *([asm_obj] if asm_obj else []),
            *([entry_obj] if entry_obj else []),
            *([output / "quickjs-linux-bridges.o"] if vm and sysv else []),
        ],
    )
    ninja = subprocess.check_output(
        ["ninja", "-C", build, "-t", "commands", "qjs_exe"], text=True
    ).splitlines()
    link = next(line for line in reversed(ninja) if " -o qjs " in line)
    args = shlex.split(link)
    args = args[args.index(compiler) :] if compiler in args else args[args.index("/usr/bin/cc") :]
    if args[-2:] == ["&&", ":"]:
        args = args[:-2]
    args[args.index("-o") + 1] = str(output / "qjs")
    args = [str(archive) if arg == "libqjs.a" else arg for arg in args]
    run("link", args)
    if sha(original_archive) != original_digest:
        raise ValueError("Portable input archive changed")
    dependencies = {}
    for depfile in (output / "core.d", output / "env.d"):
        words = shlex.split(depfile.read_text().replace("\\\n", " ").split(":", 1)[1])
        for word in words:
            path = Path(word)
            if not path.is_absolute():
                path = build / path
            dependencies[str(path.resolve())] = sha(path)
    (output / "INCLUDES.json").write_text(json.dumps(dependencies, indent=2) + "\n")
    (output / "source.diff").write_bytes(
        subprocess.check_output(["git", "-C", source, "diff", "--binary", "HEAD"])
    )
    record = dict(
        status="built-development-register-VM" if vm else "built-development-C-frame-foundation",
        register_vm=bool(vm),
        internal_quota=a.internal_quota,
        internal_entry_routed=a.route_internal,
        source=str(source),
        layout=str(layout_dir / "layout.json"),
        layout_sha256=sha(layout_dir / "layout.json"),
        compiler_input_sha256=sha(core),
        derived_input_sha256=sha(generated),
        source_commit=subprocess.check_output(
            ["git", "-C", source, "rev-parse", "HEAD"], text=True
        ).strip(),
        source_dirty=subprocess.check_output(
            ["git", "-C", source, "status", "--porcelain"], text=True
        ),
        includes_sha256=sha(output / "INCLUDES.json"),
        commands_sha256=sha(output / "COMMANDS.json"),
        original_archive_sha256=original_digest,
        archive_sha256=sha(archive),
        binary_sha256=sha(output / "qjs"),
        scope=(
            "Development register VM with typed private bridges; supplements and full feature qualification pending"
            if vm
            else "Development C frame/entry; register VM and full feature qualification pending"
        ),
    )
    (output / "BUILD.json").write_text(json.dumps(record, indent=2) + "\n")
    print("LINUX C FRAME FOUNDATION BUILT", output / "qjs")


if __name__ == "__main__":
    main()
