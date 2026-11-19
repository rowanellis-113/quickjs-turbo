/* Paused C-step boundary; the executor types are defined by the following
 * common loop include. Keep this typed prototype outside the legacy core. */
struct JSFrameRegisterState;
struct JSFrame;
struct JSFrameSegment;
static JSValue js_frame_slow_host_call(struct JSFrameRegisterState *state, struct JSFrame *frame,
                                       struct JSFrameSegment *segment, size_t used, uint8_t *pc,
                                       JSValue *sp, JSContext *ctx, JSValueConst callee,
                                       JSValueConst receiver, int argc, JSValueConst *argv);
