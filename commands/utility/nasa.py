import discord
from discord import app_commands
from discord.ext import commands
from core.errors import defer,respond
from services.nasa import fetch_apod


class Nasa(commands.Cog):
    def __init__(self,bot):self.bot=bot
    @app_commands.command(name='apod',description='Get NASA Astronomy Picture of the Day')
    async def apod(self,interaction:discord.Interaction):
        await defer(interaction)
        await respond(interaction,embed=await fetch_apod(self.bot.session,self.bot.settings.nasa_key),ephemeral=False)


async def setup(bot):await bot.add_cog(Nasa(bot))
