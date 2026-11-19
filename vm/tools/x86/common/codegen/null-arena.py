"""Generate a guarded warm allocation helper outside the original core.

The source supplies the exact shape hash and object initialization. This keeps
the original object/property layouts, arena headers, accounting and GC list.
No new shape cache owner or allocation representation is introduced.
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
import hashlib, json
from pathlib import Path
from abi_layout import load as load_layout

sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()


def inline_header_body(source, hashes, initialize):
    """Specialize the actual 0.15 constructor while retaining its allocator/GC."""
    adapter = coff_module()
    functions = {
        match[2]: match[0]
        for match in adapter.FUNCTION.finditer(
            _frame_source_file(source, "quickjs.c").read_text(encoding="utf-8")
        )
    }
    trigger = functions["js_trigger_gc"].replace(
        "static void js_trigger_gc(", "static FRAME_NULL_INLINE void frame_null_trigger_gc(", 1
    )
    release = functions["js_free_shape"].replace(
        "static void js_free_shape(", "static FRAME_NULL_INLINE void frame_null_release_shape(", 1
    )
    assert trigger.count("frame_null_trigger_gc(") == 1
    assert release.count("js_free_shape0(") == 1
    release = release.replace("js_free_shape0(", "qjs_frame_core_js_free_shape0(")
    link = functions["add_gc_object"].replace(
        "static void add_gc_object(", "static FRAME_NULL_INLINE void frame_null_add_gc_object(", 1
    )
    assert link.count("frame_null_add_gc_object(") == 1
    hashes = hashes.replace("shape_initial_hash(", "frame_null_shape_initial_hash(")
    return (
        """
/* Inline-header upstreams have no small-block arenas. Keep the warm null-shape
 * specialization, and fuse the ordinary-object constructor with its actual
 * malloc/GC protocol. There is no new allocation representation or free list. */
extern void qjs_frame_core_js_free_shape0(JSRuntime *, JSShape *);
_Static_assert(QJS_ABI_HAS_PREFIX_RC == 0 && QJS_ABI_REF_COUNT_OFFSET == 0,
               "inline-header object/shape ownership");
_Static_assert(offsetof(JSRuntime,module_loader_has_attr)+6<offsetof(JSRuntime,u),
               "warm allocation control uses measured runtime padding");
"""
        + hashes
        + "\n"
        + trigger
        + "\n"
        + release
        + "\n"
        + link
        + """
