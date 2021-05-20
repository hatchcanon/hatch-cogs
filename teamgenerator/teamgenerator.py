import discord
import random
import math
from redbot.core import commands

class teamgenerator(commands.Cog):
    """Team Generator"""

    def formatname(self):
        return f"> {self.mention}"

    @commands.command()
    async def mycom(self, ctx):
        await ctx.send("I can do stuff!")

    # @commands.command()
    # async def getvc(self, ctx):
    #     author = ctx.message.author
    #     vc = ctx.author.voice.channel
    #     people = [str(i['nick']) or str(i['name']) for i in vc.members]
    #     em = discord.Embed(title="Team Generated", color=ctx.author.color)
    #     em.add_field(name = "team", value = (people))
    #     await ctx.send(people)

    @commands.command()
    async def getmembers(self, ctx):
        if ctx.author.voice and ctx.author.voice.channel:
            vc = ctx.author.voice.channel
            people = [i.mention for i in vc.members]
            random.shuffle(people)
            half = math.ceil(len(people) / 2)
            maps = ['Blind', 'Spit', 'Accent', 'Heaven', 'Icebox', 'Breeze']
            random_index = random.randrange(len(maps))
            em = discord.Embed(title="Team Generated", color=ctx.author.color)
            em.insert_field_at(index=1, name="Map", value=(maps[random_index]))
            em.add_field(name="Team 1", value=("\n".join(people[:half])))
            em.add_field(name="Team 2", value=("\n".join(people[half:])))
            await ctx.send(embed=em)
        else:
            await ctx.send(f"**You are not connected to a VC, {ctx.author.mention}**")