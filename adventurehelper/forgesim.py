import logging
import sys
from typing import Dict, List, Optional

import discord
from redbot.core import commands
from redbot.core.i18n import Translator

from .abc import MixinMeta
from .forgemath import AVERAGE_ROLL, STATS, Loadout, SimItem, forge, roll_modifier, simulate_chain, stat_modifier
from .views import text_view

log = logging.getLogger("red.adventurehelper.forgesim")

_ = Translator("AdventureHelper", __file__)

MY_CHARACTER = "__me__"
NO_GEAR = "__none__"
FORGE_COUNTS = (1, 3, 5, 10)
ROLL_CHOICES = ["avg"] + [str(r) for r in range(1, 21)]


def _is_two_handed(data: dict) -> bool:
    return len(data.get("slot", [])) > 1


def _set_item(name: str, data: dict) -> SimItem:
    return SimItem(name, {s: int(data.get(s, 0)) for s in STATS}, two_handed=_is_two_handed(data))


def _stat_line(stats: Dict[str, int]) -> str:
    return " | ".join(f"{s.upper()} {stats.get(s, 0)}" for s in STATS)


def _row(label: str, stats: Dict[str, int]) -> str:
    return f"{label:<8}" + "".join(f"{stats.get(s, 0):>7}" for s in STATS)


