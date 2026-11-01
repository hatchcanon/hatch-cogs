"""Deterministic combat simulator.

Pure Python with no Discord dependencies. The same unit snapshots and seed always
produce the same fight, so a replay only needs the stored inputs.
"""

import hashlib
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .data import (
    BACK_SLOTS,
    BASE_ATTACK_TICKS,
    COUNTER_ACCURACY,
    COUNTER_DAMAGE,
    COUNTERS,
    ENERGY_MAX,
    ENERGY_PER_ATTACK,
    ENERGY_PER_PCT_LOST,
    FRONT_SLOTS,
    MAX_TICKS,
    TEAM_BONUSES,
    TICKS_PER_SEC,
    ULT_TIMEOUT_TICKS,
)


def seed_from_id(battle_id: str) -> int:
    return int(hashlib.sha256(battle_id.encode()).hexdigest()[:16], 16)


def team_bonus(factions: List[str]) -> float:
    """Faction team bonus for a lineup. Radiant/Abyssal count as wildcards."""
    wild = sum(1 for f in factions if f in ("radiant", "abyssal"))
    counts = sorted(
        (factions.count(f) for f in set(factions) if f not in ("radiant", "abyssal")),
        reverse=True,
    )
    counts += [0, 0]
    top = min(5, counts[0] + wild)
    left = wild - (top - counts[0])
    second = counts[1] + left
    for need_top, need_second, bonus in TEAM_BONUSES:
        if top >= need_top and second >= need_second:
            return bonus
    return 0.0


def counters(attacker: str, target: str) -> bool:
    return COUNTERS.get(attacker) == target


class Unit:
    def __init__(self, side: int, slot: int, snap: dict, bonus: float):
        self.side = side
        self.slot = slot
        self.snap = snap
        self.name = snap["name"]
        self.faction = snap["faction"]
        self.role = snap["role"]
        self.level = snap["level"]
        self.boss = snap.get("boss", False)
        self.max_hp = snap["hp"] * (1 + bonus)
        self.hp = self.max_hp
        self.base_atk = snap["atk"] * (1 + bonus)
        self.base_def = snap["def"]
        self.base_spd = snap["spd"]
        self.crit = snap["crit"]
        self.critdmg = snap["critdmg"]
        self.acc = snap["acc"]
        self.base_dodge = snap["dodge"]
        self.haste = snap["haste"]
        self.energy_gain = snap["energy"]
        self.skill_mult = snap["skill"]
        self.rule = snap.get("rule", "immediate")
        self.autos = [dict(s) for s in snap["skills"] if s.get("cd")]
        self.ult = next((s for s in snap["skills"] if not s.get("cd")), None)
        self.cooldowns = [int(s["cd"] * TICKS_PER_SEC / 2) for s in self.autos]
        self.energy = 0.0
        self.attack_timer = 0
        self.ready_tick: Optional[int] = None
        self.last_ult_tick = -1
        self.shield = 0.0
        self.shield_ticks = 0
        self.stun_ticks = 0
        self.taunt_ticks = 0
        # stat -> list of [amount, ticks_left]
        self.buffs: Dict[str, list] = {}
        self.dead = False
        self.damage_done = 0.0
        self.healing_done = 0.0
        self.damage_taken = 0.0

    @property
    def alive(self) -> bool:
        return not self.dead and self.hp > 0

    @property
    def hp_pct(self) -> float:
        return self.hp / self.max_hp * 100

    def _buffed(self, stat: str) -> float:
        return sum(b[0] for b in self.buffs.get(stat, ()))

    @property
    def atk(self) -> float:
        return self.base_atk * (1 + self._buffed("atk"))

    @property
    def defense(self) -> float:
        return max(0.0, self.base_def * (1 + self._buffed("def") - self._buffed("shred")))

    @property
    def spd(self) -> float:
        return self.base_spd * (1 + self._buffed("spd"))

    @property
    def dodge(self) -> float:
        return self.base_dodge + self._buffed("dodge")

    @property
    def attack_interval(self) -> int:
        return max(3, round(BASE_ATTACK_TICKS * 100 / self.spd))

    def tick_status(self):
        if self.stun_ticks:
            self.stun_ticks -= 1
        if self.taunt_ticks:
            self.taunt_ticks -= 1
        if self.shield_ticks:
            self.shield_ticks -= 1
            if not self.shield_ticks:
                self.shield = 0.0
        for stat in list(self.buffs):
            kept = []
            for b in self.buffs[stat]:
                b[1] -= 1
                if b[1] > 0:
                    kept.append(b)
            if kept:
                self.buffs[stat] = kept
            else:
                del self.buffs[stat]

    def gain_energy(self, amount: float):
        self.energy = min(ENERGY_MAX, self.energy + amount * self.energy_gain)


