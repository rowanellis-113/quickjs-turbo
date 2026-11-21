"""Deterministic ELF/GCC -> Mach-O/Clang adapter for generated x86-64 SysV sources."""

import hashlib
import json
from pathlib import Path
import re

ASM_SECTION_MAP = {
    ".text.qjs_linux_vm": "__TEXT,__qjs_vm,regular,pure_instructions",
    ".text.qjs_linux_cold": "__TEXT,__qjs_cold,regular,pure_instructions",
    ".qjs_linux_slots": "__TEXT,__qjs_slots,regular,pure_instructions",
    ".qjs_linux_stack": "__TEXT,__qjs_stack,regular,pure_instructions",
    ".text.qjs_linux_forward": "__TEXT,__qjs_fwd,regular,pure_instructions",
    ".text.qjs_linux_publish_proxy": "__TEXT,__qjs_pprx,regular,pure_instructions",
    ".text.qjs_linux_host": "__TEXT,__qjs_host,regular,pure_instructions",
    ".text.qjs_linux_c_invoke": "__TEXT,__qjs_cinv,regular,pure_instructions",
    ".text.qjs_linux_c_special": "__TEXT,__qjs_cspc,regular,pure_instructions",
    ".text.qjs_linux_builtin_entry": "__TEXT,__qjs_bltn,regular,pure_instructions",
    ".text.qjs_linux_comparison_leaf": "__TEXT,__qjs_cmp,regular,pure_instructions",
    ".text.qjs_linux_bigint_release": "__TEXT,__qjs_big,regular,pure_instructions",
    ".text.qjs_linux_array_own": "__TEXT,__qjs_arow,regular,pure_instructions",
    ".text.qjs_linux_slow_selector": "__TEXT,__qjs_slws,regular,pure_instructions",
    ".text.qjs_linux_bridges": "__TEXT,__qjs_brdg,regular,pure_instructions",
    ".text.qjs_linux_entry": "__TEXT,__qjs_entr,regular,pure_instructions",
    ".data.rel.ro.local.qjs_linux_dispatch": "__DATA_CONST,__const",
    ".data.rel.ro.local.qjs_linux_publish": "__DATA_CONST,__const",
    ".qjs_linux_slots_ro": "__TEXT,__const",
    ".rodata.qjs_linux_comparison": "__TEXT,__const",
    ".rodata.qjs_linux_add_local": "__TEXT,__const",
    ".data.qjs_linux_comparison": "__DATA,__data",
    ".data.qjs_linux_global_arithmetic": "__DATA,__data",
}

DROP_SECTIONS = frozenset({".note.GNU-stack", ".note.gnu.property"})

C_SECTION_RE = re.compile(r'section\("([^"]+)"\)')
ATTR_BLOCK_RE = re.compile(r"__attribute__\(\(([^()]*(?:\([^()]*\)[^()]*)*)\)\)")
ALIAS_DECL_RE = re.compile(
    r'extern\s+__typeof__\((\w+)\)\s+(\w+)\s*\n?\s*__attribute__\(\(\s*alias\("(\w+)"\)\s*,\s*visibility\("hidden"\)\s*\)\)\s*;'
)
LEAQ_RIP_RE = re.compile(r'(__asm__[^(]*\("lea[q]?\s+)([A-Za-z_][A-Za-z0-9_]*)(\(%%rip\))')
INCLUDE_ANY_RE = re.compile(r'^(\s*#include\s+")([^"\n]+)(")', re.M)
MACRO_SRC_RE = re.compile(r'^(\s*#define\s+\w+\s+")(src/[^"\n]+)(")', re.M)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def map_c_section(name):
    if "," in name:
        return name
    if name == "qjs_virtual_text":
        return "__TEXT,__qjs_varg"
    if name.startswith(
        (
            ".text.",
            ".text$",
            ".qjsvm",
            ".qjsprop",
            ".qjslng",
            ".qjscmp$C",
            ".qjscmp$S",
            ".qjssrc",
            ".qjsleaf",
            ".qjsjson",
            ".qjscbck",
            ".qjscbwr",
            ".qzzec",
        )
    ):
        return "__TEXT,__qjs_text"
    if name.startswith((".rodata.", ".qjsro")):
        return "__TEXT,__const"
    if name.startswith(
        (
            ".data.",
            ".data$",
            ".bss.",
            ".qjscmp$D",
            ".qjsacm",
            ".qjscbmt",
            ".qjsem",
            ".qjslfm",
            ".qjspmet",
            ".qjsrfm",
            ".qjsrmet",
            ".qjzzpm",
            ".qzzem",
        )
    ):
        return "__DATA,__qjs_data"
    raise ValueError("Unmapped ELF C section name for Mach-O: " + name)


