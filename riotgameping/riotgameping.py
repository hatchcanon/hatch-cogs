import asyncio
import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import List, Optional, Set

import discord
from redbot.core import Config, app_commands, commands
from redbot.core.bot import Red

log = logging.getLogger("red.riotgameping")

NO_MENTIONS = discord.AllowedMentions.none()


@dataclass(frozen=True)
class Game:
    name: str
    config_key: str  # guild config key holding this game's ping role ID
    colour: discord.Colour


VALORANT = Game("Valorant", "val_role", discord.Colour.red())
LEAGUE = Game("League of Legends", "lol_role", discord.Colour.blue())
GAMES = (VALORANT, LEAGUE)


class GamePingButtons(discord.ui.ActionRow):
    """Join / Can't Anymore buttons for a game ping"""

    @discord.ui.button(label="Join", style=discord.ButtonStyle.success)
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
        view: RiotGamePingView = self.view
        if view.closed:
            await interaction.response.send_message("This game ping is no longer active.", ephemeral=True)
            return
        if interaction.user.id in view.joined_users:
            await interaction.response.send_message("You have already joined this game!", ephemeral=True)
            return

        view.joined_users.append(interaction.user.id)
        if not view.is_full:
            view.show_open()
            await interaction.response.edit_message(view=view, allowed_mentions=NO_MENTIONS)
            return

        view.show_closed("Filled", "Game is ready to start!", discord.Colour.green())
        view.close()
        await interaction.response.edit_message(view=view, allowed_mentions=NO_MENTIONS)
        mentions = " ".join(f"<@{user_id}>" for user_id in view.joined_users)
        await interaction.channel.send(f"{mentions} - Your **{view.game.name}** game is ready!")

    @discord.ui.button(label="Can't Anymore", style=discord.ButtonStyle.danger)
    async def leave(self, interaction: discord.Interaction, button: discord.ui.Button):
        view: RiotGamePingView = self.view
        if view.closed:
            await interaction.response.send_message("This game ping is no longer active.", ephemeral=True)
            return
        if interaction.user.id not in view.joined_users:
            await interaction.response.send_message(
                "You need to join the game first before you can leave!", ephemeral=True
            )
            return

        if interaction.user.id == view.author_id:
            # The host leaving cancels the whole ping
            view.show_closed("Cancelled", "Game cancelled by the host.", discord.Colour.red())
            view.close()
        else:
            view.joined_users.remove(interaction.user.id)
            view.show_open()
        await interaction.response.edit_message(view=view, allowed_mentions=NO_MENTIONS)


class RiotGamePingView(discord.ui.LayoutView):
    """Components v2 view for a game ping"""

    def __init__(
        self,
        cog: "RiotGamePing",
        game: Game,
        role: discord.Role,
        players_needed: int,
        minutes_till_expiry: int,
        author_id: int,
    ):
        # No view timeout: it resets on every click, and the ping must expire at a fixed time
        super().__init__(timeout=None)
        self.cog = cog
        self.game = game
        self.players_needed = players_needed  # in addition to the host
        self.author_id = author_id
        self.joined_users: List[int] = [author_id]
        self.header = f"{role.mention} Looking for **{players_needed}** players!"
        self.lifetime = timedelta(minutes=minutes_till_expiry)
        self.expires_at = discord.utils.utcnow() + self.lifetime
        self.message: Optional[discord.PartialMessage] = None
        self.closed = False
        self.buttons = GamePingButtons()
        self._expiry_task: Optional[asyncio.Task] = None
        self.show_open()

    @property
    def is_full(self) -> bool:
        return len(self.joined_users) > self.players_needed

    def show_open(self) -> None:
        """Rebuild the layout for a ping that is still looking for players"""
        status = (
            f"**{len(self.joined_users) - 1}/{self.players_needed}** players"
            f" · expires <t:{int(self.expires_at.timestamp())}:R>"
        )
        self._render(self.game.name, status, self.game.colour, buttons=True)

    def show_closed(self, state: str, description: str, colour: discord.Colour) -> None:
        """Rebuild the layout for a ping that was filled, cancelled or expired"""
        self._render(f"{self.game.name} - {state}", description, colour)

    def _render(self, title: str, body: str, colour: discord.Colour, *, buttons: bool = False) -> None:
        items = [
            discord.ui.TextDisplay(f"## {title}\n{body}"),
            discord.ui.Separator(),
            discord.ui.TextDisplay("\n".join(f"<@{user_id}>" for user_id in self.joined_users)),
        ]
        if buttons:
            items += [discord.ui.Separator(), self.buttons]

        self.clear_items()
        self.add_item(discord.ui.TextDisplay(self.header))
        self.add_item(discord.ui.Container(*items, accent_colour=colour))

    def start(self, message: discord.PartialMessage) -> None:
        """Attach the sent message and start the expiry countdown"""
        self.message = message
        self.cog.active_views.add(self)
        self._expiry_task = asyncio.create_task(self._expire())

    def close(self) -> None:
        """Stop accepting clicks and cancel the pending expiry"""
        self.closed = True
        if self._expiry_task:
            self._expiry_task.cancel()
            self._expiry_task = None
        self.cog.active_views.discard(self)
        self.stop()

    async def _expire(self) -> None:
        await asyncio.sleep(self.lifetime.total_seconds())
        self._expiry_task = None  # so close() doesn't cancel this task mid-edit
        if self.closed:
            return

        self.show_closed("Cancelled", "Not enough players joined in time.", discord.Colour.red())
        self.close()
        try:
            await self.message.edit(view=self, allowed_mentions=NO_MENTIONS)
        except discord.HTTPException:
            log.exception("Failed to update expired %s game ping", self.game.name)


