"""Native current-own-data slot hints for all value tags; exact live validation."""

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
from native_abi import current as current_abi, current_or_load as load_layout, source_abi
from abi_layout import constants as abi_constants
from x86.common.build_tools import find_objdump
from pathlib import Path
import hashlib, importlib.util, json, os, re, struct, subprocess

sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
CODE = ".qjzzoc"
RW = ".qjzzom$C"
CFI = ".qjzzof"
MAGIC = b"QJSBC_UNWIND_v1!"
FOOTER = b"QJSBC_END_v1!!!!"
assert len(MAGIC) == len(FOOTER) == 16


def module(source, name):
    spec = importlib.util.spec_from_file_location(
        "own_bytecode_" + name.replace("-", "_"), _frame_tool_path(name + ".py")
    )
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


BODY = r"""
#include <stdatomic.h>
#include <immintrin.h>
#include "src/common/internal/interpreter-env.h"
#include "src/common/internal/turbo-config.h"
typedef struct JSFrameOwnBytecodeControl {
 _Atomic(unsigned char) mode;
 unsigned char diagnostic,reserved[6]; /* reserved[2]: MSVC method IC learning policy */
 _Atomic(uint64_t) reads,methods,fills,misses,abi;
 _Atomic(uint64_t) allocations,base_bytes,reserved_bytes,fallbacks;
} JSFrameOwnBytecodeControl;
_Static_assert(sizeof(JSFrameOwnBytecodeControl)==80 && offsetof(JSFrameOwnBytecodeControl,reads)==8 &&
 offsetof(JSFrameOwnBytecodeControl,reserved)+1==3 &&
 offsetof(JSFrameOwnBytecodeControl,reserved)+2==4 &&
 offsetof(JSFrameOwnBytecodeControl,methods)==16 && offsetof(JSFrameOwnBytecodeControl,fills)==24 &&
 offsetof(JSFrameOwnBytecodeControl,misses)==32 && offsetof(JSFrameOwnBytecodeControl,abi)==40 &&
 offsetof(JSFrameOwnBytecodeControl,allocations)==48 && offsetof(JSFrameOwnBytecodeControl,reserved_bytes)==64,
 "bytecode-lifetime own hint control ABI");
_Static_assert(sizeof(JSValue)%4==0 && sizeof(JSVarDef)%4==0 && sizeof(JSClosureVar)%4==0 && _Alignof(JSValue)%4==0,
 "Both creator code offsets follow an8-aligned cpool and4-divisible elements; code buffers are4-aligned");
_Static_assert(FRAME_MAX_CODE==2048 && sizeof(JSValue)==16 && sizeof(JSStackFrame)==QJS_ABI_SIZE_JSStackFrame && sizeof(JSShapeProperty)==8 &&
 offsetof(JSFrame,bytecode)==80 && offsetof(JSFunctionBytecode,byte_code_buf)==QJS_ABI_OFF_JSFunctionBytecode_byte_code_buf &&
 offsetof(JSFunctionBytecode,byte_code_len)==QJS_ABI_OFF_JSFunctionBytecode_byte_code_len &&
 offsetof(JSShapeProperty,atom)==4 && offsetof(JSObject,shape)==QJS_ABI_OFF_JSObject_shape && offsetof(JSObject,prop)==QJS_ABI_OFF_JSObject_prop &&
 offsetof(JSShape,prop_count)==QJS_ABI_OFF_JSShape_prop_count && offsetof(JSShape,prop_hash_mask)==QJS_ABI_OFF_JSShape_prop_hash_mask &&
 JS_TAG_OBJECT==-1 && JS_TAG_SYMBOL==-8 && JS_PROP_TMASK==48,
 "bytecode own hint uses pinned live descriptor/refcount and unchanged frame ABI");
#if QJS_ABI_HAS_PREFIX_RC
_Static_assert(JS_ARENA_ALIGN%4==0 && offsetof(JSShape,hash_table)==QJS_ABI_OFF_JSShape_hash_table &&
 offsetof(JSMallocBlockHeader,user_data)-offsetof(JSMallocBlockHeader,ref_count)==-QJS_ABI_REF_COUNT_OFFSET,
 "prefix allocator alignment and shape properties");
#else
_Static_assert(offsetof(JSShape,prop)==QJS_ABI_OFF_JSShape_prop && QJS_ABI_REF_COUNT_OFFSET==0,
 "inline allocator ownership and shape properties");
#endif
#ifdef QJS_INTERP_FRAME_DIAGNOSTICS
#define OWN_BYTECODE_DIAG 1
#else
#define OWN_BYTECODE_DIAG 0
#endif
#ifdef _MSC_VER
extern void JS_FrameLengthConfigure(void);
#pragma section(".qjzzom$C",read,write)
__declspec(allocate(".qjzzom$C"))
#else
extern void JS_FrameProtoDirectConfigure(void);
__attribute__((section(".qjzzom$C"),used,aligned(8)))
#endif
JSFrameOwnBytecodeControl JS_FrameOwnBytecodeData={0,OWN_BYTECODE_DIAG,{3}};

extern const uintptr_t interp_table[258];

/* All referenced symbols are private and defined in this same engine image.
   GNU PE auto-import refptr literals would introduce late absolute fixups.
   Ask for the same RIP-relative LEA used by the native backend, on this new
   cold C module only. No compiler flags, image base or core layout changes. */
#ifdef _MSC_VER
#define OWN_PRIVATE_ADDRESS(symbol) ((uintptr_t)(symbol))
#else
#define OWN_PRIVATE_ADDRESS_RAW(symbol) ({ uintptr_t own_private_address; \
 __asm__("lea " #symbol "(%%rip), %0" : "=r"(own_private_address)); own_private_address; })
#define OWN_PRIVATE_ADDRESS(symbol) OWN_PRIVATE_ADDRESS_RAW(symbol)
#endif

extern void interp_get_field(void),interp_get_field2(void);
extern void JS_FrameOwnBytecodeM1(void),JS_FrameOwnBytecodeM2(void);
#ifdef QJS_PROPERTY_IC
extern void JS_FrameOwnBytecodeM3(void),JS_FrameOwnBytecodeP3(void);
extern void interp_put_field(void),dirty_interp_put_field(void);
#endif
#if OWN_BYTECODE_DIRTY_P
extern void dirty_interp_get_field(void),dirty_interp_get_field2(void);
extern void JS_FrameOwnBytecodeP1(void),JS_FrameOwnBytecodeP2(void);
extern _Atomic(unsigned char) JS_FramePublishControl;
extern _Atomic(uintptr_t) JS_FramePublishTable[258],JS_FramePublishDirtyTable[258];
#define OWN_ORIGINAL_P1 dirty_interp_get_field
#define OWN_ORIGINAL_P2 dirty_interp_get_field2
#else
#define OWN_ORIGINAL_P1 interp_get_field
#define OWN_ORIGINAL_P2 interp_get_field2
#endif
#if OWN_BYTECODE_SHARED_DIAG
extern _Atomic(unsigned char) JS_FrameGlobalBindingControl;
extern _Atomic(uintptr_t) JS_FrameGlobalBindingDiagnosticTable[258];
#endif
typedef struct JSFrameOwnBytecodeDispatchData {
 _Atomic(unsigned char) lock;
 unsigned char reserved[7];
 _Atomic(uintptr_t) selected;
 _Atomic(uintptr_t) dirty[2];
 _Atomic(uintptr_t) base[258];
#ifdef QJS_PROPERTY_IC
 _Atomic(uintptr_t) put_dirty;
#endif
} JSFrameOwnBytecodeDispatchData;
_Static_assert(sizeof(uintptr_t)==8 && ATOMIC_LLONG_LOCK_FREE>=1 && _Alignof(_Atomic(uintptr_t))>=8 &&
 sizeof(_Atomic(uintptr_t))==8 && sizeof(JSFrameOwnBytecodeDispatchData)==2096
#ifdef QJS_PROPERTY_IC
 +8
#endif
 &&
 offsetof(JSFrameOwnBytecodeDispatchData,selected)==8 &&
 offsetof(JSFrameOwnBytecodeDispatchData,dirty)==16 &&
 offsetof(JSFrameOwnBytecodeDispatchData,base)==32 &&
 OP_get_field==OWN_BYTECODE_FIELD1 && OP_get_field2==OWN_BYTECODE_FIELD2,
 "aligned lock-free Win64 dispatch pointer cells and actual opcode IDs");
#ifdef _MSC_VER
__declspec(allocate(".qjzzom$C"))
#else
__attribute__((section(".qjzzom$C"),used,aligned(8)))
#endif
/* Before CRT the selected pointer is0. Every bytecode producer reaches
    Disable from mode0 before it may expose original-size storage; Configure
    also initializes pointers before publishing1/2. No native JS dispatch can
    precede those producer/configuration barriers. No absolute initializer. */
JSFrameOwnBytecodeDispatchData JS_FrameOwnBytecodeDispatch={0};
static FRAME_INLINE void own_bytecode_lock(void) {
 while(atomic_exchange_explicit(&JS_FrameOwnBytecodeDispatch.lock,1,memory_order_acquire)) _mm_pause();
}
static FRAME_INLINE void own_bytecode_unlock(void) {
 atomic_store_explicit(&JS_FrameOwnBytecodeDispatch.lock,0,memory_order_release);
}
FRAME_CODE void JS_FrameOwnBytecodeDisable(void) {
 own_bytecode_lock();
 if(atomic_load_explicit(&JS_FrameOwnBytecodeData.mode,memory_order_relaxed)!=2) {
  /* BUSY is not stable OFF: another runtime must join this lock before it
     may return original-size storage. Existing Own opcodes hold older tails. */
  atomic_store_explicit(&JS_FrameOwnBytecodeData.mode,3,memory_order_release);
  atomic_store_explicit(&JS_FrameOwnBytecodeDispatch.dirty[0],OWN_PRIVATE_ADDRESS(OWN_ORIGINAL_P1),memory_order_release);
  atomic_store_explicit(&JS_FrameOwnBytecodeDispatch.dirty[1],OWN_PRIVATE_ADDRESS(OWN_ORIGINAL_P2),memory_order_release);
  atomic_store_explicit(&JS_FrameOwnBytecodeDispatch.selected,OWN_PRIVATE_ADDRESS(interp_table),memory_order_release);
  /* Retained RDI addresses require restoring the old writable table itself. */
  atomic_store_explicit(&JS_FrameOwnBytecodeDispatch.base[OWN_BYTECODE_FIELD1],OWN_PRIVATE_ADDRESS(interp_get_field),memory_order_release);
  atomic_store_explicit(&JS_FrameOwnBytecodeDispatch.base[OWN_BYTECODE_FIELD2],OWN_PRIVATE_ADDRESS(interp_get_field2),memory_order_release);
#ifdef QJS_PROPERTY_IC
  atomic_store_explicit(&JS_FrameOwnBytecodeDispatch.base[OWN_BYTECODE_FIELD3],OWN_PRIVATE_ADDRESS(interp_put_field),memory_order_release);
#if OWN_BYTECODE_DIRTY_P
  atomic_store_explicit(&JS_FrameOwnBytecodeDispatch.put_dirty,OWN_PRIVATE_ADDRESS(dirty_interp_put_field),memory_order_release);
#endif
#endif
#if OWN_BYTECODE_DIRTY_P || OWN_BYTECODE_SHARED_DIAG
  /* The following owner load may otherwise bypass our buffered pointer/table
     stores. An initializer that claims0 after that load must see originals;
     one that already read Own pointers must be visible as busy/ready here.
     r6134 has a concrete FIFO-store-buffer counterexample without this fence.
     This x64 backend uses MFENCE only on the cold restoration path. */
  _mm_mfence();
#endif
#if OWN_BYTECODE_DIRTY_P
  while(atomic_load_explicit((_Atomic(unsigned char)*)OWN_PRIVATE_ADDRESS(JS_FramePublishControl),memory_order_acquire)==3) _mm_pause();
  atomic_store_explicit(&((_Atomic(uintptr_t)*)OWN_PRIVATE_ADDRESS(JS_FramePublishTable))[OWN_BYTECODE_FIELD1],OWN_PRIVATE_ADDRESS(interp_get_field),memory_order_release);
  atomic_store_explicit(&((_Atomic(uintptr_t)*)OWN_PRIVATE_ADDRESS(JS_FramePublishTable))[OWN_BYTECODE_FIELD2],OWN_PRIVATE_ADDRESS(interp_get_field2),memory_order_release);
  atomic_store_explicit(&((_Atomic(uintptr_t)*)OWN_PRIVATE_ADDRESS(JS_FramePublishDirtyTable))[OWN_BYTECODE_FIELD1],OWN_PRIVATE_ADDRESS(dirty_interp_get_field),memory_order_release);
  atomic_store_explicit(&((_Atomic(uintptr_t)*)OWN_PRIVATE_ADDRESS(JS_FramePublishDirtyTable))[OWN_BYTECODE_FIELD2],OWN_PRIVATE_ADDRESS(dirty_interp_get_field2),memory_order_release);
#ifdef QJS_PROPERTY_IC
  atomic_store_explicit(&((_Atomic(uintptr_t)*)OWN_PRIVATE_ADDRESS(JS_FramePublishTable))[OWN_BYTECODE_FIELD3],OWN_PRIVATE_ADDRESS(interp_put_field),memory_order_release);
  atomic_store_explicit(&((_Atomic(uintptr_t)*)OWN_PRIVATE_ADDRESS(JS_FramePublishDirtyTable))[OWN_BYTECODE_FIELD3],OWN_PRIVATE_ADDRESS(dirty_interp_put_field),memory_order_release);
#endif
#endif
#if OWN_BYTECODE_SHARED_DIAG
  while(atomic_load_explicit((_Atomic(unsigned char)*)OWN_PRIVATE_ADDRESS(JS_FrameGlobalBindingControl),memory_order_acquire)==3) _mm_pause();
  atomic_store_explicit(&((_Atomic(uintptr_t)*)OWN_PRIVATE_ADDRESS(JS_FrameGlobalBindingDiagnosticTable))[OWN_BYTECODE_FIELD1],OWN_PRIVATE_ADDRESS(interp_get_field),memory_order_release);
  atomic_store_explicit(&((_Atomic(uintptr_t)*)OWN_PRIVATE_ADDRESS(JS_FrameGlobalBindingDiagnosticTable))[OWN_BYTECODE_FIELD2],OWN_PRIVATE_ADDRESS(interp_get_field2),memory_order_release);
#endif
  JS_FrameOwnBytecodeData.reserved[3]=2;
  atomic_store_explicit(&JS_FrameOwnBytecodeData.mode,2,memory_order_release);
 }
 own_bytecode_unlock();
}
FRAME_CODE void JS_FrameOwnBytecodeSetTailMode(int tail_enabled) {
 own_bytecode_lock();
 unsigned char cur=atomic_load_explicit(&JS_FrameOwnBytecodeData.mode,memory_order_relaxed);
 if(!tail_enabled && cur==1) {
  atomic_store_explicit(&JS_FrameOwnBytecodeData.mode,3,memory_order_release);
  _mm_mfence();
#ifdef QJS_PROPERTY_IC
  atomic_store_explicit(&JS_FrameOwnBytecodeData.mode,4,memory_order_release);
#else
  JS_FrameOwnBytecodeData.reserved[3]=2;
  atomic_store_explicit(&JS_FrameOwnBytecodeData.mode,2,memory_order_release);
#endif
 }
 own_bytecode_unlock();
}
FRAME_CODE int JS_FrameOwnBytecodeTailActive(void) {
 return atomic_load_explicit(&JS_FrameOwnBytecodeData.mode,memory_order_acquire)==1?1:0;
}

static FRAME_INLINE size_t own_bytecode_extra(size_t n) {
 return 6+(n<FRAME_MAX_CODE?n:FRAME_MAX_CODE);
}
#include "src/common/call/reference-config.inc"
FRAME_CODE void JS_FrameOwnBytecodeConfigure(void) {
 frame_reference_configure();
#ifdef _MSC_VER
 JS_FrameLengthConfigure();
#else
 JS_FrameProtoDirectConfigure();
#endif
 JSShapeProperty prop={0};uint32_t flags;prop.flags=JS_PROP_TMASK;memcpy(&flags,&prop,4);
 unsigned valid=flags==0xc0000000u &&
  atomic_is_lock_free(&JS_FrameOwnBytecodeDispatch.selected) &&
  atomic_is_lock_free(&JS_FrameOwnBytecodeDispatch.dirty[0]) &&
  atomic_is_lock_free(&JS_FrameOwnBytecodeDispatch.base[0]);
 /* Keep all environment/parent calls outside the new cold-only lock. */
 unsigned char base_ok=valid && !getenv("QJS_DISABLE_NATIVE_OWN_BYTECODE") &&
  !qjs_internal_interp_frame_disabled() && !qjs_internal_interp_register_disabled()?1:0;
 unsigned char tail_off=qjs_turbo_own_bytecode_tail_disabled()?1:0;
#ifdef QJS_PROPERTY_IC
 unsigned char desired=base_ok ? (tail_off ? 4 : 1) : 2;
#else
 unsigned char desired=(base_ok && !tail_off) ? 1 : 2;
#endif
 unsigned char pic_active=(desired==1 || desired==4)?1:2;
#ifndef _MSC_VER
 unsigned char local_field=pic_active==1 && !getenv("QJS_DISABLE_FRAME_LOCAL_FIELD")?1:2;
#endif
 unsigned char symbol_case=pic_active==1 && !getenv("QJS_DISABLE_SYMBOL_CASE")?1:2;
#if defined(_MSC_VER) && defined(QJS_PROPERTY_IC) && !defined(QJS_INTERP_FRAME_DIAGNOSTICS)
 unsigned char method_learning=pic_active==1 && !getenv("QJS_DISABLE_METHOD_IC_LEARNING")?1:2;
#endif
 atomic_store_explicit(&JS_FrameOwnBytecodeData.abi,valid,memory_order_relaxed);
 own_bytecode_lock();
 if(atomic_load_explicit(&JS_FrameOwnBytecodeData.mode,memory_order_relaxed)==0) {
#ifndef _MSC_VER
  JS_FrameOwnBytecodeData.reserved[1]=local_field;
#endif
  JS_FrameOwnBytecodeData.reserved[3]=pic_active;
  JS_FrameOwnBytecodeData.reserved[4]=symbol_case;
#if defined(_MSC_VER) && defined(QJS_PROPERTY_IC) && !defined(QJS_INTERP_FRAME_DIAGNOSTICS)
  JS_FrameOwnBytecodeData.reserved[2]=method_learning;
#endif
  atomic_store_explicit(&JS_FrameOwnBytecodeDispatch.selected,OWN_PRIVATE_ADDRESS(interp_table),memory_order_relaxed);
  atomic_store_explicit(&JS_FrameOwnBytecodeDispatch.dirty[0],OWN_PRIVATE_ADDRESS(OWN_ORIGINAL_P1),memory_order_relaxed);
  atomic_store_explicit(&JS_FrameOwnBytecodeDispatch.dirty[1],OWN_PRIVATE_ADDRESS(OWN_ORIGINAL_P2),memory_order_relaxed);
  if(pic_active==1) {
   for(unsigned i=0;i<258;i++)
    atomic_store_explicit(&JS_FrameOwnBytecodeDispatch.base[i],((const uintptr_t*)OWN_PRIVATE_ADDRESS(interp_table))[i],memory_order_relaxed);
   atomic_store_explicit(&JS_FrameOwnBytecodeDispatch.base[OWN_BYTECODE_FIELD1],OWN_PRIVATE_ADDRESS(JS_FrameOwnBytecodeM1),memory_order_relaxed);
   atomic_store_explicit(&JS_FrameOwnBytecodeDispatch.base[OWN_BYTECODE_FIELD2],OWN_PRIVATE_ADDRESS(JS_FrameOwnBytecodeM2),memory_order_relaxed);
#ifdef QJS_PROPERTY_IC
   atomic_store_explicit(&JS_FrameOwnBytecodeDispatch.base[OWN_BYTECODE_FIELD3],OWN_PRIVATE_ADDRESS(JS_FrameOwnBytecodeM3),memory_order_relaxed);
#endif
#if OWN_BYTECODE_DIRTY_P
   atomic_store_explicit(&JS_FrameOwnBytecodeDispatch.dirty[0],OWN_PRIVATE_ADDRESS(JS_FrameOwnBytecodeP1),memory_order_relaxed);
   atomic_store_explicit(&JS_FrameOwnBytecodeDispatch.dirty[1],OWN_PRIVATE_ADDRESS(JS_FrameOwnBytecodeP2),memory_order_relaxed);
#endif
   atomic_store_explicit(&JS_FrameOwnBytecodeDispatch.selected,(uintptr_t)JS_FrameOwnBytecodeDispatch.base,memory_order_release);
  }
#if defined(QJS_PROPERTY_IC) && OWN_BYTECODE_DIRTY_P
  atomic_store_explicit(&JS_FrameOwnBytecodeDispatch.put_dirty,
   pic_active==1 ? OWN_PRIVATE_ADDRESS(JS_FrameOwnBytecodeP3) : OWN_PRIVATE_ADDRESS(dirty_interp_put_field),memory_order_release);
#endif
  atomic_store_explicit(&JS_FrameOwnBytecodeData.mode,desired,memory_order_release);
 }
 own_bytecode_unlock();
 qjs_turbo_register_own_bytecode_hooks(JS_FrameOwnBytecodeSetTailMode,JS_FrameOwnBytecodeTailActive);
}
FRAME_CODE void *JS_FrameOwnBytecodeAllocateRT(JSRuntime *rt,size_t count,size_t size) {
 unsigned char mode=atomic_load_explicit(&JS_FrameOwnBytecodeData.mode,memory_order_acquire);
 if(mode!=1) {
  if(mode!=2 && mode!=4) JS_FrameOwnBytecodeDisable();
  return js_calloc_rt(rt,count,size);
 }
 if(size && count>SIZE_MAX/size) {
  JS_FrameOwnBytecodeDisable();return js_calloc_rt(rt,count,size);
 }
 size_t n=count*size,extra=own_bytecode_extra(n);void *p=NULL;
 if(OWN_BYTECODE_DIAG) {
  atomic_fetch_add_explicit(&JS_FrameOwnBytecodeData.allocations,1,memory_order_relaxed);
  atomic_fetch_add_explicit(&JS_FrameOwnBytecodeData.base_bytes,n,memory_order_relaxed);
 }
 if(n<=SIZE_MAX-extra) p=js_calloc_rt(rt,1,n+extra);
 if(p) {
  if(OWN_BYTECODE_DIAG) atomic_fetch_add_explicit(&JS_FrameOwnBytecodeData.reserved_bytes,extra,memory_order_relaxed);
  return p;
 }
 /* Optional reservation failure preserves the original allocation/error ABI.
    Complete cold dispatch restoration and stable OFF are required before exposing an unextended b.
    A concurrent already-entered opcode can only hold an older extended b;
    a QuickJS runtime itself is never executed concurrently by multiple hosts. */
 JS_FrameOwnBytecodeDisable();
 if(OWN_BYTECODE_DIAG) atomic_fetch_add_explicit(&JS_FrameOwnBytecodeData.fallbacks,1,memory_order_relaxed);
 return js_calloc_rt(rt,count,size);
}
FRAME_CODE void *JS_FrameOwnBytecodeAllocateContext(JSContext *ctx,size_t n) {
 /* js_mallocz(ctx,n) is exactly js_calloc_rt(ctx->rt,1,n), plus the original
    context OOM exception. Share the runtime helper's monotonic OFF/fallback
    instead of a second shrink-wrapped reservation implementation. */
 void *p=JS_FrameOwnBytecodeAllocateRT(ctx->rt,1,n);
 if(!p) JS_ThrowOutOfMemory(ctx);
 return p;
}
"""


