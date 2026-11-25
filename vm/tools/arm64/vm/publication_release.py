"""Publication release unification helpers for ARM64 Fast VM."""

import re
from arm64.vm.specialize import _replace_exact


def _unify_publication_release(text, output, op_ids):
    # 1. Proxy x25 == dirty guard (sp-independent)
    proxies_path = output / "interpreter-aarch64-publication-proxies.inc"
    proxies_text = proxies_path.read_text()
    proxy_stems = re.findall(r"qjs_aarch64_publish_before_([A-Za-z0-9_]+):", proxies_text)
    if len(proxy_stems) != 29:
        raise ValueError(f"Expected 29 publication proxies, got {len(proxy_stems)}")
    proxies_new, n_prox = re.subn(
        r"(    adrp x10, qjs_aarch64_publish_clean\n"
        r"    add x10, x10, :lo12:qjs_aarch64_publish_clean\n"
        r"    cmp x25, x10\n"
        r"    b\.eq \.Lproxy_(\d+)_clean\n"
        r")(    mov x25, x10\n)",
        r"#ifdef QJS_AARCH64_VM_INSTRUMENT\n"
        r"\1"
        r"#else\n"
        r"    adrp x10, .Lfast_clean_ptrs\n"
        r"    add x10, x10, :lo12:.Lfast_clean_ptrs\n"
        r"    cmp x25, x10\n"
        r"    b.eq .Lproxy_\2_clean\n"
        r"    adrp x11, .Lfast_dirty_ptrs\n"
        r"    add x11, x11, :lo12:.Lfast_dirty_ptrs\n"
        r"    cmp x25, x11\n"
        r"    b.ne .Lproxy_\2_clean\n"
        r"#endif\n"
        r"\3",
        proxies_text,
    )
    if n_prox != 29:
        raise ValueError(f"Expected 29 proxy guards inserted, got {n_prox}")
    proxies_new = _replace_exact(
        proxies_new,
        "    b JS_FrameInterpProperty_call_constructor\n",
        "#ifdef QJS_AARCH64_VM_INSTRUMENT\n"
        "    b JS_FrameInterpProperty_call_constructor\n"
        "#else\n"
        "    b JS_FastConstructCall\n"
        "#endif\n",
        1,
        "construct proxy fast target",
    )
    proxies_path.write_text(proxies_new)

    # 2. Release dirty table unification (keep only the 11 publication-mutating slots)
    ptab_path = output / "interpreter-aarch64-publication-tables.inc"
    ptab_lines = ptab_path.read_text().splitlines()
    clean_idx = ptab_lines.index("qjs_aarch64_publish_clean:")
    dirty_idx = ptab_lines.index("qjs_aarch64_publish_dirty:")
    clean_words = ptab_lines[clean_idx + 1 : clean_idx + 257]
    dirty_words = ptab_lines[dirty_idx + 1 : dirty_idx + 257]
    keep_slots = {
        op_ids[k]
        for k in (
            "call_constructor",
            "call",
            "call_method",
            "tail_call",
            "tail_call_method",
            "return",
            "return_undef",
            "call0",
            "call1",
            "call2",
            "call3",
        )
    }
    rel_dirty_words = []
    for i in range(256):
        if i in keep_slots:
            rel_dirty_words.append(dirty_words[i])
        else:
            lbl = clean_words[i].strip()
            if not lbl.startswith(".word ") or " - qjs_aarch64_publish_clean" not in lbl:
                raise ValueError(f"Unexpected clean table line {i}: {lbl}")
            rel_dirty_words.append(
                "    " + lbl.replace(" - qjs_aarch64_publish_clean", " - qjs_aarch64_publish_dirty")
            )
    typeof_slot = op_ids["typeof"]
    pbi_slot = op_ids["push_bigint_i32"]
    dirty_words[typeof_slot] = "    .word .Lpub_literal_typeof - qjs_aarch64_publish_dirty"
    dirty_words[pbi_slot] = "    .word .Lpub_slow - qjs_aarch64_publish_dirty"
    clean_prefix = list(ptab_lines[: dirty_idx + 1])
    clean_prefix[clean_idx + 1 + typeof_slot] = (
        "#ifdef QJS_AARCH64_VM_INSTRUMENT\n"
        "    .word .Lliteral_typeof - qjs_aarch64_publish_clean\n"
        "#else\n"
        "    .word .Lfast_typeof - qjs_aarch64_publish_clean\n"
        "#endif"
    )
    clean_prefix[clean_idx + 1 + pbi_slot] = (
        "#ifdef QJS_AARCH64_VM_INSTRUMENT\n"
        "    .word .Lslow - qjs_aarch64_publish_clean\n"
        "#else\n"
        "    .word .Lfast_push_bigint_i32 - qjs_aarch64_publish_clean\n"
        "#endif"
    )
    new_ptab = (
        clean_prefix
        + ["#ifdef QJS_AARCH64_VM_INSTRUMENT"]
        + dirty_words
        + ["#else"]
        + rel_dirty_words
        + ["#endif"]
        + ptab_lines[dirty_idx + 257 :]
    )
    ptab_path.write_text("\n".join(new_ptab) + "\n")
    disp_path = output / "interpreter-aarch64-dispatch.inc"
    disp_text = _replace_exact(
        disp_path.read_text(),
        ".word .Lfast_typeof - .Ldispatch_table",
        "#ifdef QJS_AARCH64_VM_INSTRUMENT\n"
        ".word .Lliteral_typeof - .Ldispatch_table\n"
        "#else\n"
        ".word .Lfast_typeof - .Ldispatch_table\n"
        "#endif",
        1,
        "typeof instrument dispatch",
    )
    disp_text = _replace_exact(
        disp_text,
        ".word .Lfast_push_bigint_i32 - .Ldispatch_table",
        "#ifdef QJS_AARCH64_VM_INSTRUMENT\n"
        ".word .Lslow - .Ldispatch_table\n"
        "#else\n"
        ".word .Lfast_push_bigint_i32 - .Ldispatch_table\n"
        "#endif",
        1,
        "push_bigint_i32 instrument dispatch",
    )
    disp_path.write_text(disp_text)

    # 3. Rewrite non-pub_ `bl JS_<stem>` (for 29 proxy stems) after `.Lpublication_selected:`
    #    Skip lines inside existing #ifdef QJS_AARCH64_VM_INSTRUMENT blocks or inside .Lpub_ handlers.
    stem_set = set(proxy_stems)
    out_lines = []
    after_sel = False
    cond_stack = []
    in_pub_handler = False
    for line in text.splitlines():
        s = line.strip()
        if s == ".Lpublication_selected:":
            after_sel = True
        if s.startswith("#ifdef ") or s.startswith("#ifndef ") or s.startswith("#if "):
            cond_stack.append(s)
        elif s == "#else":
            if cond_stack:
                cond_stack[-1] = "ELSE:" + cond_stack[-1]
        elif s == "#endif":
            if cond_stack:
                cond_stack.pop()
        if re.match(r"^\.[A-Za-z0-9_]+:$", s):
            if (
                s.startswith(".Lpub_fast_")
                or s.startswith(".Lpub_")
                and not s.startswith(".Lpub_call")
                and not s.startswith(".Lpub_return")
            ):
                in_pub_handler = True
            else:
                in_pub_handler = s.startswith(".Lpub_") or s.startswith(".Lknown_")
        in_inst_only = any(c == "#ifdef QJS_AARCH64_VM_INSTRUMENT" for c in cond_stack)
        if after_sel and not in_inst_only and not in_pub_handler:
            m = re.match(r"^    bl JS_([A-Za-z0-9_]+)$", line)
            if m and m.group(1) in stem_set:
                st = m.group(1)
                out_lines.append("#ifdef QJS_AARCH64_VM_INSTRUMENT")
                out_lines.append(f"    bl JS_{st}")
                out_lines.append("#else")
                out_lines.append(f"    bl qjs_aarch64_publish_before_{st}")
                out_lines.append("#endif")
                continue
        out_lines.append(line)
    text = "\n".join(out_lines) + "\n"

    # 4. Wrap dead .Lpub_* ranges inside #ifdef QJS_AARCH64_VM_INSTRUMENT ... #endif
    dead_ranges = [
        (
            "pub range 1 (push_i8 .. call_forward_guard)",
            "\n.Lpub_push_i8:\n",
            "\n/* Genuine original Function.prototype.call gate.",
            1,
            1,
        ),
        (
            "pub range 2 (iterator_for_of_start .. call_short)",
            "\n/* Accepted typed synchronous iterator/checkpoint boundaries. MIT. */\n#if ARM_HAS_ITERATORS\n.Lpub_iterator_for_of_start:",
            "\n/* Native prepared child frames,",
            1,
            1,
        ),
        (
            "pub range 3 (regexp .. arguments_guard)",
            "\n/* Complete source-owned regexp opcode bridge;MIT. No immediate operands. */\n.Lpub_regexp:",
            "\n/* Original arguments prefix admission and typed same-activation builder. MIT. */\n#if ARM_HAS_ARGUMENTS\n.Lpub_arguments_guard:",
            1,
            1,
        ),
        (
            "pub range 4 (arguments_length)",
            "\n.Lpub_arguments_length:",
            "\n#endif\n\n/* Original intrinsic apply guard",
            1,
            1,
        ),
        (
            "pub range 5 (indexed_get_array_el .. AAPCS64 result)",
            "\n/* Original indexed-storage algorithms; actual measured AAPCS64 VM. MIT. */\n#if ARM_HAS_INDEXED\n.Lpub_indexed_get_array_el:",
            "\n/* Standard AAPCS64 JSValue result x0/x1.",
            1,
            2,
        ),
        (
            "pub range 6 (property_ic .. known_return)",
            "\n/* Bytecode-owned by-id PIC hits over actual target types. MIT.",
            "\n.Lknown_return:\n",
            2,
            1,
        ),
        (
            "pub range 7a (number_local_1_overflow .. add)",
            "\n.Lnumber_local_1_overflow:\n",
            "\n.Ladd:\n",
            1,
            1,
        ),
        (
            "pub range 7b (pub_add .. valueflow_nonnumber_add)",
            "\n.Lpub_add:\n",
            "\n.Lvalueflow_nonnumber_add:\n",
            1,
            1,
        ),
        (
            "pub range 7b (pub_valueflow_nonnumber_add .. get_loc_short)",
            "\n.Lpub_valueflow_nonnumber_add:\n",
            "\n.Lget_loc_short:\n",
            1,
            1,
        ),
        (
            "pub range 7c (pub_get_loc_short .. return_prepare)",
            "\n.Lpub_get_loc_short:\n",
            "\n.Lreturn_prepare:\n",
            1,
            1,
        ),
    ]

    def find_nth(hay, sub, n):
        pos = -1
        for _ in range(n):
            pos = hay.find(sub, pos + 1)
            if pos < 0:
                return -1
        return pos

    for desc, s_mark, e_mark, s_nth, e_nth in dead_ranges:
        s_idx = find_nth(text, s_mark, s_nth)
        if s_idx < 0:
            raise ValueError(f"Missing start marker for {desc}")
        e_idx = (
            text.find(e_mark, s_idx + len(s_mark)) if e_nth == 1 else find_nth(text, e_mark, e_nth)
        )
        if e_idx < 0 or e_idx <= s_idx:
            raise ValueError(f"Missing/invalid end marker for {desc}")
        body = text[s_idx:e_idx]
        text = (
            text[:s_idx]
            + "\n#ifdef QJS_AARCH64_VM_INSTRUMENT\n"
            + body
            + "\n#endif\n"
            + text[e_idx:]
        )

    # 5. Also rewrite Release-active relative dispatch/publication table loads into 8-byte .Lfast_*_ptrs
    lines = text.splitlines()
    rewritten_lines = []
    cond_stack = []
    in_env_init = False
    in_macro = False
    past_vm_end = False
    i = 0
    while i < len(lines):
        ln = lines[i]
        st = ln.strip()
        if st == ".Lfast_vm_leaf_env_init:":
            in_env_init = True
        elif st == "b .Lfast_vm_leaf_env_ready":
            in_env_init = False
        if st.startswith(".macro "):
            in_macro = True
        elif st == ".endm":
            in_macro = False
        if st == "qjs_aarch64_vm_end:":
            past_vm_end = True
        if st.startswith("#ifdef ") or st.startswith("#ifndef ") or st.startswith("#if "):
            if "QJS_AARCH64_VM_INSTRUMENT" in st:
                kind = "inst_true" if st.startswith("#ifdef ") else "inst_false"
            else:
                kind = "other"
            cond_stack.append(kind)
        elif st == "#else":
            if cond_stack:
                if cond_stack[-1] == "inst_true":
                    cond_stack[-1] = "inst_false"
                elif cond_stack[-1] == "inst_false":
                    cond_stack[-1] = "inst_true"
        elif st == "#endif":
            if cond_stack:
                cond_stack.pop()

        in_inst = any(c == "inst_true" for c in cond_stack)
        rel_only = any(c == "inst_false" for c in cond_stack)
        if (
            not in_inst
            and not in_env_init
            and not in_macro
            and not past_vm_end
            and i + 1 < len(lines)
        ):
            ln1 = lines[i + 1]
            if ln == "    ldrsw x10, [x25, x9, lsl #2]" and ln1 == "    add x10, x25, x10":
                if rel_only:
                    rewritten_lines.append("    ldr x10, [x25, x9, lsl #3]")
                else:
                    rewritten_lines.extend(
                        [
                            "#ifdef QJS_AARCH64_VM_INSTRUMENT",
                            ln,
                            ln1,
                            "#else",
                            "    ldr x10, [x25, x9, lsl #3]",
                            "#endif",
                        ]
                    )
                i += 2
                continue
            m_ptab = re.match(r"^    adrp ([A-Za-z0-9_]+), qjs_aarch64_publish_(clean|dirty)$", ln)
            if m_ptab:
                reg, pkind = m_ptab.group(1), m_ptab.group(2)
                expected_next = f"    add {reg}, {reg}, :lo12:qjs_aarch64_publish_{pkind}"
                if ln1 != expected_next:
                    raise ValueError(f"Expected `{expected_next}` after `{ln}`, got `{ln1}`")
                fast_sym = f".Lfast_{pkind}_ptrs"
                new_pair = [
                    f"    adrp {reg}, {fast_sym}",
                    f"    add {reg}, {reg}, :lo12:{fast_sym}",
                ]
                if rel_only:
                    rewritten_lines.extend(new_pair)
                else:
                    rewritten_lines.extend(
                        [
                            "#ifdef QJS_AARCH64_VM_INSTRUMENT",
                            ln,
                            ln1,
                            "#else",
                            *new_pair,
                            "#endif",
                        ]
                    )
                i += 2
                continue
        rewritten_lines.append(ln)
        i += 1
    text = "\n".join(rewritten_lines) + "\n"

    # 6. Safe line-based preprocessor check verifying ALL Release label refs exist & ZERO x26/x27 corruption!
    rel_asm = []
    stack = []

    def is_active():
        return all(st[1] for st in stack)

    in_env_init_chk = False
    in_macro_chk = False
    past_vm_end_chk = False
    for ln in text.splitlines():
        st = ln.strip()
        if st == "#ifdef QJS_AARCH64_VM_INSTRUMENT":
            stack.append(("inst", False))
        elif st == "#ifndef QJS_AARCH64_VM_INSTRUMENT":
            stack.append(("rel", True))
        elif st.startswith("#if ") or st.startswith("#ifdef ") or st.startswith("#ifndef "):
            # Treat ARM_HAS_* / QJS_AARCH64_* (except _INSTRUMENT) as enabled in Release check
            cond_true = "QJS_AARCH64_VM_INSTRUMENT" not in st
            stack.append(("other", cond_true))
        elif st == "#else":
            kind, cur = stack[-1]
            stack[-1] = (kind, not cur)
        elif st == "#endif":
            stack.pop()
        elif is_active():
            rel_asm.append(ln)
            if st == ".Lfast_vm_leaf_env_init:":
                in_env_init_chk = True
            elif st == "b .Lfast_vm_leaf_env_ready":
                in_env_init_chk = False
            if st.startswith(".macro "):
                in_macro_chk = True
            elif st == ".endm":
                in_macro_chk = False
            if st == "qjs_aarch64_vm_end:":
                past_vm_end_chk = True
            if not in_env_init_chk and not in_macro_chk and not past_vm_end_chk:
                for forbidden in (
                    "qjs_aarch64_publish_clean",
                    "qjs_aarch64_publish_dirty",
                    ".Ldispatch_table",
                ):
                    if forbidden in st:
                        raise ValueError(f"Stale relative table ref in Release code: {st}")
                if re.search(r"\bldrsw\b[^\n]*\[x25\b", st):
                    raise ValueError(f"Stale 4-byte ldrsw dispatch in Release code: {st}")
    if stack:
        raise ValueError(f"Unbalanced #if/#endif stack after Release unification: {stack}")
    rel_joined = "\n".join(rel_asm)
    # Strip comments and collect GAS macro definitions to avoid false positives on \.L\name templates
    no_macro_lines = []
    macro_defs = {}
    cur_macro = None
    for ln in rel_asm:
        st = ln.strip()
        if cur_macro is not None:
            if st == ".endm":
                cur_macro = None
            else:
                macro_defs[cur_macro][1].append(ln)
            continue
        m_mac = re.match(r"^\.macro\s+([A-Za-z0-9_]+)(.*)$", st)
        if m_mac:
            mname = m_mac.group(1)
            params = [x.strip() for x in m_mac.group(2).split(",") if x.strip()]
            macro_defs[mname] = (params, [])
            cur_macro = mname
            continue
        # Expand simple top-level macro invocations in-place so their defined/referenced .L labels are exact
        parts = re.split(r"\s+", st, maxsplit=1)
        if parts and parts[0] in macro_defs:
            mparams, mbody = macro_defs[parts[0]]
            margs = [x.strip() for x in parts[1].split(",")] if len(parts) > 1 else []
            for ml in mbody:
                exp = ml.replace("\\@", "0")
                for pn, pa in zip(mparams, margs):
                    exp = exp.replace("\\" + pn, pa)
                no_macro_lines.append(exp)
        else:
            no_macro_lines.append(ln)
    rel_exp = "\n".join(no_macro_lines)
    defined_lbls = set(re.findall(r"(?m)^(\.L[A-Za-z0-9_]+):$", rel_exp))
    rel_ptab_words = [
        line.split()[1]
        for line in clean_words + rel_dirty_words
        if line.strip().startswith(".word .L")
    ]
    disp_words = [
        line.split()[1]
        for line in (output / "interpreter-aarch64-dispatch.inc").read_text().splitlines()
        if line.strip().startswith(".word .L")
    ]
    ref_lbls = set(re.findall(r"(?<![A-Za-z0-9_])(\.L[A-Za-z0-9_]+)(?![A-Za-z0-9_:])", rel_exp))
    ref_lbls.update(rel_ptab_words)
    ref_lbls.update(disp_words)
    missing = sorted(lbl for lbl in ref_lbls if lbl not in defined_lbls)
    if missing:
        raise ValueError(f"Unresolved Release .L labels ({len(missing)}): {missing}")
    for ln in rel_asm:
        s = ln.strip()
        if re.match(r"^(add|sub|orr|and|eor|mov|ldr\w*)\s+[xw]2[67]\b", s):
            if s not in (
                "mov x26, #0",
                "mov x27, #0",
                "ldr x26, [x22, #ARM_OFF_JSFrame_bytecode]",
                "mov x26, x7",
                "mov x27, #1",
                "sub x27, x3, x9, lsl #3",
                "sub x27, x5, x9, lsl #3",
            ):
                raise ValueError(f"Unexpected write to x26/x27 in Release .S: {s}")
    return text
