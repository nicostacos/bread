import re


def matching_words(content,words):
    if not words:return []
    return re.findall(r'\b(?:'+ '|'.join(re.escape(w) for w in words)+r')\b',content,re.IGNORECASE)


class FilterService:
    def __init__(self,repository):self.repository=repository
    async def settings(self,guild_id): return await self.repository.get(guild_id)
    async def mutate(self,guild_id,action,word=None):return await self.repository.mutate(guild_id,action,word)
