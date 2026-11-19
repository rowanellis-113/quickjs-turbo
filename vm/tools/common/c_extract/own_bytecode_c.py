"""Pure-C bytecode tail lifetime body and creator contract."""

import hashlib
import re
import sys as _frame_sys
from pathlib import Path as _FramePath

_frame_tools_root = str(_FramePath(__file__).resolve().parents[2])
if _frame_tools_root not in _frame_sys.path:
    _frame_sys.path.insert(0, _frame_tools_root)
from common.paths import source_file as _frame_source_file


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


load_layout = None


BODY = r"""
#include <stdatomic.h>
#include "qjs-own-sync.h"
#include "src/common/internal/interpreter-env.h"
typedef struct JSFrameOwnBytecodeControl {
 _Atomic(unsigned char) mode;
 unsigned char diagnostic,reserved[6]; /* reserved[2]: legacy method IC learning policy */
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
   Indirect refptr literals would introduce late absolute fixups.
   Ask for the same RIP-relative LEA used by the native backend, on this new
   cold C module only. No compiler flags, image base or core layout changes. */
#define OWN_PRIVATE_ADDRESS(symbol) QJS_OWN_PRIVATE_ADDR(symbol)

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
 "aligned lock-free dispatch pointer cells and actual opcode IDs");
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
 while(atomic_exchange_explicit(&JS_FrameOwnBytecodeDispatch.lock,1,memory_order_acquire)) qjs_own_pause();
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
     This backend uses a full barrier only on the cold restoration path. */
  qjs_own_seq_cst_fence();
#endif
#if OWN_BYTECODE_DIRTY_P
  while(atomic_load_explicit((_Atomic(unsigned char)*)OWN_PRIVATE_ADDRESS(JS_FramePublishControl),memory_order_acquire)==3) qjs_own_pause();
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
  while(atomic_load_explicit((_Atomic(unsigned char)*)OWN_PRIVATE_ADDRESS(JS_FrameGlobalBindingControl),memory_order_acquire)==3) qjs_own_pause();
  atomic_store_explicit(&((_Atomic(uintptr_t)*)OWN_PRIVATE_ADDRESS(JS_FrameGlobalBindingDiagnosticTable))[OWN_BYTECODE_FIELD1],OWN_PRIVATE_ADDRESS(interp_get_field),memory_order_release);
  atomic_store_explicit(&((_Atomic(uintptr_t)*)OWN_PRIVATE_ADDRESS(JS_FrameGlobalBindingDiagnosticTable))[OWN_BYTECODE_FIELD2],OWN_PRIVATE_ADDRESS(interp_get_field2),memory_order_release);
#endif
  atomic_store_explicit(&JS_FrameOwnBytecodeData.mode,2,memory_order_release);
 }
 own_bytecode_unlock();
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
 unsigned char desired=valid && !getenv("QJS_DISABLE_NATIVE_OWN_BYTECODE") &&
  !qjs_internal_interp_frame_disabled() && !qjs_internal_interp_register_disabled()?1:2;
#ifndef _MSC_VER
 unsigned char local_field=desired==1 && !getenv("QJS_DISABLE_FRAME_LOCAL_FIELD")?1:2;
#endif
 unsigned char symbol_case=desired==1 && !getenv("QJS_DISABLE_SYMBOL_CASE")?1:2;
#if defined(_MSC_VER) && defined(QJS_PROPERTY_IC) && !defined(QJS_INTERP_FRAME_DIAGNOSTICS)
 unsigned char method_learning=desired==1 && !getenv("QJS_DISABLE_METHOD_IC_LEARNING")?1:2;
#endif
 atomic_store_explicit(&JS_FrameOwnBytecodeData.abi,valid,memory_order_relaxed);
 own_bytecode_lock();
 if(atomic_load_explicit(&JS_FrameOwnBytecodeData.mode,memory_order_relaxed)==0) {
#ifndef _MSC_VER
  JS_FrameOwnBytecodeData.reserved[1]=local_field;
#endif
  JS_FrameOwnBytecodeData.reserved[4]=symbol_case;
#if defined(_MSC_VER) && defined(QJS_PROPERTY_IC) && !defined(QJS_INTERP_FRAME_DIAGNOSTICS)
  JS_FrameOwnBytecodeData.reserved[2]=method_learning;
#endif
  atomic_store_explicit(&JS_FrameOwnBytecodeDispatch.selected,OWN_PRIVATE_ADDRESS(interp_table),memory_order_relaxed);
  atomic_store_explicit(&JS_FrameOwnBytecodeDispatch.dirty[0],OWN_PRIVATE_ADDRESS(OWN_ORIGINAL_P1),memory_order_relaxed);
  atomic_store_explicit(&JS_FrameOwnBytecodeDispatch.dirty[1],OWN_PRIVATE_ADDRESS(OWN_ORIGINAL_P2),memory_order_relaxed);
  if(desired==1) {
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
   desired==1 ? OWN_PRIVATE_ADDRESS(JS_FrameOwnBytecodeP3) : OWN_PRIVATE_ADDRESS(dirty_interp_put_field),memory_order_release);
#endif
  atomic_store_explicit(&JS_FrameOwnBytecodeData.mode,desired,memory_order_release);
 }
 own_bytecode_unlock();
}
FRAME_CODE void *JS_FrameOwnBytecodeAllocateRT(JSRuntime *rt,size_t count,size_t size) {
 unsigned char mode=atomic_load_explicit(&JS_FrameOwnBytecodeData.mode,memory_order_acquire);
 if(mode!=1) {
  if(mode!=2) JS_FrameOwnBytecodeDisable();
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


def bytecode_source_contract(source, layout=None):
    core_path = _frame_source_file(source, "quickjs.c")
    text = core_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if layout is None:
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
        source_sha256=sha(core_path),
        allocation_source_lines=alloc,
        bytecode_is_final_member_in_both_creators=True,
        all_bytecode_buffer_assignments_enumerated=True,
        reservation="Schema2,extra=6+min(original_function_allocation_bytes,FRAME_MAX_CODE2048). Both producers4-align code_buf. Cell=align4(code_end)+(PC_offset&~3)=(PC&~3)+ceil4(code_len). All property instructions are5bytes, so distinct valid starts have distinct floor(PC/4), with no collisions. Pad<=3;ceil4(len)<=len+3;fresh plane end<=old_end+6+len<=old_end+extra. Bound is conservative,not exact minimal metadata.",
        fallback="Optional nonthrowing enlarged calloc failure or pre-CRT allocation permanently disables native hint mode before returning an original-size block. Configure CAS can initialize only mode0 and never reenables mode2. Existing ON opcode has no C/GC safepoint and can only hold a previously enlarged live bytecode. No weak owner or extra JS roots.",
    )
