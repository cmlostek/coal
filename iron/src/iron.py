import discord
from discord.ext import commands
import aiosqlite
import os
import asyncio
import logging
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
log = logging.getLogger('iron')

MODULES = [
    'modules.setup',
    'modules.tasks',
    'modules.reminders',
    'modules.tags',
    'modules.calendar_module',
    'modules.canvas_module',
    'modules.email_module',
    'modules.weather',
    'modules.stats',
    'modules.daily_digest',
    'modules.economy',
    'modules.grave',
    'modules.levels',
    'modules.minecraft',
    'modules.utils',
]

DB_TABLES = [
    # ── Legacy tables ────────────────────────────────────────────────────────
    '''CREATE TABLE IF NOT EXISTS death_log (
        log_id   INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id  TEXT,
        cntr     INTEGER,
        reason   TEXT
    )''',
    '''CREATE TABLE IF NOT EXISTS balances (
        user_id    INTEGER PRIMARY KEY,
        balance    INTEGER DEFAULT 1000,
        last_daily TEXT,
        last_work  TEXT
    )''',
    '''CREATE TABLE IF NOT EXISTS levels (
        id    INTEGER PRIMARY KEY,
        level INTEGER DEFAULT 1,
        xp    INTEGER DEFAULT 0
    )''',
    # ── Guild config ─────────────────────────────────────────────────────────
    '''CREATE TABLE IF NOT EXISTS guild_config (
        guild_id              INTEGER PRIMARY KEY,
        prefix                TEXT    DEFAULT '!',
        daily_digest_channel  INTEGER,
        reminder_channel      INTEGER,
        digest_time           TEXT    DEFAULT '08:00',
        timezone              TEXT    DEFAULT 'America/New_York',
        weather_location      TEXT,
        setup_complete        INTEGER DEFAULT 0
    )''',
    # ── Tasks ────────────────────────────────────────────────────────────────
    '''CREATE TABLE IF NOT EXISTS tasks (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id      INTEGER NOT NULL,
        guild_id     INTEGER NOT NULL,
        title        TEXT    NOT NULL,
        description  TEXT,
        due_date     TEXT,
        priority     TEXT DEFAULT 'medium',
        status       TEXT DEFAULT 'pending',
        created_at   TEXT DEFAULT CURRENT_TIMESTAMP,
        completed_at TEXT,
        tag          TEXT
    )''',
    # ── Class assignments ────────────────────────────────────────────────────
    '''CREATE TABLE IF NOT EXISTS assignments (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id      INTEGER NOT NULL,
        guild_id     INTEGER NOT NULL,
        title        TEXT    NOT NULL,
        course       TEXT    NOT NULL,
        description  TEXT,
        due_date     TEXT    NOT NULL,
        points       INTEGER,
        status       TEXT DEFAULT 'pending',
        grade        TEXT,
        source       TEXT DEFAULT 'manual',
        canvas_id    TEXT,
        created_at   TEXT DEFAULT CURRENT_TIMESTAMP,
        completed_at TEXT
    )''',
    # ── Reminders ────────────────────────────────────────────────────────────
    '''CREATE TABLE IF NOT EXISTS reminders (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id    INTEGER NOT NULL,
        guild_id   INTEGER NOT NULL,
        channel_id INTEGER NOT NULL,
        message    TEXT    NOT NULL,
        remind_at  TEXT    NOT NULL,
        created_at TEXT    DEFAULT CURRENT_TIMESTAMP,
        sent       INTEGER DEFAULT 0
    )''',
    # ── Tags ─────────────────────────────────────────────────────────────────
    '''CREATE TABLE IF NOT EXISTS tags (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id   INTEGER NOT NULL,
        name       TEXT    NOT NULL,
        content    TEXT    NOT NULL,
        owner_id   INTEGER NOT NULL,
        uses       INTEGER DEFAULT 0,
        created_at TEXT    DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(guild_id, name)
    )''',
    # ── Google Calendar config (per user) ────────────────────────────────────
    '''CREATE TABLE IF NOT EXISTS calendar_config (
        user_id     INTEGER PRIMARY KEY,
        credentials TEXT,
        calendar_id TEXT DEFAULT 'primary'
    )''',
    # ── ICS / iCal feed URLs (per user, multiple) ────────────────────────────
    '''CREATE TABLE IF NOT EXISTS calendar_ics (
        id      INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        name    TEXT    NOT NULL,
        url     TEXT    NOT NULL,
        UNIQUE(user_id, name)
    )''',
    # ── Canvas config (per user) ─────────────────────────────────────────────
    '''CREATE TABLE IF NOT EXISTS canvas_config (
        user_id    INTEGER PRIMARY KEY,
        api_key    TEXT,
        canvas_url TEXT
    )''',
    # ── Email / IMAP config (per user) ──────────────────────────────────────
    '''CREATE TABLE IF NOT EXISTS email_config (
        user_id      INTEGER PRIMARY KEY,
        email_addr   TEXT,
        app_password TEXT,
        imap_server  TEXT DEFAULT 'imap.gmail.com',
        sleep_start  TEXT DEFAULT '22:00',
        sleep_end    TEXT DEFAULT '07:00'
    )''',
    # ── Task completion stats ─────────────────────────────────────────────────
    '''CREATE TABLE IF NOT EXISTS task_stats (
        id                     INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id                INTEGER NOT NULL,
        guild_id               INTEGER NOT NULL,
        date                   TEXT    NOT NULL,
        tasks_completed        INTEGER DEFAULT 0,
        tasks_on_time          INTEGER DEFAULT 0,
        tasks_late             INTEGER DEFAULT 0,
        assignments_completed  INTEGER DEFAULT 0
    )''',
]


class IronBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        super().__init__(
            command_prefix=commands.when_mentioned_or('!', '-', '?'),
            intents=intents,
            help_command=None,
        )

    async def setup_hook(self):
        db_path = os.getenv('DATABASE', 'iron_db.db')
        self.db = await aiosqlite.connect(db_path)
        self.db.row_factory = aiosqlite.Row
        await self._init_db()

        for module in MODULES:
            try:
                await self.load_extension(module)
                log.info('Loaded: %s', module)
            except Exception as exc:
                log.error('Failed to load %s: %s', module, exc, exc_info=True)

    async def _init_db(self):
        async with self.db.cursor() as cur:
            for sql in DB_TABLES:
                await cur.execute(sql)
        await self.db.commit()
        log.info('Database initialised.')

    async def on_ready(self):
        log.info('Logged in as %s (ID %s)', self.user, self.user.id)
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name='your productivity | !help',
            )
        )

    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.CommandNotFound):
            return
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(
                embed=discord.Embed(
                    description=f'Missing argument: `{error.param.name}`. '
                                f'Run `!help {ctx.command}` for usage.',
                    color=discord.Color.red(),
                )
            )
        elif isinstance(error, commands.BadArgument):
            await ctx.send(
                embed=discord.Embed(
                    description=f'Invalid argument. Run `!help {ctx.command}` for usage.',
                    color=discord.Color.red(),
                )
            )
        elif isinstance(error, commands.CheckFailure):
            await ctx.send(
                embed=discord.Embed(
                    description="You don't have permission to use that command.",
                    color=discord.Color.red(),
                )
            )
        else:
            log.error('Unhandled error in %s: %s', ctx.command, error, exc_info=error)

    async def close(self):
        await self.db.close()
        await super().close()


def main():
    token = os.getenv('DISCORD_TOKEN')
    if not token:
        raise RuntimeError('DISCORD_TOKEN is not set in the environment.')
    bot = IronBot()
    try:
        bot.run(token, log_handler=None)
    except discord.errors.LoginFailure:
        log.critical('Invalid token. Check your DISCORD_TOKEN.')
    except KeyboardInterrupt:
        log.info('Bot stopped by user.')


if __name__ == '__main__':
    main()