class ForgeSimView(discord.ui.LayoutView):
    def __init__(
        self,
        author: discord.abc.User,
        sets: Dict[str, Dict[str, dict]],
        forgeable_sets: List[str],
        my_loadout: Optional[Loadout],
        cap: float,
        forge_limit: int,
    ):
        super().__init__(timeout=600)
        self.author = author
        self.sets = sets
        self.forgeable_sets = forgeable_sets
        self.my_loadout = my_loadout
        self.cap = cap
        self.forge_limit = forge_limit
        self.message: Optional[discord.Message] = None

        self.input_set = forgeable_sets[0]
        pieces = list(sets[self.input_set])
        self.piece1 = pieces[0]
        self.piece2 = pieces[1] if len(pieces) > 1 else pieces[0]
        self.build = MY_CHARACTER if my_loadout is not None else NO_GEAR
        self.build_pieces = 0
        self.roll = "avg"
        self.forges = 1
        self.render()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message(_("This simulator isn't yours."), ephemeral=True)
            return False
        return True

    async def on_timeout(self) -> None:
        if self.message is None:
            return
        self.render(controls=False)
        try:
            await self.message.edit(view=self)
        except discord.HTTPException:
            pass

    # ---- state -> numbers ----

    def _loadout(self) -> Loadout:
        if self.build == MY_CHARACTER and self.my_loadout is not None:
            return self.my_loadout
        if self.build == NO_GEAR:
            return Loadout()
        items, slots = [], 0
        for name, data in self.sets[self.build].items():
            item = _set_item(name, data)
            if len(items) >= self.build_pieces or slots + item.slots > 11:
                break
            items.append(item)
            slots += item.slots
        return Loadout(items)

    def _build_label(self) -> str:
        if self.build == MY_CHARACTER:
            return _("your current gear")
        if self.build == NO_GEAR:
            return _("no gear")
        return _("{count} pieces of {set}").format(count=self.build_pieces, set=self.build)

    def _roll_value(self) -> float:
        return AVERAGE_ROLL if self.roll == "avg" else float(self.roll)

    def _roll_label(self) -> str:
        return _("average (10.5)") if self.roll == "avg" else self.roll

    def _results(self) -> str:
        item1 = _set_item(self.piece1, self.sets[self.input_set][self.piece1])
        item2 = _set_item(self.piece2, self.sets[self.input_set][self.piece2])
        loadout = self._loadout()
        raw = loadout.raw()
        roll = self._roll_value()

        if self.forges == 1:
            bonus_raw, bonus = stat_modifier(raw, self.cap)
            roll_mod = roll_modifier(roll)
            device = forge(item1, item2, raw, roll, self.cap)
            totals = [sum(forge(item1, item2, raw, r, self.cap).values()) for r in (1, AVERAGE_ROLL, 20)]
            table = "\n".join(
                [
                    f"{'':<8}" + "".join(f"{s.upper():>7}" for s in STATS),
                    _row("Item 1", item1.stats),
                    _row("Item 2", item2.stats),
                    _row("Device", device),
                ]
            )
            return _(
                "**Character raw stats:** {raw}\n"
                "**Modifier:** roll {roll_mod:.2f} + stats {bonus:.2f} (soft cap of {raw_bonus:.2f}) "
                "= **{total:.2f}** → inputs × {mult:.2f}\n"
                "```\n{table}\n```"
                "Device total stats — roll 1: **{low}** · average: **{avg}** · roll 20: **{high}**"
            ).format(
                raw=_stat_line(raw),
                roll_mod=roll_mod,
                bonus=bonus,
                raw_bonus=bonus_raw,
                total=roll_mod + bonus,
                mult=roll_mod + bonus + 1,
                table=table,
                low=totals[0],
                avg=totals[1],
                high=totals[2],
            )

        steps = simulate_chain(loadout, item1, item2, roll, self.cap, self.forges, self.forge_limit)
        header = f"{'#':<3}{'Raw INT':>8}{'Bonus':>7}" + "".join(f"{s.upper():>6}" for s in STATS)
        lines = [header]
        for n, step in enumerate(steps, 1):
            lines.append(
                f"{n:<3}{step.raw['int']:>8}{step.bonus:>7.2f}" + "".join(f"{step.device[s]:>6}" for s in STATS)
            )
        actions = "\n".join(f"**#{n}:** {step.action}" for n, step in enumerate(steps, 1))
        return _(
            "Forging the same two items {count} times. Each device is equipped if it beats your weakest "
            "gear (max {limit} devices) before the next forge.\n```\n{table}\n```{actions}"
        ).format(count=self.forges, limit=self.forge_limit, table="\n".join(lines), actions=actions)

    # ---- rendering ----

    def render(self, controls: bool = True) -> None:
        self.clear_items()
        container = discord.ui.Container(accent_colour=discord.Colour.from_rgb(232, 120, 190))
        container.add_item(discord.ui.TextDisplay(_("### Forge Simulator")))
        container.add_item(
            discord.ui.TextDisplay(
                _(
                    "**Forging:** {p1} + {p2} ({set})\n"
                    "**Character:** {build}\n"
                    "**Roll:** {roll} · **Forges:** {forges}"
                ).format(
                    p1=self.piece1,
                    p2=self.piece2,
                    set=self.input_set,
                    build=self._build_label(),
                    roll=self._roll_label(),
                    forges=self.forges,
                )
            )
        )
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(self._results()))
        if controls:
            container.add_item(discord.ui.Separator())
            for select in self._selects():
                container.add_item(discord.ui.ActionRow(select))
            container.add_item(discord.ui.ActionRow(*self._buttons()))
        self.add_item(container)

    def _selects(self) -> List[discord.ui.Select]:
        selects = [
            _SimSelect(
                "input_set",
                _("Set to forge from"),
                [discord.SelectOption(label=s[:100], value=s, default=s == self.input_set) for s in self.forgeable_sets],
            )
        ]
        pieces = self.sets[self.input_set]
        for key, current, placeholder in (
            ("piece1", self.piece1, _("Item 1")),
            ("piece2", self.piece2, _("Item 2")),
        ):
            selects.append(
                _SimSelect(
                    key,
                    placeholder,
                    [
                        discord.SelectOption(
                            label=name[:100],
                            value=name,
                            description=_stat_line(data)[:100],
                            default=name == current,
                        )
                        for name, data in pieces.items()
                    ],
                )
            )

        build_options = []
        if self.my_loadout is not None:
            build_options.append(
                discord.SelectOption(label=_("My character"), value=MY_CHARACTER, default=self.build == MY_CHARACTER)
            )
        build_options.append(discord.SelectOption(label=_("No gear"), value=NO_GEAR, default=self.build == NO_GEAR))
        build_options += [
            discord.SelectOption(label=_("Wearing {set}").format(set=s)[:100], value=s, default=self.build == s)
            for s in list(self.sets)[: 25 - len(build_options)]
        ]
        selects.append(_SimSelect("build", _("Character gear"), build_options))

        if self.build in self.sets:
            count = len(self.sets[self.build])
            selects.append(
                _SimSelect(
                    "build_pieces",
                    _("Pieces worn"),
                    [
                        discord.SelectOption(
                            label=_("{n} pieces").format(n=n), value=str(n), default=n == self.build_pieces
                        )
                        for n in range(1, count + 1)
                    ],
                )
            )

        selects.append(
            _SimSelect(
                "roll",
                _("Forge roll"),
                [
                    discord.SelectOption(
                        label=_("Average roll") if r == "avg" else _("Roll {r}").format(r=r),
                        value=r,
                        default=r == self.roll,
                    )
                    for r in ROLL_CHOICES
                ],
            )
        )
        return selects

    def _buttons(self) -> List[discord.ui.Button]:
        forges = discord.ui.Button(
            label=_("Forges: {n}").format(n=self.forges), style=discord.ButtonStyle.primary
        )
        forges.callback = self._cycle_forges
        close = discord.ui.Button(label=_("Close"), style=discord.ButtonStyle.secondary)
        close.callback = self._close
        return [forges, close]

    # ---- callbacks ----

    async def on_select(self, interaction: discord.Interaction, key: str, value: str) -> None:
        if key == "input_set":
            self.input_set = value
            pieces = list(self.sets[value])
            self.piece1 = pieces[0]
            self.piece2 = pieces[1] if len(pieces) > 1 else pieces[0]
        elif key == "build":
            self.build = value
            if value in self.sets:
                self.build_pieces = len(self.sets[value])
        elif key == "build_pieces":
            self.build_pieces = int(value)
        else:
            setattr(self, key, value)
        self.render()
        await interaction.response.edit_message(view=self)

    async def _cycle_forges(self, interaction: discord.Interaction) -> None:
        self.forges = FORGE_COUNTS[(FORGE_COUNTS.index(self.forges) + 1) % len(FORGE_COUNTS)]
        self.render()
        await interaction.response.edit_message(view=self)

    async def _close(self, interaction: discord.Interaction) -> None:
        self.render(controls=False)
        self.stop()
        await interaction.response.edit_message(view=self)