def generate(source, build, path):
    parent = (_frame_generated_file(build, "quickjs-interpreter-varargs.c")).read_text(
        encoding="utf-8"
    )
    include = next(line for line in parent.splitlines() if line.startswith("#include "))
    start = parent.index("#ifndef QJS_FRAME_CONTEXT_TYPES\n#define QJS_FRAME_CONTEXT_TYPES\n")
    end = parent.index(
        "/* A supported opcode is declared once, for validation and dispatch. */", start
    )
    g = json.loads(
        (_frame_generated_file(build, "quickjs-call-link-vm-generation.json")).read_text(
            encoding="utf-8-sig"
        )
    )
    names = re.findall(
        r"^\s*DEF\(\s*(\w+)",
        _frame_source_file(source, "quickjs-opcode.h").read_text(encoding="utf-8"),
        re.M,
    )
    # The compiler family comes from its recorded command, not an output path.
    cc = Path(
        json.loads(
            (
                _frame_generated_file(build, "quickjs-interpreter-dense-array-pop.compile.json")
            ).read_text(encoding="utf-8-sig")
        )["compiler_command"][0]
    )
    defines = (
        "#define OWN_BYTECODE_DIRTY_P "
        + str(int("P" in g["aliases"]))
        + "\n#define OWN_BYTECODE_SHARED_DIAG "
        + str(int(g["diagnostics"] and cc.name.lower() != "cl.exe"))
        + "\n"
    )
    defines += (
        "#define OWN_BYTECODE_FIELD1 "
        + str(names.index("get_field"))
        + "\n#define OWN_BYTECODE_FIELD2 "
        + str(names.index("get_field2"))
        + "\n"
    )
    defines += "#define OWN_BYTECODE_FIELD3 " + str(names.index("put_field")) + "\n"
    path.write_text(include + "\n" + parent[start:end] + "\n" + defines + BODY, encoding="utf-8")


