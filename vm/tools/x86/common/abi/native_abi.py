"""Bind supplemental assembly emitters to the measured source ABI of the VM."""

from contextvars import ContextVar
from functools import wraps
from inspect import signature

from abi_layout import load, validate_measured_override

_layout = ContextVar("frame_emission_layout", default=None)


def current():
    value = _layout.get()
    if value is None:
        raise RuntimeError("Native supplement emission requires a source-bound ABI scope")
    return value


def source_abi(function):
    """A nested generation restores the caller's contract, including on failure."""
    source_parameter = next(iter(signature(function).parameters))

    @wraps(function)
    def generate(*args, **kwargs):
        root = args[0] if args else kwargs[source_parameter]
        override = kwargs.get("layout_override")
        parent = _layout.get()
        if (
            override is None
            and parent is not None
            and parent.get("platform") == "linux-x86_64-sysv"
        ):
            override = parent
        selected = (
            validate_measured_override(root, override) if override is not None else load(root)
        )
        token = _layout.set(selected)
        try:
            return function(*args, **kwargs)
        finally:
            _layout.reset(token)

    return generate
