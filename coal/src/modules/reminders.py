"""Reminders module"""

import asyncio
import datetime
import re
import secrets

import discord


def setup(bot):
    """Setup function to register commands with the bot"""

    c = bot.db.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS reminders (
        id         TEXT PRIMARY KEY,
        user_id    INTEGER NOT NULL,
        channel_id INTEGER NOT NULL,
        remind_at  TEXT NOT NULL,
        message    TEXT NOT NULL
    )''')
    bot.db.commit()

    def parse_duration(s):
        """Parse '1h30m2s' style strings into total seconds. Returns None if invalid."""
        pattern = re.compile(
            r'(\d+)\s*(w(?:eek)?s?|d(?:ay)?s?|h(?:(?:ou)?r)?s?|m(?:in(?:ute)?s?)?|s(?:ec(?:ond)?s?)?)',
            re.IGNORECASE
        )
        matches = pattern.findall(s)
        if not matches:
            return None
        total = 0
        for amount, unit in matches:
            u = unit[0].lower()
            n = int(amount)
            if u == 's':
                total += n
            elif u == 'm':
                total += n * 60
            elif u == 'h':
                total += n * 3600
            elif u == 'd':
                total += n * 86400
            elif u == 'w':
                total += n * 604800
        return total if total > 0 else None

    @bot.command(name='remind', aliases=['remindme', 'reminder'])
    async def remind(ctx, duration: str, *, message: str = 'No message provided.'):
        """Set a reminder. Usage: -remind 1h30m Feed the cat"""
        seconds = parse_duration(duration)
        if not seconds:
            await ctx.send(
                'Invalid time format! Use: `30s`, `5m`, `2h`, `1d`, `1w` or combinations like `1h30m`.'
            )
            return
        if seconds < 5:
            await ctx.send('Reminder must be at least 5 seconds away.')
            return
        if seconds > 31_536_000:
            await ctx.send('Reminder cannot be more than 1 year in the future.')
            return

        remind_at = datetime.datetime.utcnow() + datetime.timedelta(seconds=seconds)
        unix_ts = int(remind_at.timestamp())
        rid = secrets.token_hex(4).upper()

        c = bot.db.cursor()
        c.execute(
            'INSERT INTO reminders (id, user_id, channel_id, remind_at, message) VALUES (?, ?, ?, ?, ?)',
            (rid, ctx.author.id, ctx.channel.id, remind_at.isoformat(), message)
        )
        bot.db.commit()

        embed = discord.Embed(title='Reminder Set', color=discord.Color.green())
        embed.add_field(name='Message', value=message[:1024], inline=False)
        embed.add_field(name='When', value=f'<t:{unix_ts}:F> (<t:{unix_ts}:R>)', inline=False)
        embed.add_field(name='ID', value=f'`{rid}`', inline=True)
        embed.set_footer(text='-reminders to list  •  -cancelreminder <id> to cancel')
        await ctx.send(embed=embed)

    @bot.command(name='reminders', aliases=['myreminders', 'listreminders'])
    async def list_reminders(ctx):
        """List all your active reminders."""
        c = bot.db.cursor()
        c.execute(
            'SELECT id, remind_at, message FROM reminders WHERE user_id = ? ORDER BY remind_at ASC',
            (ctx.author.id,)
        )
        rows = c.fetchall()

        if not rows:
            await ctx.send('You have no active reminders.')
            return

        embed = discord.Embed(
            title=f'Your Reminders ({len(rows)})',
            color=discord.Color.blue()
        )
        for rid, remind_at_str, message in rows:
            remind_at = datetime.datetime.fromisoformat(remind_at_str)
            unix_ts = int(remind_at.timestamp())
            preview = message[:80] + '…' if len(message) > 80 else message
            embed.add_field(
                name=f'ID: `{rid}`',
                value=f'{preview}\n<t:{unix_ts}:F> (<t:{unix_ts}:R>)',
                inline=False
            )
        embed.set_footer(text='-cancelreminder <id> to cancel a reminder')
        await ctx.send(embed=embed)

    @bot.command(name='cancelreminder', aliases=['rmreminder', 'delreminder', 'unremind'])
    async def cancel_reminder(ctx, rid: str):
        """Cancel a reminder by its ID. Usage: -cancelreminder A3F891C2"""
        rid = rid.upper()
        c = bot.db.cursor()
        c.execute('SELECT message FROM reminders WHERE id = ? AND user_id = ?', (rid, ctx.author.id))
        row = c.fetchone()
        if not row:
            await ctx.send(f'No reminder with ID `{rid}` found for you.')
            return
        c.execute('DELETE FROM reminders WHERE id = ?', (rid,))
        bot.db.commit()
        preview = row[0][:80] + '…' if len(row[0]) > 80 else row[0]
        await ctx.send(f'Cancelled reminder `{rid}`: {preview}')

    async def _reminder_loop():
        """Background task: fire due reminders every 15 seconds."""
        await bot.wait_until_ready()
        while not bot.is_closed():
            try:
                now = datetime.datetime.utcnow().isoformat()
                c = bot.db.cursor()
                c.execute(
                    'SELECT id, user_id, channel_id, message FROM reminders WHERE remind_at <= ?',
                    (now,)
                )
                due = c.fetchall()
                fired = []
                for rid, user_id, channel_id, message in due:
                    try:
                        channel = bot.get_channel(channel_id) or await bot.fetch_channel(channel_id)
                        user = bot.get_user(user_id) or await bot.fetch_user(user_id)
                        embed = discord.Embed(
                            title='Reminder!',
                            description=message,
                            color=discord.Color.yellow(),
                            timestamp=datetime.datetime.utcnow()
                        )
                        embed.set_footer(text=f'ID: {rid}')
                        await channel.send(f'{user.mention}', embed=embed)
                    except Exception as e:
                        print(f'[reminders] Failed to fire {rid}: {e}')
                    fired.append(rid)
                for rid in fired:
                    c.execute('DELETE FROM reminders WHERE id = ?', (rid,))
                bot.db.commit()
            except Exception as e:
                print(f'[reminders] Loop error: {e}')
            await asyncio.sleep(15)

    asyncio.create_task(_reminder_loop())