def source_blocks(build, msvc):
    abi = current_abi()
    fields = abi["offsets"]
    shape_load = f"mov r10, QWORD PTR [r8+{fields['JSObject.shape']}]"
    properties = (
        [f"lea rax, [r10+{fields['JSShape.prop']}]"]
        if abi["reference_count_model"] == "inline-header"
        else [
            f"mov eax, DWORD PTR [r10+{fields['JSShape.prop_hash_mask']}]",
            f"lea rax, [r10+rax*4+{fields['JSShape.hash_table'] + 4}]",
        ]
    )
    g = json.loads(
        (_frame_generated_file(build, "quickjs-call-link-vm-generation.json")).read_text(
            encoding="utf-8-sig"
        )
    )
    from property_ic_native import enabled, blocks as property_blocks

    property_ic_enabled = enabled(build)
    blocks = []
    external = {"JS_FrameOwnBytecodeData", "JS_FrameInterpPropertyCold_unwind"}
    contracts = []
    for tag in g["aliases"]:
        assert tag in ("M", "P")
        filename = (
            "quickjs-interpreter-register-win64.S"
            if tag == "M"
            else "quickjs-interpreter-publish-win64.S"
        )
        text = (_frame_build_file(build, filename)).read_text(encoding="ascii")
        for kind in (1, 2):
            op = "get_field" + ("2" if kind == 2 else "")
            old = ("" if tag == "M" else "dirty_") + "interp_" + op
            following = (
                ("" if tag == "M" else "dirty_")
                + "interp_"
                + ("get_field2" if kind == 1 else "put_field")
            )
            original = text.split(old + ":\n", 1)[1].split(following + ":\n", 1)[0].splitlines()
            assert original and all(x and not x.startswith(".") for x in original)
            p = "own_bytecode_" + tag + str(kind)
            name = "JS_FrameOwnBytecode" + tag + str(kind)
            labelmap = {x[:-1]: p + "_" + x[:-1] for x in original if x.endswith(":")}
            stream = [
                re.sub(r"\b[A-Za-z_]\w*\b", lambda m: labelmap.get(m[0], m[0]), x) for x in original
            ]
            slow = next(
                x.split(" ", 1)[1]
                for x in original
                if x.startswith("jne ") and "property_slow" in x
            )
            assert stream.count(shape_load) == 1
            cut = stream.index(shape_load) + 1
            prefix = stream[:cut]
            rest = stream[cut:]
            found = rest.index("dec ecx")
            assert (
                rest[found - 2 : found] == ["test DWORD PTR [rax], 3221225472", "jnz " + slow]
                and rest[found + 1] == "shl rcx, 4"
            )
            miss = p + "_hash"
            data = p + "_data"
            probe = [
                "mov r11, QWORD PTR [rbp+80]",
                f"mov eax, DWORD PTR [r11+{fields['JSFunctionBytecode.byte_code_len']}]",
                "add eax, 3",
                "and eax, -4",
                "lea r11, [r12+rax]",
                "and r11, -4",
                "movq xmm2, r11",
                "mov ecx, DWORD PTR [r11]",
                "dec ecx",
                f"cmp ecx, DWORD PTR [r10+{fields['JSShape.prop_count']}]",
                "jae " + miss,
                *properties,
                "lea rax, [rax+rcx*8]",
                "cmp DWORD PTR [rax+4], r9d",
                "jne " + miss,
                "test DWORD PTR [rax], 3221225472",
                "jnz " + slow,
            ]
            if g["diagnostics"]:
                probe += ["lock inc QWORD PTR [rip+JS_FrameOwnBytecodeData+" + str(8 * kind) + "]"]
            probe += ["jmp " + data, miss + ":"]
            if g["diagnostics"]:
                probe += ["lock inc QWORD PTR [rip+JS_FrameOwnBytecodeData+32]"]
            fill = ["movq r11, xmm2", "lea eax, [rcx+1]", "mov DWORD PTR [r11], eax"]
            if g["diagnostics"]:
                fill += ["lock inc QWORD PTR [rip+JS_FrameOwnBytecodeData+24]"]
            fill += [data + ":"]
            # The tail reservation still caps at2048. Long-code admission may
            # use IC metadata, but must never index this legacy hint plane.
            long_fallback = p + "_long_original"
            external.add(old)
            length_guard = [
                "mov r11, QWORD PTR [rbp+80]",
                f"cmp DWORD PTR [r11+{fields['JSFunctionBytecode.byte_code_len']}], 2048",
                "ja " + long_fallback,
            ]
            body = [
                *length_guard,
                *prefix,
                *probe,
                *rest[: found + 1],
                *fill,
                *rest[found + 1 :],
                long_fallback + ":",
                "jmp " + old,
            ]
            labels = {x[:-1] for x in body if x.endswith(":")}
            for x in body:
                m = re.fullmatch(r"j\w+ (\w+)", x)
                if m and m[1] not in labels:
                    external.add(m[1])
                assert not re.match(r"^(?:call|ret|push|pop)\b", x) and not re.search(
                    r"\b(?:rsp|esp)\b", x
                ), x
            blocks.append((name, body))
            contracts.append(
                dict(
                    family=tag,
                    kind=kind,
                    entry=name,
                    original_entry=old,
                    original_slow=slow,
                    original_source=filename,
                    original_source_sha256=hashlib.sha256(text.encode("ascii")).hexdigest(),
                    original_handler=original,
                    original_prefix=prefix,
                    cloned_hash_and_probe=rest[: found + 1],
                    cloned_value_rc_dispatch=rest[found + 1 :],
                    cache="Live bytecode allocation tail, align4(code_buf+len)+((PC-code_buf)&~3),uint32 slot+1,zero unknown. Current bounds/atom/data/value proof. No shared cells, cache key, shape/object/value retention or weak owner.",
                    ABI="Original receiver/refcount/PC/SP/RDI contract. Volatile GPR/XMM2 only, no CALL/RSP/allocation/poll/GC in opcode. Existing root VM CFI; bytecode roots own the tail lifetime.",
                    status="unqualified prototype; no performance claim",
                )
            )
    if property_ic_enabled:
        fallbacks = []
        live_names = {}
        for contract, (name, body) in zip(contracts, blocks):
            fallback = name.replace("JS_FrameOwnBytecode", "JS_FrameOwnBytecodeFallback")
            live = fallback + "_live"
            atom = "mov r9d, DWORD PTR [r12+1]"
            assert body.count(atom) == 1
            at = body.index(atom)
            body = body[:at] + [live + ":"] + body[at:]
            live_names[contract["original_entry"]] = live
            contract = dict(
                contract,
                entry=fallback,
                role="Retained R9 slot-hint fallback for dictionary/mega/OFF paths",
            )
            fallbacks.append((fallback, body, contract))
        method_learning = (
            msvc and not g["diagnostics"] and abi["reference_count_model"] == "inline-header"
        )
        if method_learning:
            main = (_frame_build_file(build, "quickjs-interpreter-register-win64.S")).read_text(
                encoding="ascii"
            )
            publication = main.split("interp_property_slow_get_field2:\n", 1)[1].splitlines()[:4]
            assert publication == [
                "mov QWORD PTR [rbx], rbp",
                "mov QWORD PTR [rbx+16], r12",
                "mov QWORD PTR [rbx+24], r13",
                "mov rcx, rbx",
            ]
        primary, new_external, g, new_contracts = property_blocks(
            build, abi, g, fallbacks=live_names, method_learning=method_learning
        )
        blocks = primary + [(name, body) for name, body, _ in fallbacks]
        contracts = new_contracts + [contract for _, _, contract in fallbacks]
        definitions = {name for name, _ in blocks} | {
            line[:-1] for _, body in blocks for line in body if line.endswith(":")
        }
        external = (external | new_external) - definitions
    if not g["diagnostics"] and module(_frame_project_root(), "property_ic_native").enabled(build):
        if msvc:
            # The MSVC VM retains distinct get_var/get_var_undef ready labels.
            # Keep separate stackless entries so every failed guard resumes
            # its exact original opcode without a new dispatch or saved state.
            for kind in ("GetVar", "GetVarUndef"):
                extra, symbols, proof = symbol_global_blocks(
                    abi,
                    source=_frame_project_root(),
                    name="JS_FrameSymbolGlobal" + kind + "Condition",
                    old="JS_FrameSymbolGlobal" + kind + "OriginalReady",
                    prefix="symbol_global_" + kind,
                )
                blocks += extra
                external |= symbols
                contracts += proof
        else:
            extra, symbols, proof = symbol_global_blocks(abi, source=_frame_project_root())
            blocks += extra
            external |= symbols
            contracts += proof
    return blocks, external, g, contracts


