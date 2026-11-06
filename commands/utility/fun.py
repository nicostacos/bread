from core.errors import respond
import random
import discord
from discord import app_commands
from discord.ext import commands


class Fun(commands.Cog):
    @app_commands.command(name='hello',description='Say hello')
    async def hello_slash(self,interaction:discord.Interaction):await respond(interaction,content=f'Hello, {interaction.user.mention}!')
    @commands.command(name='hello')
    async def hello_prefix(self,ctx):await ctx.send(f'Hello, {ctx.author.mention}!')
    @app_commands.command(name='coin_toss',description='Flip a coin')
    async def coin_toss(self,interaction:discord.Interaction):await respond(interaction,content=random.choice(['Heads','Tails']))


async def setup(bot):await bot.add_cog(Fun())
