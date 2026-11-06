from urllib.parse import urlparse
import discord
from core.errors import UserError


def apod_embed(data):
    if not isinstance(data,dict) or data.get('media_type') not in ('image','video') or not data.get('title'):
        raise UserError('NASA returned an unavailable or unsupported APOD result.')
    url=data.get('url','')
    if urlparse(url).scheme!='https':raise UserError('NASA returned an invalid media URL.')
    embed=discord.Embed(title=str(data['title'])[:256],description=str(data.get('explanation',''))[:4000],url=url,color=0x5865F2)
    if data['media_type']=='image':embed.set_image(url=url)
    else:embed.add_field(name='Video',value=f'[Watch the video]({url})')
    return embed


async def fetch_apod(session,key):
    async with session.get('https://api.nasa.gov/planetary/apod',params={'api_key':key}) as response:
        if response.status!=200:raise UserError('NASA is unavailable or its API quota has been reached. Please try again later.')
        return apod_embed(await response.json())
