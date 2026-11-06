async def handle_guild_remove(bot,guild):
    await bot.repos.configs.deactivate(guild.id)


async def handle_guild_join(bot,guild):
    # Retained historical jobs stay suspended until deliberately reviewed.
    await bot.repos.configs.update(guild.id,{'active':True})
