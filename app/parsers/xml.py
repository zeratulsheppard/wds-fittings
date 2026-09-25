"""pyfa / EFT XML multi-fit parser.

Supports the pyfa-style export:

    <?xml version="1.0" ?>
    <fittings>
      <fitting name="My Raven">
        <description value=""/>
        <shipType value="Raven"/>
        <hardware slot="low slot 0" type="Damage Control II"/>
        <hardware qty="5" slot="drone bay" type="Warrior II"/>
        <hardware qty="2000" slot="cargo" type="Scourge Fury Cruise Missile"/>
      </fitting>
    </fittings>

Returns a list — an XML file can contain many fittings.
"""
from __future__ import annotations

from typing import List, Union
from xml.etree import ElementTree as ET

from ..sde import loader
from .base import Fit, FitItem, ParseError

_SLOT_ROUTE = {
    "hi slot":    "high",
    "high slot":  "high",
    "med slot":   "med",
    "low slot":   "low",
    "rig slot":   "rig",
    "subsystem slot": "subsystem",
    "drone bay":  "drones",
    "cargo":      "cargo",
}


def _route(slot_label: str) -> str:
    s = (slot_label or "").strip().lower()
    for prefix, target in _SLOT_ROUTE.items():
        if s.startswith(prefix):
            return target
    return "cargo"


def parse_pyfa_xml(data: Union[str, bytes]) -> List[Fit]:
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise ParseError(f"Invalid XML: {exc}") from exc

    if root.tag != "fittings":
        raise ParseError(f"Expected <fittings> root, got <{root.tag}>")

    fits: List[Fit] = []
    for f_el in root.findall("fitting"):
        name = f_el.get("name") or "Unnamed fit"
        ship_name = ""
        desc = ""
        for child in f_el:
            if child.tag == "shipType":
                ship_name = child.get("value", "").strip()
            elif child.tag == "description":
                desc = child.get("value", "").strip()

        if not ship_name:
            raise ParseError(f"Fitting {name!r} missing <shipType>")

        ship = loader.find_type_by_name(ship_name)
        if ship is None:
            raise ParseError(f"Unknown ship type in fit {name!r}: {ship_name!r}")

        fit = Fit(
            name=name,
            ship_type_id=ship.type_id,
            ship_type_name=ship.name,
            description=desc,
        )

        for hw in f_el.findall("hardware"):
            type_name = (hw.get("type") or "").strip()
            if not type_name:
                continue
            info = loader.find_type_by_name(type_name)
            if info is None:
                raise ParseError(
                    f"Unknown item in fit {name!r}: {type_name!r}"
                )
            try:
                qty = int(hw.get("qty", "1"))
            except ValueError:
                qty = 1
            target = _route(hw.get("slot", ""))
            item = FitItem(type_id=info.type_id, name=info.name, quantity=qty)
            getattr(fit, target).append(item)

        fits.append(fit)

    if not fits:
        raise ParseError("No <fitting> elements found")
    return fits
