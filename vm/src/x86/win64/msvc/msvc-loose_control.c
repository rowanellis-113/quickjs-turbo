
#include <stdlib.h>
#include <stdint.h>
#include <stdatomic.h>
#pragma section(".qzzem$looseeq", read, write)
__declspec(allocate(".qzzem$looseeq")) _Atomic(unsigned) JS_FrameLooseEqMode = 0;
_Static_assert(sizeof(JS_FrameLooseEqMode) == 4, "native mode word");
__declspec(noinline) __declspec(code_seg(".qzzec$looseeq"))
#include "src/common/value/loose_control.inc"
