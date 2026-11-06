"""Shared, bounded Discord embeds for commands and validation feedback."""
import discord
from discord.ext import commands


def argument_embed(ctx,error):
    command=ctx.command
    name=getattr(command,'qualified_name','command')
    prefix=getattr(ctx,'clean_prefix',None) or 'bread '
    signature=getattr(command,'signature','')
    param=getattr(error,'param',None) or getattr(ctx,'current_parameter',None)
    if isinstance(error,commands.MissingRequiredArgument):
        detail=f'Please provide **{param.name}**.'
    elif param:detail=f'I could not understand **{param.name}**. {str(error)[:400]}'
    else:detail=f'I could not read those arguments. {str(error)[:400]}'
    embed=discord.Embed(title='📝 Let’s complete your command',description=detail,color=0xFEE75C)
    embed.add_field(name='📌 Expected usage',value=f'`{prefix}{name} {signature}`'[:1024],inline=False)
    params=getattr(command,'clean_params',{})
    if params:
        embed.add_field(name='📋 Arguments',value='\n'.join(f'**{key}** — '+('required' if p.required else 'optional') for key,p in params.items())[:1024],inline=False)
    examples={'warn':'@member Repeated spam','warnings':'@member','kick':'@member Repeated spam',
              'setlog':'#mod-logs','setwelcome':'#welcome','filter add':'example','blacklist add':'@member'}
    if name in examples:embed.add_field(name='💡 Example',value=f'`{prefix}{name} {examples[name]}`',inline=False)
    embed.set_footer(text='<argument> = required • [argument] = optional • Use bread help for more commands')
    return embed


def help_embed(bot):
    embed=discord.Embed(title='🍞 Bread Bot • Help',description='Your server’s moderation and utility companion.\nUse `/` for slash commands or `bread ` for prefix commands.',color=0x5865F2)
    labels={'utility':'✨ Utilities','moderation':'🛡️ Moderation','admin':'⚙️ Server settings'}
    for group,label in labels.items():
        slash=[c for c in bot.tree.get_commands() if f'.{group}.' in type(c.binding).__module__]
        prefix=[c for c in bot.commands if f'.{group}.' in type(c.cog).__module__]
        embed.add_field(name=label,value=' '.join(f'`/{c.name}`' for c in sorted(slash,key=lambda c:c.name)) or 'None',inline=False)
        if prefix:embed.add_field(name='↳ Prefix alternatives',value=' '.join(f'`bread {c.name}`' for c in sorted(prefix,key=lambda c:c.name)),inline=False)
    embed.add_field(name='📝 Warnings & evidence',value='`bread warn @member reason` opens a form for evidence.\n`bread warnings @member` shows cases and individual delete controls.\nModerator permissions are required.',inline=False)
    embed.set_footer(text='Tip: a missing argument will show the expected usage and an example.')
    if getattr(bot.user,'display_avatar',None):embed.set_thumbnail(url=bot.user.display_avatar.url)
    return embed


def user_info_embed(user,member=None):
    embed=discord.Embed(title=f'👤 {getattr(user,"display_name",str(user))}'[:256],description=f'<@{user.id}>',color=0x5865F2)
    avatar=getattr(user,'display_avatar',None)
    if avatar:embed.set_thumbnail(url=avatar.url)
    embed.add_field(name='🏷️ Username',value=str(getattr(user,'name',user))[:1024],inline=False)
    embed.add_field(name='🆔 User ID',value=f'`{user.id}`',inline=False)
    embed.add_field(name='📅 Account created',value=discord.utils.format_dt(user.created_at,'F')+'\n'+discord.utils.format_dt(user.created_at,'R'),inline=False)
    if member:
        if getattr(member,'joined_at',None):embed.add_field(name='📥 Joined this server',value=discord.utils.format_dt(member.joined_at,'F')+'\n'+discord.utils.format_dt(member.joined_at,'R'),inline=False)
        roles=list(getattr(member,'roles',[]))[1:]
        embed.add_field(name=f'🎭 Roles ({len(roles)})',value=(', '.join(discord.utils.escape_markdown(r.name) for r in roles)[:1024] or 'No assigned roles'),inline=False)
    embed.add_field(name='🤖 Account type',value='Bot' if getattr(user,'bot',False) else 'Member',inline=False)
    return embed


def warning_embed(row,title='⚠️ Warning recorded',note=''):
    embed=discord.Embed(title=title,color=0xFEE75C)
    embed.add_field(name='👤 Member',value=f"<@{row.get('user_id','unknown')}>",inline=False)
    embed.add_field(name='🛡️ Moderator',value=f"<@{row.get('moderator_id','unknown')}>",inline=False)
    embed.add_field(name='📝 Reason',value=str(row.get('reason') or 'Not provided')[:1024],inline=False)
    embed.add_field(name='🔎 Evidence',value=str(row.get('evidence') or 'Not provided')[:1024],inline=False)
    embed.add_field(name='🗂️ Case',value=f"Warning #{row.get('warning_number','?')}\n`{row.get('id','unknown')}`",inline=False)
    if note:embed.add_field(name='ℹ️ Result',value=note[:1024],inline=False)
    embed.set_footer(text='Delete controls remove this warning from active history; audit records are retained.')
    return embed
