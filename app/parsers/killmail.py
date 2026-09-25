"""Killmail → Fit parser.

Accepts ESI killmail JSON (dict or string), zKillboard's wrapper form
({"killmail": {...}, "zkb": {...}}), and a killmail_id/hash pair that
we fetch on demand.

EVE inventory flag ranges (from `esi_flags`):
    low slots      11 .. 18
    med slots      19 .. 26
    high slots     27 .. 34
    rig slots      92 .. 98
    subsystems    125 .. 132
    drone bay      87
    cargo           5
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Union

import httpx

from ..sde import loader
from .base import Fit, FitItem, ParseError

_FLAG_TO_GROUP = {}
for flag in range(11, 19):
    _FLAG_TO_GROUP[flag] = "low"
for flag in range(19, 27):
    _FLAG_TO_GROUP[flag] = "med"
for flag in range(27, 35):
    _FLAG_TO_GROUP[flag] = "high"
for flag in range(92, 99):
    _FLAG_TO_GROUP[flag] = "rig"
for flag in range(125, 133):
    _FLAG_TO_GROUP[flag] = "subsystem"
_FLAG_TO_GROUP[87] = "drones"
_FLAG_TO_GROUP[5] = "cargo"

ESI_KILLMAIL = "https://esi.evetech.net/latest/killmails/{kid}/{khash}/"


def _as_dict(payload: Union[str, bytes, Dict[str, Any]]) -> Dict[str, Any]:
    if isinstance(payload, (str, bytes)):
        try:
            return json.loads(payload)
        except json.JSONDecodeError as exc:
            raise ParseError(f"Invalid JSON: {exc}") from exc
    return payload


def fetch_killmail(killmail_id: int, killmail_hash: str) -> Dict[str, Any]:
    r = httpx.get(ESI_KILLMAIL.format(kid=killmail_id, khash=killmail_hash), timeout=15)
    if r.status_code != 200:
        raise ParseError(f"ESI killmail fetch failed: {r.status_code}")
    return r.json()


def parse_killmail(payload: Union[str, bytes, Dict[str, Any]]) -> Fit:
    data = _as_dict(payload)
    # zKB wrapper unwrap
    if "killmail" in data and isinstance(data["killmail"], dict):
        data = data["killmail"]

    victim = data.get("victim") or {}
    ship_id = victim.get("ship_type_id")
    if not ship_id:
        raise ParseError("Killmail missing victim.ship_type_id")
    ship = loader.get_type(int(ship_id))
    if ship is None:
        raise ParseError(f"Unknown ship type id: {ship_id}")

    kid = data.get("killmail_id") or "?"
    fit = Fit(
        name=f"{ship.name} loss #{kid}",
        ship_type_id=ship.type_id,
        ship_type_name=ship.name,
    )

    # Sum destroyed + dropped, grouped by (type_id, slot_flag).
    from collections import defaultdict
    counts: Dict[tuple[int, int], int] = defaultdict(int)
    for it in victim.get("items", []) or []:
        try:
            tid = int(it["item_type_id"])
            flag = int(it["flag"])
        except (KeyError, ValueError, TypeError):
            continue
        qty = int(it.get("quantity_destroyed", 0)) + int(it.get("quantity_dropped", 0))
        if qty < 1:
            qty = 1
        counts[(tid, flag)] += qty

    for (tid, flag), qty in counts.items():
        info = loader.get_type(tid)
        if info is None:
            continue
        target = _FLAG_TO_GROUP.get(flag)
        if target is None:
            continue
        item_qty = 1 if target in ("high", "med", "low", "rig", "subsystem") else qty
        getattr(fit, target).append(FitItem(
            type_id=tid, name=info.name, quantity=item_qty,
        ))

    return fit