class _SimSelect(discord.ui.Select):
    def __init__(self, key: str, placeholder: str, options: List[discord.SelectOption]):
        super().__init__(placeholder=placeholder, options=options)
        self.key = key

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.view.on_select(interaction, self.key, self.values[0])


class ForgeSimulator(MixinMeta):
    """Simulate Tinkerer forges with set pieces."""

    async def _my_loadout(self, ctx: commands.Context, adv_cog, adv_pkg: str) -> Optional[Loadout]:
        Character = sys.modules[adv_pkg + ".charsheet"].Character
        Rarities = sys.modules[adv_pkg + ".constants"].Rarities
        Slot = sys.modules[adv_pkg + ".constants"].Slot
        try:
            c = await Character.from_json(ctx, adv_cog.config, ctx.author, adv_cog._daily_bonus)
        except Exception:
            log.exception("Could not load %s's character for the forge simulator", ctx.author.id)
            return None
        items = []
        for slot in Slot:
            if slot is Slot.two_handed:
                continue
            item = getattr(c, slot.name)
            if item is None:
                continue
            # two handed items sit in both hands, so they show up once per hand here
            items.append(
                SimItem(item.name, {s: int(getattr(item, s)) for s in STATS}, forged=item.rarity is Rarities.forged)
            )
        loadout = Loadout(items)
        loadout.extra = c._att - loadout.raw()["att"]
        return loadout

    @commands.command(name="forgesim")
    async def forgesim(self, ctx: commands.Context) -> None:
        """Simulate Tinkerer forges with set pieces.

        Pick the two set pieces to forge, the gear your character wears, the forge roll and how
        many times to forge in a row. Uses the live forge formula and your current gear by default.
        """
        adv_cog = self.bot.get_cog("Adventure")
        if not adv_cog:
            return await ctx.send(view=text_view(_("Adventure cog not found.")))
        adv_pkg = type(adv_cog).__module__.rsplit(".", 1)[0]
        class_abilities = sys.modules.get(adv_pkg + ".class_abilities")
        constants = sys.modules[adv_pkg + ".constants"]
        cap = getattr(class_abilities, "FORGE_STAT_MODIFIER_CAP", 1.0)
        forge_limit = getattr(class_abilities, "FORGE_LIMIT", 3)
        unforgeable = getattr(constants, "UNFORGEABLE_SETS", set())

        sets: Dict[str, Dict[str, dict]] = {}
        for name, data in adv_cog.TR_GEAR_SET.items():
            sets.setdefault(data.get("set", name), {})[name] = data
        sets = dict(list(sorted(sets.items()))[:23])  # leave room for the "My character" / "No gear" options
        forgeable_sets = [s for s in sets if s not in unforgeable][:25]
        if not forgeable_sets:
            return await ctx.send(view=text_view(_("There are no forgeable sets in the current theme.")))

        my_loadout = await self._my_loadout(ctx, adv_cog, adv_pkg)
        view = ForgeSimView(ctx.author, sets, forgeable_sets, my_loadout, cap, forge_limit)
        view.message = await ctx.send(view=view)
