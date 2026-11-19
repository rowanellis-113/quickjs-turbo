/* Actual core types and same-image ELF data;no duplicated private layout. */
#define FRAME_CODE __attribute__((section(".text.qjs_frame"), noipa))
#define FRAME_INLINE inline __attribute__((always_inline))
FRAME_CODE void JS_FrameLengthConfigure(void);
FRAME_CODE void JS_FrameProtoDirectConfigure(void);
FRAME_CODE void JS_FrameOwnBytecodeConfigure(void);
FRAME_CODE void JS_FrameOwnBytecodeDisable(void);
FRAME_CODE void *JS_FrameOwnBytecodeAllocateRT(JSRuntime *, size_t, size_t);
FRAME_CODE void *JS_FrameOwnBytecodeAllocateContext(JSContext *, size_t);
FRAME_CODE int JS_LinuxPropertyInit(JSFrameRegisterState *state);
FRAME_CODE int JS_LinuxProtoFill(JSFrameRegisterState *state);
