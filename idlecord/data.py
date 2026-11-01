"""Static game content for IdleCord: factions, tiers, heroes and tuning constants."""

# ---------------------------------------------------------------- factions

FACTIONS = {
    "dawnguard": {"name": "Dawnguard", "emoji": "🌅"},
    "ironclad": {"name": "Ironclad", "emoji": "⚙️"},
    "wildkin": {"name": "Wildkin", "emoji": "🌿"},
    "hollow": {"name": "Hollow", "emoji": "🌑"},
    "radiant": {"name": "Radiant", "emoji": "✨"},
    "abyssal": {"name": "Abyssal", "emoji": "🕳️"},
}
CORE_FACTIONS = ["dawnguard", "ironclad", "wildkin", "hollow"]
SPECIAL_FACTIONS = ["radiant", "abyssal"]

# attacker -> faction it beats
COUNTERS = {
    "dawnguard": "ironclad",
    "ironclad": "wildkin",
    "wildkin": "hollow",
    "hollow": "dawnguard",
    "radiant": "abyssal",
    "abyssal": "radiant",
}
COUNTER_DAMAGE = 1.2
COUNTER_ACCURACY = 15

# (min heroes of top faction, min of second faction, bonus)
TEAM_BONUSES = [
    (5, 0, 0.20),
    (4, 0, 0.15),
    (3, 2, 0.12),
    (3, 0, 0.08),
]

CLASSES = {
    "might": {"name": "Might", "emoji": "🛡️"},
    "agility": {"name": "Agility", "emoji": "🏹"},
    "intellect": {"name": "Intellect", "emoji": "🔮"},
}

ROLES = {
    "tank": {"name": "Tank", "emoji": "🧱"},
    "warrior": {"name": "Warrior", "emoji": "⚔️"},
    "ranger": {"name": "Ranger", "emoji": "🎯"},
    "mage": {"name": "Mage", "emoji": "🔥"},
    "support": {"name": "Support", "emoji": "💚"},
}

# Level-1 stats of an Elite hero, by role.
ROLE_BASE_STATS = {
    "tank": {"hp": 1500, "atk": 70, "def": 70, "spd": 90},
    "warrior": {"hp": 1150, "atk": 105, "def": 45, "spd": 100},
    "ranger": {"hp": 900, "atk": 120, "def": 30, "spd": 110},
    "mage": {"hp": 850, "atk": 130, "def": 28, "spd": 95},
    "support": {"hp": 950, "atk": 90, "def": 35, "spd": 100},
}
BASE_SECONDARY = {
    "crit": 0.08,
    "critdmg": 1.5,
    "acc": 0,
    "dodge": 0,
    "haste": 0,
    "energy": 1.0,
    "skill": 1.0,
}

# ---------------------------------------------------------------- rarity & tiers

RARITIES = {
    "common": {"name": "Common", "emoji": "⚪", "stat_mult": 0.5, "level_cap": 100, "max_tier": 2},
    "rare": {"name": "Rare", "emoji": "🔵", "stat_mult": 0.65, "level_cap": 160, "max_tier": 3},
    "elite": {"name": "Elite", "emoji": "🟣", "stat_mult": 1.0, "level_cap": 240, "max_tier": 6},
}

# Shared ascension ladder. Common heroes stop at Legendary, Rare at Legendary+.
TIERS = [
    {"name": "Elite", "cap": 100, "mult": 1.00},
    {"name": "Elite+", "cap": 120, "mult": 1.10},
    {"name": "Legendary", "cap": 140, "mult": 1.25},
    {"name": "Legendary+", "cap": 160, "mult": 1.40},
    {"name": "Mythic", "cap": 180, "mult": 1.60},
    {"name": "Mythic+", "cap": 200, "mult": 1.80},
    {"name": "Ascended", "cap": 240, "mult": 2.10},
]
# MVP stops at Mythic+ (roadmap phase 1).
MAX_TIER = 5

# Cost to leave tier N: (count, fodder tier, same hero?)
ASCENSION_COSTS = {
    0: (1, 0, True),
    1: (2, 1, False),
    2: (1, 1, True),
    3: (2, 3, False),
    4: (1, 4, False),
    5: (2, 1, True),
}

# Skills unlock by tier: s2 at Legendary, passive at Mythic.
# Skill multipliers grow +10% at Legendary+ and again at Mythic+.
S2_UNLOCK_TIER = 2
PASSIVE_UNLOCK_TIER = 4
SKILL_UPGRADE_TIERS = (3, 5)

# ---------------------------------------------------------------- economy

