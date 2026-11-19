/* File input keeps its allocator, streaming reads and NUL terminator. Reserve
 * geometrically instead of reallocating the complete prefix every 8 KiB.
 * The legacy function is emitted from the pinned upstream body by the overlay.
 * Presence of QJS_DISABLE_FILE_LOAD_GROWTH selects that body for diagnostics. */
uint8_t *js_load_file(JSContext *ctx, size_t *pbuf_len, const char *filename)
{
    FILE *f;
    size_t n, len = 0, capacity = 0, need, next_capacity;
    uint8_t *p, *buf = NULL, tmp[8192];

    if (getenv("QJS_DISABLE_FILE_LOAD_GROWTH"))
        return js_load_file_legacy(ctx, pbuf_len, filename);
    f = fopen(filename, "rb");
    if (!f)
        return NULL;
    do {
        n = fread(tmp, 1, sizeof(tmp), f);
        if (n > SIZE_MAX - len - 1) {
            if (ctx)
                JS_ThrowOutOfMemory(ctx);
            goto fail;
        }
        need = len + n + 1;
        if (need > capacity) {
            next_capacity = capacity ? capacity : need;
            while (next_capacity < need) {
                if (next_capacity > SIZE_MAX / 2) {
                    next_capacity = need;
                    break;
                }
                next_capacity *= 2;
            }
            p = ctx ? js_realloc(ctx, buf, next_capacity) : realloc(buf, next_capacity);
            if (!p)
                goto fail;
            buf = p;
            capacity = next_capacity;
        }
        memcpy(buf + len, tmp, n);
        len += n;
        buf[len] = '\0';
    } while (n == sizeof(tmp));
    /* Parsing (or a binary buffer owner) need not retain spare input capacity.
     * Compact before handing off, while preserving the allocator/OOM contract. */
    if (capacity > len + 1 && !getenv("QJS_DISABLE_FILE_LOAD_COMPACT")) {
        p = ctx ? js_realloc(ctx, buf, len + 1) : realloc(buf, len + 1);
        if (!p)
            goto fail;
        buf = p;
    }
    fclose(f);
    *pbuf_len = len;
    return buf;
fail:
    if (ctx)
        js_free(ctx, buf);
    else
        free(buf);
    fclose(f);
    return NULL;
}
