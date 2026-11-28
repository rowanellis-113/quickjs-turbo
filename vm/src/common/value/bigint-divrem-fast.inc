/* Stack-limb and pseudo-Mersenne modulus fast paths for BigInt div/rem. */
static JSBigInt *js_bigint_from_stack_limbs(JSContext *ctx, const js_limb_t *tab, int l)
{
    JSBigInt *r;
    js_limb_t v;

    while (l > 1) {
        v = tab[l - 1];
        if ((v != (js_limb_t)0 && v != (js_limb_t)-1) ||
            (v & 1) != (tab[l - 2] >> (JS_LIMB_BITS - 1))) {
            break;
        }
        l--;
    }
    r = qjs_bigint_alloc_fast(ctx, l);
    if (!r)
        return NULL;
    memcpy(r->tab, tab, (size_t)l * sizeof(js_limb_t));
    return r;
}

static QJS_BIGINT_COLD_CODE int js_bigint_try_mod_pm(JSContext *ctx, js_limb_t *stk_r, int na,
                                                     const js_limb_t *stk_b, int nb, int a_sign,
                                                     JSBigInt **out)
{
    int i, top_bits;
    js_limb_t c, top;

    if (nb < 3)
        return 0;
    c = (js_limb_t)(0u - stk_b[0]);
    if (c == 0 || c >= ((js_limb_t)1 << 29))
        return 0;
    for (i = 1; i < nb - 1; i++) {
        if (stk_b[i] != (js_limb_t)-1)
            return 0;
    }
    top = stk_b[nb - 1];
    if (top == 0 || (top & (top + 1u)) != 0)
        return 0;

#if defined(__SIZEOF_INT128__) || (defined(_MSC_VER) && defined(_M_X64))
    /* 64-bit branchless pseudo-Mersenne fast path for P = 2^255 - c (e.g. Ed25519 2^255 - 19). */
    if (nb == 8 && top == UINT32_C(0x7fffffff) && na <= 17) {
        for (i = na; i < 18; i++)
            stk_r[i] = 0;
        uint64_t lo0 = (uint64_t)stk_r[0] | ((uint64_t)stk_r[1] << 32);
        uint64_t lo1 = (uint64_t)stk_r[2] | ((uint64_t)stk_r[3] << 32);
        uint64_t lo2 = (uint64_t)stk_r[4] | ((uint64_t)stk_r[5] << 32);
        uint64_t lo3 = (uint64_t)stk_r[6] | ((uint64_t)stk_r[7] << 32);
        uint64_t hi0 = (uint64_t)stk_r[8] | ((uint64_t)stk_r[9] << 32);
        uint64_t hi1 = (uint64_t)stk_r[10] | ((uint64_t)stk_r[11] << 32);
        uint64_t hi2 = (uint64_t)stk_r[12] | ((uint64_t)stk_r[13] << 32);
        uint64_t hi3 = (uint64_t)stk_r[14] | ((uint64_t)stk_r[15] << 32);
        uint64_t hi4 = (uint64_t)stk_r[16];
        uint64_t c2 = (uint64_t)c * 2u;
        uint64_t w0, w1, w2, w3, carry;
#if defined(__SIZEOF_INT128__)
        __uint128_t t;
        t = (__uint128_t)lo0 + (__uint128_t)hi0 * c2 + (__uint128_t)hi4 * (c2 * c2);
        w0 = (uint64_t)t;
        t = (__uint128_t)lo1 + (__uint128_t)hi1 * c2 + (uint64_t)(t >> 64);
        w1 = (uint64_t)t;
        t = (__uint128_t)lo2 + (__uint128_t)hi2 * c2 + (uint64_t)(t >> 64);
        w2 = (uint64_t)t;
        t = (__uint128_t)lo3 + (__uint128_t)hi3 * c2 + (uint64_t)(t >> 64);
        w3 = (uint64_t)t;
        carry = (uint64_t)(t >> 64);
#else
        uint64_t p_hi, p_lo, p4_hi, p4_lo, acc_hi;
        unsigned char cf;
        p_lo = _umul128(hi0, c2, &p_hi);
        p4_lo = _umul128(hi4, c2 * c2, &p4_hi);
        cf = _addcarry_u64(0, lo0, p_lo, &w0);
        acc_hi = p_hi + cf;
        cf = _addcarry_u64(0, w0, p4_lo, &w0);
        carry = acc_hi + p4_hi + cf;

        p_lo = _umul128(hi1, c2, &p_hi);
        cf = _addcarry_u64(0, lo1, p_lo, &w1);
        acc_hi = p_hi + cf;
        cf = _addcarry_u64(0, w1, carry, &w1);
        carry = acc_hi + cf;

        p_lo = _umul128(hi2, c2, &p_hi);
        cf = _addcarry_u64(0, lo2, p_lo, &w2);
        acc_hi = p_hi + cf;
        cf = _addcarry_u64(0, w2, carry, &w2);
        carry = acc_hi + cf;

        p_lo = _umul128(hi3, c2, &p_hi);
        cf = _addcarry_u64(0, lo3, p_lo, &w3);
        acc_hi = p_hi + cf;
        cf = _addcarry_u64(0, w3, carry, &w3);
        carry = acc_hi + cf;
#endif
        uint64_t fold = (carry << 1) | (w3 >> 63);
        w3 &= UINT64_C(0x7fffffffffffffff);
        uint64_t add0 = fold * (uint64_t)c;
        uint64_t nw0 = w0 + add0;
        uint64_t fc = (nw0 < w0) ? 1u : 0u;
        w0 = nw0;
        if (unlikely(fc)) {
            w1 += 1u;
            if (w1 == 0u) {
                w2 += 1u;
                if (w2 == 0u) {
                    w3 += 1u;
                    if (w3 >> 63) {
                        w3 &= UINT64_C(0x7fffffffffffffff);
                        uint64_t nw = w0 + (uint64_t)c;
                        if (nw < w0) {
                            w1++;
                            if (w1 == 0u) {
                                w2++;
                                if (w2 == 0u)
                                    w3++;
                            }
                        }
                        w0 = nw;
                    }
                }
            }
        }
        if (unlikely(w3 == UINT64_C(0x7fffffffffffffff) && w2 == UINT64_MAX && w1 == UINT64_MAX &&
                     w0 >= (UINT64_C(0) - (uint64_t)c))) {
            w0 += (uint64_t)c;
            w1 = 0;
            w2 = 0;
            w3 = 0;
        }
        stk_r[0] = (js_limb_t)w0;
        stk_r[1] = (js_limb_t)(w0 >> 32);
        stk_r[2] = (js_limb_t)w1;
        stk_r[3] = (js_limb_t)(w1 >> 32);
        stk_r[4] = (js_limb_t)w2;
        stk_r[5] = (js_limb_t)(w2 >> 32);
        stk_r[6] = (js_limb_t)w3;
        stk_r[7] = (js_limb_t)(w3 >> 32);
        stk_r[8] = 0;
        if (a_sign)
            js_mp_neg(stk_r, stk_r, 9);
        *out = js_bigint_from_stack_limbs(ctx, stk_r, 9);
        return 1;
    }
#endif

    top_bits = JS_LIMB_BITS - js_limb_clz(top);
    for (;;) {
        js_limb_t hi[66];
        int q_len, new_na;
        uint64_t carry;

        while (na > 1 && stk_r[na - 1] == 0)
            na--;
        if (na < nb)
            break;
        if (top_bits == JS_LIMB_BITS) {
            q_len = na - nb;
            if (q_len == 0)
                break;
            memcpy(hi, stk_r + nb, (size_t)q_len * sizeof(js_limb_t));
        } else {
            int q_shift = JS_LIMB_BITS - top_bits;
            js_limb_t last_q;
            q_len = 0;
            for (i = nb - 1; i + 1 < na; i++)
                hi[q_len++] = (stk_r[i] >> top_bits) | (stk_r[i + 1] << q_shift);
            last_q = stk_r[na - 1] >> top_bits;
            if (last_q != 0)
                hi[q_len++] = last_q;
            while (q_len > 0 && hi[q_len - 1] == 0)
                q_len--;
            if (q_len == 0)
                break;
            stk_r[nb - 1] &= top;
        }
        new_na = max_int(nb, q_len) + 1;
        for (i = nb; i < new_na; i++)
            stk_r[i] = 0;
        carry = 0;
        for (i = 0; i < q_len; i++) {
            uint64_t t = (uint64_t)stk_r[i] + (uint64_t)hi[i] * (uint64_t)c + carry;
            stk_r[i] = (js_limb_t)t;
            carry = t >> 32;
        }
        while (carry && i < new_na) {
            uint64_t t = (uint64_t)stk_r[i] + carry;
            stk_r[i] = (js_limb_t)t;
            carry = t >> 32;
            i++;
        }
        na = new_na;
    }

    for (i = na; i <= nb; i++)
        stk_r[i] = 0;
    {
        int cmp = 0;
        for (i = nb - 1; i >= 0; i--) {
            if (stk_r[i] != stk_b[i]) {
                cmp = (stk_r[i] > stk_b[i]) ? 1 : -1;
                break;
            }
        }
        if (cmp >= 0)
            js_mp_sub(stk_r, stk_r, stk_b, nb, 0);
    }
    if (a_sign)
        js_mp_neg(stk_r, stk_r, nb + 1);
    *out = js_bigint_from_stack_limbs(ctx, stk_r, nb + 1);
    return 1;
}

