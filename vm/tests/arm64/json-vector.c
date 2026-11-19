/* Actual generated scanner boundaries,Latin1/UTF16 policy and NEON lane mask. MIT. */
#ifdef NDEBUG
#undef NDEBUG
#endif
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>
#include "src/arm64/common/json-vector.h"
#include "interpreter-aarch64-json-scan-test.h"
static unsigned long cases;
static void scan8(const uint8_t *p, size_t n)
{
    size_t expected = 0;
    while (expected < n && p[expected] >= 32 && p[expected] != '"' && p[expected] != '\\')
        ++expected;
    assert(linux_json_base_frame_json_scan8(p, n, 1) == expected);
    assert(linux_json_base_frame_json_scan8(p, n, 0) == expected);
    ++cases;
}
static void scan16(const uint16_t *p, size_t n)
{
    for (unsigned quote = 0; quote <= 1; ++quote) {
        size_t expected = 0;
        while (expected < n && p[expected] >= 32 && p[expected] != '"' && p[expected] != '\\' &&
               (!quote || (p[expected] & 0xf800) != 0xd800))
            ++expected;
        assert(linux_json_base_frame_json_scan16(p, n, 1, quote) == expected);
        assert(linux_json_base_frame_json_scan16(p, n, 0, quote) == expected);
        ++cases;
    }
}
int main(void)
{
    long page = sysconf(_SC_PAGESIZE);
    assert(page >= 4096);
    uint8_t *mapping = mmap(NULL, 3 * (size_t)page, PROT_NONE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    assert(mapping != MAP_FAILED &&
           !mprotect(mapping + page, (size_t)page, PROT_READ | PROT_WRITE));
    uint8_t *end = mapping + 2 * page;
    /* n0 points into PROT_NONE;every other buffer ends exactly at that page.
     * Varying n also varies vector alignment and every scalar/vector tail. */
    for (size_t n = 0; n <= 96; ++n) {
        uint8_t *p = end - n;
        memset(p, 0xe9, n);
        scan8(p, n);
        for (size_t pos = 0; pos < n; ++pos)
            for (unsigned c = 0; c < 256; ++c) {
                uint8_t old = p[pos];
                p[pos] = (uint8_t)c;
                scan8(p, n);
                p[pos] = old;
            }
    }
    for (size_t n = 0; n <= 48; ++n) {
        uint16_t *p = (uint16_t *)end - n;
        for (size_t i = 0; i < n; ++i)
            p[i] = 0x20ac;
        scan16(p, n);
        const uint16_t values[] = {0,   31,     32,     34,     92,     127,    128,    255,
                                   256, 0xd7ff, 0xd800, 0xdbff, 0xdc00, 0xdfff, 0xe000, 0xffff};
        for (size_t pos = 0; pos < n; ++pos)
            for (unsigned c = 0; c < sizeof(values) / sizeof(values[0]); ++c) {
                uint16_t old = p[pos];
                p[pos] = values[c];
                scan16(p, n);
                p[pos] = old;
            }
    }
    uint16_t *wide = (uint16_t *)end - 17;
    for (unsigned c = 0; c < 65536; ++c) {
        for (unsigned i = 0; i < 17; ++i)
            wide[i] = 0x20ac;
        wide[c % 17] = (uint16_t)c;
        scan16(wide, 17);
    }
    uint8_t bytes[16];
    for (unsigned mask = 0; mask < 65536; ++mask) {
        for (unsigned i = 0; i < 16; ++i)
            bytes[i] = (uint8_t)((mask & (1u << i) ? 128 : 0) | ((mask + i * 29) & 127));
        assert(qjs_json_vec_sign_mask(qjs_json_vec_load(bytes)) == mask);
        ++cases;
    }
    /* Byte-to-wide quote copies preserve high Latin1 bytes and both halves. */
    for (unsigned c = 0; c < 256; ++c) {
        for (unsigned i = 0; i < 16; ++i)
            bytes[i] = (uint8_t)(c + i);
        uint16_t *out = (uint16_t *)end - 16;
        QJSJSONVector value = qjs_json_vec_load(bytes), zero = qjs_json_vec_zero();
        qjs_json_vec_store(out, qjs_json_vec_interleave_low(value, zero));
        qjs_json_vec_store(out + 8, qjs_json_vec_interleave_high(value, zero));
        for (unsigned i = 0; i < 16; ++i)
            assert(out[i] == bytes[i]);
        ++cases;
    }
    assert(!munmap(mapping, 3 * (size_t)page));
    printf("AARCH64_JSON_VECTOR_OK cases=%lu guard_pages=2 utf16_exhaustive=65536 masks=65536\n",
           cases);
    return 0;
}
