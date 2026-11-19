"""Render the SysV native C boundary from compiler-measured Linux fields."""

import re


def render(source, layout, mapping):
    if layout["sizes"]["JSStackFrame"] != 72 or layout["sizes"]["JSValue"] != 16:
        raise ValueError("Review the Linux native C frame before admitting a changed layout")
    offsets, constants = layout["offsets"], layout["constants"]
    if (constants["JS_CFUNC_generic"], constants["JS_CFUNC_generic_magic"]) != (0, 1):
        raise ValueError("Review changed generic C prototype discriminants")
    if (
        constants["JS_CFUNC_f_f"],
        constants["JS_CFUNC_f_f_f"],
        constants["JS_TAG_FLOAT64"],
        constants["JS_TAG_INT"],
    ) != (6, 7, 8, 0):
        raise ValueError("Review numeric prototype/tag encodings")
    if (
        layout["bits"]["JSShapeProperty.flags"] != [[3, 4]]
        or layout["offsets"]["JSShapeProperty.atom"] != 4
    ):
        raise ValueError("Review dense-pop property descriptor encoding")
    fast, ext = layout["bits"]["JSObject.fast_array"], layout["bits"]["JSObject.extensible"]
    if len(fast) != 1 or len(ext) != 1 or fast[0][0] != ext[0][0]:
        raise ValueError("Review dense-pop live object flags")
    values = dict(
        INIT_BRIDGE=mapping["JS_LinuxCInvokeInit"],
        FALLBACK_BRIDGE=mapping["JS_FrameInterpHostDirect"],
        GENERIC_BRIDGE=mapping["JS_FrameInterpHost"],
        RT_SHARED=offsets["JSRuntime.current_stack_frame"] - 5,
    )
    values.update(
        OBJ_ARRAY_FLAGS=fast[0][0],
        OBJ_ARRAY_FLAG_MASK=fast[0][1] | ext[0][1],
        SHAPE_FLAGS_SHIFT=26,
        LENGTH_FLAGS=constants["JS_PROP_WRITABLE"] | constants["JS_PROP_LENGTH"],
    )
    for name, field in dict(
        OBJ_CLASS="JSObject.class_id",
        OBJ_CPROTO="JSObject.u.cfunc.cproto",
        OBJ_LENGTH="JSObject.u.cfunc.length",
        OBJ_REALM="JSObject.u.cfunc.realm",
        OBJ_FUNCTION="JSObject.u.cfunc.c_function",
        OBJ_MAGIC="JSObject.u.cfunc.magic",
        RT_SF="JSRuntime.current_stack_frame",
        RT_LIMIT="JSRuntime.stack_limit",
        RT_TOP="JSRuntime.stack_top",
        CTX_INTERRUPT="JSContext.interrupt_counter",
        CTX_RT="JSContext.rt",
        SF_PREV="JSStackFrame.prev_frame",
        SF_FUNC="JSStackFrame.cur_func",
        SF_ARGV="JSStackFrame.arg_buf",
        SF_ARGC="JSStackFrame.arg_count",
        SF_STRICT="JSStackFrame.is_strict_mode",
        OBJ_SHAPE="JSObject.shape",
        OBJ_PROPERTIES="JSObject.prop",
        SHAPE_PROPERTIES="JSShape.prop",
        SHAPE_ATOM="JSShapeProperty.atom",
        ARRAY_COUNT="JSObject.u.array.count",
        ARRAY_VALUES="JSObject.u.array.u.values",
    ).items():
        values[name] = offsets[field]
    for name, constant in dict(
        TAG_OBJECT="JS_TAG_OBJECT",
        TAG_UNDEFINED="JS_TAG_UNDEFINED",
        TAG_EXCEPTION="JS_TAG_EXCEPTION",
        CLASS_C_FUNCTION="JS_CLASS_C_FUNCTION",
        CPROTO_MAGIC="JS_CFUNC_generic_magic",
        CPROTO_UNARY="JS_CFUNC_f_f",
        CPROTO_BINARY="JS_CFUNC_f_f_f",
        TAG_FLOAT="JS_TAG_FLOAT64",
        TAG_INT="JS_TAG_INT",
        CLASS_ARRAY="JS_CLASS_ARRAY",
        ATOM_LENGTH="JS_ATOM_length",
    ).items():
        values[name] = constants[constant]
    template = (source / "asm/x86/linux/c-invoke.inc").read_text()
    from c_special import render as render_special
    from builtin_vm import render as render_builtins

    special = render_special(source, layout, template) + render_builtins(template)
    template += "\n" + "\n".join(special) + "\n"
    # Restrict replacements to complete markers; comments may contain @...@.
    template = re.sub(r"@([A-Z_]+)@", lambda m: str(values[m[1]]), template)
    if re.search(r"@[A-Z_]+@", template):
        raise ValueError("Unresolved Linux C invocation field")
    return template.splitlines()
