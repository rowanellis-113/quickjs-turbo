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

sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()


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
    original = _frame_source_file(source, "string-to-number.c")
    out.write_bytes(original.read_bytes())
    out.with_suffix(".source.json").write_text(
        json.dumps(
            dict(
                source_sha256=sha(original),
                dtoa_header_sha256=sha(_frame_source_file(source, "dtoa.h")),
                generator_sha256=sha(Path(__file__)),
                generated_sha256=sha(out),
                policy="Complete decimal strings, <=15digits, decimal radix and ordinary flags; preserve original fallback.",
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def compile_extra(
    source, build, out, generator=generate, filename="string-to-number.c", late_name=None
):
    sp = importlib.util.spec_from_file_location(
        "generated_epoch", _frame_tool_path("adapter-restart")
    )
    epoch = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(epoch)
    epoch.retire_generated(out, build)
    cfile = _frame_build_file(build, filename)
    generator(source, cfile)
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
    late = late_name or (
        ".qjscold$zznullfast" if any(x.lower() == "/nologo" for x in new) else ".qjsleaf$zzzatod"
    )
    for section_index, (sec, rec) in enumerate(zip(obj.sections, obj.section_records), 1):
        name = sec["name"]
        if name.startswith("/"):
            at = int(name[1:])
            name = obj.strings[at : obj.strings.find(0, at)].decode()
        # A MinGW import-address COMDAT is data, even when its consumer is a
        # code island. Preserve its compiler section and key so the linker
        # places the DIR64 fixup on the readonly cell under normal ASLR.
        if name.startswith(".rdata$.refptr."):
            assert rec["flags"] & 0x40 and not rec["flags"] & 0xA0000020, name
            continue
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
    print("ATOD EXTRA C COMPILED", out, flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--compile", action="store_true")
    ap.add_argument("--source", type=Path, required=True)
    ap.add_argument("--build", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    assert a.compile
    compile_extra(a.source, a.build, a.out)
