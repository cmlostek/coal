"""
modules/calendar_module.py – Google Calendar integration.

Setup (one-time, run locally on your own machine)
─────────────────────────────────────────────────
1. In Google Cloud Console, create a project and enable the Calendar API.
2. Create OAuth 2.0 credentials (Desktop application type) and download
   credentials.json into  iron/src/.
3. Run the helper script on your LOCAL machine (not PebbleHost):
       python iron/src/get_google_token.py
4. A browser window opens — sign in and click Allow.
5. token.json is created in iron/src/.
6. Upload token.json to PebbleHost at  iron/src/token.json.
7. Run  !calendar status  in Discord to confirm.

Commands
────────
  !calendar today   – today's events
  !calendar week    – this week's events
  !calendar next    – next 5 upcoming events
  !calendar status  – show whether calendar is linked
  !calendar unlink  – remove stored tokens
"""
import discord
from discord.ext import commands
import asyncio
import json
import os
import logging
from datetime import datetime, timezone, timedelta

log = logging.getLogger(__name__)

SCOPES         = ['https://www.googleapis.com/auth/calendar.readonly']
SRC_DIR        = os.path.dirname(__file__)                          # …/iron/src/modules
IRON_SRC_DIR   = os.path.abspath(os.path.join(SRC_DIR, '..'))      # …/iron/src
TOKEN_FILE     = os.path.join(IRON_SRC_DIR, 'token.json')
CREDS_FILE     = os.path.join(IRON_SRC_DIR, 'credentials.json')


# ─── Token helpers ────────────────────────────────────────────────────────────

def _load_token_file() -> dict | None:
    """Read token.json from disk, return dict or None."""
    if not os.path.exists(TOKEN_FILE):
        return None
    try:
        with open(TOKEN_FILE) as f:
            return json.load(f)
    except Exception:
        return None


def _build_creds(token_data: dict):
    """Build a google.oauth2.credentials.Credentials from a token dict."""
    from google.oauth2.credentials import Credentials
    return Credentials(
        token=token_data.get('token'),
        refresh_token=token_data.get('refresh_token'),
        token_uri='https://oauth2.googleapis.com/token',
        client_id=token_data.get('client_id'),
        client_secret=token_data.get('client_secret'),
        scopes=SCOPES,
    )


def _refresh_if_needed(creds):
    from google.auth.transport.requests import Request
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return creds


async def _get_creds():
    """Load and refresh credentials. Returns creds or None."""
    data = _load_token_file()
    if not data:
        return None
    try:
        creds = _build_creds(data)
        creds = await asyncio.to_thread(_refresh_if_needed, creds)
        # Persist refreshed token back to file
        data['token'] = creds.token
        with open(TOKEN_FILE, 'w') as f:
            json.dump(data, f, indent=2)
        return creds
    except Exception as exc:
        log.warning('Calendar credential refresh failed: %s', exc)
        return None


# ─── Event fetching ───────────────────────────────────────────────────────────

async def get_todays_events(time_min: datetime, time_max: datetime, max_results: int = 25):
    """Public helper used by daily_digest. Returns list of event dicts or []."""
    creds = await _get_creds()
    if not creds:
        return []
    try:
        return await _fetch_events(creds, time_min, time_max, max_results)
    except Exception:
        return []


async def _fetch_events(creds, time_min: datetime, time_max: datetime, max_results: int = 25):
    def _call():
        from googleapiclient.discovery import build
        service = build('calendar', 'v3', credentials=creds, cache_discovery=False)
        return service.events().list(
            calendarId='primary',
            timeMin=time_min.isoformat(),
            timeMax=time_max.isoformat(),
            maxResults=max_results,
            singleEvents=True,
            orderBy='startTime',
        ).execute().get('items', [])
    return await asyncio.to_thread(_call)


def _fmt_event(event: dict) -> str:
    start   = event.get('start', {})
    dt_str  = start.get('dateTime') or start.get('date', '')
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
    return f'`{time_part}` **{summary}**{loc_str}'


# ─── Cog ─────────────────────────────────────────────────────────────────────

