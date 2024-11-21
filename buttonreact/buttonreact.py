import asyncio
import discord
from discord.ext import commands
from discord.ui import View, Button
from typing import Dict, List

class ButtonReact(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.button_reactions: Dict[int, Dict[str, List[str]]] = {}  # Server-specific word-button mapping

    class ButtonReactView(View):
        def __init__(self, cog, buttons: list):
            super().__init__(timeout=None)
            self.cog = cog
            self.user_data = {}  # Track user clicks per button
            for label in buttons:
                self.add_item(self.cog.ButtonReactButton(label, self.user_data))

    class ButtonReactButton(Button):
        def __init__(self, label: str, user_data: dict):
            super().__init__(label=label, style=discord.ButtonStyle.primary)
            self.user_data = user_data  # Shared state for button clicks

        async def callback(self, interaction: discord.Interaction):
            username = interaction.user.name[:2]  # First 2 letters of the username
            if self.label not in self.user_data:
                self.user_data[self.label] = []

            if username not in self.user_data[self.label]:
                self.user_data[self.label].append(username)
            else:
                await interaction.response.send_message(
                    "You've already clicked this button!", ephemeral=True
                )
                return

            # Update the button label dynamically
            new_label = f"{self.label.split('(')[0].strip()} ({', '.join(self.user_data[self.label])})"
            self.label = new_label

            # Update the message view
            await interaction.message.edit(view=self.view)
            await interaction.response.defer()  # Acknowledge the interaction silently

    @commands.hybrid_command(name="buttonreact")
    @commands.bot_has_permissions(read_message_history=True, add_reactions=True, embed_links=True)
    async def button_react(self, ctx: commands.Context):
        """
        Sends a message with interactive buttons.
        Each time a button is clicked, the user's initials are appended to the button.
        """
        buttons = ["Option 1", "Option 2", "Option 3"]  # Customize your buttons here
        view = self.ButtonReactView(self, buttons)
        await ctx.send("Click a button to participate:", view=view)

    @commands.hybrid_command(name="addbutton")
    @commands.bot_has_permissions(embed_links=True)
    async def addbutton(self, ctx, word: str, button: str):
        """
        Add an auto reaction to a word.
        """
        guild_id = ctx.guild.id
        if guild_id not in self.button_reactions:
            self.button_reactions[guild_id] = {}

        if word not in self.button_reactions[guild_id]:
            self.button_reactions[guild_id][word] = []

        if button not in self.button_reactions[guild_id][word]:
            self.button_reactions[guild_id][word].append(button)
            await ctx.send(f"Added button '{button}' for the word '{word}'.")
        else:
            await ctx.send(f"The button '{button}' is already assigned to the word '{word}'.")

    @commands.hybrid_command(name="delbutton")
    @commands.bot_has_permissions(embed_links=True)
    async def delbutton(self, ctx, word: str, button: str):
        """
        Delete an auto reaction to a word.
        """
        guild_id = ctx.guild.id
        if guild_id in self.button_reactions and word in self.button_reactions[guild_id]:
            if button in self.button_reactions[guild_id][word]:
                self.button_reactions[guild_id][word].remove(button)
                await ctx.send(f"Removed button '{button}' from the word '{word}'.")
                if not self.button_reactions[guild_id][word]:
                    del self.button_reactions[guild_id][word]
            else:
                await ctx.send(f"The button '{button}' is not assigned to the word '{word}'.")
        else:
            await ctx.send(f"No buttons are assigned to the word '{word}'.")

    @commands.hybrid_command(name="delallbutton")
    @commands.bot_has_permissions(embed_links=True)
    async def delallbutton(self, ctx):
        """
        Delete ALL button reactions in the server.
        """
        guild_id = ctx.guild.id
        if guild_id in self.button_reactions:
            self.button_reactions[guild_id] = {}
            await ctx.send("Deleted all button reactions for this server.")
        else:
            await ctx.send("No button reactions found for this server.")

    @commands.hybrid_command(name="listbutton")
    @commands.bot_has_permissions(embed_links=True)
    async def listbutton(self, ctx):
        """
        List button reactions for this server.
        """
        guild_id = ctx.guild.id
        if guild_id in self.button_reactions and self.button_reactions[guild_id]:
            embed = discord.Embed(title="Button Reactions", color=discord.Color.blue())
            for word, buttons in self.button_reactions[guild_id].items():
                embed.add_field(name=word, value=", ".join(buttons), inline=False)
            await ctx.send(embed=embed)
        else:
            await ctx.send("No button reactions are configured for this server.")

async def setup(bot):
    await bot.add_cog(ButtonReact(bot))
