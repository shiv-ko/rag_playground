"""Approval level rule for contract amount and project attributes."""
from __future__ import annotations

_LEVELS = ("主任承認", "APR-M1", "APR-M2", "APR-M3")


def determine_apr_level(
    amount_incl_tax: int,
    is_medical: bool,
    is_time_and_materials: bool,
) -> str:
    if amount_incl_tax < 3_000_000:
        index = 0
    elif amount_incl_tax < 5_000_000:
        index = 1
    elif amount_incl_tax < 7_000_000:
        index = 2
    else:
        index = 3
    if is_medical:
        index = min(index + 1, len(_LEVELS) - 1)
    if is_time_and_materials:
        index = max(index, _LEVELS.index("APR-M2"))
    return _LEVELS[index]


def is_medical_project(project_name: str, aliases: list[str] | None = None) -> bool:
    text = project_name + " " + " ".join(aliases or [])
    return any(keyword in text for keyword in ("医療", "病院", "クリニック", "センター"))
