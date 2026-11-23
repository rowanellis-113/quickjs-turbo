"""Native preparation of a general single .call owned child. MIT.

Only N's supported-bytecode misses enter: RCX=state, RDX=target bytecode,
R8=original argv, R11D=native argc. All observable/failing work retains H.
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
import hashlib, importlib.util, json, re, subprocess

# Same exact C proof is compiled below and extracted by the bounded-work test.
CAPTURED_PROOF = r"""
/* MIT. Cold proof only; no allocation, GC or recursive C calls.
 * Parameters remain owned by the paused caller/logical native view. Borrowing
 * is valid only while no descendant can replace a binding before detach.
 * Reject unrelated writes too: this deliberately favors a small sound proof.
 * `sizes` is the complete upstream table, passed explicitly so extracted
 * validators can share their existing original-table adapter.
 */
static FRAME_CODE bool js_frame_captured_readonly(
    const JSFunctionBytecode *root, const uint8_t *sizes)
{
    const JSFunctionBytecode *work[64];
    unsigned count = 1, cursor, i, j, code_budget = 65536, pool_budget = 4096;
    work[0] = root;
    for (cursor = 0; cursor < count; cursor++) {
        const JSFunctionBytecode *b = work[cursor];
        const uint8_t *code = b->byte_code_buf;
        int pos, size, op;
        if (b->func_kind != JS_FUNC_NORMAL || b->is_derived_class_constructor ||
            !code || b->byte_code_len <= 0 ||
            (unsigned)b->byte_code_len > code_budget ||
            b->cpool_count < 0 || (unsigned)b->cpool_count > pool_budget ||
            (b->cpool_count && !b->cpool))
            return false;
        code_budget -= b->byte_code_len;
        pool_budget -= b->cpool_count;
        for (pos = 0; pos < b->byte_code_len; pos += size) {
            op = code[pos];
            if (op >= OP_COUNT || !(size = sizes[op]) ||
                size > b->byte_code_len - pos)
                return false;
            if (op == OP_put_arg || op == OP_set_arg ||
                (op >= OP_put_arg0 && op <= OP_put_arg3) ||
                (op >= OP_set_arg0 && op <= OP_set_arg3) ||
                op == OP_put_var_ref || op == OP_set_var_ref ||
                op == OP_put_var_ref_check || op == OP_put_var_ref_check_init ||
                (op >= OP_put_var_ref0 && op <= OP_put_var_ref3) ||
                (op >= OP_set_var_ref0 && op <= OP_set_var_ref3))
                return false;
            /* Positive whitelist: eval/apply_eval, arguments/rest exposure,
             * with and all make/put reference forms are absent. New unknown
             * upstream opcodes cannot silently widen this proof.
             */
            switch (op) {
#define FRAME_OP(id) case OP_##id:
#include "src/common/call/quickjs-interpreter-opcodes.h"
#undef FRAME_OP
            case OP_for_of_start: case OP_for_of_next: case OP_iterator_close:
            case OP_catch: case OP_gosub: case OP_ret: case OP_nip_catch:
            case OP_check_object: case OP_set_name:
                break;
            default:
                return false;
            }
        }
        /* All bytecode constants, including constructors and descendants
         * never executed on the current path, participate in the proof.
         */
        for (i = 0; i < (unsigned)b->cpool_count; i++) {
            const JSFunctionBytecode *child;
            if (JS_VALUE_GET_TAG(b->cpool[i]) != JS_TAG_FUNCTION_BYTECODE)
                continue;
            child = (JSFunctionBytecode *)JS_VALUE_GET_PTR(b->cpool[i]);
            if (!child) return false;
            for (j = 0; j < count && work[j] != child; j++) {}
            if (j != count) continue;
            if (count == countof(work)) return false;
            work[count++] = child;
        }
    }
    return true;
}
"""

sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
NAME = "JS_FrameCallForwardOwnedTry"
GENERAL = "JS_FrameCallForwardOwnedGeneral"
PUBLISH = "JS_FrameCallForwardOwnedPublish"
OLD = "JS_FrameVarargsForwardTry"


def module(source, name):
    spec = importlib.util.spec_from_file_location(
        "forward_owned_" + name.replace("-", "_"), _frame_tool_path(name + ".py")
    )
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def route_probe(body):
    body = list(body)
    lo = (
        body.index(
            f"test BYTE PTR [rdx+{current_abi()['offsets']['JSFunctionBytecode.byte_code_buf'] - 1}], 1"
        )
        + 2
    )
    hi = body.index("native_probe_value:")
    changed = []
    for i in range(lo, hi):
        if body[i].endswith(" " + OLD):
            nonleaf = body[i].startswith("jo ") or body[i - 1] in (
                "cmp r11d, 2",
                "cmp DWORD PTR [r8+24], 0",
            )
            changed.append(body[i])
            body[i] = body[i][: -len(OLD)] + (GENERAL if nonleaf else NAME)
    assert len(changed) == 13, changed
    assert sum(line.endswith(" " + GENERAL) for line in body) == 3
    assert all(not line.startswith(("call ", "push ", "pop ")) for line in body[lo:hi])
    return body


def lines(source, diagnostics, layout_override=None):
    abi = layout_override if layout_override is not None else load_layout(source)
    fields = abi["offsets"]
    kind = fields["JSFunctionBytecode.byte_code_buf"] - 1
    ((strict_byte, strict_mask),) = abi["bits"]["JSFunctionBytecode.is_strict_mode"]
    assert strict_mask == 1
    ids = module(source, "leaf-entry").checked_opcodes(source)
    limit = 2312 if diagnostics else 72
    g = [
        # A compact candidate may finish without a frame in retained H.
        # Native N's definite argc/type/overflow misses bypass this guard:
        # they have already proved H's same leaf evaluator cannot finish.
        f"cmp DWORD PTR [rdx+{fields['JSFunctionBytecode.byte_code_len']}], 4",
        "ja " + GENERAL,
        f"cmp WORD PTR [rdx+{fields['JSFunctionBytecode.var_count']}], 0",
        "jne " + GENERAL,
        f"cmp DWORD PTR [rdx+{fields['JSFunctionBytecode.var_ref_count']}], 0",
        "jne " + GENERAL,
        f"cmp WORD PTR [rdx+{fields['JSFunctionBytecode.stack_size']}], 2",
        "ja " + GENERAL,
        "jmp JS_FrameCallPrepareOne",
        GENERAL + ":",
        "lea r9, [rip+JS_FrameCallForwardOwnedControl]",
        "cmp BYTE PTR [r9], 1",
        "je owned_enabled",
        "cmp BYTE PTR [r9], 2",
        "je " + OLD,
        "jmp JS_FrameCallForwardOwnedCold",
        "owned_enabled:",
        # N already proved the supported bit. Bit1 is exactly the existing
        # readonly eligibility, including proven kind7 captures; mutable captures remain owned.
        f"test BYTE PTR [rdx+{fields['JSFunctionBytecode.byte_code_buf'] - 1}], 2",
        "jne JS_FrameCallForwardBorrowTry",
        "JS_FrameCallForwardOwnedCopy:",
        "mov QWORD PTR [rsp+8], r8",
        "mov QWORD PTR [rsp+16], r11",
        "mov QWORD PTR [rsp+32], rdx",
        # Own every actual argument, including the extra prefix.
        "xor eax, eax",
        "test r11d, r11d",
        "jz owned_actual",
        "lea eax, [r11-1]",
        "owned_actual:",
        f"movzx r10d, WORD PTR [rdx+{fields['JSFunctionBytecode.arg_count']}]",
        "cmp eax, r10d",
        "cmovb eax, r10d",
        f"movzx r10d, WORD PTR [rdx+{fields['JSFunctionBytecode.var_count']}]",
        "add eax, r10d",
        f"movzx r10d, WORD PTR [rdx+{fields['JSFunctionBytecode.stack_size']}]",
        "add eax, r10d",
        "shl rax, 4",
        "add rax, 128",
        f"movzx r10d, WORD PTR [rdx+{fields['JSFunctionBytecode.var_ref_count']}]",
        "shl r10, 3",
        "add r10, 15",
        "and r10, -16",
        "add rax, r10",
        "mov QWORD PTR [rsp+24], rax",
        "add rax, 80",
        "mov r9, QWORD PTR [rcx+8]",
        "mov r10, QWORD PTR [r9+8]",
        "sub r10, QWORD PTR [r9+16]",
        "cmp rax, r10",
        "ja " + OLD,
        "add rax, QWORD PTR [rcx+32]",
        "jc " + OLD,
        "add rax, 5280",
        "jc " + OLD,
        "mov r10, rsp",
        "sub r10, rax",
        "jc " + OLD,
        f"cmp r10, QWORD PTR [rcx+{limit}]",
        "jb " + OLD,
        # Preserve H's caller and original .call wrapper realm poll order.
        "mov r9, QWORD PTR [rcx]",
        "mov r9, QWORD PTR [r9+80]",
        f"mov r9, QWORD PTR [r9+{fields['JSFunctionBytecode.realm']}]",
        "mov r10, QWORD PTR [r8-16]",
        f"mov r10, QWORD PTR [r10+{fields['JSObject.u.cfunc.realm']}]",
        "cmp r9, r10",
        "jne owned_two_realms",
        f"cmp DWORD PTR [r9+{fields['JSContext.interrupt_counter']}], 2",
        "jle " + OLD,
        "jmp owned_admitted",
        "owned_two_realms:",
        f"cmp DWORD PTR [r9+{fields['JSContext.interrupt_counter']}], 1",
        "jle " + OLD,
        f"cmp DWORD PTR [r10+{fields['JSContext.interrupt_counter']}], 1",
        "jle " + OLD,
        "owned_admitted:",
        # No C, allocation, observer or fallback after admission.
        f"dec DWORD PTR [r9+{fields['JSContext.interrupt_counter']}]",
        f"dec DWORD PTR [r10+{fields['JSContext.interrupt_counter']}]",
        "mov r9, QWORD PTR [rcx+8]",
        "mov r10, QWORD PTR [r9+16]",
        "add r10, QWORD PTR [r9+24]",
        "mov r9, r10",
        "mov rdx, QWORD PTR [rsp+32]",
        "movdqu xmm0, XMMWORD PTR [r8-32]",
        "movdqu XMMWORD PTR [r9+8], xmm0",
        "mov QWORD PTR [r9+80], rdx",
        "mov r10, QWORD PTR [rcx+8]",
        "mov QWORD PTR [r9+112], r10",
        "mov rax, QWORD PTR [rsp+24]",
        "mov DWORD PTR [r9+120], eax",
        "lea r10, [r9+rax]",
        "mov QWORD PTR [r9], r10",
        "xor eax, eax",
        "test r11d, r11d",
        "jz owned_count",
        "lea eax, [r11-1]",
        "owned_count:",
        f"movzx r10d, WORD PTR [rdx+{fields['JSFunctionBytecode.arg_count']}]",
        "cmp eax, r10d",
        "cmovb eax, r10d",
        "mov WORD PTR [r9+58], ax",
        "mov WORD PTR [r9+124], ax",
        "mov WORD PTR [r9+126], 0",
        "shl rax, 4",
        "lea r10, [r9+128]",
        "mov QWORD PTR [r9+24], r10",
        "add rax, r10",
        "mov QWORD PTR [r9+32], rax",
        f"movzx r10d, WORD PTR [rdx+{fields['JSFunctionBytecode.var_count']}]",
        "shl r10, 4",
        "add r10, rax",
        "mov QWORD PTR [r9+64], r10",
        "mov QWORD PTR [r9+104], r10",
        f"movzx eax, WORD PTR [rdx+{fields['JSFunctionBytecode.var_ref_count']}]",
        "mov WORD PTR [r9+56], ax",
        "mov QWORD PTR [r9+40], 0",
        "test eax, eax",
        "jz owned_refs_done",
        f"movzx r11d, WORD PTR [rdx+{fields['JSFunctionBytecode.stack_size']}]",
        "shl r11, 4",
        "add r10, r11",
        "mov QWORD PTR [r9+40], r10",
        "owned_zero_refs:",
        "mov QWORD PTR [r10], 0",
        "add r10, 8",
        "dec eax",
        "jnz owned_zero_refs",
        "owned_refs_done:",
        "mov QWORD PTR [r9+48], 0",
        "mov QWORD PTR [r9+72], 0",
        f"movzx eax, BYTE PTR [rdx+{strict_byte}]",
        "and eax, 1",
        "mov BYTE PTR [r9+60], al",
        "mov BYTE PTR [r9+61], 0",
        "mov WORD PTR [r9+62], 2",
        "mov r11d, DWORD PTR [rsp+16]",
        "test r11d, r11d",
        "jz owned_undefined_this",
        "movdqu xmm0, XMMWORD PTR [r8]",
        "movdqu XMMWORD PTR [r9+88], xmm0",
        "jmp owned_this_done",
        "owned_undefined_this:",
        "mov QWORD PTR [r9+88], 0",
        "mov QWORD PTR [r9+96], 3",
        "owned_this_done:",
        # Exact js_dup: tags -9..-1 and RC at allocator user_data minus4.
        "mov r10, QWORD PTR [r9+24]",
        "test r11d, r11d",
        "jz owned_pad_start",
        "dec r11d",
        "add r8, 16",
        "test r11d, r11d",
        "jz owned_pad_start",
        "owned_copy_args:",
        "movdqu xmm0, XMMWORD PTR [r8]",
        "movdqu XMMWORD PTR [r10], xmm0",
        "cmp DWORD PTR [r8+8], -9",
        "jb owned_no_dup",
        "mov rax, QWORD PTR [r8]",
        f"inc DWORD PTR [rax{abi_constants(abi)['QJS_ABI_REF_COUNT_OFFSET']:+d}]",
        "owned_no_dup:",
        "add r8, 16",
        "add r10, 16",
        "dec r11d",
        "jnz owned_copy_args",
        "owned_pad_start:",
        "cmp r10, QWORD PTR [r9+32]",
        "je owned_vars_start",
        "owned_pad_args:",
        "mov QWORD PTR [r10], 0",
        "mov QWORD PTR [r10+8], 3",
        "add r10, 16",
        "cmp r10, QWORD PTR [r9+32]",
        "jne owned_pad_args",
        "owned_vars_start:",
        "cmp r10, QWORD PTR [r9+64]",
        "je owned_vars_done",
        "owned_zero_vars:",
        "mov QWORD PTR [r10], 0",
        "mov QWORD PTR [r10+8], 3",
        "add r10, 16",
        "cmp r10, QWORD PTR [r9+64]",
        "jne owned_zero_vars",
        "owned_vars_done:",
        # Original80-byte logical C SF; zero argc borrows immutable child.this_value.
        "mov r8, QWORD PTR [rsp+8]",
        "mov r11d, DWORD PTR [rsp+16]",
        "mov r10, QWORD PTR [rsp+24]",
        "add r10, r9",
        "mov rax, QWORD PTR [rcx]",
        "mov QWORD PTR [r10], rax",
        "movdqu xmm0, XMMWORD PTR [r8-16]",
        "movdqu XMMWORD PTR [r10+8], xmm0",
        "mov QWORD PTR [r10+24], r8",
        "test r11d, r11d",
        "jnz owned_logical_argc",
        "lea rax, [r9+88]",
        "mov QWORD PTR [r10+24], rax",
        "inc r11d",
        "owned_logical_argc:",
        "mov WORD PTR [r10+58], r11w",
        "mov WORD PTR [r10+56], 0",
        "mov WORD PTR [r10+60], 0",
        "mov WORD PTR [r10+62], 50944",
        "mov QWORD PTR [r10+32], 0",
        "mov QWORD PTR [r10+40], 0",
        "mov QWORD PTR [r10+48], 0",
        "mov QWORD PTR [r10+64], 0",
        "mov QWORD PTR [r10+72], 0",
        # Complete parent roots/continuation and the whole child before publication.
        "mov r10, QWORD PTR [rcx]",
        "mov r8, QWORD PTR [rcx+24]",
        "mov QWORD PTR [r10+64], r8",
        "mov QWORD PTR [r10+104], r8",
        "mov r8, QWORD PTR [rcx+16]",
        "mov eax, DWORD PTR [rsp+16]",
        "add eax, 2",
        f"cmp BYTE PTR [r8], {ids['tail_call_method']}",
        "jne owned_not_tail",
        "or eax, 32768",
        "owned_not_tail:",
        "mov WORD PTR [r10+126], ax",
        "add r8, 3",
        "mov QWORD PTR [r10+48], r8",
        "mov rax, QWORD PTR [rsp+24]",
        "add rax, 80",
        "mov r10, QWORD PTR [rcx+8]",
        "add QWORD PTR [r10+16], rax",
        "add QWORD PTR [rcx+32], rax",
    ]
    if diagnostics:
        g += [
            "inc QWORD PTR [rcx+88]",
            "mov eax, DWORD PTR [rsp+16]",
            "test eax, eax",
            "jz owned_diag_copied",
            "dec eax",
            "owned_diag_copied:",
            "add QWORD PTR [rcx+2216], rax",
            f"cmp ax, WORD PTR [rdx+{fields['JSFunctionBytecode.arg_count']}]",
            "jae owned_diag_arity",
            "inc QWORD PTR [rcx+96]",
            "owned_diag_arity:",
            "inc DWORD PTR [rcx+128]",
            "mov eax, DWORD PTR [rcx+128]",
            "cmp eax, DWORD PTR [rcx+132]",
            "jbe owned_diag_depth",
            "mov DWORD PTR [rcx+132], eax",
            "owned_diag_depth:",
            "mov rax, QWORD PTR [rcx+32]",
            "cmp rax, QWORD PTR [rcx+120]",
            "jbe owned_diag_peak",
            "mov QWORD PTR [rcx+120], rax",
            "owned_diag_peak:",
        ]
    g += [
        "owned_commit:",
        "mov QWORD PTR [rcx], r9",
        f"mov rax, QWORD PTR [rdx+{fields['JSFunctionBytecode.byte_code_buf']}]",
        "mov QWORD PTR [rcx+16], rax",
        "mov rax, QWORD PTR [r9+64]",
        "mov QWORD PTR [rcx+24], rax",
        "mov r10, QWORD PTR [rcx+56]",
        f"mov QWORD PTR [r10+{fields['JSRuntime.current_stack_frame']}], r9",
        "mov eax, 1",
        "ret",
    ]
    return g


def compile_extra(source, build, compiler, msvc, diagnostics):
    M = module(source, "atod")

    def guard(src, path):
        text = _frame_source_text(src, "quickjs-interpreter-loop.h")
        types = []
        for tag in ("JSFrameSegment", "JSFrame", "JSFrameCallSite"):
            found = re.findall(r"typedef struct " + tag + r" \{.*?\} " + tag + ";", text, re.S)
            assert len(found) == 1
            types.append(found[0])
        body = (
            '#include "quickjs-interpreter-private.h"\n'
            + "\n".join(types)
            + '\n#include "src/common/call/quickjs-interpreter-register.h"\n'
        )
        fields = {
            "JSStackFrame.prev_frame": 0,
            "JSStackFrame.cur_func": 8,
            "JSStackFrame.arg_buf": 24,
            "JSStackFrame.var_buf": 32,
            "JSStackFrame.var_refs": 40,
            "JSStackFrame.cur_pc": 48,
            "JSStackFrame.var_ref_count": 56,
            "JSStackFrame.arg_count": 58,
            "JSStackFrame.is_strict_mode": 60,
            "JSStackFrame.is_constructor": 61,
            "JSStackFrame.cur_sp": 64,
            "JSStackFrame.cur_gc_obj": 72,
            "JSFrame.bytecode": 80,
            "JSFrame.this_value": 88,
            "JSFrame.saved_sp": 104,
            "JSFrame.segment": 112,
            "JSFrame.frame_bytes": 120,
            "JSFrame.owned_args": 124,
            "JSFrame.pending": 126,
            "JSFrameSegment.capacity": 8,
            "JSFrameSegment.used": 16,
            "JSFrameSegment.data": 24,
            "JSFunctionBytecode.byte_code_buf": 24,
            "JSFunctionBytecode.arg_count": 56,
            "JSFunctionBytecode.var_count": 58,
            "JSFunctionBytecode.stack_size": 62,
            "JSFunctionBytecode.var_ref_count": 64,
            "JSFunctionBytecode.closure_var_count": 66,
            "JSFunctionBytecode.realm": 72,
            "JSObject.u.cfunc.realm": 48,
            "JSRuntime.current_stack_frame": 1264,
            "JSContext.interrupt_counter": 556,
            "JSFrameRegisterState.used_bytes": 32,
            "JSFrameRegisterState.rt": 56,
            "JSFrameRegisterState.borrowed_values": 104,
            "JSFrameRegisterState.windows": 112,
            "JSFrameRegisterState.native_stack_limit": 2312 if diagnostics else 72,
        }
        if diagnostics:
            fields.update(
                {
                    "JSFrameRegisterState.pushes": 88,
                    "JSFrameRegisterState.copied_values": 2216,
                    "JSFrameRegisterState.arities": 96,
                    "JSFrameRegisterState.peak_bytes": 120,
                    "JSFrameRegisterState.depth": 128,
                    "JSFrameRegisterState.max_depth": 132,
                }
            )
        layout = load_layout(src)
        if layout["reference_count_model"] == "inline-header":
            del fields["JSStackFrame.is_constructor"]
            del fields["JSStackFrame.cur_gc_obj"]
        for field in fields:
            if field in layout["offsets"]:
                fields[field] = layout["offsets"][field]
        for field, offset in fields.items():
            typ, member = field.split(".", 1)
            body += f'_Static_assert(offsetof({typ},{member})=={offset},"{field}");\n'
        body += '_Static_assert(sizeof(JSFrame)==128 && sizeof(JSStackFrame)==QJS_ABI_SIZE_JSStackFrame && sizeof(JSValue)==16 && FRAME_STACK_CORO_OFFSET_VALID,"owned frames");\n'
        body += '_Static_assert(JS_TAG_FIRST==-9 && JS_TAG_UNDEFINED==3,"exact js_dup tags");\n'
        body += '#if QJS_ABI_HAS_PREFIX_RC\n_Static_assert(offsetof(JSMallocBlockHeader,ref_count)-offsetof(JSMallocBlockHeader,user_data)==QJS_ABI_REF_COUNT_OFFSET,"prefix js_dup header");\n#else\n_Static_assert(offsetof(JSGCObjectHeader,ref_count)==QJS_ABI_REF_COUNT_OFFSET,"inline js_dup header");\n#endif\n'
        path.write_text(body, encoding="utf-8")

    M.compile_extra(
        source,
        build,
        _frame_generated_file(build, "quickjs-interpreter-call-forward-owned-abi.obj"),
        generator=guard,
        filename="quickjs-interpreter-call-forward-owned-abi.c",
        late_name=".qjzzva",
    )

    def config(src, path):
        attr = "extern" if msvc else '__attribute__((section(".qjslcm$zzforwardowned"),used))'
        text = "#include <stdlib.h>\n#ifdef _MSC_VER\n#include <intrin.h>\n#endif\n"
        text += (
            attr + " unsigned char JS_FrameCallForwardOwnedControl" + (";\n" if msvc else "=255;\n")
        )
        text += "extern void JS_FrameCallForwardOwnedPublish(unsigned char);\nextern void JS_FrameCallForwardBorrowPublish(unsigned char);\nextern void JS_FrameCallForwardBorrowMissingPublish(unsigned char);\nextern int JS_FrameVarargsForwardTry(void *);\n"
        text += (
            '__declspec(code_seg(".qjzzva")) __declspec(noinline)'
            if msvc
            else '__attribute__((section(".qjzzva"),noipa))'
        )
        text += """
