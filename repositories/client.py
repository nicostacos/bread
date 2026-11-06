import httpx
from supabase import acreate_client
from supabase.lib.client_options import AsyncClientOptions
from repositories.configs import ConfigRepository
from repositories.filters import FilterRepository
from repositories.warnings import WarningRepository
from repositories.blacklists import BlacklistRepository
from repositories.cases import CaseRepository
from repositories.invites import InviteRepository


class Repositories:
    def __init__(self,client,transport,defaults):
        self.client=client;self.transport=transport
        self.configs=ConfigRepository(client);self.filters=FilterRepository(client,defaults)
        self.warnings=WarningRepository(client);self.blacklists=BlacklistRepository(client)
        self.cases=CaseRepository(client);self.invites=InviteRepository(client)

    async def check(self):
        await self.client.table('guild_settings').select('guild_id').limit(1).execute()

    async def close(self):
        await self.client.realtime.close()
        await self.transport.aclose()


async def create_repositories(settings,defaults=()):
    transport=httpx.AsyncClient(timeout=15.0)
    try:
        client=await acreate_client(settings.supabase_url,settings.supabase_key,
            options=AsyncClientOptions(httpx_client=transport,auto_refresh_token=False,persist_session=False))
        repos=Repositories(client,transport,list(defaults))
        await repos.check()
        return repos
    except BaseException:
        await transport.aclose()
        raise
