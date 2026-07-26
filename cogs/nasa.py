"""
NASA API commands for Bread Bot
"""
import discord
from discord import app_commands
from discord.ext import commands
import aiohttp


class Nasa(commands.Cog):
    """NASA-related commands"""
    
    def __init__(self, bot):
        self.bot = bot
        self.nasa_api_key = None  # Would be loaded from config
    
    @app_commands.command(name="apod", description="Get NASA's Astronomy Picture of the Day")
    async def apod(self, interaction: discord.Interaction):
        """Get NASA's Astronomy Picture of the Day"""
        await interaction.response.send_message("✅ NASA APOD command works!", ephemeral=True)


async def setup(bot):
    """Add the cog to the bot"""
    await bot.add_cog(Nasa(bot))