def _rewrite_attr_block(match):
    inner = match.group(1)
    inner = C_SECTION_RE.sub(lambda m: f'section("{map_c_section(m.group(1))}")', inner)
    inner = re.sub(r"\bnoipa\b", "noinline", inner)
    return f"__attribute__(({inner}))"


def _rewrite_alias(match):
    typeof_sym, alias_name, target_sym = match.group(1), match.group(2), match.group(3)
    if typeof_sym != target_sym:
        raise ValueError(f"Unexpected alias target mismatch: {typeof_sym} vs {target_sym}")
    return (
        f'extern __typeof__({typeof_sym}) {alias_name} __attribute__((visibility("hidden")));\n'
        f'__asm__(".globl _{alias_name}\\n.private_extern _{alias_name}\\n'
        f'_{alias_name} = _{target_sym}\\n");'
    )


def adapt_c_text(text, *, is_foundation=False, is_arguments=False):
    text = ALIAS_DECL_RE.sub(_rewrite_alias, text)
    text = ATTR_BLOCK_RE.sub(_rewrite_attr_block, text)
    text = LEAQ_RIP_RE.sub(lambda m: f"{m.group(1)}_{m.group(2)}{m.group(3)}", text)
    text = text.replace(
        "defined(__linux__) && defined(__x86_64__)",
        "(defined(__linux__) || defined(__APPLE__)) && defined(__x86_64__)",
    )
    text = text.replace(
        "__atomic_load_n(&JS_FrameSlowDirectData.mode, __ATOMIC_RELAXED)",
        "atomic_load_explicit(&JS_FrameSlowDirectData.mode, memory_order_relaxed)",
    )
    text = text.replace("bigint_done:\n", "bigint_done:;\n")
    # Clang lowers (double)(uint64_t) on x86-64 using an SSE2 subpd/addsd bias
    # sequence whose 0-0 subtraction yields -0.0 under FE_DOWNWARD. Both
    # mantissa (<= 10^15 - 1) and scale (<= 10^15) fit in int64_t and lower to
    # exact single-instruction cvtsi2sdq across all IEEE-754 rounding modes.
    text = text.replace("result.d = (double)mantissa;", "result.d = (double)(int64_t)mantissa;")
    text = text.replace("result.d /= (double)scale;", "result.d /= (double)(int64_t)scale;")
    if is_foundation:
        # Expose js_function_apply and js_function_call with hidden linkage so
        # Mach-O symbol aliases (_qjs_linux_core_js_function_{apply,call}) resolve
        # to the exact same addresses without GCC __attribute__((alias(...))).
        for fn in ("js_function_apply", "js_function_call"):
            old = f"static JSValue {fn}("
            if text.count(old) < 1:
                raise ValueError("Expected static definition for Mach-O alias target: " + fn)
            text = text.replace(
                old,
                f'__attribute__((used, noinline, visibility("hidden"))) JSValue {fn}(',
            )
    if is_arguments:
        old = "static FRAME_CODE bool js_frame_arguments_push("
        if text.count(old) != 1:
            raise ValueError("Expected static definition for js_frame_arguments_push")
        text = text.replace(
            old,
            '__attribute__((used, noinline, visibility("hidden"))) FRAME_CODE bool js_frame_arguments_push(',
            1,
        )
    return text


