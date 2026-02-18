"""
modules/daily_digest.py – Automated daily and weekly digest.

The background loop fires every minute and checks whether it's time to post
the digest for any configured guild. The digest aggregates:
  • Current weather & daily forecast
  • Today's Google Calendar events
  • Tasks due today / overdue
  • Assignments due today or this week
  • Overnight email count
  • Weekly stats graph (on Mondays)

Configuration is per-guild via `!setup`.
"""
import discord
from discord.ext import commands, tasks
import asyncio
import aiohttp
import logging
import os
import io
from datetime import datetime, timezone, timedelta

import pytz

log = logging.getLogger(__name__)

BASE_WEATHER = 'https://api.openweathermap.org/data/2.5'

CONDITION_EMOJI = {
    'clear': '☀️', 'clouds': '☁️', 'rain': '🌧️', 'drizzle': '🌦️',
    'thunderstorm': '⛈️', 'snow': '❄️', 'mist': '🌫️', 'haze': '🌫️',
    'fog': '🌫️', 'dust': '💨', 'tornado': '🌪️',
}


def _w_emoji(cond: str) -> str:
    return CONDITION_EMOJI.get(cond.lower(), '🌡️')


async def _weather_section(location: str, api_key: str) -> str:
    """Return a formatted weather string for the digest."""
    try:
        params = {'q': location, 'appid': api_key, 'units': 'imperial'}
        async with aiohttp.ClientSession() as sess:
            async with sess.get(f'{BASE_WEATHER}/weather', params=params) as r:
                if r.status != 200:
                    return f'⚠️ Weather unavailable for {location}'
                d = await r.json()
        emoji = _w_emoji(d['weather'][0]['main'])
        temp  = d['main']['temp']
        desc  = d['weather'][0]['description'].title()
        hi    = d['main']['temp_max']
        lo    = d['main']['temp_min']
        hum   = d['main']['humidity']
        return f'{emoji} **{location.title()}** — {desc} | {temp}°F (Hi {hi}°F / Lo {lo}°F) 💧{hum}%'
    except Exception as exc:
        log.debug('Weather section failed: %s', exc)
        return f'⚠️ Could not fetch weather for {location}'


async def _forecast_section(location: str, api_key: str) -> str:
    """Return a short 5-day forecast string."""
    try:
        params = {'q': location, 'appid': api_key, 'units': 'imperial', 'cnt': 40}
        async with aiohttp.ClientSession() as sess:
            async with sess.get(f'{BASE_WEATHER}/forecast', params=params) as r:
                if r.status != 200:
                    return ''
                d = await r.json()

        days: dict[str, list] = {}
        for item in d['list']:
            dt = datetime.utcfromtimestamp(item['dt'])
            key = dt.strftime('%Y-%m-%d')
            days.setdefault(key, []).append(item)

        lines = []
        for date_key in list(days.keys())[:5]:
            items = days[date_key]
            temps = [i['main']['temp'] for i in items]
            conds = [i['weather'][0]['main'] for i in items]
            pop   = max(i.get('pop', 0) for i in items) * 100
            most  = max(set(conds), key=conds.count)
            emoji = _w_emoji(most)
            dt    = datetime.strptime(date_key, '%Y-%m-%d')
            label = dt.strftime('%a')
            lines.append(f'{emoji} **{label}** {int(max(temps))}°/{int(min(temps))}° {int(pop)}%🌧️')

        return ' · '.join(lines)
    except Exception as exc:
        log.debug('Forecast section failed: %s', exc)
        return ''


async def _calendar_section(bot, user_id: int, tz_name: str) -> str:
    """Fetch today's Google Calendar events (reads from token.json on disk)."""
    try:
        from modules.calendar_module import get_todays_events, _fmt_event

        tz = pytz.timezone(tz_name)
        now_local = datetime.now(tz)
        start = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
        end   = start + timedelta(days=1)

        events = await get_todays_events(start, end)
        if not events:
            return '📅 No calendar events today.'
        return '📅 **Calendar:**\n' + '\n'.join(_fmt_event(e) for e in events[:10])
    except Exception as exc:
        log.debug('Calendar section failed: %s', exc)
        return ''


async def _tasks_section(bot, user_id: int, guild_id: int) -> str:
    """Get today's and overdue tasks."""
    today = datetime.now().date().isoformat()
    tomorrow = (datetime.now().date() + timedelta(days=1)).isoformat()

    async with bot.db.cursor() as cur:
        await cur.execute(
            '''SELECT * FROM tasks
               WHERE user_id=? AND guild_id=? AND status!='completed'
                 AND due_date >= ? AND due_date < ?
               ORDER BY priority''',
            (user_id, guild_id, today, tomorrow),
        )
        due_today = await cur.fetchall()
        await cur.execute(
            '''SELECT * FROM tasks
               WHERE user_id=? AND guild_id=? AND status!='completed'
                 AND due_date < ?
               ORDER BY due_date ASC LIMIT 5''',
            (user_id, guild_id, today),
        )
        overdue = await cur.fetchall()

    lines = []
    if overdue:
        lines.append(f'⚠️ **Overdue ({len(overdue)}):**')
        for r in overdue:
            lines.append(f'  🔴 #{r["id"]} {r["title"]}')
    if due_today:
        lines.append(f'📋 **Due Today ({len(due_today)}):**')
        prio = {'high': '🔴', 'medium': '🟡', 'low': '🟢'}
        for r in due_today:
            lines.append(f'  {prio.get(r["priority"], "⬜")} #{r["id"]} {r["title"]}')
    return '\n'.join(lines) if lines else '✅ No tasks due today!'


