/* Backend supplies LOCAL_STRING_CODE, the mode getter, legacy boundary and
 * consuming rope constructor. No opcode, public value or frame layout changes.
 * Only the operand and the matching local may own the candidate root. */
static FRAME_INLINE uint32_t local_rope_length(JSValueConst value)
{
    return JS_VALUE_GET_TAG(value) == JS_TAG_STRING ? JS_VALUE_GET_STRING(value)->len
                                                    : JS_VALUE_GET_STRING_ROPE(value)->len;
}

static FRAME_INLINE bool local_rope_same(JSValueConst a, JSValueConst b)
{
    return JS_VALUE_GET_TAG(a) == JS_VALUE_GET_TAG(b) && JS_VALUE_GET_PTR(a) == JS_VALUE_GET_PTR(b);
}

LOCAL_STRING_CODE int JS_FrameLocalRopeAppendStep(JSFrameRegisterState *state)
{
    JSFrame *frame = state->frame;
    JSStackFrame *sf = &frame->sf;
    JSFunctionBytecode *bytecode = frame->bytecode;
    JSContext *ctx = bytecode->realm;
    uint8_t *pc = state->pc;
    uintptr_t start = (uintptr_t)bytecode->byte_code_buf;
    uintptr_t end = start + (uintptr_t)bytecode->byte_code_len;
    unsigned op, size, index, mode;
    bool keep = false, is_arg = false;
    JSValue *sp = state->sp, *local;
    JSValue input, rhs, prefix, old_right, right, result;
    JSStringRope *root;
    uint32_t old_length;
    uint8_t old_depth, old_width;

    if ((uintptr_t)pc < start || (uintptr_t)pc + 1 >= end || *pc != OP_add)
        return JS_FrameInterpAddTrampoline(state);
    op = pc[1];
    size = 1;
    if (op >= OP_put_loc0 && op <= OP_put_loc3)
        index = op - OP_put_loc0;
    else if (op >= OP_set_loc0 && op <= OP_set_loc3) {
        index = op - OP_set_loc0;
        keep = true;
    } else if (op == OP_put_loc8 || op == OP_set_loc8) {
        if ((uintptr_t)pc + 2 >= end)
            return JS_FrameInterpAddTrampoline(state);
        size = 2;
        index = pc[2];
        keep = op == OP_set_loc8;
    } else if (op == OP_put_loc || op == OP_set_loc) {
        if ((uintptr_t)pc + 3 >= end)
            return JS_FrameInterpAddTrampoline(state);
        size = 3;
        index = (unsigned)pc[2] | ((unsigned)pc[3] << 8);
        keep = op == OP_set_loc;
    } else if (op >= OP_put_arg0 && op <= OP_put_arg3) {
        index = op - OP_put_arg0;
        is_arg = true;
    } else if (op >= OP_set_arg0 && op <= OP_set_arg3) {
        index = op - OP_set_arg0;
        keep = true;
        is_arg = true;
    } else if (op == OP_put_arg || op == OP_set_arg) {
        if ((uintptr_t)pc + 3 >= end)
            return JS_FrameInterpAddTrampoline(state);
        size = 3;
        index = (unsigned)pc[2] | ((unsigned)pc[3] << 8);
        keep = op == OP_set_arg;
        is_arg = true;
    } else
        return JS_FrameInterpAddTrampoline(state);
    if (is_arg) {
        if (index >= sf->arg_count || !sf->arg_buf || FRAME_CAPTURED_ARGS(bytecode))
            return JS_FrameInterpAddTrampoline(state);
        local = &sf->arg_buf[index];
    } else {
        if (index >= bytecode->var_count || !sf->var_buf)
            return JS_FrameInterpAddTrampoline(state);
        local = &sf->var_buf[index];
    }
    if (JS_VALUE_GET_TAG(sp[-2]) != JS_TAG_STRING_ROPE || JS_VALUE_GET_TAG(sp[-1]) != JS_TAG_STRING)
        return JS_FrameInterpAddTrampoline(state);
    input = sp[-2];
    rhs = sp[-1];
    root = JS_VALUE_GET_STRING_ROPE(input);
    if (JS_REF_COUNT(root) != 2 || !local_rope_same(*local, input) ||
        JS_VALUE_GET_TAG(root->right) != JS_TAG_STRING ||
        JS_VALUE_GET_STRING(root->right)->len > JS_STRING_ROPE_SHORT_LEN ||
        !JS_VALUE_GET_STRING(rhs)->len || JS_VALUE_GET_STRING(rhs)->len > JS_STRING_ROPE_SHORT_LEN)
        return JS_FrameInterpAddTrampoline(state);
    mode = JS_FrameLocalRopeModeGet();
    if ((mode & 3) != 1)
        return JS_FrameInterpAddTrampoline(state);

    state->rt->current_stack_frame = sf;
    frame->saved_sp = sp;
    sf->cur_sp = sp;
    state->pc = pc + 1;
    sf->cur_pc = state->pc;
    js_frame_begin_c(state);
#if defined(JS_ARENA_FREE_NIL)
    if (mode & 16) {
        JSString *leaf = JS_VALUE_GET_STRING(root->right), *suffix = JS_VALUE_GET_STRING(rhs);
        bool nonlast = JS_REF_COUNT(suffix) > 1;
        unsigned depth = JS_VALUE_GET_TAG(root->left) == JS_TAG_STRING_ROPE
                             ? (unsigned)JS_VALUE_GET_STRING_ROPE(root->left)->depth + 1
                             : 1;
        uint64_t length = (uint64_t)root->len + suffix->len;
        /* The NORMAL arena leaf owns its payload. A slice, indirect or
           backing-allocator string does not use inline payload growth. */
        if (JS_REF_COUNT(leaf) == 1 && !leaf->atom_type && leaf->kind == JS_STRING_KIND_NORMAL &&
            leaf->is_wide_char == suffix->is_wide_char && length <= JS_STRING_LEN_MAX &&
            depth <= JS_STRING_ROPE_MAX_DEPTH &&
            container_of(leaf, JSMallocBlockHeader, user_data)->u.block_idx != JS_ARENA_FREE_NIL &&
            (nonlast || (!suffix->atom_type && suffix->kind == JS_STRING_KIND_NORMAL))) {
            unsigned wide = leaf->is_wide_char;
            uint32_t leaf_length = leaf->len, suffix_length = suffix->len;
            size_t required =
                sizeof(*leaf) + ((size_t)(leaf_length + suffix_length) << wide) + 1 - wide;
            /* Small arena blocks only read JSArena block metadata: no allocation,
               owner change or reentry between the proof and the commit. */
            size_t capacity = js_malloc_usable_size(ctx, leaf);
            if (capacity >= required) {
                if (wide)
                    memcpy(str16(leaf) + leaf_length, str16(suffix), (size_t)suffix_length << 1);
                else {
                    memcpy(str8(leaf) + leaf_length, str8(suffix), suffix_length);
                    str8(leaf)[leaf_length + suffix_length] = '\0';
                }
                if (unlikely(leaf->hash))
                    leaf->hash = 0;
                leaf->len = leaf_length + suffix_length;
                root->len = (uint32_t)length;
                root->depth = (uint8_t)depth;
                sp[-1] = JS_UNDEFINED;
                if (!keep) {
                    --JS_REF_COUNT(root);
                    sp[-2] = JS_UNDEFINED;
                }
                state->sp = sp - (keep ? 1 : 2);
                state->pc = pc + 1 + size;
                frame->saved_sp = state->sp;
                sf->cur_sp = state->sp;
                sf->cur_pc = state->pc;
                if (nonlast)
                    --JS_REF_COUNT(suffix);
                else {
                    /* NORMAL non-atom string destruction only frees memory and
                       cannot invoke host code or release objects. */
                    JS_FreeValue(ctx, rhs);
                }
                js_frame_finish_c(state);
                return 0;
            }
        }
    }
#endif
    old_right = root->right;
    old_length = root->len;
    old_depth = root->depth;
    old_width = root->is_wide_char;
    /* Keep the original left value across allocation/reentry, even if a
       callback linearizes the old rope or replaces the destination local. */
    prefix = js_dup(root->left);
    sp[-1] = JS_UNDEFINED; /* RHS ownership moves to the consuming helper. */
    right = JS_ConcatString(ctx, js_dup(old_right), rhs);
    if (JS_IsException(right)) {
        sp[-2] = JS_UNDEFINED;
        state->exception_pending = true;
        JS_FreeValue(ctx, prefix);
        JS_FreeValue(ctx, input);
        js_frame_finish_c(state);
        return JS_FrameInterpSlow(state);
    }
    /* Two short flat strings use the original flat concat algorithm. No
       root/local mutation happens until every fallible leaf step succeeded. */
    if (JS_REF_COUNT(root) == 2 && local_rope_same(*local, input) &&
        local_rope_same(root->left, prefix) && local_rope_same(root->right, old_right) &&
        root->len == old_length && root->depth == old_depth && root->is_wide_char == old_width &&
        JS_VALUE_GET_TAG(right) == JS_TAG_STRING) {
        uint64_t length = (uint64_t)local_rope_length(prefix) + JS_VALUE_GET_STRING(right)->len;
        unsigned depth = JS_VALUE_GET_TAG(prefix) == JS_TAG_STRING_ROPE
                             ? (unsigned)JS_VALUE_GET_STRING_ROPE(prefix)->depth + 1
                             : 1;
        if (length <= JS_STRING_LEN_MAX && depth <= JS_STRING_ROPE_MAX_DEPTH) {
            unsigned width = JS_VALUE_GET_TAG(prefix) == JS_TAG_STRING
                                 ? JS_VALUE_GET_STRING(prefix)->is_wide_char
                                 : JS_VALUE_GET_STRING_ROPE(prefix)->is_wide_char;
            root->right = right;
            root->len = (uint32_t)length;
            root->is_wide_char = width | JS_VALUE_GET_STRING(right)->is_wide_char;
            root->depth = (uint8_t)depth;
            JS_FreeValue(ctx, prefix); /* Non-last: the unchanged left edge owns it. */
            if (!keep) {
                --JS_REF_COUNT(root);
                sp[-2] = JS_UNDEFINED;
            }
            state->sp = sp - (keep ? 1 : 2);
            state->pc = pc + 1 + size;
            frame->saved_sp = state->sp;
            sf->cur_sp = state->sp;
            sf->cur_pc = state->pc;
            /* Logical local assignment is now complete. Release the removed
               leaf only after publishing the committed stack/cursor. */
            JS_FreeValue(ctx, old_right);
            js_frame_finish_c(state);
            return 0;
        }
    }
    /* A callback changed the proof, or a constructor limit requires the old
       path. Preserve captured operand values and finish the original store. */
    result = qjs_frame_core_js_new_string_rope(ctx, prefix, right);
    sp[-2] = JS_UNDEFINED;
    if (JS_IsException(result))
        state->exception_pending = true;
    JS_FreeValue(ctx, input);
    if (JS_IsException(result)) {
        js_frame_finish_c(state);
        return JS_FrameInterpSlow(state);
    }
    input = *local;
    if (keep) {
        *local = js_dup(result);
        sp[-2] = result;
    } else
        *local = result;
    state->sp = sp - (keep ? 1 : 2);
    state->pc = pc + 1 + size;
    frame->saved_sp = state->sp;
    sf->cur_sp = state->sp;
    sf->cur_pc = state->pc;
    JS_FreeValue(ctx, input);
    js_frame_finish_c(state);
    return 0;
}
