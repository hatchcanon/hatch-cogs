"""Game rules that operate on a plain player dict. No Discord code lives here."""

import copy
import datetime
import random
from typing import Dict, List, Optional, Tuple

from .combat import BattleResult, counters, seed_from_id, simulate
from .data import (
    ASCENSION_COSTS,
    BASE_SECONDARY,
    BIG_SPEND_CONFIRM,
    BOSS_CLEAR_GEMS,
    CHAPTER_CHEST,
    DAILY_BONUS,
    DAILY_QUESTS,
    FACTIONS,
    FAST_REWARD_FREE,
    FAST_REWARD_GEM_COSTS,
    FAST_REWARD_MINUTES,
    FIRST_CLEAR_GEMS,
    GEM_TRICKLE_PER_MIN,
    HEROES,
    IDLE_CAP_MINUTES,
    ITEM_ROLL_MINUTES,
    MAX_STAGE,
    MAX_TIER,
    PASSIVE_UNLOCK_TIER,
    RARITIES,
    ROLE_BASE_STATS,
    S2_UNLOCK_TIER,
    SCROLL_FRAGMENTS_PER_SCROLL,
    SKILL_UPGRADE_TIERS,
    SPECIAL_FACTIONS,
    STAGES_PER_CHAPTER,
    STARTER_FODDER,
    STARTING_RESOURCES,
    SUMMON_GEM_COST,
    SUMMON_PITY,
    SUMMON_RATES,
    TIERS,
    WISHLIST_CHANCE,
    heroes_of,
)

DEFAULT_PLAYER = {
    "started": False,
    "res": {},
    "heroes": {},
    "next_iid": 1,
    "stage": 0,
    "last_claim": 0.0,
    "pity": 0,
    "pulls": 0,
    "wishlist": [],
    "teams": {},
    "daily": {},
    "settings": {"dm": False, "public": True},
    "notified_claim": 0.0,
    "last_dm": 0.0,
    "battles": 0,
    "last_battle": None,
}


class GameError(Exception):
    """A rule was broken; the message is shown to the player."""


def now_ts() -> float:
    return datetime.datetime.now(datetime.timezone.utc).timestamp()


def today_str(ts: Optional[float] = None) -> str:
    ts = now_ts() if ts is None else ts
    return datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).strftime("%Y-%m-%d")


def next_reset_ts(ts: Optional[float] = None) -> int:
    ts = now_ts() if ts is None else ts
    day = datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).date()
    reset = datetime.datetime.combine(day + datetime.timedelta(days=1), datetime.time(), datetime.timezone.utc)
    return int(reset.timestamp())


# ---------------------------------------------------------------- new player


def empty_team() -> dict:
    return {"slots": [None] * 5, "rules": ["immediate"] * 5}


def new_player(starter: str, ts: float) -> dict:
    p = copy.deepcopy(DEFAULT_PLAYER)
    p["started"] = True
    p["res"] = dict(STARTING_RESOURCES)
    p["last_claim"] = ts
    p["notified_claim"] = ts
    add_hero(p, starter)
    for hid in STARTER_FODDER:
        add_hero(p, hid)
    p["teams"]["campaign"] = empty_team()
    auto_team(p, "campaign")
    return p


def add_hero(p: dict, hid: str) -> str:
    iid = str(p["next_iid"])
    p["next_iid"] += 1
    p["heroes"][iid] = {"hid": hid, "tier": 0, "level": 1, "gold_spent": 0, "ess_spent": 0}
    return iid


def add_resources(p: dict, loot: Dict[str, int]):
    for key, amount in loot.items():
        p["res"][key] = p["res"].get(key, 0) + int(amount)
    frags = p["res"].get("scroll_frags", 0)
    if frags >= SCROLL_FRAGMENTS_PER_SCROLL:
        p["res"]["scrolls"] = p["res"].get("scrolls", 0) + frags // SCROLL_FRAGMENTS_PER_SCROLL
        p["res"]["scroll_frags"] = frags % SCROLL_FRAGMENTS_PER_SCROLL


# ---------------------------------------------------------------- hero stats


def hero_def(inst_or_hid) -> dict:
    hid = inst_or_hid if isinstance(inst_or_hid, str) else inst_or_hid["hid"]
    return HEROES[hid]