class Calendar(commands.Cog):
    """Google Calendar integration (read-only)."""

    def __init__(self, bot):
        self.bot = bot

    @commands.group(name='calendar', aliases=['cal'], invoke_without_command=True)
    async def calendar(self, ctx):
        """Google Calendar commands."""
        linked = os.path.exists(TOKEN_FILE)
        embed = discord.Embed(
            title='📅 Calendar Commands',
            color=0x9B59B6,
        )
        embed.add_field(
            name='Status',
            value='✅ token.json found' if linked else '❌ Not linked — see setup instructions below',
            inline=False,
        )
        embed.add_field(
            name='Commands',
            value=(
                '`!calendar today` – today\'s events\n'
                '`!calendar week` – this week\n'
                '`!calendar next` – next 5 events\n'
                '`!calendar status` – check link\n'
                '`!calendar unlink` – remove token'
            ),
            inline=False,
        )
        if not linked:
            embed.add_field(
                name='How to link',
                value=(
                    '1. Download `credentials.json` from Google Cloud Console\n'
                    '2. Run `python iron/src/get_google_token.py` **on your local machine**\n'
                    '3. Upload the generated `token.json` to PebbleHost at `iron/src/token.json`'
                ),
                inline=False,
            )
        await ctx.send(embed=embed)

    @calendar.command(name='status')
    async def calendar_status(self, ctx):
        """Check if Google Calendar is linked."""
        creds = await _get_creds()
        if creds:
            embed = discord.Embed(
                description='✅ Google Calendar is linked and the token is valid.',
                color=discord.Color.green(),
            )
        elif os.path.exists(TOKEN_FILE):
            embed = discord.Embed(
                description='⚠️ token.json exists but the token could not be refreshed. Try re-running the setup script.',
                color=discord.Color.orange(),
            )
        else:
            embed = discord.Embed(
                description=(
                    '❌ No token.json found.\n\n'
                    '**To link Google Calendar:**\n'
                    '1. Download `credentials.json` from Google Cloud Console\n'
                    '2. Run `python iron/src/get_google_token.py` on your **local machine**\n'
                    '3. Upload the resulting `token.json` to `iron/src/token.json` on PebbleHost'
                ),
                color=discord.Color.red(),
            )
        await ctx.send(embed=embed)

    @calendar.command(name='today')
    async def calendar_today(self, ctx):
        """Show today's calendar events."""
        creds = await _get_creds()
        if not creds:
            return await ctx.send(
                '❌ Calendar not linked. Upload `token.json` to `iron/src/` — see `!calendar status`.'
            )

        now   = datetime.now(timezone.utc)
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end   = start + timedelta(days=1)

        async with ctx.typing():
            try:
                events = await _fetch_events(creds, start, end)
            except Exception as exc:
                return await ctx.send(f'❌ Failed to fetch events: `{exc}`')

        embed = discord.Embed(
            title=f'📅 Today — {now.strftime("%A, %B %d")}',
            color=0x9B59B6,
        )
        embed.description = ('\n'.join(_fmt_event(e) for e in events)
                             if events else '🎉 No events today!')
        await ctx.send(embed=embed)

    @calendar.command(name='week')
    async def calendar_week(self, ctx):
        """Show this week's calendar events."""
        creds = await _get_creds()
        if not creds:
            return await ctx.send('❌ Calendar not linked. See `!calendar status`.')

        now   = datetime.now(timezone.utc)
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end   = start + timedelta(days=7)

        async with ctx.typing():
            try:
                events = await _fetch_events(creds, start, end, max_results=50)
            except Exception as exc:
                return await ctx.send(f'❌ Failed to fetch events: `{exc}`')

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
        creds = await _get_creds()
        if not creds:
            return await ctx.send('❌ Calendar not linked. See `!calendar status`.')

        now = datetime.now(timezone.utc)
        end = now + timedelta(days=30)

        async with ctx.typing():
            try:
                events = await _fetch_events(creds, now, end, max_results=5)
            except Exception as exc:
                return await ctx.send(f'❌ Failed to fetch events: `{exc}`')

        embed = discord.Embed(title='📅 Upcoming Events', color=0x9B59B6)
        embed.description = ('\n'.join(_fmt_event(e) for e in events)
                             if events else 'No upcoming events in the next 30 days.')
        await ctx.send(embed=embed)

    @calendar.command(name='unlink')
    @commands.has_permissions(administrator=True)
    async def calendar_unlink(self, ctx):
        """Remove the stored Google Calendar token (admin only)."""
        if os.path.exists(TOKEN_FILE):
            os.remove(TOKEN_FILE)
            await ctx.send(embed=discord.Embed(
                description='✅ token.json deleted. Calendar is now unlinked.',
                color=discord.Color.green(),
            ))
        else:
            await ctx.send('No token.json found — calendar was not linked.')


async def setup(bot):
    await bot.add_cog(Calendar(bot))