class RiotGamePing(commands.Cog):
    """
    Create game pings for Riot Games (Valorant and League of Legends)
    """

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=0x52474150, force_registration=True)
        self.config.register_guild(**{game.config_key: None for game in GAMES})
        self.active_views: Set[RiotGamePingView] = set()

    async def cog_unload(self):
        for view in list(self.active_views):
            view.close()

    @app_commands.command(name="val", description="Look for players for Valorant")
    @app_commands.describe(
        players_needed="Number of players needed (default: 4)",
        minutes_till_expiry="Number of minutes until this ping expires (default: 30)",
    )
    @app_commands.guild_only()
    async def valorant_ping(
        self,
        interaction: discord.Interaction,
        players_needed: app_commands.Range[int, 1, 10] = 4,
        minutes_till_expiry: app_commands.Range[int, 10, 60] = 30,
    ):
        """Create a Valorant game ping"""
        await self._create_game_ping(interaction, VALORANT, players_needed, minutes_till_expiry)

    @app_commands.command(name="lol", description="Look for players for League of Legends")
    @app_commands.describe(
        players_needed="Number of players needed (default: 4)",
        minutes_till_expiry="Number of minutes until this ping expires (default: 30)",
    )
    @app_commands.guild_only()
    async def lol_ping(
        self,
        interaction: discord.Interaction,
        players_needed: app_commands.Range[int, 1, 10] = 4,
        minutes_till_expiry: app_commands.Range[int, 10, 60] = 30,
    ):
        """Create a League of Legends game ping"""
        await self._create_game_ping(interaction, LEAGUE, players_needed, minutes_till_expiry)

    async def _create_game_ping(
        self,
        interaction: discord.Interaction,
        game: Game,
        players_needed: int,
        minutes_till_expiry: int,
    ):
        role_id = await self.config.guild(interaction.guild).get_attr(game.config_key)()
        role = interaction.guild.get_role(role_id) if role_id else None
        if not role:
            await interaction.response.send_message(
                f"No {game.name} role is set up for this server. Please contact an admin.",
                ephemeral=True,
            )
            return

        view = RiotGamePingView(self, game, role, players_needed, minutes_till_expiry, interaction.user.id)
        # Ping the role only; the host's mention in the player list should stay silent
        await interaction.response.send_message(
            view=view,
            allowed_mentions=discord.AllowedMentions(everyone=False, users=False, roles=[role]),
        )

        # Keep a bot-token handle on the message: the interaction token dies after
        # 15 minutes, well before a ping can expire
        message = await interaction.original_response()
        view.start(interaction.channel.get_partial_message(message.id))

    @commands.group(name="gamepingset")
    @commands.guild_only()
    @commands.admin_or_permissions(administrator=True)
    async def gamepingset(self, ctx: commands.Context):
        """Configure the roles pinged by /val and /lol"""

    @gamepingset.command(name="val")
    async def gamepingset_val(self, ctx: commands.Context, role: Optional[discord.Role] = None):
        """Set the role pinged by /val. Leave blank to clear it."""
        await self._set_role(ctx, VALORANT, role)

    @gamepingset.command(name="lol")
    async def gamepingset_lol(self, ctx: commands.Context, role: Optional[discord.Role] = None):
        """Set the role pinged by /lol. Leave blank to clear it."""
        await self._set_role(ctx, LEAGUE, role)

    @gamepingset.command(name="show")
    async def gamepingset_show(self, ctx: commands.Context):
        """Show the currently configured ping roles"""
        lines = []
        for game in GAMES:
            role_id = await self.config.guild(ctx.guild).get_attr(game.config_key)()
            role = ctx.guild.get_role(role_id) if role_id else None
            lines.append(f"**{game.name}:** {role.mention if role else 'Not set'}")
        await ctx.send("\n".join(lines), allowed_mentions=NO_MENTIONS)

    async def _set_role(self, ctx: commands.Context, game: Game, role: Optional[discord.Role]):
        await self.config.guild(ctx.guild).get_attr(game.config_key).set(role.id if role else None)
        if role:
            await ctx.send(f"{game.name} pings will now mention {role.mention}.", allowed_mentions=NO_MENTIONS)
        else:
            await ctx.send(f"{game.name} ping role cleared.")
