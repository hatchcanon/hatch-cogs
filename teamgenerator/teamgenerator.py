import discord
import random
import math
from redbot.core import commands


def formatname(member):
    return f"> {member.mention}"

class teamgenerator(commands.Cog):
    """"Team Generator"""
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
    async def team(self, ctx, game=None):

        em = discord.Embed(title="Team Generated", color=ctx.author.color)

        if game is None:
            pass
        else:
            if game == "val":
                maps = ['Blind', 'Spit', 'Accent', 'Heaven', 'Icebox', 'Breeze']
                random_index = random.randrange(len(maps))
                valmaps = maps[random_index]
                em.add_field(name="Map", value=(valmaps), inline=False)
            if game == "csgo":
                maps = ['Inferno', 'Mirage', 'Nuke', 'Overpass', 'Dust II', 'Vertigo', 'Ancient']
                random_index = random.randrange(len(maps))
                valmaps = maps[random_index]
                em.add_field(name="Map", value=(valmaps), inline=False)

        if ctx.author.voice and ctx.author.voice.channel:
            vc = ctx.author.voice.channel
            people = [formatname(i) for i in vc.members]
            random.shuffle(people)
            half = math.ceil(len(people) / 2)
            em.add_field(name="Team 1", value=("\n".join(people[:half])), inline=True)
            em.add_field(name="Team 2", value=("\n".join(people[half:])), inline=True)
            await ctx.send(embed=em)
        else:
            await ctx.send(f"**You are not connected to a VC, {ctx.author.mention}**")