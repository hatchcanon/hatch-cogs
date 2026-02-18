import re

import discord
from redbot.core import commands, app_commands, Config
from redbot.core.bot import Red
from copy import copy
import logging
import requests
import asyncio

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
            "gemini_api_key": None,
            "openrouter_api_key": None,
            "use_openrouter": False
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

        url = f"https://wordsapiv1.p.rapidapi.com/words?partOfSpeech={part_of_speech}&random=true&lettersMin=3&lettersMax=10"

        headers = {
            "X-Mashape-Key": api_key,
            "X-Mashape-Host": "wordsapiv1.p.rapidapi.com"
        }

        max_attempts = 5
        for _ in range(max_attempts):
            try:
                response = requests.get(url, headers=headers)
                response.raise_for_status()
                data = response.json()
                word = data.get('word', None)
                if word and ' ' not in word:
                    return word
            except requests.exceptions.RequestException as e:
                log.error(f"Error fetching {part_of_speech}: {e}")
                return None
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

    async def get_gemini_response(self, action: str, adjective: str, noun: str, verb: str, interaction: discord.Interaction = None) -> str:
        """
        Call Gemini API to generate a D&D-style narrative response.

        Args:
            action: The action chosen ('verb', 'sell', or 'equip')
            adjective: The item's adjective
            noun: The item's noun
            verb: The random verb generated
            interaction: Optional interaction for sending retry messages

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

        max_retries = 2
        for attempt in range(max_retries):
            try:
                response = requests.post(url, headers=headers, json=payload)

                # Check for 503 error and retry
                if response.status_code == 503 and attempt < max_retries - 1:
                    log.warning(f"Gemini API returned 503, retrying in 5 seconds...")
                    if interaction:
                        await interaction.followup.send("Retrying...")
                    await asyncio.sleep(5)
                    continue

                response.raise_for_status()
                data = response.json()

                # Extract the text from Gemini's response
                if 'candidates' in data and len(data['candidates']) > 0:
                    candidate = data['candidates'][0]

                    # Check if content was blocked or has no parts
                    if 'content' not in candidate or 'parts' not in candidate.get('content', {}):
                        finish_reason = candidate.get('finishReason', 'UNKNOWN')
                        log.warning(f"Gemini response missing content/parts. Finish reason: {finish_reason}")
                        if finish_reason == 'SAFETY':
                            return "The response was blocked by safety filters. Try again with a different item!"
                        return f"Error: Gemini returned an incomplete response (reason: {finish_reason}). Try again!"

                    text = candidate['content']['parts'][0]['text']
                    return text.strip()
                else:
                    return "Error: Could not generate a response from Gemini."

            except requests.exceptions.RequestException as e:
                log.error(f"Error calling Gemini API: {e}")
                return f"Error: Could not connect to Gemini API. {str(e)}"

        return "Error: Gemini API is currently unavailable (503). Please try again later."

    async def get_openrouter_response(self, action: str, adjective: str, noun: str, verb: str, interaction: discord.Interaction = None) -> str:
        """
        Call OpenRouter API to generate a D&D-style narrative response.

        Args:
            action: The action chosen ('verb', 'sell', or 'equip')
            adjective: The item's adjective
            noun: The item's noun
            verb: The random verb generated
            interaction: Optional interaction for sending retry messages

        Returns:
            A narrative response with stat changes, or an error message
        """
        openrouter_api_key = await self.config.openrouter_api_key()
        if not openrouter_api_key:
            return "Error: No OpenRouter API key set! Use `[p]womp openrouterapi <your_api_key>` to set it."

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

        url = "https://openrouter.ai/api/v1/chat/completions"

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {openrouter_api_key}"
        }

        payload = {
            "model": "arcee-ai/trinity-large-preview:free",
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        }

        max_retries = 2
        for attempt in range(max_retries):
            try:
                response = requests.post(url, headers=headers, json=payload)

                # Check for 503 error and retry
                if response.status_code == 503 and attempt < max_retries - 1:
                    log.warning(f"OpenRouter API returned 503, retrying in 5 seconds...")
                    if interaction:
                        await interaction.followup.send("Retrying...")
                    await asyncio.sleep(5)
                    continue

                response.raise_for_status()
                data = response.json()

                # Extract the text from OpenRouter's response
                if 'choices' in data and len(data['choices']) > 0:
                    choice = data['choices'][0]
                    if 'message' in choice and 'content' in choice['message']:
                        text = choice['message']['content']
                        return text.strip()
                    else:
                        return "Error: OpenRouter returned an incomplete response. Try again!"
                else:
                    return "Error: Could not generate a response from OpenRouter."

            except requests.exceptions.RequestException as e:
                log.error(f"Error calling OpenRouter API: {e}")
                return f"Error: Could not connect to OpenRouter API. {str(e)}"

        return "Error: OpenRouter API is currently unavailable (503). Please try again later."

    async def get_ai_response(self, action: str, adjective: str, noun: str, verb: str, interaction: discord.Interaction = None) -> str:
        """
        Get AI response using the configured provider (Gemini or OpenRouter).
        """
        use_openrouter = await self.config.use_openrouter()
        if use_openrouter:
            return await self.get_openrouter_response(action, adjective, noun, verb, interaction)
        else:
            return await self.get_gemini_response(action, adjective, noun, verb, interaction)

    @commands.group(name="womp", invoke_without_command=True)
    async def womp_group(self, ctx: commands.Context):
        """Womp commands"""
        if ctx.invoked_subcommand is None:
            await ctx.send("rigged")

    @womp_group.command(name="forage")
    async def womp_forage(self, ctx: commands.Context):
        """Womp goes foraging and finds you something random!"""
        result = await self.generate_womp_phrase()

        # Check if it's an error message
        if isinstance(result, str):
            await ctx.send(result)
            return

        phrase, adjective, noun, verb = result
        view = WompActionView(self, adjective, noun, verb, ctx.author.id)
        await ctx.send(phrase, view=view)

    @womp_group.command(name="wordsapi")
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

    @womp_group.command(name="openrouterapi")
    @commands.is_owner()
    async def womp_openrouter_api(self, ctx: commands.Context, api_key: str):
        """Set the OpenRouter API key for D&D-style responses"""
        await self.config.openrouter_api_key.set(api_key)
        await ctx.send("OpenRouter API key has been set successfully!")
        # Delete the message to protect the API key
        try:
            await ctx.message.delete()
        except discord.Forbidden:
            await ctx.send("Warning: Could not delete your message. Please manually delete it to protect your API key.")

    @womp_group.command(name="provider")
    @commands.is_owner()
    async def womp_provider(self, ctx: commands.Context, provider: str = None):
        """Set or view the AI provider (gemini or openrouter)"""
        if provider is None:
            use_openrouter = await self.config.use_openrouter()
            current = "openrouter" if use_openrouter else "gemini"
            await ctx.send(f"Current AI provider: **{current}**\nUse `[p]womp provider gemini` or `[p]womp provider openrouter` to switch.")
            return

        provider = provider.lower()
        if provider == "openrouter":
            await self.config.use_openrouter.set(True)
            await ctx.send("AI provider set to **OpenRouter** (moonshotai/kimi-k2.5).")
        elif provider == "gemini":
            await self.config.use_openrouter.set(False)
            await ctx.send("AI provider set to **Gemini**.")
        else:
            await ctx.send("Invalid provider. Use `gemini` or `openrouter`.")

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
        view = WompActionView(self, adjective, noun, verb, interaction.user.id)
        await interaction.response.send_message(phrase, view=view)

    @commands.command(name="wpc")
    async def wpc(self, ctx: commands.Context) -> None:
        msg = copy(ctx.message)
        for cmd in ["work", "payday", "crime"]:
            msg.content = f"{ctx.prefix}{cmd}"
            await self.bot.process_commands(msg)



class WompActionView(discord.ui.View):
    """View with buttons for womp actions"""

    def __init__(self, cog, adjective: str, noun: str, verb: str, user_id: int):
        super().__init__(timeout=60.0)
        self.cog = cog
        self.adjective = adjective
        self.noun = noun
        self.verb = verb
        self.user_id = user_id

        # Update the first button label with the random verb
        self.children[0].label = f"{verb.capitalize()} it"

    def _check_positive_outcome(self, response: str) -> bool:
        """Check if the AI response contains a positive stat change."""
        match = re.search(r"Stat Change:\s*([+-]?\d+)", response)
        return match is not None and int(match.group(1)) > 0

    async def _handle_response(self, interaction: discord.Interaction, response: str):
        """Send the AI response and dispatch event if positive outcome."""
        await interaction.followup.send(response)
        if self._check_positive_outcome(response):
            self.cog.bot.dispatch("womp_positive_outcome", interaction.user, interaction.channel)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Only allow the original user to interact with the buttons"""
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your forage!", ephemeral=True)
            return False
        return True

    async def disable_all_buttons(self, interaction: discord.Interaction):
        """Disable all buttons and update the message"""
        for child in self.children:
            child.disabled = True
        await interaction.message.edit(view=self)

    @discord.ui.button(label="Verb it", style=discord.ButtonStyle.primary)
    async def verb_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.disable_all_buttons(interaction)
        await interaction.response.defer()
        response = await self.cog.get_ai_response("verb", self.adjective, self.noun, self.verb, interaction)
        await self._handle_response(interaction, response)
        self.stop()

    @discord.ui.button(label="Sell it", style=discord.ButtonStyle.success)
    async def sell_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.disable_all_buttons(interaction)
        await interaction.response.defer()
        response = await self.cog.get_ai_response("sell", self.adjective, self.noun, self.verb, interaction)
        await self._handle_response(interaction, response)
        self.stop()

    @discord.ui.button(label="Equip it", style=discord.ButtonStyle.danger)
    async def equip_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.disable_all_buttons(interaction)
        await interaction.response.defer()
        response = await self.cog.get_ai_response("equip", self.adjective, self.noun, self.verb, interaction)
        await self._handle_response(interaction, response)
        self.stop()


async def setup(bot: Red):
    """Load the cog"""
    cog = Utility(bot)
    await bot.add_cog(cog)
