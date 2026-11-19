"""Connect the complete accepted native in-capacity array append block."""

import hashlib
from c_workers import module


def append(source, stream, layout):
    expected_sizes = {"JSValue": 16, "JSShapeProperty": 8, "JSProperty": 16}
    expected_bits = {
        "JSObject.extensible": [[5, 1]],
        "JSContext.std_array_prototype": [[55, 128]],
        "JSShapeProperty.flags": [[3, 4]],
    }
    # Shape/object/context geometry is measured for this compiler input. The
    # shared factory consumes those values; bit encodings with literal guards
    # remain explicitly reviewed instead of inheriting a Windows layout.
    for name, value in expected_sizes.items():
        if layout["sizes"].get(name) != value:
            raise ValueError("Review dense append value geometry: " + name)
    for name, value in expected_bits.items():
        if layout["bits"].get(name) != value:
            raise ValueError("Review dense append bit encoding: " + name)
    if layout["reference_count_model"] != "inline-header":
        raise ValueError("Review native append release protocol")
    code = stream["code"]
    start = code.index("interp_put_array_el:")
    end = code.index("interp_put_array_el_typed:", start)
    old = "cmp ecx, DWORD PTR [r8+" + str(layout["offsets"]["JSObject.u.array.count"]) + "]"
    at = code.index(old, start, end) + 1
    if code[at] != "jae interp_slow":
        raise ValueError("Review dense array miss preconditions")
    name = "JS_FrameLinuxArrayAppend"
    code[at] = "jae " + name
    shared = module(source, "array-append")
    # The fast store emits an INT-tagged length. Preserve the source's uint32
    # length transition by retaining C before INT32_MAX+1, even with huge pools.
    rows = ["cmp ecx, 2147483647", "jae interp_slow"] + shared.body(
        name, "interp_slow", layout=layout
    )
    rows = [
        row.replace(
            "inc QWORD PTR [rip+JS_FrameVarargsArrayAppendData+8]",
            "lock inc QWORD PTR [rip+JS_FrameVarargsArrayAppendData+8]",
        )
        for row in rows
    ]
    fields = [
        "JSObject.u.array.count",
        "JSObject.u.array.u1",
        "JSObject.u.array.u.values",
        "JSObject.shape",
        "JSObject.prop",
        "JSShape.proto",
        "JSShape.prop",
        "JSContext.class_proto",
    ]
    return (
        [(name, rows)],
        ["JS_FrameVarargsArrayAppendData"],
        dict(
            native_in_capacity_append=True,
            source_edges=1,
            source_factory_sha256=hashlib.sha256(
                (source / "tools/x86/common/codegen/array-append.py").read_bytes()
            ).hexdigest(),
            measured_fields={name: layout["offsets"][name] for name in fields},
            measured_bits=expected_bits,
            measured_sizes=expected_sizes,
            length_guard="INT32_MAX extension retains original uint32-to-number C semantics",
            diagnostics="atomic counter update only when explicitly observed",
            commit="no C call,allocation,callback or final release;exact transferred value owner",
        ),
    )
