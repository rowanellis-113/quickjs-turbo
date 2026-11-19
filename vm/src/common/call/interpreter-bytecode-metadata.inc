#ifndef QJS_FRAME_BYTECODE_METADATA
#define QJS_FRAME_BYTECODE_METADATA
/* Shared by the VM and independently compiled function-owned call metadata. */
#define FRAME_KIND(b) (((unsigned char *)(b))[offsetof(JSFunctionBytecode, byte_code_buf) - 1])
#define FRAME_CALL_META_OFFSET (offsetof(JSFunctionBytecode, byte_code_buf) - 6)
#define FRAME_CALL_LOCALS_OFFSET (offsetof(JSFunctionBytecode, byte_code_buf) - 4)
#define FRAME_CALL_FORMALS_OFFSET (offsetof(JSFunctionBytecode, byte_code_buf) - 3)
#define FRAME_CALL_AUX_OFFSET (offsetof(JSFunctionBytecode, byte_code_buf) - 2)
_Static_assert(FRAME_CALL_META_OFFSET >= QJS_ABI_BIT_JSFunctionBytecode_is_strict_mode_BYTE + 2,
               "native preparation metadata follows the actual flag bytes");
#endif
