/* Nonmoving builtin views share the real SF/TLS/arena owner. No public type
 * or suspended-frame cursor changes. Only cold window reservation enters C.
 * Window bytes belong to the JSFrame and its ordinary pop/tail cleanup. MIT. */
typedef struct JSLinuxBuiltinView {
    JSStackFrame sf;
    FRAME_STACK_TAIL_PADDING
    JSFrameSharedAnchor anchor;
    JSFrameSharedAnchor **slot;
    unsigned char active, padding[7];
    JSFrameSegment *transient_segment;
} JSLinuxBuiltinView;
_Static_assert(sizeof(JSLinuxBuiltinView) == 128 && offsetof(JSLinuxBuiltinView, anchor) == 80 &&
                   offsetof(JSLinuxBuiltinView, slot) == 104 &&
                   offsetof(JSLinuxBuiltinView, active) == 112 &&
                   offsetof(JSLinuxBuiltinView, transient_segment) == 120 &&
                   offsetof(JSStackFrame, var_buf) == 32 &&
                   offsetof(JSStackFrame, var_refs) == 40 && offsetof(JSStackFrame, cur_pc) == 48 &&
                   offsetof(JSStackFrame, var_ref_count) == 56 &&
                   offsetof(JSStackFrame, arg_count) == 58 &&
                   offsetof(JSStackFrame, cur_sp) == 64 && sizeof(JSCFunctionType) == 8,
               "Actual SysV builtin view and callable identity contract");

/* Typed identities survive compiler-local symbol choices. The descriptors
 * remain live cfunc fields; this table holds no weak JS object addresses. */
__attribute__((visibility("hidden"))) const JSCFunctionType JS_LinuxBuiltinTargets[2] = {
    {.generic = js_string_slice}, {.generic_magic = js_number_toString}};

#define NATIVE_SLICE_CODE                                                                          \
    __attribute__((visibility("hidden"), section(".text.qjs_linux_builtin"), noipa))
#include "quickjs-linux-builtin.h"
#undef NATIVE_SLICE_CODE

__attribute__((visibility("hidden"), section(".text.qjs_linux_builtin"),
               noipa)) void JS_LinuxBuiltinRun(JSStackFrame *sf, JSValue *out)
{
    if (JS_VALUE_GET_OBJ(sf->cur_func)->u.cfunc.c_function.generic_magic == js_number_toString)
        JS_FrameNumberToStringNative(sf, out);
    else
        JS_FrameStringSliceNative(sf, out);
}

static inline __attribute__((always_inline)) uint64_t
js_linux_builtin_geometry(JSFunctionBytecode *b)
{
    return (uint64_t)b->var_count | ((uint64_t)b->stack_size << 16) |
           ((uint64_t)b->var_ref_count << 32);
}

__attribute__((visibility("hidden"), section(".text.qjs_linux_builtin"), noipa)) void *
JS_LinuxBuiltinPrepare(JSFrameRegisterState *state)
{
    JSFrame *frame = state->frame;
    JSFrameSegment *segment = state->segment;
    JSLinuxBuiltinView *view;
    unsigned mode = atomic_load_explicit(&JS_LinuxBuiltinControl, memory_order_relaxed) & 7;
    if (mode == 4) {
        if (segment->used > segment->capacity || sizeof(*view) > segment->capacity - segment->used)
            return NULL;
        view = (JSLinuxBuiltinView *)(segment->data + segment->used);
        segment->used += sizeof(*view);
        js_frame_charge_stack(state->rt, sizeof(*view));
        view->transient_segment = segment;
        return view;
    }
    JSFunctionBytecode *b = frame->bytecode;
    uint64_t geometry = js_linux_builtin_geometry(b);
    if (state->arities == (uintptr_t)frame && (FRAME_FLAGS(frame) & FRAME_FLAG_C_WINDOW) &&
        state->borrowed_values == (uintptr_t)frame->sf.var_buf && state->windows == geometry &&
        frame->frame_bytes >= state->peak_bytes) {
        view = (JSLinuxBuiltinView *)(uintptr_t)state->pushes;
        /* Dormant views share caller argument-padding storage. Geometry
         * validity says nothing about the old SF/release-owner contents. */
        view->transient_segment = NULL;
        return view;
    }
    uint8_t *end = (uint8_t *)(frame->sf.var_buf + (size_t)b->var_count + b->stack_size) +
                   FRAME_CAPTURE_BYTES(b);
    size_t needed = (size_t)(end - (uint8_t *)frame) + sizeof(*view);
    if (needed > frame->frame_bytes) {
        size_t delta = needed - frame->frame_bytes;
        if (delta > sizeof(*view) || frame->segment != segment ||
            segment->used > segment->capacity || delta > segment->capacity - segment->used ||
            segment->data + segment->used != (uint8_t *)frame + frame->frame_bytes)
            return NULL;
        segment->used += delta;
        frame->frame_bytes += (uint32_t)delta;
        state->used_bytes += delta;
        js_frame_charge_stack(state->rt, delta);
        js_frame_finish_c(state);
    }
    view = (JSLinuxBuiltinView *)end;
    view->transient_segment = NULL;
    FRAME_FLAGS(frame) |= FRAME_FLAG_C_WINDOW;
    state->pushes = (uintptr_t)view;
    state->arities = (uintptr_t)frame;
    state->borrowed_values = (uintptr_t)frame->sf.var_buf;
    state->windows = geometry;
    state->peak_bytes = needed;
    return view;
}

/* Read-only fixture observation: match the live SF AND the actual typed TLS
 * anchor before inspecting a view. No hot-path counters or public fields. */
__attribute__((visibility("hidden"), section(".text.qjs_linux_builtin"), noipa)) int
JS_LinuxBuiltinProbe(JSRuntime *rt, uintptr_t *words)
{
    for (JSFrameSharedAnchor *anchor = *js_frame_shared_slot(); anchor; anchor = anchor->prev) {
        if (anchor->kind || anchor->state->rt != rt)
            continue;
        for (JSStackFrame *sf = rt->current_stack_frame; sf; sf = sf->prev_frame) {
            if ((uintptr_t)sf + offsetof(JSLinuxBuiltinView, anchor) != (uintptr_t)anchor)
                continue;
            JSLinuxBuiltinView *view = (JSLinuxBuiltinView *)sf;
            if (view->slot != js_frame_shared_slot() ||
                JS_VALUE_GET_TAG(sf->cur_func) != JS_TAG_OBJECT)
                continue;
            JSObject *callee = JS_VALUE_GET_OBJ(sf->cur_func);
            if (callee->class_id != JS_CLASS_C_FUNCTION ||
                (callee->u.cfunc.c_function.generic != js_string_slice &&
                 callee->u.cfunc.c_function.generic_magic != js_number_toString))
                continue;
            JSFrameRegisterState *state = anchor->state;
            uintptr_t kind =
                view->transient_segment ? 4
                : (state->arities == (uintptr_t)state->frame && state->pushes == (uintptr_t)view &&
                   (FRAME_FLAGS(state->frame) & FRAME_FLAG_C_WINDOW))
                    ? 1
                    : 3;
            if (words) {
                words[0] = kind;
                words[1] = state->used_bytes;
                words[2] = state->committed_bytes;
                words[3] = state->frame->frame_bytes;
                words[4] = state->segment->used;
                words[5] = (uintptr_t)view;
                words[6] = (uintptr_t)state->frame;
            }
            return 1;
        }
    }
    return 0;
}