FRAME_NULL_CODE JSValue JS_FrameNewNullObject(JSContext *ctx, JSValueConst proto_val, JSClassID class_id)
{
    JSRuntime *rt=ctx->rt;
    JSShape *sh;
    JSObject *p;
    uint32_t hash;
    if(class_id!=JS_CLASS_OBJECT || !JS_IsNull(proto_val) ||
       ((unsigned char *)rt)[offsetof(JSRuntime,module_loader_has_attr)+6] ||
       rt->in_free || rt->gc_phase!=JS_GC_PHASE_NONE)
        return JS_NewObjectProtoClass(ctx,proto_val,class_id);
    hash=frame_null_shape_initial_hash(NULL);
    for(sh=rt->shape_hash[hash>>(32-rt->shape_hash_bits)];sh;sh=sh->shape_hash_next)
        if(sh->hash==hash && sh->proto==NULL && sh->prop_count==0)
            break;
    if(!sh || sh->prop_size!=JS_PROP_INITIAL_SIZE)
        return JS_NewObjectProtoClass(ctx,proto_val,class_id);
    /* The original prototype constructor duplicates this owner BEFORE the
     * trigger or allocator can run GC/reenter. Every failure consumes it. */
    JS_REF_COUNT(sh)++;
    frame_null_trigger_gc(rt,sizeof(JSObject));
    p=js_malloc(ctx,sizeof(JSObject));
    if(unlikely(!p)) {
        frame_null_release_shape(rt,sh);
        return JS_EXCEPTION;
    }
"""
        + initialize
        + """    p->prop=js_malloc(ctx,sizeof(JSProperty)*sh->prop_size);
    if(unlikely(!p->prop)) {
        js_free(ctx,p);
        frame_null_release_shape(rt,sh);
        return JS_EXCEPTION;
    }
    /* Exact ordinary-object case: no properties are live yet. Publish the
     * complete object to the GC list only after both allocations succeed. */
    p->header.ref_count=1;
    frame_null_add_gc_object(rt,&p->header,JS_GC_OBJ_TYPE_JS_OBJECT);
    return JS_MKPTR(JS_TAG_OBJECT,p);
}
"""
    )


def generate_body(source):
    text = _frame_source_file(source, "quickjs.c").read_text(encoding="utf-8")
    start = text.index("static uint32_t shape_hash(uint32_t h, uint32_t val)")
    end = text.index("\nstatic int resize_shape_hash", start)
    hashes = text[start:end]
    assert hashes.count("shape_initial_hash(JSObject *proto)") == 1
    hashes = hashes.replace("shape_hash", "frame_null_shape_hash").replace(
        "static uint32_t", "static FRAME_NULL_INLINE uint32_t"
    )
    constructor = text.index(
        "static JSValue JS_NewObjectFromShape(JSContext *ctx, JSShape *sh, JSClassID class_id,\n                                     JSProperty *props)\n{"
    )
    begin = text.index("    p->class_id = class_id;", constructor)
    end = text.index("    p->prop = js_malloc(", begin)
    initialize = text[begin:end]
    assert (
        initialize.count("p->shape = sh;") == 1
        and initialize.count("p->first_weak_ref = NULL;") == 1
    )
    if load_layout(source)["reference_count_model"] == "inline-header":
        return inline_header_body(source, hashes, initialize)
    return (
        """
/* Only the native NULL_PROTO opcode calls this helper. Its compiler ABI is
   identical to JS_NewObjectProtoClass (including Win64 hidden JSValue result).
   Runtime byte1366 is unused original padding: zero enables this fast path.
   Never commit an allocation before every guard succeeds. */
_Static_assert(offsetof(JSRuntime,module_loader_has_attr)==1360 && offsetof(JSRuntime,u)==1368, "null arena switch1366 remains original padding");
_Static_assert(JS_ARENA_ALIGN==8 && sizeof(JSMallocBlockHeader)==8, "original arena prefix");
_Static_assert(sizeof(JSObject)>=16 && sizeof(JSObject)+8<=128, "object stays in exact eight-byte size classes");
_Static_assert(sizeof(JSProperty)*JS_PROP_INITIAL_SIZE>=16 && sizeof(JSProperty)*JS_PROP_INITIAL_SIZE+8<=128, "properties stay in exact eight-byte size classes");
"""
        + hashes
        + """
static FRAME_NULL_INLINE void *frame_null_take(JSArena *ar, unsigned block_size)
{
    unsigned index=ar->first_free_block;
    JSMallocBlockHeader *b=(JSMallocBlockHeader *)(ar->blocks+(size_t)index*block_size);
    ar->first_free_block=b->u.free_next;
    b->u.block_idx=index;
    ar->n_used_blocks++;
    return b->user_data;
}