@dataclass
class BattleResult:
    win: bool
    ticks: int
    attackers: List[dict]
    defenders: List[dict]
    log: List[str] = field(default_factory=list)
    front_fell_tick: Optional[int] = None
    timed_out: bool = False

    @property
    def seconds(self) -> float:
        return self.ticks / TICKS_PER_SEC

    @property
    def mvp(self) -> Optional[dict]:
        if not self.attackers:
            return None
        return max(self.attackers, key=lambda u: u["damage"] + u["healing"])


class Battle:
    def __init__(self, attackers: List[Optional[dict]], defenders: List[Optional[dict]], seed: int, log: bool = False):
        self.rng = random.Random(seed)
        self.logging = log
        self.log: List[str] = []
        self.tick = 0
        self.sides: List[List[Unit]] = []
        for side, snaps in enumerate((attackers, defenders)):
            factions = [s["faction"] for s in snaps if s]
            bonus = team_bonus(factions)
            units = [Unit(side, slot, s, bonus) for slot, s in enumerate(snaps) if s]
            self.sides.append(units)
            if log and bonus:
                who = "Your team" if side == 0 else "Enemy team"
                self._log(f"{who} gains a +{bonus:.0%} faction bonus.")
        self.front_fell_tick: Optional[int] = None

    # ---------------------------------------------------------------- helpers

    def _log(self, text: str):
        if self.logging:
            self.log.append(f"`{self.tick / TICKS_PER_SEC:5.1f}s` {text}")

    def _allies(self, u: Unit) -> List[Unit]:
        return [a for a in self.sides[u.side] if a.alive]

    def _enemies(self, u: Unit) -> List[Unit]:
        return [e for e in self.sides[1 - u.side] if e.alive]

    def _lines(self, units: List[Unit]):
        front = [x for x in units if x.slot in FRONT_SLOTS]
        back = [x for x in units if x.slot in BACK_SLOTS]
        return front, back

    def _targets(self, u: Unit, target: str) -> List[Unit]:
        enemies = self._enemies(u)
        if not enemies:
            return []
        front, back = self._lines(enemies)
        if target == "single":
            taunting = [e for e in enemies if e.taunt_ticks]
            if taunting:
                return [self.rng.choice(taunting)]
            return [self.rng.choice(front or back)]
        if target == "front":
            return front or back
        if target == "back":
            return back or front
        if target == "back_single":
            return [self.rng.choice(back or front)]
        if target == "all":
            return enemies
        if target == "lowest":
            return [min(enemies, key=lambda e: (e.hp_pct, e.slot))]
        if target == "highest_atk":
            return [max(enemies, key=lambda e: (e.atk, -e.slot))]
        if target.startswith("random:"):
            n = int(target.split(":")[1])
            return [self.rng.choice(enemies) for _ in range(n)]
        return [self.rng.choice(front or back)]

    def _ally_targets(self, u: Unit, target: str) -> List[Unit]:
        allies = self._allies(u)
        if target == "self":
            return [u]
        if target == "lowest_ally":
            return [min(allies, key=lambda a: (a.hp_pct, a.slot))] if allies else []
        return allies

    # ---------------------------------------------------------------- actions

    def _hit(self, u: Unit, t: Unit, mult: float) -> float:
        countered = counters(u.faction, t.faction)
        hit_chance = 0.95 + (u.acc - t.dodge + (COUNTER_ACCURACY if countered else 0)) / 100
        if self.rng.random() > min(1.0, max(0.3, hit_chance)):
            return 0.0
        k = 100 + 10 * u.level
        dmg = u.atk * mult * (k / (k + t.defense))
        if countered:
            dmg *= COUNTER_DAMAGE
        if self.rng.random() < u.crit:
            dmg *= u.critdmg
        dmg *= self.rng.uniform(0.95, 1.05)
        self._apply_damage(u, t, dmg)
        return dmg

    def _apply_damage(self, u: Unit, t: Unit, dmg: float):
        u.damage_done += dmg
        absorbed = min(t.shield, dmg)
        t.shield -= absorbed
        taken = dmg - absorbed
        lost = min(t.hp, taken)
        t.hp -= taken
        t.damage_taken += lost
        t.gain_energy(ENERGY_PER_PCT_LOST * lost / t.max_hp * 100)

    def _heal(self, u: Unit, t: Unit, amount: float):
        healed = min(t.max_hp - t.hp, amount)
        t.hp += healed
        u.healing_done += healed

    def _cast(self, u: Unit, skill: dict, is_ult: bool):
        mult_scale = u.skill_mult
        notes = []
        for eff in skill["effects"]:
            kind = eff["kind"]
            if kind == "dmg":
                targets = self._targets(u, eff["target"])
                total = 0.0
                for t in targets:
                    dealt = self._hit(u, t, eff["mult"] * mult_scale)
                    total += dealt
                    if dealt and eff.get("stun"):
                        t.stun_ticks = max(t.stun_ticks, int(eff["stun"] * TICKS_PER_SEC))
                    if dealt and eff.get("shred"):
                        pct, dur = eff["shred"]
                        t.buffs.setdefault("shred", []).append([pct, int(dur * TICKS_PER_SEC)])
                if eff.get("lifesteal") and total:
                    self._heal(u, u, total * eff["lifesteal"])
                if targets:
                    names = targets[0].name if len(set(targets)) == 1 else f"{len(set(targets))} enemies"
                    notes.append(f"hits {names} for {total:,.0f}")
            elif kind == "heal":
                targets = self._ally_targets(u, eff["target"])
                before = u.healing_done
                for t in targets:
                    self._heal(u, t, u.atk * eff["mult"] * mult_scale)
                notes.append(f"heals {u.healing_done - before:,.0f}")
            elif kind == "shield":
                for t in self._ally_targets(u, eff["target"]):
                    t.shield = max(t.shield, u.atk * eff["mult"] * mult_scale)
                    t.shield_ticks = int(eff["dur"] * TICKS_PER_SEC)
                notes.append("shields " + ("self" if eff["target"] == "self" else "allies"))
            elif kind == "buff":
                for t in self._ally_targets(u, eff["target"]):
                    t.buffs.setdefault(eff["stat"], []).append([eff["amt"], int(eff["dur"] * TICKS_PER_SEC)])
                notes.append(f"buffs {eff['stat'].upper()}")
            elif kind == "taunt":
                u.taunt_ticks = int(eff["dur"] * TICKS_PER_SEC)
                notes.append("taunts")
            elif kind == "energy":
                for t in self._ally_targets(u, eff["target"]):
                    if t is not u:
                        t.gain_energy(eff["amt"])
                notes.append("energizes allies")
        if is_ult:
            self._log(f"💥 **{u.name}** unleashes **{skill['name']}** — {', '.join(notes)}")
        else:
            self._log(f"✨ {u.name} uses {skill['name']} — {', '.join(notes)}")

    def _ult_ready(self, u: Unit) -> bool:
        if not u.ult or u.energy < ENERGY_MAX:
            return False
        if u.ready_tick is None:
            u.ready_tick = self.tick
        if self.tick - u.ready_tick >= ULT_TIMEOUT_TICKS:
            return True
        rule = u.rule or "immediate"
        kind, _, arg = rule.partition(":")
        if kind == "immediate":
            return True
        if kind == "enemies":
            return len(self._enemies(u)) >= int(arg)
        if kind == "ally":
            return any(a.hp_pct < int(arg) for a in self._allies(u))
        if kind == "boss":
            enemies = self._enemies(u)
            bosses = [e for e in enemies if e.boss] or enemies
            return any(e.hp_pct < int(arg) for e in bosses)
        if kind == "after":
            partner = next((a for a in self.sides[u.side] if a.slot == int(arg)), None)
            if partner is None or partner is u or not partner.alive:
                return True
            return partner.last_ult_tick >= u.ready_tick
        return True

    def _act(self, u: Unit):
        if self._ult_ready(u):
            self._cast(u, u.ult, True)
            u.energy = 0.0
            u.ready_tick = None
            u.last_ult_tick = self.tick
            return
        for i, skill in enumerate(u.autos):
            if u.cooldowns[i] <= 0:
                self._cast(u, skill, False)
                u.cooldowns[i] = int(skill["cd"] * TICKS_PER_SEC * 100 / (100 + u.haste))
                return
        if u.attack_timer <= 0:
            targets = self._targets(u, "single")
            if targets:
                self._hit(u, targets[0], 1.0)
            u.gain_energy(ENERGY_PER_ATTACK)
            u.attack_timer = u.attack_interval

    # ---------------------------------------------------------------- loop

    def run(self) -> BattleResult:
        attackers, defenders = self.sides
        winner = None
        while self.tick < MAX_TICKS:
            everyone = [u for side in self.sides for u in side if u.alive]
            # 1. status effects
            for u in everyone:
                u.tick_status()
            # 2. cooldowns
            for u in everyone:
                u.cooldowns = [c - 1 for c in u.cooldowns]
                u.attack_timer -= 1
            # 3/4. actions in Speed order
            for u in sorted(everyone, key=lambda x: (-x.spd, x.side, x.slot)):
                if u.alive and not u.stun_ticks:
                    self._act(u)
            # 5. death checks
            for u in everyone:
                if u.hp <= 0 and not u.dead:
                    u.dead = True
                    self._log(f"☠️ {u.name} falls.")
            if self.front_fell_tick is None and attackers:
                front = [a for a in attackers if a.slot in FRONT_SLOTS]
                if front and all(a.dead for a in front):
                    self.front_fell_tick = self.tick
            self.tick += 1
            if not any(u.alive for u in defenders):
                winner = 0
                break
            if not any(u.alive for u in attackers):
                winner = 1
                break
        timed_out = winner is None
        if timed_out:
            self._log("⏱️ Time is up. The attack fails.")
        return BattleResult(
            win=winner == 0,
            ticks=self.tick,
            attackers=[self._summary(u) for u in attackers],
            defenders=[self._summary(u) for u in defenders],
            log=self.log,
            front_fell_tick=self.front_fell_tick,
            timed_out=timed_out,
        )

    @staticmethod
    def _summary(u: Unit) -> dict:
        return {
            "name": u.name,
            "slot": u.slot,
            "role": u.role,
            "faction": u.faction,
            "damage": u.damage_done,
            "healing": u.healing_done,
            "taken": u.damage_taken,
            "alive": u.alive,
            "hp_pct": max(0.0, u.hp_pct),
        }


def simulate(attackers, defenders, seed: int, log: bool = False) -> BattleResult:
    return Battle(attackers, defenders, seed, log=log).run()
