from repositories.base import Repository


class BlacklistRepository(Repository):
    async def contains(self,guild_id,user_id):
        return bool(await self.rows('guild_blacklist_entries',{'guild_id':guild_id,'user_id':user_id}))

    async def list(self,guild_id): return await self.rows('guild_blacklist_entries',{'guild_id':guild_id},'user_id')

    async def add(self,guild_id,user_id):
        await self.ensure_guild(guild_id)
        await self.client.table('guild_blacklist_entries').upsert({'guild_id':str(guild_id),'user_id':str(user_id)}).execute()

    async def remove(self,guild_id,user_id):
        await self.client.table('guild_blacklist_entries').delete().eq('guild_id',str(guild_id)).eq('user_id',str(user_id)).execute()