IDLE_CAP_MINUTES = 720
ITEM_ROLL_MINUTES = 30
GEM_TRICKLE_PER_MIN = 0.07
FAST_REWARD_MINUTES = 120
FAST_REWARD_FREE = 2
FAST_REWARD_GEM_COSTS = [50, 80, 100]

SUMMON_GEM_COST = 300
SUMMON_RATES = {"elite": 0.05, "rare": 0.45, "common": 0.50}
SUMMON_PITY = 30
WISHLIST_SIZE = 5
WISHLIST_CHANCE = 0.60
BIG_SPEND_CONFIRM = 3000
SCROLL_FRAGMENTS_PER_SCROLL = 10

STAGES_PER_CHAPTER = 40
MAX_CHAPTERS = 3
MAX_STAGE = STAGES_PER_CHAPTER * MAX_CHAPTERS
FIRST_CLEAR_GEMS = 20
BOSS_CLEAR_GEMS = 100
CHAPTER_CHEST = {"scrolls": 5, "gems": 300}

STARTING_RESOURCES = {
    "gold": 5000,
    "essence": 1500,
    "gems": 600,
    "scrolls": 10,
    "scroll_frags": 0,
    "forge_ore": 0,
}

RESOURCE_EMOJI = {
    "gold": "🪙",
    "essence": "🧪",
    "gems": "💎",
    "scrolls": "📜",
    "scroll_frags": "🧩",
    "forge_ore": "⛏️",
}
RESOURCE_NAMES = {
    "gold": "Gold",
    "essence": "Essence",
    "gems": "Gems",
    "scrolls": "Summon Scrolls",
    "scroll_frags": "Scroll Fragments",
    "forge_ore": "Forge Ore",
}

DAILY_QUESTS = {
    "collect": {"name": "Claim idle loot", "goal": 1, "reward": {"gems": 50}},
    "fight": {"name": "Fight 3 battles", "goal": 3, "reward": {"scrolls": 1}},
    "summon": {"name": "Summon a hero", "goal": 1, "reward": {"gems": 100}},
    "fast": {"name": "Use a Fast Reward", "goal": 1, "reward": {"gold": 5000}},
}
DAILY_BONUS = {"scrolls": 1}

# ---------------------------------------------------------------- combat

TICKS_PER_SEC = 10
MAX_TICKS = 900
BASE_ATTACK_TICKS = 15
ULT_TIMEOUT_TICKS = 100
ENERGY_MAX = 1000
ENERGY_PER_ATTACK = 200
ENERGY_PER_PCT_LOST = 10
FRONT_SLOTS = (0, 1)
BACK_SLOTS = (2, 3, 4)

# value -> label, shown in the ult-rule picker
ULT_RULES = {
    "immediate": "Immediately",
    "enemies:3": "When 3+ enemies are alive",
    "enemies:4": "When 4+ enemies are alive",
    "enemies:5": "When all 5 enemies are alive",
    "ally:70": "When an ally drops below 70% HP",
    "ally:50": "When an ally drops below 50% HP",
    "ally:30": "When an ally drops below 30% HP",
    "boss:50": "When the enemy boss is below 50% HP",
    "boss:30": "When the enemy boss is below 30% HP",
    "after:0": "Right after slot 1's ultimate",
    "after:1": "Right after slot 2's ultimate",
    "after:2": "Right after slot 3's ultimate",
    "after:3": "Right after slot 4's ultimate",
    "after:4": "Right after slot 5's ultimate",
}

# ---------------------------------------------------------------- skill helpers


def _dmg(target, mult, **extra):
    return {"kind": "dmg", "target": target, "mult": mult, **extra}


def _heal(target, mult):
    return {"kind": "heal", "target": target, "mult": mult}


def _shield(target, mult, dur):
    return {"kind": "shield", "target": target, "mult": mult, "dur": dur}


def _buff(target, stat, amt, dur):
    return {"kind": "buff", "target": target, "stat": stat, "amt": amt, "dur": dur}


def _taunt(dur):
    return {"kind": "taunt", "dur": dur}


def _energy(target, amt):
    return {"kind": "energy", "target": target, "amt": amt}


def _skill(name, desc, effects, cd=None):
    return {"name": name, "desc": desc, "cd": cd, "effects": effects}


def _passive(name, desc, stats):
    return {"name": name, "desc": desc, "stats": stats}


# ---------------------------------------------------------------- heroes

