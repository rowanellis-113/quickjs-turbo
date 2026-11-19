/*
 * QuickJS Javascript Engine
 *
 * Copyright (c) 2017-2026 Fabrice Bellard
 * Copyright (c) 2017-2025 Charlie Gordon
 * Copyright (c) 2023-2026 Ben Noordhuis
 * Copyright (c) 2023-2026 Saúl Ibarra Corretgé
 *
 * Permission is hereby granted, free of charge, to any person obtaining a copy
 * of this software and associated documentation files (the "Software"), to deal
 * in the Software without restriction, including without limitation the rights
 * to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 * copies of the Software, and to permit persons to whom the Software is
 * furnished to do so, subject to the following conditions:
 *
 * The above copyright notice and this permission notice shall be included in
 * all copies or substantial portions of the Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
 * THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 * OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
 * THE SOFTWARE.
 */
/* Borrowed lookup for the callback-free descriptor guards only.
 * The returned atom is never retained, cached or held across allocation/JS.
 * regexp.py checks the pinned lookup and hash algorithm before generation.
 */
#ifndef QJS_REGEXP_FLAG_ATOM_LOOKUP_INCLUDED
#define QJS_REGEXP_FLAG_ATOM_LOOKUP_INCLUDED

_Static_assert(JS_ATOM_TYPE_STRING == 1 && JS_ATOM_HASH_MASK == 0x0fffffffu,
               "Review precomputed RegExp flag hashes after upstream change");

static inline JSAtom js_regexp_borrow_flag_atom(JSRuntime *rt, const char *name, size_t len,
                                                uint32_t hash)
{
    uint32_t h, i;
    JSAtomStruct *p;
    h = hash;
    h &= JS_ATOM_HASH_MASK;
    i = rt->atom_hash[h & (rt->atom_hash_size - 1)];
    while (i != 0) {
        p = rt->atom_array[i];
        if (p->hash == h && p->atom_type == JS_ATOM_TYPE_STRING && p->len == len &&
            p->is_wide_char == 0 && memcmp(str8(p), name, len) == 0)
            return i;
        i = p->hash_next;
    }
    return JS_ATOM_NULL;
}
#endif