async def _assignments_section(bot, user_id: int, guild_id: int) -> str:
    """Get assignments due today or this week."""
    today = datetime.now().date().isoformat()
    week  = (datetime.now().date() + timedelta(days=7)).isoformat()

    async with bot.db.cursor() as cur:
        await cur.execute(
            '''SELECT * FROM assignments
               WHERE user_id=? AND guild_id=? AND status NOT IN ('completed','submitted')
                 AND due_date >= ? AND due_date <= ?
               ORDER BY due_date ASC LIMIT 10''',
            (user_id, guild_id, today, week),
        )
        rows = await cur.fetchall()

    if not rows:
        return ''
    lines = ['📚 **Assignments this week:**']
    for r in rows:
        try:
            due_dt = datetime.fromisoformat(r['due_date'])
            delta  = (due_dt.date() - datetime.now().date()).days
            badge  = '**today**' if delta == 0 else f'in {delta}d'
        except Exception:
            badge = r['due_date']
        lines.append(f'  📖 **{r["course"]}** – {r["title"]} ({badge})')
    return '\n'.join(lines)


async def _email_section(bot, user_id: int) -> str:
    """Count overnight emails."""
    try:
        from modules.email_module import _count_overnight_emails
        async with bot.db.cursor() as cur:
            await cur.execute('SELECT * FROM email_config WHERE user_id = ?', (user_id,))
            row = await cur.fetchone()
        if not row or not row['email_addr']:
            return ''
        result = await _count_overnight_emails(
            row['email_addr'], row['app_password'], row['imap_server'],
            row['sleep_start'], row['sleep_end'],
        )
        count = result['count']
        return f'📧 **{count}** new email(s) while you slept ({result["window"]})'
    except Exception as exc:
        log.debug('Email section failed: %s', exc)
        return ''


async def _stats_graph(bot, user_id: int, guild_id: int) -> io.BytesIO | None:
    """Generate a 7-day stats graph for the weekly digest."""
    try:
        from datetime import timezone as _tz
        cutoff = (datetime.now(_tz.utc) - timedelta(days=7)).date().isoformat()
        async with bot.db.cursor() as cur:
            await cur.execute(
                '''SELECT date, tasks_completed, tasks_on_time
                   FROM task_stats
                   WHERE user_id=? AND guild_id=? AND date >= ?
                   ORDER BY date ASC''',
                (user_id, guild_id, cutoff),
            )
            rows = await cur.fetchall()
        if not rows:
            return None

        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        import numpy as np

        def _draw():
            labels = [r['date'][5:] for r in rows]
            done   = [r['tasks_completed'] for r in rows]
            ot     = [r['tasks_on_time'] for r in rows]
            x = np.arange(len(labels))

            fig, ax = plt.subplots(figsize=(8, 4), facecolor='#2b2d31')
            ax.set_facecolor('#2b2d31')
            ax.bar(x - 0.2, done, 0.35, label='Completed', color='#5865F2', zorder=3)
            ax.bar(x + 0.2, ot,   0.35, label='On Time',   color='#57F287', zorder=3)
            ax.set_xticks(x)
            ax.set_xticklabels(labels, color='white', fontsize=8)
            ax.tick_params(colors='white')
            ax.spines[:].set_color('#40444b')
            ax.yaxis.grid(True, color='#40444b', zorder=0)
            ax.set_title('Last 7 Days', color='white', fontweight='bold')
            ax.legend(facecolor='#40444b', labelcolor='white')
            plt.tight_layout()
            buf = io.BytesIO()
            plt.savefig(buf, format='png', dpi=100, bbox_inches='tight', facecolor=fig.get_facecolor())
            plt.close(fig)
            buf.seek(0)
            return buf

        return await asyncio.to_thread(_draw)
    except Exception as exc:
        log.debug('Stats graph failed: %s', exc)
        return None


# ─── Cog ─────────────────────────────────────────────────────────────────────

