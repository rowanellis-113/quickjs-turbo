"""Source-owned GNU property supplements with immutable ELF dispatch.

Reuse the accepted native hint, Number, ProtoLoad, persistent/direct/live-chain,
borrowed PIC and length factories. Linux publication owns the Dirty clones.
Bytecode tails retain the two original producer/free lifetimes; immutable
dispatch uses a guarded entry instead of restoring writable PE pointer tables.
"""

import sys as _x86_sys
from pathlib import Path as _X86Path

if str(_X86Path(__file__).resolve().parents[2]) not in _x86_sys.path:
    _x86_sys.path.insert(0, str(_X86Path(__file__).resolve().parents[2]))
from x86.common.paths_x86 import source_file
import hashlib
import json
import re
from pathlib import Path
from types import SimpleNamespace
from c_workers import module, replace_one
from admission import function

OWNERS = (
    "tools/x86/common/codegen/own-bytecode.py",
    "tools/x86/common/codegen/number-property.py",
    "tools/x86/common/codegen/proto-load.py",
    "tools/x86/common/codegen/proto-direct.py",
    "tools/x86/common/codegen/length.py",
    "tools/x86/common/codegen/property_ic_native.py",
    "src/x86/win64/common/quickjs-interpreter-number-property.inc",
    "src/x86/win64/common/quickjs-interpreter-proto-load.inc",
    "src/common/kernel/proto-persistent.inc",
)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def contract(source):
    data = json.loads((source / "src/x86/linux/abi/properties.json").read_text())
    for name, value in data["owners"].items():
        if sha(source_file(source, name)) != value:
            raise ValueError("Review accepted GNU property owner: " + name)
    return data


class SourceText:
    def __init__(self, value):
        self.value = value

    def read_text(self, **kwargs):
        return self.value


def factory(source, name, assembly, generation, property_ic):
    owner = module(source, name)

    def generated(build, filename):
        if filename == "quickjs-call-link-vm-generation.json":
            return SourceText(json.dumps(generation))
        if filename == "CMakeCache.txt":
            return SourceText("QJS_PROPERTY_IC:BOOL=" + ("ON" if property_ic else "OFF"))
        if filename in (
            "quickjs-interpreter-register-win64.S",
            "quickjs-interpreter-publish-win64.S",
        ):
            return SourceText(assembly)
        raise ValueError("Unreviewed property factory input: " + filename)

    owner._frame_generated_file = generated
    owner._frame_build_file = generated
    original_module = getattr(owner, "module", None)
    if original_module:
        owner.module = lambda root, n: (
            SimpleNamespace(enabled=lambda _: property_ic)
            if n == "property_ic_native"
            else original_module(root, n)
        )
    return owner


def native_body(rows, name):
    first = rows.index(name + ":")
    end = rows.index(name + "_end:", first)
    return [r for r in rows[first + 1 : end] if r and not r.startswith(".")]


