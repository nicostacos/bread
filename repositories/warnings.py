from repositories.base import Repository


class WarningRepository(Repository):
    async def list(self,guild_id,user_id):
        return await self.rows('warnings',{'guild_id':guild_id,'user_id':user_id},'warning_number',null_columns=('deleted_at',))

    async def delete(self,guild_id,warning_id,actor_id):
        return (await self.client.rpc('bread_delete_warning',{'p_guild':str(guild_id),'p_id':warning_id,'p_actor':str(actor_id)}).execute()).data

    async def add(self,guild_id,user_id,moderator_id,reason,evidence):
        return (await self.client.rpc('bread_add_warning',{'p_guild':str(guild_id),'p_user':str(user_id),
            'p_moderator':str(moderator_id),'p_reason':reason,'p_evidence':evidence}).execute()).data