int JS_FrameCallForwardOwnedCold(void *state)
{
    unsigned char mode=getenv("QJS_DISABLE_FRAME_CALL_FORWARD_OWNED")?2:1;
    JS_FrameCallForwardOwnedPublish(mode);
    JS_FrameCallForwardBorrowPublish(getenv("QJS_DISABLE_FRAME_CALL_FORWARD_BORROW")?2:1);
    JS_FrameCallForwardBorrowMissingPublish(getenv("QJS_DISABLE_FRAME_CALL_FORWARD_BORROW_MISSING")?2:1);
    return JS_FrameVarargsForwardTry(state);
}
"""
        path.write_text(text, encoding="utf-8")

    M.compile_extra(
        source,
        build,
        _frame_generated_file(build, "quickjs-interpreter-call-forward-owned-config.obj"),
        generator=config,
        filename="quickjs-interpreter-call-forward-owned-config.c",
        late_name=".qjzzva",
    )

    def captured(src, path):
        text = '#include "quickjs-interpreter-private.h"\n'
        text += '#ifdef _MSC_VER\n#define FRAME_CODE __declspec(code_seg(".qjzzva")) __declspec(noinline)\n#else\n#define FRAME_CODE __attribute__((section(".qjzzva"),noipa))\n#endif\n'
        text += CAPTURED_PROOF
        text += '\nstatic const uint8_t captured_sizes[] = {\n#define DEF(id,size,npop,npush,fmt) size,\n#define def(id,size,npop,npush,fmt)\n#include "quickjs-opcode.h"\n};\n'
        text += r"""
