import logging
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path


class SecretFormatter(logging.Formatter):
    def __init__(self,secrets=()):
        super().__init__('%(asctime)s %(levelname)s %(name)s %(message)s')
        self.secrets=sorted((value for value in secrets if value),key=len,reverse=True)

    def format(self,record):
        rendered=super().format(record)
        for value in self.secrets: rendered=rendered.replace(value,'[REDACTED]')
        rendered=re.sub(r'(?:postgres(?:ql)?|mongodb(?:\+srv)?|https?)://[^\s\'\"<>]+',
                        '[REDACTED_URL]',rendered)
        rendered=re.sub(r'eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+','[REDACTED_JWT]',rendered)
        return rendered


def configure_logging(settings):
    import os
    secrets=[settings.token,settings.supabase_key,settings.nasa_key]
    secrets.extend(value for key,value in os.environ.items() if any(part in key for part in ('TOKEN','KEY','PASS','MONGO_URI','DB_URL')))
    formatter=SecretFormatter(secrets)
    root=logging.getLogger()
    root.setLevel(logging.INFO)
    for handler in list(root.handlers):
        root.removeHandler(handler)
        handler.close()
    console=logging.StreamHandler();console.setFormatter(formatter);root.addHandler(console)
    if settings.log_path:
        path=Path(settings.log_path);path.parent.mkdir(parents=True,exist_ok=True)
        handler=RotatingFileHandler(path,maxBytes=2_000_000,backupCount=3,encoding='utf-8')
        handler.setFormatter(formatter);root.addHandler(handler)
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('httpcore').setLevel(logging.WARNING)
