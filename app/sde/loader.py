"""Read-only accessor for the Fuzzwork SDE SQLite dump.

Fuzzwork's dump preserves CCP's SDE table names (`invTypes`, `dgmTypeAttributes`,
etc.). We treat it as immutable reference data — opened read-only, shared
across threads via SQLite's `check_same_thread=False`.

Refresh the underlying file with `python -m app.sde.refresh`.
"""
from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass
from functools import lru_cache
from typing import Dict, List, Optional

from .. import config

# Attribute IDs from CCP dogma that matter for slot layout / hardpoints.
ATTR = {
    "hi_slots":            14,
    "med_slots":           13,
    "low_slots":           12,
    "rig_slots":         1154,
    "subsystem_slots":   1367,
    "launcher_hardpoints": 101,
    "turret_hardpoints":   102,
    "drone_bandwidth":    1271,
    "drone_capacity":      283,
    "cpu_output":            48,
    "power_output":          11,
    "capacitor_capacity":   482,
    "recharge_rate":         55,
    "hp":                    9,  # structure HP
    "shield_capacity":      263,
    "armor_hp":             265,
    "mass":                    4,
    "max_velocity":           37,
    "signature_radius":      552,
    "scan_resolution":      564,
    "max_locked_targets":   192,
    "max_target_range":     76,
}

# Effect IDs that flag slot type for modules.
EFFECT = {
    "hi_power":   12,
    "med_power":  13,
    "lo_power":   11,
    "rig_slot": 2663,
    "subsystem": 3772,
}

SLOT_FROM_EFFECT: Dict[int, str] = {
    EFFECT["hi_power"]:  "high",
    EFFECT["med_power"]: "med",
    EFFECT["lo_power"]:  "low",
    EFFECT["rig_slot"]:  "rig",
    EFFECT["subsystem"]: "subsystem",
}


@dataclass
class TypeInfo:
    type_id: int
    name: str
    group_id: int
    group_name: str
    category_id: int
    category_name: str
    published: bool
    volume: float
    mass: float
    capacity: float


# --- Connection -------------------------------------------------------------

_conn: Optional[sqlite3.Connection] = None
_conn_lock = threading.Lock()


def _connect() -> sqlite3.Connection:
    global _conn
    if _conn is not None:
        return _conn
    with _conn_lock:
        if _conn is None:
            path = config.SDE_SQLITE_PATH
            if not path.exists():
                raise FileNotFoundError(
                    f"SDE SQLite not found at {path}. Run: python -m app.sde.refresh"
                )
            uri = f"file:{path.as_posix()}?mode=ro"
            _conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
            _conn.row_factory = sqlite3.Row
    return _conn


def close() -> None:
    global _conn
    if _conn is not None:
        _conn.close()
        _conn = None


# --- Lookups ----------------------------------------------------------------


@lru_cache(maxsize=8192)
def get_type(type_id: int) -> Optional[TypeInfo]:
    row = _connect().execute(
        """
        SELECT t.typeID, t.typeName, t.groupID, t.published,
               COALESCE(t.volume, 0)   AS volume,
               COALESCE(t.mass, 0)     AS mass,
               COALESCE(t.capacity, 0) AS capacity,
               g.groupName, g.categoryID, c.categoryName
        FROM invTypes t
        JOIN invGroups g       ON g.groupID    = t.groupID
        JOIN invCategories c   ON c.categoryID = g.categoryID
        WHERE t.typeID = ?
        """,
        (type_id,),
    ).fetchone()
    if row is None:
        return None
    return TypeInfo(
        type_id=row["typeID"],
        name=row["typeName"],
        group_id=row["groupID"],
        group_name=row["groupName"],
        category_id=row["categoryID"],
        category_name=row["categoryName"],
        published=bool(row["published"]),
        volume=float(row["volume"]),
        mass=float(row["mass"]),
        capacity=float(row["capacity"]),
    )


@lru_cache(maxsize=8192)
def find_type_by_name(name: str) -> Optional[TypeInfo]:
    """Case-insensitive exact match. Prefer this for import parsing."""
    row = _connect().execute(
        "SELECT typeID FROM invTypes WHERE typeName = ? COLLATE NOCASE LIMIT 1",
        (name,),
    ).fetchone()
    return get_type(int(row["typeID"])) if row else None


def search_types_by_name(query: str, limit: int = 30) -> List[TypeInfo]:
    """LIKE search, published items only. For future autocomplete."""
    rows = _connect().execute(
        """
        SELECT typeID FROM invTypes
        WHERE typeName LIKE ? COLLATE NOCASE AND published = 1
        ORDER BY typeName LIMIT ?
        """,
        (f"%{query}%", limit),
    ).fetchall()
    out: List[TypeInfo] = []
    for r in rows:
        ti = get_type(int(r["typeID"]))
        if ti:
            out.append(ti)
    return out


@lru_cache(maxsize=16384)
def get_attributes(type_id: int) -> Dict[int, float]:
    """All dogma attributes for a type, keyed by attributeID."""
    rows = _connect().execute(
        """
        SELECT attributeID,
               COALESCE(valueFloat, valueInt) AS v
        FROM dgmTypeAttributes WHERE typeID = ?
        """,
        (type_id,),
    ).fetchall()
    return {int(r["attributeID"]): float(r["v"] or 0) for r in rows}


def get_attr(type_id: int, attr_id: int, default: float = 0.0) -> float:
    return get_attributes(type_id).get(attr_id, default)


@lru_cache(maxsize=16384)
def get_effects(type_id: int) -> List[int]:
    rows = _connect().execute(
        "SELECT effectID FROM dgmTypeEffects WHERE typeID = ?",
        (type_id,),
    ).fetchall()
    return [int(r["effectID"]) for r in rows]


def slot_of_module(type_id: int) -> Optional[str]:
    """Return 'high' / 'med' / 'low' / 'rig' / 'subsystem' or None."""
    for eid in get_effects(type_id):
        if eid in SLOT_FROM_EFFECT:
            return SLOT_FROM_EFFECT[eid]
    return None


def ship_slot_layout(type_id: int) -> Dict[str, int]:
    """Slot counts for a ship type."""
    a = get_attributes(type_id)
    return {
        "high":      int(a.get(ATTR["hi_slots"], 0)),
        "med":       int(a.get(ATTR["med_slots"], 0)),
        "low":       int(a.get(ATTR["low_slots"], 0)),
        "rig":       int(a.get(ATTR["rig_slots"], 0)),
        "subsystem": int(a.get(ATTR["subsystem_slots"], 0)),
        "launcher_hardpoints": int(a.get(ATTR["launcher_hardpoints"], 0)),
        "turret_hardpoints":   int(a.get(ATTR["turret_hardpoints"], 0)),
    }
