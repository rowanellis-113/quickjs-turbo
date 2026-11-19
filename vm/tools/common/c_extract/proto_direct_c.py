"""Shared native prototype load C control body."""

BODY = r"""
#include <stdatomic.h>
typedef struct JSFrameProtoDirectData {
 unsigned char mode,diagnostic,reserved[6];
 _Atomic(uint64_t) objects,strings,resumes,misses;
 uint64_t abi;
} JSFrameProtoDirectData;
_Static_assert(sizeof(JSFrameProtoDirectData)==48 && offsetof(JSFrameProtoDirectData,objects)==8 &&
 offsetof(JSFrameProtoDirectData,strings)==16 && offsetof(JSFrameProtoDirectData,resumes)==24 &&
 offsetof(JSFrameProtoDirectData,misses)==32 && offsetof(JSFrameProtoDirectData,abi)==40,
 "direct prototype control ABI");
_Static_assert(sizeof(JSValue)==16 && sizeof(JSStackFrame)==QJS_ABI_SIZE_JSStackFrame && sizeof(JSShapeProperty)==8 &&
 offsetof(JSObject,shape)==QJS_ABI_OFF_JSObject_shape && offsetof(JSObject,prop)==QJS_ABI_OFF_JSObject_prop &&
 offsetof(JSObject,class_id)==QJS_ABI_OFF_JSObject_class_id &&
 offsetof(JSShape,prop_count)==QJS_ABI_OFF_JSShape_prop_count && offsetof(JSShape,prop_hash_mask)==QJS_ABI_OFF_JSShape_prop_hash_mask &&
 offsetof(JSShape,proto)==QJS_ABI_OFF_JSShape_proto && offsetof(JSContext,class_proto)==QJS_ABI_OFF_JSContext_class_proto && JS_CLASS_ARRAY==2 &&
 JS_CLASS_STRING==5 && JS_TAG_OBJECT==-1 && JS_TAG_STRING==-7 && JS_PROP_TMASK==48,
 "native prototype load uses the pinned live-object ABI");
#ifdef QJS_INTERP_FRAME_DIAGNOSTICS
#define PROTO_DIRECT_DIAG 1
#else
#define PROTO_DIRECT_DIAG 0
#endif
__attribute__((section(".qjzzdm$C"),used,aligned(8)))
JSFrameProtoDirectData JS_FrameProtoDirectData={0,PROTO_DIRECT_DIAG,{4}};
extern void JS_FrameLengthConfigure(void);
FRAME_CODE void JS_FrameProtoDirectConfigure(void){
 JS_FrameLengthConfigure();
 JSShapeProperty prop={0};JSObject object={0};uint32_t flags;unsigned char exotic;
 prop.flags=JS_PROP_TMASK;object.is_exotic=1;
 memcpy(&flags,&prop,4);memcpy(&exotic,(char *)&object+QJS_ABI_BIT_JSObject_is_exotic_BYTE,1);
 unsigned valid=flags==0xc0000000u && exotic==QJS_ABI_BIT_JSObject_is_exotic_MASK;
 JS_FrameProtoDirectData.abi=valid;
 JS_FrameProtoDirectData.mode=valid && !getenv("QJS_DISABLE_PROTO_DIRECT")?1:2;
}
"""