def append(source, output, stream, blocks, handlers, leaves, layout, *, shared_global=False):
    data = contract(source)
    if not layout["property_ic"] or layout["reference_count_model"] != "inline-header":
        raise ValueError("Review complete GNU property profile")
    main_length = len(stream["code"])
    code = list(stream["code"]) + list(stream["cold_code"])
    # Both factories operate on the unwrapped native handlers and publish the
    # same original PC/SP before any inherited C property boundary.
    module(source, "number-property").append(code)
    atoms = re.findall(r"^DEF\(\s*(\w+)", source_file(source, "quickjs-atom.h").read_text(), re.M)
    module(source, "proto-load").append(code, False, atoms.index("length") + 1)
    assembly = "\n".join(code) + "\n"
    section = next(
        i for i, r in enumerate(code) if r.startswith(".section .qjscall$zzznumberproperty")
    )
    number = native_body(code, "JS_FrameNumberPropertyEntry")
    prototype = native_body(code, "JS_FrameProtoLoadEntry")
    persistent = native_body(code, "JS_FrameProtoPersistentTry")
    stream["code"][:] = code[:main_length]
    stream["cold_code"][:] = code[main_length:section]
    number = replace_one(
        "\n".join(number),
        "call JS_FrameNumberPropertyConfigure",
        "mov rcx, rbx\ncall JS_LinuxPropertyInit",
        "typed Number cold initializer",
    ).splitlines()
    generation = dict(aliases=["M"], msvc=False, diagnostics=False)
    own = factory(source, "own-bytecode", assembly, generation, True)

    # The original factory queries enabled(build); give it only a read-only
    # virtual build input, never fabricate or consume a COFF object/receipt.
    class Build:
        def __truediv__(self, name):
            if name != "CMakeCache.txt":
                raise ValueError("Unreviewed virtual build input: " + name)
            return SourceText("QJS_PROPERTY_IC:BOOL=ON")

    own_blocks, _, _, own_contracts = own.source_blocks(Build(), False)
    own_blocks = [(n, r) for n, r in own_blocks if n != "JS_FrameSymbolGlobalCondition"]
    for kind, op in enumerate(("get_field", "get_field2", "put_field"), 1):
        name = "JS_FrameOwnBytecodeM" + str(kind)
        for n, rows in own_blocks:
            if n == name:
                rows[:0] = ["cmp BYTE PTR [rip+JS_FrameOwnBytecodeData], 1", "jne interp_" + op]
        handlers[op] = name
    old_names = {"JS_FrameOwnBytecodeM" + str(k) for k in (1, 2, 3)}
    blocks[:] = [(n, r) for n, r in blocks if n not in old_names]
    from x86.common.codegen.property_ic_native import blocks as property_blocks

    # The shared GNU borrowed-slot factory uses M's guards and is emitted
    # only with the original GNU P profile. Linux owns its own Dirty clones.
    extra, _, _, borrowed_contracts = property_blocks(
        None, layout, dict(aliases=["M", "P"], msvc=False, diagnostics=False)
    )
    borrowed = [(n, r) for n, r in extra if n == "JS_FrameBorrowedField"]
    if len(borrowed) != 1:
        raise ValueError("Missing original borrowed-slot property kernel")
    added = own_blocks + borrowed
    symbol_contracts = []
    for op in () if shared_global else ("get_var", "get_var_undef"):
        caller = next(r for n, r in blocks if n == "JS_FrameLinuxGlobal_" + op)
        ready = "interp_" + op + "_ready"
        name = "JS_FrameLinuxSymbol_" + op
        old = name + "_original"
        caller[:] = [r.replace(" " + ready, " " + name) for r in caller]
        rows, _, proofs = own.symbol_global_blocks(
            layout, source, name=name, old=old, prefix="linux_symbol_" + op
        )
        rows[0][1].extend([old + ":", "jmp " + ready])
        added += rows
        symbol_contracts += proofs
    direct = factory(source, "proto-direct", assembly, generation, True)
    direct_blocks, _, _, direct_contracts = direct.source_blocks(None, False)
    returning = [(n, r) for n, r in direct_blocks if n == "JS_FrameProtoDirectM"]
    added += [(n, r) for n, r in direct_blocks if n != "JS_FrameProtoDirectM"]
    prototype = [
        r.replace("call JS_FrameProtoPersistentTry", "call JS_FrameProtoDirectM")
        .replace("je JS_FrameProtoObjectEntry", "je JS_FrameProtoDirectMObject")
        .replace("jmp JS_FrameProtoLoadEntry", "jmp JS_FrameProtoDirectMString")
        for r in prototype
    ]
    # These are native returning probes at CFA8. Their pure C fill tail is a
    # checked SysV bridge and preserves the private RSI/RDI publication token.
    persistent = [r.replace("JS_FrameProtoPersistentFill", "JS_LinuxProtoFill") for r in persistent]
    returning = [
        (n, [r.replace("JS_FrameProtoPersistentFill", "JS_LinuxProtoFill") for r in rows])
        for n, rows in returning
    ]
    leaves += [("JS_FrameProtoPersistentTry", persistent)] + returning
    added += [("JS_FrameNumberPropertyEntry", number), ("JS_FrameProtoLoadEntry", prototype)]
    length = factory(source, "length", assembly, generation, True)
    length_blocks, _, _, length_contracts = length.source_blocks(None, False)
    if handlers.get("get_length") != "JS_FrameArgumentsLengthClean":
        raise ValueError("Review existing argument-length continuation")
    length_blocks = [
        (n, [r.replace("jmp interp_slow", "jmp JS_FrameArgumentsLengthClean") for r in rows])
        for n, rows in length_blocks
    ]
    added += length_blocks
    handlers["get_length"] = "JS_FrameLengthM"
    globals_ = [
        "JS_FrameOwnBytecodeData",
        "JS_FrameLengthData",
        "JS_FrameProtoDirectData",
        "JS_FrameNumberPropertyControl",
        "JS_FrameProtoLoadControl",
        "JS_FrameProtoPersistControl",
        "JS_FrameProtoPersistentHints",
    ]
    record = dict(
        status="generated-not-qualified",
        owners=data["owners"],
        functions=[n for n, _ in added],
        returning_functions=[
            n for n, _ in leaves if n.startswith(("JS_FrameProtoPersistent", "JS_FrameProtoDirect"))
        ],
        hint_contracts=own_contracts,
        borrowed_contracts=[
            r for r in borrowed_contracts if r.get("entry") == "JS_FrameBorrowedField"
        ],
        symbol_contracts=symbol_contracts,
        direct_contracts=direct_contracts,
        length_contracts=length_contracts,
        dispatch="Immutable original/Clean/Dirty ELF tables;every hint/PIC entry checks monotonic mode,not writable PE restoration",
        method_learning="Extra C learning policy is MSVC-only and excluded from default-active GNU parity",
        frame_growth=0,
        state_growth=0,
        extra_strong_roots=0,
    )
    (output / "PROPERTIES-VM.json").write_text(json.dumps(record, indent=2) + "\n")
    return added, globals_, record


