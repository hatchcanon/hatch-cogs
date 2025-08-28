from .dicegame import DiceGame

__red_end_user_data_statement__ = (
    "This cog stores Discord user IDs temporarily during active dice games "
    "to track player bets and balances. This data is only kept in memory "
    "during the 30-second betting duration and is not permanently stored. "
    "All balance data is handled through Red-DiscordBot's built-in bank system."
)


async def setup(bot):
    """Load the DiceGame cog"""
    await bot.add_cog(DiceGame(bot))