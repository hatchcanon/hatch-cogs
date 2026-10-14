import asyncio
import logging
import re
import time
from typing import Optional

import discord
from redbot.core import Config, bank, commands
from redbot.core.data_manager import cog_data_path
from redbot.core.i18n import Translator

from . import charts
from .abc import MixinMeta
from .statsdb import StatsDB

log = logging.getLogger("red.adventurehelper.stats")

_ = Translator("AdventureHelper", __file__)

FLUSH_INTERVAL = 15
DEFAULT_COMPARE = 5

_PERIOD_RE = re.compile(r"^(\d+)([hdw])$", re.IGNORECASE)
_UNIT_SECONDS = {"h": 3600, "d": 86400, "w": 604800}
_UNIT_NAMES = {"h": "hour", "d": "day", "w": "week"}


class Period:
    """A lookback window like `24h`, `7d`, `4w` or `all`."""

    def __init__(self, seconds: Optional[int], label: str):
        self.seconds = seconds
        self.label = label

    def since(self, now: float) -> Optional[float]:
        return None if self.seconds is None else now - self.seconds

    @classmethod
    async def convert(cls, ctx: commands.Context, argument: str) -> "Period":
        arg = argument.lower()
        if arg == "all":
            return cls(None, "All time")
        match = _PERIOD_RE.match(arg)
        if not match or int(match.group(1)) == 0:
            raise commands.BadArgument(_("Period must look like `24h`, `7d`, `4w` or `all`."))
        n, unit = int(match.group(1)), match.group(2)
        plural = "s" if n != 1 else ""
        return cls(n * _UNIT_SECONDS[unit], f"Last {n} {_UNIT_NAMES[unit]}{plural}")


DEFAULT_PERIOD = Period(30 * 86400, "Last 30 days")


