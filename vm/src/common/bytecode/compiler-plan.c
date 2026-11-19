/* Bounded compiler analyses, isolated from the runtime interpreter TU.
 * Private code/label views are borrowed only during the call. No retained
 * metadata, public opcode, frame layout, runtime guard or JS allocation.
 */
#include "compiler-plan-view.h"
#include "cutils.h"
#include <stdlib.h>
#include <string.h>
#define SHORT_OPCODES 1
typedef enum {
#define FMT(f) OP_FMT_##f,
#define DEF(id, size, npop, npush, f)
#include "quickjs-opcode.h"
#undef DEF
#undef FMT
} CompilerOpFormat;
typedef enum {
#define FMT(f)
#define DEF(id, size, npop, npush, f) OP_##id,
#define def(id, size, npop, npush, f)
#include "quickjs-opcode.h"
#undef def
#undef DEF
#undef FMT
    OP_COUNT,
    OP_TEMP_START = OP_nop + 1,
    OP___dummy = OP_TEMP_START - 1,
#define FMT(f)
#define DEF(id, size, npop, npush, f)
#define def(id, size, npop, npush, f) OP_##id,
#include "quickjs-opcode.h"
#undef def
#undef DEF
#undef FMT
    OP_TEMP_END
} CompilerOpCode;
#if defined(_MSC_VER)
#pragma code_seg(push, ".qjzzec$zzcompilerC")
#pragma section(".qjzzec$zzcompilerD", read)
#define TDZ_WORKER_CODE __declspec(noinline)
#define TDZ_WORKER_LOCAL_CODE
#define TDZ_WORKER_RO __declspec(allocate(".qjzzec$zzcompilerD"))
#elif defined(_WIN32) && defined(__GNUC__)
#if !defined(__clang__)
#define TDZ_WORKER_SWITCH __attribute__((optimize("no-jump-tables,no-tree-switch-conversion")))
#else
#define TDZ_WORKER_SWITCH
#endif
#define TDZ_WORKER_CODE __attribute__((noinline, section(".qjscmp$C"))) TDZ_WORKER_SWITCH
#define TDZ_WORKER_LOCAL_CODE __attribute__((section(".qjscmp$C"))) TDZ_WORKER_SWITCH
#define TDZ_WORKER_RO __attribute__((section(".qjscmp$D"), used))
#else
#define TDZ_WORKER_CODE
#define TDZ_WORKER_LOCAL_CODE
#define TDZ_WORKER_RO
#endif
static TDZ_WORKER_RO const char tdz_disable_plan[] = "QJS_DISABLE_TDZ_PLAN";
static TDZ_WORKER_RO const char tdz_disable_init[] = "QJS_DISABLE_TDZ_INIT";
static inline unsigned compiler_op_size(const QJSCompilerCode *b, unsigned op)
{
    return b->opcode_sizes[op];
}
static inline unsigned compiler_op_fmt(const QJSCompilerCode *b, unsigned op)
{
    return b->opcode_formats[op];
}
static inline int compiler_label_get(const QJSCompilerCode *b, unsigned index)
{
    int32_t value;
    memcpy(&value, (const uint8_t *)b->label_slots + index * b->label_stride + b->label_pos2_offset,
           4);
    return value;
}
static inline void compiler_label_set(QJSCompilerCode *b, unsigned index, int32_t value)
{
    memcpy((uint8_t *)b->label_slots + index * b->label_stride + b->label_pos2_offset, &value, 4);
}
static TDZ_WORKER_CODE void compiler_compact_entry(QJSCompilerCode *b, const uint32_t *erased,
                                                   unsigned count)
{
    if (!count)
        return;
    /* No referenced label enters an erased position. Keep label IDs and all
     * source_loc instructions; map every defined pos2 before the inherited
     * jump/shortening/source pass. Unbound unused positions remain unbound.
     */
    for (unsigned label = 0; label < (unsigned)b->label_count; label++) {
        int pos = compiler_label_get(b, label);
        if (pos < 0 || (uint32_t)pos > b->byte_code.size)
            continue;
        unsigned removed = 0;
        while (removed < count && erased[removed] + 3 <= (uint32_t)pos)
            removed++;
        compiler_label_set(b, label, pos - 3 * removed);
    }
    uint32_t input = 0, output = 0;
    for (unsigned i = 0; i < count; i++) {
        uint32_t bytes = erased[i] - input;
        memmove(b->byte_code.buf + output, b->byte_code.buf + input, bytes);
        output += bytes;
        input = erased[i] + 3;
    }
    uint32_t bytes = b->byte_code.size - input;
    memmove(b->byte_code.buf + output, b->byte_code.buf + input, bytes);
    b->byte_code.size = output + bytes;
}
#define TDZ_PLAN_BLOCKS 256
typedef struct {
    uint32_t start[TDZ_PLAN_BLOCKS + 1];
    uint64_t gen[TDZ_PLAN_BLOCKS], kill[TDZ_PLAN_BLOCKS];
    uint64_t input[TDZ_PLAN_BLOCKS], output[TDZ_PLAN_BLOCKS];
    uint16_t successor[TDZ_PLAN_BLOCKS][2], queue[TDZ_PLAN_BLOCKS];
    uint8_t root[TDZ_PLAN_BLOCKS], reachable[TDZ_PLAN_BLOCKS];
    uint8_t processed[TDZ_PLAN_BLOCKS], queued[TDZ_PLAN_BLOCKS];
    unsigned count;
} JSTdzPlan;

