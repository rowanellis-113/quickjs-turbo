"""Own data-property replacement with a proven non-final reference release.

Enter at the old put_field negative-tag branch, before mutation. The current
lookup already proved receiver>1, writable data, non-length, and loaded the old
payload/tag. No cache, allocation, C call, interpreter-layout change or last release.
"""


def append(masm, gas, layout):
    assert layout["reference_count_model"] == "inline-header"
    assert layout["sizes"]["JSValue"] == 16
    name = "JS_FramePropertyReferenceStore"
    slow = "interp_property_slow_put_field"
    body = [
        # R8 owns the receiver operand; R10 is its current property slot;
        # RAX is the old referenced payload. No C boundary can intervene.
        "cmp DWORD PTR [rax], 1",
        "jle " + slow,
        "cmp rax, r8",
        "jne " + name + "_safe",
        # Old value and receiver operand may be the same object. Both must
        # be released without bringing the combined reference count to zero.
        "cmp DWORD PTR [rax], 2",
        "jle " + slow,
        name + "_safe:",
        "mov r11, rax",
        "mov rax, QWORD PTR [r13-16]",
        "mov rdx, QWORD PTR [r13-8]",
        # Match set_value: transfer new ownership before releasing old.
        # Old==new is safe: the stack's owned incoming reference is retained
        # by the new slot. All guards precede changes to either value/RC.
        "mov QWORD PTR [r10], rax",
        "mov QWORD PTR [r10+8], rdx",
        "dec DWORD PTR [r11]",
        "dec DWORD PTR [r8]",
        "sub r13, 32",
        "add r12, 5",
        "movzx eax, BYTE PTR [r12]",
        "jmp QWORD PTR [rdi+rax*8]",
    ]
    assert masm.pop() == "END"
    masm += [
        ".qjscold SEGMENT ALIGN(16) 'CODE'",
        "PUBLIC " + name,
        "PUBLIC " + name + "_end",
        name + " PROC",
    ]
    gas += [
        '.section .qjscold,"xr"',
        ".globl " + name + ", " + name + "_end",
        ".def " + name + "; .scl 2; .type 32; .endef",
        name + ":",
    ]
    for line in body:
        if line.endswith(":"):
            masm.append(line[:-1] + "::")
        elif line.endswith(" " + slow):
            masm.append(line.replace(" " + slow, " NEAR PTR " + slow))
        else:
            masm.append(line)
    gas += body
    masm += [
        name + "_end LABEL BYTE",
        name + " ENDP",
        ".qjscold ENDS",
        ".pdata$zzqjscold SEGMENT ALIGN(4) READONLY 'DATA'",
        "DD IMAGEREL "
        + name
        + ", IMAGEREL "
        + name
        + "_end, IMAGEREL JS_FrameInterpPropertyCold_unwind",
        ".pdata$zzqjscold ENDS",
        "END",
    ]
    gas += [
        name + "_end:",
        '.section .pdata$zzqjscold,"dr"',
        ".p2align 2",
        ".rva " + name + ", " + name + "_end, JS_FrameInterpPropertyCold_unwind",
    ]
