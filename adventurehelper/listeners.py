import json
import re
from pathlib import Path

import discord
from redbot.core import commands
from redbot.core.i18n import Translator

from .abc import MixinMeta

_ = Translator("AdventureHelper", __file__)


class AdventureHelperListeners(MixinMeta):
    """Listener class for adventure events to provide strategic guidance"""

    def __init__(self, *args):
        super().__init__(*args)
        # Load attribute modifiers from JSON
        attribs_path = Path(__file__).parent / "attribs.json"
        with open(attribs_path) as f:
            self.attribs = json.load(f)

    def analyze_adventure(self, message_content: str) -> dict:
        """
        Analyze the adventure message to determine monster attributes and provide recommendations
        Returns dict with: attribute, attack_defense, talk_defense, recommendation, action
        """
        # Find which attribute is in the message
        found_attrib = None
        for attrib_key in self.attribs.keys():
            # Create pattern that handles "a" or "an" prefix
            pattern = re.compile(r"\ba" + re.escape(attrib_key) + r"\b", re.IGNORECASE)
            if pattern.search(message_content):
                found_attrib = attrib_key
                break

        if not found_attrib:
            return None

        # Get the modifiers [attack_defense, talk_defense]
        attack_defense, talk_defense = self.attribs[found_attrib]

        # Determine recommendation based on modifiers
        recommendation, action = self._get_recommendation(attack_defense, talk_defense)

        return {
            "attribute": found_attrib.strip(),
            "attack_defense": attack_defense,
            "talk_defense": talk_defense,
            "recommendation": recommendation,
            "action": action,
        }

    def _get_recommendation(self, attack_defense: float, talk_defense: float) -> tuple:
        """
        Generate a strategic recommendation based on the modifiers
        Returns tuple of (recommendation_text, preferred_action)

        Lower defense values are better (easier to succeed)
        """
        # Calculate the advantage difference
        # Negative means talk is better (attack_defense is higher)
        # Positive means attack is better (talk_defense is higher)
        advantage_diff = attack_defense - talk_defense

        # Determine the preferred action
        if abs(advantage_diff) < 0.1:
            # Nearly equal, no strong preference
            action = "Either"
            if attack_defense >= 100 or talk_defense >= 100:
                recommendation = "EXTREMELY DIFFICULT! One approach is nearly impossible. Try the other carefully!"
            elif attack_defense >= 2.0 and talk_defense >= 2.0:
                recommendation = "VERY TOUGH! Both approaches are difficult. Bring your best gear and party!"
            elif attack_defense <= 0.5 and talk_defense <= 0.5:
                recommendation = "EASY WIN! Both attack and talk are favorable. Quick victory expected!"
            else:
                recommendation = "Balanced enemy. Attack and talk are roughly equal - use your preferred approach."

        elif advantage_diff > 0:
            # Talk is better (attack_defense is higher)
            action = "Talk"

            if advantage_diff >= 99:
                recommendation = f"DEFINITELY TALK! Attack is nearly impossible ({attack_defense}x) while talk is much easier ({talk_defense}x)."
            elif advantage_diff >= 1.0:
                recommendation = f"STRONGLY RECOMMEND TALK! Attack defense is {attack_defense}x vs talk defense {talk_defense}x. Talk has a huge advantage!"
            elif advantage_diff >= 0.5:
                recommendation = f"Talk recommended! Talk defense ({talk_defense}x) is significantly better than attack defense ({attack_defense}x)."
            elif advantage_diff >= 0.2:
                recommendation = f"Talk is favorable. Talk defense ({talk_defense}x) is moderately better than attack defense ({attack_defense}x)."
            else:
                recommendation = f"Slight talk advantage. Talk defense ({talk_defense}x) is a bit better than attack defense ({attack_defense}x)."

        else:  # advantage_diff < 0
            # Attack is better (talk_defense is higher)
            action = "Attack"
            advantage_diff = abs(advantage_diff)

            if advantage_diff >= 99:
                recommendation = f"DEFINITELY ATTACK! Talk is nearly impossible ({talk_defense}x) while attack is much easier ({attack_defense}x)."
            elif advantage_diff >= 1.0:
                recommendation = f"STRONGLY RECOMMEND ATTACK! Talk defense is {talk_defense}x vs attack defense {attack_defense}x. Attack has a huge advantage!"
            elif advantage_diff >= 0.5:
                recommendation = f"Attack recommended! Attack defense ({attack_defense}x) is significantly better than talk defense ({talk_defense}x)."
            elif advantage_diff >= 0.2:
                recommendation = f"Attack is favorable. Attack defense ({attack_defense}x) is moderately better than talk defense ({talk_defense}x)."
            else:
                recommendation = f"Slight attack advantage. Attack defense ({attack_defense}x) is a bit better than talk defense ({attack_defense}x)."

        return recommendation, action

    async def send_adventure_help(self, ctx: commands.Context) -> None:
        """Send strategic guidance for the adventure"""
        if await self.bot.cog_disabled_in_guild(self, ctx.guild):
            return
        if ctx.guild is None:
            return

        # Check if the cog is enabled
        enabled = await self.config.guild(ctx.guild).enabled()
        if not enabled:
            return

        # Analyze the adventure message
        analysis = self.analyze_adventure(ctx.message.content)

        if not analysis:
            # No recognized attribute found
            return

        # Build the help message
        # Set embed color based on recommended action
        if analysis["action"] == "Attack":
            color = discord.Color.red()
        elif analysis["action"] == "Talk":
            color = discord.Color.green()
        else:
            color = discord.Color.blue()

        embed = discord.Embed(
            color=color,
        )
        # Add recommendation
        embed.add_field(
            value=analysis["recommendation"],
            inline=False,
        )

        # Send the embed
        await ctx.channel.send(embed=embed)

    @commands.Cog.listener()
    async def on_adventure(self, ctx: commands.Context) -> None:
        """Listen for adventure events and provide guidance"""
        await self.send_adventure_help(ctx)

    @commands.Cog.listener()
    async def on_adventure_miniboss(self, ctx: commands.Context) -> None:
        """Listen for miniboss events and provide guidance"""
        await self.send_adventure_help(ctx)

    @commands.Cog.listener()
    async def on_adventure_boss(self, ctx: commands.Context) -> None:
        """Listen for boss events and provide guidance"""
        await self.send_adventure_help(ctx)

    @commands.Cog.listener()
    async def on_adventure_ascended(self, ctx: commands.Context) -> None:
        """Listen for ascended events and provide guidance"""
        await self.send_adventure_help(ctx)

    @commands.Cog.listener()
    async def on_adventure_transcended(self, ctx: commands.Context) -> None:
        """Listen for transcended events and provide guidance"""
        await self.send_adventure_help(ctx)

    @commands.Cog.listener()
    async def on_adventure_immortal(self, ctx: commands.Context) -> None:
        """Listen for immortal events and provide guidance"""
        await self.send_adventure_help(ctx)

    @commands.Cog.listener()
    async def on_adventure_possessed(self, ctx: commands.Context) -> None:
        """Listen for possessed events and provide guidance"""
        await self.send_adventure_help(ctx)
