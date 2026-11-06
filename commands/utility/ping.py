from core.errors import respond
import discord
from discord import app_commands
from discord.ext import commands


class Ping(commands.Cog):
    @app_commands.command(name='ping',description='Check bot responsiveness')
    async def ping(self,interaction:discord.Interaction):await respond(interaction,content='Pong!')
    @app_commands.command(name='test',description='Test command registration')
    async def test(self,interaction:discord.Interaction):await respond(interaction,content='Test command works!')


async def setup(bot):await bot.add_cog(Ping())
