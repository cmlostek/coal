"""modules/grave.py – Graveyard / death log system (Cog version)."""
import io
import discord
from discord.ext import commands
import os


DEATH_CHANNEL_ID = int(os.getenv('DEATH_CHANNEL_ID', '1436031058469716058'))


class Grave(commands.Cog):
    """Graveyard and death-log commands."""

    def __init__(self, bot):
        self.bot = bot

    def _death_channel(self):
        return self.bot.get_channel(DEATH_CHANNEL_ID)

    # ── Helper: parse user id + reason from *args ─────────────────────────────

    @staticmethod
    def _parse_args(ctx, args):
        if not args:
            return str(ctx.author.id), None

        first = args[0]
        if first == '0' or first.startswith('<@') or first.isdigit():
            raw_id = first
            reason = ' '.join(args[1:]) or None
        else:
            raw_id = str(ctx.author.id)
            reason = ' '.join(args)

        digits = ''.join(ch for ch in raw_id if ch.isdigit())
        user_id_str = digits if digits else ('0' if raw_id == '0' else str(ctx.author.id))
        return user_id_str, reason

    # ── Commands ──────────────────────────────────────────────────────────────

    @commands.command(name='death', aliases=['die', 'd'])
    async def death(self, ctx, *args):
        """
        Log a death.

        Usage:
          `!death` – log your own death
          `!death @user reason` – log someone else's
          `!death 0 reason` – anonymous
        """
        ch = self._death_channel()
        if not ch:
            return await ctx.send(f'❌ Death channel (ID {DEATH_CHANNEL_ID}) not found.')

        user_id_str, reason = self._parse_args(ctx, args)

        async with self.bot.db.cursor() as cur:
            await cur.execute('SELECT MAX(cntr) FROM death_log')
            row = await cur.fetchone()
            num = (row[0] if row and row[0] is not None else 0) + 1
            await cur.execute(
                'INSERT INTO death_log (user_id, cntr, reason) VALUES (?, ?, ?)',
                (user_id_str, num, reason),
            )
        await self.bot.db.commit()

        if user_id_str == '0':
            await ch.send(f'💀 **Death #{num}** — Anonymous\nReason: {reason or "Unknown cause."}')
            await ctx.send('A soul has entered the graveyard anonymously.')
        else:
            mention = f'<@{user_id_str}>'
            msg = f'💀 **Death #{num}** — {mention} has met a terrible fate.'
            if reason:
                msg += f'\nReason: {reason}'
            await ch.send(msg)
            await ctx.send('A new soul has entered the graveyard.')

    @commands.command(name='revive', aliases=['resurrect', 'undeath'])
    async def revive(self, ctx, *args):
        """
        Revive a soul from the graveyard.

        Usage: `!revive [@user] [reason]`
        """
        ch = self._death_channel()
        if not ch:
            return await ctx.send(f'❌ Death channel (ID {DEATH_CHANNEL_ID}) not found.')

        user_id_str, reason = self._parse_args(ctx, args)

        if user_id_str == '0':
            return await ctx.send('Cannot revive anonymous deaths.')

        msg = f'🕊️ <@{user_id_str}> has been revived!'
        if reason:
            msg += f' Reason: {reason}'
        await ch.send(msg)
        await ctx.send('A soul has been revived from the graveyard.')

    @commands.command(name='obit', aliases=['obituary', 'deaths', 'log'])
    async def obit(self, ctx, *args):
        """
        Retrieve a death log.

        Usage:
          `!obit` – your log
          `!obit @user` – someone else's
          `!obit 0` – anonymous deaths
          `!obit -1` – full log as file (admin)
        """
        if not args:
            target = str(ctx.author.id)
        else:
            first = args[0]
            digits = ''.join(ch for ch in first if ch.isdigit())
            target = digits if digits else first  # allows '-1' or '0'

        async with self.bot.db.cursor() as cur:
            # Full log export
            if target == '-1':
                await cur.execute('SELECT user_id, cntr, reason FROM death_log ORDER BY cntr')
                rows = await cur.fetchall()
                if not rows:
                    return await ctx.send('The graveyard is empty.')
                lines = [f'[{r["cntr"]}] ID: {r["user_id"]} | {r["reason"] or "No reason"}' for r in rows]
                fp = io.BytesIO('\n'.join(lines).encode())
                return await ctx.send('📜 Full death log:', file=discord.File(fp, 'death_log.txt'))

            # Anonymous deaths
            elif target == '0':
                await cur.execute("SELECT cntr, reason FROM death_log WHERE user_id = '0' ORDER BY cntr")
                rows = await cur.fetchall()
                if not rows:
                    return await ctx.send('No anonymous deaths.')
                lines = [f'**{r["cntr"]}** — {r["reason"] or "No reason"}' for r in rows]
                embed = discord.Embed(title='💀 Anonymous Deaths', description='\n'.join(lines),
                                      color=discord.Color.dark_red())
                embed.set_footer(text=f'Total: {len(rows)}')
                return await ctx.send(embed=embed)

            # User obituary
            else:
                await cur.execute(
                    'SELECT cntr, reason FROM death_log WHERE user_id = ? ORDER BY cntr DESC',
                    (target,),
                )
                rows = await cur.fetchall()

        if not rows:
            return await ctx.send("They haven't died yet… keep trying! 😉")

        try:
            u = await self.bot.fetch_user(int(target))
            display = str(u)
        except Exception:
            display = f'ID {target}'

        lines = [f'**{r["cntr"]}** — {r["reason"] or "Rest in peace :("}' for r in rows[:10]]
        embed = discord.Embed(
            title=f'💀 Obituary — {display}',
            description='\n'.join(lines),
            color=discord.Color.red(),
        )
        embed.set_footer(text=f'Total deaths: {len(rows)}. Showing last {len(rows[:10])}.')
        await ctx.send(embed=embed)

        if len(rows) >= 100:
            await ctx.send('That is a lot of deaths… 🤯')


async def setup(bot):
    await bot.add_cog(Grave(bot))
