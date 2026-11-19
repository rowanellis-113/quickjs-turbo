"""Shared publication control symbols and proxy naming."""

CONTROL = "JS_FramePublishControl"
SELECT = "JS_FramePublishSelect"
TABLE = "JS_FramePublishTable"
DIRTY = "JS_FramePublishDirtyTable"
BOUNDARIES = (
    "JS_FrameNativeCallLinkDispatch",
    "JS_FrameInterpSlow",
    "JS_FrameInterpClose",
    "JS_FrameInterpFree",
    "JS_FrameInterpAddDirect",
    "JS_FrameInterpOp_sub",
    "JS_FrameInterpBig_mul",
    "JS_FrameInterpOp_div",
    "JS_FrameInterpOp_mod",
    "JS_FrameInterpOp_lt",
    "JS_FrameInterpOp_lte",
    "JS_FrameInterpOp_gt",
    "JS_FrameInterpOp_gte",
    "JS_FrameInterpOp_eq",
    "JS_FrameInterpOp_neq",
    "JS_FrameInterpOp_strict_eq",
    "JS_FrameInterpOp_strict_neq",
    "JS_FrameInterpProperty_get_field",
    "JS_FrameInterpProperty_put_field",
    "JS_FrameInterpProperty_drop",
    "JS_FrameInterpProperty_call_constructor",
    "JS_FrameNewNullObject",
    "JS_FrameAddLocalBig",
    "JS_FreeValue",
    "JS_FrameInterpProperty_get_field2",
    "JS_FrameAddLocalString",
    "JS_FrameProtoPersistentFill",
)


def proxy(target):
    return "JS_FramePublishBefore_" + target.removeprefix("JS_")
