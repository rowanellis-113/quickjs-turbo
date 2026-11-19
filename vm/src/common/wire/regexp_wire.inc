/* Shared serializer RegExp canonicalization; original runtime strings stay untouched. */
#ifdef QJS_FRAME_REGEXP_LEGACY_WIRE
#include "src/common/regexp/legacy-0151.h"
#define FRAME_REGEXP_WIRE_VERSION (BC_VERSION | 0x80)
typedef uint32_t FrameRegExpConstant;
#else
typedef uint8_t FrameRegExpConstant;
#endif

static int JS_RegExpConstantMask(JSContext *ctx, const JSFunctionBytecode *b,
                                 FrameRegExpConstant **pmask)
{
    uint32_t last_const = UINT32_MAX;
#ifdef QJS_FRAME_REGEXP_LEGACY_WIRE
    uint32_t previous_const = UINT32_MAX;
#endif
    int pos = 0;
    *pmask = NULL;
    if (b->cpool_count == 0)
        return 0;
    while (pos < b->byte_code_len) {
        const uint8_t *pc = b->byte_code_buf + pos;
        int op = pc[0];
        unsigned index = op >= OP_TEMP_START ? op + (OP_TEMP_END - OP_TEMP_START) : op;
        int len;
        if (index >= countof(opcode_info))
            goto bad;
        len = opcode_info[index].size;
        if (!len || len > b->byte_code_len - pos)
            goto bad;
        if (op == OP_regexp) {
            JSValueConst value;
            if (last_const >= (uint32_t)b->cpool_count)
                goto bad;
            value = b->cpool[last_const];
            if (JS_VALUE_GET_TAG(value) != JS_TAG_STRING ||
                JS_VALUE_GET_STRING(value)->is_wide_char)
                goto bad;
#ifdef QJS_FRAME_REGEXP_LEGACY_WIRE
            if (previous_const >= (uint32_t)b->cpool_count ||
                JS_VALUE_GET_TAG(b->cpool[previous_const]) != JS_TAG_STRING)
                goto bad;
#endif
            if (!*pmask) {
                *pmask = js_mallocz(ctx, (size_t)b->cpool_count * sizeof(**pmask));
                if (!*pmask)
                    goto fail;
            }
#ifdef QJS_FRAME_REGEXP_LEGACY_WIRE
            if ((*pmask)[last_const] && (*pmask)[last_const] != previous_const + 1)
                goto bad;
            (*pmask)[last_const] = previous_const + 1;
#else
            (*pmask)[last_const] = 1;
#endif
        }
#ifdef QJS_FRAME_REGEXP_LEGACY_WIRE
        previous_const = last_const;
#endif
        last_const = op == OP_push_const    ? get_u32(pc + 1)
                     : op == OP_push_const8 ? pc[1]
                                            : UINT32_MAX;
        pos += len;
    }
    return 0;
bad:
    JS_ThrowInternalError(ctx, "invalid regexp constant pool");
fail:
    js_free(ctx, *pmask);
    *pmask = NULL;
    return -1;
}

static int JS_FinishWriteRegExpBytecode(BCWriterState *s, JSString *bc)
{
    if (dbuf_error(&s->dbuf))
        return -1;
    if (lre_prepare_bytecode(s->dbuf.buf + s->dbuf.size - bc->len, bc->len, false)) {
        JS_ThrowInternalError(s->ctx, "bad regexp bytecode");
        return -1;
    }
    return 0;
}