def own_body(source, reference_controls=False):
    owner = module(source, "own-bytecode")
    text = owner.BODY
    prefix = text[: text.index("extern const uintptr_t interp_table[258];")]
    prefix = replace_one(
        prefix,
        "FRAME_MAX_CODE==2048",
        "FRAME_MAX_CODE>=2048",
        "Linux long-code admission retains a separate capped2048 hint plane",
    )
    prefix = prefix.replace('".qjzzom$C"', '".data.qjs_linux_own"')
    # Linux RELRO tables cannot be overwritten. A mode guard on every entry
    # replaces only PE pointer restoration, with the same monotonic disable.
    locking = """
static _Atomic(unsigned char) js_linux_own_lock;
static FRAME_INLINE void own_bytecode_lock(void) {
 while(atomic_exchange_explicit(&js_linux_own_lock,1,memory_order_acquire)) _mm_pause();
}
static FRAME_INLINE void own_bytecode_unlock(void) {
 atomic_store_explicit(&js_linux_own_lock,0,memory_order_release);
}
FRAME_CODE void JS_FrameOwnBytecodeDisable(void) {
 own_bytecode_lock();
 if(atomic_load_explicit(&JS_FrameOwnBytecodeData.mode,memory_order_relaxed)!=2) {
  atomic_store_explicit(&JS_FrameOwnBytecodeData.mode,3,memory_order_release);
  _mm_mfence();
  atomic_store_explicit(&JS_FrameOwnBytecodeData.mode,2,memory_order_release);
 }
 own_bytecode_unlock();
}
"""
    configure = function(text, "FRAME_CODE void JS_FrameOwnBytecodeConfigure(void)")
    configure = configure[: configure.index(" own_bytecode_lock();")]
    if not reference_controls:
        configure = replace_one(
            configure,
            " frame_reference_configure();\n",
            "",
            "independent PE reference/global controls are not an own-tail dependency",
        )
    configure = replace_one(
        configure,
        "flags==0xc0000000u &&\n  atomic_is_lock_free(&JS_FrameOwnBytecodeDispatch.selected) &&\n  atomic_is_lock_free(&JS_FrameOwnBytecodeDispatch.dirty[0]) &&\n  atomic_is_lock_free(&JS_FrameOwnBytecodeDispatch.base[0])",
        "flags==0xc0000000u && atomic_is_lock_free(&JS_FrameOwnBytecodeData.mode)",
        "actual immutable ELF dispatch requires only the lock-free mode cell",
    )
    configure += """ own_bytecode_lock();
 if(atomic_load_explicit(&JS_FrameOwnBytecodeData.mode,memory_order_relaxed)==0) {
  JS_FrameOwnBytecodeData.reserved[1]=local_field;
  JS_FrameOwnBytecodeData.reserved[4]=symbol_case;
  atomic_store_explicit(&JS_FrameOwnBytecodeData.mode,desired,memory_order_release);
 }
 own_bytecode_unlock();
}
"""
    extra = function(text, "static FRAME_INLINE size_t own_bytecode_extra(size_t n)")
    extra = replace_one(
        extra,
        "n<FRAME_MAX_CODE?n:FRAME_MAX_CODE",
        "n<2048?n:2048",
        "retain source-bound2048 reservation independently of long code",
    )
    allocate = function(text, "FRAME_CODE void *JS_FrameOwnBytecodeAllocateRT(")
    allocate_context = function(text, "FRAME_CODE void *JS_FrameOwnBytecodeAllocateContext(")
    return prefix + locking + extra + "\n" + configure + "\n" + allocate + "\n" + allocate_context