/* 0 ordinary,1 jump,2 condition,3 catch,4 terminal,5 unsupported. */
static TDZ_WORKER_LOCAL_CODE int js_tdz_edge(unsigned op)
{
    switch (op) {
    case OP_goto:
        return 1;
    case OP_if_true:
    case OP_if_false:
        return 2;
    case OP_catch:
        return 3;
    case OP_return:
    case OP_return_undef:
    case OP_throw:
    case OP_throw_error:
    case OP_tail_call:
    case OP_tail_call_method:
        return 4;
    case OP_eval:
    case OP_apply_eval:
    case OP_make_loc_ref:
    case OP_make_arg_ref:
    case OP_gosub:
    case OP_ret:
    case OP_initial_yield:
    case OP_yield:
    case OP_yield_star:
    case OP_async_yield_star:
    case OP_await:
    case OP_using_dispose:
    case OP_using_dispose_async:
    case OP_with_get_var:
    case OP_with_put_var:
    case OP_with_delete_var:
    case OP_with_make_ref:
    case OP_with_get_ref:
    case OP_with_get_ref_undef:
        return 5;
    default:
        return 0;
    }
}
static TDZ_WORKER_LOCAL_CODE int js_tdz_local(const uint8_t *pc, int *kill)
{
    unsigned op = *pc;
    *kill = 0;
    switch (op) {
    case OP_set_loc_uninitialized:
        *kill = 1;
        return get_u16(pc + 1);
    case OP_get_loc_check:
    case OP_put_loc_check:
    case OP_put_loc_check_init:
    case OP_put_loc:
    case OP_set_loc:
        return get_u16(pc + 1);
    case OP_inc_loc:
    case OP_dec_loc:
    case OP_add_loc:
        return pc[1];
    default:
        return -1;
    }
}
static TDZ_WORKER_LOCAL_CODE int js_tdz_leader(JSTdzPlan *p, uint32_t pc)
{
    unsigned i = 0;
    while (i < p->count && p->start[i] < pc)
        i++;
    if (i < p->count && p->start[i] == pc)
        return 1;
    if (p->count == TDZ_PLAN_BLOCKS + 1)
        return 0;
    memmove(p->start + i + 1, p->start + i, (p->count - i) * sizeof(*p->start));
    p->start[i] = pc;
    p->count++;
    return 1;
}
static TDZ_WORKER_LOCAL_CODE int js_tdz_block(const JSTdzPlan *p, uint32_t pc)
{
    unsigned lo = 0, hi = p->count - 1;
    while (lo < hi) {
        unsigned m = (lo + hi) / 2;
        if (p->start[m] < pc)
            lo = m + 1;
        else
            hi = m;
    }
    return lo < p->count - 1 && p->start[lo] == pc ? (int)lo : -1;
}
static int64_t js_tdz_target(const QJSCompilerCode *b, const uint8_t *code, uint32_t pc,
                             unsigned fmt)
{
    (void)fmt;
    uint32_t label = get_u32(code + pc + 1);
    if (label >= (uint32_t)b->label_count)
        return -1;
    return compiler_label_get(b, label);
}
static TDZ_WORKER_CODE void js_tdz_analyze(QJSCompilerCode *b, uint64_t mask)
{
    JSTdzPlan p;
    uint8_t *code = b->byte_code.buf;
    uint32_t len = b->byte_code.size;
    memset(&p, 0, sizeof(p));
    p.start[1] = len;
    p.count = 2;
    for (uint32_t pc = 0; pc < len;) {
        unsigned op = code[pc];
        if (op >= OP_TEMP_END)
            return;
        unsigned size = compiler_op_size(b, op), fmt = compiler_op_fmt(b, op);
        if (!size || size > len - pc)
            return;
        if (op >= OP_TEMP_START && op != OP_label && op != OP_source_loc)
            return;
        if (op == OP_label || op == OP_source_loc) {
            pc += size;
            continue;
        }
        int edge = js_tdz_edge(op);
        if (edge == 5)
            return;
        if (fmt == OP_FMT_label || fmt == OP_FMT_label8 || fmt == OP_FMT_label16) {
            if (edge < 1 || edge > 3)
                return;
            int64_t target = js_tdz_target(b, code, pc, fmt);
            if (target < 0 || target >= len || !js_tdz_leader(&p, (uint32_t)target) ||
                !js_tdz_leader(&p, pc + size))
                return;
        } else {
            if (fmt == OP_FMT_atom_label_u8 || fmt == OP_FMT_atom_label_u16 ||
                fmt == OP_FMT_label_u16)
                return;
            if (edge == 4 && !js_tdz_leader(&p, pc + size))
                return;
        }
        pc += size;
    }
    unsigned leader = 0;
    for (uint32_t pc = 0; pc < len; pc += compiler_op_size(b, code[pc])) {
        if (leader < p.count && p.start[leader] < pc)
            return;
        if (leader < p.count && p.start[leader] == pc)
            leader++;
    }
    if (leader != p.count - 1)
        return;
    unsigned blocks = p.count - 1;
    for (unsigned i = 0; i < blocks; i++) {
        uint32_t last = p.start[i], end = p.start[i + 1];
        p.successor[i][0] = p.successor[i][1] = UINT16_MAX;
        for (uint32_t pc = p.start[i]; pc < end;) {
            unsigned op = code[pc];
            int kill, idx;
            if (op == OP_label || op == OP_source_loc) {
                last = pc;
                pc += compiler_op_size(b, op);
                continue;
            }
            idx = js_tdz_local(code + pc, &kill);
            if (idx >= b->var_count)
                return;
            if (idx >= 0 && idx < 64 && (mask & (UINT64_C(1) << idx))) {
                uint64_t bit = UINT64_C(1) << idx;
                if (kill) {
                    p.kill[i] |= bit;
                    p.gen[i] &= ~bit;
                } else
                    p.gen[i] |= bit;
            }
            if (op == OP_catch) {
                int target =
                    js_tdz_block(&p, (uint32_t)js_tdz_target(b, code, pc, compiler_op_fmt(b, op)));
                if (target < 0)
                    return;
                p.root[target] = 1;
            }
            last = pc;
            pc += compiler_op_size(b, op);
        }
        unsigned op = code[last];
        int edge = js_tdz_edge(op), slot = 0;
        if (edge == 1 || edge == 2) {
            int target =
                js_tdz_block(&p, (uint32_t)js_tdz_target(b, code, last, compiler_op_fmt(b, op)));
            if (target < 0)
                return;
            p.successor[i][slot++] = (uint16_t)target;
        }
        if (edge != 1 && edge != 4 && end < len)
            p.successor[i][slot] = (uint16_t)(i + 1);
    }
    p.root[0] = 1;
    unsigned head = 0, tail = 0, pending = 0, steps = 0;
    for (unsigned i = 0; i < blocks; i++)
        if (p.root[i]) {
            p.reachable[i] = p.queued[i] = 1;
            p.input[i] = 0;
            p.queue[tail] = (uint16_t)i;
            tail = (tail + 1) % TDZ_PLAN_BLOCKS;
            pending++;
        }
    while (pending) {
        if (++steps > 65536)
            return; /* All writes occur after convergence. */
        unsigned i = p.queue[head];
        head = (head + 1) % TDZ_PLAN_BLOCKS;
        pending--;
        p.queued[i] = 0;
        uint64_t output = (p.input[i] & ~p.kill[i]) | p.gen[i];
        if (p.processed[i] && p.output[i] == output)
            continue;
        p.output[i] = output;
        p.processed[i] = 1;
        for (unsigned k = 0; k < 2; k++) {
            unsigned next = p.successor[i][k];
            if (next == UINT16_MAX)
                continue;
            uint64_t merged = p.reachable[next] ? p.input[next] & output : output;
            if (!p.reachable[next] || merged != p.input[next]) {
                p.input[next] = merged;
                p.reachable[next] = 1;
                if (!p.queued[next]) {
                    if (pending == TDZ_PLAN_BLOCKS)
                        return;
                    p.queue[tail] = (uint16_t)next;
                    tail = (tail + 1) % TDZ_PLAN_BLOCKS;
                    pending++;
                    p.queued[next] = 1;
                }
            }
        }
    }
    for (unsigned i = 0; i < blocks; i++)
        if (p.reachable[i]) {
            uint64_t state = p.input[i];
            for (uint32_t pc = p.start[i]; pc < p.start[i + 1];) {
                unsigned op = code[pc], size = compiler_op_size(b, op);
                int kill, idx;
                if (op == OP_label || op == OP_source_loc) {
                    pc += size;
                    continue;
                }
                idx = js_tdz_local(code + pc, &kill);
                if (idx >= 0 && idx < 64 && (mask & (UINT64_C(1) << idx))) {
                    uint64_t bit = UINT64_C(1) << idx;
                    if (state & bit) {
                        if (op == OP_get_loc_check)
                            code[pc] = OP_get_loc;
                        else if (op == OP_put_loc_check)
                            code[pc] = OP_put_loc;
                    }
                    if (kill)
                        state &= ~bit;
                    else
                        state |= bit;
                }
                pc += size;
            }
        }
}
static TDZ_WORKER_LOCAL_CODE int js_tdz_entry_local(const uint8_t *pc)
{
    unsigned op = *pc;
    switch (op) {
    case OP_get_loc:
    case OP_put_loc:
    case OP_set_loc:
    case OP_get_loc_check:
    case OP_put_loc_check:
    case OP_put_loc_check_init:
    case OP_set_loc_uninitialized:
    case OP_close_loc:
        return get_u16(pc + 1);
    case OP_inc_loc:
    case OP_dec_loc:
    case OP_add_loc:
        return pc[1];
#if SHORT_OPCODES
    case OP_get_loc8:
    case OP_put_loc8:
    case OP_set_loc8:
        return pc[1];
    default:
        if (op >= OP_get_loc0 && op <= OP_get_loc3)
            return op - OP_get_loc0;
        if (op >= OP_put_loc0 && op <= OP_put_loc3)
            return op - OP_put_loc0;
        if (op >= OP_set_loc0 && op <= OP_set_loc3)
            return op - OP_set_loc0;
        return -1;
#else
    default:
        return -1;
#endif
    }
}

