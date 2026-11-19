"""Pure-C global binding source invariants and slot metadata."""

import hashlib
import re
import sys as _frame_sys
from pathlib import Path as _FramePath

_frame_tools_root = str(_FramePath(__file__).resolve().parents[2])
if _frame_tools_root not in _frame_sys.path:
    _frame_sys.path.insert(0, _frame_tools_root)
from common.paths import source_file as _frame_source_file


def inspect_global_invariants(source):
    core = _frame_source_file(source, "quickjs.c").read_text(encoding="utf-8")
    assert "h = (uintptr_t)atom & sh->prop_hash_mask;" in core
    assert "return prop_hash_end(sh) - ((intptr_t)sh->prop_hash_mask + 1);" in core
    shape_property = core[
        core.index("typedef struct JSShapeProperty {") : core.index("} JSShapeProperty;")
    ]
    assert re.search(r"uint32_t\s+hash_next\s*:\s*26\s*;", shape_property)
    assert re.search(r"uint32_t\s+flags\s*:\s*6\s*;", shape_property)
    constructors = re.findall(r"->(global_obj|global_var_obj)\s*=(?!=)\s*(.*?);", core, re.S)
    expected = {
        "global_obj": "JS_NewObjectProtoClassAlloc(ctx, ctx->class_proto[JS_CLASS_OBJECT], JS_CLASS_OBJECT, 64)",
        "global_var_obj": "JS_NewObjectProtoClassAlloc(ctx, JS_NULL, JS_CLASS_OBJECT, 16)",
    }
    assert len(constructors) == 2
    assert {name: " ".join(value.split()) for name, value in constructors} == expected
    assert not re.search(r"&\s*\w+->global_(?:var_)?obj\b", core)
    context = core[
        core.index("JSContext *JS_NewContextRaw(JSRuntime *rt)") : core.index(
            "JSContext *JS_NewContext(JSRuntime *rt)"
        )
    ]
    required = "if (JS_AddIntrinsicBasicObjects(ctx)) {\n        JS_FreeContext(ctx);\n        return NULL;\n    }\n    return ctx;"
    assert required in context
    allocation = core[
        core.index("    p->class_id = class_id;") : core.index(
            "static JSValue JS_NewObjectProtoClassAlloc("
        )
    ]
    assert "p->is_exotic = 0;" in allocation
    assert "case JS_CLASS_OBJECT:\n        break;" in allocation
    exotic_writes = re.findall(r"\w+->is_exotic\s*=(?!=)", core)
    assert len(exotic_writes) == 4 and len(re.findall(r"\w+->is_exotic\s*=(?!=)", allocation)) == 4
    object_invariants = dict(
        status="passed",
        source_sha256=hashlib.sha256(core.encode("utf-8")).hexdigest(),
        constructors=expected,
        assignments=len(constructors),
        exotic_write_sites=len(exotic_writes),
        context_raw_constructs_basic_objects=True,
        global_fields_never_passed_by_mutable_address=True,
        scope="Public engine contexts, including raw contexts; all object/exotic writes belong to allocation. No cached context/object/shape pointer is introduced.",
    )
    opcodes = [
        m[1]
        for m in re.finditer(
            r"^DEF\(\s*(\w+)\s*,", _frame_source_file(source, "quickjs-opcode.h").read_text(), re.M
        )
    ]
    slots = [opcodes.index(n) for n in ("get_var", "get_var_undef")]
    atoms = re.findall(
        r"^DEF\(\s*(\w+)", _frame_source_file(source, "quickjs-atom.h").read_text(), re.M
    )
    undefined_atom = atoms.index("undefined") + 1
    undefined_hash = (undefined_atom * 7046029254386353131) & ((1 << 64) - 1)
    return dict(
        object_invariants=object_invariants,
        dispatch_slots=slots,
        undefined_atom=undefined_atom,
        undefined_hash=undefined_hash,
    )
