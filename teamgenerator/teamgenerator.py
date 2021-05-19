import discord
from redbot.core import commands

class teamgenerator(commands.Cog):
    """Team Generator"""

    @commands.command()
    async def mycom(self, ctx):
        await ctx.send("I can do stuff!")

    @commands.command()
    async def getvc(self, ctx):
        # author = ctx.message.author
        vc = ctx.author.voice.channel
        people = vc.members
        #em = discord.Embed(title="Team Generated", color=ctx.author.color)
        #em.add_field(name = "team", value = (people))
        await ctx.send(people)

    @commands.command()
    async def getmembers(self, ctx):
        if ctx.author.voice and ctx.author.voice.channel:
            vc = ctx.author.voice.channel
            people = (str(i) for i in vc.members)
            em = discord.Embed(title="Team Generated", color=ctx.author.color)
            em.add_field(name="team 1", value=("\n".join([str(i) for i in vc.members])))
            em.add_field(name="team 2", value=("blank"))
            await ctx.send(embed=em)
        else:
            await ctx.send(f"**You are not connected to a VC, {ctx.author.mention}**")

    #totalvcusers = len(ctx.author.voice.channel.members)