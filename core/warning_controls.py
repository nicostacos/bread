import asyncio
import discord
from core.checks import authorize,require_permission
from core.errors import UserError,defer,respond,interaction_error
from core.presentation import warning_embed
from config import GLOBAL_BLACKLIST


class DeleteConfirmation(discord.ui.View):
    def __init__(self,parent,warning_id,actor_id):
        super().__init__(timeout=60);self.parent=parent;self.warning_id=warning_id;self.actor_id=actor_id
        self.lock=asyncio.Lock();self.used=False

    @discord.ui.button(label='Confirm delete',emoji='🗑️',style=discord.ButtonStyle.danger)
    async def confirm(self,interaction,button):
        await defer(interaction,ephemeral=True)
        async with self.lock:
            if self.used:raise UserError('This confirmation was already used.')
            if interaction.user.id!=self.actor_id:raise UserError('Only the moderator who requested deletion can confirm.')
            await self.parent.check(interaction)
            row=await self.parent.bot.repos.warnings.delete(self.parent.guild_id,self.warning_id,interaction.user.id)
            self.used=True;self.stop()
            if not row:raise UserError('This case was already deleted or is no longer available.')
            await respond(interaction,embed=warning_embed(row,title='🗑️ Warning deleted',note=f'Deleted by <@{interaction.user.id}>. Audit history retained.'))

    @discord.ui.button(label='Cancel',style=discord.ButtonStyle.secondary)
    async def cancel(self,interaction,button):
        if interaction.user.id!=self.actor_id:raise UserError('Only the requesting moderator can cancel.')
        self.used=True;self.stop();await interaction.response.edit_message(content='Deletion cancelled.',view=None)

    async def on_error(self,interaction,error,item):await interaction_error(interaction,error)


class WarningControls(discord.ui.View):
    def __init__(self,bot,guild_id,rows,user_id):
        super().__init__(timeout=180);self.bot=bot;self.guild_id=int(guild_id);self.rows=rows;self.user_id=user_id;self.index=0
        self.previous.disabled=self.next.disabled=len(rows)<2
        self.delete_button.disabled=not rows

    async def check(self,interaction):
        if interaction.guild_id!=self.guild_id:raise UserError('Use this control in the original server.')
        await authorize(interaction.guild_id,interaction.user.id,self.bot.repos,GLOBAL_BLACKLIST)
        require_permission(interaction.guild,interaction.user,'moderate_members')

    async def interaction_check(self,interaction):
        if interaction.user.id!=self.user_id:
            await respond(interaction,content='Only the requesting moderator can use these controls.');return False
        return True

    def embed(self):
        return warning_embed(self.rows[self.index],title=f'⚠️ Warning history • {self.index+1}/{len(self.rows)}') if self.rows else discord.Embed(title='✅ No active warnings',color=0x57F287)

    @discord.ui.button(label='Previous',emoji='◀️',style=discord.ButtonStyle.secondary)
    async def previous(self,interaction,button):
        await defer(interaction,ephemeral=True);await self.check(interaction)
        self.index=(self.index-1)%len(self.rows);await interaction.edit_original_response(embed=self.embed(),view=self)

    @discord.ui.button(label='Next',emoji='▶️',style=discord.ButtonStyle.secondary)
    async def next(self,interaction,button):
        await defer(interaction,ephemeral=True);await self.check(interaction)
        self.index=(self.index+1)%len(self.rows);await interaction.edit_original_response(embed=self.embed(),view=self)

    @discord.ui.button(label='Delete this case',emoji='🗑️',style=discord.ButtonStyle.danger)
    async def delete_button(self,interaction,button):
        await defer(interaction,ephemeral=True);await self.check(interaction)
        row=self.rows[self.index]
        await respond(interaction,content=f"Delete warning #{row['warning_number']} (`{row['id']}`)? This does not reverse past kicks or bans.",
                      view=DeleteConfirmation(self,row['id'],interaction.user.id))

    async def on_error(self,interaction,error,item):await interaction_error(interaction,error)
