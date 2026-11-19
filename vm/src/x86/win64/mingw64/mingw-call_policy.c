#include "src/common/call/interpreter-retained-context.inc"

extern unsigned char JS_FrameCallLinkControl;
extern void JS_FrameCallEnvMetaMiss(JSFrameRegisterState *, unsigned);
extern void JS_FrameCallEnvLinkMiss(JSFrameRegisterState *, unsigned);
/* Called only through the original cold CALL/tail-JMP operands. Their ASM
   has already committed the actual decoded PC, current SF and owning SP.
   Keep that decoded PC; state->pc is the opcode address, not the return PC. */
static FRAME_INLINE void js_frame_call_policy_configure(JSFrameRegisterState *state)
{
    unsigned char mode;
    __asm__ volatile("movb JS_FrameCallLinkControl(%%rip),%0" : "=q"(mode)::"memory");
    if (!mode) {
        JSFrame *frame = state->frame;
        state->rt->current_stack_frame = &frame->sf;
        frame->saved_sp = state->sp;
        frame->sf.cur_sp = state->sp;
        js_frame_begin_c(state);
        unsigned char desired = 2;
        if (getenv("QJS_ENABLE_CALL_LINK_VM") && !getenv("QJS_DISABLE_CALL_LINK") &&
            !getenv("QJS_DISABLE_CALL_LINK_VM"))
            desired = 1;
        unsigned char expected = 0;
        /* Same process-lifetime publication and byte as the original mode.
           An independent RT or a reentrant first use may win initialization. */
        __asm__ volatile("lock cmpxchgb %2,JS_FrameCallLinkControl(%%rip)"
                         : "+a"(expected)
                         : "0"(expected), "q"(desired)
                         : "memory", "cc");
        js_frame_finish_c(state);
    }
}
FRAME_CODE void JS_FrameCallLinkPolicyMetaMiss(JSFrameRegisterState *state, unsigned argc)
{
    js_frame_call_policy_configure(state);
    /* Reuse the qualified environment-aware helper, including metadata mode
       handling, cold budget, optional allocation and weak ownership. */
    JS_FrameCallEnvMetaMiss(state, argc);
}
FRAME_CODE void JS_FrameCallLinkPolicyLinkMiss(JSFrameRegisterState *state, unsigned argc)
{
    js_frame_call_policy_configure(state);
    JS_FrameCallEnvLinkMiss(state, argc);
}
