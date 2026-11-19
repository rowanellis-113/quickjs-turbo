"""Separate GNU forwarding worker, using exact actual core types and helpers."""

import hashlib, json
from admission_c import function
from compiler_projection_c import actual_type_prefix


def generate(
    source,
    output,
    actual_input,
    layout,
    *,
    compat_header="src/common/linux/interpreter-linux-compat.inc",
):
    # Extract from the same actual backported input that the core/layout use.
    # No object layout, cloned struct, guessed compiler clone or public ABI change.
    signatures = (
        "static inline uintptr_t js_get_stack_pointer(void)",
        "static inline bool js_check_stack_overflow(JSRuntime *rt, size_t alloca_size)",
        "static JSValue js_dup(JSValueConst v)",
        "static inline uint32_t *prop_hash_end(JSShape *sh)",
        "static inline JSShapeProperty *find_own_property(JSProperty **ppr,",
    )
    helpers = [function(actual_input, s) for s in signatures]
    helpers[2] = helpers[2].replace(
        "static JSValue", "static inline __attribute__((always_inline)) JSValue", 1
    )
    owner = (source / "src/common/kernel/ordinary-arguments.c").read_text()
    records = owner[
        owner.index("typedef enum {") : owner.index('__attribute__((section(".qjzzpm"),')
    ]
    push = function(owner, "static FRAME_CODE bool js_frame_arguments_push(")
    declaration = push[: push.index("\n{")].replace("static FRAME_CODE bool", "extern bool", 1)
    declaration = (
        declaration.replace("js_frame_arguments_push", "JS_LinuxVirtualArgumentsPush", 1) + ";"
    )
    prefix = actual_type_prefix(actual_input)
    header = output / "quickjs-linux-virtual-arguments-private.h"
    header.write_text(
        """/* Actual source-derived private types/helpers. Keep original notices. */
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wunused-function"
#pragma GCC diagnostic ignored "-Wunused-const-variable"
"""
        + prefix
        + "\n"
        + "\n".join(helpers)
        + """
extern void close_var_ref(JSRuntime *,JSVarRef *); /* unused shared inline declaration */
"""
        + f'#include "{compat_header}"\n#include "src/common/call/interpreter-retained-context.inc"\n'
        + records
        + """
extern _Atomic(unsigned) JS_FrameArgumentsMode;
extern JSCFunctionMagic qjs_linux_core_js_function_apply;
"""
        + declaration
        + """

#define js_function_apply qjs_linux_core_js_function_apply
#define js_frame_arguments_push JS_LinuxVirtualArgumentsPush
/* Constructor admission initializes the inherited mode. A zero value declines. */
static FRAME_INLINE unsigned arguments_mode(void)
{
    return atomic_load_explicit(&JS_FrameArgumentsMode,memory_order_relaxed);
}
#undef FRAME_CODE
#define FRAME_CODE __attribute__((section("qjs_virtual_text"),noipa))
#pragma GCC diagnostic pop
"""
    )
    worker = output / "quickjs-linux-virtual-arguments.c"
    worker.write_text("""#include "quickjs-linux-virtual-arguments-private.h"
#include "src/common/linux/interpreter-virtual-arguments.inc"
__attribute__((visibility("hidden"))) FRAME_CODE
int JS_LinuxVirtualArgumentsStep(JSFrameRegisterState *state)
{
    return js_linux_virtual_arguments_step(state);
}
""")
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    record = dict(
        status="generated-not-qualified",
        source_files={
            n: sha(source / n)
            for n in [
                "tools/common/elf/virtual_arguments_c.py",
                "tools/common/elf/compiler_projection_c.py",
                "src/common/linux/interpreter-virtual-arguments.inc",
                compat_header,
                "src/common/call/interpreter-retained-context.inc",
                "src/common/kernel/ordinary-arguments.c",
            ]
        },
        actual_input_sha256=hashlib.sha256(actual_input.encode()).hexdigest(),
        helper_source_sha256={
            s: hashlib.sha256(t.encode()).hexdigest() for s, t in zip(signatures, helpers)
        },
        private_sha256=sha(header),
        worker_sha256=sha(worker),
        entry="JS_LinuxVirtualArgumentsStep",
        push="source-typed noipa alias of original js_frame_arguments_push",
        mode="inherited atomic load only; zero declines",
        text_section="qjs_virtual_text",
        frame_growth=0,
        state_growth=0,
        new_roots=0,
    )
    (output / "VIRTUAL-ARGUMENTS.json").write_text(json.dumps(record, indent=2) + "\n")
