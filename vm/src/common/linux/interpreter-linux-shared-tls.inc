/* Compiler-managed ELF TLS. No Windows TLS index, GS offset, emutls allocator
 * or hand-chosen initial-exec assumption is part of this implementation.
 * The compiler selects a valid TLS model for the actual static/PIC build. */
static _Thread_local JSFrameSharedAnchor *js_frame_linux_shared_top;
static SHARED_INLINE JSFrameSharedAnchor **js_frame_shared_slot(void)
{
    return &js_frame_linux_shared_top;
}
