from repositories.base import Repository


class ConfigRepository(Repository):
    async def get(self,guild_id):
        rows=await self.rows('guild_settings',{'guild_id':guild_id})
        return rows[0] if rows else {}

    async def update(self,guild_id,changes):
        allowed={'log_channel','welcome_channel','automod_rule_id','active'}
        if not set(changes)<=allowed: raise ValueError('Invalid settings update')
        await self.ensure_guild(guild_id)
        await self.client.table('guild_settings').update(changes).eq('guild_id',str(guild_id)).execute()

    async def deactivate(self,guild_id):
        await self.client.rpc('bread_deactivate_guild',{'p_guild':str(guild_id)}).execute()
