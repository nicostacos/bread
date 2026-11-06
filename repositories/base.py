class Repository:
    def __init__(self,client): self.client=client

    async def rows(self,table,filters=None,order=None,null_columns=()):
        result=[];start=0
        while True:
            query=self.client.table(table).select('*')
            for key,value in (filters or {}).items(): query=query.eq(key,str(value))
            for key in null_columns:query=query.is_(key,'null')
            if order: query=query.order(order)
            page=(await query.range(start,start+499).execute()).data
            result.extend(page)
            if len(page)<500:return result
            start+=500

    async def ensure_guild(self,guild_id):
        await self.client.table('guild_settings').upsert({'guild_id':str(guild_id)},on_conflict='guild_id',ignore_duplicates=True).execute()
