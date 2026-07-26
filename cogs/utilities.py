"""
Utility commands for Bread Bot
"""
import discord
from discord import app_commands
from discord.ext import commands
import random


class Utilities(commands.Cog):
    """Utility commands"""
    
    def __init__(self, bot):
        self.bot = bot
    
    @app_commands.command(name="test", description="A simple test command")
    async def test_command(self, interaction: discord.Interaction):
        await interaction.response.send_message("Test command works! ✅")

    @app_commands.command(name="ping", description="Check if the bot is responsive")
    async def ping(self, interaction: discord.Interaction):
        await interaction.response.send_message("Pong! 🏓")

    @app_commands.command(name="hello", description="Say hello to the bot")
    async def slash_hello(self, interaction: discord.Interaction):
        await interaction.response.send_message(f"Hello, {interaction.user.mention}! 👋")

    @commands.command()
    async def hello(self, ctx):
        """Say hello to the bot (prefix command)"""
        await ctx.send(f"Hello, {ctx.author.mention}! 👋")

    @app_commands.command(name="coin_toss", description="Flips a coin")
    async def coin_toss(self, interaction: discord.Interaction):
        result = random.choice(["Heads", "Tails"])
        emoji = "👑" if result == "Heads" else "🔢"

        embed = discord.Embed(
            title="🪙 Coin Toss",
            description=f"{emoji} **{result}**!",
            color=0x00FF00 if result == "Heads" else 0xFF0000,
        )
        await interaction.response.send_message(embed=embed)


async def setup(bot):
    """Add the cog to the bot"""
    await bot.add_cog(Utilities(bot))
