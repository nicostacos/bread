from repositories.base import Repository


class InviteRepository(Repository):
    async def enqueue(self,guild_id,user_id,send_at,reason):
        await self.ensure_guild(guild_id)
        await self.client.table('scheduled_invites').insert({'guild_id':str(guild_id),'user_id':str(user_id),
            'send_at':send_at.isoformat(),'reason':reason}).execute()

    async def claim(self,limit=25):
        return (await self.client.rpc('bread_claim_invites',{'p_limit':limit}).execute()).data

    async def finish(self,job,action,value=None):
        result=(await self.client.rpc('bread_finish_invite',{'p_id':job['id'],'p_lease':job['lease_token'],
            'p_action':action,'p_value':value}).execute()).data
        if not result: raise RuntimeError('Invite job lease is no longer valid')

    async def record_invite(self,job,url): await self.finish(job,'url',url)
    async def complete(self,job): await self.finish(job,'sent')
    async def fail(self,job,error_id): await self.finish(job,'fail',error_id)
