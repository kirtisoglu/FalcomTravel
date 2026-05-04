"""Unified travel-mode enum.

Each backend translates these into its own native vocabulary
(see :class:`Backend.supports` and the per-backend ``_MODE_MAP`` tables).
"""

from __future__ import annotations

from enum import Enum


class Mode(str, Enum):
    """Cross-backend travel modes.

    The string values are stable; backends translate them to their own
    native names (e.g. ``DRIVE`` -> r5r ``"CAR"``, OSRM ``"driving"``,
    OSMnx ``"drive"`` network type).
    """

    DRIVE = "drive"
    WALK = "walk"
    BIKE = "bike"
    TRANSIT = "transit"
    DRIVE_TRANSIT = "drive_transit"

    @classmethod
    def parse(cls, value: "str | Mode") -> "Mode":
        if isinstance(value, cls):
            return value
        try:
            return cls(value.lower())
        except ValueError as e:
            valid = ", ".join(m.value for m in cls)
            raise ValueError(f"unknown mode {value!r}; valid: {valid}") from e
