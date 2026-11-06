from datetime import timedelta
import discord
from core.errors import UserError, report_error


def bounded_positive(value,maximum):
    if not isinstance(value,int) or isinstance(value,bool) or not 1<=value<=maximum:
        raise UserError(f'Choose a value from 1 to {maximum}.')
    return value


def warning_pages(member,rows):
    pages=[]
    for offset in range(0,len(rows),5):
        embed=discord.Embed(title=f'Warnings for {member}'[:256],color=0xFFA500)
        for row in rows[offset:offset+5]:
            text=(f"Reason: {row.get('reason','')}\nEvidence: {row.get('evidence','')}\n"
                  f"Moderator: {row.get('moderator_id','unknown')}\nDate: {row.get('created_at','unknown')}")
            embed.add_field(name=f"Warning #{row['warning_number']}",value=text[:1024],inline=False)
        embed.set_footer(text=f'Page {len(pages)+1} / {(len(rows)+4)//5}')
        pages.append(embed)
    return pages or [discord.Embed(title='Warnings',description='No warnings found.')]


class ModerationService:
    def __init__(self,repos,send_log):self.repos=repos;self.send_log=send_log

    async def execute(self,guild,actor,target,action,reason,evidence='',duration=None):
        if action=='kick': await target.kick(reason=reason[:450])
        elif action=='ban': await guild.ban(target,reason=reason[:450])
        elif action=='unban': await guild.unban(target,reason=reason[:450])
        elif action=='timeout': await target.timeout(discord.utils.utcnow()+timedelta(minutes=duration),reason=reason[:450])
        else: raise ValueError('Unsupported moderation action')
        # Discord has succeeded. Never retry the action if the following audit steps fail.
        audit_error=None
        try:
            await self.repos.cases.record(guild.id,target.id,actor.id,action,reason,evidence,str(duration or ''))
        except Exception as error:
            audit_error=report_error(error,{'event':'moderation_case_after_action','guild':guild.id,'action':action})
        try:
            await self.send_log(guild,f'{action.title()} completed',f'User: {target.id}\nModerator: {actor.id}\nReason: {reason}\nEvidence: {evidence}')
        except Exception as error:
            audit_error=audit_error or report_error(error,{'event':'moderation_log_after_action','guild':guild.id,'action':action})
        return {'succeeded':True,'audit_error':audit_error}
