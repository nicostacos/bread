from repositories.base import Repository


class CaseRepository(Repository):
    async def record(self,guild_id,user_id,moderator_id,action,reason,evidence='',duration='',outcome='succeeded'):
        await self.ensure_guild(guild_id)
        await self.client.table('moderation_cases').insert({'guild_id':str(guild_id),'user_id':str(user_id),
            'moderator_id':str(moderator_id),'action':action,'reason':reason,'evidence':evidence,
            'duration':duration,'outcome':outcome}).execute()
