import asyncio
import unittest
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock
from core.evidence import EvidenceView
from core.errors import UserError


class EvidenceTests(unittest.IsolatedAsyncioTestCase):
    async def test_successful_warning_deletes_prepare_message(self):
        view,interaction,callback=self.setup_flow();view.action='warn'
        prompt=NS(delete=AsyncMock());interaction.message=prompt
        interaction.response.send_modal=AsyncMock()
        await view.evidence_button.callback(interaction)
        await view.submit(interaction,'reason','proof')
        self.assertEqual(prompt.delete.await_count,1)

    async def test_failed_warning_keeps_prepare_message(self):
        view,interaction,callback=self.setup_flow();view.action='warn'
        prompt=NS(delete=AsyncMock());interaction.message=prompt
        interaction.response.send_modal=AsyncMock()
        await view.evidence_button.callback(interaction)
        callback.side_effect=RuntimeError('database unavailable')
        with self.assertRaises(RuntimeError):await view.submit(interaction,'reason','proof')
        self.assertEqual(prompt.delete.await_count,0)

    def setup_flow(self):
        callback=AsyncMock()
        command=NS(callback=callback,binding=object())
        member=NS(id=3)
        bot=NS(repos=NS(blacklists=NS(contains=AsyncMock(return_value=False))),tree=NS(get_command=lambda _:command))
        guild=NS(id=10,fetch_member=AsyncMock(return_value=member))
        interaction=NS(guild_id=10,guild=guild,user=NS(id=2),
            response=NS(is_done=lambda:True),followup=NS(send=AsyncMock()))
        return EvidenceView(bot,'kick',2,10,3,'reason'),interaction,callback

    async def test_other_users_cannot_submit(self):
        view,interaction,callback=self.setup_flow();interaction.user.id=99
        with self.assertRaises(UserError):await view.submit(interaction,'reason','proof')
        self.assertEqual(callback.await_count,0)

    async def test_blacklist_is_rechecked_before_action(self):
        view,interaction,callback=self.setup_flow()
        view.bot.repos.blacklists.contains.return_value=True
        with self.assertRaises(UserError):await view.submit(interaction,'reason','proof')
        self.assertEqual(callback.await_count,0)

    async def test_simultaneous_submissions_execute_once_with_fresh_member(self):
        view,interaction,callback=self.setup_flow()
        results=await asyncio.gather(view.submit(interaction,'reason','proof'),view.submit(interaction,'reason','proof'),return_exceptions=True)
        self.assertEqual(callback.await_count,1)
        self.assertEqual(sum(isinstance(r,UserError) for r in results),1)
        self.assertEqual(callback.call_args.kwargs['evidence'],'proof')
        self.assertIs(callback.call_args.kwargs['member'],interaction.guild.fetch_member.return_value)

    async def test_failed_callback_cannot_be_replayed(self):
        view,interaction,callback=self.setup_flow();callback.side_effect=RuntimeError('uncertain result')
        with self.assertRaises(RuntimeError):await view.submit(interaction,'reason','proof')
        with self.assertRaises(UserError):await view.submit(interaction,'reason','proof')
        self.assertEqual(callback.await_count,1)

    async def test_expired_forms_cannot_submit(self):
        view,interaction,callback=self.setup_flow();view.expires_at=0
        with self.assertRaises(UserError):await view.submit(interaction,'reason','proof')
        self.assertEqual(callback.await_count,0)
