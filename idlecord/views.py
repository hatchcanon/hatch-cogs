"""Components V2 views for IdleCord.

Every screen is a ``LayoutView`` that rebuilds itself from the player dict in
``build()``. Buttons and selects hand off to a method on the view, and screens
switch by editing the same message with a new view.
"""

import contextlib
import random
from typing import Callable, List, Optional

import discord
from red_commons.logging import getLogger
from redbot.core.utils.chat_formatting import humanize_number

from . import game
from .combat import team_bonus
from .data import (
    CLASSES,
    COUNTERS,
    DAILY_BONUS,
    DAILY_QUESTS,
    FACTIONS,
    FAST_REWARD_FREE,
    HEROES,
    IDLE_CAP_MINUTES,
    PASSIVE_UNLOCK_TIER,
    RARITIES,
    RESOURCE_EMOJI,
    ROLES,
    S2_UNLOCK_TIER,
    STAGES_PER_CHAPTER,
    STARTERS,
    SUMMON_GEM_COST,
    SUMMON_PITY,
    SUMMON_RATES,
    TIERS,
    ULT_RULES,
    WISHLIST_CHANCE,
    WISHLIST_SIZE,
    heroes_of,
)
from .game import GameError

log = getLogger("red.hatch.idlecord.views")

VIEW_TIMEOUT = 600
ACCENT = discord.Color.from_rgb(240, 170, 60)
WIN_ACCENT = discord.Color.green()
LOSS_ACCENT = discord.Color.red()
HEROES_PER_PAGE = 10
TEAM_OPTIONS_PER_PAGE = 24
REPLAY_LINES_PER_PAGE = 15


# ---------------------------------------------------------------- formatting


def fmt_loot(loot: dict) -> str:
    if not loot:
        return "nothing"
    return " · ".join(f"{RESOURCE_EMOJI.get(k, '')} {humanize_number(v)}" for k, v in loot.items() if v)


def fmt_wallet(p: dict) -> str:
    keys = ("gold", "essence", "gems", "scrolls")
    return " · ".join(f"{RESOURCE_EMOJI[k]} {humanize_number(p['res'].get(k, 0))}" for k in keys)


def bar(value: float, top: float, length: int = 10) -> str:
    filled = round(value / top * length) if top else 0
    return "█" * max(0, filled) or "▏"


def hero_line(p: dict, iid: str, locked: set) -> str:
    inst = p["heroes"][iid]
    d = HEROES[inst["hid"]]
    role = ROLES[d["role"]]
    team = " · 🔒 in team" if iid in locked else ""
    return (
        f"{FACTIONS[d['faction']]['emoji']} **{d['name']}** {RARITIES[d['rarity']]['emoji']} "
        f"{TIERS[inst['tier']]['name']} Lv.{inst['level']}\n"
        f"-# {role['emoji']} {role['name']} · ⚡ {humanize_number(game.hero_power(inst))}{team}"
    )


def enemy_line(snap: Optional[dict]) -> str:
    if not snap:
        return "—"
    return f"{FACTIONS[snap['faction']]['emoji']} {snap['name']} Lv.{snap['level']}"


# ---------------------------------------------------------------- base components


class Btn(discord.ui.Button):
    """A button that hands its click to ``handler(interaction)``."""

    def __init__(self, handler: Callable, **kwargs):
        super().__init__(**kwargs)
        self.handler = handler

    async def callback(self, interaction: discord.Interaction):
        await self.view.run_action(interaction, self.handler)


class Pick(discord.ui.Select):
    """A select menu that hands its values to ``handler(interaction, values)``."""

    def __init__(self, handler: Callable, **kwargs):
        super().__init__(**kwargs)
        self.handler = handler

    async def callback(self, interaction: discord.Interaction):
        values = list(self.values)
        await self.view.run_action(interaction, lambda i: self.handler(i, values))


class IdleView(discord.ui.LayoutView):
    """Base for every IdleCord screen."""

    screen: str = ""

    def __init__(self, cog, user: discord.abc.User, notice: Optional[str] = None):
        super().__init__(timeout=VIEW_TIMEOUT)
        self.cog = cog
        self.user = user
        self.message: Optional[discord.Message] = None
        self.notice = notice
        self._busy = False

    # -- building

    def build(self, p: dict):
        raise NotImplementedError

    def render(self, p: dict) -> "IdleView":
        self.clear_items()
        self.build(p)
        return self

    def notice_items(self) -> list:
        if not self.notice:
            return []
        return [discord.ui.TextDisplay(f"-# {self.notice}")]

    def nav_row(self) -> discord.ui.ActionRow:
        row = discord.ui.ActionRow()
        for screen, label, emoji, target in (
            ("daily", "Daily", "🎁", DailyView),
            ("campaign", "Campaign", "⚔️", CampaignView),
            ("team", "Team", "🛡️", TeamView),
            ("summon", "Summon", "📜", SummonView),
            ("heroes", "Heroes", "🦸", HeroesView),
        ):
            current = screen == self.screen
            row.add_item(
                Btn(
                    lambda i, t=target: self.switch(i, t),
                    label=label,
                    emoji=emoji,
                    style=discord.ButtonStyle.primary if current else discord.ButtonStyle.secondary,
                    disabled=current,
                )
            )
        return row

    # -- actions

    async def run_action(self, interaction: discord.Interaction, handler: Callable):
        # A double-tap lands while the first click is still running: drop it.
        if self._busy:
            with contextlib.suppress(discord.HTTPException):
                await interaction.response.defer()
            return
        self._busy = True
        try:
            await handler(interaction)
        except GameError as e:
            await self.reply_error(interaction, str(e))
        except Exception:
            log.exception("IdleCord action failed")
            await self.reply_error(interaction, "Something went wrong. Please try again.")
        finally:
            self._busy = False

    async def reply_error(self, interaction: discord.Interaction, text: str):
        view = text_view(f"⚠️ {text}", LOSS_ACCENT)
        if interaction.response.is_done():
            await interaction.followup.send(view=view, ephemeral=True)
        else:
            await interaction.response.send_message(view=view, ephemeral=True)

    async def refresh(self, interaction: discord.Interaction, p: Optional[dict] = None):
        if p is None:
            p = await self.cog.get_player(self.user)
        self.render(p)
        await interaction.response.edit_message(view=self)

    async def switch(self, interaction: discord.Interaction, view_cls, **kwargs):
        p = await self.cog.get_player(self.user)
        view = view_cls(self.cog, self.user, **kwargs)
        view.message = self.message
        view.render(p)
        self.stop()
        await interaction.response.edit_message(view=view)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user.id:
            await interaction.response.send_message(
                "This isn't your game. Start your own with `/idlecord start`.", ephemeral=True
            )
            return False
        return True

    async def on_timeout(self):
        for item in self.walk_children():
            if hasattr(item, "disabled"):
                item.disabled = True
        if self.message:
            with contextlib.suppress(discord.HTTPException):
                await self.message.edit(view=self)


