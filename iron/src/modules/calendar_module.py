"""
modules/calendar_module.py – Google Calendar + iCal/ICS feed integration.

Google Calendar setup (run once, locally)
─────────────────────────────────────────
1. Download credentials.json from Google Cloud Console (Desktop app type).
2. Run:  python iron/src/get_google_token.py
3. Upload the generated token.json to iron/src/token.json on PebbleHost.

To include your SCHOOL calendar (Option A — recommended)
─────────────────────────────────────────────────────────
A. Share your school Google Calendar with your personal Gmail:
   School Google Calendar → ⋮ → Settings & sharing
   → Share with specific people → add your personal Gmail as viewer
   The bot then picks it up automatically (fetches ALL calendars).

To include your SCHOOL calendar (Option B — iCal URL, no sharing needed)
──────────────────────────────────────────────────────────────────────────
A. In school Google Calendar → Settings → click the calendar name
   → Scroll to "Secret address in iCal format" → copy the URL
B. Run:  !calendar ics add school <the_url>
   That's it — events show up in !calendar today/week alongside Google ones.

Commands
────────
  !calendar today             – today's events (all sources)
  !calendar week              – this week's events
  !calendar next              – next 5 upcoming events
  !calendar list              – list all Google calendars you have access to
  !calendar status            – check if linked
  !calendar unlink            – remove token.json

  !calendar ics add <name> <url>   – add an iCal/ICS feed
  !calendar ics remove <name>      – remove a feed
  !calendar ics list               – show saved feeds
"""
import discord
from discord.ext import commands
import asyncio
import aiohttp
import json
import os
import logging
from datetime import datetime, timezone, timedelta, date

log = logging.getLogger(__name__)

SCOPES       = ['https://www.googleapis.com/auth/calendar.readonly']
SRC_DIR      = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
TOKEN_FILE   = os.path.join(SRC_DIR, 'token.json')


# ─── Google Calendar helpers ──────────────────────────────────────────────────

def _load_token() -> dict | None:
    if not os.path.exists(TOKEN_FILE):
        return None
    try:
        with open(TOKEN_FILE) as f:
            return json.load(f)
    except Exception:
        return None


def _build_creds(data: dict):
    from google.oauth2.credentials import Credentials
    return Credentials(
        token=data.get('token'),
        refresh_token=data.get('refresh_token'),
        token_uri='https://oauth2.googleapis.com/token',
        client_id=data.get('client_id'),
        client_secret=data.get('client_secret'),
        scopes=SCOPES,
    )


def _refresh_creds(creds):
    from google.auth.transport.requests import Request
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return creds


async def _get_creds():
    data = _load_token()
    if not data:
        return None
    try:
        creds = _build_creds(data)
        creds = await asyncio.to_thread(_refresh_creds, creds)
        data['token'] = creds.token
        with open(TOKEN_FILE, 'w') as f:
            json.dump(data, f, indent=2)
        return creds
    except Exception as exc:
        log.warning('Calendar token refresh failed: %s', exc)
        return None


async def _list_calendar_ids(creds) -> list[str]:
    """Return IDs of all calendars the authenticated user can see."""
    def _call():
        from googleapiclient.discovery import build
        svc = build('calendar', 'v3', credentials=creds, cache_discovery=False)
        items = svc.calendarList().list().execute().get('items', [])
        return [item['id'] for item in items]
    return await asyncio.to_thread(_call)


async def _fetch_google_events(creds, time_min: datetime, time_max: datetime,
                                max_per_cal: int = 50) -> list[dict]:
    """Fetch events from ALL Google Calendars the user has access to."""
    cal_ids = await _list_calendar_ids(creds)

    def _fetch_one(cal_id: str):
        from googleapiclient.discovery import build
        svc = build('calendar', 'v3', credentials=creds, cache_discovery=False)
        return svc.events().list(
            calendarId=cal_id,
            timeMin=time_min.isoformat(),
            timeMax=time_max.isoformat(),
            maxResults=max_per_cal,
            singleEvents=True,
            orderBy='startTime',
        ).execute().get('items', [])

    all_events: list[dict] = []
    for cal_id in cal_ids:
        try:
            events = await asyncio.to_thread(_fetch_one, cal_id)
            all_events.extend(events)
        except Exception as exc:
            log.debug('Skipping calendar %s: %s', cal_id, exc)

    # De-duplicate by event id and sort chronologically
    seen: set[str] = set()
    unique: list[dict] = []
    for e in all_events:
        eid = e.get('id', '')
        if eid not in seen:
            seen.add(eid)
            unique.append(e)

    unique.sort(key=lambda e: (
        e.get('start', {}).get('dateTime') or e.get('start', {}).get('date', '')
    ))
    return unique


