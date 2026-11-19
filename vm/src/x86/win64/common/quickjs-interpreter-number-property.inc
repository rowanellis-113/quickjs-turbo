/* Number primitive own-data lookup. No allocation, cache or boxed this.
 * JSContext/class_proto is read live in the calling bytecode's realm.
 * Native register protocol is Win64 MinGW only. MIT. */
_Static_assert(sizeof(JSValue) == QJS_ABI_SIZE_JSValue &&
                   sizeof(JSProperty) == QJS_ABI_SIZE_JSProperty &&
                   offsetof(JSContext, class_proto) == QJS_ABI_OFF_JSContext_class_proto &&
                   JS_CLASS_NUMBER == 4 && JS_TAG_INT == 0 && JS_TAG_FLOAT64 == 8 &&
                   offsetof(JSObject, class_id) == QJS_ABI_OFF_JSObject_class_id,
               "number primitive property ABI");
volatile unsigned char JS_FrameNumberPropertyControl
    __attribute__((section(".data$zzzzzzzzzznumberproperty"))) = 0;
NUMBER_PROPERTY_CODE void JS_FrameNumberPropertyConfigure(void)
{
    unsigned char expected = 0;
    unsigned char desired = getenv("QJS_DISABLE_NUMBER_PROPERTY_FAST") ? 2 : 1;
    __atomic_compare_exchange_n(&JS_FrameNumberPropertyControl, &expected, desired, 0,
                                __ATOMIC_RELEASE, __ATOMIC_RELAXED);
}