def text_view(text: str, accent: discord.Color = ACCENT) -> discord.ui.LayoutView:
    view = discord.ui.LayoutView(timeout=None)
    view.add_item(discord.ui.Container(discord.ui.TextDisplay(text), accent_color=accent))
    return view


# ---------------------------------------------------------------- start


class StartView(IdleView):
    screen = "start"

    def build(self, p):
        items: list = [
            discord.ui.TextDisplay(
                "## 🌅 Welcome to IdleCord\n"
                "Collect heroes, build a team of five and push through the campaign. "
                "Fights run on their own, and your idle chest fills while you're away.\n\n"
                "**Pick your starter hero.** Each one leads a different faction."
            ),
            discord.ui.Separator(),
        ]
        for hid in STARTERS:
            d = HEROES[hid]
            text = (
                f"{FACTIONS[d['faction']]['emoji']} **{d['name']}** — {FACTIONS[d['faction']]['name']} "
                f"{ROLES[d['role']]['name']}\n-# {d['ult']['name']}: {d['ult']['desc']}"
            )
            items.append(
                discord.ui.Section(
                    discord.ui.TextDisplay(text),
                    accessory=Btn(
                        lambda i, h=hid: self.choose(i, h),
                        label="Choose",
                        style=discord.ButtonStyle.success,
                    ),
                )
            )
        items.append(discord.ui.Separator())
        items.append(
            discord.ui.TextDisplay(
                "-# Faction wheel: 🌅 Dawnguard → ⚙️ Ironclad → 🌿 Wildkin → 🌑 Hollow → 🌅 Dawnguard. "
                "Each one deals +20% damage to the next."
            )
        )
        self.add_item(discord.ui.Container(*items, accent_color=ACCENT))

    async def choose(self, interaction: discord.Interaction, hid: str):
        p = await self.cog.create_player(self.user, hid)
        name = HEROES[hid]["name"]
        view = CampaignView(
            self.cog,
            self.user,
            notice=f"{name} joins you, along with four recruits. The first three stages are a tutorial. Hit Fight!",
        )
        view.message = self.message
        view.render(p)
        self.stop()
        await interaction.response.edit_message(view=view)


# ---------------------------------------------------------------- daily


class DailyView(IdleView):
    screen = "daily"

    def build(self, p):
        ts = game.now_ts()
        game.ensure_daily(p, ts)
        minutes = game.idle_minutes(p, ts)
        rates = game.idle_rates(p["stage"])
        full_at = game.chest_full_at(p)
        status = "**full!**" if minutes >= IDLE_CAP_MINUTES else f"full <t:{full_at}:R>"
        chest = (
            f"### 🎁 Idle Chest\n"
            f"{int(minutes // 60)}h {int(minutes % 60)}m stored · {status}\n"
            f"-# {RESOURCE_EMOJI['gold']} {humanize_number(int(rates['gold']))}/min · "
            f"{RESOURCE_EMOJI['essence']} {humanize_number(int(rates['essence']))}/min · "
            f"item drop every 30 min"
        )
        fast_cost = game.fast_reward_cost(p, ts)
        free_left = max(0, FAST_REWARD_FREE - p["daily"]["fast_used"])
        if fast_cost is None:
            fast_note, fast_label = "None left today.", "Used up"
        elif fast_cost == 0:
            fast_note, fast_label = f"{free_left}/{FAST_REWARD_FREE} free left today.", "Use (free)"
        else:
            fast_note, fast_label = f"Next one costs {fast_cost} Gems.", f"Use ({fast_cost} 💎)"
        fast = f"### ⚡ Fast Reward\nInstantly collect 2 hours of idle loot.\n-# {fast_note}"

        daily = p["daily"]
        quest_lines = []
        for qid, q in DAILY_QUESTS.items():
            prog = min(daily["progress"].get(qid, 0), q["goal"])
            if qid in daily["claimed"]:
                mark = "✅"
            elif prog >= q["goal"]:
                mark = "🎉"
            else:
                mark = "▫️"
            quest_lines.append(f"{mark} {q['name']} ({prog}/{q['goal']}) — {fmt_loot(q['reward'])}")
        bonus = "✅" if daily["bonus"] else "▫️"
        quest_lines.append(f"{bonus} Finish all quests — {fmt_loot(DAILY_BONUS)}")
        quests = "### 📋 Daily Quests\n" + "\n".join(quest_lines) + f"\n-# Resets <t:{game.next_reset_ts(ts)}:R>"

        items: list = [
            discord.ui.TextDisplay(f"## 🎁 Daily Panel\n{fmt_wallet(p)}"),
            discord.ui.Separator(),
            discord.ui.Section(
                discord.ui.TextDisplay(chest),
                accessory=Btn(
                    self.claim, label="Claim", emoji="🎁", style=discord.ButtonStyle.success, disabled=minutes < 1
                ),
            ),
            discord.ui.Section(
                discord.ui.TextDisplay(fast),
                accessory=Btn(
                    self.fast,
                    label=fast_label,
                    style=discord.ButtonStyle.primary,
                    disabled=fast_cost is None,
                ),
            ),
            discord.ui.Section(
                discord.ui.TextDisplay(quests),
                accessory=Btn(
                    self.quests,
                    label="Claim quests",
                    style=discord.ButtonStyle.success,
                    disabled=not game.claimable_quests(p, ts),
                ),
            ),
            *self.notice_items(),
            discord.ui.Separator(),
            self.nav_row(),
        ]
        self.add_item(discord.ui.Container(*items, accent_color=ACCENT))

    async def claim(self, interaction: discord.Interaction):
        async with self.cog.player(self.user) as p:
            loot = game.claim_idle(p, game.now_ts(), random.Random())
        self.notice = f"Claimed {fmt_loot(loot)}"
        await self.refresh(interaction, p)

    async def fast(self, interaction: discord.Interaction):
        async with self.cog.player(self.user) as p:
            loot, cost = game.use_fast_reward(p, game.now_ts(), random.Random())
        spent = f" for {cost} 💎" if cost else ""
        self.notice = f"Fast Reward{spent}: {fmt_loot(loot)}"
        await self.refresh(interaction, p)

    async def quests(self, interaction: discord.Interaction):
        async with self.cog.player(self.user) as p:
            rewards = game.claim_quests(p, game.now_ts())
        self.notice = f"Quest rewards: {fmt_loot(rewards)}"
        await self.refresh(interaction, p)