def symbol_global_blocks(
    abi,
    source,
    name="JS_FrameSymbolGlobalCondition",
    old="JS_FrameSymbolGlobalOriginalReady",
    prefix="symbol_global",
):
    # Enter only from the existing resolved-cell hit after RAX/RDX are loaded.
    # Avoid a guard on every DUP. Missing cell/accessor/TDZ keeps all old paths.
    names = re.findall(
        r"^\s*DEF\(\s*(\w+)", _frame_source_file(source, "quickjs-opcode.h").read_text(), re.M
    )
    assert abi["reference_count_model"] in ("inline-header", "allocator-prefix")
    ids = {n: i for i, n in enumerate(names)}
    f = abi["offsets"]
    rc = abi_constants(abi)["QJS_ABI_REF_COUNT_OFFSET"]
    p = prefix
    body = [
        "cmp edx, -8",
        "jne " + old,
        "cmp BYTE PTR [rip+JS_FrameOwnBytecodeData+6], 1",
        "jne " + old,
        "cmp QWORD PTR [r13-8], -8",
        "jne " + old,
        "mov r10, QWORD PTR [r13-16]",
        # An arbitrary existing operand need not be a DUP. Last ownership
        # preserves original finalization/C semantics instead of committing.
        f"cmp DWORD PTR [r10{rc:+d}], 1",
        "jle " + old,
        f"cmp DWORD PTR [rsi+{f['JSContext.interrupt_counter']}], 1",
        "jle " + old,
        "mov r8, QWORD PTR [rbp+80]",
        f"mov r9d, DWORD PTR [r8+{f['JSFunctionBytecode.byte_code_len']}]",
        f"mov r11, QWORD PTR [r8+{f['JSFunctionBytecode.byte_code_buf']}]",
        "add r9, r11",
        "lea r8, [r9-11]",
        "cmp r12, r8",
        "ja " + old,
        "cmp r12, r11",
        "jb " + old,
        f"cmp BYTE PTR [r12+5], {ids['strict_eq']}",
        "jne " + old,
        "lea r8, [r12+6]",
        "movzx ecx, BYTE PTR [r8]",
        f"cmp ecx, {ids['if_true8']}",
        "je " + p + "_true8",
        f"cmp ecx, {ids['if_false8']}",
        "je " + p + "_false8",
        f"cmp ecx, {ids['if_true']}",
        "je " + p + "_true32",
        f"cmp ecx, {ids['if_false']}",
        "jne " + old,
        "cmp rax, r10",
        "je " + p + "_fall32",
        "jmp " + p + "_take32",
        p + "_true32:",
        "cmp rax, r10",
        "jne " + p + "_fall32",
        p + "_take32:",
        "movsxd rcx, DWORD PTR [r8+1]",
        "lea r8, [r8+rcx+1]",
        "jmp " + p + "_commit",
        p + "_fall32:",
        "add r8, 5",
        "jmp " + p + "_commit",
        p + "_true8:",
        "cmp rax, r10",
        "jne " + p + "_fall8",
        "jmp " + p + "_take8",
        p + "_false8:",
        "cmp rax, r10",
        "je " + p + "_fall8",
        p + "_take8:",
        "movsx rcx, BYTE PTR [r8+1]",
        "lea r8, [r8+rcx+1]",
        "jmp " + p + "_commit",
        p + "_fall8:",
        "add r8, 2",
        p + "_commit:",
        "cmp r8, r11",
        "jb " + old,
        "cmp r8, r9",
        "jae " + old,
        f"sub DWORD PTR [r10{rc:+d}], 1",
        "sub r13, 16",
        f"dec DWORD PTR [rsi+{f['JSContext.interrupt_counter']}]",
        "mov r12, r8",
        "movzx ecx, BYTE PTR [r12]",
        "jmp QWORD PTR [rdi+rcx*8]",
    ]
    return (
        [(name, body)],
        {"JS_FrameOwnBytecodeData", old},
        [
            dict(
                name=name,
                scope="Exact existing global/lexical resolved-cell hit only. RAX/RDX retained on every failure. Symbol global already owned by binding; consume existing lhs only when it retains another owner. One original conditional poll. No CALL/RSP/allocation/new cache/new owner. Original code/stack/dispatch and ready label on failure.",
            )
        ],
    )


def normalize(source, path):
    C = module(source, "object-adapter")
    co = C.Coff(path.read_bytes())
    changes = []
    for number, r in enumerate(co.section_records, 1):
        for j in range(r["count"]):
            at = r["reloc"] + 10 * j
            off, index, kind = struct.unpack_from("<IIH", co.data, at)
            if 5 <= kind <= 9:
                old = struct.unpack_from("<i", co.data, r["raw"] + off)[0]
                struct.pack_into("<i", co.data, r["raw"] + off, old - (kind - 4))
                struct.pack_into("<H", co.data, at + 8, 4)
                changes.append(
                    dict(
                        section=number,
                        offset=off,
                        old_kind=kind,
                        old_addend=old,
                        new_addend=old - (kind - 4),
                    )
                )
    path.write_bytes(co.finish())
    path.with_name(path.name + ".own-bytecode-rel32.json").write_text(
        json.dumps(dict(status="passed", changes=changes), indent=2) + "\n", encoding="utf-8"
    )


def compile_extra(source, build, msvc):
    out = _frame_generated_file(build, "quickjs-interpreter-own-bytecode.obj")
    module(source, "atod").compile_extra(
        source,
        build,
        out,
        generator=lambda s, p: generate(s, build, p),
        filename="quickjs-interpreter-own-bytecode.c",
        late_name=CODE,
    )
    privatize(out, build, source)
    normalize(source, out)
    prove_no_absolute_initializers(source, build, out)
    prove_cold_storeload(source, build, out, msvc)
    compile_asm(source, build, msvc)


