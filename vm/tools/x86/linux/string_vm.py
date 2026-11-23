"""Linux VM string boundaries and the shared no-call native byte append lane."""

import hashlib
import importlib.util
from pathlib import Path


def append(source, stream, layout):
    from common.paths import tool_path

    code = stream["code"]
    begin = code.index("interp_add_loc_number:")
    end = code.index("jmp QWORD PTR [rdi+rax*8]", begin) + 1
    positions = [i for i in range(begin, end) if code[i] == "jne interp_slow"]
    if len(positions) != 2:
        raise ValueError("Review both original numeric add_loc rejection edges")
    name = "JS_FrameLinuxAddLocalStringCold"
    for at in positions:
        code[at] = "jne " + name
    blocks = [
        (
            name,
            [
                "mov eax, DWORD PTR [r8+8]",
                "sub eax, -7",
                "cmp eax, 1",
                "ja interp_slow",
                "mov eax, DWORD PTR [r13-8]",
                "sub eax, -7",
                "cmp eax, 1",
                "ja interp_slow",
                "mov QWORD PTR [rbx], rbp",
                "mov QWORD PTR [rbx+16], r12",
                "mov QWORD PTR [rbx+24], r13",
                "mov rcx, rbx",
                "call JS_FrameAddLocalString",
                "cmp eax, 2",
                "je linux_string_local_done",
                "test eax, eax",
                "jne interp_exit",
                "jmp interp_reload",
                "linux_string_local_done:",
                "mov r12, QWORD PTR [rbx+16]",
                "mov r13, QWORD PTR [rbx+24]",
                "movzx eax, BYTE PTR [r12]",
                "jmp QWORD PTR [rdi+rax*8]",
            ],
        )
    ]
    contract = dict(
        native_byte_append=False,
        allocator_compiler_define=False,
        actual_add_loc_rejection_edges=2,
        policy="actual-type C string boundaries;no runtime padding policy byte",
    )
    globals_ = []
    # The accepted GNU route changes only the receiver object-tag miss,
    # after the original integer-index guard. Keep all other slow transfers.
    import json
    from arguments import asm_body

    manifest = json.loads((source / "src/x86/linux/abi/string-entry.json").read_text())
    for owner, digest in manifest["owners"].items():
        if hashlib.sha256((source / owner).read_bytes()).hexdigest() != digest:
            raise ValueError("Review native string-index entry owner: " + owner)
    owner = "asm/x86/win64/mingw64/mingw-string_index_entry.S"
    clean = asm_body(source, owner, "JS_FrameStringIndexClean", layout)
    dirty = asm_body(source, owner, "JS_FrameStringIndexDirty", layout)
    expected = [row.replace("dirty_interp_slow", "interp_slow") for row in dirty]
    if expected != clean:
        raise ValueError("Review complete shared Clean/Dirty string-index entry")
    for op in ("get_array_el", "get_array_el2"):
        begin = code.index("interp_" + op + ":")
        end = code.index("interp_" + op + "_typed:", begin)
        part = "\n".join(code[begin:end])
        before = "cmp DWORD PTR [r13-24], -1\njne interp_slow"
        if part.count(before) != 1 or "cmp DWORD PTR [r13-8], 0\njne interp_slow" not in part:
            raise ValueError("Review index-tag-before-receiver string entry: " + op)
        code[begin:end] = part.replace(
            before, before.replace("jne interp_slow", "jne JS_FrameStringIndexClean")
        ).splitlines()
    clean = [row.replace("JS_FrameNativeLifetimeResume", "interp_reload") for row in clean]
    blocks.append(("JS_FrameStringIndexClean", clean))
    globals_.append("JS_FrameStringIndexMode")
    contract["native_index_entry"] = dict(
        owners=manifest["owners"],
        functions=["JS_FrameStringIndexClean"],
        retained_rows=len(clean),
        Clean_Dirty_equivalent=True,
        route="Both original receiver-object misses after integer-index guard",
        source_algorithm="Complete original GNU bounds/mode/publication/C-step/return body",
        C_helper="Actual typed SysV int(JSFrameRegisterState*);original string value/GC owner",
        frame_growth=0,
        state_growth=0,
        new_strong_roots=0,
    )
    return blocks, globals_, contract
