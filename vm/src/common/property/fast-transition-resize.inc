/* Property IC transition resize helper compatible with inline property storage. */
extern JSProperty *qjs_inline_property_realloc_rt(JSRuntime *rt, JSObject *p, size_t bytes);

__attribute__((visibility("hidden"), noipa)) JSPropertyICWay *
JS_FastTransitionResize(JSRuntime *rt, JSObject *obj, JSPropertyICWay *way)
{
    JSProperty *props = qjs_inline_property_realloc_rt(
        rt, obj, (size_t)way->transition->prop_size * sizeof(JSProperty));
    if (!props)
        return NULL;
    obj->prop = props;
    return way;
}
