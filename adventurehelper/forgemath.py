"""Forge math for the forge simulator.

Mirrors `_to_forge` in adventure/class_abilities.py. Keep the two in sync when the forge formula changes.
"""
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

STATS = ("att", "cha", "int", "dex", "luck")
MAX_SLOTS = 11  # equipment slots a character has (two handed items take both hands)
AVERAGE_ROLL = 10.5


@dataclass
class SimItem:
    name: str
    stats: Dict[str, int]
    forged: bool = False
    two_handed: bool = False

    @property
    def total(self) -> int:
        return sum(self.stats.values()) * (2 if self.two_handed else 1)

    @property
    def slots(self) -> int:
        return 2 if self.two_handed else 1


@dataclass
class Loadout:
    items: List[SimItem] = field(default_factory=list)
    extra: int = 0  # rebirth points added to every stat

    def raw(self) -> Dict[str, int]:
        """Raw stats like Character.get_stat_value: no set multipliers, two handed counted in both hands."""
        raw = {s: self.extra for s in STATS}
        for item in self.items:
            for s in STATS:
                raw[s] += item.stats.get(s, 0) * item.slots
        return raw

    def used_slots(self) -> int:
        return sum(i.slots for i in self.items)

    def copy(self) -> "Loadout":
        return Loadout(list(self.items), self.extra)


def roll_modifier(roll: float) -> float:
    return 1.0 + (roll - 1) / 38


def stat_modifier(raw: Dict[str, int], cap: float) -> Tuple[float, float]:
    """Return (uncapped, soft capped) stat bonus for a character's raw stats."""
    bonus = (
        0.01 * (raw["luck"] // 10)
        + 0.01 * (raw["int"] // 20)
        + 0.01 * (max(raw["att"], 1) // 20)
        + 0.01 * (max(raw["cha"], 1) // 20)
    )
    if bonus > 0:
        return bonus, cap * (1 - math.exp(-bonus / cap))
    return bonus, bonus


def forge(item1: SimItem, item2: SimItem, raw: Dict[str, int], roll: float, cap: float) -> Dict[str, int]:
    _, stat_mod = stat_modifier(raw, cap)
    modifier = max(0.001, roll_modifier(roll) + stat_mod)
    result = {}
    for s in STATS:
        base = int(item1.stats.get(s, 0)) + int(item2.stats.get(s, 0))
        result[s] = int(base * modifier + base)
    return result


@dataclass
class ForgeStep:
    raw: Dict[str, int]
    bonus: float
    device: Dict[str, int]
    action: str


def simulate_chain(
    loadout: Loadout,
    item1: SimItem,
    item2: SimItem,
    roll: float,
    cap: float,
    forges: int,
    forge_limit: int = 3,
) -> List[ForgeStep]:
    """Forge repeatedly, equipping each device if it improves the build, like a tinkerer chasing stats."""
    loadout = loadout.copy()
    steps = []
    for n in range(1, forges + 1):
        raw = loadout.raw()
        _, bonus = stat_modifier(raw, cap)
        stats = forge(item1, item2, raw, roll, cap)
        device = SimItem(f"Device #{n}", stats, forged=True)
        devices = [i for i in loadout.items if i.forged]
        action: Optional[str] = None
        if len(devices) < forge_limit and loadout.used_slots() < MAX_SLOTS:
            loadout.items.append(device)
            action = "equipped in an empty slot"
        else:
            pool = devices if len(devices) >= forge_limit else [i for i in loadout.items if not i.forged]
            weakest = min(pool, key=lambda i: i.total, default=None)
            if weakest is not None and device.total > weakest.total:
                loadout.items[loadout.items.index(weakest)] = device
                action = f"replaced {weakest.name}"
        steps.append(ForgeStep(raw, bonus, stats, action or "weaker than gear, not equipped"))
    return steps
