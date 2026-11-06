import unittest
import httpx
from types import SimpleNamespace
from unittest.mock import patch
from repositories.configs import ConfigRepository
from repositories.warnings import WarningRepository
from repositories.client import create_repositories
from core.settings import Settings


class Query:
    def __init__(self, transport): self.transport=transport
    def select(self,*args,**kwargs): return self
    def eq(self,*args): return self
    def is_(self,*args):return self
    def order(self,*args): return self
    def range(self,start,end): self.bounds=(start,end);return self
    async def execute(self):
        if self.transport.fail: raise RuntimeError('database unavailable')
        start,end=self.bounds
        return SimpleNamespace(data=self.transport.rows[start:end+1])

class Transport:
    def __init__(self,rows): self.rows=rows;self.fail=False
    def table(self,name): return Query(self)


class RepositoryTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_async_client_initialization_and_shutdown(self):
        transport=httpx.AsyncClient(transport=httpx.MockTransport(lambda request:httpx.Response(200,json=[])))
        with patch('repositories.client.httpx.AsyncClient',return_value=transport):
            repos=await create_repositories(Settings('test','https://test.supabase.co','sb_secret_test'),[])
        await repos.close()
        self.assertTrue(transport.is_closed)

    async def test_warning_pagination_preserves_all_rows(self):
        transport=Transport([{'id':str(i)} for i in range(1205)])
        rows=await WarningRepository(transport).list('123','456')
        self.assertEqual(len(rows),1205)
        self.assertEqual(rows[-1]['id'],'1204')

    async def test_persistence_failure_propagates(self):
        transport=Transport([]);transport.fail=True
        with self.assertRaises(RuntimeError): await ConfigRepository(transport).get('123')
