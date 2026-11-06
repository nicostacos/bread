from core.errors import respond
import discord
from discord import app_commands
from discord.ext import commands
from core.presentation import help_embed


class Help(commands.Cog):
    def __init__(self,bot):self.bot=bot
    def text(self):
        return 'Slash commands:\n'+', '.join('/'+c.name for c in sorted(self.bot.tree.get_commands(),key=lambda c:c.name))+'\nPrefix commands: bread help; bread filter; bread blacklist; bread setlog; bread setwelcome; bread getchannels; bread hello; bread kick; bread warn; bread warnings.'
    @app_commands.command(name='help',description='List available bot commands')
    async def help_slash(self,interaction:discord.Interaction):await respond(interaction,embed=help_embed(self.bot),ephemeral=True)
    @commands.command(name='help')
    async def help_prefix(self,ctx):await ctx.send(embed=help_embed(self.bot))


async def setup(bot):await bot.add_cog(Help(bot))
