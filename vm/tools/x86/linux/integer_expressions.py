"""Bounded, noncalling integer expressions after the native child leaf guards.

Grammar: two scalar integer operands, binary arithmetic or comparison,
optional integer constant plus comparison or logical-not, and final return.
Operands may be arguments, live readonly closure cells, or integer constants.
No opcode, object, argument or VM state is written until a successful return.
All misses restore the inherited call arguments and use the original child.
"""


def generate(ids, offsets):
    miss = "linux_leaf_child_original_miss"
    prefix = "linux_int_expression_"
    p = lambda suffix: prefix + suffix
    rows = [
        "cmp BYTE PTR [rip+JS_LinuxIntExpressionControl], 1",
        "jne " + miss,
        "mov r11, QWORD PTR [rsp-64]",
        f"cmp WORD PTR [r11+{offsets['JSFunctionBytecode.var_count']}], 0",
        "jne " + miss,
        f"mov rax, QWORD PTR [rsp-128]",
        f"cmp QWORD PTR [r11+{offsets['JSFunctionBytecode.realm']}], rax",
        "jne " + miss,
        f"mov ecx, DWORD PTR [r11+{offsets['JSFunctionBytecode.byte_code_len']}]",
        "sub ecx, 4",
        "cmp ecx, 12",
        "ja " + miss,
        "add ecx, 4",
        f"mov r8, QWORD PTR [r11+{offsets['JSFunctionBytecode.byte_code_buf']}]",
        "lea rsi, [r8+rcx]",
    ]

    def constant(suffix):
        # EAX retains the left operand; only ECX/R11 and the private PC change.
        done = p("constant_" + suffix + "_done")
        out = [
            "cmp r8, rsi",
            "jae " + miss,
            "movzx ecx, BYTE PTR [r8]",
            "inc r8",
            "mov r11d, ecx",
            f"sub ecx, {ids['push_minus1']}",
            "cmp ecx, 8",
            "ja " + p("constant_" + suffix + "_wide"),
            "dec ecx",
            "jmp " + done,
            p("constant_" + suffix + "_wide") + ":",
        ]
        for name, size, load in [
            ("push_i8", 1, "movsx ecx, BYTE PTR [r8]"),
            ("push_i16", 2, "movsx ecx, WORD PTR [r8]"),
            ("push_i32", 4, "mov ecx, DWORD PTR [r8]"),
        ]:
            if name in ids:
                out += [f"cmp r11d, {ids[name]}", "je " + p("constant_" + suffix + "_" + name)]
        out += ["jmp " + miss]
        for name, size, load in [
            ("push_i8", 1, "movsx ecx, BYTE PTR [r8]"),
            ("push_i16", 2, "movsx ecx, WORD PTR [r8]"),
            ("push_i32", 4, "mov ecx, DWORD PTR [r8]"),
        ]:
            if name in ids:
                out += [
                    p("constant_" + suffix + "_" + name) + ":",
                    f"lea r11, [r8+{size}]",
                    "cmp r11, rsi",
                    "ja " + miss,
                    load,
                    f"add r8, {size}",
                    "jmp " + done,
                ]
        return out + [done + ":"]

    def operand(target, suffix):
        done = p("operand_" + suffix + "_done")
        arg = p("operand_" + suffix + "_argument")
        closure = p("operand_" + suffix + "_closure")
        out = [
            "cmp r8, rsi",
            "jae " + miss,
            "movzx r10d, BYTE PTR [r8]",
            "inc r8",
            f"sub r10d, {ids['get_arg0']}",
            "cmp r10d, 3",
            "jbe " + arg,
            f"add r10d, {ids['get_arg0']}",
            f"sub r10d, {ids['get_var_ref0']}",
            "cmp r10d, 3",
            "jbe " + closure,
            f"add r10d, {ids['get_var_ref0']}",
        ]
        for op in ("get_var_ref", "get_var_ref_check"):
            out += [f"cmp r10d, {ids[op]}", "je " + p("operand_" + suffix + "_wide_closure")]
        out += ["dec r8", *constant("operand_" + suffix)]
        if target != "ecx":
            out += ["mov " + target + ", ecx"]
        out += [
            "jmp " + done,
            arg + ":",
            "cmp r10d, DWORD PTR [rsp-88]",
            "jae " + miss,
            "shl r10, 4",
            "add r10, QWORD PTR [rsp+24]",
            "cmp QWORD PTR [r10+8], 0",
            "jne " + miss,
            "mov " + target + ", DWORD PTR [r10]",
            "jmp " + done,
            p("operand_" + suffix + "_wide_closure") + ":",
            "lea r11, [r8+2]",
            "cmp r11, rsi",
            "ja " + miss,
            "movzx r10d, WORD PTR [r8]",
            "add r8, 2",
            closure + ":",
            "mov r11, QWORD PTR [rsp-64]",
            f"movzx r11d, WORD PTR [r11+{offsets['JSFunctionBytecode.closure_var_count']}]",
            "cmp r10d, r11d",
            "jae " + miss,
            "mov r11, QWORD PTR [rsp-120]",
            f"mov r11, QWORD PTR [r11+{offsets['JSObject.u.func.var_refs']}]",
            "mov r11, QWORD PTR [r11+r10*8]",
            f"mov r11, QWORD PTR [r11+{offsets['JSVarRef.pvalue']}]",
            "cmp QWORD PTR [r11+8], 0",
            "jne " + miss,
            "mov " + target + ", DWORD PTR [r11]",
            done + ":",
        ]
        return out

    arithmetic = {
        "add": ["add eax, ecx", "jo " + miss],
        "sub": ["sub eax, ecx", "jo " + miss],
        "mul": [
            "mov edx, eax",
            "xor edx, ecx",
            "imul eax, ecx",
            "jo " + miss,
            "test eax, eax",
            "jnz " + p("arithmetic_done"),
            "test edx, edx",
            "js " + miss,
        ],
        "mod": [
            "test ecx, ecx",
            "jz " + miss,
            "cmp eax, -2147483648",
            "je " + miss,
            "mov r11d, eax",
            "cdq",
            "idiv ecx",
            "test edx, edx",
            "jnz " + p("remainder_ready"),
            "test r11d, r11d",
            "js " + miss,
            p("remainder_ready") + ":",
            "mov eax, edx",
        ],
        "and": ["and eax, ecx"],
        "or": ["or eax, ecx"],
        "xor": ["xor eax, ecx"],
        "shl": ["shl eax, cl"],
        "sar": ["sar eax, cl"],
        "shr": ["shr eax, cl", "test eax, eax", "js " + miss],
    }
    compares = dict(
        lt="l", lte="le", gt="g", gte="ge", eq="e", neq="ne", strict_eq="e", strict_neq="ne"
    )
    rows += operand("eax", "left")
    rows += operand("ecx", "right")
    rows += ["cmp r8, rsi", "jae " + miss, "movzx r10d, BYTE PTR [r8]", "inc r8"]
    for name in arithmetic:
        rows += [f"cmp r10d, {ids[name]}", "je " + p("arithmetic_" + name)]
    rows += ["jmp " + p("comparison")]
    for name, body in arithmetic.items():
        rows += [p("arithmetic_" + name) + ":", *body, "jmp " + p("arithmetic_done")]
    rows += [
        p("arithmetic_done") + ":",
        "cmp r8, rsi",
        "jae " + miss,
        f"cmp BYTE PTR [r8], {ids['return']}",
        "je " + p("integer_return"),
        f"cmp BYTE PTR [r8], {ids['lnot']}",
        "je " + p("logical_not"),
    ]
    rows += constant("second")
    rows += [
        "cmp r8, rsi",
        "jae " + miss,
        "movzx r10d, BYTE PTR [r8]",
        "inc r8",
        p("comparison") + ":",
    ]
    for name in compares:
        rows += [f"cmp r10d, {ids[name]}", "je " + p("compare_" + name)]
    rows += ["jmp " + miss]
    for name, cc in compares.items():
        rows += [
            p("compare_" + name) + ":",
            "cmp eax, ecx",
            "set" + cc + " al",
            "movzx eax, al",
            "mov edx, 1",
            "jmp " + p("return"),
        ]
    rows += [
        p("logical_not") + ":",
        "inc r8",
        "test eax, eax",
        "sete al",
        "movzx eax, al",
        "mov edx, 1",
        "jmp " + p("return"),
        p("integer_return") + ":",
        "xor edx, edx",
        p("return") + ":",
        "lea r11, [r8+1]",
        "cmp r11, rsi",
        "jne " + miss,
        f"cmp BYTE PTR [r8], {ids['return']}",
        "jne " + miss,
        "mov r10, QWORD PTR [rsp-128]",
        f"dec DWORD PTR [r10+{offsets['JSContext.interrupt_counter']}]",
        "ret",
    ]
    return rows
