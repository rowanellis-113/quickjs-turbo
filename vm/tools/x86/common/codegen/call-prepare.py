"""Shared prepared .call ABI: native normalization, leaf return, owned commit.

Only volatile Win64 registers and incoming home space are used by the native
entries. The prepared C boundary receives state, target-slot, original argv,
and packed (depth << 16 | original argc). It never repeats target discovery.
The complete inherited normalizer remains the fallback before commitment.
"""

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
from abi_layout import constants as abi_constants
from native_abi import current as current_abi, current_or_load as load_layout
from pathlib import Path
import hashlib, importlib.util, json, re, struct, subprocess

sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
OLD = "JS_FrameVarargsForwardTry"
DATA = "JS_FrameCallPrepareData"
KERNEL = "JS_FrameCallPrepareCommit"
ONE = "JS_FrameCallPrepareOne"
DEEP = "JS_FrameCallPrepareDeep"
EXEC = "JS_FrameCallPrepareExecute"


def module(source, name):
    sp = importlib.util.spec_from_file_location(
        "prepared_" + name.replace("-", "_"), _frame_tool_path(name + ".py")
    )
    m = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


DATA_TYPE = r"""
typedef struct JSFramePrepareData {
    unsigned char control;
    unsigned char owned_control, reserved[6];
    uint64_t leaf_hits, prepared_entries, depths[65];
} JSFramePrepareData;
_Static_assert(sizeof(JSFramePrepareData)==544 && offsetof(JSFramePrepareData,owned_control)==1 && offsetof(JSFramePrepareData,leaf_hits)==8 &&
    offsetof(JSFramePrepareData,prepared_entries)==16 && offsetof(JSFramePrepareData,depths)==24,
    "prepared diagnostics are separate from every frame and boundary record");
"""


