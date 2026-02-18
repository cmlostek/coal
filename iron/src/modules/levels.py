"""modules/levels.py – XP / levelling system (Cog version)."""
import random
import discord
from discord.ext import commands
import os

LEVEL_UP_CHANNEL_ID = int(os.getenv('LEVEL_UP_CHANNEL_ID', '1433244417367605318'))


def _xp_needed(level: int) -> int:
    return int(10 * (1.5 ** (level - 1)))


class Levels(commands.Cog):
    """Passive XP and levelling."""

    def __init__(self, bot):
        self.bot = bot

    # ── XP engine ─────────────────────────────────────────────────────────────

    async def _add_xp(self, user_id: int, amount: int):
        async with self.bot.db.cursor() as cur:
            await cur.execute('INSERT OR IGNORE INTO levels (id, level, xp) VALUES (?, 1, 0)', (user_id,))
            await cur.execute('UPDATE levels SET xp = xp + ? WHERE id = ?', (amount, user_id))
            await cur.execute('SELECT level, xp FROM levels WHERE id = ?', (user_id,))
            row = await cur.fetchone()
            level, xp = row['level'], row['xp']

            levelled_up = False
            while xp >= _xp_needed(level):
                xp   -= _xp_needed(level)
                level += 1
                levelled_up = True

            if levelled_up:
                await cur.execute('UPDATE levels SET level = ?, xp = ? WHERE id = ?', (level, xp, user_id))
        await self.bot.db.commit()

        if levelled_up:
            ch = self.bot.get_channel(LEVEL_UP_CHANNEL_ID)
            if ch:
                user = self.bot.get_user(user_id)
                mention = user.mention if user else f'<@{user_id}>'
                await ch.send(f'🎉 {mention} levelled up to **Level {level}**!')

    # ── Events ────────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        # Skip command invocations
        ctx = await self.bot.get_context(message)
        if ctx.valid:
            return
        await self._add_xp(message.author.id, random.randint(1, 3))

    # ── Commands ──────────────────────────────────────────────────────────────

    @commands.command(name='rank', aliases=['level', 'xp'])
    async def rank(self, ctx, user: discord.Member = None):
        """Display your or another user's level and XP."""
        target = user or ctx.author
        async with self.bot.db.cursor() as cur:
            await cur.execute('SELECT level, xp FROM levels WHERE id = ?', (target.id,))
            row = await cur.fetchone()

        if not row:
            return await ctx.send(f'{target.display_name} hasn\'t earned any XP yet.')

        level  = row['level']
        xp     = row['xp']
        needed = _xp_needed(level)
        total  = sum(_xp_needed(l) for l in range(1, level)) + xp

        # XP bar
        filled = int((xp / needed) * 20)
        bar = '█' * filled + '░' * (20 - filled)

        embed = discord.Embed(title=f'⚡ {target.display_name}\'s Rank', color=discord.Color.blue())
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name='Level', value=str(level), inline=True)
        embed.add_field(name='Progress', value=f'{xp:,} / {needed:,} XP', inline=True)
        embed.add_field(name='Total XP', value=f'{total:,}', inline=True)
        embed.add_field(name='XP Bar', value=f'`[{bar}]`', inline=False)
        await ctx.send(embed=embed)

    @commands.command(name='top', aliases=['lvltop', 'levelboard'])
    async def top(self, ctx):
        """Top 10 users by level."""
        async with self.bot.db.cursor() as cur:
            await cur.execute('SELECT id, level, xp FROM levels ORDER BY level DESC, xp DESC LIMIT 10')
            rows = await cur.fetchall()

        if not rows:
            return await ctx.send('No users on the leaderboard yet.')

        medals = ['🥇', '🥈', '🥉'] + ['🏅'] * 7
        embed = discord.Embed(title='⚡ Level Leaderboard', color=discord.Color.gold())
        for i, row in enumerate(rows):
            try:
                user = ctx.guild.get_member(row['id']) or await self.bot.fetch_user(row['id'])
                name = user.display_name
            except Exception:
                name = f'User {row["id"]}'
            total = sum(_xp_needed(l) for l in range(1, row['level'])) + row['xp']
            embed.add_field(
                name=f'{medals[i]} {name}',
                value=f'Level {row["level"]} — {total:,} total XP',
                inline=False,
            )
        await ctx.send(embed=embed)

    @commands.command(name='resetxp')
    @commands.has_permissions(administrator=True)
    async def reset(self, ctx, user: discord.Member = None):
        """[Admin] Reset a user's XP and level."""
        if user:
            async with self.bot.db.cursor() as cur:
                await cur.execute('UPDATE levels SET level = 1, xp = 0 WHERE id = ?', (user.id,))
            await self.bot.db.commit()
            await ctx.send(f'✅ Reset {user.mention}\'s XP and level.')
        else:
            async with self.bot.db.cursor() as cur:
                await cur.execute('UPDATE levels SET level = 1, xp = 0')
            await self.bot.db.commit()
            await ctx.send('✅ Reset all users\' XP and levels.')


async def setup(bot):
    await bot.add_cog(Levels(bot))
