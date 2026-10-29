from .idlecord import IdleCord

__red_end_user_data_statement__ = (
    "This cog stores Discord user IDs along with IdleCord game progress (heroes, resources, "
    "teams and settings), and a public post channel ID per server. Data can be deleted on request."
)


async def setup(bot):
    """Load the IdleCord cog"""
    await bot.add_cog(IdleCord(bot))