HEROES = {
    # ---- Dawnguard
    "aurelia": {
        "name": "Aurelia", "faction": "dawnguard", "cls": "might", "role": "tank", "rarity": "elite",
        "passive": _passive("Sunwall", "+15% HP, +10% DEF.", {"hp": 0.15, "def": 0.10}),
        "s1": _skill("Shield of Dawn", "Taunts for 3s and shields herself.", [_taunt(3), _shield("self", 2.0, 4)], cd=9),
        "s2": _skill("Judgment", "Smites an enemy and stuns it for 1.5s.", [_dmg("single", 1.6, stun=1.5)], cd=12),
        "ult": _skill("Bastion of Light", "Shields all allies for 6s.", [_shield("allies", 1.8, 6)]),
    },
    "seren": {
        "name": "Seren", "faction": "dawnguard", "cls": "intellect", "role": "mage", "rarity": "elite",
        "passive": _passive("Clarity", "+15% energy gain, +10% ATK.", {"energy": 0.15, "atk": 0.10}),
        "s1": _skill("Sunlance", "Burns the enemy back line.", [_dmg("back", 1.3)], cd=7),
        "s2": _skill("Flare", "Blasts the weakest enemy.", [_dmg("lowest", 2.2)], cd=11),
        "ult": _skill("Starfall", "Rains light on every enemy.", [_dmg("all", 2.4)]),
    },
    "cassius": {
        "name": "Cassius", "faction": "dawnguard", "cls": "might", "role": "warrior", "rarity": "elite",
        "passive": _passive("Zeal", "+12% ATK, +8% HP.", {"atk": 0.12, "hp": 0.08}),
        "s1": _skill("Crusader Strike", "A heavy strike that heals for 30% of damage.", [_dmg("single", 1.8, lifesteal=0.3)], cd=6),
        "s2": _skill("Rallying Cry", "Allies gain +15% ATK for 5s.", [_buff("allies", "atk", 0.15, 5)], cd=14),
        "ult": _skill("Dawnbreaker", "Cleaves the front line and stuns it for 1s.", [_dmg("front", 3.0, stun=1)]),
    },
    "lumi": {
        "name": "Lumi", "faction": "dawnguard", "cls": "intellect", "role": "support", "rarity": "elite",
        "passive": _passive("Gentle Light", "+20 Haste, +10% HP.", {"haste": 20, "hp": 0.10}),
        "s1": _skill("Mend", "Heals the most wounded ally.", [_heal("lowest_ally", 2.2)], cd=6),
        "s2": _skill("Blessing", "Allies gain +20% Speed for 5s.", [_buff("allies", "spd", 0.2, 5)], cd=13),
        "ult": _skill("Sanctuary", "Heals and shields all allies.", [_heal("allies", 2.0), _shield("allies", 1.0, 4)]),
    },
    # ---- Ironclad
    "korrak": {
        "name": "Korrak", "faction": "ironclad", "cls": "might", "role": "tank", "rarity": "elite",
        "passive": _passive("Riveted Plate", "+25% DEF.", {"def": 0.25}),
        "s1": _skill("Shield Bash", "Bashes an enemy, stunning it for 1.5s.", [_dmg("single", 1.2, stun=1.5)], cd=8),
        "s2": _skill("Iron Will", "Taunts for 3s and gains +40% DEF.", [_taunt(3), _buff("self", "def", 0.4, 4)], cd=12),
        "ult": _skill("Steam Vent", "Scalds the front line and shields himself.", [_dmg("front", 1.8), _shield("self", 3.0, 6)]),
    },
    "vess": {
        "name": "Vess", "faction": "ironclad", "cls": "agility", "role": "ranger", "rarity": "elite",
        "passive": _passive("Deadeye", "+15% crit chance, +10 Accuracy.", {"crit": 0.15, "acc": 10}),
        "s1": _skill("Piercing Bolt", "Pierces armor, lowering DEF by 20% for 4s.", [_dmg("single", 2.0, shred=(0.2, 4))], cd=7),
        "s2": _skill("Rapid Fire", "+50% Speed for 4s.", [_buff("self", "spd", 0.5, 4)], cd=12),
        "ult": _skill("Railshot", "Snipes the enemy with the highest ATK.", [_dmg("highest_atk", 4.0)]),
    },
    "odo": {
        "name": "Odo", "faction": "ironclad", "cls": "intellect", "role": "support", "rarity": "elite",
        "passive": _passive("Tinker", "+15 Haste, +10% DEF.", {"haste": 15, "def": 0.10}),
        "s1": _skill("Repair Drone", "Heals and shields the most wounded ally.", [_heal("lowest_ally", 1.8), _shield("lowest_ally", 1.0, 3)], cd=7),
        "s2": _skill("Overclock", "Grants all allies 150 energy.", [_energy("allies", 150)], cd=15),
        "ult": _skill("Field Workshop", "Shields all allies for 6s.", [_shield("allies", 2.2, 6)]),
    },
    "brakka": {
        "name": "Brakka", "faction": "ironclad", "cls": "might", "role": "warrior", "rarity": "elite",
        "passive": _passive("Pistons", "+10% HP, +10% ATK.", {"hp": 0.10, "atk": 0.10}),
        "s1": _skill("Hammerfall", "Slams the front line.", [_dmg("front", 1.3)], cd=7),
        "s2": _skill("Gear Grind", "Lowers an enemy's DEF by 25% for 5s.", [_dmg("single", 1.6, shred=(0.25, 5))], cd=11),
        "ult": _skill("Pile Driver", "Crushes an enemy and stuns it for 2s.", [_dmg("single", 4.5, stun=2)]),
    },
    # ---- Wildkin
    "bramble": {
        "name": "Bramble", "faction": "wildkin", "cls": "might", "role": "tank", "rarity": "elite",
        "passive": _passive("Thick Bark", "+20% HP.", {"hp": 0.20}),
        "s1": _skill("Thorn Hide", "Taunts for 3s and heals himself.", [_taunt(3), _heal("self", 1.5)], cd=9),
        "s2": _skill("Root Snare", "Roots the back line, stunning it for 1s.", [_dmg("back", 0.8, stun=1)], cd=13),
        "ult": _skill("Ancient Grove", "Heals allies and grants +30% DEF for 6s.", [_heal("allies", 1.5), _buff("allies", "def", 0.3, 6)]),
    },
    "thistle": {
        "name": "Thistle", "faction": "wildkin", "cls": "agility", "role": "ranger", "rarity": "elite",
        "passive": _passive("Swift Feet", "+15% Speed, +10 Dodge.", {"spd": 0.15, "dodge": 10}),
        "s1": _skill("Barbed Arrow", "A precise shot.", [_dmg("single", 1.7)], cd=6),
        "s2": _skill("Volley", "Fires at 3 random enemies.", [_dmg("random:3", 1.1)], cd=10),
        "ult": _skill("Hunter's Moon", "+50% ATK for 6s, then shoots the weakest enemy.", [_buff("self", "atk", 0.5, 6), _dmg("lowest", 3.0)]),
    },
    "fenna": {
        "name": "Fenna", "faction": "wildkin", "cls": "intellect", "role": "support", "rarity": "elite",
        "passive": _passive("Bloom", "+10% HP, +10% energy gain.", {"hp": 0.10, "energy": 0.10}),
        "s1": _skill("Sap of Life", "Heals all allies a little.", [_heal("allies", 0.9)], cd=7),
        "s2": _skill("Wild Growth", "Allies gain +12% ATK for 6s.", [_buff("allies", "atk", 0.12, 6)], cd=14),
        "ult": _skill("Spring Rite", "A large heal on all allies.", [_heal("allies", 3.0)]),
    },
    "tarrow": {
        "name": "Tarrow", "faction": "wildkin", "cls": "agility", "role": "warrior", "rarity": "elite",
        "passive": _passive("Pack Instinct", "+10% crit chance, +8% ATK.", {"crit": 0.10, "atk": 0.08}),
        "s1": _skill("Maul", "Mauls an enemy, healing for 20% of damage.", [_dmg("single", 1.6, lifesteal=0.2)], cd=6),
        "s2": _skill("Pounce", "Leaps on the weakest enemy.", [_dmg("lowest", 1.8)], cd=10),
        "ult": _skill("Primal Frenzy", "Five savage hits on random enemies.", [_dmg("random:5", 1.4)]),
    },
    # ---- Hollow
    "morwen": {
        "name": "Morwen", "faction": "hollow", "cls": "intellect", "role": "mage", "rarity": "elite",
        "passive": _passive("Grave Whisper", "+15% ATK.", {"atk": 0.15}),
        "s1": _skill("Soul Siphon", "Drains an enemy, healing for 50% of damage.", [_dmg("single", 1.5, lifesteal=0.5)], cd=7),
        "s2": _skill("Wither", "Withers all enemies, lowering DEF by 15% for 5s.", [_dmg("all", 0.7, shred=(0.15, 5))], cd=12),
        "ult": _skill("Night's Embrace", "Engulfs the back line and stuns it for 1.5s.", [_dmg("back", 2.6, stun=1.5)]),
    },
    "skarn": {
        "name": "Skarn", "faction": "hollow", "cls": "agility", "role": "warrior", "rarity": "elite",
        "passive": _passive("Shadowstep", "+15 Dodge, +10% crit chance.", {"dodge": 15, "crit": 0.10}),
        "s1": _skill("Backstab", "Strikes a back-line enemy.", [_dmg("back_single", 2.0)], cd=7),
        "s2": _skill("Fade", "+30 Dodge for 4s.", [_buff("self", "dodge", 30, 4)], cd=13),
        "ult": _skill("Eclipse Blade", "A lethal blow to a back-line enemy.", [_dmg("back_single", 4.2)]),
    },
    "grieve": {
        "name": "Grieve", "faction": "hollow", "cls": "might", "role": "tank", "rarity": "elite",
        "passive": _passive("Undying", "+15% HP, +10% DEF.", {"hp": 0.15, "def": 0.10}),
        "s1": _skill("Dread Taunt", "Taunts for 3s and lashes the front line.", [_taunt(3), _dmg("front", 0.8)], cd=9),
        "s2": _skill("Bone Armor", "Shields himself for 5s.", [_shield("self", 2.5, 5)], cd=12),
        "ult": _skill("Grasp of the Hollow", "Grips every enemy, stunning them for 1s.", [_dmg("all", 1.2, stun=1)]),
    },
    # ---- Rare fodder
    "dawn_cleric": {
        "name": "Dawn Cleric", "faction": "dawnguard", "cls": "intellect", "role": "support", "rarity": "rare",
        "s1": _skill("Prayer", "Heals the most wounded ally.", [_heal("lowest_ally", 1.6)], cd=8),
        "ult": _skill("Hymn", "Heals all allies.", [_heal("allies", 1.4)]),
    },
    "iron_gunner": {
        "name": "Iron Gunner", "faction": "ironclad", "cls": "agility", "role": "ranger", "rarity": "rare",
        "s1": _skill("Aimed Shot", "A careful shot.", [_dmg("single", 1.6)], cd=7),
        "ult": _skill("Headshot", "Snipes the enemy with the highest ATK.", [_dmg("highest_atk", 2.8)]),
    },
    "wild_warden": {
        "name": "Wild Warden", "faction": "wildkin", "cls": "might", "role": "tank", "rarity": "rare",
        "s1": _skill("Stand Firm", "Taunts for 3s and heals himself.", [_taunt(3), _heal("self", 1.0)], cd=10),
        "ult": _skill("Barkskin", "Shields all allies.", [_shield("allies", 1.0, 5)]),
    },
    "hollow_reaver": {
        "name": "Hollow Reaver", "faction": "hollow", "cls": "agility", "role": "warrior", "rarity": "rare",
        "s1": _skill("Reap", "Heals for 30% of damage dealt.", [_dmg("single", 1.5, lifesteal=0.3)], cd=7),
        "ult": _skill("Harvest", "Cleaves the front line.", [_dmg("front", 2.0)]),
    },
    # ---- Common fodder
    "dawn_recruit": {
        "name": "Dawn Recruit", "faction": "dawnguard", "cls": "might", "role": "warrior", "rarity": "common",
        "s1": _skill("Slash", "A basic slash.", [_dmg("single", 1.3)], cd=7),
        "ult": _skill("Charge", "A running strike.", [_dmg("single", 2.5)]),
    },
    "iron_conscript": {
        "name": "Iron Conscript", "faction": "ironclad", "cls": "might", "role": "tank", "rarity": "common",
        "s1": _skill("Hold the Line", "Taunts for 2s.", [_taunt(2)], cd=10),
        "ult": _skill("Brace", "Shields himself.", [_shield("self", 2.0, 5)]),
    },
    "wild_scout": {
        "name": "Wild Scout", "faction": "wildkin", "cls": "agility", "role": "ranger", "rarity": "common",
        "s1": _skill("Quick Shot", "A fast shot.", [_dmg("single", 1.4)], cd=7),
        "ult": _skill("Twin Arrows", "Shoots 2 random enemies.", [_dmg("random:2", 1.6)]),
    },
    "hollow_thrall": {
        "name": "Hollow Thrall", "faction": "hollow", "cls": "intellect", "role": "mage", "rarity": "common",
        "s1": _skill("Hex", "Curses the back line.", [_dmg("back", 0.9)], cd=9),
        "ult": _skill("Dark Pulse", "Hits every enemy.", [_dmg("all", 1.2)]),
    },
}

STARTERS = ["aurelia", "vess", "thistle", "morwen"]
STARTER_FODDER = ["dawn_recruit", "iron_conscript", "wild_scout", "hollow_thrall"]


def heroes_of(rarity: str) -> list:
    return [hid for hid, h in HEROES.items() if h["rarity"] == rarity]
