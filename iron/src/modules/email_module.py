"""
modules/email_module.py – Email (IMAP) integration.

Counts emails received while you slept and reports them in the daily digest.

Setup
─────
  !email setup <email> <app_password> [imap_server]
    e.g. !email setup you@gmail.com abcd1234efgh5678 imap.gmail.com

For Gmail you need an App Password (2FA must be enabled):
  Google Account → Security → App Passwords → Generate

Commands
────────
  !email setup <address> <app_password> [imap]  – link inbox
  !email check                                   – count overnight emails now
  !email sleep <HH:MM> <HH:MM>                  – set sleep window
  !email status                                  – show config
  !email unlink                                  – remove config
"""
import discord
from discord.ext import commands
import asyncio
import imaplib
import logging
import email as email_lib
from datetime import datetime, timezone, timedelta

log = logging.getLogger(__name__)


async def _count_overnight_emails(email_addr: str, app_password: str,
                                   imap_server: str, sleep_start: str, sleep_end: str) -> dict:
    """
    Connect via IMAP and count messages received during the sleep window.
    Returns a dict with count and metadata.
    """
    def _fetch():
        now = datetime.now()

        # Parse sleep window
        s_h, s_m = map(int, sleep_start.split(':'))
        e_h, e_m = map(int, sleep_end.split(':'))

        sleep_start_dt = now.replace(hour=s_h, minute=s_m, second=0, microsecond=0)
        sleep_end_dt   = now.replace(hour=e_h, minute=e_m, second=0, microsecond=0)

        # If sleep window spans midnight (e.g. 22:00 → 07:00), adjust
        if sleep_start_dt > sleep_end_dt:
            sleep_start_dt -= timedelta(days=1)

        since_str = sleep_start_dt.strftime('%d-%b-%Y')
        before_str = sleep_end_dt.strftime('%d-%b-%Y')

        mail = imaplib.IMAP4_SSL(imap_server)
        mail.login(email_addr, app_password)
        mail.select('INBOX')

        # IMAP date search (SINCE = inclusive start date)
        _, data = mail.search(None, f'(SINCE "{since_str}")')
        all_ids = data[0].split() if data[0] else []

        # Filter by exact datetime
        overnight_count = 0
        for msg_id in all_ids:
            _, msg_data = mail.fetch(msg_id, '(RFC822.HEADER)')
            raw = msg_data[0][1]
            msg = email_lib.message_from_bytes(raw)
            date_str = msg.get('Date', '')
            try:
                from email.utils import parsedate_to_datetime
                msg_dt = parsedate_to_datetime(date_str)
                if msg_dt.tzinfo:
                    msg_dt = msg_dt.astimezone(timezone.utc).replace(tzinfo=None)
                if sleep_start_dt <= msg_dt <= sleep_end_dt:
                    overnight_count += 1
            except Exception:
                continue

        mail.logout()
        return {
            'count': overnight_count,
            'window': f'{sleep_start} → {sleep_end}',
            'total_inbox': len(all_ids),
        }

    return await asyncio.to_thread(_fetch)


