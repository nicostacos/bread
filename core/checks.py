from core.errors import UserError


async def authorize(guild_id,user_id,repos,global_blacklist):
    if guild_id is None: raise UserError('Use this command in a server.')
    if int(user_id) in global_blacklist or await repos.blacklists.contains(str(guild_id),str(user_id)):
        raise UserError('You are blocked from using this bot.')


def require_permission(guild,actor,permission,bot_permission=None):
    if guild is None: raise UserError('Use this command in a server.')
    if actor.id != guild.owner_id and not getattr(actor.guild_permissions,permission,False):
        raise UserError('Missing permission: '+permission.replace('_',' '))
    if bot_permission and not getattr(guild.me.guild_permissions,bot_permission,False):
        raise UserError('The bot is missing permission: '+bot_permission.replace('_',' '))


def validate_target(guild,actor,target,permission):
    require_permission(guild,actor,permission,permission)
    if target.id in (actor.id,guild.me.id,guild.owner_id):
        raise UserError('That member cannot be targeted.')
    if actor.id!=guild.owner_id and target.top_role>=actor.top_role:
        raise UserError('That member has an equal or higher role than you.')
    if target.top_role>=guild.me.top_role:
        raise UserError('That member has an equal or higher role than the bot.')
