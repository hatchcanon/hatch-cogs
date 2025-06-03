from .riotgameping import RiotGamePing

__red_end_user_data_statement__ = (
    "This cog stores Discord user IDs temporarily during active game sessions "
    "to track who has joined a game ping. This data is only kept in memory "
    "during the 30-minute game ping duration and is not permanently stored. "
    "Guild configurations (game names, roles, and channels) are stored permanently."
)


async def setup(bot):
    """Load the RiotGamePing cog"""
    await bot.add_cog(RiotGamePing(bot))