def private_symbols(source, build, path, allowed):
    C = module(source, "object-adapter")
    c = C.Coff(path.read_bytes())
    old = c.data[:]
    renamed = []
    common = []
    for index, s in c.all_symbols.items():
        if s["storage"] == 2 and s["section"] == 0 and s["value"]:
            providers = []
            for provider in (
                _frame_build_file(build, "CMakeFiles/qjs-core.dir/quickjs.c.obj"),
                _frame_build_file(
                    build, "CMakeFiles/qjs.dir/src/x86/win64/common/quickjs-interpreter.c.obj"
                ),
            ):
                pc = C.Coff(provider.read_bytes())
                if any(
                    v["name"] == s["name"]
                    and v["storage"] == 2
                    and (v["section"] > 0 or (v["section"] == 0 and v["value"] >= s["value"]))
                    for v in pc.all_symbols.values()
                ):
                    providers.append(dict(path=str(provider), sha256=sha(provider)))
            assert providers, ("Prepared common storage requires an existing provider", s)
            struct.pack_into("<I", c.data, c.table + index * c.stride + 8, 0)
            common.append(dict(name=s["name"], bytes=s["value"], providers=providers))
        if s["storage"] != 2 or s["section"] <= 0 or s["name"] in allowed:
            continue
        name = "prepare_emitted_" + hashlib.sha256(s["name"].encode()).hexdigest()[:32]
        at = len(c.strings)
        c.strings += name.encode() + b"\0"
        struct.pack_into("<II", c.data, c.table + index * c.stride, 0, at)
        renamed.append(dict(index=index, old=s["name"], new=name))
    result = c.finish()
    after = C.Coff(result)
    before = C.Coff(bytes(old))
    assert before.sections == after.sections
    path.write_bytes(result)
    path.with_suffix(".private.json").write_text(
        json.dumps(
            dict(
                status="passed",
                renamed=renamed,
                common_dependencies=common,
                all_section_payloads_and_relocations_identical=True,
                object_sha256=sha(path),
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def prepared_commit_body(body):
    """Shared prepared constructor without compiler-object or TU ownership."""
    marker = "FRAME_CODE int JS_FrameVarargsForwardTry(JSFrameRegisterState *state)"
    body = body.replace(
        marker,
        "FRAME_CODE int "
        + KERNEL
        + "(JSFrameRegisterState *state, JSValueConst *prepared_target,\n"
        "    JSValue *prepared_argv, unsigned geometry)",
    )
    lo = body.index("    if (!((unsigned char *)caller)[FRAME_ITERATOR_OFFSET+3])")
    last = "    target_func=callee;target_this=receiver;"
    hi = body.index(last, lo) + len(last)
    body = (
        body[:lo]
        + """    /* Native admission proved a warm supported JS target and genuine builtin
       wrappers, without a safepoint. Preserve the original operand window. */
    argc=geometry&65535;depth=geometry>>16;size=3;method=1;
    tail=op==OP_tail_call_method;
    original_argv=prepared_argv;original_func=original_argv[-1];
    original_this=original_argv[-2];callee=*prepared_target;
    target=JS_VALUE_GET_OBJ(callee)->u.func.function_bytecode;
    receiver=argc>=depth?original_argv[depth-1]:JS_UNDEFINED;
    argv=original_argv+(argc<depth?argc:depth);
    count=argc>depth?argc-depth:0;
    target_func=callee;target_this=receiver;"""
        + body[hi:]
    )
    # Execute reaches C only with leaf control !=1, or after the complete
    # inherited leaf predicate has failed. Quota/near-poll failures go to H,
    # never here. Therefore this old branch cannot succeed for the descriptor.
    # Keep quota, poll rollback, ownership, logical frames and publication.
    lo = body.index("    if (((unsigned char *)caller)[FRAME_ITERATOR_OFFSET+3]==1 &&")
    hi = body.index("    /* There is now no allocation, JS, callback", lo)
    removed = body[lo:hi]
    assert removed.count("js_frame_forward_leaf(target,argv,count,&leaf_value)") == 1
    assert "result=2;goto done;" in removed and "poll_ctx->interrupt_counter--;" in removed
    body = (
        body[:lo]
        + "    /* Native descriptor already classified this nonleaf/leaf-disabled target. */\n"
        + body[hi:]
    )
    return body


def generate_commit(source, build, path):
    text = (_frame_generated_file(build, "quickjs-interpreter-varargs.c")).read_text(
        encoding="utf-8"
    )
    marker = "FRAME_CODE int JS_FrameVarargsForwardTry(JSFrameRegisterState *state)"
    start = text.index(marker)
    end = text.index("\n}\n", start) + 3
    prefix = text[:start]
    # Retain the exact existing TU prefix and compiler namespace contract.
    prefix = prefix.replace("JS_FrameVarargsIsUncatchable", "JS_FramePrepareIsUncatchable")
    body = prepared_commit_body(text[start:end])
    path.write_text(
        prefix + "\n" + DATA_TYPE + "\nextern JSFramePrepareData " + DATA + ";\n" + body,
        encoding="utf-8",
    )


def leaf_blocks(source, diagnostics, layout_override=None):
    abi = layout_override if layout_override is not None else load_layout(source)
    fields = abi["offsets"]
    forward = fields["JSFunctionBytecode.pc2line_len"] + 7
    kind = fields["JSFunctionBytecode.byte_code_buf"] - 1
    ids = module(source, "leaf-entry").checked_opcodes(source)
    # Bit2 is explicit test observation; normal enabled mode1 never counts.
    control = [
        "lea rax, [rip+" + DATA + "]",
        "movzx eax, BYTE PTR [rax]",
        "and eax, 3",
        "cmp eax, 1",
        "je {ready}",
        "cmp eax, 2",
        "je " + OLD,
        "jmp JS_FrameCallPrepareCold",
    ]
    one = [x.replace("{ready}", "prepare_one_ready") for x in control] + [
        "prepare_one_ready:",
        "lea r10, [r8-32]",
        "mov r9d, 1",
        "jmp " + EXEC,
    ]
    deep = [x.replace("{ready}", "prepare_deep_ready") for x in control] + [
        "prepare_deep_ready:",
        "lea r10, [r8-32]",
        "mov r9d, 1",
        "prepare_unwrap:",
        "cmp DWORD PTR [r10+8], -1",
        "jne " + OLD,
        "mov rdx, QWORD PTR [r10]",
        f"cmp WORD PTR [rdx+{fields['JSObject.class_id']}], 13",
        "je prepare_target",
        f"cmp WORD PTR [rdx+{fields['JSObject.class_id']}], 12",
        "jne " + OLD,
        "lea rax, [rip+qjs_frame_core_js_function_call]",
        f"cmp QWORD PTR [rdx+{fields['JSObject.u.cfunc.c_function']}], rax",
        "jne " + OLD,
        f"cmp BYTE PTR [rdx+{fields['JSObject.u.cfunc.cproto']}], 0",
        "jne " + OLD,
        f"cmp WORD PTR [rdx+{fields['JSObject.u.cfunc.magic']}], 0",
        "jne " + OLD,
        f"cmp BYTE PTR [rdx+{fields['JSObject.u.cfunc.length']}], 1",
        "jne " + OLD,
        "cmp r9d, 64",
        "jae " + OLD,
        # For depth d+1 the target is original argv[d-1]. No read occurs
        # when that original argument does not exist.
        "cmp r11d, r9d",
        "jb " + OLD,
        "mov eax, r9d",
        "dec eax",
        "shl rax, 4",
        "lea r10, [r8+rax]",
        "inc r9d",
        "jmp prepare_unwrap",
        "prepare_target:",
        f"mov rdx, QWORD PTR [rdx+{fields['JSObject.u.func.function_bytecode']}]",
        f"test BYTE PTR [rdx+{kind}], 1",
        "jz " + OLD,
        "jmp " + EXEC,
    ]
    run = [
        # Descriptor is entirely within the incoming 32-byte home area.
        # Original VM fallback/argc at caller rsp32/rsp40 are untouched.
        "mov QWORD PTR [rsp+8], rdx",
        "mov QWORD PTR [rsp+24], r8",
        "mov eax, r9d",
        "shl eax, 16",
        "or eax, r11d",
        "mov DWORD PTR [rsp+16], eax",
        "mov rax, QWORD PTR [rcx]",
        "mov rax, QWORD PTR [rax+80]",
        f"cmp BYTE PTR [rax+{forward}], 1",
        "jne prepare_c_commit",
        f"cmp WORD PTR [rdx+{fields['JSFunctionBytecode.var_count']}], 0",
        "jne prepare_c_commit",
        f"cmp DWORD PTR [rdx+{fields['JSFunctionBytecode.var_ref_count']}], 0",
        "jne prepare_c_commit",
        f"cmp WORD PTR [rdx+{fields['JSFunctionBytecode.stack_size']}], 2",
        "ja prepare_c_commit",
        f"mov eax, DWORD PTR [rdx+{fields['JSFunctionBytecode.byte_code_len']}]",
        f"mov r10, QWORD PTR [rdx+{fields['JSFunctionBytecode.byte_code_buf']}]",
        "cmp eax, 1",
        "je prepare_return_undefined",
        "cmp eax, 2",
        "je prepare_return_value",
        "cmp eax, 4",
        "jne prepare_c_commit",
        # Same four-byte integer-only add predicate as inherited H.
        f"cmp BYTE PTR [r10+2], {ids['add']}",
        "jne prepare_c_commit",
        f"cmp BYTE PTR [r10+3], {ids['return']}",
        "jne prepare_c_commit",
        "movzx eax, BYTE PTR [r10]",
        f"sub eax, {ids['get_arg0']}",
        "cmp eax, 3",
        "ja prepare_c_commit",
        "add eax, r9d",
        "cmp eax, r11d",
        "jae prepare_c_commit",
        "shl rax, 4",
        "cmp DWORD PTR [r8+rax+8], 0",
        "jne prepare_c_commit",
        "mov edx, DWORD PTR [r8+rax]",
        "mov DWORD PTR [rsp+32], edx",
        "movzx eax, BYTE PTR [r10+1]",
        f"sub eax, {ids['push_minus1']}",
        "cmp eax, 8",
        "jbe prepare_add_short",
        "movzx eax, BYTE PTR [r10+1]",
        f"sub eax, {ids['get_arg0']}",
        "cmp eax, 3",
        "ja prepare_c_commit",
        "add eax, r9d",
        "cmp eax, r11d",
        "jae prepare_c_commit",
        "shl rax, 4",
        "cmp DWORD PTR [r8+rax+8], 0",
        "jne prepare_c_commit",
        "mov eax, DWORD PTR [r8+rax]",
        "jmp prepare_add_value",
        "prepare_add_short:",
        "dec eax",
        "prepare_add_value:",
        "add eax, DWORD PTR [rsp+32]",
        "jo prepare_c_commit",
        "jmp prepare_integer",
        "prepare_return_undefined:",
        f"cmp BYTE PTR [r10], {ids['return_undef']}",
        "jne prepare_c_commit",
        "jmp prepare_undefined",
        "prepare_return_value:",
        f"cmp BYTE PTR [r10+1], {ids['return']}",
        "jne prepare_c_commit",
        "movzx eax, BYTE PTR [r10]",
        f"sub eax, {ids['push_minus1']}",
        "cmp eax, 8",
        "jbe prepare_small_integer",
        "movzx eax, BYTE PTR [r10]",
        f"sub eax, {ids['get_arg0']}",
        "cmp eax, 3",
        "jbe prepare_argument",
        f"cmp BYTE PTR [r10], {ids['undefined']}",
        "je prepare_undefined",
        f"cmp BYTE PTR [r10], {ids['null']}",
        "je prepare_null",
        f"cmp BYTE PTR [r10], {ids['push_false']}",
        "je prepare_false",
        f"cmp BYTE PTR [r10], {ids['push_true']}",
        "jne prepare_c_commit",
        "mov eax, 1",
        "jmp prepare_boolean",
        "prepare_false:",
        "xor eax, eax",
        "prepare_boolean:",
        "movq xmm0, rax",
        "mov eax, 1",
        "jmp prepare_tag",
        "prepare_null:",
        "pxor xmm0, xmm0",
        "mov eax, 2",
        "jmp prepare_tag",
        "prepare_undefined:",
        "pxor xmm0, xmm0",
        "mov eax, 3",
        "jmp prepare_tag",
        "prepare_small_integer:",
        "dec eax",
        "prepare_integer:",
        "movq xmm0, rax",
        "xor eax, eax",
        "prepare_tag:",
        "movq xmm1, rax",
        "punpcklqdq xmm0, xmm1",
        "jmp prepare_leaf_quota",
        "prepare_argument:",
        "add eax, r9d",
        "cmp eax, r11d",
        "jae prepare_undefined",
        "shl rax, 4",
        "movdqu xmm0, XMMWORD PTR [r8+rax]",
        "prepare_leaf_quota:",
        "mov rdx, QWORD PTR [rsp+8]",
        # H's complete hypothetical child + every logical native frame is
        # still required to fit, even when all activations can be elided.
        "mov eax, r11d",
        "sub eax, r9d",
        "jae prepare_actual",
        "xor eax, eax",
        "prepare_actual:",
        f"movzx r10d, WORD PTR [rdx+{fields['JSFunctionBytecode.arg_count']}]",
        "cmp eax, r10d",
        "cmovb eax, r10d",
        f"movzx r10d, WORD PTR [rdx+{fields['JSFunctionBytecode.stack_size']}]",
        "add eax, r10d",
        "shl rax, 4",
        "add rax, 128",
        "imul r10, r9, 80",
        "add rax, r10",
        "mov r10, QWORD PTR [rcx+8]",
        "mov rdx, QWORD PTR [r10+8]",
        "sub rdx, QWORD PTR [r10+16]",
        "cmp rax, rdx",
        "ja " + OLD,
        "add rax, QWORD PTR [rcx+32]",
        "jc " + OLD,
        "add rax, 5280",
        "jc " + OLD,
        "mov r10, rsp",
        "sub r10, rax",
        "jc " + OLD,
        f"cmp r10, QWORD PTR [rcx+{2312 if diagnostics else 72}]",
        "jb " + OLD,
        # Same exact realm order as H: caller realm, then each builtin
        # wrapper's realm. Only counters change before the final poll. A
        # near counter refunds the whole successful prefix before fallback.
        "mov r10, QWORD PTR [rcx]",
        "mov r10, QWORD PTR [r10+80]",
        f"mov r10, QWORD PTR [r10+{fields['JSFunctionBytecode.realm']}]",
        f"cmp DWORD PTR [r10+{fields['JSContext.interrupt_counter']}], 1",
        "jle " + OLD,
        f"dec DWORD PTR [r10+{fields['JSContext.interrupt_counter']}]",
        "xor edx, edx",
        "mov rax, QWORD PTR [r8-16]",
        f"mov r10, QWORD PTR [rax+{fields['JSObject.u.cfunc.realm']}]",
        f"cmp DWORD PTR [r10+{fields['JSContext.interrupt_counter']}], 1",
        "jle prepare_refund_polls",
        f"dec DWORD PTR [r10+{fields['JSContext.interrupt_counter']}]",
        "inc edx",
        "cmp edx, r9d",
        "jae prepare_polls_ready",
        "mov rax, QWORD PTR [r8-32]",
        f"mov r10, QWORD PTR [rax+{fields['JSObject.u.cfunc.realm']}]",
        f"cmp DWORD PTR [r10+{fields['JSContext.interrupt_counter']}], 1",
        "jle prepare_refund_polls",
        f"dec DWORD PTR [r10+{fields['JSContext.interrupt_counter']}]",
        "inc edx",
        "cmp edx, r9d",
        "jae prepare_polls_ready",
        "mov r11, r8",
        "prepare_poll_remaining:",
        "mov rax, QWORD PTR [r11]",
        f"mov r10, QWORD PTR [rax+{fields['JSObject.u.cfunc.realm']}]",
        f"cmp DWORD PTR [r10+{fields['JSContext.interrupt_counter']}], 1",
        "jle prepare_refund_polls",
        f"dec DWORD PTR [r10+{fields['JSContext.interrupt_counter']}]",
        "add r11, 16",
        "inc edx",
        "cmp edx, r9d",
        "jb prepare_poll_remaining",
        "prepare_polls_ready:",
        # Own a returned reference before the original return consumer can
        # free arguments or invoke a finalizer. Source window remains rooted.
        "movq rax, xmm0",
        "psrldq xmm0, 8",
        "movq r10, xmm0",
        "cmp r10d, -9",
        "jb prepare_no_dup",
        f"inc DWORD PTR [rax{abi_constants(abi)['QJS_ABI_REF_COUNT_OFFSET']:+d}]",
        "prepare_no_dup:",
        "mov QWORD PTR [rcx+40], rax",
        "mov QWORD PTR [rcx+48], r10",
        "mov r10, QWORD PTR [rcx]",
        "mov r8, QWORD PTR [rcx+24]",
        "mov QWORD PTR [r10+64], r8",
        "mov QWORD PTR [r10+104], r8",
        "mov rdx, QWORD PTR [rcx+16]",
        "mov eax, DWORD PTR [rsp+16]",
        "and eax, 65535",
        "add eax, 2",
        f"cmp BYTE PTR [rdx], {ids['tail_call_method']}",
        "jne prepare_not_tail",
        "or eax, 32768",
        "prepare_not_tail:",
        "mov WORD PTR [r10+126], ax",
        "add rdx, 3",
        "mov QWORD PTR [r10+48], rdx",
        "mov QWORD PTR [rcx+16], rdx",
    ]
    run += [
        "lea rax, [rip+" + DATA + "]",
        "test BYTE PTR [rax], 4",
        "jz prepare_leaf_unobserved",
        "lock inc QWORD PTR [rax+8]",
        "lock inc QWORD PTR [rax+r9*8+24]",
        "prepare_leaf_unobserved:",
    ]
    run += [
        "mov eax, 2",
        "ret",
        "prepare_c_commit:",
        "lea rax, [rip+" + DATA + "]",
        "test BYTE PTR [rax], 4",
        "jz prepare_c_unobserved",
        "lock inc QWORD PTR [rax+16]",
        "mov r10d, DWORD PTR [rsp+16]",
        "shr r10d, 16",
        "lock inc QWORD PTR [rax+r10*8+24]",
        "prepare_c_unobserved:",
        "mov r9d, DWORD PTR [rsp+16]",
        "mov r8, QWORD PTR [rsp+24]",
        "mov eax, r9d",
        "shr eax, 16",
        "cmp eax, 1",
        "jne prepare_c_later",
        "lea rdx, [r8-32]",
        "jmp " + KERNEL,
        "prepare_c_later:",
        "sub eax, 2",
        "shl rax, 4",
        "lea rdx, [r8+rax]",
        "jmp " + KERNEL,
    ]
    # Root was decremented before entering this label. edx is exactly the
    # number of successfully decremented wrapper realms; the failing realm
    # is excluded. Repeated/aliased realm pointers receive matching refunds.
    run += [
        "prepare_refund_polls:",
        "mov r10, QWORD PTR [rcx]",
        "mov r10, QWORD PTR [r10+80]",
        f"mov r10, QWORD PTR [r10+{fields['JSFunctionBytecode.realm']}]",
        f"inc DWORD PTR [r10+{fields['JSContext.interrupt_counter']}]",
        "test edx, edx",
        "jz " + OLD,
        "mov rax, QWORD PTR [r8-16]",
        f"mov r10, QWORD PTR [rax+{fields['JSObject.u.cfunc.realm']}]",
        f"inc DWORD PTR [r10+{fields['JSContext.interrupt_counter']}]",
        "dec edx",
        "jz " + OLD,
        "mov rax, QWORD PTR [r8-32]",
        f"mov r10, QWORD PTR [rax+{fields['JSObject.u.cfunc.realm']}]",
        f"inc DWORD PTR [r10+{fields['JSContext.interrupt_counter']}]",
        "dec edx",
        "jz " + OLD,
        "mov r11, r8",
        "prepare_refund_remaining:",
        "mov rax, QWORD PTR [r11]",
        f"mov r10, QWORD PTR [rax+{fields['JSObject.u.cfunc.realm']}]",
        f"inc DWORD PTR [r10+{fields['JSContext.interrupt_counter']}]",
        "add r11, 16",
        "dec edx",
        "jnz prepare_refund_remaining",
        "jmp " + OLD,
    ]
    return [(ONE, one), (DEEP, deep), (EXEC, run)]


def blocks(source, diagnostics, layout_override=None):
    return module(source, "call-prepare-owned").extend_blocks(
        source,
        leaf_blocks(source, diagnostics, layout_override=layout_override),
        diagnostics,
        layout_override=layout_override,
    )


def compile_extra(source, build, compiler, msvc, diagnostics):
    M = module(source, "atod")
    M.compile_extra(
        source,
        build,
        _frame_generated_file(build, "quickjs-interpreter-call-prepare-c.obj"),
        generator=lambda src, p: generate_commit(src, build, p),
        filename="quickjs-interpreter-call-prepare.c",
        late_name=".qjzzva",
    )
    private_symbols(
        source,
        build,
        _frame_generated_file(build, "quickjs-interpreter-call-prepare-c.obj"),
        {KERNEL},
    )

    def config(src, path):
        attr = (
            '__declspec(allocate(".qjszzcm$zzzzzzzzzzprepare"))'
            if msvc
            else '__attribute__((section(".qjslcm$zzforward"),used))'
        )
        code = (
            '__declspec(code_seg(".qjzzva")) __declspec(noinline)'
            if msvc
            else '__attribute__((section(".qjzzva"),noipa))'
        )
        path.write_text(
            '#include <stddef.h>\n#include <stdint.h>\n#include <stdlib.h>\n#ifdef _MSC_VER\n#include <intrin.h>\n#pragma section(".qjszzcm$zzzzzzzzzzprepare",read,write)\n#endif\n'
            + DATA_TYPE
            + "\n"
            + attr
            + " JSFramePrepareData "
            + DATA
            + "={255};\nextern int "
            + OLD
            + "(void *);\n"
            + code
            + """\nint JS_FrameCallPrepareCold(void *state)
{
    unsigned char mode=getenv("QJS_DISABLE_FRAME_CALL_PREPARE")?2:1;
    if(getenv("QJS_OBSERVE_FRAME_CALL_PREPARE"))mode|=4;
    unsigned char owned=getenv("QJS_DISABLE_FRAME_CALL_PREPARE_OWNED")?2:1;
#ifdef _MSC_VER
    _InterlockedExchange8((volatile char *)&JS_FrameCallPrepareData.owned_control,(char)owned);
    _InterlockedExchange8((volatile char *)&JS_FrameCallPrepareData.control,(char)mode);
#else
    __atomic_store_n(&JS_FrameCallPrepareData.owned_control,owned,__ATOMIC_RELAXED);
    __atomic_store_n(&JS_FrameCallPrepareData.control,mode,__ATOMIC_RELAXED);
#endif
    return JS_FrameVarargsForwardTry(state);
}
""",
            encoding="utf-8",
        )

    M.compile_extra(
        source,
        build,
        _frame_generated_file(build, "quickjs-interpreter-call-prepare-config.obj"),
        generator=config,
        filename="quickjs-interpreter-call-prepare-config.c",
        late_name=".qjzzva",
    )
    private_symbols(
        source,
        build,
        _frame_generated_file(build, "quickjs-interpreter-call-prepare-config.obj"),
        {"JS_FrameCallPrepareCold", DATA},
    )
    bs = blocks(source, diagnostics)
    externals = (OLD, KERNEL, "JS_FrameCallPrepareCold", "qjs_frame_core_js_function_call")
    if msvc:
        text = [
            "OPTION CASEMAP:NONE",
            "OPTION DOTNAME",
            *["EXTERN " + n + ":PROC" for n in externals],
            "EXTERN " + DATA + ":BYTE",
            ".qjzzva SEGMENT ALIGN(16) READONLY 'CODE'",
        ]
        for name, body in bs:
            text += ["ALIGN 16", "PUBLIC " + name + ", " + name + "_end", name + " PROC"]
            for line in body:
                line = re.sub(r"\[rip\+([^\]]+)\]", r"\1", line)
                if re.fullmatch(r"j\w+ \w+", line):
                    op, target = line.split()
                    line = op + " NEAR PTR " + target
                text.append(line)
            text += [name + "_end LABEL BYTE", name + " ENDP"]
        text += [
            "ALIGN 4",
            "prepare_unwind LABEL BYTE",
            "DB 1,0,0,0",
            ".qjzzva ENDS",
            ".pdata$zzzzzznullfast SEGMENT ALIGN(4) READONLY 'DATA'",
        ]
        for name, _ in bs:
            text += ["DD IMAGEREL " + name + ", IMAGEREL " + name + "_end, IMAGEREL prepare_unwind"]
        text += [".pdata$zzzzzznullfast ENDS", "END"]
        asm = _frame_generated_file(build, "quickjs-interpreter-call-prepare.asm")
        obj = asm.with_suffix(".obj")
        command = [compiler.with_name("ml64.exe"), "/nologo", "/c", "/Fo" + str(obj), asm]
    else:
        text = [".intel_syntax noprefix", '.section .qjzzva,"xr"']
        for name, body in bs:
            text += [
                ".p2align 4",
                ".globl " + name + ", " + name + "_end",
                ".def " + name + "; .scl 2; .type 32; .endef",
                name + ":",
                *body,
                name + "_end:",
            ]
        text += [
            ".p2align 2",
            "prepare_unwind:",
            ".byte 1,0,0,0",
            '.section .pdata$zzzzzznullfast,"dr"',
            ".p2align 2",
        ]
        for name, _ in bs:
            text += [".rva " + name + ", " + name + "_end, prepare_unwind"]
        asm = _frame_generated_file(build, "quickjs-interpreter-call-prepare.S")
        obj = asm.with_suffix(".obj")
        command = [compiler, "-c", "-g0", asm, "-o", obj]
    asm.write_text("\n".join(text) + "\n", encoding="ascii")
    command = list(map(str, command))
    p = subprocess.run(command, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
    obj.with_suffix(".log").write_bytes(p.stdout + p.stderr)
    assert p.returncode == 0, (command, p.stdout, p.stderr)
    (_frame_generated_file(build, "quickjs-call-prepare-generation.json")).write_text(
        json.dumps(
            dict(
                status="passed",
                generator_sha256=sha(__file__),
                source_sha256=sha(asm),
                object_sha256=sha(obj),
                owned_generator_sha256=sha(_frame_tool_path("call-prepare-owned")),
                functions=[n for n, _ in bs],
                diagnostics=diagnostics,
                protocol="State/target-slot/original-argv/packed-depth-and-argc in four Win64 argument registers. Native entries write only volatile registers, XMM0/1 and incoming home space. No boundary/frame growth. Partial native poll updates are fully refunded before fallback; no calls, observers or fallback after the final successful poll.",
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def append_module(source, build, output, msvc, group, prefix, owner, merge):
    for obj, root, tag, suffix in (
        ("quickjs-interpreter-call-prepare-c.obj", KERNEL, "prepared-commit-c", "L"),
        ("quickjs-interpreter-call-prepare.obj", ONE, "prepared-descriptor-asm", "M"),
        (
            "quickjs-interpreter-call-prepare-config.obj",
            "JS_FrameCallPrepareCold",
            "prepared-control",
            "N",
        ),
    ):
        merge.append(
            output,
            _frame_build_file(build, obj),
            root,
            tag,
            keep_all=True,
            code_input=".qjzzva",
            code_output=group if msvc else group + "$" + suffix,
            pdata_output=prefix + "1",
            metadata_inputs=(".voltbl",) if msvc else (),
            writable_metadata_inputs=(
                (".qjszzcm$zzzzzzzzzzprepare",) if msvc else (".qjslcm$zzforward",)
            )
            if suffix == "N"
            else (),
            base_owner=owner,
            baseline_sections=(),
        )


def route_probe(body):
    old = f"cmp WORD PTR [rdx+{current_abi()['offsets']['JSObject.class_id']}], 12"
    at = body.index(old)
    assert body[at + 1] == "je " + OLD
    body = list(body)
    body[at + 1] = "je " + DEEP
    return body
