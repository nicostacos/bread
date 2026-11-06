import unittest
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
from core.errors import UserError
from services.moderation import ModerationService, bounded_positive, warning_pages
from services.automod import AutoModService
from services.nasa import apod_embed


class ServiceTests(unittest.IsolatedAsyncioTestCase):
    def test_positive_bounds(self):
        for value in (-1,0,2001):
            with self.assertRaises(UserError): bounded_positive(value,2000)
        self.assertEqual(bounded_positive(1,2000),1)

    def test_warning_pages_stay_within_discord_limits(self):
        pages=warning_pages('member',[{'warning_number':i+1,'reason':'r'*4000,'evidence':'x'*2000} for i in range(32)])
        self.assertGreater(len(pages),1)
        self.assertEqual(sum(len(p.fields) for p in pages),32)
        for page in pages:
            self.assertLessEqual(len(page),6000)
            self.assertLessEqual(len(page.fields),25)
            self.assertTrue(all(len(field.value)<=1024 for field in page.fields))

    async def test_completed_action_survives_audit_failure(self):
        cases=SimpleNamespace(record=AsyncMock(side_effect=RuntimeError('offline')))
        service=ModerationService(SimpleNamespace(cases=cases),AsyncMock())
        target=SimpleNamespace(id=3,kick=AsyncMock())
        with self.assertLogs('core.errors',level='ERROR'):
            outcome=await service.execute(SimpleNamespace(id=1),SimpleNamespace(id=2),target,'kick','test','proof')
        self.assertTrue(outcome['succeeded'])
        self.assertIsNotNone(outcome['audit_error'])
        self.assertEqual(target.kick.await_count,1)

    async def test_automod_supported_alert_action(self):
        rule=SimpleNamespace(id=8,edit=AsyncMock(),delete=AsyncMock())
        guild=SimpleNamespace(id=1,create_automod_rule=AsyncMock(return_value=rule),fetch_automod_rule=AsyncMock(return_value=rule))
        configs=SimpleNamespace(get=AsyncMock(return_value={'log_channel':'7'}),update=AsyncMock())
        settings={'enabled':True,'words':['alpha']}
        await AutoModService(configs,SimpleNamespace(get=AsyncMock(return_value=settings))).sync(guild,settings)
        actions=guild.create_automod_rule.call_args.kwargs['actions']
        self.assertEqual([action.type.value for action in actions],[1,2])

    async def test_automod_serializes_creation_and_rereads_saved_state(self):
        saved={'log_channel':None}
        rule=SimpleNamespace(id=8,edit=AsyncMock(),delete=AsyncMock())
        async def get(_):return dict(saved)
        async def update(_,changes):saved.update(changes)
        async def create(**kwargs):await asyncio.sleep(0.01);return rule
        guild=SimpleNamespace(id=1,create_automod_rule=AsyncMock(side_effect=create),fetch_automod_rule=AsyncMock(return_value=rule))
        configs=SimpleNamespace(get=get,update=update)
        filters=SimpleNamespace(get=AsyncMock(return_value={'enabled':True,'words':['alpha','beta']}))
        service=AutoModService(configs,filters)
        await asyncio.gather(service.sync(guild,{'enabled':True,'words':['alpha']}),service.sync(guild,{'enabled':True,'words':['beta']}))
        self.assertEqual(guild.create_automod_rule.await_count,1)
        self.assertEqual(rule.edit.call_args.kwargs['trigger'].keyword_filter,['alpha','beta'])

    def test_apod_handles_video_and_invalid_response(self):
        embed=apod_embed({'title':'Test','explanation':'Info','media_type':'video','url':'https://example.com/video'})
        self.assertEqual(embed.url,'https://example.com/video')
        with self.assertRaises(UserError): apod_embed({'error':'invalid'})