class AdventureStats(MixinMeta):
    """Records adventure gold and level history and renders it as charts."""

    def __init__(self, *args):
        super().__init__(*args)
        self.stats_db = StatsDB(cog_data_path(raw_name="AdventureHelper") / "stats.db")
        self._flush_task: Optional[asyncio.Task] = None

    async def _stats_load(self) -> None:
        await self.stats_db.open()
        self._flush_task = asyncio.create_task(self._flush_loop())
        asyncio.create_task(self._seed_snapshot())

    async def _stats_unload(self) -> None:
        if self._flush_task:
            self._flush_task.cancel()
        await self.stats_db.close()

    async def _flush_loop(self) -> None:
        while True:
            await asyncio.sleep(FLUSH_INTERVAL)
            try:
                await self.stats_db.flush()
            except Exception:
                log.exception("Failed to flush adventure stats")

    async def _seed_snapshot(self) -> None:
        """Record a starting point for every adventurer who has no history yet.

        Adventure only stores current values, so this snapshot is where every
        chart begins for players who existed before logging started.
        """
        await self.bot.wait_until_red_ready()
        now = time.time()
        try:
            known_gold = await self.stats_db.known_users("gold_events")
            known_level = await self.stats_db.known_users("level_events")

            adv_config = Config.get_conf(None, 2_710_801_001, cog_name="Adventure")
            for uid, data in (await adv_config.all_users()).items():
                if uid not in known_level and "lvl" in data:
                    self.stats_db.add_level(uid, now, data["lvl"], data.get("exp", 0), data.get("rebirths", 0))

            if await self._adventure_separate_economy():
                adv_bank = Config.get_conf(None, 384734293238749, cog_name="AdventureBank")
                balances = {uid: d.get("balance", 0) for uid, d in (await adv_bank.all_users()).items()}
            elif await bank.is_global():
                balances = {uid: d["balance"] for uid, d in await bank.get_leaderboard()}
            else:
                balances = {}
            for uid, balance in balances.items():
                if uid not in known_gold:
                    self.stats_db.add_gold(uid, now, balance)
            await self.stats_db.flush()
        except Exception:
            log.exception("Failed to seed adventure stats snapshot")

    async def _adventure_separate_economy(self) -> bool:
        adv_cog = self.bot.get_cog("Adventure")
        if adv_cog is not None and adv_cog._separate_economy is not None:
            return adv_cog._separate_economy
        adv_config = Config.get_conf(None, 2_710_801_001, cog_name="Adventure")
        # Adventure defaults to a separate economy when the setting was never stored.
        return await adv_config.separate_economy() is not False

    # ---- listeners -------------------------------------------------------

    @commands.Cog.listener()
    async def on_adventure_bank_set_balance(self, member, old_balance: int, new_balance: int) -> None:
        self.stats_db.add_gold(member.id, time.time(), new_balance)

    @commands.Cog.listener()
    async def on_red_bank_set_balance(self, payload) -> None:
        # Adventure only writes to Red's bank when its separate economy is off.
        adv_cog = self.bot.get_cog("Adventure")
        if adv_cog is None or adv_cog._separate_economy is not False:
            return
        self.stats_db.add_gold(payload.recipient.id, time.time(), payload.recipient_new_balance)

    @commands.Cog.listener()
    async def on_adventure_level_change(self, user, old_lvl: int, new_lvl: int, exp: int, rebirths: int) -> None:
        self.stats_db.add_level(user.id, time.time(), new_lvl, exp, rebirths)

    # ---- commands --------------------------------------------------------

    async def _render(self, func, *args) -> discord.File:
        buf = await asyncio.get_running_loop().run_in_executor(None, func, *args)
        return discord.File(buf, filename="adventure_stats.png")

    async def _top_members(self, guild: discord.Guild, metric: str) -> list:
        if metric == "gold":
            latest = await self.stats_db.latest_gold()
            rank = latest.get
        else:
            latest = await self.stats_db.latest_level()
            rank = lambda uid: (latest[uid][1], latest[uid][0])  # noqa: E731 - rebirths, then level
        ids = sorted((uid for uid in latest if guild.get_member(uid) is not None), key=rank, reverse=True)
        return [guild.get_member(uid) for uid in ids[:DEFAULT_COMPARE]]

    @commands.group(name="advstats")
    @commands.guild_only()
    async def advstats(self, ctx: commands.Context) -> None:
        """Charts of adventure gold and level history."""
        pass

    @advstats.command(name="gold")
    @commands.bot_has_permissions(attach_files=True)
    async def advstats_gold(
        self, ctx: commands.Context, member: Optional[discord.Member] = None, period: Period = DEFAULT_PERIOD
    ) -> None:
        """Chart a player's gold over time.

        Period looks like `24h`, `7d`, `4w` or `all` (default `30d`).
        Example: `[p]advstats gold @someone 7d`
        """
        member = member or ctx.author
        now = time.time()
        since = period.since(now)
        async with ctx.typing():
            data = await self.stats_db.gold_series([member.id], since or 0)
            points = data.get(member.id)
            if not points:
                return await ctx.send(_("No gold history recorded for {name} yet.").format(name=member.display_name))
            file = await self._render(charts.gold_chart, member.display_name, period.label, points, since, now)
        await ctx.send(file=file)

    @advstats.command(name="level")
    @commands.bot_has_permissions(attach_files=True)
    async def advstats_level(
        self, ctx: commands.Context, member: Optional[discord.Member] = None, period: Period = DEFAULT_PERIOD
    ) -> None:
        """Chart a player's level over time, with rebirths marked.

        Period looks like `24h`, `7d`, `4w` or `all` (default `30d`).
        Example: `[p]advstats level @someone all`
        """
        member = member or ctx.author
        now = time.time()
        since = period.since(now)
        async with ctx.typing():
            data = await self.stats_db.level_series([member.id], since or 0)
            points = data.get(member.id)
            if not points:
                return await ctx.send(_("No level history recorded for {name} yet.").format(name=member.display_name))
            file = await self._render(charts.level_chart, member.display_name, period.label, points, since, now)
        await ctx.send(file=file)

    @advstats.group(name="compare")
    async def advstats_compare(self, ctx: commands.Context) -> None:
        """Compare several players on one chart."""
        pass

    async def _compare(self, ctx: commands.Context, metric: str, members, period: Period) -> None:
        members = list(dict.fromkeys(members))  # drop duplicates, keep order
        if len(members) > charts.MAX_SERIES:
            return await ctx.send(_("You can compare at most {n} players.").format(n=charts.MAX_SERIES))
        now = time.time()
        since = period.since(now)
        async with ctx.typing():
            if not members:
                members = await self._top_members(ctx.guild, metric)
            if metric == "gold":
                data = await self.stats_db.gold_series([m.id for m in members], since or 0)
            else:
                raw = await self.stats_db.level_series([m.id for m in members], since or 0)
                data = {uid: [(ts, lvl) for ts, lvl, _ in rows] for uid, rows in raw.items()}
            series = [(m.display_name, data[m.id]) for m in members if m.id in data]
            if len(series) < 2:
                return await ctx.send(_("Not enough recorded history to compare yet."))
            file = await self._render(charts.compare_chart, metric.title(), period.label, series, since, now)
        await ctx.send(file=file)

    @advstats_compare.command(name="gold")
    @commands.bot_has_permissions(attach_files=True)
    async def advstats_compare_gold(
        self, ctx: commands.Context, members: commands.Greedy[discord.Member], period: Period = DEFAULT_PERIOD
    ) -> None:
        """Compare gold between players.

        With no players given, compares this server's top 5 by gold.
        Example: `[p]advstats compare gold @a @b @c 7d`
        """
        await self._compare(ctx, "gold", members, period)

    @advstats_compare.command(name="level")
    @commands.bot_has_permissions(attach_files=True)
    async def advstats_compare_level(
        self, ctx: commands.Context, members: commands.Greedy[discord.Member], period: Period = DEFAULT_PERIOD
    ) -> None:
        """Compare levels between players.

        With no players given, compares this server's top 5 by rebirth then level.
        Example: `[p]advstats compare level @a @b all`
        """
        await self._compare(ctx, "level", members, period)
