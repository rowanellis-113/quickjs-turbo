/* Shared source-owned captured-argument classifier,MIT. */
static FRAME_CODE void JS_LinuxCapturedReadonlyClassify(JSFunctionBytecode *b)
{
    if ((FRAME_KIND(b) & 7) == 5 && !getenv("QJS_DISABLE_FRAME_CAPTURED_READONLY") &&
        !js_check_stack_overflow(b->realm->rt, 1024) &&
        js_frame_captured_readonly(b, js_frame_opcode_sizes))
        FRAME_KIND(b) |= 2;
}
