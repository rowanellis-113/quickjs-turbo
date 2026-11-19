"""ARM64 RegExp workers adapter."""

from c_workers import replace_one
from regexp_workers import generate as shared_generate


def _adapt(source, text):
    include = '#include "src/common/linux/interpreter-regexp.inc"'
    prefix = (source / "src/common/linux/interpreter-regexp.inc").read_text()
    prefix = prefix.replace("public SysV ABI", "typed AAPCS64 C ABI").replace(
        "Actual SysV value/core types", "Actual AAPCS64 value/core types"
    )
    text = replace_one(text, include, prefix, "source-owned typed ARM RegExp prefix")
    text += """
#ifdef QJS_AARCH64_VM_INSTRUMENT
/* Read actual intrinsic C-function identities and the already-selected mode.
 * This observer never initializes controls or changes admission. */
__attribute__((visibility("hidden"),noipa))
unsigned qjs_aarch64_regexp_worker_kind(JSValueConst function,unsigned *mode)
{
    JSObject *p;
    *mode=atomic_load_explicit(&js_linux_regexp_control,memory_order_relaxed);
    if(JS_VALUE_GET_TAG(function)!=JS_TAG_OBJECT)return 0;
    p=JS_VALUE_GET_OBJ(function);
    if(p->class_id!=JS_CLASS_C_FUNCTION)return 0;
    if(p->u.cfunc.cproto==JS_CFUNC_getter)
        return p->u.cfunc.c_function.getter==JS_RegExpOwnedFlags ? 16 : 0;
    if(p->u.cfunc.cproto!=JS_CFUNC_generic)return 0;
    JSCFunction *fn=p->u.cfunc.c_function.generic;
    if(fn==JS_LinuxRegExpReplaceDispatch)return 1;
    if(fn==JS_RegExpOwnedMatch)return 2;
    if(fn==JS_RegExpOwnedMatchAll)return 4;
    if(fn==JS_LinuxRegExpSplitDispatch)return 8;
    if(fn==js_regexp_exec)return 32;
    if(fn==js_regexp_test)return 64;
    return 0;
}
#endif
"""
    return text, {
        "callback": "Actual JS_CallInternal(ctx,rep,undefined,undefined,argc,owned_argv,COPY_ARGV);existing coherent builtin C/AAPCS64 boundary",
        "architecture": "aarch64;actual compiler C over original core types",
    }


def generate(source, output, core, layout):
    return shared_generate(
        source,
        output,
        core,
        layout,
        contract_rel="src/arm64/linux/abi/regexp.json",
        platform_binding="src/common/linux/interpreter-regexp.inc",
        abi_label="AAPCS64",
        arch_adapt=_adapt,
    )