#define QJS_BIGINT_PM255_DIRECT 1
static QJS_BIGINT_COLD_CODE JSBigInt *js_bigint_mod_pm255_direct(JSContext *ctx, const JSBigInt *a,
                                                                 uint32_t c, int a_sign)
{
    uint32_t na = (uint32_t)a->len;
    uint64_t w[9] = {0, 0, 0, 0, 0, 0, 0, 0, 0};
    uint32_t nw = (na + 1u) >> 1;
    if (!a_sign) {
        for (uint32_t i = 0; i < nw; i++) {
            uint64_t lo = a->tab[2u * i];
            uint64_t hi = (2u * i + 1u < na) ? (uint64_t)a->tab[2u * i + 1u] : 0u;
            w[i] = lo | (hi << 32);
        }
    } else {
        uint64_t borrow = 0;
        for (uint32_t i = 0; i < nw; i++) {
            uint64_t lo = a->tab[2u * i];
            uint64_t hi = (2u * i + 1u < na) ? (uint64_t)a->tab[2u * i + 1u] : UINT64_C(0xffffffff);
            uint64_t v = lo | (hi << 32);
            w[i] = (uint64_t)0 - v - borrow;
            borrow = (v | borrow) != 0u ? 1u : 0u;
        }
        /* For na == 17 negative, top limb is 0xffffffff.. sign-extended; mask top 32 bits of w[8]. */
        if (na & 1u)
            w[nw - 1u] &= UINT64_C(0xffffffff);
    }
    uint64_t c2 = (uint64_t)c * 2u;
    uint64_t w0, w1, w2, w3, carry;
#if defined(__SIZEOF_INT128__)
    __uint128_t t;
    t = (__uint128_t)w[0] + (__uint128_t)w[4] * c2 + (__uint128_t)w[8] * (c2 * c2);
    w0 = (uint64_t)t;
    t = (__uint128_t)w[1] + (__uint128_t)w[5] * c2 + (uint64_t)(t >> 64);
    w1 = (uint64_t)t;
    t = (__uint128_t)w[2] + (__uint128_t)w[6] * c2 + (uint64_t)(t >> 64);
    w2 = (uint64_t)t;
    t = (__uint128_t)w[3] + (__uint128_t)w[7] * c2 + (uint64_t)(t >> 64);
    w3 = (uint64_t)t;
    carry = (uint64_t)(t >> 64);
#elif defined(_MSC_VER) && defined(_M_X64)
    uint64_t p_hi, p_lo, p4_hi, p4_lo, acc_hi;
    unsigned char cf;
    p_lo = _umul128(w[4], c2, &p_hi);
    p4_lo = _umul128(w[8], c2 * c2, &p4_hi);
    cf = _addcarry_u64(0, w[0], p_lo, &w0);
    acc_hi = p_hi + cf;
    cf = _addcarry_u64(0, w0, p4_lo, &w0);
    carry = acc_hi + p4_hi + cf;

    p_lo = _umul128(w[5], c2, &p_hi);
    cf = _addcarry_u64(0, w[1], p_lo, &w1);
    acc_hi = p_hi + cf;
    cf = _addcarry_u64(0, w1, carry, &w1);
    carry = acc_hi + cf;

    p_lo = _umul128(w[6], c2, &p_hi);
    cf = _addcarry_u64(0, w[2], p_lo, &w2);
    acc_hi = p_hi + cf;
    cf = _addcarry_u64(0, w2, carry, &w2);
    carry = acc_hi + cf;

    p_lo = _umul128(w[7], c2, &p_hi);
    cf = _addcarry_u64(0, w[3], p_lo, &w3);
    acc_hi = p_hi + cf;
    cf = _addcarry_u64(0, w3, carry, &w3);
    carry = acc_hi + cf;
#endif
    uint64_t fold = (carry << 1) | (w3 >> 63);
    w3 &= UINT64_C(0x7fffffffffffffff);
    uint64_t add0 = fold * (uint64_t)c;
    uint64_t nw0 = w0 + add0;
    if (unlikely(nw0 < w0)) {
        w0 = nw0;
        if (++w1 == 0u && ++w2 == 0u && (++w3 >> 63)) {
            w3 &= UINT64_C(0x7fffffffffffffff);
            uint64_t nw1 = w0 + (uint64_t)c;
            if (nw1 < w0 && ++w1 == 0u && ++w2 == 0u)
                w3++;
            w0 = nw1;
        }
    } else {
        w0 = nw0;
    }
    if (unlikely(w3 == UINT64_C(0x7fffffffffffffff) && w2 == UINT64_MAX && w1 == UINT64_MAX &&
                 w0 >= (UINT64_C(0) - (uint64_t)c))) {
        w0 += (uint64_t)c;
        w1 = 0;
        w2 = 0;
        w3 = 0;
    }
    if (unlikely(a_sign && (w0 | w1 | w2 | w3) != 0u)) {
        uint64_t b0 = 0;
        uint64_t v0 = w0;
        w0 = (uint64_t)0 - v0;
        b0 = v0 != 0u ? 1u : 0u;
        uint64_t v1 = w1;
        w1 = (uint64_t)0 - v1 - b0;
        b0 = (v1 | b0) != 0u ? 1u : 0u;
        uint64_t v2 = w2;
        w2 = (uint64_t)0 - v2 - b0;
        b0 = (v2 | b0) != 0u ? 1u : 0u;
        w3 = (uint64_t)0 - w3 - b0;
        js_limb_t out_l[9];
        out_l[0] = (js_limb_t)w0;
        out_l[1] = (js_limb_t)(w0 >> 32);
        out_l[2] = (js_limb_t)w1;
        out_l[3] = (js_limb_t)(w1 >> 32);
        out_l[4] = (js_limb_t)w2;
        out_l[5] = (js_limb_t)(w2 >> 32);
        out_l[6] = (js_limb_t)w3;
        out_l[7] = (js_limb_t)(w3 >> 32);
        out_l[8] = (js_limb_t)-1;
        return js_bigint_from_stack_limbs(ctx, out_l, 9);
    }
    uint64_t top;
    uint32_t out_nw;
    if (w3) {
        out_nw = 4u;
        top = w3;
    } else if (w2) {
        out_nw = 3u;
        top = w2;
    } else if (w1) {
        out_nw = 2u;
        top = w1;
    } else {
        out_nw = 1u;
        top = w0;
    }
    uint32_t l = (top >> 32) ? (out_nw * 2u + (uint32_t)(top >> 63))
                             : (out_nw * 2u - 1u + (uint32_t)((uint32_t)top >> 31));
    JSBigInt *res = qjs_bigint_alloc_fast(ctx, (int)l);
    if (likely(res != NULL)) {
        res->tab[0] = (js_limb_t)w0;
        if (l > 1u)
            res->tab[1] = (js_limb_t)(w0 >> 32);
        if (l > 2u)
            res->tab[2] = (js_limb_t)w1;
        if (l > 3u)
            res->tab[3] = (js_limb_t)(w1 >> 32);
        if (l > 4u)
            res->tab[4] = (js_limb_t)w2;
        if (l > 5u)
            res->tab[5] = (js_limb_t)(w2 >> 32);
        if (l > 6u)
            res->tab[6] = (js_limb_t)w3;
        if (l > 7u)
            res->tab[7] = (js_limb_t)(w3 >> 32);
        if (l > 8u)
            res->tab[8] = 0;
    }
    return res;
}