# ---------------------------------------------------------------- campaign


class CampaignView(IdleView):
    screen = "campaign"

    def __init__(self, cog, user, notice: Optional[str] = None):
        super().__init__(cog, user, notice)
        self.result = None

    def build(self, p):
        if self.result:
            self._build_result(p)
        else:
            self._build_stage(p)

    def _build_stage(self, p):
        stage = p["stage"] + 1
        if stage > game.MAX_STAGE:
            body = "## ⚔️ Campaign\nYou've cleared every available chapter. More are coming soon!"
            self.add_item(
                discord.ui.Container(discord.ui.TextDisplay(body), discord.ui.Separator(), self.nav_row())
            )
            return
        enemies = game.stage_enemies(stage)
        mine = game.team_snapshots(p, "campaign")
        boss = " · 👑 **Boss stage**" if game.is_boss_stage(stage) else ""
        chapter_end = " · 🎁 Chapter chest" if stage % STAGES_PER_CHAPTER == 0 else ""
        ours, theirs = game.team_power(mine), game.team_power(enemies)
        if ours >= theirs * 1.1:
            verdict = "🟢 Favored"
        elif ours >= theirs * 0.9:
            verdict = "🟡 Even"
        else:
            verdict = "🔴 Tough"
        lineup = (
            "**Enemy front:** " + " · ".join(enemy_line(e) for e in enemies[:2] if e) + "\n"
            "**Enemy back:** " + (" · ".join(enemy_line(e) for e in enemies[2:] if e) or "—")
        )
        rewards = game.first_clear_rewards(stage)
        rate = game.idle_rates(p["stage"])["gold"]
        body = (
            f"## ⚔️ Stage {game.stage_label(stage)}{boss}{chapter_end}\n"
            f"{lineup}\n\n"
            f"**Your power:** {humanize_number(ours)} · **Enemy power:** {humanize_number(theirs)} · {verdict}\n"
            f"**First clear:** {fmt_loot(rewards)}\n"
            f"-# Current idle rate: {humanize_number(int(rate))} Gold/min. Clear stages to raise it."
        )
        actions = discord.ui.ActionRow(
            Btn(self.fight, label="Fight", emoji="⚔️", style=discord.ButtonStyle.danger),
            Btn(lambda i: self.switch(i, TeamView, back="campaign"), label="Team", emoji="🛡️"),
            Btn(self.replay, label="Replay last", emoji="🎞️", disabled=not p.get("last_battle")),
        )
        self.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(body),
                *self.notice_items(),
                actions,
                discord.ui.Separator(),
                self.nav_row(),
                accent_color=ACCENT,
            )
        )

    def _build_result(self, p):
        result, rewards, stage = self.result
        mvp = result.mvp
        mvp_text = f"MVP: {mvp['name']} ({ROLES[mvp['role']]['name']})" if mvp else ""
        header = (
            f"## {'🏆' if result.win else '💀'} Stage {game.stage_label(stage)} "
            f"{'cleared' if result.win else 'failed'}\n"
            f"Time: {result.seconds:.0f}s · {mvp_text}"
        )
        total = sum(a["damage"] for a in result.attackers) or 1
        top = max((a["damage"] for a in result.attackers), default=1) or 1
        width = max((len(a["name"]) for a in result.attackers), default=4)
        lines = [
            f"{a['name']:<{width}}  {bar(a['damage'], top):<10} {a['damage'] / total:>4.0%}"
            + ("" if a["alive"] else " ☠")
            for a in sorted(result.attackers, key=lambda a: -a["damage"])
        ]
        chart = "```\n" + "\n".join(lines) + "\n```"
        if result.win:
            rate = game.idle_rates(p["stage"])["gold"]
            footer = f"{fmt_loot(rewards)}\n-# Idle rate raised to {humanize_number(int(rate))} Gold/min"
            next_label, next_style = "Next stage", discord.ButtonStyle.success
        else:
            footer = f"💡 {game.loss_hint(result, p['last_battle']['attackers'], p['last_battle']['defenders'])}"
            next_label, next_style = "Retry", discord.ButtonStyle.danger
        actions = discord.ui.ActionRow(
            Btn(self.fight, label=next_label, emoji="⚔️", style=next_style),
            Btn(self.replay, label="Replay", emoji="🎞️"),
            Btn(lambda i: self.switch(i, TeamView, back="campaign"), label="Team", emoji="🛡️"),
            Btn(self.back_to_stage, label="Stage info", emoji="🗺️"),
        )
        self.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(header),
                discord.ui.TextDisplay(chart),
                discord.ui.TextDisplay(footer),
                *self.notice_items(),
                actions,
                discord.ui.Separator(),
                self.nav_row(),
                accent_color=WIN_ACCENT if result.win else LOSS_ACCENT,
            )
        )

    async def fight(self, interaction: discord.Interaction):
        async with self.cog.player(self.user) as p:
            result, rewards, stage = game.fight_campaign(p, self.user.id, game.now_ts())
        self.result = (result, rewards, stage)
        self.notice = None
        await self.refresh(interaction, p)
        if result.win and stage % STAGES_PER_CHAPTER == 0:
            chapter = stage // STAGES_PER_CHAPTER
            await self.cog.brag(
                interaction.guild, self.user, f"🏰 **{self.user.display_name}** cleared **Chapter {chapter}**!"
            )

    async def back_to_stage(self, interaction: discord.Interaction):
        self.result = None
        self.notice = None
        await self.refresh(interaction)

    async def replay(self, interaction: discord.Interaction):
        await self.switch(interaction, ReplayView)


