/* MIT. Compile OOM regression: every rejected allocation must fail with a
 * diagnostic or produce validated byte/wide matching code, and leak nothing. */
#include "quickjs.h"
#include "cutils.h"
#include "src/common/regexp/libregexp.h"
#include <assert.h>
#ifdef NDEBUG
#error Fault fixture requires active assertions.
#endif
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
enum {
#define DEF(id, size) OP_##id,
#include "src/common/regexp/libregexp-opcode.h"
#undef DEF
};
#include "native_oom_allocator.h"

static unsigned failures, successes, successful_fallbacks, injected;
static size_t compile_trial(unsigned offset, int flags, int window)
{
    Allocator memory = {0};
    JSRuntime *rt = JS_NewRuntime2(&functions, &memory);
    assert(rt);
    JSContext *ctx = JS_NewContext(rt);
    assert(ctx);
    int literal = window == 2;
    window = window == 1;
    const char *pattern = literal ? "abcd" : window ? "\\s?;\\s?" : "(^|[^x])abcdefgh";
    char error[128];
    int length;
    size_t before = memory.sequence;
    memory.fail_at = offset ? before + offset : 0;
    uint8_t *code =
        lre_compile(&length, error, sizeof(error), pattern, strlen(pattern), flags, ctx);
    memory.fail_at = 0;
    size_t calls = memory.sequence - before;
    if (code) {
        successes++;
        assert(!error[0]);
        assert(length > 19 && code[19] == (literal ? OP_literal_hint : OP_search_lookahead) &&
               (literal || (code[20] & 0x80)));
        assert(!lre_prepare_bytecode(code, length, true));
        if (!offset)
            printf("SEARCH_COMPILE_NOFAULT kind=%d flags=%d allocations=%zu bytes=%d\n",
                   literal ? 2 : window, flags, calls, length);
        uint8_t *capture[32];
        const uint8_t *input = (const uint8_t *)(literal  ? "zzzzabcd"
                                                 : window ? "zz ;"
                                                          : "zzzzabcdefgh");
        const uint8_t *missed =
            (const uint8_t *)(literal ? "xxxxxxxxxxxxxxxx" : "xxxxxxxxabcdefgh");
        const uint16_t old_wide[] = {0x4e2d, 'a', 'b', 'c', 'd', 'e', 'f', 'g', 'h'};
        const uint16_t window_wide[] = {0x4e2d, ' ', ';'};
        const uint16_t *wide = window ? window_wide : old_wide;
        int units = literal ? 5 : window ? 3 : 9;
        assert(lre_get_alloc_count(code) <= 32);
        assert(lre_exec(capture, code, input, 0, strlen((const char *)input), 0, ctx) == 1);
        assert(capture[0] == input + (literal  ? 4
                                      : window ? 2
                                               : 3) &&
               capture[1] == input + strlen((const char *)input));
        assert(lre_exec(capture, code, missed, 0, strlen((const char *)missed), 0, ctx) == 0);
        assert(lre_exec(capture, code, (const uint8_t *)wide, 0, units, 1, ctx) == 1);
        assert(capture[0] == (const uint8_t *)(wide + (literal || window ? 1 : 0)) &&
               capture[1] == (const uint8_t *)(wide + units));
        if (!literal)
            assert((code[20] & 0x40) == (window ? 0x40 : 0));
        if (memory.rejected) {
            ++successful_fallbacks;
            printf("SEARCH_COMPILE_VALID_FALLBACK flags=%d offset=%u calls=%zu\n", flags, offset,
                   calls);
        }
        js_free(ctx, code);
    } else {
        failures++;
        assert(offset && error[0]);
    }
    if (offset) {
        assert(memory.rejected == 1);
        ++injected;
    }
    JS_FreeValue(ctx, JS_GetException(ctx));
    JS_RunGC(rt);
    JS_FreeContext(ctx);
    JS_FreeRuntime(rt);
    assert(memory.live == 0 && memory.bytes == 0);
    return calls;
}
int main(void)
{
    for (int window = 0; window < 3; window++)
        for (int mode = 0; mode < 2; mode++) {
            int flags = mode ? LRE_FLAG_UNICODE : 0;
            size_t calls = compile_trial(0, flags, window);
            unsigned before = injected;
            for (unsigned at = 1; at <= calls; at++)
                compile_trial(at, flags, window);
            assert(injected - before == calls);
        }
    assert(failures && successes);
    printf(
        "SEARCH_COMPILE_FAULT_OK %u injections, %u fatal, %u valid fallback, %u success; zero live allocations\n",
        injected, failures, successful_fallbacks, successes);
    return 0;
}