static inline bool js_bigint_try_divrem_stack(JSContext *ctx, const JSBigInt *a, const JSBigInt *b,
                                              int na, int nb, int a_sign, int b_sign, bool is_rem,
                                              JSBigInt **out)
{
    js_limb_t stk_r[66], stk_b[32], stk_q[66], h;
    JSBigInt *r;
    int shift;

#if defined(__SIZEOF_INT128__) || (defined(_MSC_VER) && defined(_M_X64))
    if (likely(is_rem && !b_sign && nb == 8 && na >= 8 && na <= 17 &&
               b->tab[7] == UINT32_C(0x7fffffff) && b->tab[6] == UINT32_MAX &&
               b->tab[5] == UINT32_MAX && b->tab[4] == UINT32_MAX && b->tab[3] == UINT32_MAX &&
               b->tab[2] == UINT32_MAX && b->tab[1] == UINT32_MAX)) {
        uint32_t c = (uint32_t)(0u - b->tab[0]);
        if (likely(c != 0u && c < (UINT32_C(1) << 29))) {
            *out = js_bigint_mod_pm255_direct(ctx, a, c, a_sign);
            return true;
        }
    }
#endif

    if (na > 64 || nb > 32)
        return false;

    if (a_sign)
        js_mp_neg(stk_r, a->tab, na);
    else
        memcpy(stk_r, a->tab, (size_t)na * sizeof(a->tab[0]));
    while (na > 1 && stk_r[na - 1] == 0)
        na--;

    if (b_sign)
        js_mp_neg(stk_b, b->tab, nb);
    else
        memcpy(stk_b, b->tab, (size_t)nb * sizeof(stk_b[0]));
    while (nb > 1 && stk_b[nb - 1] == 0)
        nb--;

    if (na < nb) {
        if (is_rem) {
            r = js_bigint_new(ctx, a->len);
            if (r)
                memcpy(r->tab, a->tab, (size_t)a->len * sizeof(a->tab[0]));
            *out = r;
            return true;
        }
        *out = js_bigint_new_si(ctx, 0);
        return true;
    }

    if (is_rem) {
        JSBigInt *pm_res = NULL;
        if (js_bigint_try_mod_pm(ctx, stk_r, na, stk_b, nb, a_sign, &pm_res)) {
            *out = pm_res;
            return true;
        }
    }

    shift = js_limb_clz(stk_b[nb - 1]);
    if (shift != 0) {
        js_mp_shl(stk_b, stk_b, nb, shift);
        h = js_mp_shl(stk_r, stk_r, na, shift);
        if (h != 0)
            stk_r[na++] = h;
    }
    js_mp_divnorm(stk_q, stk_r, na, stk_b, nb);
    if (is_rem) {
        if (shift != 0)
            js_mp_shr(stk_r, stk_r, nb, shift, 0);
        stk_r[nb++] = 0;
        if (a_sign)
            js_mp_neg(stk_r, stk_r, nb);
        *out = js_bigint_from_stack_limbs(ctx, stk_r, nb);
    } else {
        int qn = na - nb + 2;
        stk_q[na - nb + 1] = 0;
        if (a_sign ^ b_sign)
            js_mp_neg(stk_q, stk_q, qn);
        *out = js_bigint_from_stack_limbs(ctx, stk_q, qn);
    }
    return true;
}