class ReplayView(IdleView):
    screen = "replay"

    def __init__(self, cog, user, notice: Optional[str] = None):
        super().__init__(cog, user, notice)
        self.page = 0
        self.battle = None
        self.lines: List[str] = []

    def build(self, p):
        last = p.get("last_battle")
        if not last:
            self.add_item(
                discord.ui.Container(
                    discord.ui.TextDisplay("## 🎞️ Replay\nNo battles yet."), discord.ui.Separator(), self.nav_row()
                )
            )
            return
        if self.battle is None or self.battle["id"] != last["id"]:
            self.battle = last
            result = game.replay(last)
            self.lines = result.log or ["Nothing notable happened."]
            self.lines.append(f"**{'Victory' if result.win else 'Defeat'}** in {result.seconds:.1f}s.")
        pages = max(1, -(-len(self.lines) // REPLAY_LINES_PER_PAGE))
        self.page = min(self.page, pages - 1)
        chunk = self.lines[self.page * REPLAY_LINES_PER_PAGE : (self.page + 1) * REPLAY_LINES_PER_PAGE]
        lineup = " · ".join(s["name"] for s in last["attackers"] if s)
        foes = " · ".join(s["name"] for s in last["defenders"] if s)
        body = f"## 🎞️ Replay — {last['label']}\n-# You: {lineup}\n-# Enemy: {foes}"
        nav = discord.ui.ActionRow(
            Btn(self.prev, label="◀", disabled=self.page == 0),
            Btn(self.noop, label=f"{self.page + 1}/{pages}", disabled=True),
            Btn(self.next, label="▶", disabled=self.page >= pages - 1),
            Btn(lambda i: self.switch(i, CampaignView), label="Back to campaign", emoji="⚔️"),
        )
        self.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(body),
                discord.ui.Separator(),
                discord.ui.TextDisplay("\n".join(chunk)),
                nav,
                discord.ui.Separator(),
                self.nav_row(),
                accent_color=ACCENT,
            )
        )

    async def prev(self, interaction):
        self.page = max(0, self.page - 1)
        await self.refresh(interaction)

    async def next(self, interaction):
        self.page += 1
        await self.refresh(interaction)

    async def noop(self, interaction):
        await interaction.response.defer()


# ---------------------------------------------------------------- team