def adapt_c_tree(source, output):
    """Adapt generated C/headers and transitively copy+adapt included ELF .inc files."""
    inc_root = output / "macos-inc"
    inc_root.mkdir(parents=True, exist_ok=True)
    adapted_inc = {}

    def adapt_included_rel(rel_path):
        if rel_path in adapted_inc:
            return adapted_inc[rel_path]
        src_path = source / rel_path
        if not src_path.is_file():
            return None
        raw = src_path.read_text(encoding="utf-8")
        # Reserve slot before recursing to avoid cycles
        adapted_inc[rel_path] = None
        transformed = adapt_c_text(raw)
        transformed = _rewrite_includes(transformed, src_path.parent)
        if transformed == raw:
            return None
        out_rel = "macos-inc/" + rel_path
        adapted_inc[rel_path] = out_rel
        dest = output / out_rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(transformed, encoding="utf-8")
        return out_rel

    def _rewrite_includes(text, current_dir):
        def repl_include(m):
            inc = m.group(2)
            if inc.startswith("src/"):
                new_rel = adapt_included_rel(inc)
                return f"{m.group(1)}{new_rel or inc}{m.group(3)}"
            if current_dir is not None:
                sibling = (current_dir / inc).resolve()
                if sibling.is_file() and sibling.is_relative_to(source):
                    rel = sibling.relative_to(source).as_posix()
                    new_rel = adapt_included_rel(rel)
                    return f"{m.group(1)}{new_rel or rel}{m.group(3)}"
            return m.group(0)

        def repl_macro(m):
            new_rel = adapt_included_rel(m.group(2))
            if new_rel:
                return f"{m.group(1)}{new_rel}{m.group(3)}"
            return m.group(0)

        text = INCLUDE_ANY_RE.sub(repl_include, text)
        text = MACRO_SRC_RE.sub(repl_macro, text)
        return text

    adapted_files = {}
    for path in sorted(output.iterdir()):
        if not path.is_file() or path.suffix not in (".c", ".h"):
            continue
        raw = path.read_text(encoding="utf-8")
        new_text = adapt_c_text(
            raw,
            is_foundation=(path.name == "quickjs-linux-foundation.c"),
            is_arguments=(path.name == "quickjs-linux-arguments.h"),
        )
        new_text = _rewrite_includes(new_text, None)
        if new_text != raw:
            path.write_text(new_text, encoding="utf-8")
        adapted_files[path.name] = sha(path)

    # Also adapt src/x86/linux/integer-expression.c into generated output
    int_expr_src = source / "src/x86/linux/integer-expression.c"
    int_expr_dst = output / "quickjs-macos-integer-expression.c"
    int_expr_dst.write_text(
        adapt_c_text(int_expr_src.read_text(encoding="utf-8")), encoding="utf-8"
    )
    adapted_files[int_expr_dst.name] = sha(int_expr_dst)
    return adapted_files, sorted(k for k, v in adapted_inc.items() if v is not None)


def _scan_asm_symbols(text):
    """Collect defined labels, global/hidden symbols, and referenced symbols in one .S file."""
    defined = set()
    extern_or_global = set()
    referenced = set()
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith(("/*", "*", "//", "#")):
            continue
        m = re.fullmatch(r"(\.?[A-Za-z_]\w*):", line)
        if m:
            defined.add(m.group(1))
            continue
        if line.startswith(".globl "):
            for sym in line[7:].split(","):
                s = sym.strip()
                if s:
                    extern_or_global.add(s)
            continue
        if line.startswith(".hidden "):
            for sym in line[8:].split(","):
                s = sym.strip()
                if s:
                    extern_or_global.add(s)
            continue
        if line.startswith(".quad "):
            for item in line[6:].split(","):
                tok = item.strip()
                if re.fullmatch(r"[A-Za-z_]\w*", tok):
                    referenced.add(tok)
            continue
        m = re.fullmatch(r"(?:call|jmp|j\w+)\s+([A-Za-z_]\w*)(?:@PLT)?", line)
        if m:
            referenced.add(m.group(1))
            continue
        for m in re.finditer(r"\[rip\+([A-Za-z_]\w*)(?:\+\d+)?\]", line):
            referenced.add(m.group(1))
    undefined = referenced - defined
    return defined, extern_or_global, undefined