static inline int qjs_bigint_try_mod_pm255_fast(JSContext *ctx, const JSBigInt *a,
                                                const JSBigInt *b, JSBigInt **out)
{
#if defined(__SIZEOF_INT128__) || (defined(_MSC_VER) && defined(_M_X64))
    if (likely(b->len == 8 && b->tab[7] == UINT32_C(0x7fffffff) && b->tab[6] == UINT32_MAX &&
               b->tab[5] == UINT32_MAX && b->tab[4] == UINT32_MAX && b->tab[3] == UINT32_MAX &&
               b->tab[2] == UINT32_MAX && b->tab[1] == UINT32_MAX)) {
        uint32_t c = (uint32_t)(0u - b->tab[0]);
        if (likely(c != 0u && c < (UINT32_C(1) << 29))) {
            int na = a->len;
            if (na < 8 || (na == 8 && (a->tab[7] >> 31) == 0u && a->tab[7] < UINT32_C(0x7fffffff)))
                return 2;
            if (na <= 17) {
                *out = js_bigint_mod_pm255_direct(ctx, a, c, (int)(a->tab[na - 1] >> 31));
                return 1;
            }
        }
    }
#else
    (void)ctx;
    (void)a;
    (void)b;
    (void)out;
#endif
    return 0;
}

