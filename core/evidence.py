"""One-use, author-owned evidence form for prefix moderation commands."""
import asyncio
import time
import discord
from core.checks import authorize
from core.errors import UserError,defer,interaction_error,report_error
from config import GLOBAL_BLACKLIST


class EvidenceModal(discord.ui.Modal):
    def __init__(self,flow):
        super().__init__(title=f'{flow.action.title()} member — evidence',timeout=180)
        self.flow=flow
        self.reason=discord.ui.TextInput(label='Reason',default=flow.reason[:1500],max_length=1500,style=discord.TextStyle.paragraph)
        self.evidence=discord.ui.TextInput(label='Evidence (optional)',placeholder='Links or a description of the evidence',
                                         required=False,max_length=1500,style=discord.TextStyle.paragraph)
        self.add_item(self.reason);self.add_item(self.evidence)

    async def on_submit(self,interaction):
        try:await self.flow.submit(interaction,str(self.reason),str(self.evidence))
        except Exception as error:await interaction_error(interaction,error)

    async def on_error(self,interaction,error):await interaction_error(interaction,error)


class EvidenceView(discord.ui.View):
    def __init__(self,bot,action,author_id,guild_id,member_id,reason):
        super().__init__(timeout=180)
        if action not in ('kick','warn'):raise ValueError('Unsupported evidence action')
        self.bot=bot;self.action=action;self.author_id=author_id;self.guild_id=guild_id
        self.member_id=member_id;self.reason=reason;self.used=False
        self.expires_at=time.monotonic()+180;self.lock=asyncio.Lock()
        self.prompt_message=None

    def validate(self,interaction):
        if interaction.user.id!=self.author_id or interaction.guild_id!=self.guild_id:
            raise UserError('Only the requesting moderator can use this form in the original server.')
        if self.used:raise UserError('This form was already submitted. Check its result before issuing a new command.')
        if time.monotonic()>=self.expires_at:raise UserError('This form expired. Run the command again.')

    async def interaction_check(self,interaction):
        try:self.validate(interaction);return True
        except UserError as error:
            await interaction_error(interaction,error);return False

    @discord.ui.button(label='Add evidence & continue',style=discord.ButtonStyle.primary)
    async def evidence_button(self,interaction,button):
        self.prompt_message=interaction.message
        await interaction.response.send_modal(EvidenceModal(self))

    async def submit(self,interaction,reason,evidence):
        await defer(interaction,ephemeral=True)
        async with self.lock:
            self.validate(interaction)
            await authorize(interaction.guild_id,interaction.user.id,self.bot.repos,GLOBAL_BLACKLIST)
            if not reason.strip():raise UserError('A reason is required.')
            # Never replay after an ambiguous external action failure.
            self.used=True;self.stop()
            member=await interaction.guild.fetch_member(self.member_id)
            command=self.bot.tree.get_command(self.action)
            # The callback rechecks current actor/bot permissions and target hierarchy.
            await command.callback(command.binding,interaction,member=member,reason=reason,evidence=evidence)
            if self.action=='warn' and self.prompt_message is not None:
                try:await self.prompt_message.delete()
                except discord.NotFound:pass
                except discord.HTTPException as error:
                    report_error(error,{'event':'warning_prepare_message_cleanup','guild':interaction.guild_id})

    async def on_error(self,interaction,error,item):await interaction_error(interaction,error)