_Static_assert(offsetof(JSFunctionBytecode,byte_code_buf)==QJS_ABI_OFF_JSFunctionBytecode_byte_code_buf,"capture kind before code pointer");
extern void JS_FrameJSCapturedPublish(unsigned char);
FRAME_CODE void JS_FrameCapturedReadonlyClassify(JSFunctionBytecode *b)
{
    unsigned char *kind=(unsigned char *)b+QJS_ABI_OFF_JSFunctionBytecode_byte_code_buf-1;
    if ((*kind&7)==5 && getenv("QJS_DISABLE_FRAME_CAPTURED_READONLY")==NULL &&
        js_frame_captured_readonly(b,captured_sizes)) {
        JS_FrameJSCapturedPublish(getenv("QJS_DISABLE_FRAME_JS_CAPTURED")?2:1);
        *kind|=2;
    }
}
"""
        path.write_text(text, encoding="utf-8")

    M.compile_extra(
        source,
        build,
        _frame_generated_file(build, "quickjs-interpreter-captured-readonly.obj"),
        generator=captured,
        filename="quickjs-interpreter-captured-readonly.c",
        late_name=".qjzzva",
    )
    module(source, "js-captured").compile_extra(source, build, compiler, msvc, diagnostics)
    module(source, "call-forward-borrow").compile_extra(source, build, compiler, msvc, diagnostics)
    body = lines(source, diagnostics)
    if msvc:
        text = [
            "OPTION CASEMAP:NONE",
            "OPTION DOTNAME",
            "EXTERN " + OLD + ":PROC",
            "EXTERN JS_FrameCallPrepareOne:PROC",
            "EXTERN JS_FrameCallForwardOwnedCold:PROC",
            "EXTERN JS_FrameCallForwardOwnedControl:BYTE",
            "EXTERN JS_FrameCallForwardBorrowTry:PROC",
            ".qjzzva SEGMENT ALIGN(16) READONLY 'CODE'",
            "PUBLIC " + NAME + ", " + NAME + "_end",
            NAME + " PROC",
        ]
        for line in body:
            if line == GENERAL + ":":
                text += ["PUBLIC " + GENERAL, GENERAL + " LABEL BYTE"]
                continue
            if line == "JS_FrameCallForwardOwnedCopy:":
                text += [
                    "PUBLIC JS_FrameCallForwardOwnedCopy",
                    "JS_FrameCallForwardOwnedCopy LABEL BYTE",
                ]
                continue
            line = re.sub(r"\[rip\+([^\]]+)\]", r"\1", line)
            if re.fullmatch(r"j\w+ \w+", line):
                op, target = line.split()
                line = op + " NEAR PTR " + target
            text.append(line)
        text += [
            NAME + "_end LABEL BYTE",
            NAME + " ENDP",
            "ALIGN 16",
            "PUBLIC " + PUBLISH + ", " + PUBLISH + "_end",
            PUBLISH + " PROC",
            "lea rax, JS_FrameCallForwardOwnedControl",
            "xchg BYTE PTR [rax], cl",
            "ret",
            PUBLISH + "_end LABEL BYTE",
            PUBLISH + " ENDP",
            "ALIGN 4",
            NAME + "_unwind LABEL BYTE",
            "DB 1,0,0,0",
            ".qjzzva ENDS",
            ".pdata$zzzzzznullfast SEGMENT ALIGN(4) READONLY 'DATA'",
            "DD IMAGEREL " + NAME + ", IMAGEREL " + NAME + "_end, IMAGEREL " + NAME + "_unwind",
            "DD IMAGEREL "
            + PUBLISH
            + ", IMAGEREL "
            + PUBLISH
            + "_end, IMAGEREL "
            + NAME
            + "_unwind",
            ".pdata$zzzzzznullfast ENDS",
            "END",
        ]
        path = _frame_generated_file(build, "quickjs-interpreter-call-forward-owned.asm")
        obj = path.with_suffix(".obj")
        command = [compiler.with_name("ml64.exe"), "/nologo", "/c", "/Fo" + str(obj), path]
    else:
        text = [
            ".intel_syntax noprefix",
            '.section .qjzzva,"xr"',
            ".p2align 4",
            ".globl "
            + NAME
            + ", "
            + NAME
            + "_end"
            + ", "
            + GENERAL
            + ", JS_FrameCallForwardOwnedCopy",
            ".def " + NAME + "; .scl 2; .type 32; .endef",
            NAME + ":",
            *body,
            NAME + "_end:",
            ".p2align 4",
            ".globl " + PUBLISH + ", " + PUBLISH + "_end",
            ".def " + PUBLISH + "; .scl 2; .type 32; .endef",
            PUBLISH + ":",
            "lea rax, [rip+JS_FrameCallForwardOwnedControl]",
            "xchg BYTE PTR [rax], cl",
            "ret",
            PUBLISH + "_end:",
            ".p2align 2",
            NAME + "_unwind:",
            ".byte 1,0,0,0",
            '.section .pdata$zzzzzznullfast,"dr"',
            ".p2align 2",
            ".rva " + NAME + "," + NAME + "_end," + NAME + "_unwind",
            ".rva " + PUBLISH + "," + PUBLISH + "_end," + NAME + "_unwind",
        ]
        path = _frame_generated_file(build, "quickjs-interpreter-call-forward-owned.S")
        obj = path.with_suffix(".obj")
        command = [compiler, "-c", "-g0", path, "-o", obj]
    path.write_text("\n".join(text) + "\n", encoding="ascii")
    command = list(map(str, command))
    result = subprocess.run(command, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
    obj.with_suffix(".log").write_bytes(result.stdout + result.stderr)
    assert result.returncode == 0, (
        command,
        (result.stdout + result.stderr).decode(errors="replace")[-2500:],
    )
    obj.with_suffix(".compile.json").write_text(
        json.dumps(
            dict(
                status="passed",
                command=command,
                object_sha256=sha(obj),
                source_sha256=sha(path),
                diagnostics=diagnostics,
                protocol="Ordinary Win64 leaf, no RSP/nonvolatile write. General validated owned child, one logical C SF, deferred quota, H return/unwind.",
            ),
            indent=2,
        )
        + "\n"
    )


def append_module(source, build, output, msvc, code_group, prefix, owner, merge):
    merge.append(
        output,
        _frame_generated_file(build, "quickjs-interpreter-call-forward-owned.obj"),
        NAME,
        "forward-owned-asm",
        keep_all=True,
        code_input=".qjzzva",
        code_output=code_group if msvc else code_group + "$F",
        pdata_output=prefix + "1",
        base_owner=owner,
        baseline_sections=(),
    )
    merge.append(
        output,
        _frame_generated_file(build, "quickjs-interpreter-call-forward-owned-config.obj"),
        "JS_FrameCallForwardOwnedCold",
        "forward-owned-config",
        keep_all=True,
        code_input=".qjzzva",
        code_output=code_group if msvc else code_group + "$G",
        pdata_output=prefix + "1",
        metadata_inputs=(".voltbl",) if msvc else (),
        writable_metadata_inputs=() if msvc else (".qjslcm$zzforwardowned",),
        base_owner=owner,
        baseline_sections=(),
    )


def append_control(source, build, path, raw):
    return module(source, "call-forward-native").append_control(
        source,
        build,
        path,
        raw,
        name="JS_FrameCallForwardOwnedControl",
        previous="JS_FrameCallForwardNativeControl",
        original_bytes=61,
    )


def append_captured(source, build, output, msvc, code_group, prefix, owner, merge):
    # The last contribution: keep every pre-existing late native prefix first.
    merge.append(
        output,
        _frame_generated_file(build, "quickjs-interpreter-captured-readonly.obj"),
        "JS_FrameCapturedReadonlyClassify",
        "captured-readonly-cold",
        keep_all=True,
        code_input=".qjzzva",
        code_output=code_group if msvc else code_group + "$J",
        pdata_output=prefix + "1",
        metadata_inputs=(".voltbl",) if msvc else (),
        base_owner=owner,
        baseline_sections=(),
    )

    module(source, "js-captured").append_module(
        source, build, output, msvc, code_group, prefix, owner, merge
    )