def generate(source, output, core, layout, *, reference_controls=False):
    data = contract(source)
    # Inventory pinned source creators, then bind both actual overlaid inputs.
    inventory = module(source, "own-bytecode").bytecode_source_contract(source)
    declaration = """
__attribute__((visibility("hidden"))) void *JS_FrameOwnBytecodeAllocateContext(JSContext *,size_t);
"""
    core = replace_one(
        core,
        '#include "quickjs.h"',
        '#include "quickjs.h"\n' + declaration,
        "producer declaration with actual public context type",
    )
    core = replace_one(
        core,
        "b = js_mallocz(ctx, function_size);",
        "b = JS_FrameOwnBytecodeAllocateContext(ctx, function_size);",
        "complete compiler producer",
    )
    compiler_input = Path(layout["compiler_input"])
    wire = (compiler_input.parent / "quickjs-portable-regexp-wire.h").read_text()
    wire = replace_one(
        wire,
        "b = js_mallocz(ctx, function_size);",
        "b = JS_FrameOwnBytecodeAllocateContext(ctx, function_size);",
        "complete serialized reader producer",
    )
    wire_path = output / "quickjs-linux-property-wire.h"
    wire_path.write_text(wire)
    core = replace_one(
        core,
        '#include "quickjs-portable-regexp-wire.h"',
        '#include "quickjs-linux-property-wire.h"',
        "reader with original allocation/free ownership",
    )
    code = '#include "src/x86/linux/interpreter-properties.inc"\n'
    for name in ("length", "proto-direct"):
        body = module(source, name).BODY
        for section in (".qjzzlm$C", ".qjzzdm$C"):
            body = body.replace('"' + section + '"', '".data.qjs_linux_properties"')
        code += body + "\n"
    if reference_controls:
        code += "static void frame_reference_configure(void);\n"
    code += own_body(source, reference_controls) + "\n"
    for owner, macro in (
        (OWNERS[6], "NUMBER_PROPERTY_CODE"),
        (OWNERS[7], "PROTO_LOAD_CODE"),
        (OWNERS[8], "PROTO_PERSIST_CODE"),
    ):
        body = (source / owner).read_text()
        body = re.sub(
            r'__attribute__\(\(section\("[^"]+"\)(, aligned\(8\))?\)\)',
            '__attribute__((section(".data.qjs_linux_properties"),aligned(8)))',
            body,
        )
        # Same-image ordinary hidden data has real ELF relocation binding.
        body = body.replace(
            "QJS_PROTO_LOAD_PRIMARY(primary);",
            "primary=__atomic_load_n(&JS_FrameProtoLoadControl,__ATOMIC_ACQUIRE);",
        )
        code += "#define " + macro + " FRAME_CODE\n" + body + "\n#undef " + macro + "\n"
    code += """
FRAME_CODE int JS_LinuxPropertyInit(JSFrameRegisterState *state) {
 (void)state;JS_FrameNumberPropertyConfigure();return 1;
}
FRAME_CODE int JS_LinuxProtoFill(JSFrameRegisterState *state) {
 return JS_FrameProtoPersistentFill(state);
}
static void __attribute__((constructor)) js_linux_property_configure(void) {
 JS_FrameOwnBytecodeConfigure();
}
#undef FRAME_CODE
#undef FRAME_INLINE
"""
    path = output / "quickjs-linux-properties.h"
    path.write_text(code)
    core += '\n#include "quickjs-linux-properties.h"\n'
    record = dict(
        status="generated-not-qualified",
        owners=data["owners"],
        source_files={
            n: sha(source_file(source, n))
            for n in (
                "tools/x86/linux/property_family.py",
                "src/x86/linux/interpreter-properties.inc",
            )
        },
        generated_sha256=sha(path),
        wire_sha256=sha(wire_path),
        creator_inventory=inventory,
        entries=[
            "JS_FrameOwnBytecodeAllocateRT",
            "JS_FrameOwnBytecodeAllocateContext",
            "JS_FrameOwnBytecodeConfigure",
            "JS_FrameOwnBytecodeDisable",
            "JS_FrameLengthConfigure",
            "JS_FrameProtoDirectConfigure",
            "JS_LinuxPropertyInit",
            "JS_LinuxProtoFill",
        ],
        lifetime="Two original creators and original allocation frees;zeroed bounded tail,no separate allocation/free hook or JS root",
        bytecode_hint_cap=2048,
        tail_bound="6+min(original allocation bytes,2048)",
        persistent_weak_bytes=128 * 32 + 64,
        control_lifetime="Same-image CRT constructor,pre-CRT producer disables permanently",
        frame_growth=0,
        state_growth=0,
        extra_strong_roots=0,
    )
    (output / "PROPERTIES.json").write_text(json.dumps(record, indent=2) + "\n")
    return core