def max_tier(hid: str) -> int:
    return min(MAX_TIER, RARITIES[HEROES[hid]["rarity"]]["max_tier"])


def level_cap(inst: dict) -> int:
    d = hero_def(inst)
    return min(TIERS[inst["tier"]]["cap"], RARITIES[d["rarity"]]["level_cap"])


def tier_name(tier: int) -> str:
    return TIERS[tier]["name"]


def hero_stats(inst: dict) -> dict:
    d = hero_def(inst)
    base = ROLE_BASE_STATS[d["role"]]
    growth = 1 + 0.08 * (inst["level"] - 1)
    mult = RARITIES[d["rarity"]]["stat_mult"] * TIERS[inst["tier"]]["mult"]
    stats = {
        "hp": base["hp"] * growth * mult,
        "atk": base["atk"] * growth * mult,
        "def": base["def"] * growth * mult,
        "spd": float(base["spd"]),
        **BASE_SECONDARY,
    }
    if d["cls"] == "might":
        stats["hp"] *= 1.15
        stats["def"] *= 1.15
    elif d["cls"] == "agility":
        stats["spd"] *= 1.10
        stats["crit"] += 0.07
    elif d["cls"] == "intellect":
        stats["energy"] += 0.20
        stats["skill"] += 0.15
    stats["skill"] += 0.10 * sum(1 for t in SKILL_UPGRADE_TIERS if inst["tier"] >= t)
    passive = d.get("passive")
    if passive and inst["tier"] >= PASSIVE_UNLOCK_TIER:
        for stat, value in passive["stats"].items():
            if stat in ("hp", "atk", "def", "spd"):
                stats[stat] *= 1 + value
            else:
                stats[stat] += value
    return stats


def power(stats: dict) -> int:
    offense = stats["atk"] * (stats["spd"] / 100) * (1 + stats["crit"] * (stats["critdmg"] - 1)) * stats["skill"]
    return int(stats["hp"] / 6 + offense * 3 + stats["def"] * 2)


def hero_power(inst: dict) -> int:
    return power(hero_stats(inst))


def hero_skills(inst: dict) -> List[Tuple[str, dict, bool]]:
    """(slot label, skill, unlocked) for every skill the hero has."""
    d = hero_def(inst)
    out = [("Ultimate", d["ult"], True), ("Skill 1", d["s1"], True)]
    if "s2" in d:
        out.append(("Skill 2", d["s2"], inst["tier"] >= S2_UNLOCK_TIER))
    if "passive" in d:
        out.append(("Passive", d["passive"], inst["tier"] >= PASSIVE_UNLOCK_TIER))
    return out


def snapshot(inst: dict, rule: str = "immediate", boss: bool = False, scale: float = 1.0) -> dict:
    d = hero_def(inst)
    stats = hero_stats(inst)
    stats["hp"] *= scale
    stats["atk"] *= scale
    skills = [d["s1"], d["ult"]]
    if "s2" in d and inst["tier"] >= S2_UNLOCK_TIER:
        skills.insert(1, d["s2"])
    return {
        "name": d["name"] + (" (Boss)" if boss else ""),
        "hid": inst["hid"],
        "faction": d["faction"],
        "role": d["role"],
        "level": inst["level"],
        "boss": boss,
        "rule": rule,
        "skills": copy.deepcopy(skills),
        **stats,
    }


def hero_label(inst: dict, with_level: bool = True) -> str:
    d = hero_def(inst)
    text = f"{FACTIONS[d['faction']]['emoji']} {d['name']}"
    if with_level:
        text += f" · {tier_name(inst['tier'])} Lv.{inst['level']}"
    return text


# ---------------------------------------------------------------- leveling


def level_cost(level: int) -> Tuple[int, int]:
    """Gold and Essence to go from ``level`` to ``level + 1``."""
    return int(20 + 3 * level * level), int(6 + 0.9 * level * level)


