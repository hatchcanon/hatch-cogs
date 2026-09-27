import io
import logging
import re
from typing import Optional

import aiohttp
import discord
from redbot.core import app_commands, commands
from redbot.core.bot import Red

log = logging.getLogger("red.emojisteal")

PAGE_SIZE = 20


class EmojiSteal(commands.Cog):
    """
    Copy emojis and stickers from other servers into this one, and list what's already here.
    """

    def __init__(self, bot: Red):
        self.bot = bot
        self.session: Optional[aiohttp.ClientSession] = None

    async def cog_load(self):
        self.session = aiohttp.ClientSession()
        log.info("EmojiSteal cog loaded")

    async def cog_unload(self):
        if self.session:
            await self.session.close()
        log.info("EmojiSteal cog unloaded")

    async def _send_list(self, ctx: commands.Context, title: str, items: list, empty_msg: str):
        if not items:
            await ctx.send(empty_msg)
            return
        chunks = [items[i:i + PAGE_SIZE] for i in range(0, len(items), PAGE_SIZE)]
        color = await ctx.embed_color()
        for idx, chunk in enumerate(chunks, start=1):
            page_suffix = f" - Page {idx}/{len(chunks)}" if len(chunks) > 1 else ""
            embed = discord.Embed(
                title=f"{title} ({len(items)}){page_suffix}",
                description="\n".join(chunk),
                color=color,
            )
            await ctx.send(embed=embed)

    @commands.hybrid_group(name="emote", invoke_without_command=True)
    @commands.guild_only()
    async def emote(self, ctx: commands.Context):
        """Copy and list custom emojis."""
        await ctx.send_help(ctx.command)

    @emote.command(name="copy", aliases=["steal", "add"])
    @commands.guild_only()
    @commands.bot_has_permissions(manage_emojis_and_stickers=True)
    @commands.has_permissions(manage_emojis_and_stickers=True)
    @app_commands.describe(
        emoji="The custom emoji to copy (paste it, e.g. :thing:)",
        name="Optional name for the new emoji",
    )
    async def emoji_copy(
        self,
        ctx: commands.Context,
        emoji: discord.PartialEmoji,
        *,
        name: Optional[str] = None,
    ):
        """Copy a custom emoji into this server.

        Paste the emoji itself (e.g. `[p]emote copy :thing: newname`).
        """
        await ctx.defer()

        if emoji.id is None:
            await ctx.send("That's a default Discord emoji, there's nothing to copy.")
            return

        if len(ctx.guild.emojis) >= ctx.guild.emoji_limit:
            await ctx.send(f"This server is already at its emoji limit ({ctx.guild.emoji_limit}).")
            return

        emoji_name = re.sub(r"[^a-zA-Z0-9_]", "", name or emoji.name) or "emoji"
        emoji_name = emoji_name[:32].ljust(2, "_")

        try:
            async with self.session.get(str(emoji.url)) as resp:
                if resp.status != 200:
                    await ctx.send("Couldn't download that emoji.")
                    return
                image_bytes = await resp.read()

            new_emoji = await ctx.guild.create_custom_emoji(
                name=emoji_name,
                image=image_bytes,
                reason=f"Copied by {ctx.author} ({ctx.author.id})",
            )
        except discord.HTTPException as e:
            await ctx.send(f"Failed to create emoji: {getattr(e, 'text', e)}")
            return

        await ctx.send(f"Added {new_emoji} as `:{new_emoji.name}:`")

    @emote.command(name="list", aliases=["ls"])
    @commands.guild_only()
    async def emoji_list(self, ctx: commands.Context):
        """List every custom emoji in this server."""
        await ctx.defer()
        emojis = sorted(ctx.guild.emojis, key=lambda e: e.name.lower())
        lines = [f"{e} `:{e.name}:`" + (" (animated)" if e.animated else "") for e in emojis]
        await self._send_list(ctx, f"Emojis in {ctx.guild.name}", lines, "This server has no custom emojis.")

    @commands.hybrid_group(name="sticker", invoke_without_command=True)
    @commands.guild_only()
    async def sticker(self, ctx: commands.Context):
        """Copy and list stickers."""
        await ctx.send_help(ctx.command)

    @sticker.command(name="copy", aliases=["steal", "add"])
    @commands.guild_only()
    @commands.bot_has_permissions(manage_emojis_and_stickers=True)
    @commands.has_permissions(manage_emojis_and_stickers=True)
    @app_commands.describe(
        message="Message link/ID containing the sticker (skip this if you're replying or attaching it)",
        name="Optional name for the new sticker",
    )
    async def sticker_copy(
        self,
        ctx: commands.Context,
        message: Optional[discord.Message] = None,
        *,
        name: Optional[str] = None,
    ):
        """Copy a sticker into this server.

        Reply to a message with a sticker, attach one to your command message, or pass a message link/ID.
        """
        await ctx.defer()

        source = None
        if message is not None:
            if message.stickers:
                source = message.stickers[0]
        else:
            if ctx.message.stickers:
                source = ctx.message.stickers[0]
            elif ctx.message.reference and ctx.message.reference.resolved:
                resolved = ctx.message.reference.resolved
                if getattr(resolved, "stickers", None):
                    source = resolved.stickers[0]

        if source is None:
            await ctx.send(
                "Couldn't find a sticker. Reply to a message with one, attach it to your command, "
                "or pass a message link/ID."
            )
            return

        if len(ctx.guild.stickers) >= ctx.guild.sticker_limit:
            await ctx.send(f"This server is already at its sticker limit ({ctx.guild.sticker_limit}).")
            return

        try:
            full_sticker = await source.fetch()
        except discord.HTTPException:
            full_sticker = source

        if full_sticker.format is discord.StickerFormatType.lottie:
            await ctx.send("Animated (Lottie) stickers can't be copied.")
            return

        sticker_name = re.sub(r"[^a-zA-Z0-9_ ]", "", name or full_sticker.name).strip() or "sticker"
        sticker_name = sticker_name[:30].ljust(2, "_")

        description = getattr(full_sticker, "description", None) or sticker_name
        description = description[:100].ljust(2, ".")

        emoji_tag = "\N{WHITE QUESTION MARK ORNAMENT}"
        if isinstance(full_sticker, discord.GuildSticker) and getattr(full_sticker, "emoji", None):
            emoji_tag = full_sticker.emoji

        ext = "png" if full_sticker.format is discord.StickerFormatType.png else "apng"

        try:
            async with self.session.get(str(full_sticker.url)) as resp:
                if resp.status != 200:
                    await ctx.send("Couldn't download that sticker.")
                    return
                image_bytes = await resp.read()

            file = discord.File(io.BytesIO(image_bytes), filename=f"sticker.{ext}")
            new_sticker = await ctx.guild.create_sticker(
                name=sticker_name,
                description=description,
                emoji=emoji_tag,
                file=file,
                reason=f"Copied by {ctx.author} ({ctx.author.id})",
            )
        except discord.HTTPException as e:
            await ctx.send(f"Failed to create sticker: {getattr(e, 'text', e)}")
            return

        await ctx.send(f"Added sticker **{new_sticker.name}**.")

    @sticker.command(name="list", aliases=["ls"])
    @commands.guild_only()
    async def sticker_list(self, ctx: commands.Context):
        """List every sticker in this server."""
        await ctx.defer()
        stickers = sorted(ctx.guild.stickers, key=lambda s: s.name.lower())
        lines = [f"**{s.name}** (`{s.id}`)" for s in stickers]
        await self._send_list(ctx, f"Stickers in {ctx.guild.name}", lines, "This server has no stickers.")