class DailyDigest(commands.Cog):
    """Automated daily digest sender."""

    def __init__(self, bot):
        self.bot = bot
        self._sent_today: set[int] = set()   # guild_ids that got today's digest
        self.digest_loop.start()

    def cog_unload(self):
        self.digest_loop.cancel()

    @tasks.loop(minutes=1)
    async def digest_loop(self):
        """Check every minute if any guild needs its digest sent."""
        now_utc = datetime.now(timezone.utc)

        async with self.bot.db.cursor() as cur:
            await cur.execute(
                '''SELECT * FROM guild_config
                   WHERE setup_complete = 1
                     AND daily_digest_channel IS NOT NULL
                     AND digest_time IS NOT NULL''',
            )
            guilds = await cur.fetchall()

        for cfg in guilds:
            guild_id = cfg['guild_id']
            tz_name  = cfg['timezone'] or 'UTC'
            try:
                tz = pytz.timezone(tz_name)
            except Exception:
                tz = pytz.UTC

            now_local = now_utc.astimezone(tz)
            digest_h, digest_m = map(int, (cfg['digest_time'] or '08:00').split(':'))

            # Has the digest time arrived?
            if now_local.hour != digest_h or now_local.minute != digest_m:
                continue

            # Only send once per day per guild
            day_key = (guild_id, now_local.date().isoformat())
            if day_key in self._sent_today:
                continue
            self._sent_today.add(day_key)

            asyncio.create_task(self._send_digest(cfg, now_local))

        # Clear sent cache at midnight UTC
        if now_utc.hour == 0 and now_utc.minute == 0:
            self._sent_today.clear()

    @digest_loop.before_loop
    async def before_digest(self):
        await self.bot.wait_until_ready()

    async def _send_digest(self, cfg, now_local):
        guild = self.bot.get_guild(cfg['guild_id'])
        if not guild:
            return
        channel = guild.get_channel(cfg['daily_digest_channel'])
        if not channel:
            return

        api_key  = os.getenv('OPENWEATHER_API_KEY', '')
        location = cfg['weather_location'] or ''
        tz_name  = cfg['timezone'] or 'UTC'
        is_monday = now_local.weekday() == 0

        # ── Build digest for each member who has tasks in this guild ────────
        async with self.bot.db.cursor() as cur:
            await cur.execute(
                '''SELECT DISTINCT user_id FROM tasks WHERE guild_id = ?
                   UNION
                   SELECT DISTINCT user_id FROM assignments WHERE guild_id = ?''',
                (cfg['guild_id'], cfg['guild_id']),
            )
            user_rows = await cur.fetchall()

        user_ids = [r['user_id'] for r in user_rows]

        # ── Server-wide sections (weather) ───────────────────────────────────
        header_embed = discord.Embed(
            title=f'🌅 Daily Digest — {now_local.strftime("%A, %B %d, %Y")}',
            color=0xF1C40F,
        )

        if location and api_key:
            weather_text = await _weather_section(location, api_key)
            fc_text      = await _forecast_section(location, api_key)
            header_embed.add_field(name='🌤️ Weather', value=weather_text, inline=False)
            if fc_text:
                header_embed.add_field(name='📅 5-Day Outlook', value=fc_text, inline=False)

        await channel.send(embed=header_embed)

        # ── Per-user digests ─────────────────────────────────────────────────
        for uid in user_ids:
            member = guild.get_member(uid)
            if not member:
                continue

            sections = []

            cal = await _calendar_section(self.bot, uid, tz_name)
            if cal:
                sections.append(cal)

            tasks_text = await _tasks_section(self.bot, uid, cfg['guild_id'])
            sections.append(tasks_text)

            asgn_text = await _assignments_section(self.bot, uid, cfg['guild_id'])
            if asgn_text:
                sections.append(asgn_text)

            email_text = await _email_section(self.bot, uid)
            if email_text:
                sections.append(email_text)

            if not sections:
                continue

            user_embed = discord.Embed(
                title=f'📋 {member.display_name}\'s Day',
                description='\n\n'.join(sections),
                color=0x5865F2,
            )

            file = None
            if is_monday:
                buf = await _stats_graph(self.bot, uid, cfg['guild_id'])
                if buf:
                    file = discord.File(buf, 'weekly_stats.png')
                    user_embed.set_image(url='attachment://weekly_stats.png')
                    user_embed.set_footer(text='📊 Weekly productivity graph')

            try:
                if file:
                    await channel.send(content=member.mention, embed=user_embed, file=file)
                else:
                    await channel.send(content=member.mention, embed=user_embed)
            except Exception as exc:
                log.warning('Failed to send digest for user %s: %s', uid, exc)

    # ── Manual trigger ────────────────────────────────────────────────────────

    @commands.command(name='digest')
    @commands.has_permissions(administrator=True)
    async def digest(self, ctx):
        """Manually trigger the daily digest right now (admin only)."""
        async with self.bot.db.cursor() as cur:
            await cur.execute('SELECT * FROM guild_config WHERE guild_id = ?', (ctx.guild.id,))
            row = await cur.fetchone()

        if not row:
            return await ctx.send('❌ No configuration found. Run `!setup` first.')
        if not row['daily_digest_channel']:
            return await ctx.send('❌ No digest channel set. Run `!setup`.')

        await ctx.send('📤 Sending digest now...')
        import pytz as _pytz
        tz = _pytz.timezone(row['timezone'] or 'UTC')
        now_local = datetime.now(timezone.utc).astimezone(tz)
        await self._send_digest(row, now_local)
        await ctx.send('✅ Digest sent!')


async def setup(bot):
    await bot.add_cog(DailyDigest(bot))
