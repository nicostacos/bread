import discord


class Pager(discord.ui.View):
    def __init__(self,pages,user_id):
        super().__init__(timeout=180)
        self.pages=pages;self.user_id=user_id;self.index=0

    async def interaction_check(self,interaction):
        if interaction.user.id==self.user_id:return True
        await interaction.response.send_message('Only the requesting user can change pages.',ephemeral=True)
        return False

    @discord.ui.button(label='Previous',style=discord.ButtonStyle.secondary)
    async def previous(self,interaction,button):
        self.index=(self.index-1)%len(self.pages)
        await interaction.response.edit_message(embed=self.pages[self.index],view=self)

    @discord.ui.button(label='Next',style=discord.ButtonStyle.secondary)
    async def next(self,interaction,button):
        self.index=(self.index+1)%len(self.pages)
        await interaction.response.edit_message(embed=self.pages[self.index],view=self)
