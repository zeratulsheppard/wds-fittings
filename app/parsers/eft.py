"""EFT format parser.

Example input:

    [Raven, My Fit Name]
    Damage Control II
    Power Diagnostic System II

    Large Shield Extender II
    Adaptive Invulnerability Field II

    Cruise Missile Launcher II, Scourge Fury Cruise Missile
    Cruise Missile Launcher II, Scourge Fury Cruise Missile

    Large Core Defense Field Extender I

    Warrior II x5

    Scourge Fury Cruise Missile x2000

Sections are separated by blank lines and appear in the order:
low, med, high, rig, [subsystem for T3], drones, cargo.

We route each module to a slot type using the SDE effect lookup rather
than trusting section order — this survives pyfa reorderings and empty
sections. Items with an `xN` quantity go to drones (Drone category) or
cargo (everything else).

Empty slot markers like `[Empty Low slot]` are ignored.
"""
from __future__ import annotations

import re
from typing import Iterable, List, Optional

from ..sde import loader
from .base import Fit, FitItem, ParseError

DRONE_CATEGORY_ID = 18

_HEADER = re.compile(r"^\s*\[([^,\]]+)\s*,\s*(.+?)\s*\]\s*$")
_EMPTY_SLOT = re.compile(r"^\s*\[empty\b", re.IGNORECASE)
_QTY_TAIL = re.compile(r"\s+x(\d+)\s*$", re.IGNORECASE)


def _iter_lines(text: str) -> Iterable[str]:
    for raw in text.splitlines():
        yield raw.rstrip("\r\n")


def parse_eft(text: str) -> Fit:
    lines = list(_iter_lines(text))
    if not lines:
        raise ParseError("Empty input")

    # Find header
    header_idx = -1
    for i, line in enumerate(lines):
        if line.strip():
            m = _HEADER.match(line)
            if not m:
                raise ParseError(
                    f"Expected '[Ship, Name]' as first non-blank line, got: {line!r}"
                )
            ship_name = m.group(1).strip()
            fit_name = m.group(2).strip()
            header_idx = i
            break
    if header_idx < 0:
        raise ParseError("No header found")

    ship = loader.find_type_by_name(ship_name)
    if ship is None:
        raise ParseError(f"Unknown ship type: {ship_name!r}")

    fit = Fit(name=fit_name, ship_type_id=ship.type_id, ship_type_name=ship.name)

    for raw in lines[header_idx + 1 :]:
        line = raw.strip()
        if not line or _EMPTY_SLOT.match(line):
            continue

        qty = 1
        qm = _QTY_TAIL.search(line)
        if qm:
            qty = int(qm.group(1))
            line = _QTY_TAIL.sub("", line).strip()

        # Split module,charge
        charge_id: Optional[int] = None
        charge_name: Optional[str] = None
        if "," in line:
            mod_name, charge_str = [s.strip() for s in line.split(",", 1)]
            if charge_str:
                charge = loader.find_type_by_name(charge_str)
                if charge:
                    charge_id = charge.type_id
                    charge_name = charge.name
        else:
            mod_name = line

        item_type = loader.find_type_by_name(mod_name)
        if item_type is None:
            raise ParseError(f"Unknown item: {mod_name!r}")

        item = FitItem(
            type_id=item_type.type_id,
            name=item_type.name,
            quantity=qty,
            charge_type_id=charge_id,
            charge_name=charge_name,
        )

        # Route by category/slot
        if qty > 1 or item_type.category_id == DRONE_CATEGORY_ID:
            if item_type.category_id == DRONE_CATEGORY_ID:
                fit.drones.append(item)
            else:
                fit.cargo.append(item)
            continue

        slot = loader.slot_of_module(item_type.type_id)
        if slot == "high":
            fit.high.append(item)
        elif slot == "med":
            fit.med.append(item)
        elif slot == "low":
            fit.low.append(item)
        elif slot == "rig":
            fit.rig.append(item)
        elif slot == "subsystem":
            fit.subsystem.append(item)
        else:
            # No slot effect — probably ammo or an implant listed in the fit body.
            fit.cargo.append(item)

    return fit