static TDZ_WORKER_CODE void compiler_entry_init(QJSCompilerCode *b)
{
    uint64_t mask = b->lexical_mask;
    uint32_t len = b->byte_code.size, earliest_target = UINT32_MAX;
    uint8_t *code = b->byte_code.buf;
    uint32_t erased[64], erased_count = 0;
    if (!mask || !len || len > 65535 || getenv(tdz_disable_init))
        return;
    /* Validate the whole phase2 stream before changing any byte. Any surviving
     * check keeps its sentinel, including derived-this's inverse init check.
     * Labels store IDs here, not final jump displacements.
     */
    for (uint32_t pc = 0; pc < len;) {
        unsigned op = code[pc];
        if (op >= OP_TEMP_END)
            return;
        unsigned size = compiler_op_size(b, op), fmt = compiler_op_fmt(b, op);
        if (!size || size > len - pc)
            return;
        if (op == OP_label || op == OP_source_loc) {
            pc += size;
            continue;
        }
        if (op >= OP_TEMP_START)
            return;
        int edge = js_tdz_edge(op), idx = js_tdz_entry_local(code + pc);
        if (edge == 5 || idx >= b->var_count)
            return;
        if (op == OP_set_loc_uninitialized && size != 3)
            return;
        if (idx >= 0 && idx < 64 &&
            (op == OP_get_loc_check || op == OP_put_loc_check || op == OP_put_loc_check_init))
            mask &= ~(UINT64_C(1) << idx);
        if (fmt == OP_FMT_label || fmt == OP_FMT_label8 || fmt == OP_FMT_label16) {
            if (edge < 1 || edge > 3)
                return;
            uint32_t label = get_u32(code + pc + 1);
            if (label >= (uint32_t)b->label_count)
                return;
            int target = compiler_label_get(b, label);
            if (target < 0 || (uint32_t)target >= len)
                return;
            if ((uint32_t)target < earliest_target)
                earliest_target = target;
        } else if (fmt == OP_FMT_atom_label_u8 || fmt == OP_FMT_atom_label_u16 ||
                   fmt == OP_FMT_label_u16)
            return;
        pc += size;
    }
    if (!mask)
        return;
    uint64_t untouched = mask;
    for (uint32_t pc = 0; pc < len;) {
        unsigned op = code[pc], size = compiler_op_size(b, op);
        if (op == OP_label || op == OP_source_loc) {
            pc += size;
            continue;
        }
        int edge = js_tdz_edge(op), idx = js_tdz_entry_local(code + pc);
        if (edge >= 1 && edge <= 4)
            break;
        uint64_t access = idx >= 0 && idx < 64 ? UINT64_C(1) << idx : 0;
#if SHORT_OPCODES
        if (op == OP_get_loc0_loc1)
            access |= 3;
#endif
        if (op == OP_set_loc_uninitialized && (untouched & access) && pc < earliest_target) {
            /* First local access, no incoming edge to/before this position:
             * the frame's original undefined still owns this nonref cell.
             * Collect erased positions, then compact and map labels; the
             * inherited resolver owns final jump/source-map/peephole changes.
             */
            if (erased_count == 64)
                return;
            erased[erased_count++] = pc;
        }
        untouched &= ~access;
        pc += size;
    }
    compiler_compact_entry(b, erased, erased_count);
}

