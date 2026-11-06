import asyncio
import logging
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from core.checks import authorize, validate_target
from core.errors import respond, UserError
from core.logging import SecretFormatter
from core.settings import Settings
from services.filters import matching_words


class CoreTests(unittest.IsolatedAsyncioTestCase):
    async def test_authorization_fails_closed(self):
        repo = SimpleNamespace(blacklists=SimpleNamespace(contains=AsyncMock(side_effect=RuntimeError('offline'))))
        with self.assertRaises(RuntimeError): await authorize(123,456,repo,[])
        repo.blacklists.contains = AsyncMock(return_value=True)
        with self.assertRaises(UserError): await authorize(123,456,repo,[])
        with self.assertRaises(UserError): await authorize(None,456,repo,[])

    async def test_response_uses_followup_after_defer(self):
        interaction = SimpleNamespace(response=SimpleNamespace(is_done=lambda:True,send_message=AsyncMock()),
                                      followup=SimpleNamespace(send=AsyncMock(return_value='followup')))
        self.assertEqual(await respond(interaction,content='done'), 'followup')

    def test_settings_reject_missing_secrets(self):
        with self.assertRaises(ValueError): Settings.from_env({})

    def test_filter_boundaries(self):
        self.assertEqual(matching_words('ALPHA beta alphabet', ['alpha','beta']), ['ALPHA','beta'])
        self.assertEqual(matching_words('unrelated', []), [])

    def test_secrets_redacted_in_traceback(self):
        formatter=SecretFormatter(['secret-token'])
        try: raise ValueError('secret-token https://user:pass@example.com postgres://user:pass@host/db')
        except ValueError:
            import sys
            record=logging.LogRecord('test',logging.ERROR,'',1,'failed secret-token',(),sys.exc_info())
        value=formatter.format(record)
        self.assertNotIn('secret-token',value)
        self.assertNotIn('user:pass',value)
        self.assertIn('ValueError',value)

    def test_owner_can_moderate_lower_bot_target(self):
        guild=SimpleNamespace(owner_id=1,me=SimpleNamespace(id=9,top_role=10,guild_permissions=SimpleNamespace(kick_members=True)))
        actor=SimpleNamespace(id=1,top_role=1,guild_permissions=SimpleNamespace(kick_members=True))
        target=SimpleNamespace(id=2,top_role=5)
        validate_target(guild,actor,target,'kick_members')
        target.id=1
        with self.assertRaises(UserError): validate_target(guild,actor,target,'kick_members')
