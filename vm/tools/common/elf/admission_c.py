"""Source-owned native admission supplements helper (`one` and `function`)."""

from pathlib import Path
from c_workers import module

_source_match = module(Path(__file__).resolve().parents[3], "c_source_match")


def one(text, old, new):
    return _source_match.replace_one(text, old, new)


def function(text, signature):
    return _source_match.extract_function(text, signature)
