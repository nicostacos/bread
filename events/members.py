import discord


async def handle_member_join(bot,member):
    config=await bot.repos.configs.get(member.guild.id)
    if config.get('welcome_channel'):
        channel=member.guild.get_channel(int(config['welcome_channel']))
        if channel:await channel.send(embed=discord.Embed(title='Welcome!',description=f'{member.mention} joined the server.',color=0x57F287))
