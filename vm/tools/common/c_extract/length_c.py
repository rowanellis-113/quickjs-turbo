"""Shared native get_length C control body."""

BODY = r"""
#include <stdatomic.h>
typedef struct JSFrameLengthData {
    _Atomic(unsigned char) mode;
    unsigned char diagnostic;
    unsigned char reserved[6];
    _Atomic(uint64_t) strings,arrays,misses,abi;
} JSFrameLengthData;
_Static_assert(sizeof(JSFrameLengthData)==40 && offsetof(JSFrameLengthData,strings)==8 &&
    offsetof(JSFrameLengthData,arrays)==16 && offsetof(JSFrameLengthData,misses)==24 &&
    offsetof(JSFrameLengthData,abi)==32,"length control ABI");
_Static_assert(sizeof(JSValue)==16 && JS_TAG_INT==0 && JS_TAG_FLOAT64==8 &&
    JS_TAG_STRING==-7 && JS_TAG_OBJECT==-1 && JS_CLASS_ARRAY==2 &&
    offsetof(JSObject,class_id)==QJS_ABI_OFF_JSObject_class_id &&
    offsetof(JSObject,prop)==QJS_ABI_OFF_JSObject_prop,
    "length native object/tag ABI");
#if QJS_ABI_HAS_PREFIX_RC
_Static_assert(offsetof(JSMallocBlockHeader,user_data)-offsetof(JSMallocBlockHeader,ref_count)==-QJS_ABI_REF_COUNT_OFFSET,
    "length prefix reference count ABI");
#else
_Static_assert(offsetof(JSObject,header.ref_count)==QJS_ABI_REF_COUNT_OFFSET &&
    offsetof(JSString,header.ref_count)==QJS_ABI_REF_COUNT_OFFSET,
    "length inline reference count ABI");
#endif
#ifdef QJS_INTERP_FRAME_DIAGNOSTICS
#define LENGTH_DIAG 1
#else
#define LENGTH_DIAG 0
#endif
#ifdef _MSC_VER
#pragma section(".qjzzlm$C",read,write)
__declspec(allocate(".qjzzlm$C"))
#else
__attribute__((section(".qjzzlm$C"),used,aligned(8)))
#endif
JSFrameLengthData JS_FrameLengthData={0,LENGTH_DIAG,{1}};
FRAME_CODE void JS_FrameLengthConfigure(void)
{
    JSString s={0};JSObject object={0};uint32_t bits;unsigned char flags;
    s.len=0x1234;s.is_wide_char=1;object.fast_array=1;
    memcpy(&bits,(char *)&s+QJS_ABI_BIT_JSString_len_BYTE,sizeof(bits));
    memcpy(&flags,(char *)&object+QJS_ABI_BIT_JSObject_fast_array_BYTE,1);
    unsigned valid=bits==0x80001234u && flags==QJS_ABI_BIT_JSObject_fast_array_MASK;
    unsigned char mode=valid && !getenv("QJS_DISABLE_NATIVE_LENGTH")?1:2;
    atomic_store_explicit(&JS_FrameLengthData.abi,valid,memory_order_relaxed);
    atomic_store_explicit(&JS_FrameLengthData.mode,mode,memory_order_release);
}
"""
