"""Normalized fit representation shared by every parser."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import List, Optional


class ParseError(ValueError):
    """Raised by any parser when the input cannot be interpreted."""


@dataclass
class FitItem:
    type_id: int
    name: str
    quantity: int = 1
    charge_type_id: Optional[int] = None
    charge_name: Optional[str] = None


@dataclass
class Fit:
    name: str
    ship_type_id: int
    ship_type_name: str
    description: str = ""
    high: List[FitItem] = field(default_factory=list)
    med: List[FitItem] = field(default_factory=list)
    low: List[FitItem] = field(default_factory=list)
    rig: List[FitItem] = field(default_factory=list)
    subsystem: List[FitItem] = field(default_factory=list)
    drones: List[FitItem] = field(default_factory=list)
    cargo: List[FitItem] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def slot_count(self) -> int:
        return sum(len(g) for g in (self.high, self.med, self.low, self.rig, self.subsystem))
