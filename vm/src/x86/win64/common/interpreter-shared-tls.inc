/* Platform TLS implementation extracted without changing the Win64 protocol. */
#if defined(_MSC_VER)
/* The numeric assembler takes SECREL of this actual TLS symbol. */
__declspec(thread) JSFrameSharedAnchor *js_frame_shared_top;
static SHARED_INLINE JSFrameSharedAnchor **js_frame_shared_slot(void)
{
    return &js_frame_shared_top;
}
#else
/* GCC's __thread uses emutls here. Native PE TLS needs no allocator/lookup call.
 * Do not use GAS SECREL32: this toolchain emits an erroneous HIGHLOW base
 * relocation for it. The difference of two RIP-relative addresses survives
 * ASLR and also permits other library TLS contributions before this one. */
__asm__(".section .tls$QJSSHARE,\"dw\"\n.p2align 3\n"
        ".globl JS_FrameSharedTop\nJS_FrameSharedTop: .quad 0\n.text\n");
static SHARED_INLINE JSFrameSharedAnchor **js_frame_shared_slot(void)
{
    JSFrameSharedAnchor **p;
    __asm__ volatile("movq %%gs:88, %0\n\t"
                     "movl _tls_index(%%rip), %%ecx\n\t"
                     "movq (%0,%%rcx,8), %0\n\t"
                     "leaq JS_FrameSharedTop(%%rip), %%rcx\n\t"
                     "leaq _tls_start(%%rip), %%r11\n\t"
                     "subq %%r11, %%rcx\n\taddq %%rcx, %0"
                     : "=&r"(p)
                     :
                     : "rcx", "r11", "memory");
    return p;
}
#endif