static QJS_BIGINT_COLD_CODE int
qjs_binary_arith_bigint_fast(JSContext *ctx, JSValue *sp, OPCodeEnum op, JSValue op1, JSValue op2)
{
    if (likely(JS_VALUE_GET_TAG(op1) == JS_TAG_BIG_INT &&
               JS_VALUE_GET_TAG(op2) == JS_TAG_BIG_INT)) {
        JSBigInt *bp1 = JS_VALUE_GET_PTR(op1);
        JSBigInt *bp2 = JS_VALUE_GET_PTR(op2);
        JSBigInt *br = NULL;
        if (op == OP_mod) {
            int pm = qjs_bigint_try_mod_pm255_fast(ctx, bp1, bp2, &br);
            if (pm == 2) {
                if (--JS_REF_COUNT(bp2) <= 0)
                    qjs_bigint_pool_put(ctx->rt, bp2);
                sp[-2] = op1;
                return 1;
            }
            if (pm == 1) {
                if (--JS_REF_COUNT(bp1) <= 0)
                    qjs_bigint_pool_put(ctx->rt, bp1);
                if (--JS_REF_COUNT(bp2) <= 0)
                    qjs_bigint_pool_put(ctx->rt, bp2);
                if (unlikely(!br))
                    return -1;
                if (likely(br->len > 1)) {
                    sp[-2] = JS_MKPTR(JS_TAG_BIG_INT, br);
                } else {
                    sp[-2] = __JS_NewShortBigInt(ctx, (js_slimb_t)br->tab[0]);
                    qjs_bigint_pool_put(ctx->rt, br);
                }
                return 1;
            }
        } else if (op == OP_sub && bp1->len <= 9 && bp2->len <= 9) {
            br = qjs_bigint_add_sub_u256(ctx, bp1, bp2, 1);
            if (--JS_REF_COUNT(bp1) <= 0)
                qjs_bigint_pool_put(ctx->rt, bp1);
            if (--JS_REF_COUNT(bp2) <= 0)
                qjs_bigint_pool_put(ctx->rt, bp2);
            if (unlikely(!br))
                return -1;
            if (likely(br->len > 1)) {
                sp[-2] = JS_MKPTR(JS_TAG_BIG_INT, br);
            } else {
                sp[-2] = __JS_NewShortBigInt(ctx, (js_slimb_t)br->tab[0]);
                qjs_bigint_pool_put(ctx->rt, br);
            }
            return 1;
        }
    }
    return 0;
}

