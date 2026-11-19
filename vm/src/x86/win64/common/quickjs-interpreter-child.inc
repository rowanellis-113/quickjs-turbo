/* Native child-entry binds the existing C/arena/TLS protocol. MIT. */
_Static_assert(offsetof(JSRuntime, module_normalize_has_attr) ==
                       QJS_ABI_OFF_JSRuntime_module_normalize_has_attr &&
                   offsetof(JSRuntime, normalize_u) == QJS_ABI_OFF_JSRuntime_normalize_u &&
                   sizeof(bool) == 1,
               "child mode uses independent module normalization padding");
_Static_assert(offsetof(JSRuntime, can_block) == QJS_ABI_OFF_JSRuntime_can_block &&
                   offsetof(JSRuntime, shape_hash_bits) == QJS_ABI_OFF_JSRuntime_shape_hash_bits &&
                   JS_DUMP_BYTECODE_STEP == 128,
               "measured Win64 MS-compatible dump bitfield allocation unit");
_Static_assert(sizeof(JSFrameSharedAnchor) == 24 && offsetof(JSFrameSharedAnchor, state) == 8 &&
                   offsetof(JSFrameSharedAnchor, kind) == 16,
               "native child barrier mirrors the existing TLS anchor");
_Static_assert(sizeof(JSFrameSegment) == 32 && offsetof(JSFrameSegment, capacity) == 8 &&
                   offsetof(JSFrameSegment, used) == 16 && offsetof(JSFrameSegment, data) == 24,
               "native child borrows the original nonmoving segment cursor");
_Static_assert(offsetof(JSFrameRegisterState, result) == 40 &&
                   offsetof(JSRuntime, current_stack_frame) ==
                       QJS_ABI_OFF_JSRuntime_current_stack_frame &&
                   offsetof(JSRuntime, stack_top) == QJS_ABI_OFF_JSRuntime_stack_top &&
                   FRAME_HEADER_BYTES == 128,
               "native child publication and result ABI");
#ifdef QJS_INTERP_FRAME_DIAGNOSTICS
_Static_assert(sizeof(JSFrameRegisterState) == 2448 &&
                   offsetof(JSFrameRegisterState, caller_ctx) == 2272 &&
                   offsetof(JSFrameRegisterState, sites) == 2280 &&
                   offsetof(JSFrameRegisterState, cache_next) == 2288,
               "diagnostic child state ABI");
#else
_Static_assert(sizeof(JSFrameRegisterState) == 168 &&
                   offsetof(JSFrameRegisterState, caller_ctx) == 136 &&
                   offsetof(JSFrameRegisterState, sites) == 144 &&
                   offsetof(JSFrameRegisterState, cache_next) == 152,
               "release child state ABI");
#endif
