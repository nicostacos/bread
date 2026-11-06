import logging
from uuid import uuid4
from discord import app_commands
from discord.ext import commands

logger=logging.getLogger(__name__)


async def defer(interaction,ephemeral=False):
    if not interaction.response.is_done():await interaction.response.defer(ephemeral=ephemeral)


class UserError(commands.CheckFailure, app_commands.CheckFailure):
    """Expected user-facing rejection with no internal details."""


async def respond(interaction, *, content=None, embed=None, ephemeral=True, **kwargs):
    sender=interaction.followup.send if interaction.response.is_done() else interaction.response.send_message
    return await sender(content=content,embed=embed,ephemeral=ephemeral,**kwargs)


def report_error(error, context):
    reference=uuid4().hex[:12]
    logger.error('Failure id=%s context=%s',reference,context,
                 exc_info=(type(error),error,error.__traceback__))
    return reference


async def interaction_error(interaction,error):
    error=getattr(error,'original',error)
    if isinstance(error,UserError): message=str(error)
    elif isinstance(error,(app_commands.CheckFailure,commands.CheckFailure)):
        message='You do not have permission to use this command.'
    else:
        ref=report_error(error,{'command':getattr(interaction.command,'qualified_name',None),'guild':interaction.guild_id})
        message=f'The command could not finish. Error ID: {ref}. A completed moderation action is not automatically undone.'
    try: await respond(interaction,content=message)
    except Exception as delivery_error: report_error(delivery_error,{'event':'error_response'})
