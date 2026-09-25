"""Render a stored Fit dict back to EFT text.

Section order matches pyfa / in-game paste convention:
    [Ship, Name]
    Low slots
    Med slots
    High slots (with charge after ',')
    Rigs
    Subsystems (T3 only)
    Drones (Name xN)
    Cargo (Name xN)
"""
from __future__ import annotations

from typing import List


def _module_line(item: dict) -> str:
    name = item.get("name", "")
    charge = item.get("charge_name")
    return f"{name}, {charge}" if charge else name


def _qty_line(item: dict) -> str:
    return f"{item.get('name','')} x{int(item.get('quantity', 1))}"


def to_eft(fit: dict, ship_type_name: str) -> str:
    ship = ship_type_name or fit.get("ship_type_name", "")
    name = fit.get("name", "Fit")
    lines: List[str] = [f"[{ship}, {name}]"]

    for section in ("low", "med", "high", "rig", "subsystem"):
        items = fit.get(section) or []
        if not items:
            continue
        lines.append("")
        for m in items:
            lines.append(_module_line(m))

    drones = fit.get("drones") or []
    if drones:
        lines.append("")
        lines.append("")
        for m in drones:
            lines.append(_qty_line(m))

    cargo = fit.get("cargo") or []
    if cargo:
        lines.append("")
        lines.append("")
        for m in cargo:
            lines.append(_qty_line(m))

    return "\n".join(lines) + "\n"