#ifdef QJS_FRAME_REGEXP_LEGACY_WIRE
static int JS_WritePortableRegExpBytecode(BCWriterState *s, JSString *pattern, JSString *bc)
{
    JSContext *ctx = s->ctx;
    const char *source;
    uint8_t *legacy;
    size_t source_len;
    int legacy_len, flags;
    char error[128];
    if (bc->is_wide_char || bc->len < 8) {
        JS_ThrowInternalError(ctx, "bad regexp bytecode");
        return -1;
    }
    flags = lre_get_flags(str8(bc)) & ~LRE_FLAG_NAMED_GROUPS;
    source = JS_ToCStringLen2(ctx, &source_len, JS_MKPTR(JS_TAG_STRING, pattern),
                              !(flags & LRE_FLAG_UNICODE));
    if (!source)
        return -1;
    legacy = qjs_frame_regexp_legacy_compile(&legacy_len, error, sizeof(error), source, source_len,
                                             flags, ctx, bc->len);
    JS_FreeCString(ctx, source);
    if (legacy) {
        bc_put_leb128(s, (uint32_t)legacy_len << 1);
        dbuf_put(&s->dbuf, legacy, legacy_len);
        js_free(ctx, legacy);
        return dbuf_error(&s->dbuf) ? -1 : 0;
    }
    /* New Unicode features or a much larger old representation still round
       trip natively. Old readers reject this distinct version before parsing
       any payload, rather than executing a different instruction encoding. */
    s->extended_regexp = true;
    JS_WriteString(s, bc);
    return JS_FinishWriteRegExpBytecode(s, bc);
}

static JSString *JS_CompileImportedRegExp(JSContext *ctx, JSString *pattern, JSString *serialized)
{
    const uint8_t *data;
    const char *source;
    size_t source_len;
    uint8_t *bytecode, *storage;
    JSString *result;
    int length, flags;
    char error[128];
    if (serialized->is_wide_char || serialized->len < 8)
        goto invalid;
    data = str8(serialized);
    if (get_u32(data + 4) > (uint32_t)(serialized->len - 8))
        goto invalid;
    flags = get_u16(data);
    if ((flags & ~0x1ff) || (flags & (LRE_FLAG_UNICODE | LRE_FLAG_UNICODE_SETS)) ==
                                (LRE_FLAG_UNICODE | LRE_FLAG_UNICODE_SETS))
        goto invalid;
    flags &= ~LRE_FLAG_NAMED_GROUPS;
    source = JS_ToCStringLen2(ctx, &source_len, JS_MKPTR(JS_TAG_STRING, pattern),
                              !(flags & LRE_FLAG_UNICODE));
    if (!source)
        return NULL;
    bytecode = lre_compile(&length, error, sizeof(error), source, source_len, flags, ctx);
    JS_FreeCString(ctx, source);
    if (!bytecode) {
        JS_ThrowSyntaxError(ctx, "%s", error);
        return NULL;
    }
    /* Use the pinned core's indirect-string ownership contract. No imported
       instruction is executed, and no runtime bytecode copy is needed. */
    result = js_alloc_string(ctx, sizeof(bytecode), 0);
    if (!result) {
        js_free(ctx, bytecode);
        return NULL;
    }
    storage = str8(result);
    memcpy(storage, &bytecode, sizeof(bytecode));
    storage[sizeof(bytecode)] = 0;
    result->kind = JS_STRING_KIND_INDIRECT;
    result->len = length;
    return result;
invalid:
    JS_ThrowInternalError(ctx, "bad regexp bytecode");
    return NULL;
}
#endif

static int JS_PrepareFunctionRegExp(JSContext *ctx, JSFunctionBytecode *b)
{
    FrameRegExpConstant *mask;
    int i, ret = 0;
    if (JS_RegExpConstantMask(ctx, b, &mask))
        return -1;
    if (mask) {
        for (i = 0; i < b->cpool_count; i++) {
            if (mask[i]) {
                /* Each imported string was freshly allocated by JS_ReadString. */
                JSString *bc = JS_VALUE_GET_STRING(b->cpool[i]);
#ifdef QJS_FRAME_REGEXP_LEGACY_WIRE
                JSString *pattern = JS_VALUE_GET_STRING(b->cpool[mask[i] - 1]);
                JSString *runtime = JS_CompileImportedRegExp(ctx, pattern, bc);
                if (!runtime) {
                    ret = -1;
                    break;
                }
                /* Publish the replacement owner before allocator release can
                   reenter or trigger collection. The live function owns it. */
                b->cpool[i] = JS_MKPTR(JS_TAG_STRING, runtime);
                JS_FreeValue(ctx, JS_MKPTR(JS_TAG_STRING, bc));
#else
                if (lre_prepare_bytecode(str8(bc), bc->len, true)) {
                    JS_ThrowInternalError(ctx, "bad regexp bytecode");
                    ret = -1;
                    break;
                }
#endif
            }
        }
        js_free(ctx, mask);
    }
    return ret;
}