def level_up(p: dict, iid: str, levels: int) -> Tuple[int, int, int]:
    inst = p["heroes"].get(iid)
    if not inst:
        raise GameError("That hero is no longer in your roster.")
    cap = level_cap(inst)
    if inst["level"] >= cap:
        raise GameError(f"Level cap reached ({cap}). Ascend this hero to raise it.")
    gained = gold = ess = 0
    while gained < levels and inst["level"] < cap:
        g, e = level_cost(inst["level"])
        if p["res"].get("gold", 0) < g or p["res"].get("essence", 0) < e:
            break
        p["res"]["gold"] -= g
        p["res"]["essence"] -= e
        inst["gold_spent"] += g
        inst["ess_spent"] += e
        inst["level"] += 1
        gained += 1
        gold += g
        ess += e
    if not gained:
        g, e = level_cost(inst["level"])
        raise GameError(f"Not enough resources. The next level costs {g:,} Gold and {e:,} Essence.")
    return gained, gold, ess


# ---------------------------------------------------------------- idle rewards


def idle_minutes(p: dict, ts: float) -> float:
    return max(0.0, min((ts - p["last_claim"]) / 60, IDLE_CAP_MINUTES))


def idle_rates(stage: int) -> Dict[str, float]:
    return {"gold": 20 + 4 * stage, "essence": 5 + 1.2 * stage, "gems": GEM_TRICKLE_PER_MIN}


