
#include <stdlib.h>
#include <stdint.h>
#include <stdatomic.h>
__attribute__((section(".qzzem$looseeq"), aligned(4))) _Atomic(unsigned) JS_FrameLooseEqMode = 0;
_Static_assert(sizeof(JS_FrameLooseEqMode) == 4, "native mode word");
__attribute__((noinline, section(".qzzec$looseeq")))
#include "src/common/value/loose_control.inc"
