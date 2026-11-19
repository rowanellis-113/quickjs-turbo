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
    flag = False
    for value in layout["flags"]:
        if value == "-UQJS_FRAME_EXPERIMENTAL_ALLOCATOR":
            flag = False
        elif value == "-DQJS_FRAME_EXPERIMENTAL_ALLOCATOR" or value.startswith(
            "-DQJS_FRAME_EXPERIMENTAL_ALLOCATOR="
        ):
            flag = True
    contract = dict(
        native_byte_append=False,
        allocator_compiler_define=flag,
        actual_add_loc_rejection_edges=2,
        policy="actual-type C string boundaries;no runtime padding policy byte",
    )
    globals_ = []
    if flag:
        expected_sizes = {"JSString": 24, "JSStringRope": 48}
        expected_offsets = {
            "JSString.header": 0,
            "JSString.hash_next": 12,
            "JSStringRope.header": 0,
            "JSStringRope.len": 4,
            "JSStringRope.depth": 9,
            "JSStringRope.left": 16,
            "JSStringRope.right": 32,
            "JSRuntime.mf": 0,
            "JSMallocFunctions.js_malloc_usable_size": 32,
        }
        expected_bits = {
            "JSString.len": [[4, 1]],
            "JSString.is_wide_char": [[7, 128]],
            "JSString.kind": [[11, 16]],
            "JSString.atom_type": [[11, 64]],
        }
        expected_constants = {
            "JS_TAG_STRING": -7,
            "JS_TAG_STRING_ROPE": -6,
            "JS_TAG_UNDEFINED": 3,
            "JS_STRING_ROPE_SHORT_LEN": 512,
            "JS_STRING_ROPE_SHORT2_LEN": 8192,
            "JS_STRING_LEN_MAX": 1073741823,
            "JS_STRING_ROPE_MAX_DEPTH": 60,
            "JS_STRING_KIND_NORMAL": 0,
        }
        for group, values in (
            ("sizes", expected_sizes),
            ("offsets", expected_offsets),
            ("bits", expected_bits),
            ("constants", expected_constants),
        ):
            for field, expected in values.items():
                if layout[group].get(field) != expected:
                    raise ValueError("Review native string geometry: " + field)
        if layout["reference_count_model"] != "inline-header":
            raise ValueError("Review native string reference count protocol")
        path = tool_path("add-boundary")
        spec = importlib.util.spec_from_file_location("linux_shared_append", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        opcodes = {
            name.removeprefix("OP_"): layout["constants"][name]
            for name in (
                "OP_put_loc0",
                "OP_set_loc0",
                "OP_put_loc8",
                "OP_set_loc8",
                "OP_put_loc",
                "OP_set_loc",
            )
        }
        name = "JS_FrameLinuxNativeRopeAppend"
        begin = stream["short_code"].index("interp_short_big_add:")
        end = stream["short_code"].index("interp_short_big_mul:", begin)
        positions = [
            i
            for i in range(begin, end)
            if stream["short_code"][i] in ("jne interp_op_slow_add", "jo interp_op_slow_add")
        ]
        if len(positions) != 3:
            raise ValueError("Review all short-BigInt add miss edges")
        for at in positions:
            stream["short_code"][at] = stream["short_code"][at].split()[0] + " " + name
        rows = module.native_append_body(
            layout, opcodes, name, "interp_op_slow_add", add_mode="qjs_linux_string_add_mode"
        )
        rows = [
            row.replace("[JS_FrameLocalRopeMode]", "[rip+JS_FrameLocalRopeMode]").replace(
                "[FramePoolFunctions]", "[rip+FramePoolFunctions]"
            )
            for row in rows
        ]
        blocks.append((name, rows))
        globals_ = ["JS_FrameLocalRopeMode", "FramePoolFunctions", "qjs_linux_string_add_mode"]
        contract.update(
            native_byte_append=True,
            short_add_rejection_edges=3,
            measured_sizes=expected_sizes,
            measured_offsets=expected_offsets,
            measured_bits=expected_bits,
            measured_constants=expected_constants,
            shared_factory_sha256=hashlib.sha256(Path(path).read_bytes()).hexdigest(),
            pool_source_sha256=hashlib.sha256(
                (source / "src/common/memory/allocator-pool.c").read_bytes()
            ).hexdigest(),
            pool_contract="Actual allocator TU asserts16-byte FramePoolHeader and capacity offset8;callback identity guard precedes header read",
        )
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
