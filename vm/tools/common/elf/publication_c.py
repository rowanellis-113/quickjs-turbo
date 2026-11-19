"""Shared publication label utilities."""

import re


def labels(rows):
    return {m[1] for row in rows if (m := re.fullmatch(r"(\w+):", row))}


def once(rows, before, after):
    text = "\n".join(rows)
    if text.count(before) != 1:
        raise ValueError("Review Linux publication anchor: " + before[:120])
    return text.replace(before, after).splitlines()