static QJS_BIGINT_COLD_CODE int
qjs_binary_logic_bigint_fast(JSContext *ctx, JSValue *sp, OPCodeEnum op, JSValue op1, JSValue op2)
{
    if (JS_VALUE_GET_TAG(op1) == JS_TAG_BIG_INT && JS_VALUE_GET_TAG(op2) == JS_TAG_SHORT_BIG_INT) {
        JSBigInt *bp1 = JS_VALUE_GET_PTR(op1);
        js_slimb_t sv = JS_VALUE_GET_SHORT_BIG_INT(op2);
        if (op == OP_and && sv >= 0) {
            js_slimb_t rv = (js_slimb_t)(bp1->tab[0] & (js_limb_t)sv);
            if (--JS_REF_COUNT(bp1) <= 0)
                qjs_bigint_pool_put(ctx->rt, bp1);
            sp[-2] = __JS_NewShortBigInt(ctx, rv);
            return 1;
        }
        if (op == OP_sar && sv > 0 && sv < 32 && (bp1->tab[bp1->len - 1] >> 31) == 0u) {
            JSBigInt *br = qjs_bigint_shr_small(ctx, bp1, (uint32_t)sv);
            if (--JS_REF_COUNT(bp1) <= 0)
                qjs_bigint_pool_put(ctx->rt, bp1);
            if (unlikely(!br))
                return -1;
            if (likely(br->len > 1)) {
                sp[-2] = JS_MKPTR(JS_TAG_BIG_INT, br);
            } else {
                sp[-2] = __JS_NewShortBigInt(ctx, (js_slimb_t)br->tab[0]);
                qjs_bigint_pool_put(ctx->rt, br);
            }
            return 1;
        }
    }
    return 0;
}
