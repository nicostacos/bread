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

    # ===== Info Commands =====

    @app_commands.command(name="botinfo", description="Get information about the bot")
    async def botinfo(self, interaction: discord.Interaction):
        """Get information about the bot"""
        embed = discord.Embed(
            title="🤖 Bot Information",
            description="Bread Bot - A multi-purpose Discord bot for moderation, utilities, and fun!",
            color=0xFFA500,
            timestamp=discord.utils.utcnow()
        )
        
        embed.add_field(name="Name", value=self.bot.user.name, inline=True)
        embed.add_field(name="ID", value=str(self.bot.user.id), inline=True)
        embed.add_field(name="Prefix", value="`bread`", inline=True)
        embed.add_field(name="Created", value=discord.utils.format_dt(self.bot.user.created_at, "D"), inline=False)
        embed.add_field(name="Servers", value=str(len(self.bot.guilds)), inline=True)
        embed.add_field(name="Users", value=str(len(set(m.id for m in self.bot.get_all_members()))), inline=True)
        embed.add_field(name="Latency", value=f"{round(self.bot.latency * 1000)}ms", inline=True)
        
        if self.bot.user.avatar:
            embed.set_thumbnail(url=self.bot.user.avatar.url)
        
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="serverinfo", description="Get information about the server")
    async def serverinfo(self, interaction: discord.Interaction):
        """Get information about the server"""
        if not interaction.guild:
            await interaction.response.send_message("❌ This command can only be used in a server!", ephemeral=True)
            return
        
        guild = interaction.guild
        embed = discord.Embed(
            title="🏢 Server Information",
            description=f"Information about **{guild.name}**",
            color=0x3498DB,
            timestamp=discord.utils.utcnow()
        )
        
        embed.add_field(name="Name", value=guild.name, inline=True)
        embed.add_field(name="ID", value=str(guild.id), inline=True)
        embed.add_field(name="Owner", value=guild.owner.mention, inline=True)
        embed.add_field(name="Created", value=discord.utils.format_dt(guild.created_at, "D"), inline=False)
        embed.add_field(name="Members", value=str(guild.member_count), inline=True)
        embed.add_field(name="Text Channels", value=str(len(guild.text_channels)), inline=True)
        embed.add_field(name="Voice Channels", value=str(len(guild.voice_channels)), inline=True)
        embed.add_field(name="Roles", value=str(len(guild.roles)), inline=True)
        embed.add_field(name="Emojis", value=str(len(guild.emojis)), inline=True)
        
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="userinfo", description="Get information about a user")
    @app_commands.describe(user="The user to get information about (default: you)")
    async def userinfo(self, interaction: discord.Interaction, user: discord.User = None):
        """Get information about a user"""
        user = user or interaction.user
        member = interaction.guild.get_member(user.id) if interaction.guild else None
        
        embed = discord.Embed(
            title="👤 User Information",
            description=f"Information about {user.mention}",
            color=0x9B59B6,
            timestamp=discord.utils.utcnow()
        )
        
        embed.add_field(name="Name", value=str(user), inline=True)
        embed.add_field(name="ID", value=str(user.id), inline=True)
        embed.add_field(name="Created", value=discord.utils.format_dt(user.created_at, "D"), inline=False)
        
        if member:
            embed.add_field(name="Joined Server", value=discord.utils.format_dt(member.joined_at, "D"), inline=False)
            embed.add_field(name="Roles", value=str(len(member.roles) - 1), inline=True)  # -1 to exclude @everyone
            embed.add_field(name="Highest Role", value=member.top_role.mention, inline=True)
            embed.add_field(name="Bot", value="Yes" if user.bot else "No", inline=True)
        
        if user.avatar:
            embed.set_thumbnail(url=user.avatar.url)
        
        await interaction.response.send_message(embed=embed)

    # ===== Help Command =====

    @commands.command(name="help")
    async def help_command(self, ctx):
        """Show help information (prefix command)"""
        embed = discord.Embed(
            title="📖 Bread Bot Help",
            description="List of available commands",
            color=0x3498DB,
            timestamp=discord.utils.utcnow()
        )
        
        embed.add_field(
            name="🔧 Utility Commands",
            value="`test`, `ping`, `hello`, `coin_toss`, `botinfo`, `serverinfo`, `userinfo`",
            inline=False
        )
        embed.add_field(
            name="🛡️ Moderation Commands",
            value="`kick`, `ban`, `unban`, `mute`, `purge`, `broadcast`, `blacklist`, `warn`, `warnings`",
            inline=False
        )
        embed.add_field(
            name="⚙️ Admin Commands",
            value="`setlog`, `setwelcome`, `getchannels`, `filter`, `automod`",
            inline=False
        )
        
        embed.add_field(
            name="💡 Usage",
            value="Use `/` for slash commands or `bread ` for prefix commands",
            inline=False
        )
        
        embed.set_footer(text="Bread Bot - Your friendly neighborhood bot!")
        await ctx.send(embed=embed)

    @app_commands.command(name="help", description="Show help information")
    async def slash_help(self, interaction: discord.Interaction):
        """Show help information (slash command)"""
        embed = discord.Embed(
            title="📖 Bread Bot Help",
            description="List of available commands",
            color=0x3498DB,
            timestamp=discord.utils.utcnow()
        )
        
        embed.add_field(
            name="🔧 Utility Commands",
            value="/test, /ping, /hello, /coin_toss, /botinfo, /serverinfo, /userinfo",
            inline=False
        )
        embed.add_field(
            name="🛡️ Moderation Commands",
            value="/kick, /ban, /unban, /mute, /purge, /broadcast, /blacklist, /warn, /warnings",
            inline=False
        )
        embed.add_field(
            name="⚙️ Admin Commands",
            value="/setlog, /setwelcome, /getchannels, /filter, /automod",
            inline=False
        )
        
        embed.add_field(
            name="💡 Usage",
            value="Use `/` for slash commands or `bread ` for prefix commands",
            inline=False
        )
        
        embed.set_footer(text="Bread Bot - Your friendly neighborhood bot!")
        await interaction.response.send_message(embed=embed)


async def setup(bot):
    """Add the cog to the bot"""
    await bot.add_cog(Utilities(bot))
