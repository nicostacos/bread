"""
NASA API commands for Bread Bot
"""
from discord import Interaction, app_commands
from discord.ext import commands
# aiohttp is optional for future HTTP requests; not required currently


class Nasa(commands.Cog):
    """NASA-related commands"""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.nasa_api_key: str | None = None  # Would be loaded from config
    
    @app_commands.command(name="apod", description="Get NASA's Astronomy Picture of the Day")
    async def apod(self, interaction: Interaction):
        """Get NASA's Astronomy Picture of the Day"""
        await interaction.response.send_message("✅ NASA APOD command works!", ephemeral=True)


async def setup(bot):
    """Add the cog to the bot"""
    await bot.add_cog(Nasa(bot))