class TeamView(IdleView):
    screen = "team"

    def __init__(self, cog, user, notice: Optional[str] = None, mode: str = "campaign", back: Optional[str] = None):
        super().__init__(cog, user, notice)
        self.mode = mode
        self.back = back
        self.slot = 0
        self.page = 0

    def build(self, p):
        team = p["teams"].get(self.mode) or game.empty_team()
        snaps = game.team_snapshots(p, self.mode)
        bonus = team_bonus([s["faction"] for s in snaps if s])

        def slot_line(i):
            iid = team["slots"][i]
            pointer = "▶" if i == self.slot else " "
            if not iid or iid not in p["heroes"]:
                return f"`{pointer}{i + 1}` *empty*"
            rule = ULT_RULES.get(team["rules"][i], "Immediately")
            return f"`{pointer}{i + 1}` {game.hero_label(p['heroes'][iid])}\n-# ult: {rule}"

        formation = (
            f"## 🛡️ Team — {self.mode.title()}\n"
            "**Front line**\n" + "\n".join(slot_line(i) for i in (0, 1)) + "\n"
            "**Back line**\n" + "\n".join(slot_line(i) for i in (2, 3, 4)) + "\n\n"
            f"**Team power:** {humanize_number(game.team_power(snaps))}"
            + (f" · **Faction bonus:** +{bonus:.0%} ATK/HP" if bonus else "")
        )

        slot_row = discord.ui.ActionRow()
        for i in range(5):
            slot_row.add_item(
                Btn(
                    lambda inter, s=i: self.pick_slot(inter, s),
                    label=f"{i + 1} {'Front' if i < 2 else 'Back'}",
                    style=discord.ButtonStyle.primary if i == self.slot else discord.ButtonStyle.secondary,
                )
            )

        ranked = sorted(p["heroes"], key=lambda iid: -game.hero_power(p["heroes"][iid]))
        pages = max(1, -(-len(ranked) // TEAM_OPTIONS_PER_PAGE))
        self.page = min(self.page, pages - 1)
        page_ids = ranked[self.page * TEAM_OPTIONS_PER_PAGE : (self.page + 1) * TEAM_OPTIONS_PER_PAGE]
        current = team["slots"][self.slot]
        options = [discord.SelectOption(label="— Empty slot —", value="none", emoji="➖")]
        for iid in page_ids:
            inst = p["heroes"][iid]
            d = HEROES[inst["hid"]]
            where = f" · in slot {team['slots'].index(iid) + 1}" if iid in team["slots"] else ""
            options.append(
                discord.SelectOption(
                    label=f"{d['name']} · {TIERS[inst['tier']]['name']} Lv.{inst['level']}",
                    value=iid,
                    emoji=FACTIONS[d["faction"]]["emoji"],
                    description=f"{ROLES[d['role']]['name']} · Power {humanize_number(game.hero_power(inst))}{where}",
                    default=iid == current,
                )
            )
        hero_select = Pick(
            self.pick_hero, placeholder=f"Choose a hero for slot {self.slot + 1}…", options=options
        )

        rule_select = Pick(
            self.pick_rule,
            placeholder=f"Ultimate rule for slot {self.slot + 1}…",
            options=[
                discord.SelectOption(label=label, value=value, default=value == team["rules"][self.slot])
                for value, label in ULT_RULES.items()
            ],
            disabled=not current,
        )

        tools = discord.ui.ActionRow()
        if pages > 1:
            tools.add_item(Btn(self.prev_page, label="◀ Heroes", disabled=self.page == 0))
            tools.add_item(Btn(self.next_page, label="Heroes ▶", disabled=self.page >= pages - 1))
        tools.add_item(Btn(self.autofill, label="Auto-fill", emoji="✨", style=discord.ButtonStyle.success))
        if self.back == "campaign":
            tools.add_item(
                Btn(lambda i: self.switch(i, CampaignView), label="Back to campaign", emoji="⚔️")
            )

        self.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(formation),
                *self.notice_items(),
                discord.ui.Separator(),
                slot_row,
                discord.ui.ActionRow(hero_select),
                discord.ui.ActionRow(rule_select),
                tools,
                discord.ui.Separator(),
                self.nav_row(),
                accent_color=ACCENT,
            )
        )

    async def pick_slot(self, interaction, slot: int):
        self.slot = slot
        self.notice = None
        await self.refresh(interaction)

    async def pick_hero(self, interaction, values):
        iid = None if values[0] == "none" else values[0]
        async with self.cog.player(self.user) as p:
            team = p["teams"].setdefault(self.mode, game.empty_team())
            if iid and iid in team["slots"]:
                team["slots"][team["slots"].index(iid)] = None
            game.set_slot(p, self.mode, self.slot, iid)
        self.notice = None
        await self.refresh(interaction, p)

    async def pick_rule(self, interaction, values):
        async with self.cog.player(self.user) as p:
            team = p["teams"].setdefault(self.mode, game.empty_team())
            team["rules"][self.slot] = values[0]
        self.notice = f"Slot {self.slot + 1} ultimate: {ULT_RULES[values[0]]}"
        await self.refresh(interaction, p)

    async def autofill(self, interaction):
        async with self.cog.player(self.user) as p:
            game.auto_team(p, self.mode)
        self.notice = "Filled your team with your five strongest heroes."
        await self.refresh(interaction, p)

    async def prev_page(self, interaction):
        self.page = max(0, self.page - 1)
        await self.refresh(interaction)

    async def next_page(self, interaction):
        self.page += 1
        await self.refresh(interaction)


# ---------------------------------------------------------------- summon


class SummonView(IdleView):
    screen = "summon"

    def __init__(self, cog, user, notice: Optional[str] = None):
        super().__init__(cog, user, notice)
        self.results: List[tuple] = []
        self.pending: Optional[int] = None

    def build(self, p):
        to_pity = SUMMON_PITY - p["pity"]
        wishlist = ", ".join(HEROES[h]["name"] for h in p["wishlist"]) or "*empty — pick up to 5 below*"
        rates = " · ".join(
            f"{RARITIES[r]['emoji']} {RARITIES[r]['name']} {SUMMON_RATES[r]:.0%}" for r in ("elite", "rare", "common")
        )
        body = (
            "## 📜 Summon — Standard Banner\n"
            f"{rates}\n"
            f"**Pity:** {p['pity']}/{SUMMON_PITY} · an Elite is guaranteed within **{to_pity}** pull(s)\n"
            f"**Wishlist** ({WISHLIST_CHANCE:.0%} of Elite pulls): {wishlist}\n"
            f"-# 1 pull = 1 {RESOURCE_EMOJI['scrolls']} Scroll or {SUMMON_GEM_COST} {RESOURCE_EMOJI['gems']}. "
            f"You have {RESOURCE_EMOJI['scrolls']} {humanize_number(p['res'].get('scrolls', 0))} · "
            f"{RESOURCE_EMOJI['gems']} {humanize_number(p['res'].get('gems', 0))}"
        )
        items: list = [discord.ui.TextDisplay(body)]

        if self.results:
            lines = []
            for _, hid in self.results:
                d = HEROES[hid]
                name = f"**{d['name']}**" if d["rarity"] == "elite" else d["name"]
                lines.append(f"{RARITIES[d['rarity']]['emoji']} {FACTIONS[d['faction']]['emoji']} {name}")
            elites = sum(1 for _, h in self.results if HEROES[h]["rarity"] == "elite")
            title = f"### ✨ Results{' — ELITE!' if elites else ''}"
            items += [discord.ui.Separator(), discord.ui.TextDisplay(title + "\n" + "\n".join(lines))]

        items += self.notice_items()

        if self.pending:
            cost = game.summon_cost(p, self.pending)
            spend = fmt_loot({"scrolls": cost[0], "gems": cost[1]}) if cost else "more than you have"
            items += [
                discord.ui.Separator(),
                discord.ui.TextDisplay(f"**Confirm {self.pending}× summon?** This spends {spend}."),
                discord.ui.ActionRow(
                    Btn(lambda i: self.pull(i, self.pending, True), label="Confirm", style=discord.ButtonStyle.danger),
                    Btn(self.cancel, label="Cancel"),
                ),
            ]
        else:
            one, ten = game.summon_cost(p, 1), game.summon_cost(p, 10)
            items.append(
                discord.ui.ActionRow(
                    Btn(lambda i: self.pull(i, 1), label=f"Summon ×1 ({self.cost_label(one)})",
                        style=discord.ButtonStyle.primary, disabled=one is None),
                    Btn(lambda i: self.pull(i, 10), label=f"Summon ×10 ({self.cost_label(ten)})",
                        style=discord.ButtonStyle.success, disabled=ten is None),
                )
            )
            elites = heroes_of("elite")
            items.append(
                discord.ui.ActionRow(
                    Pick(
                        self.set_wishlist,
                        placeholder="Set your wishlist (up to 5 Elite heroes)…",
                        min_values=0,
                        max_values=min(WISHLIST_SIZE, len(elites)),
                        options=[
                            discord.SelectOption(
                                label=HEROES[h]["name"],
                                value=h,
                                emoji=FACTIONS[HEROES[h]["faction"]]["emoji"],
                                description=f"{FACTIONS[HEROES[h]['faction']]['name']} {ROLES[HEROES[h]['role']]['name']}",
                                default=h in p["wishlist"],
                            )
                            for h in elites
                        ],
                    )
                )
            )
        items += [discord.ui.Separator(), self.nav_row()]
        self.add_item(discord.ui.Container(*items, accent_color=discord.Color.purple()))

    @staticmethod
    def cost_label(cost) -> str:
        if cost is None:
            return "can't afford"
        scrolls, gems = cost
        parts = []
        if scrolls:
            parts.append(f"{scrolls} 📜")
        if gems:
            parts.append(f"{humanize_number(gems)} 💎")
        return " + ".join(parts)

    async def pull(self, interaction, count: int, confirmed: bool = False):
        p = await self.cog.get_player(self.user)
        cost = game.summon_cost(p, count)
        if cost and game.needs_confirm(cost) and not confirmed:
            self.pending = count
            await self.refresh(interaction, p)
            return
        async with self.cog.player(self.user) as p:
            self.results = game.summon(p, count, random.Random(), game.now_ts())
        self.pending = None
        self.notice = None
        await self.refresh(interaction, p)
        for _, hid in self.results:
            if HEROES[hid]["rarity"] == "elite":
                d = HEROES[hid]
                await self.cog.brag(
                    interaction.guild,
                    self.user,
                    f"🟣 **{self.user.display_name}** summoned the Elite hero "
                    f"**{FACTIONS[d['faction']]['emoji']} {d['name']}**!",
                )

    async def cancel(self, interaction):
        self.pending = None
        await self.refresh(interaction)

    async def set_wishlist(self, interaction, values):
        async with self.cog.player(self.user) as p:
            p["wishlist"] = values[:WISHLIST_SIZE]
        self.notice = "Wishlist saved." if values else "Wishlist cleared."
        await self.refresh(interaction, p)