def loot_for_minutes(minutes: float, stage: int, rng: random.Random) -> Dict[str, int]:
    rates = idle_rates(stage)
    loot = {k: int(minutes * v) for k, v in rates.items()}
    for _ in range(int(minutes // ITEM_ROLL_MINUTES)):
        roll = rng.random()
        if roll < 0.5:
            loot["scroll_frags"] = loot.get("scroll_frags", 0) + rng.randint(1, 2)
        elif roll < 0.8:
            loot["forge_ore"] = loot.get("forge_ore", 0) + rng.randint(1, 3)
    return {k: v for k, v in loot.items() if v}


def claim_idle(p: dict, ts: float, rng: random.Random) -> Dict[str, int]:
    minutes = idle_minutes(p, ts)
    if minutes < 1:
        raise GameError("Your chest is empty. Check back in a few minutes.")
    loot = loot_for_minutes(minutes, p["stage"], rng)
    p["last_claim"] = ts
    add_resources(p, loot)
    quest_progress(p, "collect", ts=ts)
    return loot


def chest_full_at(p: dict) -> int:
    return int(p["last_claim"] + IDLE_CAP_MINUTES * 60)


def fast_reward_cost(p: dict, ts: float) -> Optional[int]:
    """Gem cost of the next Fast Reward: 0 if free, None if none are left today."""
    used = ensure_daily(p, ts)["fast_used"]
    if used < FAST_REWARD_FREE:
        return 0
    paid = used - FAST_REWARD_FREE
    if paid >= len(FAST_REWARD_GEM_COSTS):
        return None
    return FAST_REWARD_GEM_COSTS[paid]


def use_fast_reward(p: dict, ts: float, rng: random.Random) -> Tuple[Dict[str, int], int]:
    cost = fast_reward_cost(p, ts)
    if cost is None:
        raise GameError("No Fast Rewards left today.")
    if p["res"].get("gems", 0) < cost:
        raise GameError(f"You need {cost} Gems for another Fast Reward.")
    p["res"]["gems"] = p["res"].get("gems", 0) - cost
    p["daily"]["fast_used"] += 1
    loot = loot_for_minutes(FAST_REWARD_MINUTES, p["stage"], rng)
    add_resources(p, loot)
    quest_progress(p, "fast", ts=ts)
    return loot, cost


# ---------------------------------------------------------------- daily quests


def ensure_daily(p: dict, ts: float) -> dict:
    day = today_str(ts)
    if p.get("daily", {}).get("day") != day:
        p["daily"] = {"day": day, "fast_used": 0, "progress": {}, "claimed": [], "bonus": False}
    return p["daily"]


def quest_progress(p: dict, qid: str, amount: int = 1, ts: Optional[float] = None):
    daily = ensure_daily(p, now_ts() if ts is None else ts)
    daily["progress"][qid] = daily["progress"].get(qid, 0) + amount


def claimable_quests(p: dict, ts: float) -> List[str]:
    daily = ensure_daily(p, ts)
    return [
        qid
        for qid, q in DAILY_QUESTS.items()
        if qid not in daily["claimed"] and daily["progress"].get(qid, 0) >= q["goal"]
    ]


def claim_quests(p: dict, ts: float) -> Dict[str, int]:
    daily = ensure_daily(p, ts)
    rewards: Dict[str, int] = {}
    ready = claimable_quests(p, ts)
    for qid in ready:
        daily["claimed"].append(qid)
        for k, v in DAILY_QUESTS[qid]["reward"].items():
            rewards[k] = rewards.get(k, 0) + v
    if not daily["bonus"] and len(daily["claimed"]) == len(DAILY_QUESTS):
        daily["bonus"] = True
        for k, v in DAILY_BONUS.items():
            rewards[k] = rewards.get(k, 0) + v
    if not rewards:
        raise GameError("No quests are ready to claim.")
    add_resources(p, rewards)
    return rewards


# ---------------------------------------------------------------- summons


def summon_cost(p: dict, count: int) -> Optional[Tuple[int, int]]:
    """(scrolls, gems) a pull of ``count`` would use, or None if unaffordable."""
    scrolls = min(p["res"].get("scrolls", 0), count)
    gems = (count - scrolls) * SUMMON_GEM_COST
    if p["res"].get("gems", 0) < gems:
        return None
    return scrolls, gems


def needs_confirm(cost: Tuple[int, int]) -> bool:
    return cost[1] >= BIG_SPEND_CONFIRM


def _roll_rarity(rng: random.Random) -> str:
    roll = rng.random()
    if roll < SUMMON_RATES["elite"]:
        return "elite"
    if roll < SUMMON_RATES["elite"] + SUMMON_RATES["rare"]:
        return "rare"
    return "common"


def summon(p: dict, count: int, rng: random.Random, ts: float) -> List[Tuple[str, str]]:
    cost = summon_cost(p, count)
    if cost is None:
        raise GameError(
            f"Not enough Summon Scrolls or Gems. Each pull costs 1 Scroll or {SUMMON_GEM_COST} Gems."
        )
    p["res"]["scrolls"] = p["res"].get("scrolls", 0) - cost[0]
    p["res"]["gems"] = p["res"].get("gems", 0) - cost[1]
    elites = [h for h in heroes_of("elite") if HEROES[h]["faction"] not in SPECIAL_FACTIONS]
    wishlist = [h for h in p["wishlist"] if h in elites]
    results = []
    for _ in range(count):
        p["pulls"] += 1
        rarity = "elite" if p["pity"] + 1 >= SUMMON_PITY else _roll_rarity(rng)
        if rarity == "elite":
            p["pity"] = 0
            if wishlist and rng.random() < WISHLIST_CHANCE:
                hid = rng.choice(wishlist)
            else:
                hid = rng.choice(elites)
        else:
            p["pity"] += 1
            hid = rng.choice(heroes_of(rarity))
        results.append((add_hero(p, hid), hid))
    quest_progress(p, "summon", count, ts=ts)
    return results


# ---------------------------------------------------------------- ascension


def ascension_requirement(p: dict, iid: str) -> Optional[dict]:
    inst = p["heroes"][iid]
    if inst["tier"] >= max_tier(inst["hid"]):
        return None
    count, fodder_tier, same_hero = ASCENSION_COSTS[inst["tier"]]
    faction = hero_def(inst)["faction"]
    if faction in SPECIAL_FACTIONS:
        same_hero = True
    return {"count": count, "tier": fodder_tier, "same_hero": same_hero, "faction": faction, "hid": inst["hid"]}


def describe_requirement(req: dict) -> str:
    tier = tier_name(req["tier"])
    if req["same_hero"]:
        return f"{req['count']} × {tier} {HEROES[req['hid']]['name']}"
    plural = "es" if req["count"] > 1 else ""
    return f"{req['count']} × {tier} {FACTIONS[req['faction']]['name']} hero{plural} (any)"


def heroes_in_teams(p: dict) -> set:
    return {iid for team in p["teams"].values() for iid in team["slots"] if iid}


def eligible_fodder(p: dict, iid: str) -> List[str]:
    req = ascension_requirement(p, iid)
    if not req:
        return []
    locked = heroes_in_teams(p)
    out = []
    for other, inst in p["heroes"].items():
        if other == iid or other in locked or inst["tier"] != req["tier"]:
            continue
        if req["same_hero"] and inst["hid"] != req["hid"]:
            continue
        if not req["same_hero"] and hero_def(inst)["faction"] != req["faction"]:
            continue
        out.append(other)
    out.sort(key=lambda i: (p["heroes"][i]["level"], RARITIES[hero_def(p["heroes"][i])["rarity"]]["stat_mult"]))
    return out


def ascend(p: dict, iid: str, fodder: List[str]) -> Dict[str, int]:
    if iid not in p["heroes"]:
        raise GameError("That hero is no longer in your roster.")
    req = ascension_requirement(p, iid)
    if not req:
        raise GameError("This hero is already at its highest tier.")
    fodder = list(dict.fromkeys(fodder))
    if len(fodder) != req["count"]:
        raise GameError(f"Pick exactly {req['count']} hero(es) to sacrifice.")
    valid = set(eligible_fodder(p, iid))
    if any(f not in valid for f in fodder):
        raise GameError("One of the selected heroes can no longer be used. Reopen the menu and try again.")
    refund = {"gold": 0, "essence": 0}
    for f in fodder:
        inst = p["heroes"].pop(f)
        refund["gold"] += inst["gold_spent"]
        refund["essence"] += inst["ess_spent"]
    add_resources(p, refund)
    p["heroes"][iid]["tier"] += 1
    return refund


# ---------------------------------------------------------------- teams


def auto_team(p: dict, mode: str):
    ranked = sorted(p["heroes"], key=lambda i: hero_power(p["heroes"][i]), reverse=True)
    picked: List[str] = []
    seen_hids = set()
    for iid in ranked:
        if p["heroes"][iid]["hid"] in seen_hids:
            continue
        picked.append(iid)
        seen_hids.add(p["heroes"][iid]["hid"])
        if len(picked) == 5:
            break
    front_roles = ("tank", "warrior")
    picked.sort(key=lambda i: (hero_def(p["heroes"][i])["role"] not in front_roles, -hero_power(p["heroes"][i])))
    team = p["teams"].setdefault(mode, empty_team())
    team["slots"] = (picked + [None] * 5)[:5]


def set_slot(p: dict, mode: str, slot: int, iid: Optional[str]):
    team = p["teams"].setdefault(mode, empty_team())
    if iid is not None:
        if iid not in p["heroes"]:
            raise GameError("That hero is no longer in your roster.")
        hid = p["heroes"][iid]["hid"]
        for i, other in enumerate(team["slots"]):
            if i != slot and other and p["heroes"].get(other, {}).get("hid") == hid:
                team["slots"][i] = None
    team["slots"][slot] = iid


def team_snapshots(p: dict, mode: str) -> List[Optional[dict]]:
    team = p["teams"].get(mode) or empty_team()
    out = []
    for iid, rule in zip(team["slots"], team["rules"]):
        inst = p["heroes"].get(iid) if iid else None
        out.append(snapshot(inst, rule) if inst else None)
    return out


def team_power(snaps: List[Optional[dict]]) -> int:
    return sum(power(s) for s in snaps if s)


# ---------------------------------------------------------------- campaign


def stage_label(stage: int) -> str:
    return f"{(stage - 1) // STAGES_PER_CHAPTER + 1}-{(stage - 1) % STAGES_PER_CHAPTER + 1}"


def is_boss_stage(stage: int) -> bool:
    return stage % 10 == 0


def stage_enemies(stage: int) -> List[Optional[dict]]:
    rng = random.Random(stage * 7919)
    count = min(5, 2 + stage // 3)
    level = 1 + int(stage * 1.55)
    scale = 0.55 if stage <= 3 else min(1.05, 0.8 + stage * 0.0025)
    elite_chance = min(0.9, stage / 50)
    rare_chance = min(0.8, 0.2 + stage / 40)
    picks = []
    for _ in range(count):
        roll = rng.random()
        rarity = "elite" if roll < elite_chance else ("rare" if roll < elite_chance + rare_chance else "common")
        hid = rng.choice(heroes_of(rarity))
        inst = {"hid": hid, "tier": 0, "level": 1}
        inst["tier"] = min(stage // 20, max_tier(hid))
        inst["level"] = min(level, level_cap(inst))
        picks.append(inst)
    front_roles = ("tank", "warrior")
    picks.sort(key=lambda i: hero_def(i)["role"] not in front_roles)
    snaps: List[Optional[dict]] = []
    for slot, inst in enumerate(picks):
        boss = is_boss_stage(stage) and slot == 0
        snap = snapshot(inst, boss=boss, scale=scale)
        if boss:
            snap["hp"] *= 2.5
            snap["atk"] *= 1.25
        snaps.append(snap)
    # Keep the front line filled before the back line.
    front = snaps[:2] if len(snaps) > 2 else snaps
    back = snaps[2:]
    return (front + [None] * (2 - len(front)) + back + [None] * 3)[:5]


def first_clear_rewards(stage: int) -> Dict[str, int]:
    rewards = {"gems": BOSS_CLEAR_GEMS if is_boss_stage(stage) else FIRST_CLEAR_GEMS}
    if stage % STAGES_PER_CHAPTER == 0:
        for k, v in CHAPTER_CHEST.items():
            rewards[k] = rewards.get(k, 0) + v
    return rewards


def battle_rewards(stage: int) -> Dict[str, int]:
    return {"gold": int(60 * (20 + 4 * stage) / 10), "essence": int(60 * (5 + 1.2 * stage) / 10)}


def fight_campaign(p: dict, user_id: int, ts: float) -> Tuple[BattleResult, Dict[str, int], int]:
    stage = p["stage"] + 1
    if stage > MAX_STAGE:
        raise GameError("You've cleared every chapter available. More are on the way!")
    attackers = team_snapshots(p, "campaign")
    if not any(attackers):
        raise GameError("Your campaign team is empty. Set one up with the Team button.")
    defenders = stage_enemies(stage)
    p["battles"] += 1
    battle_id = f"{user_id}-{p['battles']}-{stage}"
    seed = seed_from_id(battle_id)
    result = simulate(attackers, defenders, seed)
    p["last_battle"] = {
        "id": battle_id,
        "seed": seed,
        "label": f"Stage {stage_label(stage)}",
        "attackers": attackers,
        "defenders": defenders,
        "win": result.win,
    }
    quest_progress(p, "fight", ts=ts)
    rewards: Dict[str, int] = {}
    if result.win:
        p["stage"] = stage
        rewards = battle_rewards(stage)
        for k, v in first_clear_rewards(stage).items():
            rewards[k] = rewards.get(k, 0) + v
        add_resources(p, rewards)
    return result, rewards, stage


def replay(last_battle: dict) -> BattleResult:
    return simulate(last_battle["attackers"], last_battle["defenders"], last_battle["seed"], log=True)


def loss_hint(result: BattleResult, attackers: List[Optional[dict]], defenders: List[Optional[dict]]) -> str:
    ratio = team_power(attackers) / max(1, team_power(defenders))
    if ratio < 0.6:
        return f"Your team is about {1 - ratio:.0%} weaker than this stage. Level up or ascend your heroes."
    if result.front_fell_tick is not None and result.front_fell_tick < 200:
        front_roles = [a["role"] for a in attackers[:2] if a]
        seconds = max(1, result.front_fell_tick // 10)
        if "tank" not in front_roles:
            return f"Your front line fell in {seconds}s. Try a Tank in slot 1."
        return f"Your front line fell in {seconds}s. A Support in the back line could keep it standing."
    if result.timed_out:
        return "Time ran out. Bring more damage, like a Mage or Ranger in the back line."
    mine = [a["faction"] for a in attackers if a]
    theirs = [d["faction"] for d in defenders if d]
    countered = sum(1 for m in mine for t in theirs if counters(t, m))
    if mine and countered > len(mine) * len(theirs) / 3:
        return "The enemy counters most of your heroes. Swap in heroes from a faction that beats theirs."
    if ratio < 0.85:
        return f"Your team is about {1 - ratio:.0%} weaker than this stage. Level up or ascend your heroes."
    return "Close fight! Try a different formation or adjust your ultimate rules."
