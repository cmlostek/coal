"""
modules/calendar_module.py – Google Calendar integration.

Setup (one-time per user)
─────────────────────────
1. Create a Google Cloud project at https://console.cloud.google.com
2. Enable the Google Calendar API
3. Create OAuth 2.0 credentials (Desktop application type)
4. Download credentials.json and place it in the bot's src/ directory
5. Run `!calendar setup` in Discord and follow the instructions

Commands
────────
  !calendar setup        – start OAuth flow (DMs you a link)
  !calendar code <code>  – finish OAuth with the authorisation code
  !calendar today        – show today's calendar events
  !calendar week         – show this week's events
  !calendar next         – next 5 upcoming events
  !calendar status       – show whether your calendar is linked
"""
import discord
from discord.ext import commands
import asyncio
import json
import os
import logging
from datetime import datetime, timezone, timedelta

log = logging.getLogger(__name__)

SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']
CREDENTIALS_FILE = os.path.join(os.path.dirname(__file__), '..', 'credentials.json')


def _build_flow():
    """Build an OAuth flow from credentials.json, returns None if file missing."""
    try:
        from google_auth_oauthlib.flow import Flow
        flow = Flow.from_client_secrets_file(
            CREDENTIALS_FILE,
            scopes=SCOPES,
            redirect_uri='urn:ietf:wg:oauth:2.0:oob',
        )
        return flow
    except Exception as exc:
        log.warning('Could not build Google OAuth flow: %s', exc)
        return None


def _creds_from_token(token_json: str):
    """Reconstruct google.oauth2.credentials.Credentials from stored JSON."""
    from google.oauth2.credentials import Credentials
    data = json.loads(token_json)
    creds = Credentials(
        token=data.get('token'),
        refresh_token=data.get('refresh_token'),
        token_uri='https://oauth2.googleapis.com/token',
        client_id=data.get('client_id'),
        client_secret=data.get('client_secret'),
        scopes=SCOPES,
    )
    return creds


def _refresh_if_needed(creds):
    from google.auth.transport.requests import Request
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return creds


async def _get_events(creds, time_min: datetime, time_max: datetime, max_results=25):
    """Fetch calendar events in a thread (google API is sync)."""
    def _fetch():
        from googleapiclient.discovery import build
        service = build('calendar', 'v3', credentials=creds, cache_discovery=False)
        result = service.events().list(
            calendarId='primary',
            timeMin=time_min.isoformat(),
            timeMax=time_max.isoformat(),
            maxResults=max_results,
            singleEvents=True,
            orderBy='startTime',
        ).execute()
        return result.get('items', [])
    return await asyncio.to_thread(_fetch)


def _fmt_event(event) -> str:
    start = event.get('start', {})
    dt_str = start.get('dateTime') or start.get('date', '')
    try:
        if 'T' in dt_str:
            dt = datetime.fromisoformat(dt_str)
            time_part = dt.strftime('%H:%M')
        else:
            time_part = 'All day'
    except Exception:
        time_part = dt_str
    summary = event.get('summary', '*(no title)*')
    location = event.get('location', '')
    loc_str = f' @ {location}' if location else ''
    return f'`{time_part}` **{summary}**{loc_str}'


# ─── Cog ─────────────────────────────────────────────────────────────────────

