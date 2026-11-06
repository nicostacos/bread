import os
from dataclasses import dataclass, field
from pathlib import Path
from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    token: str = field(repr=False)
    supabase_url: str
    supabase_key: str = field(repr=False)
    nasa_key: str = field(default='DEMO_KEY', repr=False)
    guild_id: int | None = None
    owner_id: int | None = None
    health_port: int | None = None
    log_path: str = 'logs/bread_bot.log'

    @classmethod
    def from_env(cls, env=None):
        if env is None:
            load_dotenv(Path(__file__).resolve().parents[1]/'.env')
            env = os.environ
        required = ('DISCORD_TOKEN','SUPABASE_URL','SUPABASE_SERVICE_ROLE_KEY')
        missing = [key for key in required if not env.get(key)]
        if missing: raise ValueError('Missing configuration: '+', '.join(missing))
        url=env['SUPABASE_URL'].rstrip('/')
        if not url.startswith('https://') or not url.endswith('.supabase.co'):
            raise ValueError('SUPABASE_URL must be an HTTPS Supabase project URL')
        optional_int=lambda key: int(env[key]) if env.get(key) else None
        return cls(env['DISCORD_TOKEN'],url,env['SUPABASE_SERVICE_ROLE_KEY'],
                   env.get('NASA_API_KEY') or 'DEMO_KEY',optional_int('DISCORD_GUILD_ID'),
                   optional_int('BOT_OWNER_ID'),optional_int('HEALTH_PORT'),env.get('LOG_PATH','logs/bread_bot.log'))