FRAME_NULL_CODE JSValue JS_FrameNewNullObject(JSContext *ctx, JSValueConst proto_val, JSClassID class_id)
{
#if !JS_ARENA_LARGE_BLOCKS_ONLY
    enum { OB=((sizeof(JSObject)+7)&~7)+8,
           PB=((sizeof(JSProperty)*JS_PROP_INITIAL_SIZE+7)&~7)+8,
           OI=OB/8-2, PI=PB/8-2 };
    JSRuntime *rt=ctx->rt;
    JSShape *sh;
    JSObject *p;
    JSProperty *props;
    JSArena *oa,*pa;
    struct list_head *oh,*ph;
    size_t used,limit,budget;
    uint32_t hash;
    if (class_id!=JS_CLASS_OBJECT || !JS_IsNull(proto_val) ||
        ((unsigned char *)rt)[1366] || rt->gc_phase!=JS_GC_PHASE_NONE)
        goto slow;
    used=rt->malloc_state.malloc_size;
    /* Original constructor triggers GC before the object allocation. */
    if (used>rt->malloc_gc_threshold ||
        sizeof(JSObject)>rt->malloc_gc_threshold-used)
        goto slow;
    budget=(OB-8)+(PB-8)+2*MALLOC_OVERHEAD;
    limit=rt->malloc_state.malloc_limit-1; /* zero is unlimited */
    if (used>limit || budget>limit-used)
        goto slow;
    hash=frame_null_shape_hash(frame_null_shape_hash(1,0),0);
    for (sh=rt->shape_hash[hash>>(32-rt->shape_hash_bits)];sh;sh=sh->shape_hash_next) {
        if (sh->hash==hash && sh->proto==NULL && sh->prop_count==0)
            break;
    }
    if (!sh || sh->prop_size!=JS_PROP_INITIAL_SIZE)
        goto slow;
    oh=&rt->arena_state.free_arena_list[OI];
    ph=&rt->arena_state.free_arena_list[PI];
    if (oh->next==oh || ph->next==ph)
        goto slow;
    oa=list_entry(oh->next,JSArena,free_link);
    pa=list_entry(ph->next,JSArena,free_link);
    /* Leave at least one free cell, so no free-list removal is needed.
       The same-arena case reserves both cells before either is committed. */
    if (oa==pa) {
        if ((unsigned)oa->n_used_blocks+2>=oa->n_blocks)
            goto slow;
    } else if ((unsigned)oa->n_used_blocks+1>=oa->n_blocks ||
               (unsigned)pa->n_used_blocks+1>=pa->n_blocks) {
        goto slow;
    }
    /* No GC, native callback, allocation failure or reentry after this point. */
    JS_REF_COUNT(sh)++;
    p=frame_null_take(oa,OB);
    props=frame_null_take(pa,PB);
    rt->malloc_state.malloc_count+=2;
    rt->malloc_state.malloc_size+=budget;
"""
        + initialize
        + """    p->prop=props;
    JS_REF_COUNT(p)=1;
    JS_GC_MARK(p)=0;
    JS_GC_TYPE(p)=JS_GC_OBJ_TYPE_JS_OBJECT;
    list_add_tail(&p->header.link,&rt->gc_obj_list);
    return JS_MKPTR(JS_TAG_OBJECT,p);
slow:
#endif
    /* GC, sanitizer/stress allocation, arena refill/full, memory limit, cold
       shape and unsupported class/prototype retain the complete old path. */
    return JS_NewObjectProtoClass(ctx,proto_val,class_id);
}
"""
    )


import argparse, importlib.util, struct, subprocess

HERE = Path(__file__).resolve().parent


def null_module():
    sp = importlib.util.spec_from_file_location("null_common", _frame_tool_path("null-proto"))
    m = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


def coff_module():
    return null_module().coff_module()


def win_argv(command):
    return null_module().win_argv(command)


def generate(source, out):
    # No allocation or atom initialization in this TU uses js_atom_init.
    # Exclude exactly that unreferenced definition, retaining every type,
    # inline helper, enum, declaration and the source-derived layout.
    original_header = out.parent / "quickjs-interpreter-private.h"
    private_header = out.parent / "quickjs-interpreter-null-private.h"
    original = original_header.read_text(encoding="utf-8")
    atom_table = 'static const char js_atom_init[] =\n#define DEF(name, str) str "\\0"\n#include "quickjs-atom.h"\n#undef DEF\n;'
    assert original.count(atom_table) == 1 and original.count("js_atom_init") == 1
    trimmed = original.replace(
        atom_table, "/* Unused atom initialization data omitted only for the null allocator TU. */"
    )
    assert "js_atom_init" not in trimmed
    private_header.write_text(trimmed, encoding="utf-8")
    private_header.with_suffix(".header.json").write_text(
        json.dumps(
            dict(
                original_header_sha256=sha(original_header),
                generated_header_sha256=sha(private_header),
                excluded_definition="js_atom_init",
                excluded_occurrences=1,
                limit="No original TU includes this private copy; linked machine code and relocation checks remain required.",
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    code = """#include "quickjs-interpreter-null-private.h"
#if defined(_MSC_VER)
#define FRAME_NULL_CODE __declspec(code_seg(".qjscold$zznullfast")) no_inline
#define FRAME_NULL_INLINE __forceinline
#else
#define FRAME_NULL_CODE __attribute__((section(".qjsleaf$zznullfast"), noipa))
#define FRAME_NULL_INLINE __attribute__((always_inline)) inline
#endif
""" + generate_body(source)
    out.write_text(code, encoding="utf-8")
    layout = load_layout(source)
    out.with_suffix(".source.json").write_text(
        json.dumps(
            dict(
                source_sha256=sha(_frame_source_file(source, "quickjs.c")),
                generator_sha256=sha(Path(__file__)),
                generated_sha256=sha(out),
                control_byte=layout["offsets"]["JSRuntime.module_loader_has_attr"] + 6,
                allocator_model=layout["reference_count_model"],
                guard_policy=(
                    "Warm null shape; exact source-derived normal-object initialization, GC trigger, original malloc and shape-failure ownership"
                    if layout["reference_count_model"] == "inline-header"
                    else "Existing shape and nonfull small arenas; GC/limit/ASan/stress/unsupported guards fallback before any mutation"
                ),
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def compile_extra(source, build, out):
    layout = load_layout(source)
    if layout["reference_count_model"] == "inline-header":
        # Alias one live core function, preserving every original symbol and
        # instruction. Packing retains any existing COFF relocation tail.
        from core_routes import pack

        core = _frame_build_file(build, "CMakeFiles/qjs-core.dir/quickjs.c.obj")
        original = core.read_bytes()
        raw = pack(original)
        C = coff_module().Coff
        before = C(raw)
        co = C(raw)
        if "qjs_frame_core_js_free_shape0" not in co.symbols:
            assert co.symbols["js_free_shape0"]["section"] > 0
            co.expose("js_free_shape0")
            result = co.finish()
            after = C(result)
            assert before.count == after.count
            for number, (old, new) in enumerate(
                zip(before.section_records, after.section_records), 1
            ):
                assert old["flags"] == new["flags"] and old["size"] == new["size"]
                old_data = (
                    raw[old["raw"] : old["raw"] + old["size"]] if old["raw"] else bytes(old["size"])
                )
                new_data = (
                    result[new["raw"] : new["raw"] + new["size"]]
                    if new["raw"]
                    else bytes(new["size"])
                )
                assert old_data == new_data, (
                    "Null constructor alias changes section payload",
                    number,
                )
            for index, symbol in before.all_symbols.items():
                assert after.all_symbols[index] == symbol
            core.write_bytes(result)
            (_frame_generated_file(build, "quickjs-interpreter-null-alias.json")).write_text(
                json.dumps(
                    dict(
                        status="passed",
                        input_sha256=hashlib.sha256(original).hexdigest(),
                        output_sha256=sha(core),
                        alias="qjs_frame_core_js_free_shape0",
                        original_symbols_and_section_payloads_unchanged=True,
                    ),
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
    cfile = _frame_generated_file(build, "quickjs-interpreter-null-arena.c")
    generate(source, cfile)
    records = json.loads((_frame_build_file(build, "compile_commands.json")).read_text())
    original = next(x for x in records if Path(x["file"]).name == "quickjs-interpreter.c")
    args = win_argv(original["command"])
    new = []
    i = 0
    while i < len(args):
        a = args[i]
        if a == "-o":
            new.extend([a, str(out)])
            i += 2
            continue
        if a.lower().startswith("/fo") or a.lower().startswith("-fo"):
            new.append(a[:3] + str(out))
            i += 1
            continue
        if a == "-MF":
            new.extend([a, str(out) + ".d"])
            i += 2
            continue
        if Path(a).name.lower() == "quickjs-interpreter.c":
            a = str(cfile)
        new.append(a)
        i += 1
    assert str(cfile) in new and any(str(out) in x for x in new)
    p = subprocess.run(new, cwd=original["directory"], capture_output=True)
    out.with_suffix(".compile.log").write_bytes(p.stdout + p.stderr)
    if p.returncode:
        raise RuntimeError((p.stdout + p.stderr).decode(errors="replace"))
    C = coff_module().Coff
    obj = C(out.read_bytes())
    # Its functions are appended after the register object's late code. Keep
    # compiler-generated runtime-function entries after the matching ASM ones.
    late = (
        ".qjscold$zznullfast" if any(x.lower() == "/nologo" for x in new) else ".qjsleaf$zznullfast"
    )
    for section_index, (sec, rec) in enumerate(zip(obj.sections, obj.section_records), 1):
        name = sec["name"]
        if name.startswith("/"):
            at = int(name[1:])
            name = obj.strings[at : obj.strings.find(0, at)].decode()
        renamed = (
            ".pdata$zzzzzznullfast"
            if name.startswith(".pdata")
            else (
                late
                if (
                    name.startswith((".rdata", ".text", ".xdata"))
                    or rec["flags"] & 0x20000000
                    and name != late
                )
                and rec["size"]
                else None
            )
        )
        if name == late and rec["size"] and layout["reference_count_model"] == "inline-header":
            # Match the new code carrier to the constants/unwind contributions
            # already collected into this RX group; avoid mixed CODE/DATA kinds.
            renamed = late
        if renamed:
            at = len(obj.strings)
            obj.strings += renamed.encode() + b"\0"
            encoded = ("/" + str(at)).encode()
            assert len(encoded) <= 8
            obj.data[rec["pos"] : rec["pos"] + 8] = encoded.ljust(8, b"\0")
            if renamed == late:
                flags = (rec["flags"] & ~0xE0) | 0x60000040
                struct.pack_into("<I", obj.data, rec["pos"] + 36, flags)
            # Match section-definition symbols, preserving COMDAT auxiliaries.
            for index, sym in obj.all_symbols.items():
                if (
                    sym["section"] == section_index
                    and sym["name"] == name
                    and sym["storage"] == 3
                    and sym["type"] == 0
                ):
                    struct.pack_into("<II", obj.data, obj.table + index * obj.stride, 0, at)
    if late.startswith(".qjsleaf"):
        for sec, rec in zip(obj.sections, obj.section_records):
            if not rec["flags"] & 0x20000000 and not sec["name"].startswith(".rdata"):
                continue
            for i in range(rec["count"]):
                off, sym, kind = struct.unpack_from("<IIH", obj.data, rec["reloc"] + i * 10)
                assert kind != 1, (
                    "Allocated new native/data island must have no absolute 64-bit relocation",
                    sec["name"],
                    off,
                    obj.all_symbols[sym],
                )
    out.write_bytes(obj.finish())
    out.with_suffix(".compile.json").write_text(
        json.dumps(
            {
                "status": "passed",
                "compiler_command": new,
                "original_command": original,
                "compiler_sha256": sha(Path(new[0])),
                "source_sha256": sha(cfile),
                "object_sha256": sha(out),
                "runner_sha256": sha(Path(__file__)),
            },
            indent=2,
        )
        + "\n"
    )
    print("NULL EXTRA C COMPILED", out, flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--compile", action="store_true")
    ap.add_argument("--source", type=Path, required=True)
    ap.add_argument("--build", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    assert a.compile
    compile_extra(a.source, a.build, a.out)