# ---------------------------------------------------------------- roster


class HeroesView(IdleView):
    screen = "heroes"

    def __init__(self, cog, user, notice: Optional[str] = None, faction: str = "all", role: str = "all", page: int = 0):
        super().__init__(cog, user, notice)
        self.faction = faction
        self.role = role
        self.page = page

    def filtered(self, p) -> List[str]:
        out = []
        for iid, inst in p["heroes"].items():
            d = HEROES[inst["hid"]]
            if self.faction != "all" and d["faction"] != self.faction:
                continue
            if self.role != "all" and d["role"] != self.role:
                continue
            out.append(iid)
        out.sort(key=lambda i: -game.hero_power(p["heroes"][i]))
        return out

    def build(self, p):
        ids = self.filtered(p)
        pages = max(1, -(-len(ids) // HEROES_PER_PAGE))
        self.page = min(self.page, pages - 1)
        page_ids = ids[self.page * HEROES_PER_PAGE : (self.page + 1) * HEROES_PER_PAGE]
        locked = game.heroes_in_teams(p)
        listing = "\n".join(hero_line(p, iid, locked) for iid in page_ids) or "*No heroes match these filters.*"

        faction_select = Pick(
            self.set_faction,
            options=[discord.SelectOption(label="All factions", value="all", default=self.faction == "all")]
            + [
                discord.SelectOption(label=f["name"], value=k, emoji=f["emoji"], default=self.faction == k)
                for k, f in FACTIONS.items()
            ],
        )
        role_select = Pick(
            self.set_role,
            options=[discord.SelectOption(label="All roles", value="all", default=self.role == "all")]
            + [
                discord.SelectOption(label=r["name"], value=k, emoji=r["emoji"], default=self.role == k)
                for k, r in ROLES.items()
            ],
        )
        items: list = [
            discord.ui.TextDisplay(f"## 🦸 Heroes ({len(p['heroes'])})"),
            discord.ui.Separator(),
            discord.ui.TextDisplay(listing),
            *self.notice_items(),
            discord.ui.Separator(),
            discord.ui.ActionRow(faction_select),
            discord.ui.ActionRow(role_select),
        ]
        if page_ids:
            items.append(
                discord.ui.ActionRow(
                    Pick(
                        self.open_hero,
                        placeholder="Open a hero card…",
                        options=[
                            discord.SelectOption(
                                label=f"{HEROES[p['heroes'][i]['hid']]['name']} · "
                                f"{TIERS[p['heroes'][i]['tier']]['name']} Lv.{p['heroes'][i]['level']}",
                                value=i,
                                emoji=FACTIONS[HEROES[p["heroes"][i]["hid"]]["faction"]]["emoji"],
                            )
                            for i in page_ids
                        ],
                    )
                )
            )
        items.append(
            discord.ui.ActionRow(
                Btn(self.prev, label="◀", disabled=self.page == 0),
                Btn(self.noop, label=f"{self.page + 1}/{pages}", disabled=True),
                Btn(self.next, label="▶", disabled=self.page >= pages - 1),
            )
        )
        items += [discord.ui.Separator(), self.nav_row()]
        self.add_item(discord.ui.Container(*items, accent_color=ACCENT))

    async def set_faction(self, interaction, values):
        self.faction, self.page = values[0], 0
        await self.refresh(interaction)

    async def set_role(self, interaction, values):
        self.role, self.page = values[0], 0
        await self.refresh(interaction)

    async def open_hero(self, interaction, values):
        await self.switch(
            interaction, HeroCardView, iid=values[0], back=(self.faction, self.role, self.page)
        )

    async def prev(self, interaction):
        self.page = max(0, self.page - 1)
        await self.refresh(interaction)

    async def next(self, interaction):
        self.page += 1
        await self.refresh(interaction)

    async def noop(self, interaction):
        await interaction.response.defer()


class HeroCardView(IdleView):
    screen = "hero"

    def __init__(self, cog, user, notice: Optional[str] = None, iid: str = "", back=None):
        super().__init__(cog, user, notice)
        self.iid = iid
        self.back = back or ("all", "all", 0)

    def build(self, p):
        inst = p["heroes"].get(self.iid)
        if not inst:
            self.add_item(
                discord.ui.Container(
                    discord.ui.TextDisplay("## 🦸 Hero\nThat hero is no longer in your roster."),
                    discord.ui.ActionRow(Btn(self.to_roster, label="Back to roster", emoji="🦸")),
                )
            )
            return
        d = HEROES[inst["hid"]]
        stats = game.hero_stats(inst)
        cap = game.level_cap(inst)
        weak_to = next((k for k, v in COUNTERS.items() if v == d["faction"]), None)
        header = (
            f"## {FACTIONS[d['faction']]['emoji']} {d['name']}\n"
            f"{RARITIES[d['rarity']]['emoji']} {RARITIES[d['rarity']]['name']} · "
            f"{CLASSES[d['cls']]['emoji']} {CLASSES[d['cls']]['name']} · "
            f"{ROLES[d['role']]['emoji']} {ROLES[d['role']]['name']} · {FACTIONS[d['faction']]['name']}\n"
            f"**{TIERS[inst['tier']]['name']}** · Level **{inst['level']}/{cap}** · "
            f"⚡ Power **{humanize_number(game.hero_power(inst))}**\n"
            f"-# Strong vs {FACTIONS[COUNTERS[d['faction']]]['name']} · Weak vs {FACTIONS[weak_to]['name']}"
        )
        stat_block = (
            "```\n"
            f"HP    {stats['hp']:>9,.0f}   Speed     {stats['spd']:>5.0f}\n"
            f"ATK   {stats['atk']:>9,.0f}   Crit      {stats['crit']:>5.0%}\n"
            f"DEF   {stats['def']:>9,.0f}   Crit DMG  {stats['critdmg']:>5.0%}\n"
            f"Haste {stats['haste']:>9.0f}   Energy    {stats['energy']:>5.0%}\n"
            "```"
        )
        skill_lines = []
        for label, skill, unlocked in game.hero_skills(inst):
            if unlocked:
                cd = f" · {skill['cd']}s" if skill.get("cd") else ""
                skill_lines.append(f"**{label}: {skill['name']}**{cd}\n-# {skill['desc']}")
            else:
                need = TIERS[PASSIVE_UNLOCK_TIER if label == 'Passive' else S2_UNLOCK_TIER]["name"]
                skill_lines.append(f"🔒 **{label}: {skill['name']}** — unlocks at {need}\n-# {skill['desc']}")

        if inst["level"] < cap:
            gold, ess = game.level_cost(inst["level"])
            level_text = (
                f"### 📈 Level up\nNext level: {RESOURCE_EMOJI['gold']} {humanize_number(gold)} · "
                f"{RESOURCE_EMOJI['essence']} {humanize_number(ess)}\n-# You have {fmt_wallet(p)}"
            )
        else:
            level_text = "### 📈 Level up\nLevel cap reached. Ascend to raise it."
        level_row = discord.ui.ActionRow(
            Btn(lambda i: self.level(i, 1), label="+1", style=discord.ButtonStyle.success, disabled=inst["level"] >= cap),
            Btn(lambda i: self.level(i, 10), label="+10", style=discord.ButtonStyle.success, disabled=inst["level"] >= cap),
            Btn(lambda i: self.level(i, cap), label="Max", style=discord.ButtonStyle.success, disabled=inst["level"] >= cap),
        )

        req = game.ascension_requirement(p, self.iid)
        if req:
            nxt = TIERS[inst["tier"] + 1]
            have = len(game.eligible_fodder(p, self.iid))
            asc_text = (
                f"### ⬆️ Ascension\nNext: **{nxt['name']}** (level cap {min(nxt['cap'], RARITIES[d['rarity']]['level_cap'])})\n"
                f"Needs {game.describe_requirement(req)} · you have **{have}** eligible"
            )
        else:
            asc_text = "### ⬆️ Ascension\nThis hero is at its highest tier."
        asc_section = discord.ui.Section(
            discord.ui.TextDisplay(asc_text),
            accessory=Btn(
                lambda i: self.switch(i, AscendView, iid=self.iid, back=self.back),
                label="Ascend",
                emoji="⬆️",
                style=discord.ButtonStyle.primary,
                disabled=req is None,
            ),
        )

        self.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(header),
                discord.ui.TextDisplay(stat_block),
                discord.ui.Separator(),
                discord.ui.TextDisplay("\n".join(skill_lines)),
                discord.ui.Separator(),
                discord.ui.TextDisplay(level_text),
                level_row,
                asc_section,
                *self.notice_items(),
                discord.ui.ActionRow(Btn(self.to_roster, label="Back to roster", emoji="🦸")),
                discord.ui.Separator(),
                self.nav_row(),
                accent_color=ACCENT,
            )
        )

    async def level(self, interaction, levels: int):
        async with self.cog.player(self.user) as p:
            gained, gold, ess = game.level_up(p, self.iid, levels)
        self.notice = (
            f"+{gained} level{'s' if gained != 1 else ''} for "
            f"{fmt_loot({'gold': gold, 'essence': ess})}"
        )
        await self.refresh(interaction, p)

    async def to_roster(self, interaction):
        faction, role, page = self.back
        await self.switch(interaction, HeroesView, faction=faction, role=role, page=page)


