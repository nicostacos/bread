import asyncio
import discord
from core.errors import UserError


class AutoModService:
    def __init__(self,configs,filters):
        self.configs=configs;self.filters=filters;self.locks={}

    async def sync(self,guild,settings):
        async with self.locks.setdefault(guild.id,asyncio.Lock()):
            await self._sync(guild,await self.filters.get(guild.id))

    async def _sync(self,guild,settings):
        config=await self.configs.get(guild.id)
        rule=None
        if config.get('automod_rule_id'):
            try:rule=await guild.fetch_automod_rule(int(config['automod_rule_id']))
            except discord.NotFound:pass
        words=settings['words']
        if not settings['enabled'] or not words:
            if rule:await rule.delete(reason='Bread Bot filter disabled')
            await self.configs.update(guild.id,{'automod_rule_id':None})
            return
        if len(words)>1000 or any(len(word)>60 for word in words):
            raise UserError('The saved filter exceeds Discord AutoMod keyword limits; local filtering remains active.')
        actions=[discord.AutoModRuleAction(type=discord.AutoModRuleActionType.block_message)]
        if config.get('log_channel'):
            actions.append(discord.AutoModRuleAction(channel_id=int(config['log_channel'])))
        kwargs={'name':'Bread Bot - AutoMod Filter','trigger':discord.AutoModTrigger(keyword_filter=words),
                'actions':actions,'enabled':True,'reason':'Bread Bot filter synchronization'}
        if rule:rule=await rule.edit(**kwargs)
        else:rule=await guild.create_automod_rule(event_type=discord.AutoModRuleEventType.message_send,**kwargs)
        await self.configs.update(guild.id,{'automod_rule_id':str(rule.id)})
