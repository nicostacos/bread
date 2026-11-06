from services.filters import matching_words
from core.errors import report_error,UserError
import discord


async def handle_message(bot,message):
    if message.author.bot:return
    if message.guild:
        try:
            settings=await bot.filters.settings(message.guild.id)
            matches=matching_words(message.content,settings['words']) if settings['enabled'] else []
            if matches:
                await message.delete()
                try:await message.author.send('Your message was removed by the server word filter.')
                except discord.Forbidden:pass
                await bot.send_mod_log(message.guild,'Message filtered',f'User {message.author.id}; channel {message.channel.id}; matches: {", ".join(set(matches))}')
                return
        except Exception as error:
            reference=report_error(error,{'event':'message_filter','guild':message.guild.id})
            context=await bot.get_context(message)
            if context.valid:
                await bot.on_command_error(context,UserError('Message filtering is temporarily unavailable. No command was run. Error ID: '+reference))
            return
    await bot.process_commands(message)