static TDZ_WORKER_CODE void compiler_tdz_plan(QJSCompilerCode *b)
{
    if (!b->lexical_mask || !b->byte_code.size || b->byte_code.size > 196608 ||
        getenv(tdz_disable_plan))
        return;
    const uint8_t *code = b->byte_code.buf;
    unsigned len = b->byte_code.size;
    for (unsigned pc = 0; pc < len;) {
        unsigned op = code[pc];
        if (op >= OP_TEMP_END)
            return;
        unsigned size = compiler_op_size(b, op);
        if (!size || size > len - pc)
            return;
        if (op == OP_get_loc_check || op == OP_put_loc_check) {
            js_tdz_analyze(b, b->lexical_mask);
            return;
        }
        pc += size;
    }
}
_Static_assert(sizeof(JSTdzPlan) + 2048 <= QJS_COMPILER_PLAN_STACK_RESERVE,
               "compiler caller stack reserve");
TDZ_WORKER_CODE void JS_CompilerBytecodePlan(QJSCompilerCode *b)
{
    if (!b || b->opcode_count != OP_TEMP_END || !b->opcode_sizes || !b->opcode_formats)
        return;
    compiler_tdz_plan(b);
    compiler_entry_init(b);
}
#if defined(_MSC_VER)
#pragma code_seg(pop)
#endif