class AscendView(IdleView):
    screen = "ascend"

    def __init__(self, cog, user, notice: Optional[str] = None, iid: str = "", back=None):
        super().__init__(cog, user, notice)
        self.iid = iid
        self.back = back
        self.selected: List[str] = []

    def build(self, p):
        inst = p["heroes"].get(self.iid)
        req = game.ascension_requirement(p, self.iid) if inst else None
        if not req:
            self.add_item(
                discord.ui.Container(
                    discord.ui.TextDisplay("## ⬆️ Ascend\nThis hero can't ascend any further."),
                    discord.ui.ActionRow(Btn(self.to_card, label="Back to hero", emoji="🦸")),
                )
            )
            return
        d = HEROES[inst["hid"]]
        cur, nxt = TIERS[inst["tier"]], TIERS[inst["tier"] + 1]
        rarity_cap = RARITIES[d["rarity"]]["level_cap"]
        eligible = game.eligible_fodder(p, self.iid)
        self.selected = [s for s in self.selected if s in eligible]
        body = (
            f"## ⬆️ Ascend {FACTIONS[d['faction']]['emoji']} {d['name']}\n"
            f"**{cur['name']} → {nxt['name']}** · level cap {min(cur['cap'], rarity_cap)} → {min(nxt['cap'], rarity_cap)}\n"
            f"**Cost:** {game.describe_requirement(req)}\n"
            f"-# Sacrificed heroes are gone for good, but every Gold and Essence spent on them is refunded. "
            f"Heroes in a team can't be used."
        )
        items: list = [discord.ui.TextDisplay(body), discord.ui.Separator()]
        if len(eligible) < req["count"]:
            items.append(
                discord.ui.TextDisplay(
                    f"You have **{len(eligible)}** eligible hero(es) and need **{req['count']}**. "
                    "Summon more or ascend other heroes first."
                )
            )
        else:
            options = [
                discord.SelectOption(
                    label=f"{HEROES[p['heroes'][i]['hid']]['name']} · {TIERS[p['heroes'][i]['tier']]['name']} "
                    f"Lv.{p['heroes'][i]['level']}",
                    value=i,
                    emoji=FACTIONS[HEROES[p["heroes"][i]["hid"]]["faction"]]["emoji"],
                    description=f"Refunds {humanize_number(p['heroes'][i]['gold_spent'])} Gold",
                    default=i in self.selected,
                )
                for i in eligible[:25]
            ]
            items.append(
                discord.ui.ActionRow(
                    Pick(
                        self.pick,
                        placeholder=f"Pick {req['count']} hero(es) to sacrifice…",
                        min_values=req["count"],
                        max_values=req["count"],
                        options=options,
                    )
                )
            )
            if self.selected:
                names = ", ".join(HEROES[p["heroes"][i]["hid"]]["name"] for i in self.selected)
                items.append(discord.ui.TextDisplay(f"Sacrificing: **{names}**"))
        items += self.notice_items()
        items.append(
            discord.ui.ActionRow(
                Btn(
                    self.confirm,
                    label="Confirm ascension",
                    emoji="⬆️",
                    style=discord.ButtonStyle.danger,
                    disabled=len(self.selected) != req["count"],
                ),
                Btn(self.to_card, label="Cancel"),
            )
        )
        self.add_item(discord.ui.Container(*items, accent_color=discord.Color.purple()))

    async def pick(self, interaction, values):
        self.selected = values
        await self.refresh(interaction)

    async def confirm(self, interaction):
        async with self.cog.player(self.user) as p:
            old = p["heroes"][self.iid]["tier"] if self.iid in p["heroes"] else 0
            refund = game.ascend(p, self.iid, self.selected)
        name = HEROES[p["heroes"][self.iid]["hid"]]["name"]
        refunded = f" Refunded {fmt_loot(refund)}." if any(refund.values()) else ""
        notice = f"{name} ascended to {TIERS[old + 1]['name']}!{refunded}"
        await self.switch(interaction, HeroCardView, iid=self.iid, back=self.back, notice=notice)

    async def to_card(self, interaction):
        await self.switch(interaction, HeroCardView, iid=self.iid, back=self.back)