def adapt_asm_files(output):
    """Translate generated ELF x86-64 Intel-syntax assembly files to Mach-O."""
    names = ("quickjs-linux-vm.S", "quickjs-linux-bridges.S", "quickjs-linux-entry.S")
    texts = {n: (output / n).read_text(encoding="utf-8") for n in names}

    # Gather every symbol that is global, hidden, or cross-TU referenced across the 3 files.
    prefixed = set()
    defined_per_file = {}
    for n, text in texts.items():
        defined, ext, undef = _scan_asm_symbols(text)
        defined_per_file[n] = defined
        prefixed |= ext | undef

    # Never prefix x86 registers or assembler keywords (defensive guard).
    registers = {
        "rax",
        "rbx",
        "rcx",
        "rdx",
        "rsi",
        "rdi",
        "rbp",
        "rsp",
        "r8",
        "r9",
        "r10",
        "r11",
        "r12",
        "r13",
        "r14",
        "r15",
        "eax",
        "ebx",
        "ecx",
        "edx",
        "esi",
        "edi",
        "ebp",
        "esp",
        "r8d",
        "r9d",
        "r10d",
        "r11d",
        "r12d",
        "r13d",
        "r14d",
        "r15d",
        "ax",
        "bx",
        "cx",
        "dx",
        "si",
        "di",
        "bp",
        "sp",
        "al",
        "bl",
        "cl",
        "dl",
        "sil",
        "dil",
        "bpl",
        "spl",
        "r8b",
        "r9b",
        "r10b",
        "r11b",
        "r12b",
        "r13b",
        "r14b",
        "r15b",
        "rip",
    }
    prefixed -= registers

    def collect_cfi_locals(text, defined):
        """Collect TU-local labels inside .cfi_startproc..endproc blocks.

        Mach-O splits linker atoms at every non-'L' label, which breaks
        DW_CFA_advance_loc expressions across internal labels inside a CFI
        procedure. Renaming those TU-local labels to 'L_<name>' keeps each
        procedure a single Mach-O atom with valid DWARF EH frame FDEs.
        """
        locals_in_cfi = set()
        in_cfi = False
        for raw in text.splitlines():
            line = raw.strip()
            if line.startswith(".cfi_startproc"):
                in_cfi = True
            elif line == ".cfi_endproc":
                in_cfi = False
            elif in_cfi:
                m = re.fullmatch(r"([A-Za-z_]\w*):", line)
                if m:
                    sym = m.group(1)
                    if sym not in prefixed and not sym.startswith("L"):
                        locals_in_cfi.add(sym)
        locals_in_cfi -= registers
        for sym in locals_in_cfi:
            renamed = "L_" + sym
            if renamed in defined or renamed in prefixed:
                raise ValueError(f"Mach-O local label rename collision: {sym} -> {renamed}")
        return locals_in_cfi

    result_hashes = {}
    for n, text in texts.items():
        defined = defined_per_file[n]
        cfi_locals = collect_cfi_locals(text, defined)
        rename_map = {s: "_" + s for s in prefixed}
        for s in cfi_locals:
            rename_map[s] = "L_" + s
        sym_pattern = (
            re.compile(
                r"\b(?:"
                + "|".join(map(re.escape, sorted(rename_map, key=len, reverse=True)))
                + r")\b"
            )
            if rename_map
            else None
        )

        def rewrite_syms(line, _pat=sym_pattern, _map=rename_map):
            if _pat is None:
                return line
            return _pat.sub(lambda m: _map[m.group(0)], line)

        out_lines = []
        skip_note = False
        for raw in text.splitlines():
            line = raw.strip()
            if not line:
                continue
            if line.startswith(("/*", "*", "//")):
                out_lines.append(line)
                continue
            if line.startswith(".section "):
                m = re.match(r"\.section\s+([^,\s]+)", line)
                if not m:
                    raise ValueError("Cannot parse ELF .section directive: " + line)
                sec_name = m.group(1)
                if sec_name in DROP_SECTIONS:
                    skip_note = True
                    continue
                skip_note = False
                if sec_name not in ASM_SECTION_MAP:
                    raise ValueError("Unmapped ELF ASM section for Mach-O: " + sec_name)
                out_lines.append(".section " + ASM_SECTION_MAP[sec_name])
                continue
            if skip_note:
                # Skip directives inside .note.gnu.property / .note.GNU-stack
                if line.startswith((".p2align", ".long", ".asciz", ".quad", ".byte", ".zero")):
                    continue
                skip_note = False
            if line.startswith((".type ", ".size ")):
                continue
            if line.startswith(".hidden "):
                for sym in line[8:].split(","):
                    s = sym.strip()
                    if s and s in defined:
                        out_lines.append(".private_extern _" + s)
                continue
            if line.startswith(".globl "):
                for sym in line[7:].split(","):
                    s = sym.strip()
                    if s:
                        out_lines.append(".globl _" + s)
                continue
            if line.startswith(".asciz "):
                out_lines.append(line)
                continue
            # Remove ELF @PLT suffix
            line = line.replace("@PLT", "")
            # Convert ELF .L local labels to Mach-O L local labels
            line = re.sub(r"(?<![A-Za-z0-9_])\.L([A-Za-z0-9_]+)", r"L\1", line)
            line = rewrite_syms(line)
            out_lines.append(line)
        rendered = "\n".join(out_lines) + "\n"
        # Sanity check: ensure no non-L label remains inside any CFI procedure
        in_cfi = False
        for check_line in out_lines:
            if check_line.startswith(".cfi_startproc"):
                in_cfi = True
            elif check_line == ".cfi_endproc":
                in_cfi = False
            elif in_cfi:
                m = re.fullmatch(r"([A-Za-z_]\w*):", check_line)
                if m and not m.group(1).startswith("L"):
                    raise ValueError(f"Non-local Mach-O label {m.group(1)!r} inside CFI in {n}")
        # Sanity check: ensure no ELF-only directives leaked into Mach-O output
        for forbidden in (
            "@progbits",
            "@function",
            "@object",
            "@PLT",
            "@note",
            ".size ",
            ".type ",
            ".hidden ",
        ):
            if forbidden in rendered:
                raise ValueError(f"ELF directive {forbidden!r} leaked into Mach-O {n}")
        (output / n).write_text(rendered, encoding="utf-8")
        result_hashes[n] = sha(output / n)
    return result_hashes, sorted(prefixed)


def adapt_all(source, output):
    source, output = Path(source).resolve(), Path(output).resolve()
    c_hashes, copied_incs = adapt_c_tree(source, output)
    asm_hashes, prefixed_syms = adapt_asm_files(output)
    record = dict(
        schema=1,
        target="macos-x86_64-macho",
        c_files=c_hashes,
        adapted_includes=copied_incs,
        asm_files=asm_hashes,
        prefixed_symbol_count=len(prefixed_syms),
    )
    (output / "MACOS-ADAPT.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(
        "MACOS MACH-O ADAPTED",
        len(c_hashes),
        "C/H files,",
        len(copied_incs),
        "includes,",
        len(asm_hashes),
        "ASM files",
    )
    return record
