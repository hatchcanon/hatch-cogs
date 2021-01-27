from redbot.core import commands

class teamgenerator(commands.Cog):
    """My custom cog"""

    @commands.command()
    async def mycom(self, ctx):
        await ctx.send("I can do stuff!")

    async def get_vc(self, ctx, user, channel):
        await ctx.send("crap")