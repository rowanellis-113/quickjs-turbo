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
    r = js_bigint_new(ctx, l);
    if (!r)
        return NULL;
    memcpy(r->tab, tab, (size_t)l * sizeof(js_limb_t));
    return r;
}

static int js_bigint_try_mod_pm(JSContext *ctx, js_limb_t *stk_r, int na, const js_limb_t *stk_b,
                                int nb, int a_sign, JSBigInt **out)
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

static inline bool js_bigint_try_divrem_stack(JSContext *ctx, const JSBigInt *a, const JSBigInt *b,
                                              int na, int nb, int a_sign, int b_sign, bool is_rem,
                                              JSBigInt **out)
{
    js_limb_t stk_r[66], stk_b[32], stk_q[66], h;
    JSBigInt *r;
    int shift;

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
