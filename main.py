"""Bread Bot entry point. Supabase is the only runtime database."""
import asyncio
import logging
import signal
from aiohttp import web
from bot import BreadBot
from core.settings import Settings
from core.logging import configure_logging


async def run():
    settings=Settings.from_env()
    configure_logging(settings)
    bot=BreadBot(settings)
    stop=asyncio.Event()
    loop=asyncio.get_running_loop()
    for sig in (signal.SIGINT,signal.SIGTERM):
        try:loop.add_signal_handler(sig,stop.set)
        except (NotImplementedError,RuntimeError):pass
    runner=None
    if settings.health_port:
        async def health(request):
            ready=bot.is_ready() and bot.database_ready
            if ready:
                try:await bot.repos.check()
                except Exception:ready=False
            return web.json_response({'status':'ready' if ready else 'not_ready'},status=200 if ready else 503)
        app=web.Application();app.router.add_get('/health',health)
        runner=web.AppRunner(app);await runner.setup();await web.TCPSite(runner,'0.0.0.0',settings.health_port).start()
    task=stop_task=None
    try:
        async with bot:
            task=asyncio.create_task(bot.start(settings.token),name='discord')
            stop_task=asyncio.create_task(stop.wait())
            done,_=await asyncio.wait((task,stop_task),return_when=asyncio.FIRST_COMPLETED)
            if task in done:await task
    finally:
        for pending in (task,stop_task):
            if pending:pending.cancel()
        await asyncio.gather(*(t for t in (task,stop_task) if t),return_exceptions=True)
        if runner:await runner.cleanup()


if __name__=='__main__':
    try:asyncio.run(run())
    except KeyboardInterrupt:pass
    except Exception:
        logging.getLogger(__name__).exception('Bot stopped due to an unrecoverable startup error')
        raise SystemExit(1)
