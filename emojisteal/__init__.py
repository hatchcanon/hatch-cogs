from .emojisteal import EmojiSteal

__red_end_user_data_statement__ = (
    "This cog does not persistently store any user data."
)


async def setup(bot):
    """Load the EmojiSteal cog"""
    await bot.add_cog(EmojiSteal(bot))
