from core.errors import UserError


class InviteService:
    async def create_url(self,guild,reason):
        channel=next((ch for ch in guild.text_channels if ch.permissions_for(guild.me).create_instant_invite),None)
        if channel is None:raise UserError('The bot needs Create Invite permission in a text channel.')
        invite=await channel.create_invite(max_age=604800,max_uses=1,unique=True,reason=reason[:450])
        return invite.url

    async def send_once(self,guild,user,reason):
        url=await self.create_url(guild,reason)
        await user.send(f'You have been invited back to **{guild.name}**.\nReason: {reason[:1500]}\n{url}')