class Calendar(commands.Cog):
    """Google Calendar integration."""

    def __init__(self, bot):
        self.bot = bot

    async def _get_creds(self, user_id: int):
        """Load and refresh credentials for a user. Returns None if not set up."""
        async with self.bot.db.cursor() as cur:
            await cur.execute('SELECT credentials FROM calendar_config WHERE user_id = ?', (user_id,))
            row = await cur.fetchone()
        if not row or not row['credentials']:
            return None
        try:
            creds = _creds_from_token(row['credentials'])
            creds = await asyncio.to_thread(_refresh_if_needed, creds)
            # Persist refreshed token
            token_data = {
                'token': creds.token,
                'refresh_token': creds.refresh_token,
                'client_id': creds.client_id,
                'client_secret': creds.client_secret,
            }
            async with self.bot.db.cursor() as cur:
                await cur.execute(
                    'UPDATE calendar_config SET credentials = ? WHERE user_id = ?',
                    (json.dumps(token_data), user_id),
                )
            await self.bot.db.commit()
            return creds
        except Exception as exc:
            log.warning('Failed to load/refresh creds for %s: %s', user_id, exc)
            return None

    @commands.group(name='calendar', aliases=['cal'], invoke_without_command=True)
    async def calendar(self, ctx):
        """Google Calendar commands."""
        embed = discord.Embed(
            title='📅 Calendar Commands',
            description=(
                '`!calendar setup` – link your Google Calendar\n'
                '`!calendar code <code>` – finish linking\n'
                '`!calendar today` – today\'s events\n'
                '`!calendar week` – this week\'s events\n'
                '`!calendar next` – next 5 events\n'
                '`!calendar status` – check if linked'
            ),
            color=0x9B59B6,
        )
        await ctx.send(embed=embed)

    @calendar.command(name='setup')
    async def calendar_setup(self, ctx):
        """Begin Google Calendar OAuth setup."""
        if not os.path.exists(CREDENTIALS_FILE):
            return await ctx.send(
                embed=discord.Embed(
                    title='❌ credentials.json not found',
                    description=(
                        'To use Google Calendar:\n'
                        '1. Go to https://console.cloud.google.com\n'
                        '2. Create a project and enable the **Google Calendar API**\n'
                        '3. Create **OAuth 2.0 credentials** (Desktop app type)\n'
                        '4. Download the JSON and place it at `src/credentials.json`\n'
                        '5. Run `!calendar setup` again'
                    ),
                    color=discord.Color.red(),
                )
            )

        flow = _build_flow()
        if not flow:
            return await ctx.send('❌ Failed to build auth flow. Check that credentials.json is valid.')

        auth_url, _ = flow.authorization_url(prompt='consent')

        embed = discord.Embed(
            title='🔗 Link Google Calendar',
            description=(
                '1. Click the link below and sign in with your Google account\n'
                '2. Authorise the app\n'
                '3. Copy the authorisation code shown on screen\n'
                '4. Run `!calendar code <your_code>` in this channel'
            ),
            color=0x9B59B6,
        )
        embed.add_field(name='Auth URL', value=f'[Click here to authorise]({auth_url})', inline=False)

        try:
            await ctx.author.send(embed=embed)
            await ctx.send('📬 Check your DMs for the authorisation link!')
        except discord.Forbidden:
            await ctx.send(embed=embed)

    @calendar.command(name='code')
    async def calendar_code(self, ctx, *, code: str):
        """Provide the OAuth authorisation code returned by Google."""
        if not os.path.exists(CREDENTIALS_FILE):
            return await ctx.send('❌ credentials.json not found. Run `!calendar setup` first.')

        flow = _build_flow()
        if not flow:
            return await ctx.send('❌ Failed to build auth flow.')

        try:
            def _exchange():
                flow.fetch_token(code=code.strip())
                return flow.credentials
            creds = await asyncio.to_thread(_exchange)
        except Exception as exc:
            return await ctx.send(f'❌ Failed to exchange code: {exc}')

        token_data = {
            'token': creds.token,
            'refresh_token': creds.refresh_token,
            'client_id': creds.client_id,
            'client_secret': creds.client_secret,
        }

        async with self.bot.db.cursor() as cur:
            await cur.execute(
                '''INSERT INTO calendar_config (user_id, credentials)
                   VALUES (?, ?)
                   ON CONFLICT(user_id) DO UPDATE SET credentials = excluded.credentials''',
                (ctx.author.id, json.dumps(token_data)),
            )
        await self.bot.db.commit()

        embed = discord.Embed(
            title='✅ Google Calendar Linked!',
            description='Your Google Calendar is now connected. Try `!calendar today`.',
            color=discord.Color.green(),
        )
        try:
            await ctx.author.send(embed=embed)
        except discord.Forbidden:
            await ctx.send(embed=embed)

    @calendar.command(name='today')
    async def calendar_today(self, ctx):
        """Show today's calendar events."""
        creds = await self._get_creds(ctx.author.id)
        if not creds:
            return await ctx.send('❌ Calendar not linked. Run `!calendar setup`.')

        now = datetime.now(timezone.utc)
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end   = start + timedelta(days=1)

        async with ctx.typing():
            try:
                events = await _get_events(creds, start, end)
            except Exception as exc:
                return await ctx.send(f'❌ Failed to fetch events: {exc}')

        embed = discord.Embed(
            title=f'📅 Today — {now.strftime("%A, %B %d")}',
            color=0x9B59B6,
        )
        if events:
            embed.description = '\n'.join(_fmt_event(e) for e in events)
        else:
            embed.description = '🎉 No events today!'
        await ctx.send(embed=embed)

    @calendar.command(name='week')
    async def calendar_week(self, ctx):
        """Show this week's calendar events."""
        creds = await self._get_creds(ctx.author.id)
        if not creds:
            return await ctx.send('❌ Calendar not linked. Run `!calendar setup`.')

        now   = datetime.now(timezone.utc)
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end   = start + timedelta(days=7)

        async with ctx.typing():
            try:
                events = await _get_events(creds, start, end, max_results=50)
            except Exception as exc:
                return await ctx.send(f'❌ Failed to fetch events: {exc}')

        embed = discord.Embed(
            title=f'📅 This Week — {start.strftime("%b %d")} to {end.strftime("%b %d")}',
            color=0x9B59B6,
        )
        if events:
            embed.description = '\n'.join(_fmt_event(e) for e in events[:20])
        else:
            embed.description = '🎉 No events this week!'
        await ctx.send(embed=embed)

    @calendar.command(name='next')
    async def calendar_next(self, ctx):
        """Show the next 5 upcoming events."""
        creds = await self._get_creds(ctx.author.id)
        if not creds:
            return await ctx.send('❌ Calendar not linked. Run `!calendar setup`.')

        now = datetime.now(timezone.utc)
        end = now + timedelta(days=30)

        async with ctx.typing():
            try:
                events = await _get_events(creds, now, end, max_results=5)
            except Exception as exc:
                return await ctx.send(f'❌ Failed to fetch events: {exc}')

        embed = discord.Embed(title='📅 Upcoming Events', color=0x9B59B6)
        if events:
            embed.description = '\n'.join(_fmt_event(e) for e in events)
        else:
            embed.description = 'No upcoming events in the next 30 days.'
        await ctx.send(embed=embed)

    @calendar.command(name='status')
    async def calendar_status(self, ctx):
        """Check if your Google Calendar is linked."""
        async with self.bot.db.cursor() as cur:
            await cur.execute('SELECT credentials FROM calendar_config WHERE user_id = ?', (ctx.author.id,))
            row = await cur.fetchone()
        linked = row and row['credentials']
        embed = discord.Embed(
            description=('✅ Your Google Calendar is linked.' if linked
                         else '❌ No calendar linked. Run `!calendar setup`.'),
            color=discord.Color.green() if linked else discord.Color.red(),
        )
        await ctx.send(embed=embed)

    @calendar.command(name='unlink')
    async def calendar_unlink(self, ctx):
        """Remove your Google Calendar link."""
        async with self.bot.db.cursor() as cur:
            await cur.execute('DELETE FROM calendar_config WHERE user_id = ?', (ctx.author.id,))
        await self.bot.db.commit()
        await ctx.send(embed=discord.Embed(description='✅ Calendar unlinked.', color=discord.Color.green()))


async def setup(bot):
    await bot.add_cog(Calendar(bot))