# ---------------------------------------------------------------- settings


class SettingsView(IdleView):
    screen = "settings"

    def build(self, p):
        s = p["settings"]
        dm = (
            "### 🔔 DM notifications\nGet one DM when your idle chest is full.\n"
            f"-# Currently **{'on' if s.get('dm') else 'off'}**. Never more than 1 DM per 6 hours."
        )
        public = (
            "### 📣 Public brag posts\nShare Elite pulls and chapter clears in the server's IdleCord channel.\n"
            f"-# Currently **{'on' if s.get('public', True) else 'off'}**."
        )
        self.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay("## ⚙️ Settings"),
                discord.ui.Separator(),
                discord.ui.Section(
                    discord.ui.TextDisplay(dm),
                    accessory=Btn(
                        lambda i: self.toggle(i, "dm", False),
                        label="Turn off" if s.get("dm") else "Turn on",
                        style=discord.ButtonStyle.secondary if s.get("dm") else discord.ButtonStyle.success,
                    ),
                ),
                discord.ui.Section(
                    discord.ui.TextDisplay(public),
                    accessory=Btn(
                        lambda i: self.toggle(i, "public", True),
                        label="Turn off" if s.get("public", True) else "Turn on",
                        style=discord.ButtonStyle.secondary
                        if s.get("public", True)
                        else discord.ButtonStyle.success,
                    ),
                ),
                *self.notice_items(),
                discord.ui.Separator(),
                self.nav_row(),
                accent_color=ACCENT,
            )
        )

    async def toggle(self, interaction, key: str, default: bool):
        async with self.cog.player(self.user) as p:
            p["settings"][key] = not p["settings"].get(key, default)
        await self.refresh(interaction, p)
