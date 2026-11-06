import asyncio
from core.errors import report_error
from services.invites import InviteService


class InviteWorker:
    def __init__(self,bot):self.bot=bot;self.invites=InviteService()

    async def run_once(self):
        jobs=await self.bot.repos.invites.claim(5)
        await asyncio.gather(*(self.process(job) for job in jobs))

    async def process(self,job):
        repo=self.bot.repos.invites
        try:
            async with asyncio.timeout(90):
                guild=self.bot.get_guild(int(job['guild_id']))
                if guild is None:raise RuntimeError('Guild unavailable for invite job')
                user=self.bot.get_user(int(job['user_id'])) or await self.bot.fetch_user(int(job['user_id']))
                url=job.get('invite_url') or await self.invites.create_url(guild,job.get('reason','Scheduled rejoin'))
                # Verify ownership even for reused URLs before the external delivery.
                await repo.record_invite(job,url)
                await user.send(f"You are invited back to **{guild.name}**.\n{job.get('reason','')[:1500]}\n{url}")
                await repo.complete(job)
        except asyncio.CancelledError:raise
        except Exception as error:
            reference=report_error(error,{'event':'invite_job','job':job['id']})
            try:await repo.fail(job,reference)
            except Exception as failure:report_error(failure,{'event':'invite_job_failure_state','job':job['id']})

    async def run(self):
        while True:
            try:await self.run_once()
            except asyncio.CancelledError:raise
            except Exception as error:report_error(error,{'event':'invite_worker'})
            await asyncio.sleep(60)
