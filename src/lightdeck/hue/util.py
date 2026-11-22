from __future__ import annotations

import copy
from typing import Any

# Setting a color and a color temperature are mutually exclusive on the
# bridge; whichever was requested last wins.
_EXCLUSIVE = {"color": "color_temperature", "color_temperature": "color"}


def deep_merge(base: dict[str, Any], update: dict[str, Any]) -> dict[str, Any]:
    """Returns a new dict with ``update`` merged recursively into ``base``."""
    result = copy.deepcopy(base)
    for key, value in update.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def merge_command(pending: dict[str, Any], update: dict[str, Any]) -> dict[str, Any]:
    merged = deep_merge(pending, update)
    for key, other in _EXCLUSIVE.items():
        if key in update:
            merged.pop(other, None)
    return merged
