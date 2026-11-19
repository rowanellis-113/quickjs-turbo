/* Platform-neutral lifecycle body; private declarations come from this build. */
#include "quickjs-property-ic-lifetime-private.h"

static JSPropertyICWay *js_ic_way(JSPropertyICSite *site, unsigned index)
{
    return index ? &site->secondary[index - 1] : &site->primary;
}

#include "src/common/property/property-ic-lifetime.inc"