# ─── iCal / ICS helpers ──────────────────────────────────────────────────────

def _parse_ics_dt(dt_val) -> datetime | None:
    """Convert icalendar date/datetime to an aware UTC datetime."""
    try:
        if isinstance(dt_val, datetime):
            if dt_val.tzinfo is None:
                return dt_val.replace(tzinfo=timezone.utc)
            return dt_val.astimezone(timezone.utc)
        if isinstance(dt_val, date):
            return datetime(dt_val.year, dt_val.month, dt_val.day, tzinfo=timezone.utc)
    except Exception:
        pass
    return None


async def _fetch_ics_events(url: str, time_min: datetime, time_max: datetime) -> list[dict]:
    """Download an ICS feed and return events in the given window as dicts."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    return []
                text = await resp.text()

        from icalendar import Calendar as ICal
        cal = ICal.from_ical(text)

        events: list[dict] = []
        for component in cal.walk():
            if component.name != 'VEVENT':
                continue
            dtstart = component.get('DTSTART')
            if not dtstart:
                continue
            start_dt = _parse_ics_dt(dtstart.dt)
            if not start_dt or not (time_min <= start_dt <= time_max):
                continue
            events.append({
                'summary':  str(component.get('SUMMARY', '(no title)')),
                'location': str(component.get('LOCATION', '')),
                'start':    {'dateTime': start_dt.isoformat()},
                '_ics':     True,
            })

        events.sort(key=lambda e: e['start']['dateTime'])
        return events
    except Exception as exc:
        log.debug('ICS fetch failed (%s): %s', url[:60], exc)
        return []


# ─── Public helper (used by daily_digest) ────────────────────────────────────

async def get_todays_events(bot, user_id: int,
                             time_min: datetime, time_max: datetime) -> list[dict]:
    """Return merged Google + ICS events for a user in the given window."""
    events: list[dict] = []

    # Google Calendar
    creds = await _get_creds()
    if creds:
        try:
            events.extend(await _fetch_google_events(creds, time_min, time_max))
        except Exception as exc:
            log.debug('Google Calendar fetch failed: %s', exc)

    # ICS feeds
    async with bot.db.cursor() as cur:
        await cur.execute('SELECT name, url FROM calendar_ics WHERE user_id = ?', (user_id,))
        ics_rows = await cur.fetchall()

    for row in ics_rows:
        ics_events = await _fetch_ics_events(row['url'], time_min, time_max)
        for e in ics_events:
            e['_source'] = row['name']
        events.extend(ics_events)

    events.sort(key=lambda e: (
        e.get('start', {}).get('dateTime') or e.get('start', {}).get('date', '')
    ))
    return events


# ─── Formatting ───────────────────────────────────────────────────────────────

def _fmt_event(event: dict) -> str:
    start    = event.get('start', {})
    dt_str   = start.get('dateTime') or start.get('date', '')
    source   = event.get('_source', '')  # ICS feed name
    try:
        if 'T' in dt_str:
            dt = datetime.fromisoformat(dt_str)
            time_part = dt.strftime('%H:%M')
        else:
            time_part = 'All day'
    except Exception:
        time_part = dt_str
    summary  = event.get('summary', '*(no title)*')
    location = event.get('location', '')
    loc_str  = f' @ {location}' if location else ''
    src_str  = f' `[{source}]`' if source else ''
    return f'`{time_part}` **{summary}**{loc_str}{src_str}'


# ─── Cog ─────────────────────────────────────────────────────────────────────

class Calendar(commands.Cog):
    """Google Calendar + iCal/ICS feed integration."""

    def __init__(self, bot):
        self.bot = bot

    async def _all_events(self, user_id: int,
                          time_min: datetime, time_max: datetime) -> list[dict]:
        return await get_todays_events(self.bot, user_id, time_min, time_max)

    # ── Main group ────────────────────────────────────────────────────────────

    @commands.group(name='calendar', aliases=['cal'], invoke_without_command=True)
    async def calendar(self, ctx):
        """Google Calendar commands. Run `!calendar status` to check your link."""
        linked = os.path.exists(TOKEN_FILE)
        embed  = discord.Embed(title='📅 Calendar', color=0x9B59B6)
        embed.add_field(
            name='Google Calendar',
            value='✅ Linked (token.json found)' if linked else '❌ Not linked',
            inline=False,
        )

        async with self.bot.db.cursor() as cur:
            await cur.execute('SELECT name FROM calendar_ics WHERE user_id = ?', (ctx.author.id,))
            ics_rows = await cur.fetchall()
        ics_names = [r['name'] for r in ics_rows]
        embed.add_field(
            name='iCal Feeds',
            value=', '.join(f'`{n}`' for n in ics_names) if ics_names else '*(none)*',
            inline=False,
        )
        embed.add_field(
            name='Commands',
            value=(
                '`!calendar today` · `!calendar week` · `!calendar next`\n'
                '`!calendar list` · `!calendar status`\n'
                '`!calendar ics add <name> <url>` · `!calendar ics remove <name>` · `!calendar ics list`'
            ),
            inline=False,
        )
        await ctx.send(embed=embed)

    # ── Event views ───────────────────────────────────────────────────────────

    @calendar.command(name='today')
    async def calendar_today(self, ctx):
        """Show today's events from all sources."""
        now   = datetime.now(timezone.utc)
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end   = start + timedelta(days=1)

        async with ctx.typing():
            events = await self._all_events(ctx.author.id, start, end)

        embed = discord.Embed(
            title=f'📅 Today — {now.strftime("%A, %B %d")}',
            color=0x9B59B6,
        )
        embed.description = ('\n'.join(_fmt_event(e) for e in events)
                             if events else '🎉 No events today!')
        await ctx.send(embed=embed)

    @calendar.command(name='week')
    async def calendar_week(self, ctx):
        """Show this week's events from all sources."""
        now   = datetime.now(timezone.utc)
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end   = start + timedelta(days=7)

        async with ctx.typing():
            events = await self._all_events(ctx.author.id, start, end)

        embed = discord.Embed(
            title=f'📅 This Week — {start.strftime("%b %d")} to {end.strftime("%b %d")}',
            color=0x9B59B6,
        )
        embed.description = ('\n'.join(_fmt_event(e) for e in events[:20])
                             if events else '🎉 No events this week!')
        await ctx.send(embed=embed)

    @calendar.command(name='next')
    async def calendar_next(self, ctx):
        """Show the next 5 upcoming events."""
        now = datetime.now(timezone.utc)
        end = now + timedelta(days=30)

        async with ctx.typing():
            events = await self._all_events(ctx.author.id, now, end)

        embed = discord.Embed(title='📅 Upcoming Events', color=0x9B59B6)
        embed.description = ('\n'.join(_fmt_event(e) for e in events[:5])
                             if events else 'No events in the next 30 days.')
        await ctx.send(embed=embed)

    # ── Google Calendar list ──────────────────────────────────────────────────

    @calendar.command(name='list')
    async def calendar_list(self, ctx):
        """List all Google Calendars your account has access to."""
        creds = await _get_creds()
        if not creds:
            return await ctx.send('❌ Google Calendar not linked. Upload `token.json` first.')

        async with ctx.typing():
            cal_ids = await _list_calendar_ids(creds)

        if not cal_ids:
            return await ctx.send('No calendars found.')

        def _get_names():
            from googleapiclient.discovery import build
            svc   = build('calendar', 'v3', credentials=creds, cache_discovery=False)
            items = svc.calendarList().list().execute().get('items', [])
            return [(i.get('summary', i['id']), i.get('primary', False)) for i in items]

        names = await asyncio.to_thread(_get_names)
        lines = [f'{"⭐" if primary else "📅"} {name}' for name, primary in names]
        embed = discord.Embed(
            title='📅 Your Google Calendars',
            description='\n'.join(lines),
            color=0x9B59B6,
        )
        embed.set_footer(text='All of these are included in !calendar today/week/next automatically.')
        await ctx.send(embed=embed)

    # ── Status / unlink ───────────────────────────────────────────────────────

    @calendar.command(name='status')
    async def calendar_status(self, ctx):
        """Check if Google Calendar is linked."""
        creds = await _get_creds()
        if creds:
            desc  = '✅ Google Calendar is linked and the token is valid.'
            color = discord.Color.green()
        elif os.path.exists(TOKEN_FILE):
            desc  = '⚠️ token.json exists but could not be refreshed. Re-run `get_google_token.py`.'
            color = discord.Color.orange()
        else:
            desc = (
                '❌ No `token.json` found.\n\n'
                '**To link Google Calendar:**\n'
                '1. Put `credentials.json` in `iron/src/`\n'
                '2. Run `python iron/src/get_google_token.py` on your **local machine**\n'
                '3. Upload the resulting `token.json` to `iron/src/token.json` on PebbleHost'
            )
            color = discord.Color.red()
        await ctx.send(embed=discord.Embed(description=desc, color=color))

    @calendar.command(name='unlink')
    @commands.has_permissions(administrator=True)
    async def calendar_unlink(self, ctx):
        """Remove the stored Google Calendar token (admin only)."""
        if os.path.exists(TOKEN_FILE):
            os.remove(TOKEN_FILE)
            await ctx.send(embed=discord.Embed(
                description='✅ token.json deleted. Google Calendar unlinked.',
                color=discord.Color.green(),
            ))
        else:
            await ctx.send('No token.json found — Google Calendar was not linked.')

    # ── iCal / ICS feed commands ──────────────────────────────────────────────

    @calendar.group(name='ics', invoke_without_command=True)
    async def ics(self, ctx):
        """Manage iCal/ICS feed URLs (school calendars, Outlook, etc.)."""
        async with self.bot.db.cursor() as cur:
            await cur.execute(
                'SELECT name, url FROM calendar_ics WHERE user_id = ?', (ctx.author.id,)
            )
            rows = await cur.fetchall()

        if not rows:
            embed = discord.Embed(
                title='📅 iCal Feeds',
                description=(
                    'No iCal feeds saved yet.\n\n'
                    '**Add your school calendar:**\n'
                    '1. Open school Google Calendar → Settings → click your calendar name\n'
                    '2. Scroll to **"Secret address in iCal format"** → copy the URL\n'
                    '3. Run: `!calendar ics add school <url>`'
                ),
                color=0x9B59B6,
            )
        else:
            lines = [f'`{r["name"]}` — {r["url"][:60]}…' for r in rows]
            embed = discord.Embed(
                title=f'📅 iCal Feeds ({len(rows)})',
                description='\n'.join(lines),
                color=0x9B59B6,
            )
            embed.set_footer(text='!calendar ics remove <name> to delete a feed')

        await ctx.send(embed=embed)

    @ics.command(name='add')
    async def ics_add(self, ctx, name: str, *, url: str):
        """
        Add an iCal/ICS feed.

        Usage: `!calendar ics add school https://calendar.google.com/calendar/ical/...`

        Get the URL from:
          Google Calendar → Settings → your calendar → Secret address in iCal format
        """
        url = url.strip()
        if not url.startswith('http'):
            return await ctx.send('❌ URL must start with `http://` or `https://`')

        # Test the URL
        async with ctx.typing():
            test = await _fetch_ics_events(url, datetime.now(timezone.utc),
                                           datetime.now(timezone.utc) + timedelta(days=30))

        try:
            async with self.bot.db.cursor() as cur:
                await cur.execute(
                    '''INSERT INTO calendar_ics (user_id, name, url)
                       VALUES (?, ?, ?)
                       ON CONFLICT(user_id, name) DO UPDATE SET url = excluded.url''',
                    (ctx.author.id, name.lower(), url),
                )
            await self.bot.db.commit()
        except Exception as exc:
            return await ctx.send(f'❌ Failed to save feed: `{exc}`')

        embed = discord.Embed(
            title='✅ iCal Feed Added',
            color=discord.Color.green(),
        )
        embed.add_field(name='Name', value=name.lower(), inline=True)
        embed.add_field(name='Events found (next 30 days)', value=str(len(test)), inline=True)
        embed.set_footer(text='Events from this feed will appear in !calendar today/week/next')
        await ctx.send(embed=embed)

    @ics.command(name='remove', aliases=['delete', 'del'])
    async def ics_remove(self, ctx, name: str):
        """Remove an iCal feed by name."""
        async with self.bot.db.cursor() as cur:
            await cur.execute(
                'SELECT id FROM calendar_ics WHERE user_id = ? AND name = ?',
                (ctx.author.id, name.lower()),
            )
            row = await cur.fetchone()
            if not row:
                return await ctx.send(f'❌ No feed named `{name}` found.')
            await cur.execute('DELETE FROM calendar_ics WHERE id = ?', (row['id'],))
        await self.bot.db.commit()
        await ctx.send(embed=discord.Embed(
            description=f'🗑️ Removed iCal feed `{name}`.',
            color=discord.Color.red(),
        ))

    @ics.command(name='list')
    async def ics_list(self, ctx):
        """List all saved iCal feeds."""
        await self.ics(ctx)  # reuse the parent command output


async def setup(bot):
    await bot.add_cog(Calendar(bot))
