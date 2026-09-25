"""DNA fit parser.

DNA is the in-game clipboard format:

    <ShipID>:<TypeID>;<Count>:<TypeID>;<Count>:...::

Modules appear once per fitted slot (`Count` = 1 per slot instance is
common but sometimes packed as `Count` for stacked identical modules).
Drones and charges appear as regular entries — we classify them via
category and slot effect just like the EFT parser.

The chat-clickable form is:

    <url=fitting:638:2048;1:519;5:3436;1::>My Raven Fit</url>

We also accept `fitting:638:...` on its own.
"""
from __future__ import annotations

import re
from typing import Optional

from ..sde import loader
from .base import Fit, FitItem, ParseError
from .eft import DRONE_CATEGORY_ID

_URL = re.compile(r"<url=fitting:([^>]+)>([^<]*)</url>", re.IGNORECASE)
_PREFIX = re.compile(r"^\s*(?:fitting:)?", re.IGNORECASE)


def _extract_dna(text: str) -> tuple[str, str]:
    """Return (dna_body, fit_name_if_present)."""
    m = _URL.search(text)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return _PREFIX.sub("", text.strip()), ""


def parse_dna(text: str, default_name: Optional[str] = None) -> Fit:
    body, url_name = _extract_dna(text)
    if not body:
        raise ParseError("Empty DNA input")

    # Trim trailing `::` and any whitespace
    body = body.rstrip(":").rstrip()
    parts = [p for p in body.split(":") if p.strip()]
    if not parts:
        raise ParseError("Malformed DNA — no ship id")

    try:
        ship_id = int(parts[0])
    except ValueError:
        raise ParseError(f"Malformed DNA ship id: {parts[0]!r}")

    ship = loader.get_type(ship_id)
    if ship is None:
        raise ParseError(f"Unknown ship type id: {ship_id}")

    name = url_name or default_name or f"{ship.name} fit"
    fit = Fit(name=name, ship_type_id=ship.type_id, ship_type_name=ship.name)

    for entry in parts[1:]:
        if ";" not in entry:
            # Ignore malformed segments rather than aborting the whole paste.
            continue
        tid_s, qty_s = entry.split(";", 1)
        try:
            tid = int(tid_s)
            qty = int(qty_s) if qty_s else 1
        except ValueError:
            continue
        if qty < 1:
            continue

        info = loader.get_type(tid)
        if info is None:
            continue

        slot = loader.slot_of_module(tid)
        is_drone = info.category_id == DRONE_CATEGORY_ID

        # A fitted-module entry has Count == 1. Anything higher is either
        # stacked charges, drones, or cargo — send it to the right bay.
        if slot in ("high", "med", "low", "rig", "subsystem") and qty == 1:
            item = FitItem(type_id=tid, name=info.name, quantity=1)
            getattr(fit, slot).append(item)
        else:
            item = FitItem(type_id=tid, name=info.name, quantity=qty)
            if is_drone:
                fit.drones.append(item)
            else:
                fit.cargo.append(item)

    return fit
