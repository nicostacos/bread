import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from commands.utility.info import server_info_embed


class ServerInfoTests(unittest.TestCase):
    def guild(self,**overrides):
        values=dict(name='Freshblox Shop',id=1501332741440934002,owner_id=123,
            owner=SimpleNamespace(name='keykye0683'),member_count=12,roles=list(range(72)),
            categories=list(range(15)),text_channels=list(range(46)),voice_channels=[1],
            created_at=datetime(2026,5,5,16,20,tzinfo=timezone.utc),
            icon=SimpleNamespace(url='https://cdn.discordapp.com/icons/test.png'))
        return SimpleNamespace(**(values|overrides))

    def test_grouped_stats_icon_and_timestamps(self):
        embed=server_info_embed(self.guild())
        self.assertEqual(embed.title,'Freshblox Shop')
        self.assertEqual(embed.thumbnail.url,'https://cdn.discordapp.com/icons/test.png')
        self.assertIn('**Owner:** keykye0683',embed.description)
        self.assertIn('**Members:** 12',embed.description)
        self.assertIn('**Roles:** 72',embed.description)
        self.assertIn('**Category Channels:** 15',embed.fields[0].value)
        self.assertIn('**Text Channels:** 46',embed.fields[0].value)
        self.assertIn('**Voice Channels:** 1',embed.fields[0].value)
        self.assertIn('1501332741440934002',embed.fields[1].value)
        self.assertIn(':F>',embed.fields[1].value)
        self.assertIn(':R>',embed.fields[1].value)
        self.assertTrue(all(not field.inline for field in embed.fields))

    def test_missing_owner_icon_and_count(self):
        embed=server_info_embed(self.guild(owner=None,icon=None,member_count=None))
        self.assertIn('<@123>',embed.description)
        self.assertIn('Unknown',embed.description)
        self.assertIsNone(embed.thumbnail.url)
