/* Actual shared activation type, independent of OS TLS addressing. MIT. */
#ifndef QJS_FRAME_SHARED_TYPES
#define QJS_FRAME_SHARED_TYPES
typedef struct JSFrameSharedAnchor {
    struct JSFrameSharedAnchor *prev;
    JSFrameRegisterState *state;
    unsigned kind; /* 0: coherent host; 1: C child; 2: native child; 3: blocked VM activation */
} JSFrameSharedAnchor;
_Static_assert(sizeof(JSFrameSharedAnchor) == 24 && offsetof(JSFrameSharedAnchor, state) == 8 &&
                   offsetof(JSFrameSharedAnchor, kind) == 16,
               "activation home32 retains original shared anchor24 prefix");
#endif
