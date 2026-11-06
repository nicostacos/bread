from repositories.base import Repository


class FilterRepository(Repository):
    def __init__(self,client,defaults): super().__init__(client);self.defaults=defaults

    async def get(self,guild_id): return await self.mutate(guild_id,'status')

    async def mutate(self,guild_id,action,word=None):
        return (await self.client.rpc('bread_mutate_filter',{'p_guild':str(guild_id),
            'p_action':action,'p_word':word,'p_defaults':self.defaults}).execute()).data