def append_crt(source, build, output):
    C = module(source, "object-adapter")
    N = module(source, "extension-merge")
    raw = output.read_bytes()
    co = C.Coff(raw)
    wanted = "JS_FrameOwnBytecodeConfigure"
    target = [
        i
        for i, s in co.all_symbols.items()
        if s["name"] == wanted and s["section"] > 0 and s["storage"] == 2
    ]
    assert len(target) == 1
    generation = json.loads(
        (
            _frame_generated_file(build, "quickjs-interpreter-own-bytecode-generation.json")
        ).read_text(encoding="utf-8")
    )
    parent = "JS_FrameLengthConfigure" if generation["msvc"] else "JS_FrameProtoDirectConfigure"
    changed = []
    for number, r in enumerate(co.section_records, 1):
        if N.section_name(co, number) != ".CRT$XCU":
            continue
        for j in range(r["count"]):
            at = r["reloc"] + 10 * j
            off, index, kind = struct.unpack_from("<IIH", co.data, at)
            s = co.all_symbols[index]
            if s["name"] != parent:
                continue
            assert kind == 1 and struct.unpack_from("<Q", co.data, r["raw"] + off)[0] == 0
            struct.pack_into("<I", co.data, at + 4, target[0])
            changed.append(
                dict(
                    section=number,
                    offset=off,
                    kind=kind,
                    old_target=parent,
                    new_target=wanted,
                    width=8,
                )
            )
    assert len(changed) == 1, changed
    result = co.finish()
    after = C.Coff(result)
    assert co.all_symbols == after.all_symbols
    for number, (a, b) in enumerate(zip(C.Coff(raw).sections, after.sections), 1):
        assert {k: v for k, v in a.items() if k != "relocations_sha256"} == {
            k: v for k, v in b.items() if k != "relocations_sha256"
        }
        if number != changed[0]["section"]:
            assert a == b
    output.write_bytes(result)
    (_frame_generated_file(build, "quickjs-interpreter-own-bytecode-crt.json")).write_text(
        json.dumps(
            dict(
                status="passed",
                before_sha256=hashlib.sha256(raw).hexdigest(),
                after_sha256=sha(output),
                routes=changed,
                additional_crt_bytes=0,
                all_old_allocated_section_payloads_held=True,
                initialization_order=[parent, wanted],
                policy="Compose the actual existing toolchain CRT initializer, no new early CRT storage or placement setting.",
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def has_tables(co):
    return any(
        s["name"] in ("interp_table", "JS_FramePublishDirtyTable") for s in co.all_symbols.values()
    )


@source_abi
def route_tables(source, build, path, raw, msvc):
    C = module(source, "object-adapter")
    raw, _ = module(source, "call-metadata").packed(raw, C)
    co = C.Coff(raw)
    original = C.Coff(raw)
    routes = []
    exports = []
    cache = {}
    blocks, external_names, g, contracts = source_blocks(build, msvc)
    external_names |= {"interp_table", "interp_get_field", "interp_get_field2"}
    if "P" in g["aliases"]:
        external_names |= {"dirty_interp_get_field", "dirty_interp_get_field2"}
    names = re.findall(
        r"^\s*DEF\(\s*(\w+)",
        _frame_source_file(source, "quickjs-opcode.h").read_text(encoding="utf-8"),
        re.M,
    )

    def external(name):
        if name not in cache:
            hits = [
                i
                for i, s in co.all_symbols.items()
                if s["name"] == name and s["section"] == 0 and s["storage"] == 2
            ]
            cache[name] = hits[0] if hits else co.external(name)
        return cache[name]

    # New C initialization deliberately reads the original RO table. Never
    # redirect those owned references back through the selected pointer.
    owned = {
        s["section"]
        for s in co.all_symbols.values()
        if s["section"] > 0
        and s["name"]
        in (
            "JS_FrameOwnBytecodeConfigure",
            "JS_FrameOwnBytecodeDisable",
            "JS_FrameOwnBytecodeAllocateRT",
            "JS_FrameOwnBytecodeAllocateContext",
            "JS_FrameOwnBytecodeDispatch",
        )
    }
    base = [s for s in co.all_symbols.values() if s["name"] == "interp_table" and s["section"] > 0]
    assert len(base) <= 1
    for number, r in enumerate(co.section_records, 1):
        if not r["flags"] & 0x20000000 or number in owned:
            continue
        for j in range(r["count"]):
            at = r["reloc"] + 10 * j
            off, index, kind = struct.unpack_from("<IIH", co.data, at)
            if kind != 4:
                continue
            sym = co.all_symbols[index]
            addend = struct.unpack_from("<i", co.data, r["raw"] + off)[0]
            match = sym["name"] == "interp_table" and addend == 0
            if base and sym["section"] == base[0]["section"]:
                value = sym["value"] + addend - base[0]["value"]
                if 0 <= value < 2064:
                    assert value == 0, ("unknown base-table arithmetic", path, number, off, value)
                    match = True
            if not match:
                continue
            before = bytes(co.data[r["raw"] + off - 3 : r["raw"] + off + 4])
            assert before[:3] in (b"\x48\x8d\x35", b"\x48\x8d\x3d"), (
                "unknown base reader",
                path,
                number,
                off,
                before.hex(),
            )
            co.data[r["raw"] + off - 2] = 0x8B
            struct.pack_into("<i", co.data, r["raw"] + off, 8)
            struct.pack_into("<I", co.data, at + 4, external("JS_FrameOwnBytecodeDispatch"))
            routes.append(
                dict(
                    role="dispatch base reader",
                    section=number,
                    offset=off,
                    kind=4,
                    instruction_offset=off - 3,
                    old_instruction=before.hex(),
                    new_instruction=bytes(co.data[r["raw"] + off - 3 : r["raw"] + off + 4]).hex(),
                    selected_field_offset=8,
                    old="interp_table",
                    new="JS_FrameOwnBytecodeDispatch.selected",
                    width=7,
                )
            )
    if "P" in g["aliases"]:
        tables = [s for s in co.all_symbols.values() if s["name"] == "JS_FramePublishDirtyTable"]
        assert len(tables) <= 1
        if tables:
            table = tables[0]
            for kind in (1, 2, 3) if len(blocks) > 2 * len(g["aliases"]) else (1, 2):
                current_symbols = C.Coff(co.finish()).all_symbols
                op = "put_field" if kind == 3 else "get_field" + ("2" if kind == 2 else "")
                opcode = names.index(op)
                oldname = "dirty_interp_" + op
                oldhits = [s for s in co.all_symbols.values() if s["name"] == oldname]
                assert len(oldhits) <= 1
                old = oldhits[0] if oldhits else None
                for number, r in enumerate(co.section_records, 1):
                    if not r["flags"] & 0x20000000 or number in owned:
                        continue
                    rels = {
                        struct.unpack_from("<I", co.data, r["reloc"] + 10 * j)[0]: (
                            j,
                            *struct.unpack_from("<IIH", co.data, r["reloc"] + 10 * j)[1:],
                        )
                        for j in range(r["count"])
                    }
                    for off, (j, target, relkind) in rels.items():
                        if relkind != 4:
                            continue
                        sym = current_symbols[target]
                        addend = struct.unpack_from("<i", co.data, r["raw"] + off)[0]
                        if (
                            sym["section"] != table["section"]
                            or sym["value"] + addend != table["value"] + opcode * 8
                        ):
                            continue
                        if table["section"] == 0 and sym["name"] != table["name"]:
                            continue
                        assert old is not None, (
                            "unbound dirty initializer",
                            path,
                            number,
                            off,
                            oldname,
                        )
                        at = r["raw"] + off
                        assert (
                            bytes(co.data[at - 10 : at - 7]) == b"\x4c\x8d\x15"
                            and bytes(co.data[at - 3 : at]) == b"\x4c\x89\x15"
                        )
                        operand = off - 7
                        previous = struct.unpack_from("<i", co.data, r["raw"] + operand)[0]
                        before = bytes(co.data[r["raw"] + operand - 3 : r["raw"] + operand + 4])
                        oldrel = rels.get(operand)
                        target = external("JS_FrameOwnBytecodeDispatch")
                        selected = 2096 if kind == 3 else 16 + 8 * (kind - 1)
                        if oldrel:
                            num, index, reltype = oldrel
                            v = co.all_symbols[index]
                            assert (
                                reltype == 4
                                and v["section"] == old["section"]
                                and v["value"] + previous == old["value"]
                            )
                            assert old["section"] > 0 or v["name"] == old["name"]
                            struct.pack_into("<I", co.data, r["reloc"] + 10 * num + 4, target)
                        else:
                            assert (
                                number == old["section"] and operand + 4 + previous == old["value"]
                            )
                            co.extra_relocations.setdefault(number, []).append(
                                struct.pack("<IIH", operand, target, 4)
                            )
                        co.data[r["raw"] + operand - 2] = 0x8B
                        struct.pack_into("<i", co.data, r["raw"] + operand, selected)
                        routes.append(
                            dict(
                                role="dirty table initializer",
                                section=number,
                                offset=operand,
                                kind=4,
                                instruction_offset=operand - 3,
                                old_instruction=before.hex(),
                                new_instruction=bytes(
                                    co.data[r["raw"] + operand - 3 : r["raw"] + operand + 4]
                                ).hex(),
                                selected_field_offset=selected,
                                old=oldname,
                                new="JS_FrameOwnBytecodeDispatch.dirty",
                                slot=opcode,
                                width=7,
                                source_relocation=bool(oldrel),
                            )
                        )
    for index, s in list(co.all_symbols.items()):
        if s["name"] in external_names and s["section"] > 0 and s["storage"] in (3, 6):
            assert not co.section_records[s["section"] - 1]["flags"] & 0x1000, (
                "Do not alter COMDAT identity",
                s,
            )
            co.data[co.table + index * co.stride + co.class_offset] = 2
            exports.append(
                dict(name=s["name"], index=index, old_storage=s["storage"], new_storage=2)
            )
    if not routes and not exports:
        return raw, None
    result = co.finish()
    after = C.Coff(result)
    restored = bytearray(result)
    for row in routes:
        r = after.section_records[row["section"] - 1]
        start = r["raw"] + row["instruction_offset"]
        restored[start : start + 7] = bytes.fromhex(row["old_instruction"])
    assert [s["sha256"] for s in C.Coff(restored).sections] == [
        s["sha256"] for s in original.sections
    ]
    folder = _frame_generated_file(build, "own-bytecode-link")
    folder.mkdir(exist_ok=True)
    receipt = folder / (path.name + ".json")
    assert not receipt.exists()
    receipt.write_text(
        json.dumps(
            dict(
                status="passed",
                input=str(path),
                input_sha256=hashlib.sha256(raw).hexdigest(),
                output_sha256=hashlib.sha256(result).hexdigest(),
                routes=routes,
                exposed=exports,
                old_RO_base_dispatch_cells_unchanged=True,
                all_other_section_bytes_held=True,
                policy="Exact seven-byte LEA-to-MOV instruction witnesses and typed or proven local targets only; selected cells are aligned RW pointers. All original table identities and non-property cells preserved.",
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return result, str(receipt)


def privatize(output, build, source):
    C = module(source, "object-adapter")
    raw = output.read_bytes()
    co = C.Coff(raw)
    renamed = []
    commons = []
    for index, s in co.all_symbols.items():
        if s["section"] == 0 and s["storage"] == 2 and s["value"]:
            providers = []
            for p in (
                _frame_build_file(build, "CMakeFiles/qjs-core.dir/quickjs.c.obj"),
                _frame_build_file(
                    build, "CMakeFiles/qjs.dir/src/x86/win64/common/quickjs-interpreter.c.obj"
                ),
            ):
                pc = C.Coff(p.read_bytes())
                if any(
                    v["name"] == s["name"]
                    and v["storage"] == 2
                    and (v["section"] > 0 or (v["section"] == 0 and v["value"] >= s["value"]))
                    for v in pc.all_symbols.values()
                ):
                    providers.append(str(p))
            assert providers, ("No common provider", s)
            struct.pack_into("<I", co.data, co.table + index * co.stride + 8, 0)
            commons.append(dict(name=s["name"], bytes=s["value"], providers=providers))
        if (
            s["section"] > 0
            and s["storage"] == 2
            and not s["name"].startswith("JS_FrameOwnBytecode")
        ):
            name = "own_bytecode_emitted_" + hashlib.sha256(s["name"].encode()).hexdigest()[:32]
            at = len(co.strings)
            co.strings += name.encode() + b"\0"
            struct.pack_into("<II", co.data, co.table + index * co.stride, 0, at)
            renamed.append(dict(old=s["name"], new=name))
    backup = output.with_name(output.name + ".unrenamed")
    assert not backup.exists()
    backup.write_bytes(raw)
    output.write_bytes(co.finish())
    assert C.Coff(raw).sections == C.Coff(output.read_bytes()).sections
    output.with_name(output.name + ".private-symbols.json").write_text(
        json.dumps(
            dict(
                status="passed",
                input_sha256=sha(backup),
                output_sha256=sha(output),
                renamed=renamed,
                commons=commons,
                section_bytes_held=True,
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


@source_abi
def compile_asm(source, build, msvc):
    C = module(source, "object-adapter")
    merge = module(source, "extension-merge")
    blocks, external, generation, contracts = source_blocks(build, msvc)
    compiler = Path(
        json.loads(
            (
                _frame_generated_file(build, "quickjs-interpreter-dense-array-pop.compile.json")
            ).read_text(encoding="utf-8-sig")
        )["compiler_command"][0]
    )
    co = C.Coff((_frame_generated_file(build, "quickjs-interpreter-own-bytecode.obj")).read_bytes())
    c_pdata = sum(
        r["size"]
        for i, r in enumerate(co.section_records, 1)
        if merge.section_name(co, i).startswith(".pdata")
    )
    parent_generation = _frame_build_file(
        build,
        "quickjs-interpreter-length-generation.json"
        if msvc
        else "quickjs-interpreter-proto-direct-generation.json",
    )
    parent_capacity = json.loads(parent_generation.read_text(encoding="utf-8"))["capacity"]
    capacity = parent_capacity + c_pdata + 12 * len(blocks)
    header = MAGIC + bytes(16)
    footer = FOOTER + struct.pack("<II", capacity, 1) + bytes(capacity)
    asm = _frame_build_file(
        build,
        "quickjs-interpreter-own-bytecode.asm" if msvc else "quickjs-interpreter-own-bytecode.S",
    )
    obj = _frame_generated_file(build, "quickjs-interpreter-own-bytecode-asm.obj")
    if msvc:
        lines = [
            "OPTION CASEMAP:NONE",
            "OPTION DOTNAME",
            *["EXTERN " + name + ":BYTE" for name in sorted(external)],
            CODE + " SEGMENT ALIGN(16) 'CODE'",
        ]
        for name, stream in blocks:
            lines += ["ALIGN 16", "PUBLIC " + name + ", " + name + "_end", name + " PROC"]
            for line in stream:
                line = line.replace("rip+", "")
                if line.endswith(":"):
                    lines += ["PUBLIC " + line[:-1], line[:-1] + "::"]
                else:
                    lines.append(re.sub(r"^(j\w+) (\w+)$", r"\1 NEAR PTR \2", line))
            lines += [name + "_end LABEL BYTE", name + " ENDP"]
        lines += [CODE + " ENDS", ".pdata$zzzzzznullfast SEGMENT ALIGN(4) READONLY 'DATA'"]
        for name, _ in blocks:
            lines += [
                "DD IMAGEREL "
                + name
                + ", IMAGEREL "
                + name
                + "_end, IMAGEREL JS_FrameInterpPropertyCold_unwind"
            ]
        lines += [".pdata$zzzzzznullfast ENDS"]
        for name, payload in ((CFI + "$A", header), (CFI + "$Z", footer)):
            lines += [name + " SEGMENT ALIGN(4) READONLY 'CODE'"]
            for i in range(0, len(payload), 32):
                lines += ["DB " + ",".join(str(b) for b in payload[i : i + 32])]
            lines += [name + " ENDS"]
        lines += ["END"]
        command = [str(compiler.with_name("ml64.exe")), "/nologo", "/c", "/Fo" + str(obj), str(asm)]
    else:
        lines = [".intel_syntax noprefix", ".section " + CODE + ',"xr"']
        for name, stream in blocks:
            lines += [
                ".p2align 4",
                ".globl " + name + ", " + name + "_end",
                ".def " + name + "; .scl 2; .type 32; .endef",
                name + ":",
                *stream,
                name + "_end:",
            ]
        lines += ['.section .pdata$zzzzzznullfast,"dr"', ".p2align 2"]
        for name, _ in blocks:
            lines += [".rva " + name + ", " + name + "_end, JS_FrameInterpPropertyCold_unwind"]
        for name, payload in ((CFI + "$A", header), (CFI + "$Z", footer)):
            lines += [".section " + name + ',"xr"', ".p2align 2"]
            nonzero = len(payload) if name.endswith("$A") else 24
            lines += [".byte " + ",".join(map(str, payload[:nonzero]))]
            if len(payload) > nonzero:
                lines += [".zero " + str(len(payload) - nonzero)]
        command = [str(compiler), "-g0", "-c", str(asm), "-o", str(obj)]
    asm.write_text("\n".join(lines) + "\n", encoding="ascii")
    env = dict(os.environ)
    env["PATH"] = str(compiler.parent) + ";" + env["PATH"]
    p = subprocess.run(
        command, capture_output=True, env=env, creationflags=subprocess.CREATE_NO_WINDOW
    )
    log = asm.with_suffix(".compile.log")
    log.write_bytes(p.stdout + p.stderr)
    assert p.returncode == 0, (command, (p.stdout + p.stderr).decode(errors="replace")[-2000:])
    # MASM REL32_n operands are canonicalized exactly like the inherited VM.
    co = C.Coff(obj.read_bytes())
    corrections = []
    for r in co.section_records:
        for j in range(r["count"]):
            at = r["reloc"] + 10 * j
            off, index, kind = struct.unpack_from("<IIH", co.data, at)
            if 5 <= kind <= 9:
                assert msvc
                value = struct.unpack_from("<i", co.data, r["raw"] + off)[0]
                struct.pack_into("<i", co.data, r["raw"] + off, value - (kind - 4))
                struct.pack_into("<H", co.data, at + 8, 4)
                corrections.append(dict(offset=off, kind=kind))
    obj.write_bytes(co.finish())
    (_frame_generated_file(build, "quickjs-interpreter-own-bytecode-generation.json")).write_text(
        json.dumps(
            dict(
                status="passed",
                msvc=msvc,
                diagnostics=generation["diagnostics"],
                asm=str(asm),
                asm_sha256=sha(asm),
                object=str(obj),
                object_sha256=sha(obj),
                compiler_command=command,
                blocks=[name for name, _ in blocks],
                contracts=contracts,
                rel32_corrections=corrections,
                capacity=capacity,
                compiler_pdata_bytes=c_pdata,
                native_pdata_bytes=12 * len(blocks),
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def append_module(source, build, output, msvc, group, prefix, owner, merge):
    C = module(source, "object-adapter")
    old = C.Coff(output.read_bytes())
    # Miss is an actual MSVC leaf with no native record; Configure owns compiler
    # CFI. Keep all contributions while anchoring the strict merger to that CFI.
    merge.append(
        output,
        _frame_generated_file(build, "quickjs-interpreter-own-bytecode.obj"),
        "JS_FrameOwnBytecodeConfigure",
        "own-bytecode-c",
        keep_all=True,
        code_input=CODE,
        code_output=CODE + "$C",
        pdata_output=CFI + "$B",
        metadata_inputs=(".voltbl",) if msvc else (),
        writable_metadata_inputs=(RW,),
        base_owner=owner,
        baseline_sections=(),
    )
    merge.append(
        output,
        _frame_generated_file(build, "quickjs-interpreter-own-bytecode-asm.obj"),
        "JS_FrameOwnBytecodeM1",
        "own-bytecode-asm",
        keep_all=True,
        code_input=CODE,
        code_output=CODE + "$A",
        pdata_output=CFI + "$C",
        allocated_metadata_inputs=(CFI + "$A", CFI + "$Z"),
        base_owner=owner,
        baseline_sections=(),
    )
    raw = bytearray(output.read_bytes())
    co = C.Coff(raw)
    for i, r in enumerate(co.section_records, 1):
        if i <= old.count:
            continue
        if merge.section_name(co, i).startswith(CFI):
            struct.pack_into("<I", raw, r["pos"] + 36, (r["flags"] & ~0xE00000E0) | 0x40000040)
        if merge.section_name(co, i).startswith(CODE):
            struct.pack_into("<I", raw, r["pos"] + 36, (r["flags"] & ~0xE0) | 0x60000040)
    output.write_bytes(raw)
    if msvc:
        use_parent_ms_groups(source, build, output, old.count)
    append_crt(source, build, output)


def packet(image):
    raw = bytearray(image.read_bytes())
    pe = struct.unpack_from("<I", raw, 60)[0]
    opt = pe + 24
    at = opt + struct.unpack_from("<H", raw, pe + 20)[0]
    sections = []
    for i in range(struct.unpack_from("<H", raw, pe + 6)[0]):
        pos = at + 40 * i
        name = raw[pos : pos + 8].rstrip(b"\0").decode("ascii")
        size, rva, physical_size, physical = struct.unpack_from("<IIII", raw, pos + 8)
        sections.append(
            dict(
                name=name,
                size=size,
                rva=rva,
                physical_size=physical_size,
                physical=physical,
                flags=struct.unpack_from("<I", raw, pos + 36)[0],
            )
        )
    found = [
        s
        for s in sections
        if s["name"] == CFI
        or (s["name"] == ".qjzzlf" and MAGIC in raw[s["physical"] : s["physical"] + s["size"]])
    ]
    if not found:
        return None
    assert len(found) == 1
    s = found[0]
    assert s["flags"] & 0xE0000000 == 0x40000000
    data = raw[s["physical"] : s["physical"] + s["size"]]
    starts = [i for i in range(len(data)) if data.startswith(MAGIC, i)]
    assert len(starts) == 1
    start = starts[0]
    ends = [i for i in range(len(data)) if data.startswith(FOOTER, i)]
    assert len(ends) == 1
    end = ends[0]
    assert end > start + 32 and (end - start - 32) % 12 == 0
    native = [bytes(data[i : i + 12]) for i in range(start + 32, end, 12)]
    capacity, version = struct.unpack_from("<II", data, end + 16)
    assert version == 1 and end + 24 + capacity <= s["size"]
    return raw, opt, sections, s, native, end + 24, capacity


def strip_native_before_parent(image):
    """Parent's fixed RO packet never receives this independent contribution."""
    p = packet(image)
    if not p:
        return
    raw, opt, sections, s, native, relative, capacity = p
    directory = opt + 112 + 3 * 8
    rva, size = struct.unpack_from("<II", raw, directory)
    current = next(
        v for v in sections if v["rva"] <= rva and rva + size <= v["rva"] + v["physical_size"]
    )
    off = current["physical"] + rva - current["rva"]
    rows = [bytes(raw[i : i + 12]) for i in range(off, off + size, 12)]
    extra = set(native)
    filtered = [r for r in rows if r not in extra]
    if len(filtered) == len(rows):
        return
    table = b"".join(filtered)
    assert len(table) <= capacity
    target = s["physical"] + relative
    raw[target : target + capacity] = table + bytes(capacity - len(table))
    struct.pack_into("<II", raw, directory, s["rva"] + relative, len(table))
    image.write_bytes(raw)


def finalize_image(image, previous):
    p = packet(image)
    if not p:
        return previous
    raw, opt, sections, s, native, relative, capacity = p
    directory = opt + 112 + 3 * 8
    rva, size = struct.unpack_from("<II", raw, directory)
    current = next(
        v for v in sections if v["rva"] <= rva and rva + size <= v["rva"] + v["physical_size"]
    )
    off = current["physical"] + rva - current["rva"]
    inherited = [bytes(raw[i : i + 12]) for i in range(off, off + size, 12)]
    rows = sorted(set(inherited) | set(native), key=lambda r: struct.unpack_from("<I", r)[0])
    end = 0
    for row in rows:
        begin, stop, uw = struct.unpack("<III", row)
        assert end <= begin < stop and uw
        end = stop
        for address, length in ((begin, stop - begin), (uw, 4)):
            assert any(
                v["rva"] <= address and address + length <= v["rva"] + v["physical_size"]
                for v in sections
            )
    table = b"".join(rows)
    assert len(table) <= capacity
    target = s["physical"] + relative
    raw[target : target + capacity] = table + bytes(capacity - len(table))
    struct.pack_into("<II", raw, directory, s["rva"] + relative, len(table))
    before = sha(image)
    if raw != image.read_bytes():
        image.write_bytes(raw)
    return dict(
        status="passed",
        image=str(image),
        before_sha256=before,
        image_sha256=sha(image),
        inherited_finalization=previous,
        own_bytecode_rows=len(native),
        combined_rows=len(rows),
        capacity=capacity,
        directory_rva=s["rva"] + relative,
        all_inherited_rows_retained=True,
        native_storage_readonly=True,
        policy="Independent final RO directory and PE exception pointer only; parent packet kept free of new contribution. No executable or old RW bytes/addresses changed by finalization.",
    )


"""Exact creator allocation CALL operands only; no constructor/core recompilation."""


def bytecode_source_contract(source):
    text = _frame_source_file(source, "quickjs.c").read_text(encoding="utf-8")
    lines = text.splitlines()
    layout = load_layout(source)
    alloc = [
        i + 1 for i, x in enumerate(lines) if x.strip() == "b = js_mallocz(ctx, function_size);"
    ]
    assert len(alloc) == 2, ("Need inventory of every bytecode creator", alloc)
    for before in ("function_size += fd->byte_code.size;", "function_size += bc.byte_code_len;"):
        i = next(i for i, x in enumerate(lines) if x.strip() == before)
        assert lines[i - 1].strip() == "byte_code_offset = function_size;"
        assert (
            lines[i + 1].strip() == ""
            and lines[i + 2].strip() == "b = js_mallocz(ctx, function_size);"
        )
    assert sum(bool(re.search(r"\bb->byte_code_buf\s*=", x)) for x in lines) == 2
    assert (
        "bc_buf = (uint8_t*)b + byte_code_offset;" in text and "b->byte_code_buf = bc_buf;" in text
    )
    assert "b->byte_code_buf = (void *)((uint8_t*)b + byte_code_offset);" in text
    assert "BC_READ_FLAG_ROM_DATA" not in text and "read_only_bytecode" not in text
    for size_prefix in ("fd", "bc"):
        member = "fd->" if size_prefix == "fd" else "bc."
        if layout["reference_count_model"] == "allocator-prefix":
            expected = (
                "    function_size = sizeof(*b);\n"
                "    cpool_offset = (function_size + 7) & ~7;\n"
                "    function_size = cpool_offset + "
                + member
                + "cpool_count * sizeof(*"
                + member
                + "cpool);"
            )
        else:
            assert layout["reference_count_model"] == "inline-header"
            assert layout["sizes"]["JSFunctionBytecode"] % 8 == 0
            expected = (
                "    function_size = sizeof(*b);\n"
                "    cpool_offset = function_size;\n"
                "    function_size += " + member + "cpool_count * sizeof(*" + member + "cpool);"
            )
        assert text.count(expected) == 1, ("Need4-aligned producer seed", size_prefix)
    assert "function_size += (fd->arg_count + fd->var_count) * sizeof(*b->vardefs);" in text
    assert "function_size += fd->closure_var_count * sizeof(*fd->closure_var);" in text
    assert "function_size += local_count * sizeof(*bc.vardefs);" in text
    assert "function_size += bc.closure_var_count * sizeof(*bc.closure_var);" in text
    opcode = _frame_source_file(source, "quickjs-opcode.h").read_text(encoding="utf-8")
    for name in ("get_field", "get_field2"):
        assert len(re.findall(r"^\s*DEF\(\s*" + name + r"\s*,\s*5\s*,", opcode, re.M)) == 1, (
            "Need5-byte property opcodes",
            name,
        )
    return dict(
        source_sha256=sha(_frame_source_file(source, "quickjs.c")),
        allocation_source_lines=alloc,
        bytecode_is_final_member_in_both_creators=True,
        all_bytecode_buffer_assignments_enumerated=True,
        reservation="Schema2,extra=6+min(original_function_allocation_bytes,FRAME_MAX_CODE2048). Both producers4-align code_buf. Cell=align4(code_end)+(PC_offset&~3)=(PC&~3)+ceil4(code_len). All property instructions are5bytes, so distinct valid starts have distinct floor(PC/4), with no collisions. Pad<=3;ceil4(len)<=len+3;fresh plane end<=old_end+6+len<=old_end+extra. Bound is conservative,not exact minimal metadata.",
        fallback="Optional nonthrowing enlarged calloc failure or pre-CRT allocation permanently disables native hint mode before returning an original-size block. Configure CAS can initialize only mode0 and never reenables mode2. Existing ON opcode has no C/GC safepoint and can only hold a previously enlarged live bytecode. No weak owner or extra JS roots.",
    )


def decoded_allocation_refcount_path(decoded, first, ref_offset):
    """Prove the non-null return edge reaches an allocated-pointer RC store.

    MSVC can move the failure block/epilogue between CALL and success. Follow
    the decoded null test rather than increasing an arbitrary byte window.
    Only pointer copies, the null test and its explicit branch are admitted.
    """
    aliases = {"rax"}
    pc = first
    nonnull = False
    operand = (
        r"(?:\+0x0)?"
        if ref_offset == 0
        else re.escape(("+" if ref_offset > 0 else "-") + "0x" + format(abs(ref_offset), "x"))
    )
    store = re.compile(r"^mov\s+DWORD PTR \[(\w+)" + operand + r"\],0x1$")
    for _ in range(8):
        if pc not in decoded:
            return []
        row = decoded[pc]
        instruction = row["instruction"]
        match = store.fullmatch(instruction)
        if match:
            return [row] if nonnull and match[1] in aliases else []
        match = re.fullmatch(r"mov\s+(r\w+),(r\w+)", instruction)
        if match and match[2] in aliases:
            aliases.add(match[1])
            pc += len(bytes.fromhex(row["code"]))
            continue
        match = re.fullmatch(r"test\s+(r\w+),\1", instruction)
        if match and match[1] in aliases:
            branch_pc = pc + len(bytes.fromhex(row["code"]))
            branch = decoded.get(branch_pc)
            if not branch:
                return []
            edge = re.fullmatch(r"(je|jz|jne|jnz)\s+0x([0-9a-f]+)", branch["instruction"])
            if not edge:
                return []
            nonnull = True
            pc = (
                row["function_start"] + int(edge[2], 16)
                if edge[1] in ("jne", "jnz")
                else branch_pc + len(bytes.fromhex(branch["code"]))
            )
            continue
        return []
    return []


def core_allocation_sites(source, build, path, raw, msvc):
    C = module(source, "object-adapter")
    co = C.Coff(raw)
    contract = bytecode_source_contract(source)
    ref_offset = abi_constants(load_layout(source))["QJS_ABI_REF_COUNT_OFFSET"]

    def functions(section):
        out = {}
        for s in co.all_symbols.values():
            if s["section"] == section and s["type"] == 32:
                out.setdefault(s["value"], set()).add(s["name"])
        return out

    def owner(section, address):
        f = functions(section)
        at = max(v for v in f if v <= address)
        return (
            sorted(f[at]),
            at,
            min([v for v in f if v > at] + [co.section_records[section - 1]["size"]]),
        )

    sites = []
    if msvc:
        for name, expected_count, target in (
            ("js_create_function", 1, "js_calloc_rt"),
            ("JS_ReadFunctionTag", 3, "js_mallocz"),
        ):
            ss = co.symbols[name]
            rr = co.section_records[ss["section"] - 1]
            _, start, end = owner(ss["section"], ss["value"])
            matches = []
            for j in range(rr["count"]):
                at = rr["reloc"] + 10 * j
                off, index, kind = struct.unpack_from("<IIH", co.data, at)
                if not start <= off < end or co.all_symbols[index]["name"] != target:
                    continue
                assert kind == 4 and co.data[rr["raw"] + off - 1] == 0xE8
                matches.append((off, at, index))
            assert len(matches) == expected_count, (
                name,
                "allocator ABI/creator inventory changed",
                matches,
            )
            off, at, index = min(matches)
            # The first allocation initializes the bytecode refcount. Later
            # optional debug/source buffers in ReadFunctionTag do not. Decode
            # the exact function bytes so inline/prefix RC checks cannot match
            # bytes inside another instruction. A small raw slice also avoids
            # quadratic whole-COFF section/symbol traversal in GNU objdump.
            directory = _frame_generated_file(build, "own-bytecode-allocator-witness")
            directory.mkdir(exist_ok=True)
            binary = directory / (name + ".bin")
            binary.write_bytes(co.data[rr["raw"] + start : rr["raw"] + end])
            command = [
                str(find_objdump(build)),
                "-D",
                "-b",
                "binary",
                "-m",
                "i386:x86-64",
                "-w",
                "-Mintel",
                str(binary),
            ]
            listing = subprocess.run(
                command, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW
            )
            assert listing.returncode == 0, listing.stderr
            binary.with_suffix(".log").write_bytes(listing.stdout + listing.stderr)
            displacement = (
                ""
                if ref_offset == 0
                else ("+" if ref_offset > 0 else "-") + "0x" + format(abs(ref_offset), "x")
            )
            operand = re.escape(displacement) if displacement else r"(?:\+0x0)?"
            store = re.compile(
                r"^mov\s+DWORD PTR \[(r(?:ax|bx|cx|dx|si|di|bp|[89]|1[0-5]))" + operand + r"\],0x1$"
            )
            witnesses = []
            decoded_rows = {}
            for line in listing.stdout.decode("ascii", errors="replace").splitlines():
                decoded = re.match(r"^\s*([0-9a-f]+):\s+((?:[0-9a-f]{2}\s+)+)(.*?)\s*$", line)
                if not decoded:
                    continue
                address = start + int(decoded[1], 16)
                code = bytes.fromhex(decoded[2])
                decoded_rows[address] = dict(
                    offset=address, code=code.hex(), instruction=decoded[3], function_start=start
                )
                if off + 4 <= address < min(end, off + 132) and store.fullmatch(decoded[3]):
                    assert code == bytes(
                        co.data[rr["raw"] + address : rr["raw"] + address + len(code)]
                    )
                    witnesses.append(dict(offset=address, code=code.hex(), instruction=decoded[3]))
            if not witnesses:
                witnesses = decoded_allocation_refcount_path(decoded_rows, off + 4, ref_offset)
                for witness in witnesses:
                    address = witness["offset"]
                    code = bytes.fromhex(witness["code"])
                    assert code == bytes(
                        co.data[rr["raw"] + address : rr["raw"] + address + len(code)]
                    )
            assert witnesses, (
                name,
                "need independent decoded allocated-b refcount witness",
                ref_offset,
            )
            sites.append(
                dict(
                    section=ss["section"],
                    offset=off,
                    caller=name,
                    old_target=target,
                    existing_relocation_at=at,
                    old_symbol=index,
                    old_bytes=bytes(co.data[rr["raw"] + off : rr["raw"] + off + 4]).hex(),
                    source_line=contract["allocation_source_lines"][
                        0 if name == "js_create_function" else 1
                    ],
                    ref_count_offset=ref_offset,
                    ref_count_witnesses=witnesses,
                    function_slice_sha256=sha(binary),
                    decoded_sha256=hashlib.sha256(listing.stdout).hexdigest(),
                    locator="Complete retained creator function, exact typed allocator CALL inventory and decoded first allocated-bytecode refcount initialization witness; source still has exactly two tail-final allocations.",
                )
            )
    else:
        cc = Path(
            json.loads(
                (
                    _frame_generated_file(build, "quickjs-interpreter-dense-array-pop.compile.json")
                ).read_text(encoding="utf-8-sig")
            )["compiler_command"][0]
        )
        objdump = cc.with_name("objdump.exe")
        assert path.read_bytes() == raw, (
            "GNU disassembly/debug-line binding must use exact supplied input"
        )
        p = subprocess.run(
            [str(objdump), "--dwarf=decodedline", str(path)],
            capture_output=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        assert p.returncode == 0
        decoded = p.stdout.decode("utf-8", errors="replace")
        line_positions = {}
        for x in decoded.splitlines():
            m = re.match(r"^\s*quickjs\.c\s+(\d+)\s+(0x[0-9a-fA-F]+)", x)
            if m:
                line_positions.setdefault(int(m[2], 16), set()).add(int(m[1]))
        ordered = sorted(line_positions)
        assert ordered, "GNU bytecode allocator routing requires core DWARF source line tables"
        sections = [i + 1 for i, s in enumerate(co.sections) if s["name"] == ".text"]
        assert len(sections) == 1
        section = sections[0]
        rr = co.section_records[section - 1]
        listing = subprocess.run(
            [str(objdump), "-d", "-w", "-M", "intel", "-j", ".text", str(path)],
            capture_output=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        assert listing.returncode == 0
        import bisect

        for x in listing.stdout.decode("utf-8", errors="replace").splitlines():
            m = re.match(r"^\s*([0-9a-f]+):\s+((?:[0-9a-f]{2}[ \t]+)+)(\S.*)$", x)
            if not m:
                continue
            address = int(m[1], 16)
            code = bytes.fromhex(m[2])
            if len(code) != 5 or code[0] != 0xE8:
                continue
            q = bisect.bisect_right(ordered, address) - 1
            if q < 0:
                continue
            wanted = line_positions[ordered[q]] & set(contract["allocation_source_lines"])
            if not wanted:
                continue
            target = address + 5 + struct.unpack_from("<i", code, 1)[0]
            found = [
                s["name"]
                for s in co.all_symbols.values()
                if s["section"] == section
                and s["value"] == target
                and s["name"] in ("js_mallocz", "js_calloc_rt")
            ]
            if not found:
                continue
            assert (
                len(wanted) == len(found) == 1
                and bytes(co.data[rr["raw"] + address : rr["raw"] + address + 5]) == code
            )
            names, start, end = owner(section, address)
            caller = next(
                (n for n in names if n in ("js_create_function", "JS_ReadObjectRec")), None
            )
            assert caller, (names, address)
            reloc = []
            for j in range(rr["count"]):
                at = rr["reloc"] + 10 * j
                off, index, kind = struct.unpack_from("<IIH", co.data, at)
                if off == address + 1:
                    reloc.append((at, index, kind))
            assert not reloc, ("Need typed-relocation GNU support for changed compiler", reloc)
            sites.append(
                dict(
                    section=section,
                    offset=address + 1,
                    caller=caller,
                    old_target=found[0],
                    old_bytes=code[1:].hex(),
                    source_line=next(iter(wanted)),
                    decoded_line_sha256=hashlib.sha256(p.stdout).hexdigest(),
                    locator="Genuine decoded five-byte CALL; exact original source allocation line interval, owner function and unspecialized standard allocator target, no relocation. Reader is inlined into JS_ReadObjectRec.",
                )
            )
        assert sorted(s["source_line"] for s in sites) == sorted(
            contract["allocation_source_lines"]
        ), ("Need every bytecode creator allocation, no extras", sites)
    assert len(sites) == 2 and {s["caller"] for s in sites} == (
        {"js_create_function", "JS_ReadFunctionTag"}
        if msvc
        else {"js_create_function", "JS_ReadObjectRec"}
    )
    return sites, contract


def route_core_allocations(source, build, path, raw, msvc):
    C = module(source, "object-adapter")
    before = path.with_name(path.name + ".before-own-bytecode-allocators")
    assert not before.exists()
    before.write_bytes(raw)
    sites, contract = core_allocation_sites(source, build, before, raw, msvc)
    co = C.Coff(raw)
    original = C.Coff(raw)
    for row in sites:
        target = (
            "JS_FrameOwnBytecodeAllocateRT"
            if row["old_target"] == "js_calloc_rt"
            else "JS_FrameOwnBytecodeAllocateContext"
        )
        index = co.external(target)
        row["new_target"] = target
        row["new_symbol"] = index
        if "existing_relocation_at" in row:
            struct.pack_into("<I", co.data, row["existing_relocation_at"] + 4, index)
        else:
            rr = co.section_records[row["section"] - 1]
            struct.pack_into("<i", co.data, rr["raw"] + row["offset"], 0)
            co.extra_relocations.setdefault(row["section"], []).append(
                struct.pack("<IIH", row["offset"], index, 4)
            )
    result = co.finish()
    after = C.Coff(result)
    restored = bytearray(result)
    for row in sites:
        rr = after.section_records[row["section"] - 1]
        restored[rr["raw"] + row["offset"] : rr["raw"] + row["offset"] + 4] = bytes.fromhex(
            row["old_bytes"]
        )
    assert [s["sha256"] for s in C.Coff(restored).sections] == [
        s["sha256"] for s in original.sections
    ]
    for name in ("JS_CallInternal", "JS_LegacyCall"):
        assert original.symbols[name] == after.symbols[name]
    out = _frame_generated_file(build, "quickjs-interpreter-own-bytecode-allocator-routes.json")
    assert not out.exists()
    out.write_text(
        json.dumps(
            dict(
                status="passed",
                input=str(before),
                input_sha256=sha(before),
                output_sha256=hashlib.sha256(result).hexdigest(),
                source_contract=contract,
                routes=sites,
                all_section_geometry_and_non_operand_bytes_held=True,
                all_original_symbol_addresses_held=True,
                standard_existing_allocator_ABIs_only=True,
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return result, str(out)


"""MS append-only code/RW/RO groups already owned by the actual parent.

Do not add COFF group kinds for each feature: their debug catalog lives before
the interpreter sections. Preserve new metadata as one contiguous late packet.
"""


def use_parent_ms_groups(source, build, output, old_count):
    C = module(source, "object-adapter")
    M = module(source, "extension-merge")
    original = output.read_bytes()
    co = C.Coff(original)
    code = ".qjs$zzzzzzzzzzrvV"
    rw = ".qjszzcm$zzzzzzzzzzzzzzslowdirect"
    ro = ".qjlnro$Z"
    oldnames = {M.section_name(co, i) for i in range(1, old_count + 1)}
    assert {code, rw, ro} <= oldnames, (
        "Need declared existing parent cold/RW/finalRO groups",
        oldnames,
    )
    parts = [i for i in range(old_count + 1, co.count + 1) if M.section_name(co, i).startswith(CFI)]
    assert parts
    parts.sort(key=lambda i: (M.section_name(co, i), i))
    assert (
        M.section_name(co, parts[0]) == CFI + "$A" and M.section_name(co, parts[-1]) == CFI + "$Z"
    )
    destination = parts[-1]
    packet = bytearray()
    relocations = []
    offsets = {}
    renames = []
    for number in parts:
        r = co.section_records[number - 1]
        assert not r["flags"] & 0x20000000 and r["size"] and not r["size"] % 4
        offsets[number] = len(packet)
        packet += co.data[r["raw"] : r["raw"] + r["size"]]
        for j in range(r["count"]):
            off, index, kind = struct.unpack_from("<IIH", co.data, r["reloc"] + 10 * j)
            assert kind == 3 and off + 4 <= r["size"]
            relocations.append((offsets[number] + off, index, kind))
    assert packet.startswith(MAGIC) and len(relocations) * 4 <= len(packet)
    assert packet.count(MAGIC) == packet.count(FOOTER) == 1

    def rename(number, name):
        r = co.section_records[number - 1]
        previous = M.section_name(co, number)
        at = len(co.strings)
        co.strings += name.encode() + b"\0"
        co.data[r["pos"] : r["pos"] + 8] = ("/" + str(at)).encode().ljust(8, b"\0")
        for index, s in co.all_symbols.items():
            if (
                s["section"] == number
                and s["storage"] == 3
                and s["type"] == 0
                and s["name"] == previous
            ):
                struct.pack_into("<II", co.data, co.table + index * co.stride, 0, at)
        renames.append(dict(section=number, old=previous, new=name))

    for number in range(old_count + 1, co.count + 1):
        name = M.section_name(co, number)
        if name.startswith(CODE):
            rename(number, code)
        elif name.startswith(".qjzzom"):
            rename(number, rw)
        elif number in parts:
            rename(number, ro)
    # Keep section indexes stable. Source section-definition auxiliaries remain
    # attached to now-empty sections; ordinary metadata labels move to the one
    # owned packet. No old section or old symbol is changed.
    moved = []
    for index, s in co.all_symbols.items():
        if s["section"] not in parts:
            continue
        pos = co.table + index * co.stride
        aux = co.data[pos + 17]
        if s["storage"] == 3 and s["type"] == 0 and aux:
            assert aux == 1
            length = len(packet) if s["section"] == destination else 0
            count = len(relocations) if s["section"] == destination else 0
            struct.pack_into("<IHHIhBBh", co.data, pos + 18, length, count, 0, 0, 0, 0, 0, 0)
            continue
        assert not aux
        value = s["value"] + offsets[s["section"]]
        struct.pack_into("<Ih", co.data, pos + 8, value, destination)
        moved.append(
            dict(
                symbol=s["name"],
                old_section=s["section"],
                old_value=s["value"],
                new_section=destination,
                new_value=value,
            )
        )
    raw = bytearray(co.finish())
    packet_at = len(raw)
    raw += packet
    reloc_at = len(raw)
    for entry in relocations:
        raw += struct.pack("<IIH", *entry)
    for number in parts:
        r = co.section_records[number - 1]
        if number == destination:
            struct.pack_into("<III", raw, r["pos"] + 16, len(packet), packet_at, reloc_at)
            struct.pack_into("<HH", raw, r["pos"] + 32, len(relocations), 0)
        else:
            struct.pack_into("<III", raw, r["pos"] + 16, 0, 0, 0)
            struct.pack_into("<HH", raw, r["pos"] + 32, 0, 0)
        flags = (r["flags"] & ~(0xE00000E0 | 0x1000)) | 0x40000040
        struct.pack_into("<I", raw, r["pos"] + 36, flags)
    # No relocation can reference an emptied metadata section definition.
    view = C.Coff(bytes(raw))
    for number, r in enumerate(view.section_records, 1):
        for j in range(r["count"]):
            off, index, kind = struct.unpack_from("<IIH", view.data, r["reloc"] + 10 * j)
            s = view.all_symbols[index]
            assert s["section"] not in set(parts) - {destination}, (
                "Reference to emptied owned metadata",
                number,
                off,
                s,
            )
    result, _ = module(source, "call-metadata").packed(bytes(raw), C)
    after = C.Coff(result)
    before = C.Coff(original)
    assert after.sections[:old_count] == before.sections[:old_count]
    for index, s in before.all_symbols.items():
        if s["section"] <= old_count:
            assert after.all_symbols[index] == s
    output.write_bytes(result)
    (_frame_generated_file(build, "quickjs-interpreter-own-bytecode-common-ms.json")).write_text(
        json.dumps(
            dict(
                status="passed",
                before_sha256=hashlib.sha256(original).hexdigest(),
                after_sha256=sha(output),
                parent_groups=dict(code=code, rw=rw, ro=ro),
                old_sections=old_count,
                renames=renames,
                moved_metadata_labels=moved,
                packet_section=destination,
                packet_bytes=len(packet),
                typed_relocations=len(relocations),
                old_payloads_and_symbols_held=True,
                policy="Append new code to the existing final parent cold-code input group, new control to the existing final RW input group, and one complete new RO packet after the parent final RO allocation. No new group kinds, numeric addresses, padding or measured capacity selection.",
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def prove_no_absolute_initializers(source, build, obj):
    C = module(source, "object-adapter")
    M = module(source, "extension-merge")
    co = C.Coff(obj.read_bytes())
    sections = []
    for number, r in enumerate(co.section_records, 1):
        name = M.section_name(co, number)
        if name.startswith(".debug"):
            continue
        for j in range(r["count"]):
            off, index, kind = struct.unpack_from("<IIH", co.data, r["reloc"] + 10 * j)
            assert kind != 1, (
                "No allocated absolute pointer initializer/refptr",
                name,
                off,
                co.all_symbols[index],
            )
        sections.append(dict(number=number, name=name, bytes=r["size"], relocations=r["count"]))
    assert not any(
        s["section"] > 0 and s["name"].startswith(".refptr.") for s in co.all_symbols.values()
    )
    data = [
        s
        for s in co.all_symbols.values()
        if s["name"] == "JS_FrameOwnBytecodeDispatch" and s["section"] > 0
    ]
    assert len(data) == 1
    data = data[0]
    r = co.section_records[data["section"] - 1]
    assert M.section_name(co, data["section"]) == RW
    from property_ic_native import enabled

    dispatch_bytes = 2104 if enabled(build) else 2096
    assert bytes(
        co.data[r["raw"] + data["value"] : r["raw"] + data["value"] + dispatch_bytes]
    ) == bytes(dispatch_bytes)
    out = _frame_generated_file(build, "quickjs-interpreter-own-bytecode-relative-addresses.json")
    assert not out.exists()
    out.write_text(
        json.dumps(
            dict(
                status="passed",
                object_sha256=sha(obj),
                sections=sections,
                dispatch_initial_bytes=dispatch_bytes,
                policy="All selected/configuration code/data has no ADDR64 or GNU refptr definitions. Dispatch starts zero and the existing producer/configuration barrier initializes original/new RIP-relative targets before1/2 publication. Original generic merger retained.",
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def prove_cold_storeload(source, build, obj, msvc):
    C = module(source, "object-adapter")
    co = C.Coff(obj.read_bytes())
    found = [
        s
        for s in co.all_symbols.values()
        if s["name"] == "JS_FrameOwnBytecodeDisable" and s["section"] > 0 and s["type"] == 32
    ]
    assert len(found) == 1
    s = found[0]
    r = co.section_records[s["section"] - 1]
    end = min(
        [
            v["value"]
            for v in co.all_symbols.values()
            if v["section"] == s["section"] and v["type"] == 32 and v["value"] > s["value"]
        ]
        + [r["size"]]
    )
    body = bytes(co.data[r["raw"] + s["value"] : r["raw"] + end])
    needle = bytes.fromhex("0faef0")
    offsets = [i for i in range(len(body) - 2) if body[i : i + 3] == needle]
    assert len(offsets) == (0 if msvc else 1), (msvc, offsets)
    out = _frame_generated_file(build, "quickjs-interpreter-own-bytecode-storeload.json")
    assert not out.exists()
    out.write_text(
        json.dumps(
            dict(
                status="passed-byte-witness-only",
                object_sha256=sha(obj),
                function="JS_FrameOwnBytecodeDisable",
                body_bytes=len(body),
                MFENCE_offsets=offsets,
                scope="GNU lazy-table restoration requires one cold MFENCE before its owner read. MS has no shared lazy table and needs no such barrier. This COFF byte witness alone is not a final linked-instruction ordering or OS-unwind qualification.",
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
