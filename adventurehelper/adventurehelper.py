from abc import ABC
from typing import Literal

import discord
from redbot.core import Config, checks, commands
from redbot.core.i18n import Translator, cog_i18n

from .listeners import AdventureHelperListeners

_ = Translator("AdventureHelper", __file__)


class CompositeMetaClass(type(commands.Cog), type(ABC)):
    """
    This allows the metaclass used for proper type detection to
    coexist with discord.py's metaclass

    This is from
    https://github.com/Cog-Creators/Red-DiscordBot/blob/V3/develop/redbot/cogs/mod/mod.py#L23
    """

    pass


@cog_i18n(_)
class AdventureHelper(
    AdventureHelperListeners,
    commands.Cog,
    metaclass=CompositeMetaClass,
):
    """Provide strategic guidance for adventure encounters based on enemy attributes"""

    __version__ = "1.0.0"
    __author__ = ["hatch"]

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, 154497072148643841, force_registration=True)
        self.config.register_guild(
            enabled=True,
        )
        # Initialize parent class to load attribs
        super().__init__()

    def format_help_for_context(self, ctx: commands.Context) -> str:
        pre_processed = super().format_help_for_context(ctx)
        return f"{pre_processed}\n\nCog Version: {self.__version__}"

    async def red_delete_data_for_user(
        self,
        *,
        requester: Literal["discord_deleted_user", "owner", "user", "user_strict"],
        user_id: int,
    ):
        """
        Method for finding users data inside the cog and deleting it.
        """
        # This cog doesn't store user-specific data
        pass

    @commands.group()
    @commands.guild_only()
    async def adventurehelper(self, ctx: commands.Context) -> None:
        """Configure AdventureHelper settings"""
        pass

    @adventurehelper.command(name="toggle")
    @checks.mod_or_permissions(manage_guild=True)
    async def toggle_helper(self, ctx: commands.Context) -> None:
        """
        Toggle adventure helper on/off for this server
        """
        current = await self.config.guild(ctx.guild).enabled()
        await self.config.guild(ctx.guild).enabled.set(not current)

        if not current:
            await ctx.send(_("AdventureHelper is now **enabled** for this server."))
        else:
            await ctx.send(_("AdventureHelper is now **disabled** for this server."))

    @adventurehelper.command(name="status")
    async def helper_status(self, ctx: commands.Context) -> None:
        """
        Check if adventure helper is enabled in this server
        """
        enabled = await self.config.guild(ctx.guild).enabled()
        status = _("enabled") if enabled else _("disabled")
        await ctx.send(
            _("AdventureHelper is currently **{status}** for this server.").format(status=status)
        )

    @adventurehelper.command(name="test")
    async def test_helper(self, ctx: commands.Context, *, attribute: str) -> None:
        """
        Test the helper with a specific attribute

        Example: `[p]adventurehelper test immortal`
        """
        # Create a fake message content with the attribute
        test_message = f"An adventure has begun with a{attribute} dragon!"

        # Temporarily store original message content
        original_content = ctx.message.content
        ctx.message.content = test_message

        # Analyze and send help
        await self.send_adventure_help(ctx)

        # Restore original content
        ctx.message.content = original_content
