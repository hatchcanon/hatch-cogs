import asyncio
import contextlib
import random
import time
from collections import defaultdict
from typing import Dict, Literal, Optional

import discord
from discord.ext import tasks
from red_commons.logging import getLogger
from redbot.core import Config, commands

from . import game
from .data import HEROES, IDLE_CAP_MINUTES
from .game import DEFAULT_PLAYER, GameError
from .views import (
    ACCENT,
    LOSS_ACCENT,
    AscendView,
    Btn,
    CampaignView,
    DailyView,
    HeroCardView,
    HeroesView,
    IdleView,
    SettingsView,
    StartView,
    SummonView,
    TeamView,
    fmt_loot,
    text_view,
)

log = getLogger("red.hatch.idlecord")

# Minimum seconds between public brag posts in one server.
BRAG_COOLDOWN = 30
DM_COOLDOWN = 6 * 3600


class _CollectView(IdleView):
    """Small result card for /idlecord collect with a shortcut to the daily panel."""

    screen = "collect"

    def build(self, p):
        self.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(f"## 🎁 Idle loot claimed\n{self.notice}"),
                discord.ui.ActionRow(
                    Btn(lambda i: self.switch(i, DailyView), label="Open daily panel", emoji="🎁"),
                    Btn(lambda i: self.switch(i, CampaignView), label="Campaign", emoji="⚔️"),
                ),
                accent_color=ACCENT,
            )
        )


