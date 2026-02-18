"""
modules/reminders.py – RDanny-style reminder system.

Usage
─────
  !remind in 30 minutes to submit the lab report
  !remind tomorrow at 9am to check email
  !remind 2025-05-01 to start the project
  !reminders           – list your pending reminders
  !reminders delete 3  – delete reminder #3
"""
import discord
from discord.ext import commands, tasks
from datetime import datetime, timezone
import dateparser
import asyncio
import logging

log = logging.getLogger(__name__)


def parse_time(text: str):
    """Return a timezone-aware datetime or None."""
    settings = {
        'RETURN_AS_TIMEZONE_AWARE': True,
        'PREFER_DATES_FROM': 'future',
        'TO_TIMEZONE': 'UTC',
    }
    dt = dateparser.parse(text, settings=settings)
    return dt


class Reminders(commands.Cog):
    """Set and manage timed reminders."""

    def __init__(self, bot):
        self.bot = bot
        self.check_reminders.start()

    def cog_unload(self):
        self.check_reminders.cancel()

    # ── Background task ───────────────────────────────────────────────────────

    @tasks.loop(seconds=30)
    async def check_reminders(self):
        now = datetime.now(timezone.utc).isoformat()
        async with self.bot.db.cursor() as cur:
            await cur.execute(
                'SELECT * FROM reminders WHERE sent = 0 AND remind_at <= ?',
                (now,),
            )
            due = await cur.fetchall()

        for row in due:
            try:
                channel = self.bot.get_channel(row['channel_id'])
                user = self.bot.get_user(row['user_id'])
                if channel and user:
                    embed = discord.Embed(
                        title='⏰ Reminder',
                        description=row['message'],
                        color=0xFEE75C,
                        timestamp=datetime.now(timezone.utc),
                    )
                    embed.set_footer(text=f'Reminder #{row["id"]} • Set by {user.display_name}')
                    await channel.send(content=user.mention, embed=embed)
            except Exception as exc:
                log.warning('Failed to send reminder %s: %s', row['id'], exc)
            finally:
                async with self.bot.db.cursor() as cur:
                    await cur.execute('UPDATE reminders SET sent = 1 WHERE id = ?', (row['id'],))
                await self.bot.db.commit()

    @check_reminders.before_loop
    async def before_check(self):
        await self.bot.wait_until_ready()

    # ── Commands ─────────────────────────────────────────────────────────────

    @commands.command(name='remind')
    async def remind(self, ctx, *, args: str):
        """
        Set a reminder.

        Examples:
          `!remind in 30 minutes to submit lab`
          `!remind tomorrow at 9am to check email`
          `!remind 2025-05-01 12:00 to start project`

        The word **to** separates the time from the message.
        If no **to** is found the whole text is treated as the time.
        """
        # Split on first ' to ' (case-insensitive)
        lower = args.lower()
        if ' to ' in lower:
            split_pos = lower.index(' to ')
            time_str = args[:split_pos].strip()
            message  = args[split_pos + 4:].strip()
        else:
            time_str = args.strip()
            message  = '*(no message set)*'

        if not message:
            message = '*(no message set)*'

        dt = parse_time(time_str)
        if not dt or dt <= datetime.now(timezone.utc):
            return await ctx.send(
                embed=discord.Embed(
                    description=f'❌ Could not parse `{time_str}` as a future time.\n'
                                'Try: `in 30 minutes`, `tomorrow at 9am`, `2025-05-01 12:00`',
                    color=discord.Color.red(),
                )
            )

        # Determine reminder channel
        channel_id = ctx.channel.id
        async with self.bot.db.cursor() as cur:
            await cur.execute('SELECT reminder_channel FROM guild_config WHERE guild_id = ?', (ctx.guild.id,))
            cfg = await cur.fetchone()
            if cfg and cfg['reminder_channel']:
                channel_id = cfg['reminder_channel']

            await cur.execute(
                '''INSERT INTO reminders (user_id, guild_id, channel_id, message, remind_at)
                   VALUES (?, ?, ?, ?, ?)''',
                (ctx.author.id, ctx.guild.id, channel_id, message, dt.isoformat()),
            )
            rid = cur.lastrowid
        await self.bot.db.commit()

        discord_ts = int(dt.timestamp())
        embed = discord.Embed(
            title='⏰ Reminder Set',
            description=f'**#{rid}** — {message}',
            color=0xFEE75C,
        )
        embed.add_field(name='When', value=f'<t:{discord_ts}:F> (<t:{discord_ts}:R>)', inline=False)
        await ctx.send(embed=embed)

    @commands.group(name='reminders', invoke_without_command=True)
    async def reminders_group(self, ctx):
        """List your pending reminders."""
        async with self.bot.db.cursor() as cur:
            await cur.execute(
                '''SELECT * FROM reminders
                   WHERE user_id = ? AND guild_id = ? AND sent = 0
                   ORDER BY remind_at ASC''',
                (ctx.author.id, ctx.guild.id),
            )
            rows = await cur.fetchall()

        if not rows:
            return await ctx.send(
                embed=discord.Embed(description='You have no pending reminders.', color=0xFEE75C)
            )

        lines = []
        for r in rows:
            try:
                dt = datetime.fromisoformat(r['remind_at'])
                ts = int(dt.timestamp())
                lines.append(f'`#{r["id"]}` <t:{ts}:F> (<t:{ts}:R>) — {r["message"][:60]}')
            except Exception:
                lines.append(f'`#{r["id"]}` {r["remind_at"]} — {r["message"][:60]}')

        embed = discord.Embed(
            title=f'⏰ Your Reminders ({len(rows)})',
            description='\n'.join(lines),
            color=0xFEE75C,
        )
        embed.set_footer(text='!reminders delete <id> to cancel one')
        await ctx.send(embed=embed)

    @reminders_group.command(name='delete', aliases=['del', 'cancel', 'remove'])
    async def reminders_delete(self, ctx, reminder_id: int):
        """Cancel a reminder by ID."""
        async with self.bot.db.cursor() as cur:
            await cur.execute(
                'SELECT * FROM reminders WHERE id = ? AND user_id = ? AND guild_id = ?',
                (reminder_id, ctx.author.id, ctx.guild.id),
            )
            row = await cur.fetchone()
            if not row:
                return await ctx.send(f'❌ Reminder #{reminder_id} not found or not yours.')
            if row['sent']:
                return await ctx.send(f'Reminder #{reminder_id} has already been sent.')
            await cur.execute('DELETE FROM reminders WHERE id = ?', (reminder_id,))
        await self.bot.db.commit()
        await ctx.send(
            embed=discord.Embed(
                description=f'🗑️ Reminder **#{reminder_id}** cancelled.',
                color=discord.Color.red(),
            )
        )

    @reminders_group.command(name='clear')
    async def reminders_clear(self, ctx):
        """Delete all your pending reminders."""
        async with self.bot.db.cursor() as cur:
            await cur.execute(
                'DELETE FROM reminders WHERE user_id = ? AND guild_id = ? AND sent = 0',
                (ctx.author.id, ctx.guild.id),
            )
        await self.bot.db.commit()
        await ctx.send(
            embed=discord.Embed(description='🗑️ All pending reminders cleared.', color=discord.Color.red())
        )


async def setup(bot):
    await bot.add_cog(Reminders(bot))
