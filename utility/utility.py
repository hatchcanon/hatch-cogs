import discord
from redbot.core import commands, app_commands, Config
from redbot.core.bot import Red
import logging
import requests

log = logging.getLogger("red.utility")


class Utility(commands.Cog):
    """
    Utility commands including Womp's foraging adventure
    """

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890, force_registration=True)
        default_global = {
            "api_key": None
        }
        self.config.register_global(**default_global)

    async def cog_load(self):
        """Called when the cog is loaded"""
        log.info("Utility cog loaded")

    async def cog_unload(self):
        """Called when the cog is unloaded"""
        log.info("Utility cog unloaded")

    async def get_random_word(self, part_of_speech: str) -> str:
        """
        Fetch a random word of the specified part of speech from Words API.

        Args:
            part_of_speech: 'adjective', 'noun', or 'verb'

        Returns:
            A random word string, or None if the request fails
        """
        api_key = await self.config.api_key()
        if not api_key:
            return None

        url = f"https://wordsapiv1.p.rapidapi.com/words?partOfSpeech={part_of_speech}&random=true"

        headers = {
            "X-Mashape-Key": api_key,
            "X-Mashape-Host": "wordsapiv1.p.rapidapi.com"
        }

        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()
            return data.get('word', None)
        except requests.exceptions.RequestException as e:
            log.error(f"Error fetching {part_of_speech}: {e}")
            return None

    async def generate_womp_phrase(self) -> str:
        """
        Generate a phrase where Womp finds a random item.

        Returns:
            A formatted string with the phrase, or an error message
        """
        # Check if API key is set
        api_key = await self.config.api_key()
        if not api_key:
            return "Error: No API key set! Please use `[p]womp api <your_api_key>` to set your Words API key."

        # Fetch random words
        adjective = await self.get_random_word('adjective')
        noun = await self.get_random_word('noun')
        verb = await self.get_random_word('verb')

        # Check if all words were successfully retrieved
        if not all([adjective, noun, verb]):
            return "Error: Could not fetch all words from the API."

        # Format and return the phrase
        phrase = f"Womp goes foraging and finds you a {adjective} {noun}. Would you like to {verb} it, sell it, or equip it?"
        return phrase

    @commands.group(name="womp")
    async def womp_group(self, ctx: commands.Context):
        """Womp commands"""
        if ctx.invoked_subcommand is None:
            await ctx.send("Use `[p]womp forage` to go foraging or `[p]womp api <key>` to set your API key!")

    @womp_group.command(name="forage")
    async def womp_forage(self, ctx: commands.Context):
        """Womp goes foraging and finds you something random!"""
        phrase = await self.generate_womp_phrase()
        await ctx.send(phrase)

    @womp_group.command(name="api")
    @commands.is_owner()
    async def womp_api(self, ctx: commands.Context, api_key: str):
        """Set the Words API key for womp foraging"""
        await self.config.api_key.set(api_key)
        await ctx.send("API key has been set successfully!")
        # Delete the message to protect the API key
        try:
            await ctx.message.delete()
        except discord.Forbidden:
            await ctx.send("Warning: Could not delete your message. Please manually delete it to protect your API key.")

    @app_commands.command(name="womp", description="Womp goes foraging and finds you something random!")
    @app_commands.guild_only()
    async def womp_slash(self, interaction: discord.Interaction):
        """Womp goes foraging and finds you something random!"""
        phrase = await self.generate_womp_phrase()
        await interaction.response.send_message(phrase)


async def setup(bot: Red):
    """Load the cog"""
    cog = Utility(bot)
    await bot.add_cog(cog)
