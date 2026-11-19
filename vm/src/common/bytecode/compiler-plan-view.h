/* Private, borrowed compiler inputs. No public JS/runtime/bytecode layout. */
#ifndef QJS_COMPILER_PLAN_VIEW_H
#define QJS_COMPILER_PLAN_VIEW_H
#include <stddef.h>
#include <stdint.h>
#define QJS_COMPILER_PLAN_STACK_RESERVE (20 * 1024)
typedef struct QJSCompilerCode {
    struct {
        uint8_t *buf;
        uint32_t size;
    } byte_code;
    int var_count, label_count;
    uint64_t lexical_mask;
    void *label_slots;
    size_t label_stride, label_pos2_offset;
    const uint8_t *opcode_sizes, *opcode_formats;
    unsigned opcode_count;
} QJSCompilerCode;
void JS_CompilerBytecodePlan(QJSCompilerCode *view);
#endif