class IdleCord(commands.Cog):
    """An idle hero-collector RPG played inside Discord."""

    __version__ = "0.1.0"
    __author__ = "hatch"

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=0x1D1EC0BD, force_registration=True)
        self.config.register_user(**DEFAULT_PLAYER)
        self.config.register_guild(public_channel=None)
        self.locks: Dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)
        self.last_brag: Dict[int, float] = {}

    async def cog_load(self):
        self.chest_notifier.start()

    async def cog_unload(self):
        self.chest_notifier.cancel()

    def format_help_for_context(self, ctx: commands.Context) -> str:
        pre = super().format_help_for_context(ctx)
        return f"{pre}\n\nVersion: {self.__version__}"

    async def red_delete_data_for_user(
        self,
        *,
        requester: Literal["discord_deleted_user", "owner", "user", "user_strict"],
        user_id: int,
    ):
        await self.config.user_from_id(user_id).clear()

    # ---------------------------------------------------------------- state

    async def get_player(self, user: discord.abc.User) -> dict:
        return await self.config.user(user).all()

    @contextlib.asynccontextmanager
    async def player(self, user: discord.abc.User):
        """Lock, load and save a player. Nothing is saved if the block raises."""
        async with self.locks[user.id]:
            p = await self.config.user(user).all()
            if not p["started"]:
                raise GameError("You haven't started yet. Use `/idlecord start`.")
            yield p
            await self.config.user(user).set(p)

    async def create_player(self, user: discord.abc.User, starter: str) -> dict:
        async with self.locks[user.id]:
            if await self.config.user(user).started():
                raise GameError("You've already started your adventure.")
            p = game.new_player(starter, game.now_ts())
            await self.config.user(user).set(p)
            return p

    # ---------------------------------------------------------------- public posts

    async def brag(self, guild: Optional[discord.Guild], user: discord.abc.User, text: str):
        if guild is None:
            return
        channel_id = await self.config.guild(guild).public_channel()
        if not channel_id:
            return
        settings = await self.config.user(user).settings()
        if not settings.get("public", True):
            return
        now = time.monotonic()
        if now - self.last_brag.get(guild.id, 0) < BRAG_COOLDOWN:
            return
        channel = guild.get_channel(channel_id)
        if channel is None or not channel.permissions_for(guild.me).send_messages:
            return
        self.last_brag[guild.id] = now
        with contextlib.suppress(discord.HTTPException):
            await channel.send(view=text_view(text), allowed_mentions=discord.AllowedMentions.none())

    # ---------------------------------------------------------------- notifications

    @tasks.loop(minutes=10)
    async def chest_notifier(self):
        now = game.now_ts()
        for user_id, data in (await self.config.all_users()).items():
            if not data.get("started") or not data.get("settings", {}).get("dm"):
                continue
            last_claim = data.get("last_claim", 0)
            if now < last_claim + IDLE_CAP_MINUTES * 60:
                continue
            if data.get("notified_claim", 0) > last_claim:
                continue
            if now - data.get("last_dm", 0) < DM_COOLDOWN:
                continue
            user = self.bot.get_user(user_id)
            if user is None:
                continue
            async with self.locks[user_id]:
                await self.config.user_from_id(user_id).notified_claim.set(now)
                await self.config.user_from_id(user_id).last_dm.set(now)
            with contextlib.suppress(discord.HTTPException):
                await user.send(
                    view=text_view(
                        "## 🎁 Your idle chest is full\n"
                        "It has stopped filling. Claim it with `/idlecord daily` or `/idlecord collect`.\n"
                        "-# Turn these off with `/idlecord settings`."
                    )
                )

    @chest_notifier.before_loop
    async def _before_notifier(self):
        await self.bot.wait_until_red_ready()

    # ---------------------------------------------------------------- helpers

    async def _defer(self, ctx: commands.Context):
        if ctx.interaction and not ctx.interaction.response.is_done():
            await ctx.defer(ephemeral=True)

    async def _open(self, ctx: commands.Context, view: IdleView, need_player: bool = True):
        await self._defer(ctx)
        p = await self.get_player(ctx.author)
        if need_player and not p["started"]:
            return await self._error(ctx, "You haven't started yet. Use `/idlecord start`.")
        view.render(p)
        view.message = await ctx.send(view=view, ephemeral=True)

    async def _error(self, ctx: commands.Context, text: str):
        await ctx.send(view=text_view(f"⚠️ {text}", LOSS_ACCENT), ephemeral=True)

    async def _find_hero(self, ctx: commands.Context, name: str) -> Optional[str]:
        """The iid of the player's strongest copy of the named hero."""
        p = await self.get_player(ctx.author)
        if not p["started"]:
            await self._error(ctx, "You haven't started yet. Use `/idlecord start`.")
            return None
        needle = name.lower().strip()
        matches = [hid for hid, h in HEROES.items() if h["name"].lower() == needle]
        if not matches:
            matches = [hid for hid, h in HEROES.items() if h["name"].lower().startswith(needle)]
        owned = [iid for iid, inst in p["heroes"].items() if inst["hid"] in matches]
        if not owned:
            await self._error(ctx, f"You don't own a hero called `{name}`.")
            return None
        return max(owned, key=lambda i: (p["heroes"][i]["tier"], game.hero_power(p["heroes"][i])))

    # ---------------------------------------------------------------- commands

    @commands.hybrid_group(name="idlecord", aliases=["ic"])
    async def idlecord(self, ctx: commands.Context):
        """IdleCord: collect heroes, build a team and push the campaign."""

    @idlecord.command(name="start")
    async def ic_start(self, ctx: commands.Context):
        """Begin your adventure and pick a starter hero."""
        if await self.config.user(ctx.author).started():
            return await self._open(ctx, DailyView(self, ctx.author, notice="You've already started. Welcome back!"))
        await self._open(ctx, StartView(self, ctx.author), need_player=False)

    @idlecord.command(name="daily")
    async def ic_daily(self, ctx: commands.Context):
        """Claim idle loot, Fast Rewards and daily quests from one panel."""
        await self._open(ctx, DailyView(self, ctx.author))

    @idlecord.command(name="collect")
    async def ic_collect(self, ctx: commands.Context):
        """Claim your idle loot."""
        await self._defer(ctx)
        try:
            async with self.player(ctx.author) as p:
                loot = game.claim_idle(p, game.now_ts(), random.Random())
        except GameError as e:
            return await self._error(ctx, str(e))
        view = _CollectView(self, ctx.author, notice=fmt_loot(loot))
        view.render(p)
        view.message = await ctx.send(view=view, ephemeral=True)

    @idlecord.command(name="campaign")
    async def ic_campaign(self, ctx: commands.Context):
        """See the next campaign stage and fight it."""
        await self._open(ctx, CampaignView(self, ctx.author))

    @idlecord.command(name="team")
    async def ic_team(self, ctx: commands.Context, mode: Literal["campaign"] = "campaign"):
        """Edit your formation and ultimate rules."""
        await self._open(ctx, TeamView(self, ctx.author, mode=mode))

    @idlecord.command(name="summon")
    async def ic_summon(self, ctx: commands.Context, count: Optional[Literal[1, 10]] = None):
        """Summon heroes from the standard banner.

        Pass 1 or 10 to pull right away, or leave it empty to open the banner.
        """
        view = SummonView(self, ctx.author)
        if count:
            await self._defer(ctx)
            p = await self.get_player(ctx.author)
            cost = game.summon_cost(p, count) if p["started"] else None
            if p["started"] and cost and game.needs_confirm(cost):
                view.pending = count
            elif p["started"]:
                try:
                    async with self.player(ctx.author) as p:
                        view.results = game.summon(p, count, random.Random(), game.now_ts())
                except GameError as e:
                    view.notice = str(e)
        await self._open(ctx, view)
        for _, hid in view.results:
            if HEROES[hid]["rarity"] == "elite":
                await self.brag(
                    ctx.guild,
                    ctx.author,
                    f"🟣 **{ctx.author.display_name}** summoned the Elite hero **{HEROES[hid]['name']}**!",
                )

    @idlecord.command(name="heroes")
    async def ic_heroes(self, ctx: commands.Context):
        """Browse your hero roster."""
        await self._open(ctx, HeroesView(self, ctx.author))

    @idlecord.command(name="hero")
    async def ic_hero(self, ctx: commands.Context, *, name: str):
        """Show a hero card: stats, skills, leveling and ascension."""
        await self._defer(ctx)
        iid = await self._find_hero(ctx, name)
        if iid:
            await self._open(ctx, HeroCardView(self, ctx.author, iid=iid))

    @idlecord.command(name="ascend")
    async def ic_ascend(self, ctx: commands.Context, *, name: str):
        """Ascend a hero by sacrificing copies or faction fodder."""
        await self._defer(ctx)
        iid = await self._find_hero(ctx, name)
        if iid:
            await self._open(ctx, AscendView(self, ctx.author, iid=iid))

    @idlecord.command(name="settings")
    async def ic_settings(self, ctx: commands.Context):
        """DM notifications and public post opt-out."""
        await self._open(ctx, SettingsView(self, ctx.author))

    @idlecord.command(name="setup")
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    async def ic_setup(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None):
        """Set the channel for public brag posts. Leave empty to turn them off."""
        await self.config.guild(ctx.guild).public_channel.set(channel.id if channel else None)
        text = (
            f"## ✅ IdleCord setup\nBrag posts will go to {channel.mention}."
            if channel
            else "## ✅ IdleCord setup\nPublic brag posts are turned off for this server."
        )
        await ctx.send(view=text_view(text), ephemeral=True)

    @idlecord.command(name="reset", with_app_command=False)
    @commands.is_owner()
    async def ic_reset(self, ctx: commands.Context, user: discord.User):
        """Wipe a player's IdleCord progress."""
        async with self.locks[user.id]:
            await self.config.user(user).clear()
        await ctx.send(view=text_view(f"Reset IdleCord progress for **{user}**."))
