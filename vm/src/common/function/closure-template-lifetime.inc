/* Context-owned ordinary shape edges, like array_shape. No cached values. */
static void js_closure_templates_set_class_proto(JSContext *ctx, JSClassID class_id, JSValue obj)
{
    JSShape *old[2] = {NULL, NULL};
    int base = class_id == JS_CLASS_BYTECODE_FUNCTION ? 0
               : class_id == JS_CLASS_ASYNC_FUNCTION  ? 2
                                                      : -1;
    if (base >= 0) {
        old[0] = ctx->closure_template_shapes[base];
        old[1] = ctx->closure_template_shapes[base + 1];
        ctx->closure_template_shapes[base] = NULL;
        ctx->closure_template_shapes[base + 1] = NULL;
    }
    /* set_value publishes the replacement before releasing the old value.
       Detached local shape owners protect old prototypes across reentry. */
    set_value(ctx, &ctx->class_proto[class_id], obj);
    js_free_shape_null(ctx->rt, old[0]);
    js_free_shape_null(ctx->rt, old[1]);
}

static void js_closure_templates_cleanup(JSContext *ctx)
{
    JSShape *old[4];
    JSShape *internal = ctx->internal_function_shape;
    int i;
    ctx->closure_template_mode = 2;
    ctx->internal_function_mode = 2;
    ctx->internal_function_shape = NULL;
    for (i = 0; i < 4; i++) {
        old[i] = ctx->closure_template_shapes[i];
        ctx->closure_template_shapes[i] = NULL;
    }
    for (i = 0; i < 4; i++)
        js_free_shape_null(ctx->rt, old[i]);
    js_free_shape_null(ctx->rt, internal);
}
