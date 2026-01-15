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
            "api_key": None,
            "gemini_api_key": None
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

        # Format and return the phrase with item details
        phrase = f"Womp goes foraging and finds you a {adjective} {noun}. Would you like to {verb} it, sell it, or equip it?"
        return phrase, adjective, noun, verb

    async def get_gemini_response(self, action: str, adjective: str, noun: str, verb: str) -> str:
        """
        Call Gemini API to generate a D&D-style narrative response.

        Args:
            action: The action chosen ('verb', 'sell', or 'equip')
            adjective: The item's adjective
            noun: The item's noun
            verb: The random verb generated

        Returns:
            A narrative response with stat changes, or an error message
        """
        gemini_api_key = await self.config.gemini_api_key()
        if not gemini_api_key:
            return "Error: No Gemini API key set! Use `[p]womp geminiapi <your_api_key>` to set it."

        # Determine the action verb
        if action == "verb":
            action_verb = verb
        elif action == "sell":
            action_verb = "sell"
        else:  # equip
            action_verb = "equip"

        # Create the prompt
        prompt = f"""You are a Dungeon Master narrating the outcome of a player's action in a humorous D&D-style adventure.

The player chose to {action_verb} a {adjective} {noun}.

Generate a creative, entertaining response (2-3 sentences) describing what happens when they perform this action. Make it funny, dramatic, or unexpected.

Then, decide if this action would increase or decrease ONE of these stats: attack, charisma, or intelligence. The stat change should be between -3 to +3.

Format your response EXACTLY like this:
[Your 2-3 sentence narrative here]

Stat Change: [+/-][number] [stat name]

Example:
You bravely equip the rusty spoon as a helmet. It sits awkwardly on your head, and passersby can't help but laugh at your ridiculous appearance.

Stat Change: -2 Charisma"""

        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash-preview:generateContent?key={gemini_api_key}"

        headers = {
            "Content-Type": "application/json"
        }

        payload = {
            "contents": [{
                "parts": [{
                    "text": prompt
                }]
            }]
        }

        try:
            response = requests.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

            # Extract the text from Gemini's response
            if 'candidates' in data and len(data['candidates']) > 0:
                text = data['candidates'][0]['content']['parts'][0]['text']
                return text.strip()
            else:
                return "Error: Could not generate a response from Gemini."

        except requests.exceptions.RequestException as e:
            log.error(f"Error calling Gemini API: {e}")
            return f"Error: Could not connect to Gemini API. {str(e)}"


class WompActionView(discord.ui.View):
    """View with buttons for womp actions"""

    def __init__(self, cog, adjective: str, noun: str, verb: str):
        super().__init__(timeout=60.0)
        self.cog = cog
        self.adjective = adjective
        self.noun = noun
        self.verb = verb

        # Update the first button label with the random verb
        self.children[0].label = f"{verb.capitalize()} it"

    @discord.ui.button(label="Verb it", style=discord.ButtonStyle.primary)
    async def verb_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        response = await self.cog.get_gemini_response("verb", self.adjective, self.noun, self.verb)
        await interaction.followup.send(response)
        self.stop()

    @discord.ui.button(label="Sell it", style=discord.ButtonStyle.success)
    async def sell_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        response = await self.cog.get_gemini_response("sell", self.adjective, self.noun, self.verb)
        await interaction.followup.send(response)
        self.stop()

    @discord.ui.button(label="Equip it", style=discord.ButtonStyle.danger)
    async def equip_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        response = await self.cog.get_gemini_response("equip", self.adjective, self.noun, self.verb)
        await interaction.followup.send(response)
        self.stop()

    @commands.group(name="womp")
    async def womp_group(self, ctx: commands.Context):
        """Womp commands"""
        if ctx.invoked_subcommand is None:
            await ctx.send("Use `[p]womp forage` to go foraging, `[p]womp api <key>` to set your Words API key, or `[p]womp geminiapi <key>` to set your Gemini API key!")

    @womp_group.command(name="forage")
    async def womp_forage(self, ctx: commands.Context):
        """Womp goes foraging and finds you something random!"""
        result = await self.generate_womp_phrase()

        # Check if it's an error message
        if isinstance(result, str):
            await ctx.send(result)
            return

        phrase, adjective, noun, verb = result
        view = WompActionView(self, adjective, noun, verb)
        await ctx.send(phrase, view=view)

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

    @womp_group.command(name="geminiapi")
    @commands.is_owner()
    async def womp_gemini_api(self, ctx: commands.Context, api_key: str):
        """Set the Gemini API key for D&D-style responses"""
        await self.config.gemini_api_key.set(api_key)
        await ctx.send("Gemini API key has been set successfully!")
        # Delete the message to protect the API key
        try:
            await ctx.message.delete()
        except discord.Forbidden:
            await ctx.send("Warning: Could not delete your message. Please manually delete it to protect your API key.")

    @app_commands.command(name="womp", description="Womp goes foraging and finds you something random!")
    @app_commands.guild_only()
    async def womp_slash(self, interaction: discord.Interaction):
        """Womp goes foraging and finds you something random!"""
        result = await self.generate_womp_phrase()

        # Check if it's an error message
        if isinstance(result, str):
            await interaction.response.send_message(result)
            return

        phrase, adjective, noun, verb = result
        view = WompActionView(self, adjective, noun, verb)
        await interaction.response.send_message(phrase, view=view)


async def setup(bot: Red):
    """Load the cog"""
    cog = Utility(bot)
    await bot.add_cog(cog)
