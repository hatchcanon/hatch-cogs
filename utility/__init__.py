from .utility import Utility

__red_end_user_data_statement__ = (
    "This cog stores Discord user IDs temporarily"
)


async def setup(bot):
    """Load the Utility cog"""
    await bot.add_cog(Utility(bot))