class Email(commands.Cog):
    """IMAP email integration for overnight email counts."""

    def __init__(self, bot):
        self.bot = bot

    async def _get_config(self, user_id: int):
        async with self.bot.db.cursor() as cur:
            await cur.execute('SELECT * FROM email_config WHERE user_id = ?', (user_id,))
            return await cur.fetchone()

    @commands.group(name='email', invoke_without_command=True)
    async def email_group(self, ctx):
        """Email inbox commands."""
        embed = discord.Embed(
            title='📧 Email Commands',
            description=(
                '`!email setup <address> <app_password>` – link inbox\n'
                '`!email check` – count overnight emails now\n'
                '`!email sleep <start> <end>` – set sleep window (e.g. `22:00 07:00`)\n'
                '`!email imap <server>` – change IMAP server (default: imap.gmail.com)\n'
                '`!email status` – show configuration\n'
                '`!email unlink` – remove configuration'
            ),
            color=0x4A90D9,
        )
        await ctx.send(embed=embed)

    @email_group.command(name='setup')
    async def email_setup(self, ctx, email_addr: str, *, app_password: str):
        """
        Link your email inbox via IMAP.

        Usage: `!email setup you@gmail.com yourAppPassword`

        For Gmail: generate a 16-character App Password in your Google Account
        (myaccount.google.com/apppasswords). Spaces in the password are fine —
        just paste it as-is after your email address.

        To use a non-Gmail server run `!email imap <server>` afterwards.
        The setup message is deleted immediately to protect your credentials.
        """
        # Strip spaces from app password (Google includes them for readability)
        app_password = app_password.replace(' ', '')

        try:
            await ctx.message.delete()
        except Exception:
            pass

        # Look up any previously stored IMAP server, default to Gmail
        cfg = await self._get_config(ctx.author.id)
        imap_server = cfg['imap_server'] if cfg and cfg['imap_server'] else 'imap.gmail.com'

        # Test the connection
        try:
            def _test():
                mail = imaplib.IMAP4_SSL(imap_server)
                mail.login(email_addr, app_password)
                mail.logout()
            await asyncio.to_thread(_test)
        except Exception as exc:
            try:
                await ctx.author.send(f'❌ Could not connect to `{imap_server}`: `{exc}`')
            except Exception:
                pass
            return

        async with self.bot.db.cursor() as cur:
            await cur.execute(
                '''INSERT INTO email_config (user_id, email_addr, app_password, imap_server)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(user_id) DO UPDATE SET
                       email_addr   = excluded.email_addr,
                       app_password = excluded.app_password,
                       imap_server  = excluded.imap_server''',
                (ctx.author.id, email_addr, app_password, imap_server),
            )
        await self.bot.db.commit()

        embed = discord.Embed(
            title='✅ Email Linked',
            description=f'Connected to `{email_addr}` via `{imap_server}`.\nYour credentials are stored and your message was deleted.',
            color=discord.Color.green(),
        )
        try:
            await ctx.author.send(embed=embed)
        except Exception:
            pass
        await ctx.send('✅ Email linked! Check your DMs for confirmation.')

    @email_group.command(name='check')
    async def email_check(self, ctx):
        """Count emails received during your sleep window."""
        cfg = await self._get_config(ctx.author.id)
        if not cfg or not cfg['email_addr']:
            return await ctx.send('❌ Email not linked. Run `!email setup`.')

        async with ctx.typing():
            try:
                result = await _count_overnight_emails(
                    cfg['email_addr'], cfg['app_password'], cfg['imap_server'],
                    cfg['sleep_start'], cfg['sleep_end'],
                )
            except Exception as exc:
                return await ctx.send(f'❌ Failed to check email: `{exc}`')

        embed = discord.Embed(
            title='📧 Overnight Email Report',
            color=0x4A90D9,
        )
        embed.add_field(
            name='Received While You Slept',
            value=f'**{result["count"]}** new email(s)',
            inline=True,
        )
        embed.add_field(name='Sleep Window', value=result['window'], inline=True)
        await ctx.send(embed=embed)

    @email_group.command(name='sleep')
    async def email_sleep(self, ctx, sleep_start: str, sleep_end: str):
        """
        Set your sleep window.

        Example: `!email sleep 22:00 07:00`
        The bot will count emails between these times.
        """
        for t in (sleep_start, sleep_end):
            try:
                h, m = t.split(':')
                assert 0 <= int(h) <= 23 and 0 <= int(m) <= 59
            except Exception:
                return await ctx.send(f'❌ Invalid time `{t}`. Use HH:MM format.')

        async with self.bot.db.cursor() as cur:
            await cur.execute(
                '''INSERT INTO email_config (user_id, sleep_start, sleep_end)
                   VALUES (?, ?, ?)
                   ON CONFLICT(user_id) DO UPDATE SET
                       sleep_start = excluded.sleep_start,
                       sleep_end   = excluded.sleep_end''',
                (ctx.author.id, sleep_start, sleep_end),
            )
        await self.bot.db.commit()
        await ctx.send(f'✅ Sleep window set to **{sleep_start} → {sleep_end}**')

    @email_group.command(name='status')
    async def email_status(self, ctx):
        """Show your email configuration."""
        cfg = await self._get_config(ctx.author.id)
        if not cfg or not cfg['email_addr']:
            return await ctx.send(embed=discord.Embed(
                description='❌ Email not linked. Run `!email setup`.',
                color=discord.Color.red(),
            ))
        embed = discord.Embed(title='📧 Email Configuration', color=0x4A90D9)
        embed.add_field(name='Address', value=cfg['email_addr'], inline=True)
        embed.add_field(name='IMAP Server', value=cfg['imap_server'], inline=True)
        embed.add_field(name='Sleep Window',
                        value=f'{cfg["sleep_start"]} → {cfg["sleep_end"]}', inline=True)
        await ctx.send(embed=embed)

    @email_group.command(name='imap')
    async def email_imap(self, ctx, server: str):
        """
        Set a custom IMAP server (default is imap.gmail.com).

        Examples:
          `!email imap imap.gmail.com`       – Gmail
          `!email imap outlook.office365.com` – Outlook / Microsoft 365
          `!email imap imap.mail.yahoo.com`  – Yahoo Mail
        """
        async with self.bot.db.cursor() as cur:
            await cur.execute(
                '''INSERT INTO email_config (user_id, imap_server)
                   VALUES (?, ?)
                   ON CONFLICT(user_id) DO UPDATE SET imap_server = excluded.imap_server''',
                (ctx.author.id, server.strip()),
            )
        await self.bot.db.commit()
        await ctx.send(f'✅ IMAP server set to `{server.strip()}`. Re-run `!email setup` to reconnect.')

    @email_group.command(name='unlink')
    async def email_unlink(self, ctx):
        """Remove your email configuration."""
        async with self.bot.db.cursor() as cur:
            await cur.execute('DELETE FROM email_config WHERE user_id = ?', (ctx.author.id,))
        await self.bot.db.commit()
        await ctx.send(embed=discord.Embed(description='✅ Email unlinked.', color=discord.Color.green()))


async def setup(bot):
    await bot.add_cog(Email(bot))
