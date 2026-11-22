"""Shared pure-C bytecode-tail own-body builder."""

from admission_c import function
from c_workers import module, replace_one


def own_body(source, reference_controls=False):
    owner = module(source, "own-bytecode-c")
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
 while(atomic_exchange_explicit(&js_linux_own_lock,1,memory_order_acquire)) qjs_own_pause();
}
static FRAME_INLINE void own_bytecode_unlock(void) {
 atomic_store_explicit(&js_linux_own_lock,0,memory_order_release);
}
static FRAME_INLINE void own_bytecode_fence(void) {
 qjs_own_seq_cst_fence();
}
FRAME_CODE void JS_FrameOwnBytecodeDisable(void) {
 own_bytecode_lock();
 if(atomic_load_explicit(&JS_FrameOwnBytecodeData.mode,memory_order_relaxed)!=2) {
  atomic_store_explicit(&JS_FrameOwnBytecodeData.mode,3,memory_order_release);
  own_bytecode_fence();
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
  own_bytecode_fence();
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
"""
    configure = function(text, "FRAME_CODE void JS_FrameOwnBytecodeConfigure(void)")
    configure = configure[: configure.index(" own_bytecode_lock();")]
    if not reference_controls:
        configure = replace_one(
            configure,
            " frame_reference_configure();\n",
            "",
            "independent global controls are not an own-tail dependency",
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
  JS_FrameOwnBytecodeData.reserved[3]=pic_active;
  JS_FrameOwnBytecodeData.reserved[4]=symbol_case;
  atomic_store_explicit(&JS_FrameOwnBytecodeData.mode,desired,memory_order_release);
 }
 own_bytecode_unlock();
 qjs_turbo_register_own_bytecode_hooks(JS_FrameOwnBytecodeSetTailMode,JS_FrameOwnBytecodeTailActive);
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
